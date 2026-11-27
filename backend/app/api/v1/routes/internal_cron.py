"""The production scheduling entry point.

PRODUCTION SCHEDULING AUTHORITY: Vercel Cron -> GET /tick -> each task.

The `crons` entry in /vercel.json calls GET /internal/cron/tick every five
minutes. The tick runs SCHEDULE in order, each task through the same path as
POST /{task}, and each task decides from its own period and threshold whether
it is due. POST /{task} (X-Cron-Key) stays for one-off runs: the manual
GitHub Actions workflow (.github/workflows/scheduled-maintenance.yml, which no
longer has a schedule) and the admin console's "Run now".

Celery beat was never deployed. Worker and beat exist only in
backend/docker-compose.yml, a development file; production runs the Next.js
frontend and this FastAPI service on Vercel and nothing else. Every periodic
responsibility — including PII retention, which is a legal obligation — was
therefore waiting on a moderator to press a button.

Why not deploy Celery: it would mean a persistent worker, a persistent beat and
a Redis broker, three new always-on services and their cost, to run eight jobs
that between them do a few seconds of work a day. The workload does not justify
the architecture. A scheduler that makes an authenticated HTTP call into the
service that already has the database connection does.

Why Vercel Cron now: it was ruled out while the team was on the Hobby plan,
which allows cron entries at daily granularity only. The team is on Pro, where
one entry every five minutes covers every cadence. GitHub Actions, the
scheduler until then, billed every hourly run as at least a minute and stopped
running entirely during the October 2026 billing hold.


THE STATE MACHINE
-----------------

Two independent things, deliberately not conflated (see app/models/maintenance):

  LOGICAL RUN STATE — `status`, one row per (task, period), forever:

      (none) -> running -> ok            finished in one invocation
             -> running -> continuing    incomplete, idle, resumable
             -> running -> failed        incomplete, idle, progress preserved

  EXECUTION OWNERSHIP — the lease:

      lease_token set, lease_expires_at future  -> someone is executing it
      lease_token NULL                          -> idle, claimable NOW
      lease_expires_at past                     -> abandoned, stealable

`continuing` is "incomplete but idle", so the scheduler's very next call
resumes it immediately. There is no waiting period on the normal path; lease
expiry only governs recovery from a request that died.

Transitions, and what each returns to the scheduler:

    no row, due                -> claim (INSERT)          -> ok | continuing
    continuing, lease NULL     -> reclaim (UPDATE)        -> ok | continuing
    failed, lease NULL         -> reclaim (UPDATE)        -> ok | continuing
    running, lease live        -> refused                 -> already_running
    running, lease expired     -> steal (UPDATE, fenced)  -> ok | continuing
    ok                         -> refused                 -> already_completed
    not yet due                -> refused                 -> not_due

WHY NOT ADVISORY LOCKS. The application connects through the Supabase
TRANSACTION pooler — documented in app/db/session.py, because the session
pooler accepts only about four concurrent clients. PgBouncer in transaction
mode hands the backend back at every commit, so a session-level lock taken in
one transaction can be released on a different backend, or not at all. The
sweep services commit internally, several times. A dedicated SQLAlchemy
connection would not help, because the multiplexing is beneath SQLAlchemy.

So ownership is a lease taken by ONE conditional UPDATE. The database picks the
winner: a second runner blocks on the row lock, re-evaluates the predicate once
the first commits, sees a live lease, and matches zero rows. Single statement,
single transaction — exactly the property pooling cannot undermine.

FENCING. Every write an executing request makes is conditioned on
`lease_token = <mine>`. A request that stalled past its expiry, was taken over,
and then woke up matches zero rows and cannot overwrite the newer owner's
cursor. Without this, time-based takeover would be a data-loss mechanism.

Everything here is deliberately narrow:

  * only names in TASKS may be invoked; the path is not a function reference
  * the caller supplies no cursor, offset or batch size — the backend owns
    progression entirely, so the credential cannot be used to skip a population
  * every invocation is recorded in `cron_runs`, success, refusal or failure;
    the one exception is the tick's not-due and already-completed skips,
    which would otherwise add a dozen rows every five minutes
  * failures record an exception CLASS, never a message
  * monthly jobs are evaluated by logical PERIOD, not by "is today the 1st",
    so a scheduler that misses a day still completes the period
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import BaseModel
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.maintenance import CronCredential, CronRun

log = get_logger(__name__)

router = APIRouter(prefix="/internal/cron", tags=["internal: scheduled maintenance"])

CREDENTIAL_NAME = "scheduler"


# --- Time budget -------------------------------------------------------------
#
# CONSERVATIVE APPLICATION BUDGET — NOT A PLATFORM MAXIMUM.
#
# Set when the team was on the Hobby plan and the function's duration ceiling
# could not be read. The backend now declares `maxDuration: 300` in
# vercel.json (the documented Pro default), so this is far below the ceiling;
# it stays small because it is the size of one slice of a sweep, and a tick
# runs as many slices as its own budget (TICK_BUDGET below) allows. Raise it
# with SCHEDULER_REQUEST_BUDGET_SECONDS rather than editing this line.
#
# A too-small budget costs extra invocations. It never costs correctness: the
# cursor is persisted every batch and the traversal resumes exactly where it
# stopped.
_DEFAULT_BUDGET_SECONDS = 8.0
REQUEST_BUDGET = timedelta(
    seconds=float(os.getenv("SCHEDULER_REQUEST_BUDGET_SECONDS",
                            _DEFAULT_BUDGET_SECONDS)))

#: How long a lease is honoured before another runner may steal it.
#:
#: This must comfortably EXCEED the request budget, or a healthy invocation
#: could be preempted while it is still working — which is what the fencing
#: token would then have to clean up after, every night. At a 8s budget this is
#: a ~37x margin, which also covers request start-up, the final persist and the
#: HTTP response. Because one invocation cannot approach the lease lifetime,
#: no lease heartbeat is needed; shortening the workload is the simpler bound.
LEASE = timedelta(minutes=5)

#: The whole of one Vercel Cron tick (GET /tick), across every task it runs.
#:
#: Each task call inside a tick still gets the per-request budget above, cut
#: down to whatever is left of this. The backend function's ceiling is the
#: `maxDuration` in vercel.json (300s), so this leaves room for the simple
#: tasks, which do not watch a budget, to run past it. Raise it with
#: SCHEDULER_TICK_BUDGET_SECONDS rather than editing this line.
_DEFAULT_TICK_BUDGET_SECONDS = 40.0
TICK_BUDGET = timedelta(
    seconds=float(os.getenv("SCHEDULER_TICK_BUDGET_SECONDS",
                            _DEFAULT_TICK_BUDGET_SECONDS)))


class Budget:
    """Wall-clock allowance for one invocation's processing.

    Monotonic, so a clock adjustment cannot extend or collapse it.
    """

    __slots__ = ("deadline",)

    def __init__(self, allowance: timedelta = REQUEST_BUDGET):
        self.deadline = time.monotonic() + allowance.total_seconds()

    def spent(self) -> bool:
        return time.monotonic() >= self.deadline

    def remaining(self) -> timedelta:
        return timedelta(seconds=max(0.0, self.deadline - time.monotonic()))


#: TEST SEAM. Overrides every task's batch capacity so a multi-batch traversal
#: can be exercised against a handful of real records instead of hundreds.
#: Deliberately module state and NOT a request parameter — see the test that
#: asserts `run_task` accepts no cursor, offset or batch argument. A caller who
#: could choose the batch size could also choose to process one record and
#: report the period continuing forever.
_BATCH_OVERRIDE: int | None = None

#: Same seam for the time budget, so a test can prove the budget — not the
#: record count — is what stopped a batch.
_BUDGET_OVERRIDE: timedelta | None = None

#: Same seam for the tick budget.
_TICK_BUDGET_OVERRIDE: timedelta | None = None


def _now() -> datetime:
    return datetime.now(MANILA)


class TaskSpec:
    """One schedulable job: what it does, when its work belongs to, and whether
    it can finish inside a single request.

    CADENCE. No scheduler guarantees delivery: Vercel Cron, like the GitHub
    Actions schedule before it, can be late, dropped, retried or overlapped.
    Keying eligibility off "is today the 1st in Manila" means one missed
    invocation postpones a monthly job by a month. So each job has a logical
    PERIOD ("2026-08-29" daily, "2026-08" monthly, always Asia/Manila) and a
    THRESHOLD, and eligibility is "the threshold has passed and this period is
    not already done or in flight" — which catches up instead of skipping.

    SHAPE. Some jobs are one set-based statement and finish in milliseconds.
    Others recompute a population one record at a time; CI measured the trust
    sweep at 82 minutes against ~7,000 users, which no serverless request
    survives. Those declare a `sweep`, and are traversed across as many
    invocations as it takes, the period completing only when the whole
    population has been covered.
    """

    def __init__(self, run=None, *, sweep=None, batch: int = 250,
                 cadence: str, hour: int, minute: int = 0,
                 day_of_month: int | None = None, weekday: int = 0, note: str = ""):
        assert (run is None) != (sweep is None), "a task is either simple or a sweep"
        self.run = run
        self.sweep = sweep
        self.batch = batch
        self.cadence = cadence
        self.hour = hour
        self.minute = minute
        self.day_of_month = day_of_month
        #: weekly cadence: 0 = Monday (ISO weeks, Manila).
        self.weekday = weekday
        self.note = note

    @property
    def resumable(self) -> bool:
        return self.sweep is not None

    def capacity(self) -> int:
        return _BATCH_OVERRIDE if _BATCH_OVERRIDE is not None else self.batch

    def period(self, now: datetime) -> str:
        """The logical run this invocation belongs to, in Manila."""
        local = now.astimezone(MANILA)
        if self.cadence == "hourly":
            return local.strftime("%Y-%m-%dT%H")
        if self.cadence == "weekly":
            year, week, _ = local.isocalendar()
            return f"{year}-W{week:02d}"
        return (local.strftime("%Y-%m") if self.cadence == "monthly"
                else local.strftime("%Y-%m-%d"))

    def threshold(self, now: datetime) -> datetime:
        """When the current period became due, in Manila."""
        local = now.astimezone(MANILA)
        if self.cadence == "hourly":
            # Due from `minute` past every hour; `hour` is unused.
            return local.replace(minute=self.minute, second=0, microsecond=0)
        if self.cadence == "weekly":
            start = local - timedelta(days=local.weekday() - self.weekday)
            return start.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        day = self.day_of_month if self.cadence == "monthly" else local.day
        return local.replace(day=day, hour=self.hour, minute=self.minute,
                             second=0, microsecond=0)

    def is_due(self, now: datetime) -> bool:
        return now.astimezone(MANILA) >= self.threshold(now)

    def next_threshold(self, now: datetime) -> datetime:
        """When the next period becomes due: this period's threshold if it is
        still ahead, otherwise the following period's (Overlay/Admin/Jobs
        "Next in 20h")."""
        local = now.astimezone(MANILA)
        current = self.threshold(local)
        if local < current:
            return current
        if self.cadence == "hourly":
            return current + timedelta(hours=1)
        if self.cadence == "weekly":
            return current + timedelta(days=7)
        if self.cadence == "monthly":
            if local.month == 12:
                return current.replace(year=local.year + 1, month=1)
            return current.replace(month=local.month + 1)
        return current + timedelta(days=1)


def _expire_requests(db: Session) -> int:
    from app.services.request_service import expire_open_requests
    return int(expire_open_requests(db) or 0)


def _integrity_sweep(db: Session) -> int:
    """Business Rules §12: automated signals become SYSTEM_DETECTED reports.

    Replaces the retired contract sweep: revenue-share contracts no longer
    exist (§14), so there is nothing to renew or expire."""
    from app.services.integrity_sweep import sweep
    return int((sweep(db) or {}).get("filed", 0))


def _pii_retention(db: Session) -> int:
    """Uses the retention policy already configured — no new duration here.

    Set-based: three UPDATE/DELETE statements over rows past their retention
    horizon, with no Python loop and no per-record round trip. It does not need
    the continuation protocol, and giving it one would be complexity for its
    own sake.
    """
    from app.services.retention_service import run_retention_sweep
    counts = run_retention_sweep(db) or {}
    return sum(int(v) for v in counts.values())


def _sweep_trust(db: Session, cursor, batch, snapshot_at, budget):
    """Full production population, traversed across invocations. No limit on
    who is eligible and no sampling — only where this batch stops."""
    from app.services.sweep_service import sweep_trust
    return sweep_trust(db, cursor, batch, snapshot_at, budget)


def _sweep_wilson(db: Session, cursor, batch, snapshot_at, budget):
    from app.services.sweep_service import sweep_wilson
    return sweep_wilson(db, cursor, batch, snapshot_at, budget)


def _refresh_payout_batches(db: Session) -> int:
    """Poll in-flight batches and settle them, exactly as the beat task did.

    Loops, but over DISTINCT batch ids that are currently processing — a
    handful at most, and bounded by how many batches can be in flight rather
    than by how many users exist.
    """
    from sqlalchemy import select as _select

    from app.models.enums import PayoutStatus
    from app.models.payout import Payout
    from app.services.payout_service import refresh_batch

    batches = db.scalars(_select(Payout.batch_id).where(
        Payout.status == PayoutStatus.processing).distinct()).all()
    refreshed = 0
    for batch in batches:
        if batch:
            refresh_batch(db, batch)
            refreshed += 1
    return refreshed


def _honesty_fund(db: Session) -> int:
    """Idempotent by design: an already-distributed cycle aborts.

    NOT resumable, deliberately. It divides a fixed pool proportionally across
    every eligible review — `payout = pool * score / total_score` — so it must
    see the whole population in one pass. A half-visible population would
    compute wrong shares for everyone, which is far worse than taking longer.
    Its size is bounded by honesty-fund-eligible reviews in one month, not by
    the user table.
    """
    from app.core.config import settings
    from app.services.honesty_fund_service import distribute
    if not settings.honesty_fund_distribution_enabled:
        return 0  # §14: formula pending an owner decision; the pool still accrues.
    result = distribute(db) or {}
    return int(result.get("recipients", 0) or result.get("distributed", 0) or 0)


def _priority_tiers(db: Session) -> int:
    """Admin queue priority tiers (dev note 2026-09-26): age items left
    untouched past the window one tier, and refresh every queued item's tier.

    Hourly, and never on a page load: an escalation that waited for someone to
    open the dashboard would defeat the point of it. Set-sized by the two open
    queues, not by the user table, so one pass suffices. Changes no item's
    queue membership.
    """
    from app.services.priority_triage import recalculate
    return int(recalculate(db).get("items", 0))


def _reconcile_admin_upvotes(db: Session) -> int:
    """One-time backfill (owner, 2026-10-06), run by hand: an administrator's
    or super admin's upvote now nominates the review for the earnings queue;
    this applies that to the upvotes cast before it did. Idempotent — a review
    is only ever lifted from `none` to `pending`, so a second run queues
    nothing. Approves nothing and pays nothing."""
    from app.services.earn_gate import reconcile_staff_upvotes
    return reconcile_staff_upvotes(db)


def _schedule_payouts(db: Session) -> int:
    """Reserve wallet balances into a payout batch — preparation only.

    DELIBERATE DIFFERENCE from the old beat task, which followed scheduling
    with `submit_batch`. Automating internal ledger preparation is safe;
    automating the hand-off to a payment provider is a different decision, and
    turning a step a moderator used to take into one that happens unattended is
    not something a scheduler change should do quietly. Submission stays where
    it already is: POST /admin/payouts/run, a moderator action, through the
    same service call.

    (Submission is externally blocked regardless — no sandbox credentials — but
    the reason this is preparation-only is the policy, not the blocker.)

    NOT resumable: it orders candidates by tier priority across the whole
    eligible set, and its population is users already above the payout
    threshold. Duplicate protection is the `uq_payout_user_batch` constraint,
    not this route.
    """
    from app.services.payout_service import schedule_payouts
    result = schedule_payouts(db) or {}
    return int(result.get("scheduled", 0) or 0)


def _send_emails(db: Session) -> int:
    """The email outbox (0085): send notification emails and summaries that are due,
    retry failures with backoff, purge settled rows past 30 days. Hourly."""
    from app.services.email_outbox_service import drain
    return int(drain(db).get("sent", 0))


def _weekly_summaries(db: Session) -> int:
    """Queue the Monday summary for every claimed store whose owner has it on.
    `send_emails` sends them (deduplicated per store and ISO week)."""
    from app.services.weekly_summary_service import enqueue_all
    return enqueue_all(db)


#: The allow-list. A name not in here cannot be invoked, and the path segment
#: is matched against these keys rather than resolved to anything.
TASKS: dict[str, TaskSpec] = {
    "pii_retention": TaskSpec(
        _pii_retention, cadence="daily", hour=3, note="daily 03:00 Manila"),
    "recompute_wilson_scores": TaskSpec(
        sweep=_sweep_wilson, cadence="daily", hour=4, note="daily 04:00 Manila"),
    "recompute_all_trust": TaskSpec(
        sweep=_sweep_trust, cadence="daily", hour=4, minute=30,
        note="daily 04:30 Manila"),
    "integrity_sweep": TaskSpec(
        _integrity_sweep, cadence="daily", hour=5, note="daily 05:00 Manila"),
    "expire_requests": TaskSpec(
        _expire_requests, cadence="daily", hour=5, minute=30, note="daily 05:30 Manila"),
    "refresh_payout_batches": TaskSpec(
        _refresh_payout_batches, cadence="daily", hour=6, note="daily 06:00 Manila"),
    "honesty_fund_distribution": TaskSpec(
        _honesty_fund, cadence="monthly", day_of_month=1, hour=2,
        note="1st of the month, 02:00 Manila"),
    "schedule_payouts": TaskSpec(
        _schedule_payouts, cadence="monthly", day_of_month=5, hour=2, minute=30,
        note="5th of the month, 02:30 Manila"),
    "priority_tiers": TaskSpec(
        _priority_tiers, cadence="hourly", hour=0, minute=15, note="hourly, :15"),
    "send_emails": TaskSpec(
        _send_emails, cadence="hourly", hour=0, minute=20, note="hourly, :20"),
    # Manual only (workflow_dispatch, admin "Run now"): not in SCHEDULE. Hourly
    # period so it can be re-run within the day; every run is idempotent.
    "reconcile_admin_upvotes": TaskSpec(
        _reconcile_admin_upvotes, cadence="hourly", hour=0, minute=0,
        note="manual backfill; idempotent"),
    "weekly_summaries": TaskSpec(
        _weekly_summaries, cadence="weekly", weekday=0, hour=8,
        note="Mondays, 08:00 Manila"),
}

#: What a Vercel Cron tick runs, in this order. It is the order the GitHub
#: Actions SCHEDULE used, which the ordering guarantees were written against
#: (Wilson before trust: Wilson scores feed trust progression). Due-ness is
#: still each task's own period and threshold; the tick calls everything and
#: the task decides.
#:
#: `reconcile_admin_upvotes` is left out on purpose. It is a one-time manual
#: backfill and the workflow never scheduled it either.
SCHEDULE: tuple[str, ...] = (
    "priority_tiers",
    "send_emails",
    "honesty_fund_distribution",
    "schedule_payouts",
    "pii_retention",
    "recompute_wilson_scores",
    "recompute_all_trust",
    "integrity_sweep",
    "expire_requests",
    "refresh_payout_batches",
    "weekly_summaries",
)

#: LOGICAL RUN STATE.
OK = "ok"
FAILED = "failed"
RUNNING = "running"
CONTINUING = "continuing"
#: States a new invocation may take over. `ok` is absent: it is terminal.
CLAIMABLE = (RUNNING, CONTINUING, FAILED)

#: REFUSALS. Distinct, so "nothing happened" is never ambiguous — a scheduler
#: that has stopped must not look like one that is merely early.
NOT_DUE = "skipped_not_due"
ALREADY_DONE = "skipped_already_completed"
ALREADY_RUNNING = "skipped_already_running"


@dataclass
class Claim:
    """Proof that this invocation owns the logical run, plus its progress."""

    id: uuid.UUID
    token: uuid.UUID
    cursor: str | None
    processed_total: int
    snapshot_at: datetime | None


class CronResult(BaseModel):
    task: str
    status: str
    period: str | None = None
    processed: int | None = None
    #: Total across every batch of this period, not just this invocation.
    processed_total: int | None = None
    #: True when the scheduler should call again to continue the traversal.
    more: bool = False
    detail: str | None = None
    run_id: str | None = None


class TickTask(BaseModel):
    """One task's part in a tick. Same rule as CronResult: no identifiers."""

    task: str
    status: str
    #: Records handled across every call this tick made to the task.
    processed: int | None = None
    #: True when the task is a sweep that still has records left.
    more: bool = False
    calls: int = 1


class TickResult(BaseModel):
    tasks: list[TickTask]
    #: True when the tick ran out of budget before reaching every task. The
    #: rest wait for the next tick, in order.
    stopped: bool = False


def _check_secret(db: Session, presented: str | None) -> None:
    """Compare a presented scheduler secret with the stored digest.

    Both scheduler routes use this, so the X-Cron-Key header and Vercel
    Cron's Bearer header are checked against the same `cron_credentials`
    row. Comparison is constant time, and a missing credential row fails
    closed.
    """
    if not presented:
        raise HTTPException(status_code=401, detail="Scheduler credential required.")

    try:
        row = db.scalar(select(CronCredential).where(
            CronCredential.name == CREDENTIAL_NAME,
            CronCredential.is_active.is_(True)))
    except Exception:  # noqa: BLE001 - table absent until migration 0034 is applied
        db.rollback()
        log.warning("scheduler credential table unavailable; refusing")
        raise HTTPException(
            status_code=503,
            detail="Scheduler credential is not configured.") from None

    if row is None:
        # Fail closed: no configured credential means nothing may run.
        raise HTTPException(status_code=503, detail="Scheduler credential is not configured.")

    digest = hashlib.sha256(presented.encode()).hexdigest()
    if not hmac.compare_digest(digest, row.secret_sha256):
        raise HTTPException(status_code=401, detail="Scheduler credential rejected.")


def require_scheduler(
    db: Session = Depends(get_db),
    x_cron_key: str | None = Header(default=None, alias="X-Cron-Key"),
) -> None:
    """Authenticate the scheduler on POST /{task}.

    The secret arrives in a header, never a query string, so it cannot end up
    in an access log or a browser history.
    """
    _check_secret(db, x_cron_key)


def require_vercel_cron(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> None:
    """Authenticate Vercel Cron on GET /tick.

    Vercel sends the project's CRON_SECRET as `Authorization: Bearer <secret>`.
    It must be the same secret the `scheduler` credential row was made from.
    A user's access token in the same header is just a wrong secret.
    """
    scheme, _, secret = (authorization or "").partition(" ")
    _check_secret(db, secret.strip() if scheme.lower() == "bearer" else None)


@router.post("/{task}", response_model=CronResult, dependencies=[Depends(require_scheduler)],
             summary="Run one scheduled maintenance task")
def run_task(
    task: str = Path(...),
    db: Session = Depends(get_db),
    source: str = "scheduler",
) -> CronResult:
    """Take the execution lease on this task's current period and do as much of
    it as the time budget allows.

    Note the signature: no cursor, no offset, no batch size. Progression is
    entirely the backend's, so possession of the scheduler credential does not
    confer the ability to steer or truncate a traversal.
    """
    spec = TASKS.get(task)
    if spec is None:
        # Do not echo the requested name into the response body.
        raise HTTPException(status_code=404, detail="Unknown maintenance task.")

    result = _execute(db, task, spec, source,
                      allowance=REQUEST_BUDGET if _BUDGET_OVERRIDE is None
                      else _BUDGET_OVERRIDE)
    if result.status == FAILED:
        raise HTTPException(status_code=500, detail=result.detail)
    return result


@router.get("/tick", response_model=TickResult,
            dependencies=[Depends(require_vercel_cron)],
            summary="Run every scheduled maintenance task that is due (Vercel Cron)")
def tick(response: Response, db: Session = Depends(get_db)) -> TickResult:
    """Vercel Cron calls this every five minutes. It runs SCHEDULE in order,
    each task through the same path as POST /{task}.

    * A task that is not due, or already done this period, is skipped and
      writes no `cron_runs` row: at twelve tasks every five minutes those
      rows would bury the ones that matter. Every other outcome is recorded
      as POST /{task} records it.
    * A sweep that answers `continuing` is called again while the tick has
      budget. If the budget runs out first the tick stops there, so a later
      task never starts ahead of an earlier one that is still running (Wilson
      finishes before trust).
    * A failed task is recorded and the tick moves on, as the workflow did.
      The tick then answers 500 so the failure shows in Vercel's cron log.
    """
    tick_budget = Budget(TICK_BUDGET if _TICK_BUDGET_OVERRIDE is None
                         else _TICK_BUDGET_OVERRIDE)
    per_call = REQUEST_BUDGET if _BUDGET_OVERRIDE is None else _BUDGET_OVERRIDE
    attempted: list[TickTask] = []
    stopped = failed = False

    for task in SCHEDULE:
        spec = TASKS[task]
        entry: TickTask | None = None
        while True:
            if tick_budget.spent():
                stopped = True
                break
            result = _execute(db, task, spec, "vercel-cron",
                              allowance=min(per_call, tick_budget.remaining()),
                              record_skips=False)
            if entry is None:
                entry = TickTask(task=task, status=result.status,
                                 processed=result.processed, more=result.more)
                attempted.append(entry)
            else:
                entry.calls += 1
                entry.status, entry.more = result.status, result.more
                if result.processed is not None:
                    entry.processed = (entry.processed or 0) + result.processed
            if result.status != CONTINUING:
                break
        if stopped:
            break
        if entry is not None and entry.status == FAILED:
            failed = True

    if failed:
        response.status_code = 500
    return TickResult(tasks=attempted, stopped=stopped)


def _execute(db: Session, task: str, spec: TaskSpec, source: str, *,
             allowance: timedelta, record_skips: bool = True) -> CronResult:
    """One invocation of one task: the body both scheduler routes share.

    Never raises for a task failure; it answers `failed` and the caller
    decides what that means for its response. `record_skips=False` leaves
    out the `cron_runs` row for `not_due` and `already_completed`, and only
    for those.
    """
    now = _now()
    period = spec.period(now)
    due_at = spec.threshold(now)

    if not spec.is_due(now):
        if record_skips:
            _record(db, task, source, NOT_DUE, period, due_at,
                    detail=f"due {due_at:%Y-%m-%d %H:%M} Manila")
        return CronResult(task=task, status=NOT_DUE, period=period,
                          detail="not due yet")

    # A finished period is the common case for every call but the first. Read
    # it before trying to claim: the claim would only reach the same answer
    # through a refused INSERT, which Postgres logs as an error each time.
    existing = _existing(db, task, period)
    claim = None if existing == OK else _claim(db, task, source, period, due_at)
    if claim is None:
        if existing != OK:
            existing = _existing(db, task, period)
        status = ALREADY_DONE if existing == OK else ALREADY_RUNNING
        if record_skips or status != ALREADY_DONE:
            _record(db, task, source, status, period, due_at,
                    detail="period already completed" if status == ALREADY_DONE
                    else "another runner holds the lease")
        return CronResult(task=task, status=status, period=period,
                          detail="already completed" if status == ALREADY_DONE
                          else "already running")

    budget = Budget(allowance)
    try:
        if spec.resumable:
            result = spec.sweep(db, claim.cursor, spec.capacity(),
                                claim.snapshot_at, budget)
            total = claim.processed_total + result.processed

            if result.complete:
                _release(db, claim, OK, cursor=None,
                         processed=result.processed, total=total)
                log.info("scheduled sweep complete",
                         extra={"extra_fields": {"task": task, "period": period,
                                                 "processed_total": total}})
                return CronResult(task=task, status=OK, period=period,
                                  processed=result.processed, processed_total=total,
                                  run_id=str(claim.id))

            # Incomplete. Persist progress and RELEASE the lease: `continuing`
            # means idle, so the scheduler's next call resumes it at once
            # rather than waiting out an expiry.
            _release(db, claim, CONTINUING, cursor=result.cursor,
                     processed=result.processed, total=total)
            return CronResult(task=task, status=CONTINUING, period=period,
                              processed=result.processed, processed_total=total,
                              more=True, run_id=str(claim.id),
                              detail="more records remain")

        processed = spec.run(db)
        db.commit()
        _release(db, claim, OK, cursor=None, processed=processed, total=processed)
        log.info("scheduled maintenance ok",
                 extra={"extra_fields": {"task": task, "period": period,
                                         "processed": processed}})
        return CronResult(task=task, status=OK, period=period,
                          processed=processed, processed_total=processed,
                          run_id=str(claim.id))

    except Exception as exc:  # noqa: BLE001 - recorded and reported, never swallowed
        db.rollback()
        failure = type(exc).__name__
        log.exception("scheduled maintenance failed",
                      extra={"extra_fields": {"task": task, "period": period}})
        # PRESERVE PROGRESS. The cursor stays where the last completed batch
        # left it, so a retry resumes rather than restarting the population.
        # The batch that failed is rolled back and will be replayed; that is
        # safe because the per-record work is a recomputation from source data,
        # which lands on the same value however many times it runs.
        _release(db, claim, FAILED, cursor=claim.cursor, processed=0,
                 total=claim.processed_total, failure=failure)
        # The class, not the message: a message can carry row data.
        return CronResult(task=task, status=FAILED, period=period,
                          processed=0, processed_total=claim.processed_total,
                          run_id=str(claim.id), detail=f"Task failed: {failure}")


def _claim(db: Session, task: str, source: str, period: str,
           due_at: datetime) -> Claim | None:
    """Take the execution lease on this period, or None if someone holds it.

    Two statements, each atomic on its own; no read-then-write anywhere.
    """
    token = uuid.uuid4()
    now = _now()
    expires = now + LEASE

    try:
        # 1. RECLAIM an existing incomplete run whose lease is free or expired.
        #
        #    This single UPDATE is the arbitration. Two concurrent runners
        #    cannot both win: the second blocks on the row lock, re-reads the
        #    row after the first commits, finds `lease_expires_at` in the
        #    future, and updates nothing. `lease_expires_at IS NULL` is the
        #    normal continuation path — a released `continuing` row is
        #    claimable immediately, with no delay of any kind.
        row = db.execute(
            update(CronRun)
            .where(CronRun.task == task,
                   CronRun.period == period,
                   CronRun.status.in_(CLAIMABLE),
                   or_(CronRun.lease_expires_at.is_(None),
                       CronRun.lease_expires_at <= now))
            .values(status=RUNNING, lease_token=token, lease_acquired_at=now,
                    lease_expires_at=expires, claimed_at=now, failure=None)
            .returning(CronRun.id, CronRun.cursor, CronRun.processed_total,
                       CronRun.snapshot_at)
            .execution_options(synchronize_session=False)
        ).first()
        db.commit()
        if row is not None:
            return Claim(id=row[0], token=token, cursor=row[1],
                         processed_total=row[2] or 0, snapshot_at=row[3])

        # 2. No incomplete row to take over, so this period has either never
        #    run or is finished. Create it; the unique index decides.
        #
        #    `snapshot_at` is captured HERE, once per logical run, and is never
        #    rewritten — it is the traversal's fixed upper boundary.
        run = CronRun(task=task, source=source, status=RUNNING, period=period,
                      scheduled_for=due_at, started_at=now, claimed_at=now,
                      processed_total=0, snapshot_at=now,
                      lease_token=token, lease_acquired_at=now,
                      lease_expires_at=expires)
        db.add(run)
        db.commit()
        return Claim(id=run.id, token=token, cursor=None, processed_total=0,
                     snapshot_at=run.snapshot_at)

    except IntegrityError:
        # The unique index refused it: the period is complete, or another
        # runner created it between our UPDATE and our INSERT. Mechanism
        # working as designed.
        db.rollback()
        return None
    except Exception:  # noqa: BLE001 - tables absent before the migrations land
        db.rollback()
        log.exception("could not claim scheduled period",
                      extra={"extra_fields": {"task": task, "period": period}})
        return None


def _existing(db: Session, task: str, period: str) -> str | None:
    """The status of whatever already holds this period."""
    try:
        return db.scalar(
            select(CronRun.status).where(
                CronRun.task == task, CronRun.period == period,
                CronRun.status.in_((*CLAIMABLE, OK))).limit(1))
    except Exception:  # noqa: BLE001
        db.rollback()
        return None


def _release(db: Session, claim: Claim, status: str, *, cursor: str | None,
             processed: int, total: int, failure: str | None = None) -> bool:
    """Persist this invocation's progress and give up the lease. Never raises.

    THE FENCE. Every field is written by one UPDATE conditioned on our own
    lease token. If the lease has since been stolen — because this request
    stalled past its expiry — the WHERE matches nothing, we write nothing, and
    the newer owner's cursor survives untouched. An expired request cannot
    resurrect its own view of the world.
    """
    try:
        result = db.execute(
            update(CronRun)
            .where(CronRun.id == claim.id, CronRun.lease_token == claim.token)
            .values(status=status, cursor=cursor, processed=processed,
                    processed_total=total, finished_at=_now(), failure=failure,
                    lease_token=None, lease_acquired_at=None,
                    lease_expires_at=None)
            .execution_options(synchronize_session=False))
        db.commit()
        if result.rowcount != 1:
            # Not an error we can fix here, but it must never be silent: it
            # means this request ran past its lease and something else took the
            # work over.
            log.warning("scheduler write fenced out; a newer owner holds this run",
                        extra={"extra_fields": {"run_id": str(claim.id),
                                                "attempted_status": status}})
            return False
        return True
    except Exception:  # noqa: BLE001 - bookkeeping must not break the task
        db.rollback()
        log.exception("could not close scheduled run",
                      extra={"extra_fields": {"run_id": str(claim.id),
                                              "status": status}})
        return False


def _record(db: Session, task: str, source: str, status: str,
            period: str | None = None, scheduled_for: datetime | None = None, *,
            processed: int | None = None, failure: str | None = None,
            detail: str | None = None,
            started: datetime | None = None) -> str:
    """Write a non-claiming audit row — the refusals. Never raises.

    These take no lease and stay outside the unique index: a refusal is a note
    that the scheduler called and was turned away, not a claim on the period.
    They are what makes "the scheduler is alive but everything is already done"
    distinguishable from "the scheduler stopped calling".
    """
    try:
        now = _now()
        run = CronRun(task=task, source=source, status=status, period=period,
                      scheduled_for=scheduled_for,
                      started_at=started or now, finished_at=now,
                      processed=processed, processed_total=processed or 0,
                      failure=failure, detail=detail)
        db.add(run)
        db.commit()
        return str(run.id)
    except Exception:  # noqa: BLE001 - history must not break the task itself
        db.rollback()
        log.exception("could not record scheduled run",
                      extra={"extra_fields": {"task": task, "status": status}})
        return ""

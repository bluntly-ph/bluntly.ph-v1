"""The production scheduler's entry point.

This route is the only thing standing between an unauthenticated caller and
eight maintenance jobs that mutate production data, so most of what follows is
about refusing people rather than about running tasks.

The tasks themselves keep their own coverage elsewhere; here the questions are:
who may invoke them, what may be invoked, what happens when two invocations
overlap, and whether anything sensitive leaks into a response or a run record.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.v1.routes import internal_cron
from tests.conftest import register_and_token, requires_db

CRON = "/api/v1/internal/cron"
SECRET = "test-scheduler-secret-not-used-anywhere-else"


@pytest.fixture
def scheduler_credential(db):
    """A live credential row, deleted again when the test ends.

    `name` is unique and the isolated CI database is cumulative. A run that is
    cancelled mid-test (any push cancels the one in progress) never reaches the
    teardown below, and the row it leaves makes every later insert here a
    UniqueViolation — 58 setup errors in run 34761871674. So a leftover is
    cleared first; this is the test database only (BLUNTLY_TEST_ENV).
    """
    from app.models.maintenance import CronCredential

    db.query(CronCredential).filter(
        CronCredential.name == internal_cron.CREDENTIAL_NAME).delete()
    db.commit()
    row = CronCredential(
        name=internal_cron.CREDENTIAL_NAME,
        secret_sha256=hashlib.sha256(SECRET.encode()).hexdigest(),
        is_active=True,
    )
    db.add(row)
    db.commit()          # the API opens its own session and must see it
    yield row
    db.delete(row)
    db.commit()


@pytest.fixture(autouse=True)
def _due_clock():
    """Run route tests after every daily threshold, independent of CI time.

    The scheduler correctly refuses a task before its Manila wall-clock
    threshold.  A suite that happens to start at 01:00 Manila therefore cannot
    use the real clock for tests whose subject is claims, retries, or task
    effects.  Keep the real Manila *date* so period assertions agree, but pin
    the time to 06:30 — after the final daily task is due.

    This deliberately assigns/restores directly instead of using pytest's
    ``monkeypatch`` fixture: two retry tests call ``monkeypatch.undo()`` to
    restore a temporary TaskSpec, and that must not also restore the wall
    clock halfway through the test.
    """
    from app.core.constants import MANILA

    original = internal_cron._now
    today = datetime.now(MANILA).date()
    fixed = datetime(
        today.year, today.month, today.day, 6, 30, tzinfo=MANILA,
    ).astimezone(UTC)
    internal_cron._now = lambda: fixed
    try:
        yield
    finally:
        internal_cron._now = original


@pytest.fixture(autouse=True)
def _an_unclaimed_period(request, _due_clock):
    """Give every test in this module a period nobody has claimed yet.

    These tests drive REAL task names, and the entire point of the claim is
    that a logical period can be completed exactly once. So the first test to
    call `expire_requests` legitimately consumes today's period, and every
    later test is correctly told the work is already done — the mechanism
    working as designed, but it makes the whole file order-dependent.

    That is a second, independent cause of the CI failures here, separate from
    the model/schema drift: `test_a_failed_period_may_be_retried` could not
    even reach its 500, because the period was already `ok` before it started.

    Scoped to the current period of the declared tasks, so it clears exactly
    what this module creates and leaves earlier run history alone.

    Autouse, so it must not drag the `db` fixture onto the tests in this file
    that need no database — on a machine with no Postgres that does not skip,
    it hangs on connect.
    """
    from app.models.maintenance import CronRun
    from tests.conftest import DB_AVAILABLE

    if not DB_AVAILABLE:
        yield
        return

    db = request.getfixturevalue("db")

    def clear() -> None:
        now = internal_cron._now()
        names = tuple(internal_cron.TASKS)
        periods = tuple({spec.period(now) for spec in internal_cron.TASKS.values()})
        db.query(CronRun).filter(
            CronRun.task.in_(names), CronRun.period.in_(periods),
        ).delete(synchronize_session=False)
        db.commit()

    clear()
    yield
    clear()


# --- Who may invoke -------------------------------------------------------

@requires_db
def test_no_credential_header_is_refused(client):
    resp = client.post(f"{CRON}/expire_requests")
    assert resp.status_code == 401


@requires_db
def test_a_wrong_secret_is_refused(client, scheduler_credential):
    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": "not-the-secret"})
    assert resp.status_code == 401


@requires_db
def test_a_moderator_session_is_not_a_scheduler_credential(client, scheduler_credential):
    """Role and scheduler identity are different things. A moderator token must
    not open the maintenance endpoint just because it opens /admin."""
    _, token, _ = register_and_token(client, role="administrator")
    resp = client.post(f"{CRON}/expire_requests",
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@requires_db
def test_the_correct_secret_is_accepted(client, scheduler_credential):
    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 200, resp.text
    assert resp.json()["task"] == "expire_requests"


@requires_db
def test_an_inactive_credential_is_refused(client, db, scheduler_credential):
    scheduler_credential.is_active = False
    db.commit()
    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    # No active credential at all -> fail closed, not open.
    assert resp.status_code in (401, 503)


# --- What may be invoked --------------------------------------------------

@requires_db
def test_an_unknown_task_is_refused(client, scheduler_credential):
    resp = client.post(f"{CRON}/drop_everything", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 404


@requires_db
def test_the_unknown_task_name_is_not_echoed_back(client, scheduler_credential):
    """The path is matched against an allow-list, not resolved to anything, and
    the response must not reflect attacker-supplied text."""
    probe = "zzz_probe_marker_zzz"
    resp = client.post(f"{CRON}/{probe}", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"] == "Unknown maintenance task."
    # RFC 9457's `instance` is the request URL by contract, so it necessarily
    # contains the path.  The attacker-controlled name must not enter any
    # semantic field that a UI, alert, or log summary would present as prose.
    for field in ("type", "title", "detail", "code"):
        assert probe not in str(body.get(field, ""))


def test_every_allow_listed_task_is_callable():
    """A name in the list with no working callable behind it would fail only at
    3am in production."""
    for name, spec in internal_cron.TASKS.items():
        body = spec.sweep if spec.resumable else spec.run
        assert callable(body), f"{name} has no runnable body"


def test_the_allow_list_covers_every_beat_task():
    """The scheduler replaced Celery beat; it must not silently drop a job."""
    import app.workers.tasks  # noqa: F401
    from app.workers.celery_app import celery_app

    beat = {e["task"].rsplit(".", 1)[-1] for e in celery_app.conf.beat_schedule.values()}
    scheduled = set(internal_cron.TASKS)
    # Two names differ deliberately; map them before comparing.
    aliases = {"run_pii_retention": "pii_retention",
               "run_honesty_fund_distribution": "honesty_fund_distribution"}
    beat = {aliases.get(name, name) for name in beat}
    assert beat <= scheduled, f"beat tasks with no scheduler entry: {beat - scheduled}"


# --- Cadence and catch-up ------------------------------------------------
#
# GitHub Actions does not guarantee delivery. These are the tests that stop a
# missed invocation from silently postponing a monthly job by a month.

def test_every_task_declares_a_real_cadence():
    for name, spec in internal_cron.TASKS.items():
        assert spec.cadence in ("hourly", "daily", "weekly", "monthly"), name
        if spec.cadence == "monthly":
            assert spec.day_of_month, f"{name} is monthly with no day"


def test_an_hourly_period_is_the_manila_hour_and_due_from_its_minute():
    """The priority tiers age hourly (dev note 2026-09-26): each Manila hour is
    its own period, due from :15, so a late call still completes that hour and
    a second call in the same hour finds it done."""
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["priority_tiers"]
    assert spec.cadence == "hourly"
    at = datetime(2026, 9, 27, 1, 20, tzinfo=MANILA)
    assert spec.period(at) == "2026-09-27T01"
    assert spec.is_due(at) is True
    assert spec.is_due(at.replace(minute=10)) is False
    assert spec.period(at.replace(hour=2)) != spec.period(at)


def test_a_weekly_period_is_the_manila_iso_week_due_from_monday_08_00():
    """The store owners' summary (0085): one period per ISO week, due from Monday
    08:00 Manila, so a late run on Tuesday still sends that week's, once."""
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["weekly_summaries"]
    assert spec.cadence == "weekly"
    monday = datetime(2026, 10, 5, 8, 0, tzinfo=MANILA)
    assert spec.period(monday) == "2026-W41"
    assert spec.is_due(monday) is True
    assert spec.is_due(monday.replace(hour=7, minute=59)) is False
    sunday = datetime(2026, 10, 11, 23, 30, tzinfo=MANILA)
    assert spec.period(sunday) == "2026-W41" and spec.is_due(sunday) is True
    assert spec.next_threshold(sunday) == datetime(2026, 10, 12, 8, 0, tzinfo=MANILA)
    assert spec.next_threshold(monday.replace(hour=7)) == monday
    # The year turns mid-week: Monday 2026-12-28 starts ISO week 2026-W53.
    assert spec.period(datetime(2027, 1, 1, 12, tzinfo=MANILA)) == "2026-W53"
    # 00:00 UTC Monday (the workflow's "0 0 * * 1") is 08:00 Manila: due on time.
    assert spec.is_due(datetime(2026, 10, 5, 0, 0, tzinfo=UTC)) is True


def test_send_emails_is_hourly_at_twenty_past():
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["send_emails"]
    at = datetime(2026, 10, 5, 9, 20, tzinfo=MANILA)
    assert spec.cadence == "hourly" and spec.period(at) == "2026-10-05T09"
    assert spec.is_due(at) and not spec.is_due(at.replace(minute=19))


def test_the_workflow_is_a_manual_backup_that_names_only_known_tasks():
    """Vercel Cron schedules production (vercel.json -> GET /tick); the GitHub
    Actions workflow keeps workflow_dispatch only. Two schedulers would double
    the calls, so it must not regain a `schedule:` trigger.

    Regression kept from the scheduled version: the 05:00 Manila schedule
    still called `sweep_contracts` after the contract sweep was retired, so
    production answered 404 every day. Every dispatch option must name a task
    in the allow-list."""
    import pathlib
    import re

    wf = (pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
          / "scheduled-maintenance.yml").read_text()
    triggers = wf.split("\non:\n", 1)[1].split("\nconcurrency:", 1)[0]
    assert re.findall(r"^  (\w+):", triggers, re.M) == ["workflow_dispatch"]
    assert "cron:" not in triggers
    options = re.findall(r"^\s+- (\w+)\s*$", triggers.split("options:", 1)[1], re.M)
    unknown = set(options) - set(internal_cron.TASKS)
    assert options and not unknown, unknown


def test_the_tick_reaches_each_task_on_time():
    """Every five minutes, so each task runs within five minutes of its
    threshold (the hourly tasks at :15 and :20, the dailies at their minute),
    and the hourly tasks run first, as the workflow ran them."""
    hourly = [n for n in internal_cron.SCHEDULE
              if internal_cron.TASKS[n].cadence == "hourly"]
    assert internal_cron.SCHEDULE[:len(hourly)] == tuple(hourly)
    for name in internal_cron.SCHEDULE:
        assert internal_cron.TASKS[name].minute % 5 == 0, name


def test_periods_are_dated_in_manila_not_utc():
    """18:30 UTC on the 4th is 02:30 Manila on the 5th. Reading the UTC date
    would file the run under the wrong month at a boundary."""
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["schedule_payouts"]
    utc_moment = datetime(2026, 9, 4, 18, 30, tzinfo=UTC)
    assert utc_moment.astimezone(MANILA).day == 5
    assert spec.period(utc_moment) == "2026-09"
    assert spec.is_due(utc_moment) is True


def test_a_daily_period_is_a_date_and_a_monthly_period_is_a_month():
    from app.core.constants import MANILA

    when = datetime(2026, 8, 29, 12, 0, tzinfo=MANILA)
    assert internal_cron.TASKS["expire_requests"].period(when) == "2026-08-29"
    assert internal_cron.TASKS["honesty_fund_distribution"].period(when) == "2026-08"


def test_a_task_is_not_due_before_its_threshold():
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["pii_retention"]          # 03:00 Manila
    assert spec.is_due(datetime(2026, 8, 29, 2, 59, tzinfo=MANILA)) is False
    assert spec.is_due(datetime(2026, 8, 29, 3, 0, tzinfo=MANILA)) is True


def test_a_missed_monthly_run_is_caught_up_later_in_the_same_period():
    """THE point of this design. If the scheduler never fired on the 1st, an
    invocation on the 2nd — or the 20th — must still be due, because the period
    is the month and the month has not been done."""
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["honesty_fund_distribution"]
    missed_day = datetime(2026, 8, 2, 2, 0, tzinfo=MANILA)
    assert spec.is_due(missed_day) is True
    assert spec.period(missed_day) == "2026-08", "still August's run, not September's"

    much_later = datetime(2026, 8, 20, 9, 0, tzinfo=MANILA)
    assert spec.is_due(much_later) is True
    assert spec.period(much_later) == "2026-08"


def test_the_next_month_is_a_different_period():
    """Catch-up must not mean "run August again in September"."""
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["honesty_fund_distribution"]
    assert spec.period(datetime(2026, 8, 20, 9, 0, tzinfo=MANILA)) == "2026-08"
    assert spec.period(datetime(2026, 9, 1, 9, 0, tzinfo=MANILA)) == "2026-09"


@requires_db
def test_a_completed_period_is_not_run_again(client, db, scheduler_credential):
    """Every extra invocation inside a period must be a no-op. This is what
    makes triggering a monthly job daily safe."""
    from app.core.constants import MANILA
    from app.models.maintenance import CronRun

    spec = internal_cron.TASKS["expire_requests"]
    period = spec.period(datetime.now(MANILA))

    first = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert first.status_code == 200
    assert first.json()["status"] == internal_cron.OK

    second = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert second.status_code == 200
    assert second.json()["status"] == internal_cron.ALREADY_DONE

    db.expire_all()
    successes = db.query(CronRun).filter(
        CronRun.task == "expire_requests", CronRun.period == period,
        CronRun.status == internal_cron.OK).count()
    assert successes == 1, "a period may succeed exactly once"


@requires_db
def test_a_failed_period_may_be_retried(client, db, monkeypatch, scheduler_credential):
    """A failure must not consume the period. If it did, one bad night would
    mean the job never ran that month."""
    from app.core.constants import MANILA

    spec = internal_cron.TASKS["expire_requests"]
    period = spec.period(datetime.now(MANILA))

    def boom(_db):
        raise RuntimeError("transient")

    monkeypatch.setitem(internal_cron.TASKS, "expire_requests",
                        internal_cron.TaskSpec(boom, cadence="daily", hour=0))
    failed = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert failed.status_code == 500

    monkeypatch.undo()
    retried = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert retried.status_code == 200
    assert retried.json()["status"] == internal_cron.OK, "a failed period must retry"
    assert retried.json()["period"] == period


@requires_db
def test_a_task_before_its_threshold_records_not_due(client, monkeypatch,
                                                     scheduler_credential):
    """An early scheduler must be told it is early, distinctly from being told
    the work is already done."""
    late = internal_cron.TaskSpec(lambda _db: 0, cadence="daily", hour=23, minute=59)
    monkeypatch.setitem(internal_cron.TASKS, "expire_requests", late)

    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 200
    assert resp.json()["status"] == internal_cron.NOT_DUE


def test_the_skip_reasons_are_distinct():
    """Collapsing these into one "skipped" would hide a scheduler that had
    stopped working behind one that was merely early."""
    reasons = {internal_cron.NOT_DUE, internal_cron.ALREADY_DONE,
               internal_cron.ALREADY_RUNNING}
    assert len(reasons) == 3
    assert internal_cron.OK not in reasons and internal_cron.FAILED not in reasons


# --- Claims and overlap ----------------------------------------------------
#
# There is no advisory lock here, deliberately. The application connects
# through the Supabase TRANSACTION pooler, which hands the backend back at
# every commit, so a session-level advisory lock can be released on a different
# connection than took it — and the sweep services commit internally, several
# times. Ownership is a database-arbitrated lease instead.
#
# The arbitration, fencing and continuation properties are proved against real
# concurrent sessions in tests/test_scheduler_state_machine.py. What follows is
# the route-level behaviour that sits on top of them.

@requires_db
def test_a_claim_survives_the_services_internal_commits(client, db, scheduler_credential):
    """The failure mode an advisory lock would have had here.

    `pii_retention` commits inside its service. If exclusion depended on
    connection state it would be gone by the time the task returned, and a
    second caller would happily run it again.
    """
    first = client.post(f"{CRON}/pii_retention", headers={"X-Cron-Key": SECRET})
    assert first.status_code == 200
    assert first.json()["status"] == internal_cron.OK

    second = client.post(f"{CRON}/pii_retention", headers={"X-Cron-Key": SECRET})
    assert second.status_code == 200
    assert second.json()["status"] == internal_cron.ALREADY_DONE, (
        "the period claim must outlive the service's own commits")


@requires_db
def test_a_failing_task_leaves_the_period_retryable(client, db, monkeypatch,
                                                    scheduler_credential):
    """A failure must not consume the period. If it did, one bad night would
    mean the job never ran that day at all."""
    def boom(_db):
        raise RuntimeError("transient")

    monkeypatch.setitem(internal_cron.TASKS, "expire_requests",
                        internal_cron.TaskSpec(boom, cadence="daily", hour=0))
    assert client.post(f"{CRON}/expire_requests",
                       headers={"X-Cron-Key": SECRET}).status_code == 500

    monkeypatch.undo()
    retried = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert retried.status_code == 200
    assert retried.json()["status"] == internal_cron.OK


def test_only_the_o_n_sweeps_are_resumable():
    """Set-based jobs should stay simple.

    The two sweeps recompute a population one record at a time and can outgrow
    a serverless request. The rest are either single statements or loops over
    sets bounded by something other than the user table — and two of them
    (honesty fund, payout scheduling) MUST see their whole population at once,
    because they divide a fixed pool proportionally. Forcing those into a
    continuation protocol would make them wrong, not safer.
    """
    resumable = {n for n, s in internal_cron.TASKS.items() if s.resumable}
    assert resumable == {"recompute_all_trust", "recompute_wilson_scores"}


# --- What is recorded ------------------------------------------------------

@requires_db
def test_every_invocation_is_recorded(client, db, scheduler_credential):
    from app.models.maintenance import CronRun

    before = db.query(CronRun).filter(CronRun.task == "expire_requests").count()
    client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    db.expire_all()
    after = db.query(CronRun).filter(CronRun.task == "expire_requests").count()
    assert after == before + 1


@requires_db
def test_the_response_carries_no_secret_material(client, scheduler_credential):
    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    body = resp.text
    assert SECRET not in body
    assert hashlib.sha256(SECRET.encode()).hexdigest() not in body


@requires_db
def test_a_failing_task_records_a_class_not_a_message(client, db, monkeypatch,
                                                      scheduler_credential):
    """A run record is readable by moderators, so a failure must not carry row
    data in a message — the same rule the admin Overview's diagnostics follow."""
    from app.models.maintenance import CronRun

    def boom(_db):
        raise ValueError("secret-row-value-42")

    monkeypatch.setitem(internal_cron.TASKS, "expire_requests",
                        internal_cron.TaskSpec(boom, cadence="daily", hour=0))

    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 500
    assert "secret-row-value-42" not in resp.text

    db.expire_all()
    run = (db.query(CronRun).filter(CronRun.task == "expire_requests")
           .order_by(CronRun.started_at.desc()).first())
    assert run is not None
    assert run.status == "failed"
    assert run.failure == "ValueError"
    assert "secret-row-value-42" not in (run.detail or "")


# --- The jobs still do their job -------------------------------------------

@requires_db
def test_request_expiry_transitions_only_what_is_due(client, db, scheduler_credential):
    """Before expires_at: untouched. After: expired. Both proved on run-owned
    rows, so the shared project's contents cannot make this pass or fail."""
    from app.models.enums import RequestStatus
    from app.models.request_board import ReviewRequest
    from tests.conftest import make_user

    owner = make_user(db, display_name="Expiry probe")
    db.flush()
    now = datetime.now(UTC)
    due = ReviewRequest(requester_id=owner.id, title="Due request",
                        details="x" * 40, status=RequestStatus.open,
                        expires_at=now - timedelta(hours=1))
    fresh = ReviewRequest(requester_id=owner.id, title="Fresh request",
                          details="x" * 40, status=RequestStatus.open,
                          expires_at=now + timedelta(days=7))
    db.add_all([due, fresh])
    db.commit()
    try:
        resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
        assert resp.status_code == 200

        db.expire_all()
        db.refresh(due)
        db.refresh(fresh)
        assert due.status == RequestStatus.expired, "a request past its term must expire"
        assert fresh.status == RequestStatus.open, "a request still in term must not"
    finally:
        for row in (due, fresh):
            db.delete(row)
        db.commit()


@requires_db
def test_pii_retention_runs_and_reports_a_count(client, scheduler_credential):
    """The legal obligation that most needed automating. It uses the retention
    policy already configured; nothing here invents a duration."""
    resp = client.post(f"{CRON}/pii_retention", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["processed"], int)


@requires_db
def test_payout_scheduling_prepares_without_submitting(client, scheduler_credential,
                                                       monkeypatch):
    """Automating internal preparation must not become an automatic transfer.
    If the scheduler ever reached the provider, this fails."""
    from app.services import payout_service

    submitted = []
    monkeypatch.setattr(payout_service, "submit_batch",
                        lambda *a, **k: submitted.append(a) or {})

    resp = client.post(f"{CRON}/schedule_payouts", headers={"X-Cron-Key": SECRET})
    assert resp.status_code == 200
    assert submitted == [], "the scheduler must not hand a batch to the provider"


@requires_db
def test_the_scheduler_does_not_expose_arbitrary_execution(client, scheduler_credential):
    """Dotted names are refused; URL normalization cannot borrow cron auth."""
    for probe in ("os.system", "app.workers.tasks.schedule_payouts"):
        resp = client.post(f"{CRON}/{probe}", headers={"X-Cron-Key": SECRET})
        assert resp.status_code in (404, 405), f"{probe} resolved to something"

    # HTTP clients normalize `../` before routing, so this becomes the real
    # admin payout URL rather than an internal-cron task name.  That route has
    # its own Bearer-token guard: a cron credential must still be useless.
    traversal = client.post(
        f"{CRON}/../../admin/payouts/run", headers={"X-Cron-Key": SECRET})
    assert traversal.status_code == 401


def test_claims_are_scoped_per_task_and_period():
    """Exclusion must be per (task, period). One shared key would make
    unrelated jobs block each other; a task-only key would block tomorrow's run
    behind today's."""
    from app.models.maintenance import CronRun

    index = next(ix for ix in CronRun.__table__.indexes
                 if ix.name == "uq_cron_runs_task_period_claim")
    assert index.unique
    assert [c.name for c in index.columns] == ["task", "period"]


def test_the_credential_is_never_stored_in_plaintext():
    """The model holds a digest column and no secret column."""
    from app.models.maintenance import CronCredential

    columns = set(CronCredential.__table__.columns.keys())
    assert "secret_sha256" in columns
    assert not {"secret", "token", "password", "plaintext"} & columns


@requires_db
def test_uuid_columns_serialize_as_strings(client, scheduler_credential):
    """The admin Overview went down for exactly this: a UUID reaching a str
    field. The run id crosses the same boundary."""
    resp = client.post(f"{CRON}/expire_requests", headers={"X-Cron-Key": SECRET})
    run_id = resp.json().get("run_id")
    if run_id:
        assert isinstance(run_id, str)
        uuid.UUID(run_id)


# --- The Vercel Cron tick ---------------------------------------------------
#
# GET /tick runs SCHEDULE in order through the same path as POST /{task}. The
# tasks are replaced with fakes here: the subject is the dispatcher (order,
# continuation, budget, what it records), and the real task bodies keep their
# coverage above.

TICK = f"{CRON}/tick"


def _bearer(secret: str = SECRET) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


@pytest.fixture
def fake_tasks(monkeypatch):
    """Every TASKS entry swapped for a fake that is due and records its call.

    Returns the call log (task names, in call order) and a helper to swap one
    task for a different spec.
    """
    calls: list[str] = []

    def simple(name):
        def run(_db):
            calls.append(name)
            return 1
        return internal_cron.TaskSpec(run, cadence="daily", hour=0)

    for name in internal_cron.TASKS:
        monkeypatch.setitem(internal_cron.TASKS, name, simple(name))

    def replace(name, spec):
        monkeypatch.setitem(internal_cron.TASKS, name, spec)

    return calls, replace


def _sweep(name, calls, *, finish_after: int | None, pause: float = 0.0):
    """A resumable fake: `continuing` until it has been called
    `finish_after` times (never, if None)."""
    import time as _time

    from app.services.sweep_service import BatchResult

    def sweep(_db, cursor, batch, snapshot_at, budget):
        calls.append(name)
        if pause:
            _time.sleep(pause)
        done = finish_after is not None and calls.count(name) >= finish_after
        return BatchResult(processed=2, cursor=None if done else "k", complete=done)

    return internal_cron.TaskSpec(sweep=sweep, cadence="daily", hour=0)


def _tick_rows(db):
    from app.models.maintenance import CronRun

    db.expire_all()
    return db.query(CronRun).filter(CronRun.source == "vercel-cron").all()


# Who may invoke the tick

@requires_db
def test_the_tick_accepts_the_bearer_secret(client, scheduler_credential, fake_tasks):
    resp = client.get(TICK, headers=_bearer())
    assert resp.status_code == 200, resp.text


@requires_db
def test_the_tick_refuses_a_wrong_bearer_secret(client, scheduler_credential, fake_tasks):
    calls, _ = fake_tasks
    assert client.get(TICK, headers=_bearer("not-the-secret")).status_code == 401
    assert calls == [], "a refused tick must run nothing"


@requires_db
def test_the_tick_refuses_a_missing_or_non_bearer_header(client, scheduler_credential,
                                                         fake_tasks):
    calls, _ = fake_tasks
    assert client.get(TICK).status_code == 401
    # The POST route's header does not open the tick, and a bare secret with
    # no scheme is not a Bearer credential.
    assert client.get(TICK, headers={"X-Cron-Key": SECRET}).status_code == 401
    assert client.get(TICK, headers={"Authorization": SECRET}).status_code == 401
    assert calls == []


@requires_db
def test_the_tick_refuses_a_user_access_token(client, scheduler_credential, fake_tasks):
    _, token, _ = register_and_token(client, role="administrator")
    assert client.get(TICK, headers=_bearer(token)).status_code == 401


@requires_db
def test_the_tick_fails_closed_without_a_configured_credential(client, db, fake_tasks):
    from app.models.maintenance import CronCredential

    db.query(CronCredential).filter(
        CronCredential.name == internal_cron.CREDENTIAL_NAME).delete()
    db.commit()
    calls, _ = fake_tasks
    assert client.get(TICK, headers=_bearer()).status_code == 503
    assert calls == []


@requires_db
def test_the_tick_refuses_an_inactive_credential(client, db, scheduler_credential,
                                                 fake_tasks):
    scheduler_credential.is_active = False
    db.commit()
    assert client.get(TICK, headers=_bearer()).status_code == 503


@requires_db
def test_x_cron_key_still_opens_post_and_bearer_does_not(client, scheduler_credential,
                                                         fake_tasks):
    """The POST route is unchanged: its header is X-Cron-Key, and only that."""
    assert client.post(f"{CRON}/expire_requests",
                       headers={"X-Cron-Key": SECRET}).status_code == 200
    assert client.post(f"{CRON}/integrity_sweep",
                       headers=_bearer()).status_code == 401


# What the tick runs, and in what order

def test_the_tick_schedule_is_every_task_but_the_manual_backfill():
    assert len(internal_cron.SCHEDULE) == len(set(internal_cron.SCHEDULE))
    assert set(internal_cron.SCHEDULE) == set(internal_cron.TASKS) - {
        "reconcile_admin_upvotes"}
    order = list(internal_cron.SCHEDULE)
    assert order.index("recompute_wilson_scores") < order.index("recompute_all_trust")


@requires_db
def test_the_tick_runs_tasks_in_schedule_order(client, scheduler_credential, fake_tasks):
    calls, _ = fake_tasks
    resp = client.get(TICK, headers=_bearer())
    assert resp.status_code == 200, resp.text
    assert calls == list(internal_cron.SCHEDULE)
    body = resp.json()
    assert [t["task"] for t in body["tasks"]] == list(internal_cron.SCHEDULE)
    assert {t["status"] for t in body["tasks"]} == {internal_cron.OK}
    assert body["stopped"] is False


@requires_db
def test_the_tick_never_runs_the_manual_backfill(client, scheduler_credential, fake_tasks):
    calls, _ = fake_tasks
    client.get(TICK, headers=_bearer())
    assert "reconcile_admin_upvotes" not in calls


@requires_db
def test_the_tick_response_carries_no_identifiers(client, scheduler_credential, fake_tasks):
    resp = client.get(TICK, headers=_bearer())
    assert SECRET not in resp.text
    for entry in resp.json()["tasks"]:
        assert set(entry) == {"task", "status", "processed", "more", "calls"}


# What the tick records

@requires_db
def test_the_tick_records_runs_but_not_skips(client, db, scheduler_credential, fake_tasks):
    """First tick: one `ok` row per task. Second tick: everything is already
    done, and that writes nothing."""
    first = client.get(TICK, headers=_bearer())
    assert first.status_code == 200
    rows = _tick_rows(db)
    assert sorted(r.task for r in rows) == sorted(internal_cron.SCHEDULE)
    assert {r.status for r in rows} == {internal_cron.OK}

    second = client.get(TICK, headers=_bearer())
    assert second.status_code == 200
    assert {t["status"] for t in second.json()["tasks"]} == {internal_cron.ALREADY_DONE}
    assert len(_tick_rows(db)) == len(rows), "already-completed must write no row"


@requires_db
def test_a_not_due_task_in_the_tick_writes_no_row(client, db, scheduler_credential,
                                                  fake_tasks):
    calls, replace = fake_tasks
    replace("expire_requests", internal_cron.TaskSpec(
        lambda _db: calls.append("expire_requests") or 0,
        cadence="daily", hour=23, minute=59))
    resp = client.get(TICK, headers=_bearer())
    statuses = {t["task"]: t["status"] for t in resp.json()["tasks"]}
    assert statuses["expire_requests"] == internal_cron.NOT_DUE
    assert "expire_requests" not in calls
    assert not [r for r in _tick_rows(db) if r.task == "expire_requests"]


@requires_db
def test_an_already_running_task_is_still_recorded(client, db, scheduler_credential,
                                                   fake_tasks):
    """Only not-due and already-completed are quiet. A held lease is the
    kind of thing an operator needs to see, so it keeps its row."""
    spec = internal_cron.TASKS["integrity_sweep"]
    now = internal_cron._now()
    held = internal_cron._claim(db, "integrity_sweep", "manual", spec.period(now),
                                spec.threshold(now))
    assert held is not None
    resp = client.get(TICK, headers=_bearer())
    statuses = {t["task"]: t["status"] for t in resp.json()["tasks"]}
    assert statuses["integrity_sweep"] == internal_cron.ALREADY_RUNNING
    assert [r.status for r in _tick_rows(db) if r.task == "integrity_sweep"] == [
        internal_cron.ALREADY_RUNNING]


# Continuation and the budget

@requires_db
def test_a_continuing_sweep_is_called_again_within_the_tick(client, scheduler_credential,
                                                            fake_tasks):
    calls, replace = fake_tasks
    replace("recompute_wilson_scores",
            _sweep("recompute_wilson_scores", calls, finish_after=3))
    resp = client.get(TICK, headers=_bearer())
    assert resp.status_code == 200, resp.text
    assert calls.count("recompute_wilson_scores") == 3
    # Wilson finished inside the tick, so trust and everything after it ran.
    assert calls == [n for n in internal_cron.SCHEDULE
                     for _ in range(3 if n == "recompute_wilson_scores" else 1)]
    wilson = next(t for t in resp.json()["tasks"] if t["task"] == "recompute_wilson_scores")
    assert wilson == {"task": "recompute_wilson_scores", "status": internal_cron.OK,
                      "processed": 6, "more": False, "calls": 3}


@requires_db
def test_the_tick_stops_when_its_budget_runs_out_mid_sweep(client, db, monkeypatch,
                                                           scheduler_credential, fake_tasks):
    """Wilson never finishes inside this tick, so trust must not start: it
    reads the scores Wilson is still writing."""
    calls, replace = fake_tasks
    replace("recompute_wilson_scores",
            _sweep("recompute_wilson_scores", calls, finish_after=None, pause=0.05))
    monkeypatch.setattr(internal_cron, "_TICK_BUDGET_OVERRIDE", timedelta(seconds=0.4))

    resp = client.get(TICK, headers=_bearer())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stopped"] is True
    assert calls.count("recompute_wilson_scores") >= 2, "re-called while budget remained"
    after = list(internal_cron.SCHEDULE)[
        internal_cron.SCHEDULE.index("recompute_wilson_scores") + 1:]
    assert not set(after) & set(calls), "nothing after the unfinished sweep may run"
    assert body["tasks"][-1]["task"] == "recompute_wilson_scores"
    assert body["tasks"][-1]["status"] == internal_cron.CONTINUING
    assert body["tasks"][-1]["more"] is True

    # The period is left resumable, not done.
    rows = [r for r in _tick_rows(db) if r.task == "recompute_wilson_scores"]
    assert [r.status for r in rows] == [internal_cron.CONTINUING]


@requires_db
def test_each_call_gets_at_most_what_is_left_of_the_tick(client, monkeypatch,
                                                         scheduler_credential, fake_tasks):
    calls, replace = fake_tasks
    seen = []

    from app.services.sweep_service import BatchResult

    def sweep(_db, cursor, batch, snapshot_at, budget):
        seen.append(budget.remaining())
        return BatchResult(processed=0, cursor=None, complete=True)

    replace("recompute_wilson_scores",
            internal_cron.TaskSpec(sweep=sweep, cadence="daily", hour=0))
    monkeypatch.setattr(internal_cron, "_BUDGET_OVERRIDE", timedelta(seconds=30))
    monkeypatch.setattr(internal_cron, "_TICK_BUDGET_OVERRIDE", timedelta(seconds=2))
    client.get(TICK, headers=_bearer())
    assert seen and seen[0] <= timedelta(seconds=2)


# Failure

@requires_db
def test_a_failed_task_does_not_stop_the_tick(client, db, scheduler_credential, fake_tasks):
    calls, replace = fake_tasks

    def boom(_db):
        calls.append("pii_retention")
        raise ValueError("secret-row-value-42")

    replace("pii_retention", internal_cron.TaskSpec(boom, cadence="daily", hour=0))
    resp = client.get(TICK, headers=_bearer())
    # The tick answers 500 so Vercel's cron log shows the failure ...
    assert resp.status_code == 500
    assert "secret-row-value-42" not in resp.text
    # ... after running everything, the failure included.
    assert calls == list(internal_cron.SCHEDULE)
    statuses = {t["task"]: t["status"] for t in resp.json()["tasks"]}
    assert statuses["pii_retention"] == internal_cron.FAILED
    assert {s for t, s in statuses.items() if t != "pii_retention"} == {internal_cron.OK}

    failed = [r for r in _tick_rows(db) if r.task == "pii_retention"]
    assert [(r.status, r.failure) for r in failed] == [(internal_cron.FAILED, "ValueError")]


def test_vercel_cron_calls_the_tick_every_five_minutes_through_the_backend_rewrite():
    """vercel.json is what schedules production maintenance. The cron path
    must reach the backend through the public `/api/v1` rewrite (a cron call
    is an ordinary GET to the production deployment), and every five minutes
    is often enough for the hourly tasks' :15 and :20 thresholds."""
    import json
    import pathlib
    import re

    config = json.loads((pathlib.Path(__file__).resolve().parents[2]
                         / "vercel.json").read_text())
    assert config["crons"] == [
        {"path": "/api/v1/internal/cron/tick", "schedule": "*/5 * * * *"}]
    path = config["crons"][0]["path"]
    first = next(r for r in config["rewrites"]
                 if re.fullmatch(r["source"], path))
    assert first["destination"]["service"] == "backend"
    assert path == "/api/v1" + internal_cron.router.prefix + "/tick"
    # The tick runs inside one backend request: its budget must sit well
    # inside the function ceiling.
    ceiling = config["services"]["backend"]["functions"]["app/main.py"]["maxDuration"]
    assert internal_cron.TICK_BUDGET.total_seconds() * 2 <= ceiling

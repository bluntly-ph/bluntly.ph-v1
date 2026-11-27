"""Admin queue priority tiers — facts, aging and the hourly job.

`priority_tiers` is the pure rule. This module loads the facts it needs in
bounded batches, keeps the aging record (`queue_triage`), and exposes the tier
of every item already in the earn_eligible queue ("earnings") or the content
report queue ("reports").

QUEUE ADMISSION IS NOT TOUCHED HERE. Nothing in this module changes a review's
earn_eligible_status, files or resolves a report, or decides membership: the
items are whatever `referral_service._all_queue_candidates` and the open
reports already are. The only table written is `queue_triage`, a triage
annotation. Opening, previewing or reading an item writes nothing at all.

VOTER RISK. The dev note reads the voter risk class (Baseline / Elevated /
High / Critical) from "the existing voter risk table". No such table or
scoring exists in this codebase (docs/FULL_FEATURE_MATRIX.md row 8.10). So the
four levels are mapped, deterministically and without any new scoring, onto
the enforcement state the trust-integrity work already maintains:

* Critical — the account is suspended, under investigation, or a moderator
  upheld a vote-concentration finding against it (ADR-016);
* High     — on probation, or a vote-concentration hold awaits a moderator;
* Elevated — younger than the 30-day maturation window (trust.py) or carrying
             a strike;
* Baseline — none of the above.

It is recorded as a provisional mapping in docs/ADMIN_PRIORITY_TIERS.md for the
owner to confirm or replace.

WILSON. The tiers read the earn_eligible gate's weighted Wilson lower bound
(earn_gate.gate_state: trust-weighted votes snapshotted at vote time), the
number the 0.65 threshold applies to. The trend compares it with the same
bound over only the votes cast before the trend window.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import ACCOUNT_MATURATION_DAYS
from app.models.comment import ReviewComment
from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    ReportSource,
    VoteDirection,
)
from app.models.moderation import ModerationLog
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.seller import SellerReview
from app.models.triage import QueueTriage
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import priority_settings
from app.services.priority_settings import TierConfig
from app.services.priority_tiers import (
    FLAGGED_RISKS,
    TIER_RANK,
    Tier,
    TierAssessment,
    TierFacts,
    Trend,
    VoterRisk,
    evaluate,
)
from app.services.ranking import wilson_lower_bound

EARNINGS = "earnings"
REPORTS = "reports"

_CHUNK = 500


def _chunks(values: Iterable[uuid.UUID]) -> Iterable[tuple[uuid.UUID, ...]]:
    items = tuple(dict.fromkeys(values))
    for start in range(0, len(items), _CHUNK):
        yield items[start:start + _CHUNK]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --------------------------------------------------------------- voter risk

def classify_voter(user: User, *, now: datetime, concentration: str | None = None) -> VoterRisk:
    """One account's risk class from existing enforcement state (see module doc).

    `concentration` is "upheld", "open" or None — the account's vote-
    concentration review state (trust_service.concentration_review_state).
    """
    if user.is_suspended or user.is_under_investigation or concentration == "upheld":
        return VoterRisk.critical
    if user.is_on_probation or concentration == "open":
        return VoterRisk.high
    age_days = (now - _aware(user.created_at)).days
    if age_days < ACCOUNT_MATURATION_DAYS or (user.strikes or 0) > 0:
        return VoterRisk.elevated
    return VoterRisk.baseline


def _concentration_states(db: Session, user_ids: Collection[uuid.UUID]) -> dict[uuid.UUID, str]:
    from app.services.trust_service import (
        CONCENTRATION_SIGNAL,
        concentration_review_state,
    )
    by_user: dict[uuid.UUID, list[ModerationLog]] = {}
    for chunk in _chunks(user_ids):
        for report in db.scalars(select(ModerationLog).where(
                ModerationLog.action == ModerationAction.report,
                ModerationLog.target_type == ModerationTargetType.user,
                ModerationLog.target_ref.in_(chunk),
                ModerationLog.reporter_id.is_(None),
                ModerationLog.context["signal"].astext == CONCENTRATION_SIGNAL)):
            by_user.setdefault(report.target_ref, []).append(report)
    states: dict[uuid.UUID, str] = {}
    for user_id, reports in by_user.items():
        cleared, upheld, open_report = concentration_review_state(reports)
        if upheld > cleared:
            states[user_id] = "upheld"
        elif open_report is not None:
            states[user_id] = "open"
    return states


def voter_risks(db: Session, user_ids: Collection[uuid.UUID], *,
                now: datetime) -> dict[uuid.UUID, VoterRisk]:
    ids = [u for u in dict.fromkeys(user_ids) if u is not None]
    if not ids:
        return {}
    users: dict[uuid.UUID, User] = {}
    for chunk in _chunks(ids):
        users.update((u.id, u) for u in db.scalars(select(User).where(User.id.in_(chunk))))
    concentration = _concentration_states(db, ids)
    return {uid: classify_voter(u, now=now, concentration=concentration.get(uid))
            for uid, u in users.items()}


# --------------------------------------------------------------- the facts

@dataclass(frozen=True)
class QueuedTarget:
    """One item in one queue, as the tiers see it."""

    queue: str
    target_type: ModerationTargetType
    target_ref: uuid.UUID
    #: When it entered the queue by the data (the fallback when no triage row
    #: recorded it), and the last decision that restarted its clock.
    entered_at: datetime
    last_decision_at: datetime | None = None


def _trend(before_lb: float | None, now_lb: float | None, tolerance: float) -> Trend:
    if now_lb is None or before_lb is None:
        return Trend.unknown
    delta = now_lb - before_lb
    if delta > tolerance:
        return Trend.rising
    if delta < -tolerance:
        return Trend.falling
    return Trend.stable


def _review_facts(db: Session, reviews: list[Review], config: TierConfig,
                  now: datetime) -> dict[uuid.UUID, TierFacts]:
    """Facts for reviews, in one query per source."""
    if not reviews:
        return {}
    ids = [r.id for r in reviews]
    cutoff = now - timedelta(days=config.trend_window_days)

    votes: dict[uuid.UUID, list[tuple[VoteDirection, float | None, datetime, uuid.UUID]]] = {}
    for chunk in _chunks(ids):
        for rid, vote, weight, created, voter in db.execute(
                select(ReviewVote.review_id, ReviewVote.vote, ReviewVote.vote_weight,
                       ReviewVote.created_at, ReviewVote.voter_id)
                .where(ReviewVote.review_id.in_(chunk))):
            votes.setdefault(rid, []).append(
                (vote, float(weight) if weight is not None else None, _aware(created), voter))

    authors = {r.author_id for r in reviews if r.author_id}
    # Every upvoter of every review these authors have written: the author's
    # vote-evidence history, for Low/Lowest.
    history: dict[uuid.UUID, set[uuid.UUID]] = {}
    for chunk in _chunks(authors):
        for author_id, voter in db.execute(
                select(Review.author_id, ReviewVote.voter_id)
                .join(ReviewVote, ReviewVote.review_id == Review.id)
                .where(Review.author_id.in_(chunk), ReviewVote.vote == VoteDirection.up)
                .distinct()):
            history.setdefault(author_id, set()).add(voter)

    upvoters = {v for rows in votes.values() for d, _, _, v in rows if d == VoteDirection.up}
    risks = voter_risks(db, upvoters | {v for s in history.values() for v in s}, now=now)

    stages: dict[uuid.UUID, int] = {}
    first_root: dict[uuid.UUID, uuid.UUID] = {}
    for chunk in _chunks(authors):
        stages.update(db.execute(select(User.id, User.trust_stage).where(User.id.in_(chunk))).all())
        # The author's earliest thread root, removed or not: "first submission
        # ever" means ever, not "first still standing".
        for author_id, rid in db.execute(
                select(Review.author_id, Review.id)
                .where(Review.author_id.in_(chunk),
                       (Review.thread_id.is_(None)) | (Review.thread_id == Review.id))
                .order_by(Review.author_id, Review.created_at.asc(), Review.id.asc())
                .distinct(Review.author_id)):
            first_root[author_id] = rid

    reports = _report_counts(db, ModerationTargetType.review, ids, config)
    out: dict[uuid.UUID, TierFacts] = {}
    for r in reviews:
        rows = [row for row in votes.get(r.id, []) if row[1] is not None]
        pos = sum(w for d, w, _, _ in rows if d == VoteDirection.up)
        tot = sum(w for _, w, _, _ in rows)
        now_lb = wilson_lower_bound(pos, tot) if tot > 0 else None
        old = [row for row in rows if row[2] < cutoff]
        old_pos = sum(w for d, w, _, _ in old if d == VoteDirection.up)
        old_tot = sum(w for _, w, _, _ in old)
        before_lb = wilson_lower_bound(old_pos, old_tot) if old_tot > 0 else None
        up_ids = {v for d, _, _, v in votes.get(r.id, []) if d == VoteDirection.up}
        count, fraud = reports.get(r.id, (0, 0))
        out[r.id] = TierFacts(
            wilson_lower_bound=round(now_lb, 4) if now_lb is not None else None,
            trend=_trend(before_lb, now_lb, config.trend_tolerance),
            flagged_upvoters=sum(1 for v in up_ids if risks.get(v) in FLAGGED_RISKS),
            author_history_flagged_voters=sum(
                1 for v in history.get(r.author_id, set()) if risks.get(v) in FLAGGED_RISKS),
            author_stage=stages.get(r.author_id) if r.author_id else None,
            first_submission=(r.author_id is not None and r.is_thread_root
                              and first_root.get(r.author_id) == r.id),
            report_count=count,
            fraud_reports=fraud,
        )
    return out


def _report_counts(db: Session, target_type: ModerationTargetType,
                   refs: Collection[uuid.UUID], config: TierConfig
                   ) -> dict[uuid.UUID, tuple[int, int]]:
    """(every report, user fraud reports) per target — resolved ones included,
    the same "how contested has this been" count the queue badges show."""
    out: dict[uuid.UUID, tuple[int, int]] = {}
    fraud = set(config.fraud_reasons)
    for chunk in _chunks(refs):
        for ref, reason, source in db.execute(
                select(ModerationLog.target_ref, ModerationLog.reason, ModerationLog.report_source)
                .where(ModerationLog.action == ModerationAction.report,
                       ModerationLog.target_type == target_type,
                       ModerationLog.target_ref.in_(chunk))):
            total, frauds = out.get(ref, (0, 0))
            is_fraud = (source != ReportSource.system_detected
                        and reason is not None and reason.value in fraud)
            out[ref] = (total + 1, frauds + (1 if is_fraud else 0))
    return out


#: Who authored each non-review report target, and its creation time.
_AUTHOR_COLUMNS = {
    ModerationTargetType.comment: (ReviewComment, ReviewComment.author_id),
    ModerationTargetType.question: (Question, Question.asker_id),
    ModerationTargetType.answer: (Answer, Answer.responder_id),
    ModerationTargetType.seller_review: (SellerReview, SellerReview.reviewer_id),
}


def _content_facts(db: Session, target_type: ModerationTargetType,
                   refs: list[uuid.UUID], config: TierConfig) -> dict[uuid.UUID, TierFacts]:
    """Facts for a reported comment, question, answer, seller review or account.

    No Wilson and no upvoter risk apply, so signals A and B are absent and the
    trend is "unknown" (nothing moved). Reports, the author's stage and the
    first-submission rule still apply.
    """
    if not refs:
        return {}
    reports = _report_counts(db, target_type, refs, config)
    author_of: dict[uuid.UUID, uuid.UUID | None] = {}
    first: dict[uuid.UUID, bool] = {}
    if target_type is ModerationTargetType.user:
        author_of = {ref: ref for ref in refs}
    elif target_type in _AUTHOR_COLUMNS:
        model, author_col = _AUTHOR_COLUMNS[target_type]
        for chunk in _chunks(refs):
            author_of.update(db.execute(
                select(model.id, author_col).where(model.id.in_(chunk))).all())
        authors = {a for a in author_of.values() if a}
        earliest: dict[uuid.UUID, uuid.UUID] = {}
        for chunk in _chunks(authors):
            for author_id, cid in db.execute(
                    select(author_col, model.id).where(author_col.in_(chunk))
                    .order_by(author_col, model.created_at.asc(), model.id.asc())
                    .distinct(author_col)):
                earliest[author_id] = cid
        first = {ref: (a is not None and earliest.get(a) == ref) for ref, a in author_of.items()}
    stages: dict[uuid.UUID, int] = {}
    for chunk in _chunks({a for a in author_of.values() if a}):
        stages.update(db.execute(select(User.id, User.trust_stage).where(User.id.in_(chunk))).all())
    out: dict[uuid.UUID, TierFacts] = {}
    for ref in refs:
        author = author_of.get(ref)
        count, fraud = reports.get(ref, (0, 0))
        out[ref] = TierFacts(
            wilson_lower_bound=None, trend=Trend.unknown, flagged_upvoters=0,
            author_history_flagged_voters=0,
            author_stage=stages.get(author) if author else None,
            first_submission=first.get(ref, False),
            report_count=count, fraud_reports=fraud)
    return out


def facts_for(db: Session, targets: Collection[QueuedTarget], config: TierConfig,
              now: datetime) -> dict[tuple[str, uuid.UUID], TierFacts]:
    by_type: dict[ModerationTargetType, set[uuid.UUID]] = {}
    for t in targets:
        by_type.setdefault(t.target_type, set()).add(t.target_ref)
    out: dict[tuple[str, uuid.UUID], TierFacts] = {}
    for target_type, refs in by_type.items():
        if target_type is ModerationTargetType.review:
            reviews = []
            for chunk in _chunks(refs):
                reviews.extend(db.scalars(select(Review).where(Review.id.in_(chunk))))
            facts = _review_facts(db, reviews, config, now)
        else:
            facts = _content_facts(db, target_type, list(refs), config)
        out.update(((target_type.value, ref), f) for ref, f in facts.items())
    return out


# --------------------------------------------------------------- the queues

def _last_decisions(db: Session, target_type: ModerationTargetType,
                    refs: Collection[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    """The newest moderator decision on each target: approve, reject, resolve
    or any other audited action BY A MODERATOR. Reports and automated checks
    are not decisions; neither is opening an item, which is never recorded."""
    out: dict[uuid.UUID, datetime] = {}
    for chunk in _chunks(refs):
        for ref, at in db.execute(
                select(ModerationLog.target_ref, func.max(ModerationLog.created_at))
                .where(ModerationLog.target_type == target_type,
                       ModerationLog.target_ref.in_(chunk),
                       ModerationLog.moderator_id.is_not(None),
                       ModerationLog.action != ModerationAction.report,
                       ModerationLog.action != ModerationAction.receipt_view)
                .group_by(ModerationLog.target_ref)):
            out[ref] = _aware(at)
    return out


def earnings_targets(db: Session, reviews_with_kind: Iterable[tuple[Review, str]]
                     ) -> list[QueuedTarget]:
    pairs = list(reviews_with_kind)
    decided = _last_decisions(db, ModerationTargetType.review, [r.id for r, _ in pairs])
    return [QueuedTarget(
        queue=EARNINGS, target_type=ModerationTargetType.review, target_ref=r.id,
        # Fallback only: the gate records the real moment (note_entered).
        entered_at=_aware(r.created_at if kind == "pending" else r.updated_at),
        last_decision_at=decided.get(r.id)) for r, kind in pairs]


def report_targets(db: Session) -> list[QueuedTarget]:
    """One target per item with at least one open report. It entered the queue
    with its earliest open report; any resolution on it since (a report
    dismissed, another left open) restarts the clock."""
    rows = db.execute(
        select(ModerationLog.target_type, ModerationLog.target_ref,
               func.min(ModerationLog.created_at))
        .where(ModerationLog.action == ModerationAction.report,
               ModerationLog.resolution.is_(None),
               ModerationLog.target_ref.is_not(None))
        .group_by(ModerationLog.target_type, ModerationLog.target_ref)).all()
    if not rows:
        return []
    refs = [ref for _, ref, _ in rows]
    resolved: dict[uuid.UUID, datetime] = {}
    for chunk in _chunks(refs):
        for ref, at in db.execute(
                select(ModerationLog.target_ref, func.max(ModerationLog.resolved_at))
                .where(ModerationLog.action == ModerationAction.report,
                       ModerationLog.target_ref.in_(chunk),
                       ModerationLog.resolution.is_not(None))
                .group_by(ModerationLog.target_ref)):
            if at is not None:
                resolved[ref] = _aware(at)
    return [QueuedTarget(queue=REPORTS, target_type=target_type, target_ref=ref,
                         entered_at=_aware(first), last_decision_at=resolved.get(ref))
            for target_type, ref, first in rows if target_type is not None]


# --------------------------------------------------------------- assessments

@dataclass(frozen=True)
class Triage:
    assessment: TierAssessment
    clock_started_at: datetime
    aged_at: datetime | None

    @property
    def tier(self) -> Tier:
        return self.assessment.tier


def _clock_start(target: QueuedTarget, row: QueueTriage | None) -> datetime:
    entered = _aware(row.entered_at) if row is not None else target.entered_at
    if target.last_decision_at is not None and target.last_decision_at > entered:
        return target.last_decision_at
    return entered


def _triage_rows(db: Session, targets: Collection[QueuedTarget]
                 ) -> dict[tuple[str, str, uuid.UUID], QueueTriage]:
    out: dict[tuple[str, str, uuid.UUID], QueueTriage] = {}
    refs = {t.target_ref for t in targets}
    for chunk in _chunks(refs):
        for row in db.scalars(select(QueueTriage).where(QueueTriage.target_ref.in_(chunk))):
            out[(row.queue, row.target_type, row.target_ref)] = row
    return out


def assess(db: Session, targets: Collection[QueuedTarget], *,
           now: datetime | None = None, config: TierConfig | None = None
           ) -> dict[tuple[str, str, uuid.UUID], Triage]:
    """The tier of each queued target, read-only, keyed (queue, type, ref).

    The base tier is computed live, so a Wilson move from a new vote shows at
    once. Aging comes only from the persisted `aged_at` the hourly job set —
    and counts only while it is newer than the clock's last restart.
    """
    now = _aware(now or datetime.now(UTC))
    config = config or priority_settings.load(db)
    targets = list(targets)
    facts = facts_for(db, targets, config, now)
    rows = _triage_rows(db, targets)
    out: dict[tuple[str, str, uuid.UUID], Triage] = {}
    for t in targets:
        row = rows.get((t.queue, t.target_type.value, t.target_ref))
        clock = _clock_start(t, row)
        aged_at = _aware(row.aged_at) if row is not None and row.aged_at else None
        aged = aged_at is not None and aged_at >= clock
        f = facts.get((t.target_type.value, t.target_ref))
        if f is None:
            continue
        out[(t.queue, t.target_type.value, t.target_ref)] = Triage(
            assessment=evaluate(f, config, aged=aged), clock_started_at=clock,
            aged_at=aged_at if aged else None)
    return out


def note_entered(db: Session, queue: str, target_type: ModerationTargetType,
                 target_ref: uuid.UUID, *, at: datetime | None = None) -> None:
    """Record the moment an item entered a queue (the gate calls this when it
    queues a review). Triage only: the caller has already decided membership,
    and this neither checks nor changes it. Does not commit."""
    at = _aware(at or datetime.now(UTC))
    row = db.scalar(select(QueueTriage).where(
        QueueTriage.queue == queue, QueueTriage.target_type == target_type.value,
        QueueTriage.target_ref == target_ref))
    if row is None:
        db.add(QueueTriage(queue=queue, target_type=target_type.value,
                           target_ref=target_ref, entered_at=at))
    else:
        row.entered_at = at
        row.aged_at = None


def tier_sort_key(triage: Triage | None) -> tuple[int, datetime]:
    """Most urgent tier first, then oldest clock first."""
    if triage is None:
        return (TIER_RANK[Tier.neutral], datetime.max.replace(tzinfo=UTC))
    return (TIER_RANK[triage.tier], triage.clock_started_at)


# --------------------------------------------------------------- the job

def recalculate(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """The hourly job: age what has waited past the window, record every tier,
    and forget items that have left their queue.

    Aging moves an item exactly one tier, once per clock: `aged_at` is set the
    first time the clock has run past `aging_hours`, and a decision that
    restarts the clock voids it. Commits.
    """
    from app.services.referral_service import _all_queue_candidates

    now = _aware(now or datetime.now(UTC))
    config = priority_settings.load(db)
    targets = earnings_targets(db, _all_queue_candidates(db)) + report_targets(db)
    rows = _triage_rows(db, targets)
    window = timedelta(hours=config.aging_hours)

    aged_now = 0
    live_keys: set[tuple[str, str, uuid.UUID]] = set()
    for t in targets:
        key = (t.queue, t.target_type.value, t.target_ref)
        live_keys.add(key)
        row = rows.get(key)
        if row is None:
            row = QueueTriage(queue=t.queue, target_type=t.target_type.value,
                              target_ref=t.target_ref, entered_at=t.entered_at)
            db.add(row)
            rows[key] = row
        clock = _clock_start(t, row)
        if row.aged_at is not None and _aware(row.aged_at) < clock:
            row.aged_at = None  # a decision restarted the clock
        if row.aged_at is None and now - clock >= window:
            row.aged_at = now
            aged_now += 1
    db.flush()

    triaged = assess(db, targets, now=now, config=config)
    for t in targets:
        row = rows[(t.queue, t.target_type.value, t.target_ref)]
        tri = triaged.get((t.queue, t.target_type.value, t.target_ref))
        if tri is None:
            continue
        row.tier = tri.tier.value
        row.base_tier = tri.assessment.base_tier.value
        row.reasons = [r.code for r in tri.assessment.reasons]
        row.computed_at = now

    # Items that left their queue: their record goes with them, so a later
    # re-entry starts a fresh clock.
    stale = [row for row in db.scalars(select(QueueTriage))
             if (row.queue, row.target_type, row.target_ref) not in live_keys]
    for row in stale:
        db.delete(row)
    db.commit()
    return {"items": len(targets), "aged": aged_now, "removed": len(stale)}

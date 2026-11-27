"""The earn_eligible gate (FR-6), wired.

Publication and earning are separate decisions (confirmed by Zient,
2026-09-22): a review is public the moment it is submitted, and a separate
process decides whether it may earn. This module owns the second half — how a
public review *enters* the moderator's earn_eligible queue. The moderator
still makes the final call; nothing here approves earnings.

The rules are the capstone's, and every number comes from code that already
existed and was tested but never called:

* **Seeding Phase** — until ``SEEDING_TRANSITION_REVIEWERS`` Stage 2+ verified
  reviewers exist, every new submission goes straight to the moderator ("direct
  moderator review of all qualifying submissions; no Wilson threshold"). That is
  the behaviour ``earn_eligible_auto_queue`` already gave new reviews, so the
  Seeding path is unchanged.
* **Post-Seeding Phase** — a review auto-queues once its *gate votes* pass
  ``ranking.gate_passes``: trust-weighted Wilson lower bound >= 0.65 on effective
  n, from >= 3 distinct Stage 2+ voters.

Gate votes are not helpfulness votes. The PRD keeps them apart ("Community
visibility votes are equal-weight for all stages and independent of gate
voting"), and ``earn_eligible_votes`` was built for them: each row snapshots the
voter's weight and trust at vote time, so a gate decision stays auditable when
trust later moves.

Pending decisions, deliberately left configurable rather than decided here:
``earn_gate_phase`` defaults to Post-Seeding — Zient's rule that a review
reaches the queue when enough votes accumulate. Seeding (queue at submission)
must be switched on deliberately, and ``auto`` (which counts reviewers
globally where the PRD says "in the pilot category") is opt-in too: a small
platform must not fall into Seeding by accident. Seeding activation policy is
pending Zient.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import EarnEligibleStatus, VerificationStatus, VoteDirection
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from app.services.ranking import (
    GATE_MIN_STAGE2_VOTERS,
    GATE_WILSON_LB,
    gate_passes,
    is_post_seeding,
    wilson_lower_bound,
)

SEEDING = "seeding"
POST_SEEDING = "post_seeding"


def stage2_verified_reviewers(db: Session) -> int:
    """Stage 2+ members with at least one verified, moderator-approved review."""
    from app.services.trust_service import TRUST_COUNTED_STATUSES
    return int(db.scalar(
        select(func.count(func.distinct(User.id)))
        .join(Review, Review.author_id == User.id)
        .where(User.trust_stage >= 2,
               Review.verification_status == VerificationStatus.verified,
               Review.published_at.isnot(None),
               Review.is_removed.is_(False),
               Review.earn_eligible_status.in_(TRUST_COUNTED_STATUSES))
    ) or 0)


def current_phase(db: Session) -> str:
    """Seeding only when configured, directly or via an explicit `auto`.
    A blank or unrecognised value is Post-Seeding: an accident must never put
    every new review into the queue."""
    mode = (settings.earn_gate_phase or "").strip().lower()
    if mode == SEEDING:
        return SEEDING
    if mode == "auto":
        return POST_SEEDING if is_post_seeding(stage2_verified_reviewers(db)) else SEEDING
    return POST_SEEDING


def initial_status(db: Session) -> EarnEligibleStatus:
    """Where a brand-new public review starts on the earning side."""
    if current_phase(db) == SEEDING and settings.earn_eligible_auto_queue:
        return EarnEligibleStatus.pending
    return EarnEligibleStatus.none


@dataclass(frozen=True)
class GateState:
    effective_positive: float
    effective_total: float
    wilson_lower_bound: float
    stage2_plus_voters: int
    voters: int
    passes: bool
    threshold: float = GATE_WILSON_LB
    min_stage2_voters: int = GATE_MIN_STAGE2_VOTERS


def gate_state(db: Session, review_id: uuid.UUID) -> GateState:
    """The community earnings gate over the review's weighted helpfulness votes.

    Business Rules §2 and §11: a review's upvotes have a visible count and a
    backend weight (trust stage x reputation, halved for new or
    under-investigation accounts, zero for probation and claimed sellers). The
    weight is snapshotted on each vote (`review_votes.vote_weight`); votes cast
    before migration 0050 carry none and do not count toward the gate. An
    admin's cold-start approval is never a vote and never enters this math.
    """
    return gate_states(db, [review_id])[review_id]


def gate_states(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, GateState]:
    """`gate_state` for many reviews in one query (the admin All Reviews list).
    The one implementation of the gate's arithmetic: `gate_state` calls this."""
    rows: dict[uuid.UUID, list[tuple]] = {rid: [] for rid in review_ids}
    if review_ids:
        # A suspended voter's votes stop counting while the suspension lasts
        # (owner decision, session 4): read-time, so reinstating restores them
        # and the snapshotted weights stay as cast.
        for rid, vote, weight, stage in db.execute(
                select(ReviewVote.review_id, ReviewVote.vote, ReviewVote.vote_weight,
                       ReviewVote.trust_stage_snapshot)
                .outerjoin(User, User.id == ReviewVote.voter_id)
                .where(ReviewVote.review_id.in_(review_ids),
                       ReviewVote.vote_weight.isnot(None),
                       or_(User.id.is_(None), User.is_suspended.is_(False)))):
            rows[rid].append((vote, weight, stage))
    return {rid: _gate_from_rows(votes) for rid, votes in rows.items()}


def _gate_from_rows(rows: list[tuple]) -> GateState:
    positive = sum(float(w) for v, w, _ in rows if v == VoteDirection.up)
    total = sum(float(w) for _, w, _ in rows)
    stage2 = sum(1 for _, w, stage in rows if (stage or 0) >= 2 and float(w) > 0)
    return GateState(
        effective_positive=round(positive, 4), effective_total=round(total, 4),
        wilson_lower_bound=round(wilson_lower_bound(positive, total), 4),
        stage2_plus_voters=stage2, voters=len(rows),
        passes=gate_passes(positive, total, stage2),
    )


def maybe_queue(db: Session, review: Review) -> bool:
    """Post-Seeding auto-queue. Only lifts `none` to `pending`; a moderator's
    decision (approved, rejected, monetized, honesty_fund) is never reopened by
    votes, and a queued review is never pulled back out by them either. Only a
    thread's original review is queued: that is where its earning lives (§4)."""
    if review.earn_eligible_status != EarnEligibleStatus.none:
        return False
    if review.published_at is None or review.is_removed or not review.is_thread_root:
        return False
    if current_phase(db) != POST_SEEDING:
        return False
    db.flush()
    if not gate_state(db, review.id).passes:
        return False
    _queue(db, review)
    return True


def _queue(db: Session, review: Review) -> None:
    review.earn_eligible_status = EarnEligibleStatus.pending
    # Triage only (dev note 2026-09-26): record when it entered, so the admin
    # priority tiers age it from here. Membership was decided by the caller.
    from app.models.enums import ModerationTargetType
    from app.services.priority_triage import EARNINGS, note_entered
    note_entered(db, EARNINGS, ModerationTargetType.review, review.id)


def nominate(db: Session, review: Review) -> bool:
    """An administrator's or super admin's upvote: put the review in the
    earnings queue now (owner, 2026-10-06), in any phase and whatever its
    community votes. The same doors as `maybe_queue`: only from `none`, so a
    decision is never reopened and a queued review is never queued twice; only
    a public, standing thread original. Queueing is not approval — the review
    waits for an administrator's decision, and nothing is paid from here."""
    if review.earn_eligible_status != EarnEligibleStatus.none:
        return False
    if review.published_at is None or review.is_removed or not review.is_thread_root:
        return False
    _queue(db, review)
    return True


def reconcile_staff_upvotes(db: Session) -> int:
    """One-time backfill, safe to repeat: nominate every review an
    administrator or super admin upvoted before upvotes nominated (the votes
    are already there; this applies the rule they now carry). Also returns
    staff vote snapshots to the voter's own trust weight, undoing the brief
    "staff vote weighs 3.0" rule (PR #16) so the community gate is exactly the
    members' again. Does not commit. Returns the number of reviews queued."""
    from app.models.enums import MemberRole
    from app.services.trust import weight_of
    staff = (MemberRole.administrator, MemberRole.super_admin)
    rows = db.execute(
        select(ReviewVote, User)
        .join(User, User.id == ReviewVote.voter_id)
        .where(User.role.in_(staff))).all()
    nominate_ids: set[uuid.UUID] = set()
    for vote, user in rows:
        weight = Decimal(str(round(weight_of(user), 4)))
        if vote.vote_weight != weight or vote.trust_stage_snapshot != user.trust_stage:
            vote.vote_weight = weight
            vote.trust_stage_snapshot = user.trust_stage
        if vote.vote == VoteDirection.up and not user.is_suspended:
            nominate_ids.add(vote.review_id)
    queued = 0
    for rid in sorted(nominate_ids):
        review = db.get(Review, rid)
        if review is not None and nominate(db, review):
            queued += 1
    db.flush()
    return queued

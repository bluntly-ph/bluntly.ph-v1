"""Community visibility voting on published reviews (M2 slice 2).

Equal-weight up/down votes feed the time-decayed Wilson score (ADR-004, 45d
half-life) that ranks listings, and the author's helpfulness_ratio that feeds
trust progression. All aggregate updates happen in the same transaction as the
vote write so counters can never drift from the vote rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.models.enums import MemberRole, VoteDirection
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from app.services.ranking import time_decayed_wilson
from app.services.trust import weight_of


@dataclass(frozen=True)
class CastVoteResult:
    """The vote just written, plus whether it was a brand-new row.

    `created` answers exactly one question: did this call INSERT a
    `ReviewVote`? A same-direction retry or a direction change both upsert an
    existing row and are `False` — the route's first-vote telemetry (geography
    bucket) depends on that distinction to stay "first-time votes", not "vote
    button presses".
    """

    review: Review
    created: bool


def _now() -> datetime:
    return datetime.now(UTC)


def age_days(created_at: datetime, now: datetime | None = None) -> float:
    now = now or _now()
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max(0.0, (now - created_at).total_seconds() / 86400.0)


def recompute_review_vote_aggregates(db: Session, review: Review) -> None:
    """Refresh helpful/unhelpful counts + time-decayed wilson from the vote rows."""
    votes = list(db.execute(
        select(ReviewVote.vote, ReviewVote.created_at)
        .where(ReviewVote.review_id == review.id)
    ))
    now = _now()
    review.helpful_votes = sum(1 for v, _ in votes if v == VoteDirection.up)
    review.unhelpful_votes = len(votes) - review.helpful_votes
    review.wilson_score = time_decayed_wilson(
        (v == VoteDirection.up, age_days(created, now)) for v, created in votes
    )


def _votable_or_404(review: Review) -> None:
    if review.published_at is None or review.is_removed:
        raise NotFoundError("Review not found.", code="review_not_found")


def _lock_review(db: Session, review: Review) -> None:
    """Take the review's row lock for the rest of this vote write.

    Every vote write recounts the review's counters from its vote rows. Two
    writers recounting at once each saw only their own uncommitted vote, so 12
    people voting together left 12 rows and `helpful_votes` 11 (QA,
    2026-09-29). Holding the review row serialises writers on ONE review; the
    second recounts after the first commits and sees its vote. Taken before any
    other write, and always review before author, so writers never deadlock.
    """
    db.execute(select(Review.id).where(Review.id == review.id).with_for_update())


#: Staff whose upvote nominates a review for the earnings queue (owner, 2026-10-06).
STAFF_ROLES = frozenset({MemberRole.administrator, MemberRole.super_admin})


def is_nominating_staff(user: User) -> bool:
    """An administrator or super admin in good standing: their upvote is a
    nomination (`earn_gate.nominate`), not a community gate vote."""
    return user.role in STAFF_ROLES and not user.is_suspended


def cast_vote(db: Session, review: Review, voter: User,
              direction: VoteDirection) -> CastVoteResult:
    _votable_or_404(review)
    if voter.is_claimed_seller:
        # §9/§11: a claimed seller never votes or downvotes, on anything.
        raise ForbiddenError("A claimed seller account can't vote.", code="seller_cannot_vote")
    if review.author_id == voter.id:
        raise AppError("You cannot vote on your own review.",
                       code="cannot_vote_own_review", status_code=409,
                       title="Conflicting state")

    _lock_review(db, review)
    # §11: the visible vote is one per person; its backend weight is taken now
    # and kept, so the earnings gate stays auditable when trust later moves.
    weight = Decimal(str(round(weight_of(voter), 4)))
    stage = voter.trust_stage
    existing = db.scalar(select(ReviewVote).where(
        ReviewVote.review_id == review.id, ReviewVote.voter_id == voter.id))
    created = existing is None
    previous = existing.vote if existing is not None else None
    if existing is None:
        db.add(ReviewVote(review_id=review.id, voter_id=voter.id, vote=direction,
                          vote_weight=weight, trust_stage_snapshot=stage))
    else:
        existing.vote = direction
        existing.vote_weight = weight
        existing.trust_stage_snapshot = stage
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent first-votes hit uq_review_vote_once
        db.rollback()
        raise AppError("Your vote was submitted twice at once; retry.",
                       code="vote_conflict", status_code=409,
                       title="Conflicting state") from exc
    if direction == VoteDirection.up and is_nominating_staff(voter):
        # Owner, 2026-10-06: an administrator's or super admin's upvote
        # nominates the review for the earnings queue at once, whatever the
        # community gate says. It only queues (`none` -> `pending`): approving
        # earnings and any payout stay separate human decisions.
        from app.services import earn_gate
        earn_gate.nominate(db, review)
    if direction == VoteDirection.up and previous != VoteDirection.up:
        # QA-067: the author hears about a new upvote, or a downvote changed to
        # one — in this transaction (committed by _finish_vote_write). Pressing
        # the same vote again, or taking a vote back, announces nothing, and a
        # vote taken back and cast again finds its receipt and stays silent.
        # Downvotes notify nobody: no product rule asks for it.
        from app.services import notification_service
        notification_service.review_upvoted(db, review, voter.id)
    _finish_vote_write(db, review)
    return CastVoteResult(review=review, created=created)


def remove_vote(db: Session, review: Review, voter_id: uuid.UUID) -> Review:
    _votable_or_404(review)
    _lock_review(db, review)
    existing = db.scalar(select(ReviewVote).where(
        ReviewVote.review_id == review.id, ReviewVote.voter_id == voter_id))
    if existing is None:
        raise NotFoundError("You have no vote on this review.", code="vote_not_found")
    db.delete(existing)
    db.flush()
    _finish_vote_write(db, review)
    return review


def _finish_vote_write(db: Session, review: Review) -> None:
    """Shared tail of every vote mutation — one transaction end to end.

    Trust recompute (slice 3) also refreshes the author's helpfulness_ratio from
    the just-updated review counters (it flushes before reading — sessions run
    with autoflush=False).
    """
    recompute_review_vote_aggregates(db, review)
    # §2: enough trust-weighted community votes put the review in the admin's
    # earnings queue. Never reopens a decision; only lifts `none` to `pending`.
    from app.services import earn_gate
    earn_gate.maybe_queue(db, review)
    if review.author_id is not None:
        from app.services.trust_service import recompute_user_trust
        recompute_user_trust(db, review.author_id)
    db.commit()
    db.refresh(review)


def voted_review_ids(db: Session, created_before=None) -> list:
    """Reviews with at least one vote — the population the nightly re-decay
    walks. Named so the selection can be tested and bounded independently of
    the recomputation it feeds.

    `created_before` defaults to None (the historical behaviour). The resumable
    scheduler passes the instant its logical run began, so a traversal spread
    over several requests has a fixed population; reviews created after it are
    picked up by the next period.
    """
    voted = select(ReviewVote.review_id.label("id"))
    # A review whose stored counters say it was voted on but whose vote rows
    # are gone (a voter's account deleted: `review_votes.voter_id` cascades)
    # has nothing left to find it by above, and would keep its old counts and
    # Wilson for ever. It is re-counted to zero instead (QA, 2026-09-29).
    orphaned = select(Review.id.label("id")).where(
        (Review.helpful_votes + Review.unhelpful_votes) > 0,
        ~select(ReviewVote.id).where(ReviewVote.review_id == Review.id).exists())
    if created_before is not None:
        voted = voted.join(Review, Review.id == ReviewVote.review_id).where(
            Review.created_at <= created_before)
        orphaned = orphaned.where(Review.created_at <= created_before)
    return list(db.scalars(select(voted.union(orphaned).subquery().c.id)).all())


def recompute_all_wilson_scores(db: Session) -> int:
    """Nightly sweep: re-decay wilson for published reviews with >=1 vote.

    Decay drifts with time even without new votes, so listings would go stale
    without this. Returns the number of reviews updated.
    """
    review_ids = voted_review_ids(db)
    updated = 0
    for review_id in review_ids:
        review = db.get(Review, review_id)
        if review is None or review.published_at is None or review.is_removed:
            continue
        recompute_review_vote_aggregates(db, review)
        updated += 1
    db.commit()
    return updated

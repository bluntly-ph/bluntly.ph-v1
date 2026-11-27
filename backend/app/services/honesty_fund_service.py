"""Honesty Fund monthly distribution (M2 slice 8; FR-6).

Pool = 30% honesty-fund shares of the cycle's commissions. Eligible = published,
not-removed reviews routed to the fund (<=2 stars). Each review's Honesty Score =
trust-weighted helpful votes x price-bracket multiplier (existing pure fns).
Payout_i = pool x score_i / sum(scores), rounded DOWN to the centavo; the dust
remainder stays with the pool (documented). Idempotent per cycle: if the cycle
already has distribution rows, the run ABORTS rather than re-distributing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import MANILA
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models.commission import Commission
from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    VoteDirection,
)
from app.models.honesty_fund import HonestyFundDistribution
from app.models.moderation import ModerationLog
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import wallet
from app.services.trust import (
    MIN_VOTES_PER_VERIFIED_REVIEW,
    gate_vote_weight,
    honesty_score,
    voter_evidence_weight,
)

log = get_logger("honesty_fund")

_CENT = Decimal("0.01")

#: Eligibility floor, not formula (ADR-016): a fund-routed review is scored only
#: when its up-voters add up to at least this many people of voter evidence —
#: the same per-review evidence ADR-014 expects of a verified review. Below it,
#: a handful of arranged votes would carry a share of real money.
FUND_MIN_REVIEW_EVIDENCE = MIN_VOTES_PER_VERIFIED_REVIEW


def previous_cycle_month(now: datetime | None = None) -> date:
    """First day of the previous calendar month, Asia/Manila."""
    today = (now or datetime.now(UTC)).astimezone(MANILA).date()
    first_of_this = today.replace(day=1)
    last_month = first_of_this - timedelta(days=1)
    return last_month.replace(day=1)


#: Reviews scored per voter query. Bounded so an IN list stays a sane size.
_SCORE_BATCH = 1000


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


@dataclass(frozen=True)
class ScoreInputs:
    """What a review's Honesty Score is made of, for the fund report."""

    weighted_up_votes: Decimal
    voter_evidence: float
    score: Decimal


def _review_scores(db: Session, reviews: list[Review], now: datetime) -> list[Decimal]:
    """Honesty Score per review, in the order given (see `score_inputs`)."""
    inputs = score_inputs(db, reviews, now)
    return [inputs[r.id].score for r in reviews]


def score_inputs(db: Session, reviews: list[Review], now: datetime) -> dict[uuid.UUID, ScoreInputs]:
    """Honesty Score per review: gate-weighted UP votes x price bracket (0 if no votes).

    One grouped query per batch of reviews, not one per review. The eligible set
    is every fund-routed review in the database; one round trip each made a
    distribution cost minutes at scale (13.6 of them for a single test against
    the shared test project). The arithmetic is unchanged, in the same order.

    Each vote's weight honours all of §11 — a claimed seller's and a suspended
    account's up-vote weigh nothing, an investigated one's half — which the
    four-argument call here used to skip. A review whose up-voters fall short
    of FUND_MIN_REVIEW_EVIDENCE people (ADR-016) scores 0.
    """
    weighted: dict[uuid.UUID, Decimal] = {r.id: Decimal("0") for r in reviews}
    evidence: dict[uuid.UUID, float] = {r.id: 0.0 for r in reviews}
    ids = list(weighted)
    for start in range(0, len(ids), _SCORE_BATCH):
        rows = db.execute(
            select(ReviewVote.review_id, ReviewVote.created_at, User.trust_stage,
                   User.reputation_score, User.created_at, User.is_on_probation,
                   User.is_under_investigation, User.is_claimed_seller,
                   User.is_suspended)
            .join(User, ReviewVote.voter_id == User.id)
            .where(ReviewVote.review_id.in_(ids[start:start + _SCORE_BATCH]),
                   ReviewVote.vote == VoteDirection.up)
            .order_by(ReviewVote.review_id, ReviewVote.id)
        ).all()
        for (review_id, voted_at, stage, reputation, created_at, probation,
             investigating, claimed, suspended) in rows:
            created_at = _aware(created_at)
            age_days = max(0, (now - created_at).days)
            if not suspended:
                weighted[review_id] += Decimal(str(gate_vote_weight(
                    stage, float(reputation), age_days, probation,
                    bool(investigating), bool(claimed))))
            # One vote per (review, voter), so each row here is a distinct person.
            evidence[review_id] += voter_evidence_weight(
                stage, max(0, (_aware(voted_at) - created_at).days), probation,
                bool(investigating), bool(claimed), bool(suspended))
    return {r.id: ScoreInputs(
        weighted_up_votes=weighted[r.id], voter_evidence=evidence[r.id],
        score=(honesty_score(weighted[r.id], r.price_paid or Decimal("0"))
               if evidence[r.id] >= FUND_MIN_REVIEW_EVIDENCE else Decimal("0")))
        for r in reviews}


def eligible_reviews(db: Session) -> list[Review]:
    """The fund-routed reviews that may take part in a cycle.

    Public, not removed, on the fund track — and never a claimed seller's (§9),
    nor one whose author is under a concentration hold a moderator has not
    released (ADR-016): passed over for the cycle, held rather than punished.
    """
    eligible = db.scalars(
        select(Review).outerjoin(User, User.id == Review.author_id).where(
            Review.earn_eligible_status == EarnEligibleStatus.honesty_fund,
            Review.published_at.isnot(None),
            Review.is_removed.is_(False),
            or_(User.id.is_(None), User.is_claimed_seller.is_(False)))
    ).all()
    from app.services.trust_service import held_by_concentration
    held = held_by_concentration(db, {r.author_id for r in eligible if r.author_id})
    return [r for r in eligible if r.author_id not in held]


def distribute(db: Session, cycle_month: date | None = None,
               triggered_by: uuid.UUID | None = None) -> dict:
    if not settings.honesty_fund_distribution_enabled:
        # Business Rules §14: the fund's internal mechanics — pool sizing,
        # distribution formula, anti-collusion, price-bracket weighting — are
        # an open decision. The pool keeps accruing its 30%; nothing is paid
        # out of it by a formula nobody has approved.
        raise AppError("Honesty Fund distribution is paused until its formula is decided.",
                       code="honesty_fund_formula_pending", status_code=409,
                       title="Pending owner decision")
    cycle = cycle_month or previous_cycle_month()
    now = datetime.now(UTC)

    existing = db.scalar(select(func.count(HonestyFundDistribution.id))
                         .where(HonestyFundDistribution.cycle_month == cycle))
    if existing:
        log.info("honesty fund cycle already distributed; aborting",
                 extra={"extra_fields": {"cycle": str(cycle), "rows": existing}})
        return {"cycle_month": cycle, "pool": "0.00", "recipients": 0,
                "status": "already_distributed"}

    pool = db.scalar(
        select(func.coalesce(func.sum(Commission.honesty_fund_share), 0))
        .where(Commission.cycle_month == cycle, Commission.is_test.is_(False))
    ) or Decimal("0")
    pool = Decimal(pool).quantize(_CENT)
    if pool <= 0:
        log.info("honesty fund pool empty; nothing to distribute",
                 extra={"extra_fields": {"cycle": str(cycle)}})
        return {"cycle_month": cycle, "pool": "0.00", "recipients": 0,
                "status": "empty_pool"}

    eligible = eligible_reviews(db)
    scored = list(zip(eligible, _review_scores(db, list(eligible), now), strict=True))
    scored = [(r, s) for r, s in scored if s > 0]
    total_score = sum(s for _, s in scored)
    if not scored or total_score <= 0:
        log.info("no eligible scored reviews for honesty fund cycle",
                 extra={"extra_fields": {"cycle": str(cycle), "pool": str(pool)}})
        return {"cycle_month": cycle, "pool": str(pool), "recipients": 0,
                "status": "no_eligible_reviews"}

    recipients = 0
    for review, score in scored:
        payout = (pool * score / total_score).quantize(_CENT, rounding=ROUND_FLOOR)
        db.add(HonestyFundDistribution(
            distribution_id=f"hfd_{uuid.uuid4().hex[:12]}",
            cycle_month=cycle, review_id=review.id, reviewer_id=review.author_id,
            honesty_score=score, pool_amount=pool, payout_amount=payout,
        ))
        if payout > 0 and review.author_id is not None:
            wallet.adjust(db, review.author_id, payout)
        recipients += 1

    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        moderator_id=triggered_by,
        action=ModerationAction.honesty_fund_distribution,
        context={"cycle": str(cycle), "pool": str(pool), "recipients": recipients},
    ))
    db.commit()
    return {"cycle_month": cycle, "pool": str(pool), "recipients": recipients,
            "status": "distributed"}

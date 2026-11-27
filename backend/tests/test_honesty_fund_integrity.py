"""Honesty Fund eligibility hardening (ADR-016).

Distribution stays OFF by default and its formula is an open owner decision
(Business Rules §14); none of this decides how the pool is split. It decides
what may take part at all: §9/§11 weights honoured in full, a minimum of
distinct voter evidence per review, claimed sellers never paid, and authors
under an unreleased concentration hold passed over for the cycle.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select

from tests.conftest import make_user, register_and_token, requires_db
from tests.test_trust_integrity_holds import _cohort_member, _holds
from tests.test_trust_ring_exploit import MATURE, NOW, _recompute, _vote, _voters

pytestmark = requires_db


def _fund_review(db, author=None):
    from app.models.enums import EarnEligibleStatus, Verdict
    from app.models.product import Product
    from app.models.review import Review

    author = author or make_user(db, created_at=MATURE)
    product = Product(canonical_name=f"Fund probe {uuid.uuid4().hex[:8]}",
                      category="electronics")
    db.add(product)
    db.flush()
    review = Review(product_id=product.id, author_id=author.id, title="Broke fast",
                    discussion="An honest warning.", verdict=Verdict.hard_pass,
                    star_rating=2, is_removed=False, price_paid=Decimal("100"),
                    published_at=NOW - timedelta(days=10),
                    earn_eligible_status=EarnEligibleStatus.honesty_fund)
    db.add(review)
    db.flush()
    return review


def _score(db, review):
    from app.services.honesty_fund_service import _review_scores

    return _review_scores(db, [review], NOW)[0]


def test_fund_scores_nothing_below_the_evidence_floor(db):
    from app.services.honesty_fund_service import FUND_MIN_REVIEW_EVIDENCE

    review = _fund_review(db)
    _vote(db, [review], _voters(db, FUND_MIN_REVIEW_EVIDENCE - 1))
    assert _score(db, review) == 0

    _vote(db, [review], _voters(db, 1))
    assert _score(db, review) > 0


def test_fund_gives_a_claimed_sellers_up_vote_no_weight(db):
    """The fund used to call gate_vote_weight with four arguments, so a claimed
    seller's earlier up-vote still weighed in real money (§9, §11)."""
    review = _fund_review(db)
    voters = _voters(db, 5)
    _vote(db, [review], voters)
    full = _score(db, review)

    voters[0].is_claimed_seller = True
    db.flush()
    assert _score(db, review) == full * Decimal(4) / Decimal(5)


def test_fund_halves_an_investigated_vote_and_ignores_a_suspended_one(db):
    review = _fund_review(db)
    voters = _voters(db, 6)
    _vote(db, [review], voters)
    full = _score(db, review)
    per_vote = full / 6

    voters[0].is_under_investigation = True
    voters[1].is_suspended = True
    db.flush()
    assert _score(db, review) == per_vote * Decimal("4.5")


@requires_db
def test_distribution_passes_over_a_held_author(client):
    """End to end through `distribute`: the held author's review is not among
    the cycle's recipients; the unheld one is."""
    from app.db.session import SessionLocal
    from app.models.enums import ModerationTargetType
    from app.models.honesty_fund import HonestyFundDistribution
    from app.services.honesty_fund_service import FUND_MIN_REVIEW_EVIDENCE, distribute
    from app.services.report_service import file_system_report
    from app.services.trust_service import CONCENTRATION_SIGNAL
    from tests.test_retention_and_fund import (
        _auth,
        _free_cycle,
        _honesty_review,
        _seed_pool,
        _weighted_upvote,
    )

    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)
    tag = uuid.uuid4().hex[:6]
    held_rid, held_author = _honesty_review(client, mh, price="100", name=f"Held-{tag}")
    free_rid, _ = _honesty_review(client, mh, price="100", name=f"Free-{tag}")
    for _ in range(FUND_MIN_REVIEW_EVIDENCE):
        _weighted_upvote(client, held_rid, stage=2, reputation=100.0)
        _weighted_upvote(client, free_rid, stage=2, reputation=100.0)

    db = SessionLocal()
    try:
        report, _ = file_system_report(
            db, target_type=ModerationTargetType.user,
            target_ref=uuid.UUID(held_author), signal=CONCENTRATION_SIGNAL)
        report.context = {**report.context, "candidate_stage": 3}
        db.commit()

        cycle = _free_cycle()
        _seed_pool(cycle, Decimal("30.00"), free_rid)
        assert distribute(db, cycle_month=cycle)["status"] == "distributed"
        paid = {str(d.review_id) for d in db.scalars(select(HonestyFundDistribution).where(
            HonestyFundDistribution.cycle_month == cycle))}
        assert free_rid in paid
        assert held_rid not in paid
    finally:
        db.close()





def test_a_claimed_seller_author_is_never_scored(db):
    """§9: a claimed seller never earns — the cycle does not even score them."""
    from app.models.user import User
    from app.services.honesty_fund_service import eligible_reviews

    review = _fund_review(db)
    _vote(db, [review], _voters(db, 5))
    assert review.id in {r.id for r in eligible_reviews(db)}

    db.get(User, review.author_id).is_claimed_seller = True
    db.flush()
    assert review.id not in {r.id for r in eligible_reviews(db)}


def test_an_author_under_a_concentration_hold_is_passed_over(db):
    author = _cohort_member(db)
    _recompute(db, author)
    assert _holds(db, author), "the cohort member is held"
    review = _fund_review(db, author=author)
    _vote(db, [review], _voters(db, 5))

    from app.services.honesty_fund_service import eligible_reviews
    assert review.id not in {r.id for r in eligible_reviews(db)}

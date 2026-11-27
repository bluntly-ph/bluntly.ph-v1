"""The redesigned contributor dashboard (Figma Screen/Dashboard 7833:9534):
GET /users/me/contributor, with exact money and the real trust ladder.

Each test builds its own member in a rolled-back session (the `db` fixture),
fixed to a known "now", so nothing here depends on what else the database holds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.commission import Commission
from app.models.enums import (
    CommissionTarget,
    EarnEligibleStatus,
    Platform,
    Verdict,
    VerificationStatus,
    VoteDirection,
)
from app.models.honesty_fund import HonestyFundDistribution
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import contributor_dashboard as cd
from app.services import trust as ladder
from tests.conftest import register_and_token, requires_db

D = Decimal
# Thursday 1 October 2026, 10:00 Manila.
NOW = datetime(2026, 10, 1, 2, 0, tzinfo=UTC)

pytestmark = requires_db


def _member(db, **kw) -> User:
    u = User(email=f"cd_{uuid.uuid4().hex}@example.com", password_hash="x",
             display_name="Dash Fixture", username=f"cd_{uuid.uuid4().hex[:10]}", **kw)
    db.add(u)
    db.flush()
    return u


def _review(db, author) -> Review:
    product = Product(canonical_name=f"Dash Product {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    r = Review(product_id=product.id, author_id=author.id, title="Fixture",
               discussion="Body text for the fixture review.", verdict=Verdict.yes_absolutely,
               star_rating=D("5"), earn_eligible_status=EarnEligibleStatus.monetized,
               verification_status=VerificationStatus.verified, published_at=NOW)
    db.add(r)
    db.flush()
    return r


def _commission(db, review, author, share: str, when: datetime, *, cleared: bool,
                reverses: Commission | None = None) -> Commission:
    amount = D(share)
    c = Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                   target_type=CommissionTarget.review, review_id=review.id,
                   reviewer_id=author.id, platform=Platform.shopee, currency="PHP",
                   csv_source="dash-test", row_reference=uuid.uuid4().hex,
                   cycle_month=when.date().replace(day=1),
                   gross_amount=amount * 10 / 3, platform_share=amount * 4 / 3,
                   reviewer_share=amount, honesty_fund_share=amount,
                   cleared_at=when if cleared else None, created_at=when,
                   reverses_commission_id=reverses.id if reverses else None)
    db.add(c)
    db.flush()
    return c


def test_week_and_month_buckets_end_today():
    week = cd._windows("week", NOW.date())
    assert [w[0] for w in week] == ["F", "S", "S", "M", "T", "W", "T"]
    assert week[-1][1] == NOW.date()
    month = cd._windows("month", NOW.date())
    assert len(month) == 4 and month[-1][2] == NOW.date()
    assert month[0][0] == "Sep 4"


def test_wallet_earnings_and_returns_are_exact(db):
    member = _member(db, wallet_balance=D("500.00"))
    review = _review(db, member)
    sold = _commission(db, review, member, "300.00", NOW - timedelta(days=2), cleared=True)
    _commission(db, review, member, "200.00", NOW - timedelta(days=1), cleared=False)
    # Returned today: the reversal of the cleared sale's share... of 30.00.
    small = _commission(db, review, member, "30.00", NOW - timedelta(days=3), cleared=True)
    _commission(db, review, member, "-30.00", NOW, cleared=True, reverses=small)
    db.add(HonestyFundDistribution(
        distribution_id=f"hfd_{uuid.uuid4().hex[:12]}", cycle_month=NOW.date().replace(day=1),
        review_id=review.id, reviewer_id=member.id, honesty_score=D("1"), pool_amount=D("80"),
        payout_amount=D("40.00"), created_at=NOW - timedelta(hours=1)))
    db.flush()
    del sold

    d = cd.build(db, member, period="week", now=NOW)
    assert d.total_balance == D("500.00")
    assert (d.honesty_fund_balance, d.commission_balance) == (D("40.00"), D("460.00"))
    assert d.pending == D("200.00")           # credited, not cleared yet
    assert d.withdrawable == D("300.00")
    assert d.earned == D("570.00")            # 300 + 200 + 30 + the 40.00 fund credit
    assert d.returned == D("30.00")
    today = d.buckets[-1]
    assert today.current and today.earned == D("40.00") and today.returned == D("30.00")
    assert [b.label for b in d.buckets][-1] == "T"
    assert d.has_earned is True
    # An account with nothing ever credited is the dashboard's empty state.
    assert cd.build(db, _member(db), period="week", now=NOW).has_earned is False


def test_next_stage_requirements_follow_the_ladder(db):
    newcomer = _member(db)
    d = cd.build(db, newcomer, now=NOW)
    assert (d.stage, d.next_level_name) == (0, "Contributor")
    assert [(r.key, r.needed, r.done) for r in d.requirements] == [("reviews", 1, False)]

    verified = _member(db, trust_stage=2, verified_review_count=4,
                       helpfulness_ratio=D("80.00"))
    d = cd.build(db, verified, now=NOW)
    assert (d.level_name, d.next_level_name) == ("Verified Buyer", "Established Reviewer")
    reqs = {r.key: (r.have, r.needed, r.done) for r in d.requirements}
    assert reqs["receipt_reviews"] == (4, ladder.STAGE_MIN_VERIFIED_REVIEWS[3], False)
    assert reqs["helpfulness"][2] is True                      # 80 >= 49.5
    assert reqs["helpful_votes"][1] == ladder.stage_evidence_required(3)
    assert d.held_for_review is False

    top = _member(db, trust_stage=5)
    d = cd.build(db, top, now=NOW)
    assert d.next_stage is None and d.requirements == []


def test_reach_counts_views_helped_clicks_and_purchases(db):
    member = _member(db)
    review = _review(db, member)
    voter = _member(db)
    db.add(ReviewVote(review_id=review.id, voter_id=voter.id, vote=VoteDirection.up,
                      created_at=NOW - timedelta(hours=2)))
    _commission(db, review, member, "10.00", NOW - timedelta(hours=1), cleared=False)
    db.flush()
    d = cd.build(db, member, reach_month="this", now=NOW)
    assert d.reach_month == "October" and d.reach_previous_month == "Sep"
    assert (d.reach.helped, d.reach.bought) == (1, 1)
    last = cd.build(db, member, reach_month="last", now=NOW)
    assert last.reach_month == "September" and (last.reach.helped, last.reach.bought) == (0, 0)


def test_unknown_period_is_refused(db):
    member = _member(db)
    with pytest.raises(ValueError):
        cd.build(db, member, period="year", now=NOW)


def test_endpoint_is_the_callers_own(client):
    assert client.get("/api/v1/users/me/contributor").status_code == 401
    _, token, _ = register_and_token(client)
    r = client.get("/api/v1/users/me/contributor?period=month&reach=last",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "month" and body["reach_choice"] == "last"
    assert body["total_balance"] == "0.00" and len(body["buckets"]) == 4
    bad = client.get("/api/v1/users/me/contributor?period=year",
                     headers={"Authorization": f"Bearer {token}"})
    assert bad.status_code == 422
    # No id anywhere in the path: another member's dashboard is not addressable.
    other = create_access_token(uuid.uuid4(), "user")
    assert client.get("/api/v1/users/me/contributor",
                      headers={"Authorization": f"Bearer {other}"}).status_code in (401, 404)


def test_performance_all_products_or_one(db):
    member = _member(db)
    first = _review(db, member)
    second = _review(db, member)
    _commission(db, first, member, "50.00", NOW - timedelta(hours=1), cleared=False)
    _commission(db, second, member, "20.00", NOW - timedelta(days=2), cleared=False)
    db.flush()
    everything = cd.performance(db, member, period="week", now=NOW)
    assert len(everything.products) == 2 and everything.earned == D("70.00")
    # The chooser dates each product by its latest published review.
    assert {x.published_at for x in everything.products} == {NOW}
    assert everything.totals.bought == 2
    one = cd.performance(db, member, product_id=first.product_id, period="week", now=NOW)
    assert one.earned == D("50.00") and one.totals.bought == 1
    assert one.buckets[-1].earned == D("50.00")
    from app.core.errors import NotFoundError
    with pytest.raises(NotFoundError):
        cd.performance(db, member, product_id=uuid.uuid4(), now=NOW)


def test_performance_endpoint(client):
    _, token, _ = register_and_token(client)
    auth = {"Authorization": f"Bearer {token}"}
    body = client.get("/api/v1/users/me/performance", headers=auth).json()
    assert body["products"] == [] and len(body["buckets"]) == 4
    assert client.get(f"/api/v1/users/me/performance?product_id={uuid.uuid4()}",
                      headers=auth).status_code == 404


def test_performance_cards_votes_split_orders_and_rows(db):
    """Screen/Performance cards: rating, votes per bucket, last-30-days line,
    the stored commission shares and orders per marketplace, per-product rows."""
    member = _member(db)
    review = _review(db, member)
    up_voter, down_voter = _member(db), _member(db)
    db.add(ReviewVote(review_id=review.id, voter_id=up_voter.id, vote=VoteDirection.up,
                      created_at=NOW - timedelta(hours=3)))
    db.add(ReviewVote(review_id=review.id, voter_id=down_voter.id, vote=VoteDirection.down,
                      created_at=NOW - timedelta(days=1)))
    _commission(db, review, member, "30.00", NOW - timedelta(hours=1), cleared=False)
    _commission(db, review, member, "15.00", NOW - timedelta(days=20), cleared=True)
    db.flush()
    p = cd.performance(db, member, period="week", now=NOW)
    assert (p.rating, p.review_count) == (D("5.0"), 1)
    assert (p.helpful, p.not_helpful, p.upvotes) == (1, 1, 1)
    assert p.buckets[-1].up == 1 and p.buckets[-2].down == 1
    assert len(p.daily) == 30 and p.daily[-1].day == NOW.date()
    assert p.earned_30d == D("45.00") and p.earned_7d == D("30.00")
    # The donut and Card/Buyers read the ⓘ breakdown: every credited sale, not
    # the week's (owner, 2026-10-19), split 30 / 30 / 40 of the net.
    assert (p.share_you, p.share_honesty_fund, p.share_platform) == (
        D("45.00"), D("45.00"), D("60.00"))
    assert [(o.platform, o.orders) for o in p.orders] == [("shopee", 2), ("lazada", 0)]
    row = p.products[0]
    assert (row.helped, row.earned) == (1, D("30.00"))
    assert p.reach_week.bought == 1 and p.reach_prev_week.bought == 0

"""MQA-033: the Sellers tab is ranked, not alphabetical.

The tester found the Sellers tab defaulting to Name A-Z, which puts "Aaa Store"
with one review above a store thirty shoppers vouched for. The default order is
now "ranked": the Wilson lower bound of a store's share of positive (4-star or
better) reviews, nudged by recent activity - so a long, good record outranks a
short perfect one, and a store with no reviews comes last. "reviews" and "name"
remain as explicit orders.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tests.conftest import make_user, requires_db


def _seller(db, name):
    from app.models.enums import Platform, SellerClaimStatus
    from app.models.seller import Seller
    from app.services.seller_service import normalize_seller_name

    seller = Seller(display_name=name, normalized_name=normalize_seller_name(name),
                    platform=Platform.shopee, claim_status=SellerClaimStatus.unclaimed)
    db.add(seller)
    db.flush()
    return seller


def _reviews(db, seller, ratings, *, days_ago=1, removed=False):
    from app.models.seller import SellerReview

    for rating in ratings:
        db.add(SellerReview(
            seller_id=seller.id, reviewer_id=make_user(db).id, accuracy=True,
            order_completeness=True, customer_service=4, packaging_quality=4,
            overall_rating=Decimal(rating), would_recommend=rating >= 4,
            is_removed=removed, created_at=datetime.now(UTC) - timedelta(days=days_ago)))
    db.flush()


def _ids(db, tag, **kw):
    from app.services.seller_service import list_sellers
    return [s.id for s in list_sellers(db, q=tag, platform=None, limit=20, **kw)]


@requires_db
def test_a_long_good_record_outranks_a_short_perfect_one(db):
    tag = uuid.uuid4().hex[:8]
    none = _seller(db, f"Aaa {tag}")                 # first by name, no reviews
    short = _seller(db, f"Bbb {tag}")
    _reviews(db, short, [5, 5, 5])
    long = _seller(db, f"Zzz {tag}")
    _reviews(db, long, [5] * 26 + [2] * 4)            # 30 reviews, 87% positive
    poor = _seller(db, f"Mmm {tag}")
    _reviews(db, poor, [1, 2, 1, 2, 5, 1])

    assert _ids(db, tag) == [long.id, short.id, poor.id, none.id]
    assert _ids(db, tag, sort="ranked") == _ids(db, tag)
    assert _ids(db, tag, sort="name") == [none.id, short.id, poor.id, long.id]
    assert _ids(db, tag, sort="reviews") == [long.id, poor.id, short.id, none.id]


@requires_db
def test_recent_reviews_break_a_tie_and_removed_ones_do_not_count(db):
    tag = uuid.uuid4().hex[:8]
    old = _seller(db, f"Aaa {tag}")
    _reviews(db, old, [5, 5, 5, 5], days_ago=400)
    fresh = _seller(db, f"Zzz {tag}")
    _reviews(db, fresh, [5, 5, 5, 5], days_ago=3)
    padded = _seller(db, f"Mmm {tag}")
    _reviews(db, padded, [5])
    _reviews(db, padded, [5] * 20, removed=True)     # taken down: not evidence

    assert _ids(db, tag) == [fresh.id, old.id, padded.id]


def test_the_python_score_matches_the_rule():
    from app.services.seller_service import RECENT_BONUS, seller_rank_score

    assert seller_rank_score(0, 0, 0) == 0.0
    assert seller_rank_score(30, 26, 0) > seller_rank_score(3, 3, 0)
    assert seller_rank_score(3, 3, 0) > seller_rank_score(6, 1, 0)
    # Recency nudges by at most RECENT_BONUS, however busy a store is.
    gap = seller_rank_score(10, 9, 500) - seller_rank_score(10, 9, 0)
    assert abs(gap - RECENT_BONUS) < 1e-9


@requires_db
def test_the_route_defaults_to_ranked_and_takes_the_orders(client):
    assert client.get("/api/v1/sellers").status_code == 200
    for sort in ("ranked", "reviews", "name"):
        assert client.get(f"/api/v1/sellers?sort={sort}").status_code == 200
    assert client.get("/api/v1/sellers?sort=rating").status_code == 422

"""QA-053: the All filters sheet's Review score, Trust rating and Budget.

The definitions live in app/services/review_lenses.py; these pin them down on
the feed so the sheet's controls change the results the way the sheet says.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tests.conftest import make_user, requires_db

pytestmark = requires_db

NOW = datetime.now(UTC)


def _product(db):
    from app.models.product import Product

    product = Product(canonical_name=f"Lens probe {uuid.uuid4().hex[:8]}", category="electronics")
    db.add(product)
    db.flush()
    return product


def _review(db, product, *, up=0, down=0, score="50", price=None, days_ago=1):
    from app.models.enums import Verdict
    from app.models.review import Review

    at = NOW - timedelta(days=days_ago)
    review = Review(product_id=product.id,
                    author_id=make_user(db, reputation_score=Decimal(score)).id,
                    title=f"Lens {uuid.uuid4().hex[:6]}", discussion="Body.",
                    verdict=Verdict.it_depends, star_rating=4, is_removed=False,
                    helpful_votes=up, unhelpful_votes=down,
                    wilson_score=Decimal(up) / Decimal(up + down + 1),
                    price_paid=Decimal(price) if price is not None else None,
                    published_at=at, created_at=at)
    db.add(review)
    db.flush()
    return review


def _ids(db, **kwargs):
    from app.services.review_service import list_feed

    return [r.id for r, _, _ in list_feed(db, limit=100, **kwargs)]


def test_hidden_gems_are_helpful_reviews_of_little_covered_products(db):
    quiet = _product(db)
    gem = _review(db, quiet, up=3, down=1)
    unhelpful = _review(db, quiet, up=1, down=2)
    unvoted = _review(db, quiet)
    crowded = _product(db)
    popular = [_review(db, crowded, up=5) for _ in range(4)]

    ids = set(_ids(db, lens="hidden_gems", product_id=quiet.id))
    assert gem.id in ids and unhelpful.id not in ids and unvoted.id not in ids
    # Four reviewers have covered it: not hidden.
    assert not set(_ids(db, lens="hidden_gems", product_id=crowded.id)) & {r.id for r in popular}


def test_controversial_means_readers_split_most_votes_first(db):
    product = _product(db)
    split_big = _review(db, product, up=6, down=5)
    split_small = _review(db, product, up=1, down=1)
    lopsided = _review(db, product, up=9, down=1)
    one_way = _review(db, product, up=4)

    ids = _ids(db, lens="controversial", product_id=product.id)
    assert ids == [split_big.id, split_small.id]
    assert lopsided.id not in ids and one_way.id not in ids


def test_trending_counts_recent_helpful_votes_and_comments(db):
    from app.models.comment import ReviewComment
    from app.models.enums import VoteDirection
    from app.models.vote import ReviewVote

    product = _product(db)
    busy, quiet, stale = (_review(db, product, days_ago=30) for _ in range(3))
    for _ in range(2):
        db.add(ReviewVote(review_id=busy.id, voter_id=make_user(db).id, vote=VoteDirection.up))
    db.add(ReviewComment(review_id=quiet.id, author_id=make_user(db).id, body="Same here."))
    old = NOW - timedelta(days=20)
    db.add(ReviewVote(review_id=stale.id, voter_id=make_user(db).id, vote=VoteDirection.up,
                      created_at=old, updated_at=old))
    db.flush()

    assert _ids(db, lens="trending", product_id=product.id) == [busy.id, quiet.id]


def test_a_chosen_date_order_wins_over_the_lens_order(db):
    product = _product(db)
    older = _review(db, product, up=2, down=2, days_ago=5)
    newer = _review(db, product, up=1, down=1, days_ago=1)
    assert _ids(db, lens="controversial", product_id=product.id) == [older.id, newer.id]
    assert _ids(db, lens="controversial", sort="newest", product_id=product.id) == [
        newer.id, older.id]


def test_trust_rating_bands_split_at_80(db):
    product = _product(db)
    trusted = _review(db, product, score="85")
    edge = _review(db, product, score="80")
    newer = _review(db, product, score="79.5")

    high = set(_ids(db, trust="high", product_id=product.id))
    low = set(_ids(db, trust="low", product_id=product.id))
    assert high == {trusted.id, edge.id}
    assert low == {newer.id}


def test_budget_keeps_what_was_paid_at_most_the_amount(db):
    product = _product(db)
    cheap = _review(db, product, price="450")
    exact = _review(db, product, price="1000")
    dear = _review(db, product, price="3200")
    silent = _review(db, product)

    ids = set(_ids(db, max_price=Decimal("1000"), product_id=product.id))
    assert ids == {cheap.id, exact.id}
    assert dear.id not in ids and silent.id not in ids


def test_the_feed_route_takes_the_new_filters_and_bounds_them(client):
    ok = client.get("/api/v1/reviews/feed", params={
        "lens": "trending", "trust": "high", "max_price": "2500"})
    assert ok.status_code == 200, ok.text
    for bad in ({"lens": "viral"}, {"trust": "medium"}, {"max_price": "0"},
                {"max_price": "-5"}):
        assert client.get("/api/v1/reviews/feed", params=bad).status_code == 422

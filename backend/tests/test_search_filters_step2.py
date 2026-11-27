"""Search filters, step 2 (owner 2026-10-07): the rest of what the Figma sheets draw.

Screen/Search/Reviews/Filters (7762:9999): Rating (whole-star groups), Show
only (With photos, Verified buyers, Recommends it), Variant, and the live
"Show 42 reviews" count; the Sort menu's "Lowest rated" (7762:9948).
Sheet/Filter sellers (8462:36591): Profile (claimed / unclaimed), Rating
(4★ & up, 3★ & up) and Answers buyers (within a day, within a week), with
its own "Show 24 sellers" count.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from tests.conftest import make_user, requires_db
from tests.test_figma_search_filters import _product, _question, _seller, _seller_review

NOW = datetime.now(UTC)


def _review(db, product, *, stars=4, photos=(), verified=False, verdict="it_depends",
            days_ago=1, variant=None, variant_status="pending"):
    from app.models.enums import (
        Platform,
        PriceObservationStatus,
        Verdict,
        VerificationStatus,
    )
    from app.models.product import PriceHistory
    from app.models.review import Review

    at = NOW - timedelta(days=days_ago)
    review = Review(product_id=product.id, author_id=make_user(db).id,
                    title=f"Probe {uuid.uuid4().hex[:6]}", discussion="Body.",
                    verdict=Verdict(verdict), star_rating=Decimal(str(stars)),
                    photo_urls=list(photos), is_removed=False, published_at=at, created_at=at,
                    verification_status=(VerificationStatus.verified if verified
                                         else VerificationStatus.unverified))
    db.add(review)
    db.flush()
    if variant is not None:
        db.add(PriceHistory(product_id=product.id, platform=Platform.shopee, price=Decimal("999"),
                            variant=variant, observed_at=date.today(), review_id=review.id,
                            status=PriceObservationStatus(variant_status)))
        db.flush()
    return review


def _ids(db, product, **show):
    from app.services import review_filters
    from app.services.review_service import count_feed, list_feed

    f = review_filters.FeedShow.of(**show)
    ids = [r.id for r, _, _ in list_feed(db, limit=100, product_id=product.id, show=f,
                                          sort="newest")]
    assert count_feed(db, product_id=product.id, show=f) == len(ids), "count disagrees with list"
    return ids


# ------------------------------------------------------------------- reviews

@requires_db
def test_rating_groups_are_whole_stars_and_several_may_be_picked(db):
    product = _product(db)
    five, four_half, four, two = (_review(db, product, stars=s, days_ago=d)
                                  for s, d in ((5, 1), (4.5, 2), (4, 3), (2, 4)))
    assert _ids(db, product, stars=[5]) == [five.id]
    assert _ids(db, product, stars=[4]) == [four_half.id, four.id]
    assert _ids(db, product, stars=[4, 2]) == [four_half.id, four.id, two.id]
    # All five groups is "All": nothing is filtered.
    assert _ids(db, product, stars=[1, 2, 3, 4, 5]) == [five.id, four_half.id, four.id, two.id]


@requires_db
def test_show_only_narrows_and_the_three_combine(db):
    product = _product(db)
    photo = _review(db, product, photos=["https://example.test/a.jpg"], days_ago=1)
    verified = _review(db, product, verified=True, days_ago=2)
    yes = _review(db, product, verdict="yes_absolutely", days_ago=3)
    every = _review(db, product, photos=["https://example.test/b.jpg"], verified=True,
                    verdict="yes_absolutely", days_ago=4)
    _review(db, product, verdict="hard_pass", days_ago=5)

    assert _ids(db, product, photos=True) == [photo.id, every.id]
    assert _ids(db, product, verified=True) == [verified.id, every.id]
    # "It depends" is not a recommendation.
    assert _ids(db, product, recommends=True) == [yes.id, every.id]
    assert _ids(db, product, photos=True, verified=True, recommends=True) == [every.id]


@requires_db
def test_variant_is_the_reviewers_own_and_the_product_lists_its_variants(db):
    from app.services.review_filters import variants_for_product

    product = _product(db)
    a = _review(db, product, variant="4000 mAh", days_ago=1)
    b = _review(db, product, variant="4000 mAh", variant_status="approved", days_ago=2)
    c = _review(db, product, variant="3600 mAh", days_ago=3)
    _review(db, product, variant="5000 mAh", variant_status="rejected", days_ago=4)
    _review(db, product, days_ago=5)

    assert _ids(db, product, variant="4000 MAH") == [a.id, b.id]
    assert _ids(db, product, variant="3600 mAh") == [c.id]
    # Most-reviewed first; a rejected observation names no variant.
    assert variants_for_product(db, product.id) == ["4000 mAh", "3600 mAh"]


@requires_db
def test_lowest_rated_puts_the_fewest_stars_first(db):
    from app.services.review_service import list_feed

    product = _product(db)
    high = _review(db, product, stars=5, days_ago=3)
    low = _review(db, product, stars=1.5, days_ago=2)
    mid_old = _review(db, product, stars=3, days_ago=5)
    mid_new = _review(db, product, stars=3, days_ago=1)
    order = [r.id for r, _, _ in list_feed(db, limit=10, product_id=product.id, sort="lowest")]
    assert order == [low.id, mid_new.id, mid_old.id, high.id]


@requires_db
def test_the_feed_routes_take_the_new_filters(client, db):
    product = _product(db)
    _review(db, product, stars=5, photos=["https://example.test/a.jpg"], variant="Blue")
    _review(db, product, stars=2)
    db.commit()
    base = f"/api/v1/reviews/feed?product_id={product.id}"
    rows = client.get(f"{base}&stars=5&photos=true&sort=lowest")
    assert rows.status_code == 200, rows.text
    assert len(rows.json()) == 1
    count = client.get(f"/api/v1/reviews/feed/count?product_id={product.id}&stars=5&stars=2")
    assert count.json() == {"total": 2}
    variants = client.get(f"/api/v1/reviews/feed/variants?product_id={product.id}")
    assert variants.json() == ["Blue"]
    assert client.get(f"{base}&stars=6").status_code == 422
    assert client.get(f"{base}&stars=0").status_code == 422


# ------------------------------------------------------------------- sellers

def _answer(db, question, *, after: timedelta, seller_answer=True):
    from app.models.qa import Answer

    db.add(Answer(question_id=question.id, responder_id=make_user(db).id, body="Yes.",
                  is_seller_answer=seller_answer, created_at=question.created_at + after))
    db.flush()


def _sellers(db, tag, **filters):
    from app.services.seller_service import count_sellers, list_sellers

    ids = {s.id for s in list_sellers(db, q=tag, platform=None, limit=50, **filters)}
    assert count_sellers(db, q=tag, platform=None, **filters) == len(ids)
    return ids


@requires_db
def test_profile_picks_claimed_or_unclaimed(db):
    tag = uuid.uuid4().hex[:8]
    claimed = _seller(db, claimed=True, name=f"A {tag}")
    unclaimed = _seller(db, claimed=False, name=f"B {tag}")
    assert _sellers(db, tag, claimed=True) == {claimed.id}
    assert _sellers(db, tag, claimed=False) == {unclaimed.id}
    assert _sellers(db, tag) == {claimed.id, unclaimed.id}


@requires_db
def test_rating_and_up_uses_the_shown_rating(db):
    tag = uuid.uuid4().hex[:8]
    great, ok, poor = (_seller(db, name=f"{n} {tag}") for n in ("A", "B", "C"))
    for store, rating in ((great, 5), (ok, 3), (poor, 2)):
        _seller_review(db, store, rating=rating)
    _seller(db, name=f"D {tag}")  # no reviews: no rating, never "& up"
    assert _sellers(db, tag, min_rating=4) == {great.id}
    assert _sellers(db, tag, min_rating=3) == {great.id, ok.id}


@requires_db
def test_answers_buyers_is_the_stores_median_time_to_its_own_answer(db):
    tag = uuid.uuid4().hex[:8]
    fast, slow, community = (_seller(db, name=f"{n} {tag}") for n in ("A", "B", "C"))
    for hours in (2, 5, 30):           # median 5 hours
        _answer(db, _question(db, seller=fast, days_ago=10), after=timedelta(hours=hours))
    for days in (3, 4):                # median 3.5 days
        _answer(db, _question(db, seller=slow, days_ago=10), after=timedelta(days=days))
    # Only a buyer answered: the store itself never did.
    _answer(db, _question(db, seller=community, days_ago=10), after=timedelta(hours=1),
            seller_answer=False)
    assert _sellers(db, tag, answers_within="day") == {fast.id}
    assert _sellers(db, tag, answers_within="week") == {fast.id, slow.id}


@requires_db
def test_the_seller_routes_take_the_new_filters(client, db):
    tag = uuid.uuid4().hex[:8]
    _seller(db, claimed=False, name=f"A {tag}")
    db.commit()
    rows = client.get(f"/api/v1/sellers?q={tag}&claimed=false&min_rating=3")
    assert rows.status_code == 200 and rows.json() == []
    count = client.get(f"/api/v1/sellers/count?q={tag}&claimed=false")
    assert count.json() == {"total": 1}
    assert client.get("/api/v1/sellers?min_rating=6").status_code == 422
    assert client.get("/api/v1/sellers?answers_within=month").status_code == 422

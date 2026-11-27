"""Search and listing controls the Figma frames draw, served for real (2026-09-24).

Each control here exists because the API can do what it says:

- QA-025: several categories at once; a review in any of them is shown.
- QA-053: the All filters sheet's Time (all / past year / past month) and the
  Sort frame's Oldest, on the review feed.
- QA-050: the same Time and By-date order on the Questions tab, and the
  product's stored image for the question row's tile.
- QA-052: a store's answered-question count, a claimed-only filter and a
  most-reviewed order on the Sellers tab.
- QA-020: a comment author's public score, for the byline's Honesty Score.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tests.conftest import make_user, requires_db

NOW = datetime.now(UTC)


def _product(db, category="electronics", image_url=None):
    from app.models.product import Product

    product = Product(canonical_name=f"Filter probe {uuid.uuid4().hex[:8]}",
                      category=category, image_url=image_url)
    db.add(product)
    db.flush()
    return product


def _review(db, product, *, published_days_ago=1, title=None):
    from app.models.enums import Verdict
    from app.models.review import Review

    at = NOW - timedelta(days=published_days_ago)
    review = Review(product_id=product.id, author_id=make_user(db).id,
                    title=title or f"Probe {uuid.uuid4().hex[:6]}", discussion="Body.",
                    verdict=Verdict.it_depends, star_rating=4, is_removed=False,
                    published_at=at, created_at=at)
    db.add(review)
    db.flush()
    return review


def _feed_ids(db, **kwargs):
    from app.services.review_service import list_feed

    return [r.id for r, _, _ in list_feed(db, limit=100, **kwargs)]


# --------------------------------------------------------------- review feed

@requires_db
def test_several_categories_show_reviews_in_any_of_them(db):
    tag = uuid.uuid4().hex[:8]
    a = _review(db, _product(db, "electronics"), title=f"multi {tag} a")
    b = _review(db, _product(db, "beauty"), title=f"multi {tag} b")
    c = _review(db, _product(db, "pets"), title=f"multi {tag} c")

    both = set(_feed_ids(db, category=["electronics", "beauty"], q=f"multi {tag}"))
    assert {a.id, b.id} <= both and c.id not in both
    # A single category, as every existing caller passes it, is unchanged.
    one = set(_feed_ids(db, category="beauty", q=f"multi {tag}"))
    assert b.id in one and a.id not in one


@requires_db
@pytest.mark.parametrize(("period", "kept", "dropped"), [
    ("month", {5}, {60, 500}),
    ("year", {5, 60}, {500}),
    ("all", {5, 60, 500}, set()),
])
def test_time_keeps_only_the_period(db, period, kept, dropped):
    tag = uuid.uuid4().hex[:8]
    product = _product(db)
    by_age = {d: _review(db, product, published_days_ago=d, title=f"time {tag} {d}")
              for d in (5, 60, 500)}
    ids = set(_feed_ids(db, product_id=product.id, period=period))
    assert {by_age[d].id for d in kept} <= ids
    assert not ({by_age[d].id for d in dropped} & ids)


@requires_db
def test_oldest_first_is_the_reverse_of_newest(db):
    product = _product(db)
    reviews = [_review(db, product, published_days_ago=d) for d in (3, 2, 1)]
    oldest = _feed_ids(db, product_id=product.id, sort="oldest")
    newest = _feed_ids(db, product_id=product.id, sort="newest")
    assert oldest == [r.id for r in reviews]
    assert newest == list(reversed(oldest))


@requires_db
def test_the_feed_route_takes_the_new_controls_and_bounds_them(client):
    ok = client.get("/api/v1/reviews/feed?category=electronics&category=beauty"
                    "&period=month&sort=oldest")
    assert ok.status_code == 200, ok.text
    assert client.get("/api/v1/reviews/feed?period=decade").status_code == 422
    assert client.get("/api/v1/reviews/feed?sort=random").status_code == 422
    too_many = "&".join(f"category=c{i}" for i in range(13))
    assert client.get(f"/api/v1/reviews/feed?{too_many}").status_code == 422


# ----------------------------------------------------------------- questions

def _question(db, *, product=None, seller=None, days_ago=1, body=None):
    from app.models.enums import QuestionDirectedTo
    from app.models.qa import Question

    at = NOW - timedelta(days=days_ago)
    question = Question(product_id=product.id if product else None,
                        seller_id=seller.id if seller else None,
                        asker_id=make_user(db).id,
                        body=body or f"Does it last? {uuid.uuid4().hex[:6]}",
                        directed_to=(QuestionDirectedTo.seller if seller
                                     else QuestionDirectedTo.buyers),
                        created_at=at)
    db.add(question)
    db.flush()
    return question


@requires_db
def test_questions_take_time_and_order_and_carry_the_product_image(db):
    from app.services.qa_service import list_questions

    product = _product(db, image_url="https://example.test/p.jpg")
    old, mid, new = (_question(db, product=product, days_ago=d) for d in (400, 60, 2))

    month = [q.id for q in list_questions(db, product_id=product.id, period="month")]
    assert month == [new.id]
    year = [q.id for q in list_questions(db, product_id=product.id, period="year")]
    assert year == [new.id, mid.id]
    oldest = [q.id for q in list_questions(db, product_id=product.id, sort="oldest")]
    assert oldest == [old.id, mid.id, new.id]
    assert {q.product_image_url for q in list_questions(db, product_id=product.id)} == {
        "https://example.test/p.jpg"}


@requires_db
def test_the_question_route_takes_the_new_controls(client):
    assert client.get("/api/v1/questions?period=year&sort=oldest").status_code == 200
    assert client.get("/api/v1/questions?sort=best").status_code == 422


# ------------------------------------------------------------------- sellers

def _seller(db, *, claimed=False, name=None):
    from app.models.enums import Platform, SellerClaimStatus
    from app.models.seller import Seller
    from app.services.seller_service import normalize_seller_name

    name = name or f"Probe Store {uuid.uuid4().hex[:8]}"
    seller = Seller(display_name=name, normalized_name=normalize_seller_name(name),
                    platform=Platform.shopee,
                    claim_status=(SellerClaimStatus.claimed if claimed
                                  else SellerClaimStatus.unclaimed))
    db.add(seller)
    db.flush()
    return seller


def _seller_review(db, seller, rating=4):
    from app.models.seller import SellerReview

    db.add(SellerReview(seller_id=seller.id, reviewer_id=make_user(db).id, accuracy=True,
                        order_completeness=True, customer_service=4, packaging_quality=4,
                        overall_rating=Decimal(rating), would_recommend=True))
    db.flush()


@requires_db
def test_a_store_counts_only_its_answered_questions(db):
    from app.models.qa import Answer
    from app.services.seller_service import get_seller_detail, list_sellers

    seller = _seller(db)
    answered = _question(db, seller=seller)
    _question(db, seller=seller)                              # unanswered
    removed = _question(db, seller=seller)
    removed.is_removed = True
    for q in (answered, removed):
        db.add(Answer(question_id=q.id, responder_id=make_user(db).id, body="Yes."))
    db.flush()

    [row] = [s for s in list_sellers(db, q=seller.display_name, platform=None, limit=10)
             if s.id == seller.id]
    assert row.answered_question_count == 1
    assert get_seller_detail(db, seller.id).answered_question_count == 1


@requires_db
def test_claimed_only_and_most_reviewed_first(db):
    from app.services.seller_service import list_sellers

    tag = uuid.uuid4().hex[:8]
    quiet = _seller(db, claimed=True, name=f"Aaa {tag}")
    busy = _seller(db, claimed=False, name=f"Zzz {tag}")
    for _ in range(3):
        _seller_review(db, busy)

    by_name = [s.id for s in list_sellers(db, q=tag, platform=None, limit=10, sort="name")]
    assert by_name == [quiet.id, busy.id]
    most = [s.id for s in list_sellers(db, q=tag, platform=None, limit=10, sort="reviews")]
    assert most == [busy.id, quiet.id]
    claimed = [s.id for s in list_sellers(db, q=tag, platform=None, limit=10,
                                          claimed_only=True)]
    assert claimed == [quiet.id]


@requires_db
def test_the_seller_route_takes_the_new_controls(client):
    assert client.get("/api/v1/sellers?claimed=true&sort=reviews").status_code == 200
    assert client.get("/api/v1/sellers?sort=rating").status_code == 422


# ------------------------------------------------------------------ comments

def test_a_comment_author_carries_the_public_score():
    from app.schemas.comment import CommentAuthor

    fields = CommentAuthor.model_fields
    assert "reputation_score" in fields
    # Nothing private rides along: no email, wallet or staff reference.
    assert not ({"email", "wallet_balance", "staff_ref", "payout_account"} & set(fields))

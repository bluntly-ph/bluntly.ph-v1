"""Page-shaped reads (cost work, 2026-10-22): app/api/v1/routes/pages.py.

The review page made seven backend calls per visit and a worded search up to
eleven; each was a billed function call, a database transaction and a CDN
round trip. These routes answer a whole page in one call. They must change
nothing but the number of trips, so every test here compares the bundled
answer with what the separate routes return for the same viewer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import make_user, register_and_token, requires_db

NOW = datetime.now(UTC)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(db, *, name, category="electronics", review_count=0):
    from app.models.product import Product

    product = Product(canonical_name=name, category=category, review_count=review_count)
    db.add(product)
    db.flush()
    return product


def _review(db, product, *, title, published=True, days_ago=1, helpful=0):
    from app.models.enums import Verdict
    from app.models.review import Review

    at = NOW - timedelta(days=days_ago, minutes=len(title))
    review = Review(product_id=product.id, author_id=make_user(db).id, title=title,
                    discussion=f"{title}. " * 30, verdict=Verdict.it_depends,
                    star_rating=4, is_removed=False, published_at=at if published else None,
                    created_at=at, helpful_votes=helpful)
    db.add(review)
    db.flush()
    return review


@pytest.fixture
def review_page_data(db):
    tag = uuid.uuid4().hex[:10]
    category = f"probe-{tag}"
    product = _product(db, name=f"Bundle probe {tag}", category=category, review_count=4)
    reviews = [_review(db, product, title=f"{tag} take {i}", days_ago=1 + i, helpful=i)
               for i in range(4)]
    db.commit()
    return tag, product, reviews


# --------------------------------------------------------------------------
# GET /pages/review/{id}
# --------------------------------------------------------------------------

@requires_db
def test_review_page_matches_the_separate_routes(client, review_page_data):
    _, product, reviews = review_page_data
    rid, pid = reviews[0].id, product.id

    page = client.get(f"/api/v1/pages/review/{rid}")
    assert page.status_code == 200, page.text
    body = page.json()

    assert body["review"] == client.get(f"/api/v1/reviews/{rid}/full").json()
    assert body["comments"] == client.get(f"/api/v1/reviews/{rid}/comments").json()
    assert body["thread"] == client.get(f"/api/v1/reviews/{rid}/thread").json()
    assert body["price_panel"] == client.get(f"/api/v1/products/{pid}/prices").json()
    assert body["removed_after_payout_count"] == \
        client.get(f"/api/v1/products/{pid}").json()["removed_after_payout_count"]

    related = client.get("/api/v1/reviews/feed", params={
        "category": product.category, "sort": "wilson", "limit": 5, "view": "card"}).json()
    assert body["related"] == related
    assert len(body["related"]) == 4


@requires_db
def test_review_page_keeps_the_publication_gate(client, db, review_page_data):
    _, product, _ = review_page_data
    hidden = _review(db, product, title="unpublished draft", published=False)
    db.commit()

    full = client.get(f"/api/v1/reviews/{hidden.id}/full")
    page = client.get(f"/api/v1/pages/review/{hidden.id}")
    assert full.status_code == 404
    assert page.status_code == 404
    assert client.get(f"/api/v1/pages/review/{uuid.uuid4()}").status_code == 404


@requires_db
def test_review_page_carries_the_viewers_own_vote(client, db, review_page_data):
    from app.models.enums import VoteDirection
    from app.models.vote import ReviewVote

    _, _, reviews = review_page_data
    uid, token, _ = register_and_token(client)
    db.add(ReviewVote(review_id=reviews[1].id, voter_id=uuid.UUID(uid), vote=VoteDirection.up))
    db.commit()

    signed_in = client.get(f"/api/v1/pages/review/{reviews[1].id}", headers=_auth(token)).json()
    signed_out = client.get(f"/api/v1/pages/review/{reviews[1].id}").json()
    assert signed_in["review"]["review"]["my_vote"] == "up"
    assert signed_out["review"]["review"]["my_vote"] is None
    # The sidebar is read signed out, as it always was.
    assert all(card["review"]["my_vote"] is None for card in signed_in["related"])


# --------------------------------------------------------------------------
# GET /reviews/my-votes
# --------------------------------------------------------------------------

@requires_db
def test_my_votes_returns_only_the_readers_votes(client, db, review_page_data):
    from app.models.enums import VoteDirection
    from app.models.vote import ReviewVote

    _, _, reviews = review_page_data
    uid, token, _ = register_and_token(client)
    other_uid, _, _ = register_and_token(client)
    db.add(ReviewVote(review_id=reviews[0].id, voter_id=uuid.UUID(uid), vote=VoteDirection.up))
    db.add(ReviewVote(review_id=reviews[1].id, voter_id=uuid.UUID(uid), vote=VoteDirection.down))
    db.add(ReviewVote(review_id=reviews[2].id, voter_id=uuid.UUID(other_uid),
                      vote=VoteDirection.up))
    db.commit()

    resp = client.get("/api/v1/reviews/my-votes", headers=_auth(token),
                      params={"ids": [str(r.id) for r in reviews]})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"votes": {str(reviews[0].id): "up", str(reviews[1].id): "down"}}


@requires_db
def test_my_votes_needs_a_session_and_bounds_its_input(client, review_page_data):
    _, _, reviews = review_page_data
    assert client.get("/api/v1/reviews/my-votes",
                      params={"ids": [str(reviews[0].id)]}).status_code == 401
    _, token, _ = register_and_token(client)
    too_many = [str(uuid.uuid4()) for _ in range(101)]
    assert client.get("/api/v1/reviews/my-votes", headers=_auth(token),
                      params={"ids": too_many}).status_code == 422
    assert client.get("/api/v1/reviews/my-votes", headers=_auth(token)).status_code == 422


# --------------------------------------------------------------------------
# GET /search/resolve (was lib/search-product.ts)
# --------------------------------------------------------------------------

@pytest.fixture
def fans(db):
    tag = uuid.uuid4().hex[:8]
    big = _product(db, name=f"Jisulife{tag} Fan", review_count=9)
    small = _product(db, name=f"Jisulife{tag} Mini Fan", review_count=2)
    db.commit()
    return tag, big, small


@requires_db
def test_resolve_splits_product_words_from_the_question(client, fans):
    tag, big, small = fans
    resp = client.get("/api/v1/search/resolve", params={"q": f"jisulife{tag} fan noise library"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chosen"]["product"]["id"] == str(big.id)
    assert body["productTerms"] == f"jisulife{tag} fan"
    assert body["rest"] == "noise library"
    # "jisulife… fan" names the Fan only: the Mini Fan's name does not start
    # with those words. The one-word run would list both, but the longest run
    # whose best match is as reviewed as any is the one kept.
    assert [m["product"]["id"] for m in body["matches"]] == [str(big.id)]
    assert body["chosen"]["card"] == \
        client.get(f"/api/v1/products/{big.id}/search-card").json()


@requires_db
def test_resolve_honours_the_readers_pick(client, fans):
    tag, big, small = fans
    body = client.get("/api/v1/search/resolve",
                      params={"q": f"jisulife{tag}", "pick": str(small.id)}).json()
    ids = [m["product"]["id"] for m in body["matches"]]
    assert ids[:2] == [str(big.id), str(small.id)], "most-reviewed first"
    assert body["chosen"]["product"]["id"] == str(small.id)


@requires_db
def test_resolve_fetches_a_pick_outside_the_matches(client, db, fans):
    tag, _, _ = fans
    elsewhere = _product(db, name=f"Unrelated{tag} Kettle", review_count=1)
    db.commit()
    body = client.get("/api/v1/search/resolve",
                      params={"q": f"jisulife{tag}", "pick": str(elsewhere.id)}).json()
    assert body["chosen"]["product"]["id"] == str(elsewhere.id)
    assert body["chosen"]["card"] is not None
    # A pick that is not an id is ignored, as before: the best match stands.
    body = client.get("/api/v1/search/resolve",
                      params={"q": f"jisulife{tag}", "pick": "not-an-id"}).json()
    assert body["chosen"]["product"]["id"] == body["matches"][0]["product"]["id"]


@requires_db
def test_resolve_answers_null_when_nothing_matches(client):
    resp = client.get("/api/v1/search/resolve",
                      params={"q": f"zz{uuid.uuid4().hex[:12]}qq"})
    assert resp.status_code == 200
    assert resp.json() is None

"""The author's own reviews in every state — GET /reviews/mine (2026-09-18).

A real user submitted a review, saw it accepted, refreshed their profile and
found it gone: the profile read the public feed. Since 2026-09-22 reviews are
public from submission (confirmed by Zient), so the states the author sees are:

    published  the normal case — public at once, and listed for its author
    pending    taken down by a moderator; visible to its author, nowhere public
    rejected   legacy: rejected under the old hide-until-approved flow

Earnings are a separate state and never change what the author sees here.
"""

from __future__ import annotations

import uuid

from tests.conftest import owned_photo_url, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers: dict) -> str:
    resp = client.post("/api/v1/products", headers=headers,
                       json={"name": f"OwnReviewsWidget {uuid.uuid4().hex[:8]}",
                             "category": "electronics"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _submit(client, headers: dict, product_id: str, title: str) -> dict:
    resp = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product_id,
        "title": title,
        "discussion": "Weeks of use and it has held up well.",
        "verdict": "yes_absolutely",
        "star_rating": 4,
        "photo_url": owned_photo_url(headers),
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _mine(client, headers: dict) -> dict[str, dict]:
    resp = client.get("/api/v1/reviews/mine", headers=headers, params={"limit": 100})
    assert resp.status_code == 200, resp.text
    return {item["review"]["id"]: item for item in resp.json()}


def _public_feed_ids(client, author_id: str, headers: dict | None = None) -> set[str]:
    resp = client.get("/api/v1/reviews/feed", headers=headers or {},
                      params={"author_id": author_id, "sort": "newest", "limit": 100})
    assert resp.status_code == 200, resp.text
    return {item["review"]["id"] for item in resp.json()}


@requires_db
def test_mine_needs_a_signed_in_caller(client):
    assert client.get("/api/v1/reviews/mine").status_code == 401


@requires_db
def test_a_submitted_review_is_public_at_once_and_listed_for_its_author(client):
    author_id, token, _ = register_and_token(client)
    headers = _auth(token)
    review = _submit(client, headers, _product(client, headers), "Public on submit")

    assert review["published_at"] is not None
    mine = _mine(client, headers)
    assert mine[review["id"]]["status"] == "published"
    assert mine[review["id"]]["author"]["id"] == str(author_id)
    # Everyone can read it, signed in or not, and it is on the public profile.
    assert client.get(f"/api/v1/reviews/{review['id']}/full").status_code == 200
    _, other_token, _ = register_and_token(client)
    assert client.get(f"/api/v1/reviews/{review['id']}/full",
                      headers=_auth(other_token)).status_code == 200
    assert review["id"] in _public_feed_ids(client, str(author_id))
    assert review["id"] not in _mine(client, _auth(other_token))


@requires_db
def test_approving_earnings_does_not_change_what_the_author_sees(client):
    author_id, token, _ = register_and_token(client)
    headers = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    review = _submit(client, headers, _product(client, headers), "Worth earning")

    approved = client.post(f"/api/v1/admin/reviews/{review['id']}/approve-earnings",
                           headers=_auth(mod_token))
    assert approved.status_code == 200, approved.text
    assert approved.json()["published_at"] == review["published_at"]
    assert _mine(client, headers)[review["id"]]["status"] == "published"
    assert review["id"] in _public_feed_ids(client, str(author_id))


@requires_db
def test_rejecting_earnings_keeps_the_review_public(client):
    author_id, token, _ = register_and_token(client)
    headers = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    review = _submit(client, headers, _product(client, headers), "Not earning")

    rejected = client.post(f"/api/v1/admin/reviews/{review['id']}/reject",
                           headers=_auth(mod_token), json={"reason": "No proof of purchase."})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["earn_eligible_status"] == "rejected"
    assert _mine(client, headers)[review["id"]]["status"] == "published"
    assert review["id"] in _public_feed_ids(client, str(author_id))
    assert client.get(f"/api/v1/reviews/{review['id']}/full").status_code == 200


@requires_db
def test_a_taken_down_review_stays_with_its_author_and_nowhere_public(client):
    author_id, token, _ = register_and_token(client)
    headers = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    review = _submit(client, headers, _product(client, headers), "Taken down")

    down = client.post(f"/api/v1/admin/reviews/{review['id']}/unpublish",
                       headers=_auth(mod_token), json={"reason": "Checking a report."})
    assert down.status_code == 200, down.text
    assert _mine(client, headers)[review["id"]]["status"] == "pending"
    assert client.get(f"/api/v1/reviews/{review['id']}/full", headers=headers).status_code == 200
    assert client.get(f"/api/v1/reviews/{review['id']}/full").status_code == 404
    assert review["id"] not in _public_feed_ids(client, str(author_id))

    back = client.post(f"/api/v1/admin/reviews/{review['id']}/restore", headers=_auth(mod_token))
    assert back.status_code == 200, back.text
    # Restored at its original publication time, not "now".
    assert back.json()["published_at"] == review["published_at"]
    assert client.get(f"/api/v1/reviews/{review['id']}/full").status_code == 200


@requires_db
def test_mine_is_the_callers_own_newest_first(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    # Two products: an author reviews a product once (Business Rules §4).
    first = _submit(client, headers, _product(client, headers), "First of two")
    second = _submit(client, headers, _product(client, headers), "Second of two")

    resp = client.get("/api/v1/reviews/mine", headers=headers, params={"limit": 100})
    ids = [item["review"]["id"] for item in resp.json()]
    assert ids.index(second["id"]) < ids.index(first["id"])
    # There is no author parameter to point it at someone else.
    _, other_token, _ = register_and_token(client)
    assert client.get("/api/v1/reviews/mine", headers=_auth(other_token),
                      params={"author_id": ids[0]}).json() == []

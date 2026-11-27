"""Double-submit and post-submit behaviour (BUG-031) — integration.

QA filed this as "cannot verify", not as "broken": double-submit prevention and
post-submit state needed moderator access they did not have. The suspicion was
right. The composer disabled its own button while a request was in flight and
nothing else stopped a second one, so two taps that beat a re-render — or a
retry on a slow connection, or a second tab, or anything posting to the API
directly — produced two identical reviews in the moderation queue, with no way
for their author to remove either.

These tests are the verification QA could not run: the duplicate is refused, a
legitimate second review is not, and the post-submit state is what the
confirmation screen claims it is.
"""

from __future__ import annotations

import uuid

from tests.conftest import owned_photo_url, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers: dict, name: str) -> str:
    resp = client.post("/api/v1/products", headers=headers,
                       json={"name": f"{name} {uuid.uuid4().hex[:8]}",
                             "category": "electronics"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _submission(product_id: str, headers: dict, title: str = "Solid") -> dict:
    return {
        "product_id": product_id,
        "title": title,
        "discussion": "Weeks of use and it has held up well.",
        "verdict": "yes_absolutely",
        "star_rating": 4,
        "photo_url": owned_photo_url(headers),
    }


@requires_db
def test_the_same_review_submitted_twice_creates_one(client):
    """The bug in one test: press Publish twice, get one review."""
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    product = _product(client, headers, "DoubleSubmitWidget")
    payload = _submission(product, headers)

    first = client.post("/api/v1/reviews", headers=headers, json=payload)
    assert first.status_code == 201, first.text

    second = client.post("/api/v1/reviews", headers=headers, json=payload)
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "review_already_pending"

    mine = client.get("/api/v1/reviews", headers=headers,
                      params={"product_id": product, "limit": 50})
    assert mine.status_code == 200, mine.text
    ids = {r["id"] for r in mine.json()}
    assert ids == {first.json()["id"]}, "a second review of the product exists"


@requires_db
def test_a_second_review_of_the_same_product_is_a_thread_update_not_a_new_review(client):
    """Business Rules §4 supersedes the old "different review, same product is
    fine": more to say later is a new entry on the SAME thread, every 3 months,
    never a second independent review. The endpoint refuses and says where to go.
    """
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    product = _product(client, headers, "RetypeWidget")
    first = client.post("/api/v1/reviews", headers=headers,
                        json=_submission(product, headers, "First go"))
    assert first.status_code == 201, first.text
    second = _submission(product, headers, "Second go")
    second["discussion"] = "A different experience, written out separately."
    again = client.post("/api/v1/reviews", headers=headers, json=second)
    assert again.status_code == 409, again.text
    body = again.json()
    assert body["code"] == "review_thread_exists"
    assert body["thread_id"] == first.json()["id"]
    assert body["next_update_at"]
    # Same body, different title: still the same author's second review.
    third = client.post("/api/v1/reviews", headers=headers,
                        json=_submission(product, headers, "Third title"))
    assert third.status_code == 409


@requires_db
def test_another_reviewer_is_not_blocked_by_yours(client):
    """The rule is per author. Two people reviewing one product is the product."""
    _, mine, _ = register_and_token(client)
    _, theirs, _ = register_and_token(client)
    product = _product(client, _auth(mine), "SharedWidget")

    assert client.post("/api/v1/reviews", headers=_auth(mine),
                       json=_submission(product, _auth(mine))).status_code == 201
    assert client.post("/api/v1/reviews", headers=_auth(theirs),
                       json=_submission(product, _auth(theirs))).status_code == 201


@requires_db
def test_a_second_product_is_not_blocked(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    one = _product(client, headers, "FirstWidget")
    two = _product(client, headers, "SecondWidget")

    assert client.post("/api/v1/reviews", headers=headers,
                       json=_submission(one, headers)).status_code == 201
    assert client.post("/api/v1/reviews", headers=headers,
                       json=_submission(two, headers)).status_code == 201


@requires_db
def test_an_earnings_rejection_keeps_the_review_and_its_thread(client):
    """An earnings rejection no longer hides a review (§2) and the thread stays
    the author's one review of the product (§4): no fresh review around it."""
    _, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    headers, mh = _auth(token), _auth(mod_token)
    product = _product(client, headers, "ResubmitWidget")
    first = client.post("/api/v1/reviews", headers=headers,
                        json=_submission(product, headers)).json()["id"]
    rejected = client.post(f"/api/v1/admin/reviews/{first}/reject", headers=mh,
                           json={"reason": "Needs a clearer photo."})
    assert rejected.status_code == 200, rejected.text
    assert client.get(f"/api/v1/reviews/{first}").status_code == 200
    again = client.post("/api/v1/reviews", headers=headers,
                        json=_submission(product, headers, "With a better photo"))
    assert again.status_code == 409
    assert again.json()["code"] == "review_thread_exists"


@requires_db
def test_buying_again_later_is_an_update_on_the_same_thread(client):
    """Buying the same thing again a year later is not a double submit; under
    §4 it is an update entry, opened three months after the last one."""
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    product = _product(client, headers, "SecondPurchaseWidget")
    first = client.post("/api/v1/reviews", headers=headers,
                        json=_submission(product, headers)).json()["id"]
    too_soon = client.post(f"/api/v1/reviews/{first}/updates", headers=headers,
                           json={k: v for k, v in _submission(product, headers,
                                                             "Bought it again").items()
                                 if k != "product_id"})
    assert too_soon.status_code == 409, too_soon.text
    assert too_soon.json()["code"] == "thread_update_cooldown"


@requires_db
def test_post_submit_state_is_what_the_confirmation_claims(client):
    """The other half of BUG-031: where the review goes after Publish.

    Since 2026-09-22 the composer's last screen says "Your review is now live!"
    (Figma 4550:8882). That has to be true — public, in the feed, visible to
    its author — and, in the Seeding Phase, in the moderator's earn_eligible
    queue for its earnings decision.
    """
    _, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    headers, mh = _auth(token), _auth(mod_token)
    product = _product(client, headers, "PostSubmitWidget")

    created = client.post("/api/v1/reviews", headers=headers,
                          json=_submission(product, headers))
    assert created.status_code == 201, created.text
    review_id = created.json()["id"]

    # Public, and in the public feed.
    assert client.get(f"/api/v1/reviews/{review_id}").status_code == 200
    feed = client.get("/api/v1/reviews/feed", params={"limit": 100, "sort": "newest"}).json()
    assert review_id in [i["review"]["id"] for i in feed]

    # Visible to its author.
    assert client.get(f"/api/v1/reviews/{review_id}", headers=headers).status_code == 200

    # And waiting for an earnings decision (Seeding Phase).
    queue = client.get("/api/v1/admin/review-queue", headers=mh,
                       params={"q": "PostSubmitWidget", "limit": 100}).json()
    assert review_id in [i["review"]["id"] for i in queue["items"]]

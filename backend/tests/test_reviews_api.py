"""Review submission, version history, and ownership enforcement (integration)."""

from __future__ import annotations

from tests.conftest import owned_photo_url, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@requires_db
def test_review_submission_and_versioning(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)

    prod = client.post("/api/v1/products", headers=headers,
                       json={"name": f"Test Earbuds {token[-10:]}", "category": "electronics"})
    assert prod.status_code == 201, prod.text
    product_id = prod.json()["id"]

    created = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product_id, "title": "Solid pick", "discussion": "Used daily for a month.",
        "verdict": "yes_absolutely", "star_rating": 4, "pros": ["battery"], "cons": ["case"],
        "photo_url": owned_photo_url(headers)})
    assert created.status_code == 201, created.text
    review = created.json()
    review_id = review["id"]
    assert review["verification_status"] == "verified"  # photo => verified
    assert review["current_version"] == 1
    # Public from submission (confirmed by Zient 2026-09-22). Earning is
    # separate: queued for a decision (the suite runs the Seeding Phase
    # explicitly; the application default leaves it at `none`), not earning.
    assert review["published_at"] is not None
    assert review["earn_eligible_status"] == "pending"
    assert review["referral_redirect_url"] is None

    # Business Rules §4: published text, rating and verdict are frozen forever.
    for frozen in ({"title": "Solid pick (updated)"}, {"star_rating": 2},
                   {"verdict": "hard_pass"}, {"discussion": "Rewritten."},
                   {"pros": ["other"]}):
        refused = client.patch(f"/api/v1/reviews/{review_id}", headers=headers, json=frozen)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "review_content_frozen"

    # The one exception: a single photo swap within 72 hours -> version 2.
    swapped = client.patch(f"/api/v1/reviews/{review_id}", headers=headers,
                           json={"photo_url": owned_photo_url(headers)})
    assert swapped.status_code == 200, swapped.text
    assert swapped.json()["current_version"] == 2
    assert swapped.json()["photo_replaced_at"] is not None
    assert swapped.json()["title"] == "Solid pick"

    # A second swap is refused, even inside the window.
    second = client.patch(f"/api/v1/reviews/{review_id}", headers=headers,
                          json={"photo_url": owned_photo_url(headers)})
    assert second.status_code == 409
    assert second.json()["code"] == "photo_swap_used"

    # A public review's history is public; the author reads it too.
    assert client.get(f"/api/v1/reviews/{review_id}/versions").status_code == 200
    versions = client.get(f"/api/v1/reviews/{review_id}/versions", headers=headers)
    assert versions.status_code == 200
    assert [v["version_number"] for v in versions.json()] == [1, 2]

    v1 = client.get(f"/api/v1/reviews/{review_id}/versions/1", headers=headers)
    assert v1.json()["snapshot"]["title"] == "Solid pick"  # original preserved


@requires_db
def test_unverified_without_photo(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    product_id = client.post("/api/v1/products", headers=headers,
                             json={"name": f"No Photo Product {token[-10:]}"}).json()["id"]
    r = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product_id, "title": "Meh", "discussion": "No proof attached.",
        "verdict": "it_depends", "star_rating": 3})
    assert r.json()["verification_status"] == "unverified"


@requires_db
def test_only_the_author_can_touch_a_review_and_only_its_photo(client):
    _, author_token, _ = register_and_token(client)
    _, other_token, _ = register_and_token(client)
    ah = _auth(author_token)

    product_id = client.post("/api/v1/products", headers=ah,
                             json={"name": f"Owned Product {author_token[-10:]}"}).json()["id"]
    review_id = client.post("/api/v1/reviews", headers=ah, json={
        "product_id": product_id, "title": "Mine", "discussion": "My review.",
        "verdict": "hard_pass", "star_rating": 2}).json()["id"]

    forbidden = client.patch(f"/api/v1/reviews/{review_id}", headers=_auth(other_token),
                             json={"photo_url": owned_photo_url(_auth(other_token))})
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "not_review_owner"

    # §4: not even a moderator edits published content.
    _, mod_token, _ = register_and_token(client, role="administrator")
    refused = client.patch(f"/api/v1/reviews/{review_id}", headers=_auth(mod_token),
                           json={"title": "moderated"})
    assert refused.status_code == 403

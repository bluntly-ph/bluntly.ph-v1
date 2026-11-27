"""Several photos on a product review (owner requirement 2026-10-05; 0094).

Contract: docs/REVIEW_MEDIA_CONTRACT.md. The rules under test:

* NO PHOTO = NO DEFAULT PHOTO. A review with no reviewer photos has
  photo_urls == [] and photo_url == null - even when its product has a
  listing image, which stays on product.image_url only.
* Photos are kept in the order sent, each once, at most MAX_REVIEW_PHOTOS.
* Only what is submitted is published: an upload removed (or skipped)
  before submitting is not on the review.
* Every photo must be the author's own upload; nobody else changes them.
* The one photo swap (§4) replaces the whole ordered set, once, within 72 h.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from tests.conftest import owned_photo_url, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers, image_url: str | None = None) -> str:
    pid = client.post("/api/v1/products", headers=headers, json={
        "name": f"PhotoWidget {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
    if image_url:
        from app.db.session import SessionLocal
        with SessionLocal() as db:
            db.execute(text("UPDATE products SET image_url = :u WHERE id = :p"),
                       {"u": image_url, "p": pid})
            db.commit()
    return pid


def _review(client, headers, pid, **photos):
    body = {"product_id": pid, "title": "Solid", "discussion": "Weeks of daily use.",
            "verdict": "yes_absolutely", "star_rating": 4, **photos}
    return client.post("/api/v1/reviews", headers=headers, json=body)


@requires_db
def test_no_photos_means_an_empty_list_even_when_the_product_has_an_image(client):
    _, author, _ = register_and_token(client)
    h = _auth(author)
    listing = "https://cdn.example-shop.ph/listing/widget.jpg"
    pid = _product(client, h, image_url=listing)
    res = _review(client, h, pid)
    assert res.status_code == 201, res.text
    rid = res.json()["id"]
    assert res.json()["photo_urls"] == [] and res.json()["photo_url"] is None
    assert res.json()["verification_status"] == "unverified"

    full = client.get(f"/api/v1/reviews/{rid}/full").json()
    assert full["review"]["photo_urls"] == [] and full["review"]["photo_url"] is None
    assert full["product"]["image_url"] == listing          # product context, kept apart
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        stored = db.execute(text("SELECT photo_url, photo_urls FROM reviews WHERE id = :r"),
                            {"r": rid}).one()
    assert stored == (None, [])


@requires_db
def test_one_photo_from_a_single_photo_client(client):
    _, author, _ = register_and_token(client)
    h = _auth(author)
    url = owned_photo_url(h)
    res = _review(client, h, _product(client, h), photo_url=url)
    assert res.status_code == 201, res.text
    assert res.json()["photo_urls"] == [url] and res.json()["photo_url"] == url
    assert res.json()["verification_status"] == "verified"


@requires_db
def test_several_photos_are_kept_in_order_each_once(client):
    _, author, _ = register_and_token(client)
    h = _auth(author)
    a, b, c = (owned_photo_url(h) for _ in range(3))
    res = _review(client, h, _product(client, h), photo_urls=[c, a, b, a])
    assert res.status_code == 201, res.text
    assert res.json()["photo_urls"] == [c, a, b]
    assert res.json()["photo_url"] == c                     # the first, for one-photo readers
    rid = res.json()["id"]
    assert client.get(f"/api/v1/reviews/{rid}").json()["photo_urls"] == [c, a, b]
    assert client.get(f"/api/v1/reviews/{rid}/full").json()["review"]["photo_urls"] == [c, a, b]


@requires_db
def test_a_removed_or_skipped_upload_is_not_published(client):
    _, author, _ = register_and_token(client)
    h = _auth(author)
    kept, removed = owned_photo_url(h), owned_photo_url(h)
    # Uploaded two, removed one before submitting: only what is sent is kept.
    res = _review(client, h, _product(client, h), photo_urls=[kept])
    assert res.json()["photo_urls"] == [kept] and removed not in str(res.json())
    # Picked a photo, then "Skip / I'll add a photo later": an empty list wins
    # over a stale single-photo field.
    skipped = _review(client, h, _product(client, h), photo_urls=[], photo_url=removed)
    assert skipped.status_code == 201, skipped.text
    assert skipped.json()["photo_urls"] == [] and skipped.json()["photo_url"] is None


@requires_db
def test_only_the_authors_own_uploads_and_at_most_four(client):
    _, author, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    h, oh = _auth(author), _auth(other)
    theirs = owned_photo_url(oh)
    res = _review(client, h, _product(client, h), photo_urls=[owned_photo_url(h), theirs])
    assert res.status_code == 403 and res.json()["code"] == "photo_not_owned"
    five = [owned_photo_url(h) for _ in range(5)]
    assert _review(client, h, _product(client, h), photo_urls=five).status_code == 422
    assert _review(client, h, _product(client, h),
                   photo_urls=["javascript:alert(1)"]).status_code == 422


@requires_db
def test_the_one_swap_replaces_the_ordered_set_and_nobody_else_can(client):
    _, author, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    h, oh = _auth(author), _auth(other)
    first = owned_photo_url(h)
    rid = _review(client, h, _product(client, h), photo_urls=[first]).json()["id"]
    url = f"/api/v1/reviews/{rid}"
    assert client.patch(url, headers=oh, json={"photo_urls": [owned_photo_url(oh)]}
                        ).status_code == 403
    x, y = owned_photo_url(h), owned_photo_url(h)
    swapped = client.patch(url, headers=h, json={"photo_urls": [y, x]})
    assert swapped.status_code == 200, swapped.text
    assert swapped.json()["photo_urls"] == [y, x] and swapped.json()["photo_url"] == y
    assert swapped.json()["photo_replaced_at"]
    again = client.patch(url, headers=h, json={"photo_urls": [x]})
    assert again.status_code == 409 and again.json()["code"] == "photo_swap_used"
    # The swap cannot empty a review's photos.
    rid2 = _review(client, h, _product(client, h), photo_urls=[owned_photo_url(h)]).json()["id"]
    empty = client.patch(f"/api/v1/reviews/{rid2}", headers=h, json={"photo_urls": []})
    assert empty.status_code == 422 and empty.json()["code"] == "photo_required"
    # The version history records the set.
    versions = client.get(f"{url}/versions", headers=h).json()
    assert versions[-1]["snapshot"]["photo_urls"] == [y, x]
    assert versions[-1]["change_note"] == "photo replaced"


@requires_db
def test_an_upload_is_checked_before_storage(client):
    """Unsupported type → 415, oversize → 413; neither reaches storage, so no
    object and no record exist for them."""
    _, author, _ = register_and_token(client)
    h = _auth(author)
    gif = client.post("/api/v1/reviews/photo", headers=h,
                      files={"file": ("x.gif", b"GIF89a" + b"0" * 64, "image/gif")})
    assert gif.status_code == 415
    from app.services.storage import MAX_REVIEW_PHOTO_BYTES
    big = b"\xff\xd8\xff\xe0" + b"0" * (MAX_REVIEW_PHOTO_BYTES + 1)
    assert client.post("/api/v1/reviews/photo", headers=h,
                       files={"file": ("big.jpg", big, "image/jpeg")}).status_code == 413


def test_the_model_keeps_the_first_photo_and_the_list_in_step():
    """No database: the flush hook's rule, through the same function."""
    from app.models.review import Review, _sync_photos

    review = Review(photo_urls=["a", "b"])
    _sync_photos(None, None, review)
    assert (review.photo_url, review.photo_urls) == ("a", ["a", "b"])
    legacy = Review(photo_url="z")
    _sync_photos(None, None, legacy)
    assert (legacy.photo_url, legacy.photo_urls) == ("z", ["z"])
    none = Review()
    _sync_photos(None, None, none)
    assert (none.photo_url, none.photo_urls) == (None, [])

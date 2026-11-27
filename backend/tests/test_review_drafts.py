"""Review drafts follow the account, not the device (QA-003).

The tester saved drafts on desktop and found none on mobile: the composer kept
them only in the browser's localStorage. A draft now lives with the account too.
These pin what that must mean: another device sees it, the newer save wins, the
composer's cap holds, and a draft is never anyone else's to read or discard.
"""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _draft(title: str) -> dict:
    return {"step": 2, "title": title, "discussion": "Quiet on low.", "product": None}


@requires_db
def test_a_draft_saved_on_one_device_is_listed_on_another(client):
    """Two logins of one account are two devices: same list, same content."""
    _, token, _ = register_and_token(client)
    slot = str(uuid.uuid4())
    put = client.put(f"/api/v1/review-drafts/{slot}", headers=_h(token),
                     json={"draft": _draft("Tefal first try"), "saved_at": 1_000})
    assert put.status_code == 200, put.text

    body = client.get("/api/v1/review-drafts", headers=_h(token)).json()

    assert [d["slot"] for d in body] == [slot]
    assert body[0]["draft"]["title"] == "Tefal first try"
    assert body[0]["saved_at"] == 1_000


@requires_db
def test_two_products_keep_two_drafts_newest_first(client):
    """The original QA-003 report: a second draft must not replace the first."""
    _, token, _ = register_and_token(client)
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    client.put(f"/api/v1/review-drafts/{first}", headers=_h(token),
               json={"draft": _draft("Tefal pan"), "saved_at": 1_000})
    client.put(f"/api/v1/review-drafts/{second}", headers=_h(token),
               json={"draft": _draft("Tefal kettle"), "saved_at": 2_000})

    body = client.get("/api/v1/review-drafts", headers=_h(token)).json()

    assert [d["slot"] for d in body] == [second, first]


@requires_db
def test_an_older_save_never_replaces_newer_work(client):
    """A phone that was offline must not overwrite what the laptop saved since."""
    _, token, _ = register_and_token(client)
    slot = str(uuid.uuid4())
    client.put(f"/api/v1/review-drafts/{slot}", headers=_h(token),
               json={"draft": _draft("newer"), "saved_at": 5_000})
    late = client.put(f"/api/v1/review-drafts/{slot}", headers=_h(token),
                      json={"draft": _draft("older"), "saved_at": 4_000})

    assert late.status_code == 200
    assert late.json()["draft"]["title"] == "newer"
    body = client.get("/api/v1/review-drafts", headers=_h(token)).json()
    assert body[0]["draft"]["title"] == "newer"


@requires_db
def test_the_unpicked_slot_is_accepted_and_arbitrary_slots_are_not(client):
    _, token, _ = register_and_token(client)
    ok = client.put("/api/v1/review-drafts/__no-product__", headers=_h(token),
                    json={"draft": _draft("before picking"), "saved_at": 1})
    bad = client.put("/api/v1/review-drafts/..%2Fetc", headers=_h(token),
                     json={"draft": _draft("x"), "saved_at": 1})

    assert ok.status_code == 200
    assert bad.status_code in (404, 422)


@requires_db
def test_the_account_keeps_the_composers_ten_newest(client):
    _, token, _ = register_and_token(client)
    slots = [str(uuid.uuid4()) for _ in range(12)]
    for i, slot in enumerate(slots):
        client.put(f"/api/v1/review-drafts/{slot}", headers=_h(token),
                   json={"draft": _draft(f"d{i}"), "saved_at": 1_000 + i})

    kept = [d["slot"] for d in client.get("/api/v1/review-drafts", headers=_h(token)).json()]

    assert kept == list(reversed(slots))[:10]


@requires_db
def test_an_oversized_draft_is_refused(client):
    _, token, _ = register_and_token(client)
    huge = {"discussion": "x" * (70 * 1024)}
    r = client.put(f"/api/v1/review-drafts/{uuid.uuid4()}", headers=_h(token),
                   json={"draft": huge, "saved_at": 1})
    assert r.status_code == 413


@requires_db
def test_one_account_can_neither_read_nor_discard_anothers_draft(client):
    """No cross-user draft access, by listing or by guessing a slot."""
    _, alice, _ = register_and_token(client)
    _, bob, _ = register_and_token(client)
    slot = str(uuid.uuid4())
    client.put(f"/api/v1/review-drafts/{slot}", headers=_h(alice),
               json={"draft": _draft("Alice's secret"), "saved_at": 1})

    assert client.get("/api/v1/review-drafts", headers=_h(bob)).json() == []
    assert client.delete(f"/api/v1/review-drafts/{slot}", headers=_h(bob)).status_code == 404
    # Bob writing the same slot makes Bob's own row; Alice's is untouched.
    client.put(f"/api/v1/review-drafts/{slot}", headers=_h(bob),
               json={"draft": _draft("Bob's"), "saved_at": 9})
    alice_list = client.get("/api/v1/review-drafts", headers=_h(alice)).json()
    assert alice_list[0]["draft"]["title"] == "Alice's secret"


@requires_db
def test_drafts_need_a_signed_in_caller(client):
    assert client.get("/api/v1/review-drafts").status_code == 401
    assert client.put(f"/api/v1/review-drafts/{uuid.uuid4()}",
                      json={"draft": {}, "saved_at": 1}).status_code == 401


@requires_db
def test_discarding_a_draft_removes_it_everywhere(client):
    _, token, _ = register_and_token(client)
    slot = str(uuid.uuid4())
    client.put(f"/api/v1/review-drafts/{slot}", headers=_h(token),
               json={"draft": _draft("to discard"), "saved_at": 1})

    assert client.delete(f"/api/v1/review-drafts/{slot}", headers=_h(token)).status_code == 204
    assert client.get("/api/v1/review-drafts", headers=_h(token)).json() == []


# --- Publishing consumes the draft (owner bug report, 2026-10-03) -----------
#
# A published review's draft stayed in the list: the reviewer could reopen and
# edit it, and publishing it again was (correctly) refused as already posted.
# The server now ends the draft with the publish, and refuses the late copies
# that used to bring it back.

def _product(client, headers: dict) -> str:
    resp = client.post("/api/v1/products", headers=headers,
                       json={"name": f"DraftWidget {uuid.uuid4().hex[:8]}",
                             "category": "electronics"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _publish(client, headers: dict, product: str):
    from tests.conftest import owned_photo_url
    return client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product, "title": "Held up well",
        "discussion": "Weeks of use and it has held up well.",
        "verdict": "yes_absolutely", "star_rating": 4,
        "photo_url": owned_photo_url(headers)})


@requires_db
def test_publishing_removes_the_draft_and_a_second_publish_is_still_refused(client):
    """draft -> publish -> no active draft, the review exists, no duplicate."""
    _, token, _ = register_and_token(client)
    headers = _h(token)
    product = _product(client, headers)
    other = str(uuid.uuid4())
    client.put(f"/api/v1/review-drafts/{product}", headers=headers,
               json={"draft": _draft("about to publish"), "saved_at": 1_000})
    client.put(f"/api/v1/review-drafts/{other}", headers=headers,
               json={"draft": _draft("another product"), "saved_at": 900})

    published = _publish(client, headers, product)
    assert published.status_code == 201, published.text

    slots = [d["slot"] for d in client.get("/api/v1/review-drafts", headers=headers).json()]
    assert slots == [other], "the published draft is still offered (or the other one went)"
    mine = client.get("/api/v1/reviews", headers=headers,
                      params={"product_id": product, "limit": 50}).json()
    assert [r["id"] for r in mine] == [published.json()["id"]]
    again = _publish(client, headers, product)
    assert again.status_code == 409, again.text


@requires_db
def test_a_late_copy_of_the_published_draft_is_refused_not_stored(client):
    """The composer's debounced autosave, or another device's local copy,
    arriving after the publish must not bring the draft back."""
    import time

    _, token, _ = register_and_token(client)
    headers = _h(token)
    product = _product(client, headers)
    before_publish = int(time.time() * 1000) - 500
    assert _publish(client, headers, product).status_code == 201

    late = client.put(f"/api/v1/review-drafts/{product}", headers=headers,
                      json={"draft": _draft("stale copy"), "saved_at": before_publish})

    assert late.status_code == 409, late.text
    assert late.json()["code"] == "draft_published"
    assert late.json()["thread_id"]
    assert client.get("/api/v1/review-drafts", headers=headers).json() == []


@requires_db
def test_a_draft_left_over_from_before_the_publish_is_not_listed(client):
    """A row written before this fix (or by any path that skipped the publish's
    cleanup) is hidden by the server, not just by the composer."""
    from sqlalchemy import update

    from app.db.session import SessionLocal
    from app.models.review_draft import ReviewDraft

    _, token, _ = register_and_token(client)
    headers = _h(token)
    product = _product(client, headers)
    assert _publish(client, headers, product).status_code == 201
    # Re-create the stale row directly, as the old code could leave it.
    client.put(f"/api/v1/review-drafts/{product}", headers=headers,
               json={"draft": _draft("future"), "saved_at": 9_999_999_999_999})
    with SessionLocal() as db:
        db.execute(update(ReviewDraft).where(ReviewDraft.slot == product)
                   .values(saved_at_ms=1_000))
        db.commit()

    assert client.get("/api/v1/review-drafts", headers=headers).json() == []


@requires_db
def test_an_update_draft_written_after_the_publish_is_a_live_draft(client):
    """Work saved after the newest entry (an update for the thread) still counts."""
    import time

    _, token, _ = register_and_token(client)
    headers = _h(token)
    product = _product(client, headers)
    assert _publish(client, headers, product).status_code == 201
    later = int(time.time() * 1000) + 60_000

    put = client.put(f"/api/v1/review-drafts/{product}", headers=headers,
                     json={"draft": _draft("what changed since"), "saved_at": later})

    assert put.status_code == 200, put.text
    assert [d["slot"] for d in client.get("/api/v1/review-drafts", headers=headers).json()] \
        == [product]


@requires_db
def test_a_failed_publish_keeps_the_draft(client):
    _, token, _ = register_and_token(client)
    headers = _h(token)
    product = _product(client, headers)
    client.put(f"/api/v1/review-drafts/{product}", headers=headers,
               json={"draft": _draft("keep me"), "saved_at": 1_000})

    bad = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product, "title": "x", "discussion": "", "verdict": "yes_absolutely",
        "star_rating": 9})

    assert bad.status_code == 422
    assert [d["slot"] for d in client.get("/api/v1/review-drafts", headers=headers).json()] \
        == [product]

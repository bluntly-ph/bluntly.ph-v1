"""Round 3 catalogue and lifecycle on a real database (QA-054, 071-075).

* every review of a request's canonical product answers it, its asker is told
  and linked to the request's own page, and only the asker's Best Answer takes
  it off the board, never deleting it (QA-073; QA-074 superseded by the
  2026-09-29 decision); never a similar-named product;
* a product keeps its category through submission, duplicate detection,
  canonicalisation and attachment, and its review stays browsable under it
  (QA-071);
* a pasted link is never a product's name; the name in the link is offered,
  nothing is fetched (QA-072);
* a malformed DTI/SEC number is refused by the server too (QA-075);
* the author of a taken-down review is shown why (QA-054).
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models.review import Review
from app.services import request_service
from tests.conftest import owned_photo_url, register_and_token, requires_db

pytestmark = requires_db

DETAILS = ("I want an honest look at battery life and build quality after at least "
           "two weeks of daily use, please.")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _person(client, role: str = "user") -> tuple[str, dict]:
    uid, token, _ = register_and_token(client, role)
    return uid, _auth(token)


def _product(client, headers, name: str, *, url: str | None = None,
             category: str | None = "electronics-tech") -> dict:
    res = client.post("/api/v1/products", headers=headers,
                      json={"name": name, "category": category, "source_url": url})
    assert res.status_code in (200, 201), res.text
    return res.json()


def _review(client, headers, product_id: str, title: str = "Solid") -> str:
    res = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product_id, "title": title,
        "discussion": "Three weeks of daily use; it held up.",
        "verdict": "yes_absolutely", "star_rating": 4, "photo_url": owned_photo_url(headers)})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _request(client, headers, *, product_id: str | None = None,
             source_url: str | None = None) -> dict:
    res = client.post("/api/v1/requests", headers=headers, json={
        "title": "Please review this", "details": DETAILS,
        "product_id": product_id, "source_url": source_url})
    assert res.status_code == 201, res.text
    return res.json()


def _get_request(client, request_id: str) -> dict:
    res = client.get(f"/api/v1/requests/{request_id}")
    assert res.status_code == 200, res.text
    return res.json()


def _notes(client, headers, kind: str) -> list[dict]:
    return [n for n in client.get("/api/v1/notifications?limit=100", headers=headers).json()
            if n["kind"] == kind]


def _me(client, headers) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["id"]


def _answers(client, request_id: str) -> list[dict]:
    return client.get(f"/api/v1/requests/{request_id}/answers").json()


# --- QA-073 / the Bounty Board model agreed 2026-09-29 ----------------------------
# QA-074 closed a request at its first review, so one person could answer and
# the asker chose nothing. The team's final model (dev/QA sync, ~41:30): every
# review of the product answers, the request stays on the board, and the ASKER
# picks the Best Answer; then it leaves the board, neither deleted nor archived.

def test_every_review_of_the_product_answers_and_the_request_stays_open(client):
    tag = uuid.uuid4().hex[:8]
    _, maker = _person(client)
    product = _product(client, maker, f"Anker Q20i {tag}")
    _, r1 = _person(client)
    _, r2 = _person(client)
    _, fan = _person(client)
    first = _request(client, r1, product_id=product["id"])
    second = _request(client, r2, product_id=product["id"])
    assert client.post(f"/api/v1/requests/{first['id']}/upvote", headers=fan).status_code == 200

    _, writer = _person(client)
    rid = _review(client, writer, product["id"])
    for req in (first, second):
        row = _get_request(client, req["id"])
        assert row["status"] == "open" and row["fulfilled_by_review_id"] is None
        assert row["answer_count"] == 1
    for headers, req in ((r1, first), (r2, second)):
        [note] = _notes(client, headers, "request_answered")
        assert note["title"] == "Someone answered your request"
        # The notice opens the request itself, not a board it may have left.
        assert note["link"] == f"/requests/{req['id']}"
    [waiting] = _notes(client, fan, "request_fulfilled")
    assert waiting["title"] == "A review you were waiting for is up"
    assert waiting["link"] == f"/requests/{first['id']}"
    assert _notes(client, writer, "request_answered") == []

    # A retry announces nothing twice.
    db = SessionLocal()
    try:
        request_service.announce_answer(db, db.get(Review, uuid.UUID(rid)))
        db.commit()
    finally:
        db.close()
    assert len(_notes(client, r1, "request_answered")) == 1

    # Many people may answer: a second review is a second answer, the asker's
    # notice groups, and the up-voter is not told again.
    _, other = _person(client)
    rid2 = _review(client, other, product["id"], title="Another take")
    assert _get_request(client, first["id"])["answer_count"] == 2
    assert [a["review_id"] for a in _answers(client, first["id"])] == [rid, rid2]
    [grouped] = _notes(client, r1, "request_answered")
    assert grouped["title"] == "2 people answered your request"
    assert len(_notes(client, fan, "request_fulfilled")) == 1
    assert first["id"] in [r["id"] for r in client.get(
        "/api/v1/requests?status=open&limit=100").json()]


def test_only_the_asker_picks_the_best_answer_and_the_request_leaves_the_board(client):
    tag = uuid.uuid4().hex[:8]
    _, maker = _person(client)
    product = _product(client, maker, f"Tefal Wok {tag}")
    _, asker = _person(client)
    req = _request(client, asker, product_id=product["id"])
    _, a1 = _person(client)
    _, a2 = _person(client)
    first = _review(client, a1, product["id"])
    second = _review(client, a2, product["id"], title="Durable enough")

    # Nobody else picks: not the answer's author, not a bystander.
    for headers in (a2, maker):
        res = client.post(f"/api/v1/requests/{req['id']}/best-answer", headers=headers,
                          json={"review_id": second})
        assert res.status_code == 403 and res.json()["code"] == "not_request_owner"
    # Only a real answer can be picked.
    elsewhere = _review(client, a1, _product(client, maker, f"Other {tag}")["id"])
    res = client.post(f"/api/v1/requests/{req['id']}/best-answer", headers=asker,
                      json={"review_id": elsewhere})
    assert res.status_code == 409 and res.json()["code"] == "not_an_answer"

    res = client.post(f"/api/v1/requests/{req['id']}/best-answer", headers=asker,
                      json={"review_id": second})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "fulfilled" and res.json()["fulfilled_by_review_id"] == second
    # Off the board...
    assert req["id"] not in [r["id"] for r in client.get(
        "/api/v1/requests?status=open&limit=100").json()]
    # ...and not deleted or archived: its page, its answers and search keep it.
    assert _get_request(client, req["id"])["status"] == "fulfilled"
    answers = _answers(client, req["id"])
    assert [a["review_id"] for a in answers] == [second, first]
    assert answers[0]["is_best"] is True and answers[1]["is_best"] is False
    assert req["id"] in [r["id"] for r in client.get(
        f"/api/v1/requests?q=Tefal+Wok+{tag}&limit=100").json()]
    [picked] = _notes(client, a2, "request_best_answer")
    assert picked["link"] == f"/requests/{req['id']}"
    # Audited as the asker's pick, like Q&A's Best Answer, and never as a staff
    # approval (the Overview counts `approve` rows as "Approved today").
    from sqlalchemy import select

    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    db = SessionLocal()
    try:
        logs = list(db.scalars(select(ModerationLog).where(
            ModerationLog.target_ref == uuid.UUID(second))))
        assert [log.action for log in logs] == [ModerationAction.best_answer_pick]
        assert str(logs[0].moderator_id) == _me(client, asker)
    finally:
        db.close()
    # Picked once.
    res = client.post(f"/api/v1/requests/{req['id']}/best-answer", headers=asker,
                      json={"review_id": first})
    assert res.status_code == 409 and res.json()["code"] == "request_not_open"


def test_a_request_needs_a_product(client):
    _, asker = _person(client)
    res = client.post("/api/v1/requests", headers=asker, json={
        "title": "Please review this", "details": DETAILS})
    assert res.status_code == 422 and res.json()["code"] == "request_product_required"


def test_a_similar_name_is_not_the_same_product(client):
    tag = uuid.uuid4().hex[:8]
    _, maker = _person(client)
    base = _product(client, maker, f"Jisulife Life 9 {tag}")
    pro = _product(client, maker, f"Jisulife Life 9 Pro {tag}")
    _, asker = _person(client)
    req = _request(client, asker, product_id=base["id"])
    _, writer = _person(client)
    _review(client, writer, pro["id"])
    assert _get_request(client, req["id"])["answer_count"] == 0
    assert _answers(client, req["id"]) == []
    assert _notes(client, asker, "request_answered") == []


def test_a_request_by_listing_link_is_matched_by_that_exact_listing(client):
    tag = uuid.uuid4().hex[:8]
    url = f"https://shopee.ph/Fan-{tag}-i.41.{int(tag, 16)}"
    _, maker = _person(client)
    product = _product(client, maker, f"Fan {tag}", url=url)
    _, asker = _person(client)
    # The same listing with tracking parameters pins the request to the product.
    req = _request(client, asker, source_url=url + "?sp_atk=tracking")
    assert req["product_id"] == product["id"]
    # A listing the catalogue does not know names no product, so it is refused.
    res = client.post("/api/v1/requests", headers=asker, json={
        "title": "Please review this", "details": DETAILS,
        "source_url": f"https://shopee.ph/Fan-{tag}-i.9.9"})
    assert res.status_code == 422 and res.json()["code"] == "request_product_required"
    _, writer = _person(client)
    rid = _review(client, writer, product["id"])
    assert [a["review_id"] for a in _answers(client, req["id"])] == [rid]


def test_a_request_is_not_answered_by_its_own_requester_or_an_older_review(client):
    tag = uuid.uuid4().hex[:8]
    _, maker = _person(client)
    product = _product(client, maker, f"Kettle {tag}")
    _, early = _person(client)
    _review(client, early, product["id"])                  # written before the request
    _, asker = _person(client)
    req = _request(client, asker, product_id=product["id"])
    _review(client, asker, product["id"], title="My own")  # the requester's own review
    row = _get_request(client, req["id"])
    assert row["status"] == "open" and row["answer_count"] == 0


def test_a_request_upvote_tells_the_requester_once(client):
    _, asker = _person(client)
    product = _product(client, asker, f"Blender {uuid.uuid4().hex[:8]}")
    req = _request(client, asker, product_id=product["id"])
    _, fan = _person(client)
    client.post(f"/api/v1/requests/{req['id']}/upvote", headers=fan)
    client.delete(f"/api/v1/requests/{req['id']}/upvote", headers=fan)
    client.post(f"/api/v1/requests/{req['id']}/upvote", headers=fan)
    [note] = _notes(client, asker, "request_upvoted")
    assert note["link"] == f"/requests/{req['id']}" and note["group_count"] == 1
    # Another request's up-vote is its own notice, never merged into this one.
    other = _request(client, asker, product_id=product["id"])
    client.post(f"/api/v1/requests/{other['id']}/upvote", headers=fan)
    notes = _notes(client, asker, "request_upvoted")
    assert len(notes) == 2 and all(n["group_count"] == 1 for n in notes)


# --- QA-071 --------------------------------------------------------------------

def test_the_category_survives_submit_attach_and_browse(client):
    tag = uuid.uuid4().hex[:8]
    _, mh = _person(client, "administrator")
    canonical = client.post("/api/v1/products", headers=mh,
                            json={"name": f"Canon Cam {tag}"}).json()     # no category yet
    _, reviewer = _person(client)
    sub = _product(client, reviewer, f"canon cam listing {tag}",
                   url=f"https://shopee.ph/Canon-Cam-{tag}-i.1.{int(tag, 16)}",
                   category="electronics-tech")
    assert sub["status"] == "pending" and sub["category"] == "electronics-tech"
    rid = _review(client, reviewer, sub["id"], title=f"Cam {tag}")

    attached = client.post(f"/api/v1/products/{sub['id']}/attach", headers=mh,
                           json={"target_product_id": canonical["id"]})
    assert attached.status_code == 200, attached.text
    assert attached.json()["category"] == "electronics-tech"

    feed = client.get(f"/api/v1/reviews/feed?category=electronics-tech&q={tag}&limit=50").json()
    ids = [row["review"]["id"] for row in (feed["items"] if isinstance(feed, dict) else feed)]
    assert rid in ids


def test_a_duplicate_submission_fills_a_missing_category_but_never_replaces_one(client):
    tag = uuid.uuid4().hex[:8]
    _, a = _person(client)
    first = _product(client, a, f"Desk Lamp {tag}", category=None)
    again = _product(client, a, f"desk lamp {tag}", category="home-living")
    assert again["id"] == first["id"] and again["category"] == "home-living"
    third = _product(client, a, f"DESK LAMP {tag}", category="office-productivity")
    assert third["category"] == "home-living"


def test_canonicalising_needs_a_category(client):
    tag = uuid.uuid4().hex[:8]
    _, mh = _person(client, "administrator")
    _, a = _person(client)
    bare = _product(client, a, f"Mystery {tag}", category=None)
    refused = client.post(f"/api/v1/products/{bare['id']}/canonicalize", headers=mh,
                          json={"brand": "Mystery", "product_line": tag})
    assert refused.status_code == 422 and refused.json()["code"] == "category_required"
    named = client.post(f"/api/v1/products/{bare['id']}/canonicalize", headers=mh,
                        json={"brand": "Mystery", "product_line": tag, "category": "gaming"})
    assert named.status_code == 200 and named.json()["category"] == "gaming"
    kept = _product(client, a, f"Kept {tag}", category="audio")
    ok = client.post(f"/api/v1/products/{kept['id']}/canonicalize", headers=mh,
                     json={"brand": "Kept", "product_line": tag})
    assert ok.status_code == 200 and ok.json()["category"] == "audio"


# --- QA-072 --------------------------------------------------------------------

def test_a_link_is_never_a_product_name(client):
    _, a = _person(client)
    url = "https://shopee.ph/Anker-Soundcore-Q20i-i.123.456"
    res = client.post("/api/v1/products", headers=a, json={"name": url, "source_url": url})
    assert res.status_code == 422


def test_resolve_link_proposes_the_name_in_the_link_and_finds_the_listing(client):
    tag = uuid.uuid4().hex[:8]
    _, a = _person(client)
    url = f"https://shopee.ph/Soundcore-Q20i-{tag}-i.77.{int(tag, 16)}"
    res = client.get(f"/api/v1/products/resolve-link?url={url}", headers=a)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["proposed_name"] == f"Soundcore Q20i {tag}"
    assert body["marketplace"] == "shopee" and body["existing_product"] is None

    made = _product(client, a, body["proposed_name"], url=url)
    again = client.get(f"/api/v1/products/resolve-link?url={url}?sp_atk=x", headers=a).json()
    assert again["existing_product"]["id"] == made["id"]

    short = client.get("/api/v1/products/resolve-link?url=https://shp.ee/abc123",
                       headers=a).json()
    assert short["proposed_name"] is None
    assert client.get("/api/v1/products/resolve-link?url=javascript:alert(1)",
                      headers=a).status_code == 422
    assert client.get(f"/api/v1/products/resolve-link?url={url}").status_code == 401


# --- QA-075 --------------------------------------------------------------------

def test_the_server_refuses_a_malformed_registration(client):
    _, owner = _person(client)
    seller = client.post("/api/v1/sellers", headers=owner, json={
        "display_name": f"Shop {uuid.uuid4().hex[:6]}", "platform": "shopee"}).json()
    body = {"registration_kind": "dti", "registered_business_name": "Test Trading",
            "marketplace_shop_name": seller["display_name"]}
    for bad in ("1234567", "N/A", "CS201012345"):
        res = client.post(f"/api/v1/sellers/{seller['id']}/claims", headers=owner,
                          json={**body, "registration_number": bad})
        assert res.status_code == 422, bad
    ok = client.post(f"/api/v1/sellers/{seller['id']}/claims", headers=owner,
                     json={**body, "registration_number": "DTI-3145678"})
    assert ok.status_code == 201, ok.text
    assert ok.json()["status"] == "pending"       # a well-formed number verifies nothing


# --- QA-054 --------------------------------------------------------------------

def test_the_author_sees_why_their_review_was_taken_down(client):
    tag = uuid.uuid4().hex[:8]
    _, author = _person(client)
    _, mh = _person(client, "administrator")
    _, reader = _person(client)
    product = _product(client, author, f"Blender {tag}")
    rid = _review(client, author, product["id"])
    assert client.get(f"/api/v1/reviews/{rid}/full",
                      headers=author).json()["author_takedown_reason"] is None
    down = client.post(f"/api/v1/admin/reviews/{rid}/unpublish", headers=mh,
                       json={"reason": "The photo shows a different model."})
    assert down.status_code == 200, down.text
    mine = client.get(f"/api/v1/reviews/{rid}/full", headers=author).json()
    assert mine["author_takedown_reason"] == "The photo shows a different model."
    assert client.get(f"/api/v1/reviews/{rid}/full", headers=reader).status_code == 404
    assert client.get(f"/api/v1/reviews/{rid}/full",
                      headers=mh).json()["author_takedown_reason"] is None
    client.post(f"/api/v1/admin/reviews/{rid}/restore", headers=mh)
    assert client.get(f"/api/v1/reviews/{rid}/full",
                      headers=author).json()["author_takedown_reason"] is None

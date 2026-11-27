"""Request board — free to post, AI validation, the asker's Best Answer (M3 slice 9;
the 2026-09-29 Bounty Board model)."""

from __future__ import annotations

import uuid as _uuid

import pytest

from app.services.ai_critique import heuristic_validate
from tests.conftest import register_and_token, requires_db
from tests.test_votes_api import make_published_review

GOOD_DETAILS = ("I want an honest look at battery life and build quality after "
                "at least two weeks of daily use, please.")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pid(client, headers) -> str:
    """A product to ask about: every request names one (dev/QA sync 2026-09-29)."""
    res = client.post("/api/v1/products", headers=headers,
                      json={"name": f"Asked-{_uuid.uuid4().hex[:8]}", "category": "electronics"})
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _balance(client, headers) -> int:
    return client.get("/api/v1/tokens/balance", headers=headers).json()["token_balance"]


def _fund(client, uid: str, mod_headers: dict, amount: int) -> None:
    """Give a user tokens via the admin grant (the only mint path)."""
    r = client.post(f"/api/v1/admin/users/{uid}/tokens", headers=mod_headers,
                    json={"amount": amount, "note": "test funding"})
    assert r.status_code == 200, r.text


# --- pure heuristic contract (no DB) ---
@pytest.mark.parametrize(("title", "details", "src", "valid"), [
    ("Review this fan", GOOD_DETAILS, None, True),
    ("Review this fan", "too short", None, False),                      # < 30 chars
    ("Same text here padded out to thirty plus", "Same text here padded out to thirty plus",
     None, False),                                                      # title == details
    ("Review this", GOOD_DETAILS + " https://evil.example.com/x", None, False),  # foreign link
    ("Review this", GOOD_DETAILS + " https://shopee.ph/x",
     "https://shopee.ph/item", True),                                   # same host as source_url
])
def test_heuristic_validation_contract(title, details, src, valid):
    ok, reasons = heuristic_validate(title, details, src)
    assert ok is valid
    assert ok or reasons  # a rejection always explains itself


@requires_db
def test_create_and_cancel_cost_nothing(client):
    """Posting is free (migration 0022 retired the bounty).

    The balance assertions are the point: they used to prove the escrow moved,
    and now prove nothing moves at all. A request must not touch the ledger.
    """
    uid, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    h, mh = _auth(token), _auth(mod_token)
    _fund(client, uid, mh, 100)
    before = _balance(client, h)

    r = client.post("/api/v1/requests", headers=h, json={
        "title": "Review this handheld fan", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "open"
    assert body["ai_validation"]["valid"] is True
    assert "bounty" not in body and "effective_reward" not in body
    assert _balance(client, h) == before

    rid = body["id"]
    cancelled = client.delete(f"/api/v1/requests/{rid}", headers=h)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert _balance(client, h) == before

    # Nothing was written to the ledger against this request, in either direction.
    assert [t for t in client.get("/api/v1/tokens/transactions",
                                  headers=h).json() if t["ref_id"] == rid] == []


@requires_db
def test_create_guards(client):
    uid, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    h, mh = _auth(token), _auth(mod_token)

    # AI screening rejects thin details with reasons. This is now the *only*
    # way a request can be refused — affordability is no longer a concept.
    r = client.post("/api/v1/requests", headers=h, json={
        "title": "Review it", "details": "pls"})
    assert r.status_code == 422
    assert r.json()["code"] == "request_invalid"
    assert r.json()["reasons"]

    # A user with no tokens at all can still post, which was the whole of
    # BUG-025 before the currency went away.
    assert _balance(client, h) == 0
    r = client.post("/api/v1/requests", headers=h, json={
        "title": "Review this fan", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)})
    assert r.status_code == 201, r.text

    # Anonymous.
    assert client.post("/api/v1/requests", json={
        "title": "x", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)}).status_code == 401
    _fund(client, uid, mh, 50)  # keep the fixture usable


@requires_db
def test_upvotes_count_once_per_user_and_persist(client):
    """Up-votes are the demand signal now, not a multiplier on a purse."""
    uid, token, _ = register_and_token(client)
    h = _auth(token)
    rid = client.post("/api/v1/requests", headers=h, json={
        "title": "Review this blender", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)}).json()["id"]

    # Self-upvote blocked.
    assert client.post(f"/api/v1/requests/{rid}/upvote",
                       headers=h).json()["code"] == "cannot_upvote_own_request"

    _, v1, _ = register_and_token(client)
    r = client.post(f"/api/v1/requests/{rid}/upvote", headers=_auth(v1))
    assert r.status_code == 200
    assert r.json()["upvote_count"] == 1
    assert r.json()["my_upvote"] is True

    # BUG-026: the voter's own state survives a fresh read, and is not visible
    # to anyone else.
    assert client.get(f"/api/v1/requests/{rid}", headers=_auth(v1)).json()["my_upvote"] is True
    assert client.get(f"/api/v1/requests/{rid}").json()["my_upvote"] is False

    # Same user twice -> 409.
    assert client.post(f"/api/v1/requests/{rid}/upvote",
                       headers=_auth(v1)).status_code == 409
    # Remove own upvote.
    r = client.delete(f"/api/v1/requests/{rid}/upvote", headers=_auth(v1))
    assert r.json()["upvote_count"] == 0 and r.json()["my_upvote"] is False
    assert client.delete(f"/api/v1/requests/{rid}/upvote",
                         headers=_auth(v1)).status_code == 404

    # Many voters simply accumulate — there is no ceiling to hit any more.
    for _ in range(4):
        _, tok, _ = register_and_token(client)
        assert client.post(f"/api/v1/requests/{rid}/upvote",
                           headers=_auth(tok)).status_code == 200
    assert client.get(f"/api/v1/requests/{rid}").json()["upvote_count"] == 4


@requires_db
def test_best_answer_guards(client):
    """Only the asker picks, and only a real answer (dev/QA sync 2026-09-29).

    The retired reviewer self-claim (`/fulfill`) follows the same rule, so the
    person who wrote a review can no longer close someone else's request.
    """
    req_uid, req_token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    rh, mh = _auth(req_token), _auth(mod_token)
    reviewer_uid, rev_token, _ = register_and_token(client)
    vh = _auth(rev_token)

    pid = _pid(client, rh)
    rid = client.post("/api/v1/requests", headers=rh, json={
        "title": "Review this kettle", "details": GOOD_DETAILS,
        "product_id": pid}).json()["id"]
    _, v1, _ = register_and_token(client)
    client.post(f"/api/v1/requests/{rid}/upvote", headers=_auth(v1))

    # A taken-down review is not an answer.
    draft = client.post("/api/v1/reviews", headers=vh, json={
        "product_id": pid, "title": "Draft", "discussion": "Not yet published.",
        "verdict": "it_depends", "star_rating": 3}).json()["id"]
    assert client.post(f"/api/v1/admin/reviews/{draft}/unpublish", headers=mh,
                       json={"reason": "Test take-down."}).status_code == 200
    r = client.post(f"/api/v1/requests/{rid}/best-answer", headers=rh,
                    json={"review_id": draft})
    assert r.status_code == 409 and r.json()["code"] == "review_not_published"

    # The reviewer cannot claim it, through either route.
    other_uid, other_token, _ = register_and_token(client)
    answer = client.post("/api/v1/reviews", headers=_auth(other_token), json={
        "product_id": pid, "title": "Kettle, three weeks in", "discussion": "Boils fast.",
        "verdict": "yes_absolutely", "star_rating": 4}).json()["id"]
    for route in ("fulfill", "best-answer"):
        r = client.post(f"/api/v1/requests/{rid}/{route}", headers=_auth(other_token),
                        json={"review_id": answer})
        assert r.status_code == 403 and r.json()["code"] == "not_request_owner"

    # Happy path: the asker picks.
    before = _balance(client, _auth(other_token))
    r = client.post(f"/api/v1/requests/{rid}/fulfill", headers=rh, json={"review_id": answer})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "fulfilled"
    assert r.json()["fulfilled_by_review_id"] == answer
    # Picking pays nothing: the answer's author earns from the review itself
    # through the ordinary revenue share, exactly as they would unprompted.
    assert _balance(client, _auth(other_token)) == before

    # Picked once only, and a fulfilled request can no longer be cancelled.
    assert client.post(f"/api/v1/requests/{rid}/best-answer", headers=rh,
                       json={"review_id": answer}).status_code == 409
    assert client.delete(f"/api/v1/requests/{rid}", headers=rh).status_code == 409


@requires_db
def test_a_review_of_another_product_is_not_an_answer(client):
    uid, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    h, mh = _auth(token), _auth(mod_token)
    reviewer_uid, rev_token, _ = register_and_token(client)
    vh = _auth(rev_token)

    wanted = _pid(client, h)
    rid = client.post("/api/v1/requests", headers=h, json={
        "title": "Review this exact product", "details": GOOD_DETAILS,
        "product_id": wanted}).json()["id"]
    # Published review, but for a DIFFERENT product.
    other, _ = make_published_review(client, vh, mh, name=f"Wrong-{_uuid.uuid4().hex[:5]}")
    r = client.post(f"/api/v1/requests/{rid}/best-answer", headers=h, json={"review_id": other})
    assert r.status_code == 409 and r.json()["code"] == "not_an_answer"


@requires_db
def test_moderator_remove_and_rbac(client):
    uid, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    h, mh = _auth(token), _auth(mod_token)
    rid = client.post("/api/v1/requests", headers=h, json={
        "title": "Review this lamp", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)}).json()["id"]

    # Non-moderator cannot remove.
    assert client.post(f"/api/v1/admin/requests/{rid}/remove", headers=h,
                       json={"reason": "nope"}).status_code == 403
    r = client.post(f"/api/v1/admin/requests/{rid}/remove", headers=mh,
                    json={"reason": "spam"})
    assert r.status_code == 200 and r.json()["status"] == "removed"
    # Removed requests disappear from the board and 404 by id.
    assert client.get(f"/api/v1/requests/{rid}").status_code == 404
    assert rid not in [x["id"] for x in client.get("/api/v1/requests?limit=100").json()]


@requires_db
def test_expiry_closes_open_requests(client):
    from datetime import UTC, datetime, timedelta

    from app.db.session import SessionLocal
    from app.models.request_board import ReviewRequest
    from app.services.request_service import expire_open_requests

    uid, token, _ = register_and_token(client)
    h = _auth(token)
    rid = client.post("/api/v1/requests", headers=h, json={
        "title": "Review this mug", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)}).json()["id"]

    db = SessionLocal()
    try:
        db.get(ReviewRequest, _uuid.UUID(rid)).expires_at = datetime.now(UTC) - timedelta(days=1)
        db.commit()
        assert expire_open_requests(db) >= 1
    finally:
        db.close()

    assert client.get(f"/api/v1/requests/{rid}").json()["status"] == "expired"


@requires_db
def test_list_sorting_by_demand(client):
    """sort=demand puts the most-wanted request first.

    This replaced sort=reward, which ordered by whoever escrowed the largest
    bounty — a measure of one person's balance rather than of how many people
    wanted the answer.
    """
    uid, token, _ = register_and_token(client)
    h = _auth(token)
    quiet = client.post("/api/v1/requests", headers=h, json={
        "title": "Quietly wanted request", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)}).json()["id"]
    popular = client.post("/api/v1/requests", headers=h, json={
        "title": "Widely wanted request", "details": GOOD_DETAILS,
        "product_id": _pid(client, h)}).json()["id"]

    for _ in range(3):
        _, voter, _ = register_and_token(client)
        assert client.post(f"/api/v1/requests/{popular}/upvote",
                           headers=_auth(voter)).status_code == 200

    rows = client.get("/api/v1/requests?sort=demand&limit=100").json()

    # The contract is that the page comes back most-wanted first, and THAT is
    # what gets asserted. Asking whether one specific brand-new request sits
    # above another only works if both are on the page, and the board is a
    # shared database that accumulates across runs: once more than `limit`
    # requests carry an up-vote, a zero-vote request cannot be in the first
    # hundred at all. That is correct sorting, not a sorting failure, and it
    # is what made this test start raising "not in list" — 106 of the 270
    # requests in the test project already had votes.
    counts = [r["upvote_count"] for r in rows]
    assert counts == sorted(counts, reverse=True), (
        "sort=demand must return requests in non-increasing demand order")

    # The up-votes landed where they were aimed...
    assert client.get(f"/api/v1/requests/{popular}").json()["upvote_count"] == 3
    assert client.get(f"/api/v1/requests/{quiet}").json()["upvote_count"] == 0

    # ...and wherever both are visible together, the wanted one leads.
    ids = [r["id"] for r in rows]
    if popular in ids and quiet in ids:
        assert ids.index(popular) < ids.index(quiet)

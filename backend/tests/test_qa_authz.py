"""Ownership sweep (full-system QA, 2026-09-24).

Every mutation that takes another account's resource id, attempted by the wrong
account. Each case asserts the refusal AND that the owner's data is unchanged —
a 403 that still wrote something is not a refusal. Also: unauthenticated calls,
and a moderator where the rule allows one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from tests.conftest import claim_body, register_and_token, register_commenter, requires_db
from tests.test_business_rules_api import _auth, _claimed_seller, _product, _review

REFUSED = (403, 404)


@requires_db
def test_review_owner_operations_refuse_everyone_else(client):
    owner_id, owner, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    oh, xh = _auth(owner), _auth(other)
    pid = _product(client, oh)
    # With proof of purchase attached, so the receipt check below is about
    # authorization itself — not merely "there is no receipt here".
    rid = client.post("/api/v1/reviews", headers=oh, json={
        "product_id": pid, "title": "Solid", "discussion": "Weeks of daily use.",
        "verdict": "yes_absolutely", "star_rating": 4,
        "receipt_key": f"{owner_id}/{uuid.uuid4().hex}.jpg"}).json()["id"]

    assert client.delete(f"/api/v1/reviews/{rid}?confirm=delete-thread",
                         headers=xh).status_code in REFUSED
    assert client.patch(f"/api/v1/reviews/{rid}", headers=xh,
                        json={"title": "hijacked"}).status_code in REFUSED
    assert client.post(f"/api/v1/reviews/{rid}/updates", headers=xh, json={
        "title": "Not mine", "discussion": "An update to someone else's review.",
        "verdict": "hard_pass", "star_rating": 1}).status_code in REFUSED
    assert client.post(f"/api/v1/reviews/{rid}/critique", headers=xh).status_code in REFUSED
    # The receipt: refused as the authorization failure specifically (the same
    # 404 a missing review gets, so its existence is not confirmed); a
    # moderator gets past authorization; nobody anonymous gets anywhere.
    refused = client.get(f"/api/v1/reviews/{rid}/receipt", headers=xh)
    assert refused.status_code == 404 and refused.json()["code"] == "review_not_found"
    assert client.get(f"/api/v1/reviews/{rid}/receipt").status_code == 401
    as_mod = client.get(f"/api/v1/reviews/{rid}/receipt", headers=_auth(mod))
    assert as_mod.status_code == 200 or as_mod.json().get("code") == "receipt_not_found"
    # No credential at all.
    assert client.delete(f"/api/v1/reviews/{rid}?confirm=delete-thread").status_code == 401
    assert client.post(f"/api/v1/reviews/{rid}/updates", json={}).status_code in (401, 422)

    after = client.get(f"/api/v1/reviews/{rid}")
    assert after.status_code == 200 and after.json()["title"] == "Solid"
    thread = client.get(f"/api/v1/reviews/{rid}/thread").json()
    assert [e["id"] for e in thread["entries"]] == [rid]


@requires_db
def test_comment_and_notification_ownership(client):
    from app.db.session import SessionLocal
    from app.models.notification import Notification

    _, author, _ = register_and_token(client)
    owner_id, owner, _ = register_commenter(client)
    _, other, _ = register_commenter(client)
    rid = _review(client, _auth(author), _product(client, _auth(author)))["id"]
    cid = client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(owner),
                      json={"body": "My own comment."}).json()["id"]

    assert client.delete(f"/api/v1/comments/{cid}", headers=_auth(other)).status_code in REFUSED
    listed = client.get(f"/api/v1/reviews/{rid}/comments").json()
    assert any(c["id"] == cid and not c.get("is_removed") for c in listed)

    db = SessionLocal()
    try:
        note = db.scalars(select(Notification).where(
            Notification.user_id == uuid.UUID(owner_id)).limit(1)).first()
        if note is None:
            note = Notification(user_id=uuid.UUID(owner_id), kind="test", title="Yours")
            db.add(note)
            db.commit()
            db.refresh(note)
        note_id, was_read = note.id, note.read_at
    finally:
        db.close()
    # Another account's notification is "not found", not "forbidden" — its
    # existence is not confirmed to someone it does not belong to.
    assert client.post(f"/api/v1/notifications/{note_id}/read",
                       headers=_auth(other)).status_code == 404
    db = SessionLocal()
    try:
        assert db.get(Notification, note_id).read_at == was_read
    finally:
        db.close()


@requires_db
def test_only_the_asker_picks_the_best_answer(client):
    _, asker, _ = register_and_token(client)
    _, answerer, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    qid = client.post("/api/v1/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "Does it run quietly at night?"}).json()["id"]
    aid = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(answerer),
                      json={"body": "Yes, on the lowest setting.", "rating": 4}).json()["id"]

    assert client.post(f"/api/v1/questions/{qid}/answers/{aid}/best",
                       headers=_auth(other)).status_code in REFUSED
    assert client.post(f"/api/v1/questions/{qid}/answers/{aid}/best",
                       headers=_auth(answerer)).status_code in REFUSED
    assert client.get(f"/api/v1/questions/{qid}").json()["best_answer_id"] is None
    assert client.post(f"/api/v1/questions/{qid}/answers/{aid}/best",
                       headers=_auth(asker)).status_code == 200


@requires_db
def test_request_board_owner_operations(client):
    _, owner, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    pid = _product(client, _auth(owner))
    req = client.post("/api/v1/requests", headers=_auth(owner), json={
        "title": "Review this handheld fan", "product_id": pid,
        "details": "Please cover battery life and build quality after two weeks."}).json()
    assert client.delete(f"/api/v1/requests/{req['id']}",
                         headers=_auth(other)).status_code in REFUSED
    assert client.get(f"/api/v1/requests/{req['id']}").json()["status"] == "open"
    # Only the asker picks the Best Answer (2026-09-29): anyone else is refused,
    # through either route, even with a real answer of the right product.
    _, author, _ = register_and_token(client)
    their_rid = _review(client, _auth(author), pid)["id"]
    for route in ("best-answer", "fulfill"):
        assert client.post(f"/api/v1/requests/{req['id']}/{route}", headers=_auth(other),
                           json={"review_id": their_rid}).status_code in REFUSED
        assert client.post(f"/api/v1/requests/{req['id']}/{route}", headers=_auth(author),
                           json={"review_id": their_rid}).status_code in REFUSED
    assert client.get(f"/api/v1/requests/{req['id']}").json()["status"] == "open"


@requires_db
def test_seller_owner_operations_refuse_non_owners(client):
    _, seller, store, mod = _claimed_seller(client)
    _, buyer, _ = register_and_token(client)
    _, stranger, _ = register_and_token(client)
    rated = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 3,
        "packaging_quality": 3, "overall_rating": 3, "would_recommend": True,
        "comment": "Fine.", "order_id": "ORD-777"}).json()
    srid = rated["id"]

    for who in (buyer, stranger):
        assert client.post(f"/api/v1/sellers/reviews/{srid}/response", headers=_auth(who),
                           json={"body": "Not my store."}).status_code in REFUSED
        assert client.post(f"/api/v1/sellers/reviews/{srid}/appeal", headers=_auth(who),
                           json={"reason": "Not my store either."}).status_code in REFUSED
    # The order id never reaches a public read.
    public = client.get(f"/api/v1/sellers/{store['id']}/reviews").text
    assert "ORD-777" not in public

    appeal = client.post(f"/api/v1/sellers/reviews/{srid}/appeal", headers=_auth(seller),
                         json={"reason": "We have no such order."}).json()
    client.post(f"/api/v1/admin/seller-review-appeals/{appeal['id']}/substantiation-request",
                headers=_auth(mod), json={"note": "Please share your order."})
    # Only the reviewer answers, and only the reviewer reads it.
    for who in (seller, stranger):
        assert client.post(f"/api/v1/sellers/appeals/{appeal['id']}/substantiation",
                           headers=_auth(who), json={"response": "x"}).status_code in REFUSED
        assert client.get(f"/api/v1/sellers/appeals/{appeal['id']}",
                          headers=_auth(who)).status_code == 404
    # Admin surfaces stay admin: a claimed seller is not a moderator.
    assert client.get("/api/v1/admin/seller-review-appeals",
                      headers=_auth(seller)).status_code == 403
    assert client.post(f"/api/v1/admin/seller-review-appeals/{appeal['id']}/decision",
                       headers=_auth(seller), json={"decision": "uphold"}).status_code == 403
    assert client.get(f"/api/v1/sellers/{store['id']}/reviews").json()[0]["id"] == srid


@requires_db
def test_money_and_moderation_surfaces_are_scoped(client):
    uid, user, _ = register_and_token(client)
    other_id, other, _ = register_and_token(client)
    # Balances and payouts are the caller's own; there is no id to swap.
    assert client.get("/api/v1/payouts/balance").status_code == 401
    assert client.get("/api/v1/payouts", headers=_auth(user)).json() == []
    for path, method in (("/api/v1/admin/payouts", "get"), ("/api/v1/admin/remittances", "post"),
                         ("/api/v1/admin/reports", "get"), ("/api/v1/admin/seller-claims", "get"),
                         (f"/api/v1/admin/users/{other_id}/investigation", "put")):
        call = getattr(client, method)
        kwargs = {"headers": _auth(user)}
        if method in ("post", "put"):
            kwargs["json"] = {}
        assert call(path, **kwargs).status_code in (403, 422), path
    # A seller claim record is the moderator's to read, not another user's.
    store = client.post("/api/v1/sellers", headers=_auth(user), json={
        "display_name": f"Scoped Store {uuid.uuid4().hex[:6]}", "platform": "lazada"}).json()
    client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(user),
                json=claim_body(shop_name=store["display_name"]))
    assert client.get("/api/v1/admin/seller-claims", headers=_auth(other)).status_code == 403

"""Seller support requests (owner decision 2026-09-28): the lifecycle, the
isolation between stores, and what a seller may never see."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import ModerationAction
from app.models.moderation import ModerationLog
from app.models.notification import Notification
from tests.conftest import claim_body, register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _store(client, mod_h=None):
    uid, owner, _ = register_and_token(client)
    if mod_h is None:
        _, mod, _ = register_and_token(client, role="administrator")
        mod_h = _auth(mod)
    store = client.post("/api/v1/sellers", headers=_auth(owner), json={
        "display_name": f"Support Store {uuid.uuid4().hex[:8]}", "platform": "lazada"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision", headers=mod_h,
                       json={"decision": "approve"}).status_code == 200
    return store["id"], _auth(owner), mod_h, uid


def _body(**kw):
    body = {"category": "fake_review_dispute", "subject": "A review I believe is fake",
            "message": "The order number in this review does not exist in our records."}
    body.update(kw)
    return body


def test_the_full_lifecycle(client):
    store, owner, mod, owner_id = _store(client)
    _, buyer, _ = register_and_token(client)
    review = client.post(f"/api/v1/sellers/{store}/reviews", headers=_auth(buyer), json={
        "accuracy": False, "order_completeness": False, "customer_service": 1,
        "packaging_quality": 1, "overall_rating": 1, "would_recommend": False}).json()

    created = client.post(f"/api/v1/sellers/{store}/support-requests", headers=owner,
                          json=_body(related_seller_review_id=review["id"]))
    assert created.status_code == 201, created.text
    req = created.json()
    assert req["status"] == "open" and req["reference"].startswith("SUP-")
    assert req["related_seller_review_id"] == review["id"]
    assert "internal_note" not in req

    listed = client.get(f"/api/v1/sellers/{store}/support-requests", headers=owner).json()
    assert [r["id"] for r in listed] == [req["id"]]

    queue = client.get("/api/v1/admin/support-requests", headers=mod).json()
    assert req["id"] in [r["id"] for r in queue]
    assigned = client.post(f"/api/v1/admin/support-requests/{req['id']}/assign", headers=mod)
    assert assigned.status_code == 200 and assigned.json()["status"] == "in_review"

    noted = client.post(f"/api/v1/admin/support-requests/{req['id']}/status", headers=mod,
                        json={"status": "in_review", "internal_note": "Check the order DB."})
    assert noted.json()["internal_note"] == "Check the order DB."
    answered = client.post(f"/api/v1/admin/support-requests/{req['id']}/respond", headers=mod,
                           json={"response": "We asked the reviewer to substantiate.",
                                 "status": "resolved"})
    assert answered.status_code == 200
    assert answered.json()["status"] == "resolved" and answered.json()["resolved_at"]

    seen = client.get(f"/api/v1/sellers/{store}/support-requests/{req['id']}",
                      headers=owner).json()
    assert seen["admin_response"] == "We asked the reviewer to substantiate."
    assert seen["status"] == "resolved"
    # The staff-only note never reaches the seller, in any read.
    assert "Check the order DB." not in str(seen) and "internal_note" not in seen
    assert "Check the order DB." not in client.get(
        f"/api/v1/sellers/{store}/support-requests", headers=owner).text

    db = SessionLocal()
    try:
        events = [log.context["event"] for log in db.scalars(
            select(ModerationLog).where(ModerationLog.target_ref == uuid.UUID(req["id"]),
                                        ModerationLog.action == ModerationAction.support_request)
            .order_by(ModerationLog.created_at))]
        assert events == ["created", "assigned", "status", "responded"]
        told = db.scalars(select(Notification.kind).where(
            Notification.user_id == uuid.UUID(owner_id),
            Notification.kind == "support_request")).all()
        assert len(told) >= 2
    finally:
        db.close()


def test_seller_a_never_reaches_seller_b(client):
    store_a, owner_a, mod, _ = _store(client)
    store_b, owner_b, _, _ = _store(client, mod)
    req_b = client.post(f"/api/v1/sellers/{store_b}/support-requests", headers=owner_b,
                        json=_body()).json()

    # B's store path: not A's store.
    for method, url, body in (
            ("get", f"/api/v1/sellers/{store_b}/support-requests", None),
            ("get", f"/api/v1/sellers/{store_b}/support-requests/{req_b['id']}", None),
            ("post", f"/api/v1/sellers/{store_b}/support-requests", _body())):
        r = getattr(client, method)(url, headers=owner_a, **({"json": body} if body else {}))
        assert r.status_code == 403 and r.json()["code"] == "not_store_owner", url
    # B's request through A's own store: simply not there.
    swapped = client.get(f"/api/v1/sellers/{store_a}/support-requests/{req_b['id']}",
                         headers=owner_a)
    assert swapped.status_code == 404
    # A cannot attach B's store review to A's request.
    _, buyer, _ = register_and_token(client)
    review_b = client.post(f"/api/v1/sellers/{store_b}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 5,
        "packaging_quality": 5, "overall_rating": 5, "would_recommend": True}).json()
    stolen = client.post(f"/api/v1/sellers/{store_a}/support-requests", headers=owner_a,
                         json=_body(related_seller_review_id=review_b["id"]))
    assert stolen.status_code == 404
    # And A's list holds none of B's.
    assert client.get(f"/api/v1/sellers/{store_a}/support-requests", headers=owner_a).json() == []


def test_who_may_use_support(client):
    store, owner, _, _ = _store(client)
    url = f"/api/v1/sellers/{store}/support-requests"
    assert client.post(url, json=_body()).status_code == 401
    _, member, _ = register_and_token(client)
    assert client.post(url, headers=_auth(member), json=_body()).status_code == 403
    # A claimant whose claim is still pending is not the owner yet.
    _, claimant, _ = register_and_token(client)
    unclaimed = client.post("/api/v1/sellers", headers=_auth(claimant), json={
        "display_name": f"Pending {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    client.post(f"/api/v1/sellers/{unclaimed['id']}/claims", headers=_auth(claimant),
                json=claim_body("Mine."))
    assert client.post(f"/api/v1/sellers/{unclaimed['id']}/support-requests",
                       headers=_auth(claimant), json=_body()).status_code == 403
    # Members and sellers cannot use the staff queue.
    for h in (_auth(member), owner):
        assert client.get("/api/v1/admin/support-requests", headers=h).status_code == 403
    # No links in the text (Business Rules 1).
    linked = client.post(url, headers=owner, json=_body(message="See https://example.com now"))
    assert linked.status_code == 422


def test_the_queue_keeps_waiting_requests_ahead_of_closed_ones(client):
    store, owner, mod, _ = _store(client)
    first = client.post(f"/api/v1/sellers/{store}/support-requests", headers=owner,
                        json=_body(subject="First one")).json()
    second = client.post(f"/api/v1/sellers/{store}/support-requests", headers=owner,
                         json=_body(subject="Second one")).json()
    # The older one is closed: it must now sort after the newer, waiting one.
    client.post(f"/api/v1/admin/support-requests/{first['id']}/status", headers=mod,
                json={"status": "resolved"})
    ids = [r["id"] for r in client.get("/api/v1/admin/support-requests", headers=mod).json()]
    assert ids.index(second["id"]) < ids.index(first["id"])
    only_open = client.get("/api/v1/admin/support-requests?status=open", headers=mod).json()
    assert second["id"] in [r["id"] for r in only_open]
    assert first["id"] not in [r["id"] for r in only_open]
    # A closed request cannot be taken again.
    again = client.post(f"/api/v1/admin/support-requests/{first['id']}/assign", headers=mod)
    assert again.status_code == 409 and again.json()["code"] == "support_request_closed"

"""Editing a store's response (Figma Confirm/Store/SaveResponse 8202:22699):
the first response's time is kept (the store's reply time reads it), the edit
is marked so buyers see "Edited", and the reviewer is not notified twice."""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth, _claimed_seller

pytestmark = requires_db


def test_an_edit_keeps_the_reply_time_marks_edited_and_does_not_renotify(client):
    _, owner, store, _ = _claimed_seller(client)
    _, buyer, _ = register_and_token(client)
    rated = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 2,
        "packaging_quality": 3, "overall_rating": 2, "would_recommend": False,
        "comment": "Slow to reply to my chat.", "order_id": "ORD-EDIT-1"}).json()
    url = f"/api/v1/sellers/reviews/{rated['id']}/response"

    first = client.post(url, headers=_auth(owner), json={"body": "Sorry, we answer within a day."})
    assert first.status_code == 200, first.text
    at = first.json()["seller_response_at"]
    assert at and first.json()["seller_response_edited_at"] is None

    def notes():
        body = client.get("/api/v1/notifications", headers=_auth(buyer)).json()
        items = body["items"] if isinstance(body, dict) else body
        return [n for n in items if n.get("kind") == "seller_responded"]

    assert len(notes()) == 1
    edit = client.post(url, headers=_auth(owner),
                       json={"body": "Sorry, we now answer chats within 4 hours."})
    assert edit.status_code == 200, edit.text
    assert edit.json()["seller_response"] == "Sorry, we now answer chats within 4 hours."
    assert edit.json()["seller_response_at"] == at
    assert edit.json()["seller_response_edited_at"] is not None
    assert len(notes()) == 1

    shown = client.get(f"/api/v1/sellers/{store['id']}/reviews").json()
    row = next(r for r in shown if r["id"] == rated["id"])
    assert row["seller_response_at"] == at and row["seller_response_edited_at"] is not None

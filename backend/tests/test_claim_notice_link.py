"""MQA-027: "Bluntly replied about your store claim" opens the claim's
conversation, not the store's public page.

A claimant whose claim is still pending has no seller console yet, so the
notice opens their Messages thread; once the claim is approved the same thread
opens in the console's Messages. Opening it marks the reply read.
"""

from __future__ import annotations

import uuid

from tests.conftest import claim_body, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _latest_link(client, headers) -> str:
    items = client.get("/api/v1/notifications", headers=headers).json()
    items = items["items"] if isinstance(items, dict) else items
    return next(n["link"] for n in items if n["kind"] == "case_message")


@requires_db
def test_a_claim_reply_opens_the_claim_thread_then_the_console_thread(client):
    _, owner_token, _ = register_and_token(client)
    _, staff_token, _ = register_and_token(client, role="administrator")
    owner, staff = _auth(owner_token), _auth(staff_token)
    store = client.post("/api/v1/sellers", headers=owner, json={
        "display_name": f"Notice Co {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=owner,
                        json=claim_body(shop_name=store["display_name"])).json()

    sent = client.post(f"/api/v1/cases/claim/{claim['id']}/messages", headers=staff,
                       json={"body": "Please send your DTI certificate."})
    assert sent.status_code == 201, sent.text
    link = _latest_link(client, owner)
    assert link.startswith("/messages/"), link
    conv_id = link.rsplit("/", 1)[1]
    assert client.get("/api/v1/conversations/unread", headers=owner).json()["unread"] >= 1
    opened = client.get(f"/api/v1/conversations/{conv_id}", headers=owner)
    assert opened.status_code == 200
    assert any("DTI certificate" in m["body"] for m in opened.json()["messages"])

    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision", headers=staff,
                       json={"decision": "approve"}).status_code == 200
    client.post(f"/api/v1/cases/claim/{claim['id']}/messages", headers=staff,
                json={"body": "Approved. Welcome aboard."})
    assert _latest_link(client, owner) == f"/seller/{store['id']}/messages?c={conv_id}"

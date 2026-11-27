"""MQA-021/022/023/024/026/029: a request moved to Support stays one thread.

The Inbox's "Move to Queue -> Support" used to close the seller's conversation
and copy it into a ticket: the moderator's reply on the ticket never reached the
seller's Messages thread, the ticket page had no reply box, the two showed
different states, and "In review" never told the seller they had to act.
"""

from __future__ import annotations

import pytest

from tests.conftest import requires_db
from tests.test_conversations import (  # noqa: F401 - outbox is a fixture
    _claimed_store,
    _start,
    outbox,
)

pytestmark = [requires_db, pytest.mark.usefixtures("outbox")]


def _moved(client):
    store, owner, staff = _claimed_store(client)
    started = _start(client, owner, audience="seller", seller_id=store, topic="other",
                     body="Our store link changed last week, can you update it?")
    assert started.status_code == 201, started.text
    conv = started.json()
    moved = client.post(f"/api/v1/admin/inbox/{conv['id']}/move-to-support", headers=staff)
    assert moved.status_code == 200, moved.text
    ref = moved.json()["support_reference"]
    rows = client.get("/api/v1/admin/support-requests?limit=200", headers=staff).json()
    req = next(r for r in rows if r["reference"] == ref)
    return store, owner, staff, conv, req


def _thread(client, owner, conv_id):
    return client.get(f"/api/v1/conversations/{conv_id}", headers=owner).json()


def _notices(client, owner):
    items = client.get("/api/v1/notifications", headers=owner).json()
    return items["items"] if isinstance(items, dict) else items


def test_the_ticket_reply_lands_in_the_sellers_thread_and_asks_them_to_act(client):
    store, owner, staff, conv, req = _moved(client)
    assert _thread(client, owner, conv["id"])["status"] == "open", "still in the Open list"

    res = client.post(f"/api/v1/admin/support-requests/{req['id']}/respond", headers=staff,
                      json={"response": "Please send a screenshot of the new link.",
                            "action": "ask"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "waiting_for_seller"

    thread = _thread(client, owner, conv["id"])
    assert thread["status"] == "waiting"
    assert any(m["from_staff"] and "screenshot" in m["body"] for m in thread["messages"]), \
        "the moderator's reply is in the seller's thread"
    notice = next(n for n in _notices(client, owner) if n["kind"] == "support_request")
    assert notice["title"] == f"Bluntly replied: {conv['subject']} · your reply is needed"
    assert notice["link"] == f"/seller/{store}/messages?c={conv['id']}"
    assert req["reference"] in notice["body"], "the code is only small print"
    assert req["reference"] not in notice["title"]

    # MQA-023: the seller answers in the thread; the request is in review again.
    client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=owner,
                data={"body": "Here it is: shopee.ph/ourstore"})
    again = client.get(f"/api/v1/admin/support-requests/{req['id']}", headers=staff).json()
    assert again["status"] == "in_review"
    assert _thread(client, owner, conv["id"])["status"] == "open"


def test_resolving_closes_the_thread_and_closing_the_thread_resolves_the_request(client):
    store, owner, staff, conv, req = _moved(client)
    res = client.post(f"/api/v1/admin/support-requests/{req['id']}/respond", headers=staff,
                      json={"response": "Updated. Thanks!", "action": "resolve"})
    assert res.json()["status"] == "resolved"
    assert _thread(client, owner, conv["id"])["status"] == "closed"

    # And the other way round, from the Inbox's status menu.
    store, owner, staff, conv, req = _moved(client)
    client.post(f"/api/v1/admin/inbox/{conv['id']}/status", headers=staff,
                json={"status": "closed"})
    assert client.get(f"/api/v1/admin/support-requests/{req['id']}",
                      headers=staff).json()["status"] == "resolved"


def test_a_staff_reply_in_the_inbox_is_the_requests_last_reply(client):
    store, owner, staff, conv, req = _moved(client)
    client.post(f"/api/v1/admin/inbox/{conv['id']}/messages", headers=staff,
                data={"body": "Looking at it now."})
    got = client.get(f"/api/v1/admin/support-requests/{req['id']}", headers=staff).json()
    assert got["admin_response"] == "Looking at it now."
    assert got["status"] == "in_review"
    seller_view = client.get(f"/api/v1/sellers/{store}/support-requests/{req['id']}",
                             headers=owner).json()
    assert seller_view["conversation_id"] == conv["id"]


def test_waiting_for_the_seller_is_not_waiting_on_a_moderator(client, db):
    from app.services import needs_attention_service as svc
    store, owner, staff, conv, req = _moved(client)
    before = svc.support_requests_open(db)
    client.post(f"/api/v1/admin/support-requests/{req['id']}/respond", headers=staff,
                json={"response": "Which link?", "action": "ask"})
    db.expire_all()
    assert svc.support_requests_open(db) == before - 1

"""The Inbox and Messages (0076; Figma Screen/Admin/Inbox, Screen/Seller/Inbox,
Screen/Messages): a member and the Bluntly team, and nobody else."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import claim_body, register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _start(client, headers, **fields):
    data = {"audience": "reviewer", "topic": "account", "body": "Can I change my username?"}
    data.update({k: v for k, v in fields.items() if k != "files"})
    return client.post("/api/v1/conversations", headers=headers, data=data,
                       files=fields.get("files"))


@pytest.fixture
def outbox(monkeypatch):
    sent: list[tuple[str, str, str]] = []
    from app.adapters import email as email_adapter
    monkeypatch.setattr(email_adapter, "send_email",
                        lambda to, subject, text, html=None: sent.append((to, subject, text)))
    return sent


def _claimed_store(client) -> tuple[str, dict, dict]:
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(owner), json={
        "display_name": f"Inbox Store {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()["id"]
    claim = client.post(f"/api/v1/sellers/{store}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                       headers=_auth(mod), json={"decision": "approve"}).status_code == 200
    return store, _auth(owner), _auth(mod)


def _appeal(client, store: str, owner: dict) -> str:
    _, buyer, _ = register_and_token(client)
    rated = client.post(f"/api/v1/sellers/{store}/reviews", headers=_auth(buyer), json={
        "accuracy": False, "order_completeness": False, "customer_service": 1,
        "packaging_quality": 1, "overall_rating": 2, "would_recommend": False,
        "comment": "Never arrived and nobody answered. " + "Words " * 8}).json()
    return client.post(f"/api/v1/sellers/reviews/{rated['id']}/appeal", headers=owner,
                       json={"reason": "We have no order under this name."}).json()["id"]


def test_a_reviewer_and_the_team_talk_and_nobody_else_reads_it(client, outbox):
    _, me, my_email = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    _, stranger, _ = register_and_token(client)
    started = _start(client, _auth(me))
    assert started.status_code == 201, started.text
    conv = started.json()
    cid = conv["id"]
    assert conv["status"] == "open" and conv["topic"] == "account"
    assert conv["subject"] == "Can I change my username?" and conv["reference"].startswith("MSG-")
    assert [m["body"] for m in conv["messages"]] == ["Can I change my username?"]

    mine = client.get("/api/v1/conversations", headers=_auth(me)).json()
    assert cid in [c["id"] for c in mine["items"]] and mine["counts"]["open"] >= 1

    # The team sees it unread under Reviewers; opening it marks it read.
    inbox = client.get("/api/v1/admin/inbox", headers=_auth(staff),
                       params={"tab": "reviewers", "q": conv["reference"]}).json()
    row = next(c for c in inbox["items"] if c["id"] == cid)
    assert row["unread"] is True and row["member"]["name"] == "Tester"
    detail = client.get(f"/api/v1/admin/inbox/{cid}", headers=_auth(staff)).json()
    assert detail["member_summary"]["role"] == "reviewer"
    again = client.get("/api/v1/admin/inbox", headers=_auth(staff),
                       params={"q": conv["reference"]}).json()
    assert next(c for c in again["items"] if c["id"] == cid)["unread"] is False

    # A reply reaches the member: notification, email, unread.
    sent = client.post(f"/api/v1/admin/inbox/{cid}/messages", headers=_auth(staff),
                       data={"body": "Done. Your username is updated."})
    assert sent.status_code == 201 and sent.json()["from_staff"] is True
    assert outbox and outbox[-1][0] == my_email and "Done. Your username" in outbox[-1][2]
    notes = client.get("/api/v1/notifications", headers=_auth(me)).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n["kind"] == "message_reply" and n["link"] == f"/messages/{cid}" for n in items)
    assert client.get("/api/v1/conversations/unread", headers=_auth(me)).json()["unread"] >= 1
    read = client.get(f"/api/v1/conversations/{cid}", headers=_auth(me)).json()
    assert read["unread"] is False and [m["from_staff"] for m in read["messages"]] == [False, True]

    # Strangers: not found, never forbidden (ids cannot be probed).
    assert client.get(f"/api/v1/conversations/{cid}", headers=_auth(stranger)).status_code == 404
    assert client.post(f"/api/v1/conversations/{cid}/messages", headers=_auth(stranger),
                       data={"body": "hi"}).status_code == 404
    assert client.get("/api/v1/admin/inbox", headers=_auth(stranger)).status_code == 403
    assert client.get(f"/api/v1/admin/inbox/{cid}", headers=_auth(me)).status_code == 403
    assert client.get("/api/v1/conversations").status_code == 401


def test_close_reopen_and_waiting(client, outbox):
    _, me, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    cid = _start(client, _auth(me), body="My payout email changed.").json()["id"]
    url = f"/api/v1/admin/inbox/{cid}"

    waiting = client.post(f"{url}/status", headers=_auth(staff), json={"status": "waiting"})
    assert waiting.json()["status"] == "waiting"
    # The member answering ends "waiting on them".
    client.post(f"/api/v1/conversations/{cid}/messages", headers=_auth(me),
                data={"body": "Here is the new one."})
    assert client.get(url, headers=_auth(staff)).json()["status"] == "open"

    closed = client.post(f"{url}/status", headers=_auth(staff), json={"status": "closed"}).json()
    assert closed["status"] == "closed" and closed["closed_by"]["id"]
    assert closed["messages"][-1]["kind"] == "event" and closed["messages"][-1]["body"] == "closed"
    assert outbox and outbox[-1][1].startswith("Closed:")
    assert client.post(f"{url}/messages", headers=_auth(staff),
                       data={"body": "One more thing"}).status_code == 409
    closed_tab = client.get("/api/v1/admin/inbox", headers=_auth(staff),
                            params={"tab": "closed", "q": closed["reference"]}).json()
    assert [c["id"] for c in closed_tab["items"]] == [cid]

    # A member's reply opens it again.
    client.post(f"/api/v1/conversations/{cid}/messages", headers=_auth(me),
                data={"body": "Actually it still fails."})
    reopened = client.get(url, headers=_auth(staff)).json()
    assert reopened["status"] == "open"
    assert [m["body"] for m in reopened["messages"] if m["kind"] == "event"] == ["closed",
                                                                                "reopened"]
    # The member resolves it themselves.
    done = client.post(f"/api/v1/conversations/{cid}/resolve", headers=_auth(me)).json()
    assert done["status"] == "closed" and done["closed_by"]["name"] == "Tester"
    assert client.get("/api/v1/conversations", headers=_auth(me),
                      params={"status": "closed"}).json()["counts"]["closed"] >= 1


def test_message_rules(client):
    _, me, _ = register_and_token(client)
    assert _start(client, _auth(me), body="   ").status_code == 422
    assert _start(client, _auth(me), body="x" * 501).status_code == 422
    # A reviewer cannot open a store topic; a store topic needs a store.
    assert _start(client, _auth(me), topic="appeal").status_code == 422
    assert _start(client, _auth(me), audience="seller", topic="other").status_code == 422
    # A link must fit the topic and be the member's own.
    assert _start(client, _auth(me), topic="payout", link_type="review",
                  link_id=str(uuid.uuid4())).status_code == 422
    assert _start(client, _auth(me), topic="payout", link_type="payout",
                  link_id=str(uuid.uuid4())).status_code == 404


def test_a_store_owner_writes_about_their_appeal_and_staff_move_it_to_support(client, outbox):
    store, owner, staff = _claimed_store(client)
    appeal_id = _appeal(client, store, owner)
    options = client.get("/api/v1/conversations/link-options", headers=owner,
                         params={"audience": "seller", "seller_id": store}).json()
    assert any(o["type"] == "appeal" and o["id"] == appeal_id for o in options)
    started = _start(client, owner, audience="seller", seller_id=store, topic="appeal",
                     link_type="appeal", link_id=appeal_id, body="Any news on this one?")
    assert started.status_code == 201, started.text
    conv = started.json()
    assert conv["subject"] == "Tester’s review" and conv["link"]["type"] == "appeal"
    assert conv["link"]["href"] == f"/seller/{store}/appeals"
    listed = client.get("/api/v1/conversations", headers=owner, params={"seller_id": store}).json()
    assert conv["id"] in [c["id"] for c in listed["items"]]

    # Someone else's store or appeal: refused.
    other_store, other_owner, _ = _claimed_store(client)
    assert _start(client, other_owner, audience="seller", seller_id=store,
                  topic="other").status_code == 403
    assert _start(client, other_owner, audience="seller", seller_id=other_store, topic="appeal",
                  link_type="appeal", link_id=appeal_id).status_code == 404

    sellers = client.get("/api/v1/admin/inbox", headers=staff,
                         params={"tab": "sellers", "topic": "appeal",
                                 "q": conv["reference"]}).json()
    assert [c["id"] for c in sellers["items"]] == [conv["id"]]
    staff_view = client.get(f"/api/v1/admin/inbox/{conv['id']}", headers=staff).json()
    assert staff_view["member_summary"]["label"] == "Store owner"
    assert staff_view["link"]["href"] == "/admin/sellers?tab=appeals"

    moved = client.post(f"/api/v1/admin/inbox/{conv['id']}/move-to-support", headers=staff)
    assert moved.status_code == 200, moved.text
    body = moved.json()
    # MQA-021/024: the thread stays open - it IS the request's history, and a
    # request still being handled stays in the seller's Open list.
    assert body["status"] == "open" and body["support_reference"].startswith("SUP-")
    assert body["messages"][-1]["body"] == f"support:{body['support_reference']}"
    support = client.get("/api/v1/admin/support-requests?limit=200", headers=staff).json()
    rows = support["items"] if isinstance(support, dict) else support
    req = next(r for r in rows if r["reference"] == body["support_reference"])
    # MQA-026: the seller's words as written, and the thread's own short title.
    assert req["message"] == "Any news on this one?"
    assert req["subject"] == conv["subject"]
    assert req["conversation_id"] == conv["id"]
    assert client.post(f"/api/v1/admin/inbox/{conv['id']}/move-to-support",
                       headers=staff).status_code == 409


def test_a_claims_chat_is_the_inbox_conversation(client, outbox):
    claimant_id, claimant, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(claimant), json={
        "display_name": f"Merge Store {uuid.uuid4().hex[:8]}", "platform": "lazada"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(claimant),
                        json=claim_body(shop_name=store["display_name"])).json()
    case_url = f"/api/v1/cases/claim/{claim['id']}/messages"
    assert client.post(case_url, headers=_auth(staff),
                       json={"body": "Can you send the DTI page?"}).status_code == 201

    mine = client.get("/api/v1/conversations", headers=_auth(claimant)).json()
    conv = next(c for c in mine["items"] if c["topic"] == "claim")
    assert conv["subject"] == store["display_name"] and conv["link"]["id"] == claim["id"]
    # Answering in Messages lands in the claim's chat, and the reverse.
    assert client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=_auth(claimant),
                       data={"body": "Sent it just now."}).status_code == 201
    assert [m["body"] for m in client.get(case_url, headers=_auth(staff)).json()] == [
        "Can you send the DTI page?", "Sent it just now."]
    client.post(f"/api/v1/admin/inbox/{conv['id']}/messages", headers=_auth(staff),
                data={"body": "Thanks, approving."})
    assert client.get(case_url, headers=_auth(claimant)).json()[-1]["body"] == "Thanks, approving."


def test_assign_and_filters(client):
    _, me, _ = register_and_token(client)
    staff_id, staff, _ = register_and_token(client, role="administrator")
    member_id, _, _ = register_and_token(client)
    cid = _start(client, _auth(me), body=f"Filter check {uuid.uuid4().hex[:6]}").json()["id"]
    url = f"/api/v1/admin/inbox/{cid}/assign"
    assert client.post(url, headers=_auth(staff), json={"admin_id": member_id}).status_code == 422
    done = client.post(url, headers=_auth(staff), json={"admin_id": staff_id}).json()
    assert done["assigned_admin"]["id"] == staff_id
    ref = done["reference"]
    mine = client.get("/api/v1/admin/inbox", headers=_auth(staff),
                      params={"handled": "me", "q": ref}).json()
    assert [c["id"] for c in mine["items"]] == [cid]
    assert client.get("/api/v1/admin/inbox", headers=_auth(staff),
                      params={"handled": "unassigned", "q": ref}).json()["items"] == []
    staff_list = client.get("/api/v1/admin/inbox/staff", headers=_auth(staff)).json()
    assert staff_id in [s["id"] for s in staff_list] and member_id not in [s["id"]
                                                                           for s in staff_list]
    assert client.post(url, headers=_auth(staff), json={"admin_id": None}).json()[
        "assigned_admin"] is None


def test_attachments_are_private(client, monkeypatch):
    from app.services import storage
    stored = {}

    def upload(conversation_id, data):
        stored["key"] = f"{conversation_id}/x.png"
        return stored["key"], "image/png"

    monkeypatch.setattr(storage, "upload_attachment", upload)
    def signed(key, expires_in=300, download=None):
        return f"https://signed.example/{key}" + (f"?download={download}" if download else "")

    monkeypatch.setattr(storage, "signed_attachment_url", signed)
    _, me, _ = register_and_token(client)
    _, stranger, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    conv = _start(client, _auth(me), body="Screenshot attached.",
                  files={"file": ("order.png", png, "image/png")}).json()
    att = conv["messages"][0]["attachment"]
    assert att["name"] == "order.png" and att["type"] == "image/png" and att["size"] == len(png)
    href = att["href"].removeprefix("/api/v1")
    assert client.get(f"/api/v1{href}", headers=_auth(me)).json()["url"].endswith(stored["key"])
    assert client.get(f"/api/v1{href}", headers=_auth(staff)).status_code == 200
    assert client.get(f"/api/v1{href}", headers=_auth(stranger)).status_code == 404
    # The image viewer's Download: the same check, a link that downloads by name.
    assert client.get(f"/api/v1{href}", headers=_auth(staff), params={"download": "true"}
                      ).json()["url"].endswith("?download=order.png")
    assert client.get(f"/api/v1{href}", headers=_auth(stranger),
                      params={"download": "true"}).status_code == 404


def test_attachment_types():
    from app.core.errors import AppError
    from app.services import storage
    assert storage.validate_attachment(b"%PDF-1.7 ...") == "application/pdf"
    assert storage.validate_attachment(b"\xff\xd8\xff" + b"0" * 10) == "image/jpeg"
    with pytest.raises(AppError):
        storage.validate_attachment(b"<html><script>alert(1)</script>")


def test_email_failure_never_loses_the_reply(client, monkeypatch):
    from app.adapters import email as email_adapter

    def broken(*_a, **_k):
        raise email_adapter.EmailSendError("down")

    monkeypatch.setattr(email_adapter, "send_email", broken)
    _, me, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    cid = _start(client, _auth(me)).json()["id"]
    assert client.post(f"/api/v1/admin/inbox/{cid}/messages", headers=_auth(staff),
                       data={"body": "Saved even if the email fails."}).status_code == 201
    assert client.post(f"/api/v1/conversations/{cid}/email-copy",
                       headers=_auth(me)).status_code == 503


def test_a_claim_file_is_listed_on_the_case_for_staff_only(client, monkeypatch):
    """Figma Overlay/Seller/Claim 7996:11538 lists the claimant's files under
    Evidence: a file sent in the claim's thread rides on the case chat, and
    only the parties and staff can open it."""
    from app.services import storage

    monkeypatch.setattr(storage, "upload_attachment",
                        lambda conversation_id, data: (f"{conversation_id}/bir.pdf",
                                                       "application/pdf"))
    monkeypatch.setattr(storage, "signed_attachment_url",
                        lambda key, expires_in=300, download=None: f"https://signed.example/{key}")
    _, claimant, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    _, stranger, _ = register_and_token(client)
    store = client.post("/api/v1/sellers", headers=_auth(claimant), json={
        "display_name": f"Evidence Store {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(claimant),
                        json=claim_body(shop_name=store["display_name"])).json()
    case_url = f"/api/v1/cases/claim/{claim['id']}/messages"
    assert client.post(case_url, headers=_auth(staff),
                       json={"body": "Can you upload your BIR 2303?"}).status_code == 201
    conv = next(c for c in client.get("/api/v1/conversations", headers=_auth(claimant)).json()[
        "items"] if c["topic"] == "claim")
    pdf = b"%PDF-1.7 " + b"0" * 64
    assert client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=_auth(claimant),
                       data={"body": "Uploaded it."},
                       files={"file": ("BIR_2303.pdf", pdf, "application/pdf")}).status_code == 201

    thread = client.get(case_url, headers=_auth(staff)).json()
    assert thread[0]["attachment"] is None
    att = thread[-1]["attachment"]
    assert att["name"] == "BIR_2303.pdf" and att["type"] == "application/pdf"
    href = att["href"].removeprefix("/api/v1")
    assert client.get(f"/api/v1{href}", headers=_auth(staff)).status_code == 200
    assert client.get(f"/api/v1{href}", headers=_auth(stranger)).status_code == 404
    assert client.get(case_url, headers=_auth(stranger)).status_code == 403

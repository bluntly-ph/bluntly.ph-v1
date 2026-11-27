"""MQA-011: edit, unsend and delete-for-me in a conversation.

The tester could not correct a sent message or take back one sent by mistake
(with its file). Now:

* its sender - member or staff, on the side they sent it from - may edit or
  unsend a message for CHANGE_WINDOW after sending; what it said before is kept
  in conversation_message_revisions, and an unsent file leaves storage;
* anyone in the thread may delete any message for themselves only;
* nobody may change someone else's message, or their own once the window shuts.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from tests.conftest import requires_db
from tests.test_claim_evidence import (  # noqa: F401 - fake_storage is a fixture
    PDF,
    _claim,
    _start_claim_thread,
    fake_storage,
)

pytestmark = [requires_db, pytest.mark.usefixtures("fake_storage")]


def _thread(client):
    claimant, staff, claim_id, store_id = _claim(client)
    started = _start_claim_thread(client, claimant, claim_id, store_id, body="Our DTI is 1234.")
    assert started.status_code == 201, started.text
    conv = started.json()["id"]
    first = next(m for m in client.get(f"/api/v1/conversations/{conv}", headers=claimant)
                 .json()["messages"] if m["kind"] == "message")
    return claimant, staff, conv, first


def _age(message_id: str, minutes: int) -> None:
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        db.execute(text("UPDATE conversation_messages SET created_at = created_at - :d "
                        "WHERE id = :m"), {"d": timedelta(minutes=minutes), "m": message_id})
        db.commit()


def _revisions(message_id: str) -> list[tuple[str, str]]:
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        return [tuple(r) for r in db.execute(text(
            "SELECT action, body FROM conversation_message_revisions WHERE message_id = :m "
            "ORDER BY created_at"), {"m": message_id})]


def test_the_sender_edits_and_the_old_words_are_kept(client):
    claimant, staff, conv, first = _thread(client)
    assert first["change_until"] is not None and first["edited_at"] is None
    url = f"/api/v1/conversations/{conv}/messages/{first['id']}"
    res = client.patch(url, headers=claimant, json={"body": "Our DTI is 3318207."})
    assert res.status_code == 200, res.text
    assert res.json()["body"] == "Our DTI is 3318207." and res.json()["edited_at"]
    # Both sides see the new words and that it was edited.
    seen = next(m for m in client.get(f"/api/v1/admin/inbox/{conv}", headers=staff)
                .json()["messages"] if m["id"] == first["id"])
    assert seen["body"] == "Our DTI is 3318207." and seen["edited_at"]
    assert _revisions(first["id"]) == [("edit", "Our DTI is 1234.")]
    # Words are still required for a message with no file.
    assert client.patch(url, headers=claimant, json={"body": "  "}).status_code == 422


def test_only_the_sender_and_only_within_the_window(client):
    claimant, staff, conv, first = _thread(client)
    member_url = f"/api/v1/conversations/{conv}/messages/{first['id']}"
    staff_url = f"/api/v1/admin/inbox/{conv}/messages/{first['id']}"
    # Staff cannot rewrite the member's message, nor unsend it.
    res = client.patch(staff_url, headers=staff, json={"body": "Changed by staff"})
    assert res.status_code == 403 and res.json()["code"] == "message_not_yours"
    assert client.post(f"{staff_url}/unsend", headers=staff).status_code == 403
    # Past the window, not even the sender.
    _age(first["id"], 16)
    late = client.patch(member_url, headers=claimant, json={"body": "Too late"})
    assert late.status_code == 409 and late.json()["code"] == "message_change_closed"
    assert client.post(f"{member_url}/unsend", headers=claimant).status_code == 409
    listed = client.get(f"/api/v1/conversations/{conv}", headers=claimant).json()["messages"]
    assert next(m for m in listed if m["id"] == first["id"])["change_until"] is None


def test_staff_edit_and_unsend_their_own_reply(client):
    claimant, staff, conv, _ = _thread(client)
    reply = client.post(f"/api/v1/admin/inbox/{conv}/messages", headers=staff,
                        data={"body": "Send your permit."}).json()
    url = f"/api/v1/admin/inbox/{conv}/messages/{reply['id']}"
    assert client.patch(url, headers=staff,
                        json={"body": "Send your mayor's permit."}).status_code == 200
    # The member cannot touch the team's reply from their side.
    assert client.post(f"/api/v1/conversations/{conv}/messages/{reply['id']}/unsend",
                       headers=claimant).status_code == 403
    gone = client.post(f"{url}/unsend", headers=staff)
    assert gone.status_code == 200 and gone.json()["unsent"] is True
    assert gone.json()["body"] == "" and gone.json()["change_until"] is None
    member_view = next(m for m in client.get(f"/api/v1/conversations/{conv}", headers=claimant)
                       .json()["messages"] if m["id"] == reply["id"])
    assert member_view["unsent"] is True and member_view["body"] == ""
    assert [a for a, _ in _revisions(reply["id"])] == ["edit", "unsend"]
    # An unsent message cannot be edited back.
    assert client.patch(url, headers=staff, json={"body": "Back"}).status_code == 409


def test_unsending_a_file_removes_it_from_the_thread_and_storage(client, fake_storage):  # noqa: F811
    claimant, staff, conv, _ = _thread(client)
    sent = client.post(f"/api/v1/conversations/{conv}/messages", headers=claimant,
                       files={"file": ("id-card.pdf", PDF, "application/pdf")}).json()
    assert sent["attachment"]["name"] == "id-card.pdf"
    res = client.post(f"/api/v1/conversations/{conv}/messages/{sent['id']}/unsend",
                      headers=claimant)
    assert res.status_code == 200 and res.json()["attachment"] is None
    assert fake_storage.removed and fake_storage.removed[-1].endswith(".pdf")
    assert client.get(f"/api/v1/conversations/{conv}/messages/{sent['id']}/attachment",
                      headers=staff).status_code == 404
    rows = client.get("/api/v1/conversations", headers=claimant).json()["items"]
    assert next(r for r in rows if r["id"] == conv)["preview"] == "Message unsent"


def test_delete_for_me_hides_it_from_that_person_only(client):
    claimant, staff, conv, first = _thread(client)
    reply = client.post(f"/api/v1/admin/inbox/{conv}/messages", headers=staff,
                        data={"body": "Thanks, checking now."}).json()
    # Anyone may hide anyone's message, at any time, for themselves.
    _age(reply["id"], 120)
    assert client.post(f"/api/v1/conversations/{conv}/messages/{reply['id']}/hide",
                       headers=claimant).status_code == 204
    assert client.post(f"/api/v1/conversations/{conv}/messages/{reply['id']}/hide",
                       headers=claimant).status_code == 204          # again: no error
    mine = [m["id"] for m in client.get(f"/api/v1/conversations/{conv}",
                                        headers=claimant).json()["messages"]]
    assert reply["id"] not in mine and first["id"] in mine
    theirs = [m["id"] for m in client.get(f"/api/v1/admin/inbox/{conv}",
                                          headers=staff).json()["messages"]]
    assert reply["id"] in theirs
    # A message in someone else's conversation is not found.
    other, _, _, _ = _thread(client)
    assert client.post(f"/api/v1/conversations/{conv}/messages/{reply['id']}/hide",
                       headers=other).status_code == 404


def test_a_staff_reply_with_an_unfilled_template_tag_is_refused(client):
    """MQA-028: "Hi {{store_name}}" never reaches a seller - not as a reply,
    not as an edit. A member's own braces are their business."""
    claimant, staff, conv, first = _thread(client)
    res = client.post(f"/api/v1/admin/inbox/{conv}/messages", headers=staff,
                      data={"body": "Hi {{store_name}}, please check {{ platform }}."})
    assert res.status_code == 422 and res.json()["code"] == "template_unfilled"
    assert res.json()["detail"] == "Fill in {{store_name}} and {{ platform }} before sending."
    ok = client.post(f"/api/v1/admin/inbox/{conv}/messages", headers=staff,
                     data={"body": "Hi PowerHub, please check Shopee."}).json()
    edit = client.patch(f"/api/v1/admin/inbox/{conv}/messages/{ok['id']}", headers=staff,
                        json={"body": "Hi {{seller_name}}"})
    assert edit.status_code == 422
    assert client.post(f"/api/v1/conversations/{conv}/messages", headers=claimant,
                       data={"body": "My shop is {{literally}} called that"}).status_code == 201

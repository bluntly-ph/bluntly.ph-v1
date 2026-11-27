"""MQA-009: a reply can be a file alone.

The tester attached proof in a support conversation and Send stayed grey; the
API also refused a message with no words ("Write a message before sending.").
A reply - the member's or the team's - may now carry only an attachment. A
message with neither words nor a file is still refused, and starting a new
conversation still needs words to say what it is about.

The attachment ERROR the tester also saw was the missing message-attachments
bucket (0086, test_claim_evidence); storage is faked here as it is there.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.conftest import requires_db
from tests.test_claim_evidence import (  # noqa: F401 - fake_storage is a fixture
    PDF,
    _claim,
    _rows,
    _start_claim_thread,
    fake_storage,
)

# Storage is faked for every test here (the fixture comes from test_claim_evidence).
pytestmark = pytest.mark.usefixtures("fake_storage")


def _thread(client):
    claimant, staff, claim_id, store_id = _claim(client)
    started = _start_claim_thread(client, claimant, claim_id, store_id)
    assert started.status_code == 201, started.text
    return claimant, staff, started.json()["id"]


@requires_db
def test_a_member_can_send_a_file_with_no_words(client):
    claimant, _, conv = _thread(client)
    res = client.post(f"/api/v1/conversations/{conv}/messages", headers=claimant,
                      data={"body": ""}, files={"file": ("dti.pdf", PDF, "application/pdf")})
    assert res.status_code == 201, res.text
    assert res.json()["body"] == ""
    assert res.json()["attachment"]["name"] == "dti.pdf"
    assert _rows(conv) == (2, 1)
    # The body field may be left out entirely, as a browser form with no text does.
    res = client.post(f"/api/v1/conversations/{conv}/messages", headers=claimant,
                      files={"file": ("permit.pdf", PDF, "application/pdf")})
    assert res.status_code == 201, res.text


@requires_db
def test_the_list_preview_names_the_file_instead_of_a_blank(client):
    claimant, staff, conv = _thread(client)
    client.post(f"/api/v1/conversations/{conv}/messages", headers=claimant,
                data={"body": "  "}, files={"file": ("dti.pdf", PDF, "application/pdf")})
    rows = client.get("/api/v1/conversations", headers=claimant).json()
    row = next(r for r in rows["items"] if r["id"] == conv)
    assert row["preview"] == "Sent a file: dti.pdf"


@requires_db
def test_the_team_can_reply_with_a_file_and_the_notice_says_so(client):
    claimant, staff, conv = _thread(client)
    res = client.post(f"/api/v1/admin/inbox/{conv}/messages", headers=staff,
                      files={"file": ("checklist.pdf", PDF, "application/pdf")})
    assert res.status_code == 201, res.text
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        member = db.execute(text("SELECT member_id FROM conversations WHERE id = :c"),
                            {"c": conv}).scalar()
        body = db.execute(text(
            "SELECT body FROM notifications WHERE user_id = :u ORDER BY created_at DESC LIMIT 1"),
            {"u": member}).scalar()
    assert body == "Sent a file: checklist.pdf"


@requires_db
def test_neither_words_nor_a_file_is_still_refused(client):
    claimant, staff, conv = _thread(client)
    for headers, path in ((claimant, f"/api/v1/conversations/{conv}/messages"),
                          (staff, f"/api/v1/admin/inbox/{conv}/messages")):
        res = client.post(path, headers=headers, data={"body": "   "})
        assert res.status_code == 422, res.text
        assert res.json()["code"] == "message_empty"
        assert "attach a file" in res.json()["detail"]
    assert _rows(conv) == (1, 0)


@requires_db
def test_a_new_unlinked_conversation_still_needs_words(client):
    claimant, _, _, _ = _claim(client)
    res = client.post("/api/v1/conversations", headers=claimant, data={
        "audience": "reviewer", "topic": "other", "body": ""},
        files={"file": ("x.pdf", PDF, "application/pdf")})
    assert res.status_code == 422
    assert res.json()["code"] == "message_empty"


@requires_db
def test_a_claims_proof_can_open_its_case_thread_alone(client):
    """MQA-013: the claim form sends its files into the claim's own thread -
    named by the claim, so the file needs no words - where staff read them."""
    claimant, staff, claim_id, store_id = _claim(client)
    res = _start_claim_thread(client, claimant, claim_id, store_id, body="",
                              file=("dti.pdf", PDF, "application/pdf"))
    assert res.status_code == 201, res.text
    again = _start_claim_thread(client, claimant, claim_id, store_id, body="",
                                file=("permit.pdf", PDF, "application/pdf"))
    assert again.status_code == 201 and again.json()["id"] == res.json()["id"], \
        "a second file joins the same case thread"
    case = client.get(f"/api/v1/cases/claim/{claim_id}/messages", headers=staff).json()
    assert [m["attachment"]["name"] for m in case if m["attachment"]] == ["dti.pdf", "permit.pdf"]

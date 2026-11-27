"""A store edits its own answer (Figma Overlay/Store/EditAnswer 8202:22530):
only the store's owner, only the store's answer, and buyers see "Edited"."""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth, _claimed_seller

pytestmark = requires_db


def _store_question_answered(client):
    owner_id, owner, store, _ = _claimed_seller(client)
    _, buyer, _ = register_and_token(client)
    q = client.post("/api/v1/questions", headers=_auth(buyer), json={
        "body": "Does it come with a charging cable?", "seller_id": store["id"]})
    assert q.status_code == 201, q.text
    qid = q.json()["id"]
    a = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(owner),
                    json={"body": "Yes, a cable is in the box."})
    assert a.status_code == 201, a.text
    assert a.json()["is_seller_answer"] is True and a.json()["edited_at"] is None
    return qid, a.json()["id"], owner, buyer, store


def test_the_owner_edits_the_store_answer_and_buyers_see_edited(client):
    qid, aid, owner, buyer, store = _store_question_answered(client)
    url = f"/api/v1/questions/{qid}/answers/{aid}"
    r = client.patch(url, headers=_auth(owner),
                     json={"body": "  Yes, a USB-C cable is in the box.  "})
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "Yes, a USB-C cable is in the box."
    assert r.json()["edited_at"] is not None
    shown = client.get(f"/api/v1/questions/{qid}").json()
    mine = next(a for a in shown["answers"] if a["id"] == aid)
    assert mine["body"] == "Yes, a USB-C cable is in the box." and mine["edited_at"] is not None
    console = client.get(f"/api/v1/sellers/{store['id']}/questions", headers=_auth(owner)).json()
    row = next(q for q in console if q["id"] == qid)
    assert row["store_answer"]["edited_at"] is not None


def test_only_the_owner_and_only_the_store_answer(client):
    qid, aid, owner, buyer, _ = _store_question_answered(client)
    url = f"/api/v1/questions/{qid}/answers/{aid}"
    # Another member, and the buyer who asked, cannot edit the store's answer.
    _, stranger, _ = register_and_token(client)
    assert client.patch(url, headers=_auth(stranger), json={"body": "Hijacked"}).status_code == 403
    assert client.patch(url, headers=_auth(buyer), json={"body": "Hijacked"}).status_code == 403
    assert client.patch(url, json={"body": "Hijacked"}).status_code == 401
    # A buyer's answer is not editable this way, even by its own author.
    b = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(stranger),
                    json={"body": "Mine came with one too."}).json()
    assert client.patch(f"/api/v1/questions/{qid}/answers/{b['id']}", headers=_auth(stranger),
                        json={"body": "Changed"}).status_code == 403
    # An unknown answer: 404.
    assert client.patch(f"/api/v1/questions/{qid}/answers/{uuid.uuid4()}", headers=_auth(owner),
                        json={"body": "x y z"}).status_code == 404


def test_the_edit_keeps_the_answer_rules(client):
    qid, aid, owner, _, _ = _store_question_answered(client)
    url = f"/api/v1/questions/{qid}/answers/{aid}"
    assert client.patch(url, headers=_auth(owner), json={"body": "   "}).status_code == 422
    assert client.patch(url, headers=_auth(owner), json={"body": "x" * 1001}).status_code == 422
    assert client.patch(url, headers=_auth(owner),
                        json={"body": "Buy it at https://example.com/deal"}).status_code == 422
    body = client.get(f"/api/v1/questions/{qid}").json()
    assert next(a for a in body["answers"] if a["id"] == aid)["edited_at"] is None

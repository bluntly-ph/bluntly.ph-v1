"""Owner decision 2026-09-28: the asker no longer chooses who may answer.

Removing the "for other buyers / for the seller" choice must change nothing
about WHO may answer — that is the Q&A rules' job, not the asker's — and must
keep the question's SUBJECT (a product or a store) exactly as it was.
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models.enums import QuestionDirectedTo
from app.models.qa import Question
from tests.conftest import claim_body, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, h) -> str:
    r = client.post("/api/v1/products", headers=h,
                    json={"name": f"QA Widget {uuid.uuid4().hex[:8]}", "category": "electronics"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _claimed_store(client, owner_h, mod_h) -> str:
    store = client.post("/api/v1/sellers", headers=owner_h, json={
        "display_name": f"QA Store {uuid.uuid4().hex[:8]}", "platform": "lazada"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=owner_h,
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision", headers=mod_h,
                       json={"decision": "approve"}).status_code == 200
    return store["id"]


def _stored_audience(question_id: str) -> QuestionDirectedTo:
    db = SessionLocal()
    try:
        return db.get(Question, uuid.UUID(question_id)).directed_to
    finally:
        db.close()


@requires_db
def test_a_product_question_takes_no_audience_and_anyone_may_answer(client):
    _, asker, _ = register_and_token(client)
    _, buyer, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    # An old client still sending the field: accepted, and ignored.
    q = client.post("/api/v1/questions", headers=_auth(asker),
                    json={"product_id": pid, "body": "Does it hold charge overnight?",
                          "directed_to": "seller"})
    assert q.status_code == 201, q.text
    question = q.json()
    assert "directed_to" not in question
    assert question["product_id"] == pid and question["seller_id"] is None
    # The deprecated column is derived from the subject, not from the client.
    assert _stored_audience(question["id"]) == QuestionDirectedTo.buyers

    answer = client.post(f"/api/v1/questions/{question['id']}/answers", headers=_auth(buyer),
                         json={"body": "Yes, about ninety percent by morning.", "rating": 4})
    assert answer.status_code == 201, answer.text

    # Best Answer stays the asker's call alone.
    url = f"/api/v1/questions/{question['id']}/answers/{answer.json()['id']}/best"
    assert client.post(url, headers=_auth(buyer)).status_code == 403
    assert client.post(url, headers=_auth(asker)).status_code == 200


@requires_db
def test_a_store_question_keeps_its_subject_and_the_store_may_answer(client):
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    _, buyer, _ = register_and_token(client)
    store = _claimed_store(client, _auth(owner), _auth(mod))
    q = client.post("/api/v1/questions", headers=_auth(buyer),
                    json={"seller_id": store, "body": "Do you ship to Davao?"}).json()
    assert q["seller_id"] == store and q["product_id"] is None
    assert _stored_audience(q["id"]) == QuestionDirectedTo.seller

    from_store = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_auth(owner),
                             json={"body": "Yes, three to five days."})
    assert from_store.status_code == 201 and from_store.json()["is_seller_answer"] is True
    _, another_buyer, _ = register_and_token(client)
    also = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_auth(another_buyer),
                       json={"body": "Mine took four days."})
    assert also.status_code == 201


@requires_db
def test_the_seller_rules_are_unchanged(client):
    """A claimed seller still never competes with buyers on a product question
    (§7), and a store answer still cannot be picked as best (§13)."""
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    _, asker, _ = register_and_token(client)
    store = _claimed_store(client, _auth(owner), _auth(mod))
    pid = _product(client, _auth(asker))
    product_q = client.post("/api/v1/questions", headers=_auth(asker),
                            json={"product_id": pid, "body": "Is the cable detachable?"}).json()
    competing = client.post(f"/api/v1/questions/{product_q['id']}/answers", headers=_auth(owner),
                            json={"body": "Buy ours instead."})
    assert competing.status_code == 403 and competing.json()["code"] == "seller_cannot_answer"

    store_q = client.post("/api/v1/questions", headers=_auth(asker),
                          json={"seller_id": store, "body": "Is this item in stock?"}).json()
    store_answer = client.post(f"/api/v1/questions/{store_q['id']}/answers", headers=_auth(owner),
                               json={"body": "Yes."}).json()
    best = client.post(f"/api/v1/questions/{store_q['id']}/answers/{store_answer['id']}/best",
                       headers=_auth(asker))
    assert best.status_code == 409 and best.json()["code"] == "seller_cannot_win"

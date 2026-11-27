"""The question page's thread (0073, Figma Question Detail v6B 7731:15601):
question up-votes, answer and reply votes from per-member rows, replies three
levels deep, removal by the author or staff, and answer reports."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.enums import VoteDirection
from app.models.qa import QAVote
from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth, _product

pytestmark = requires_db


def _thread(client):
    _, asker, _ = register_and_token(client)
    _, answerer, _ = register_and_token(client)
    _, reader, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    qid = client.post("/api/v1/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "How loud is it in a library?"}).json()["id"]
    aid = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(answerer),
                      json={"body": "Quiet on low.", "verdict": "yes", "rating": 4}).json()["id"]
    return qid, aid, _auth(asker), _auth(answerer), _auth(reader)


def test_question_upvote_toggles_and_is_counted_once(client):
    qid, _aid, asker, answerer, reader = _thread(client)
    url = f"/api/v1/questions/{qid}/vote"
    assert client.put(url, json={"up": True}).status_code == 401
    assert client.put(url, headers=asker, json={"up": True}).json()["code"] == "self_vote"
    for _ in range(2):                                   # idempotent
        r = client.put(url, headers=reader, json={"up": True})
        assert r.status_code == 200 and r.json() == {"upvotes": 1, "my_upvote": True}
    client.put(url, headers=answerer, json={"up": True})
    detail = client.get(f"/api/v1/questions/{qid}", headers=reader).json()
    assert (detail["upvotes"], detail["my_upvote"]) == (2, True)
    assert client.put(url, headers=reader, json={"up": False}).json() == {
        "upvotes": 1, "my_upvote": False}
    assert client.get(f"/api/v1/questions/{qid}").json()["my_upvote"] is False


def test_answer_votes_come_from_rows_and_order_the_answers(client):
    qid, aid, asker, answerer, reader = _thread(client)
    url = f"/api/v1/questions/{qid}/answers/{aid}/vote"
    assert client.put(url, headers=answerer, json={"vote": "up"}).status_code == 422
    assert client.put(url, headers=reader, json={"vote": "up"}).json() == {
        "up": 1, "down": 0, "my_vote": "up"}
    assert client.put(url, headers=reader, json={"vote": "down"}).json() == {
        "up": 0, "down": 1, "my_vote": "down"}
    client.put(url, headers=asker, json={"vote": "up"})
    a = client.get(f"/api/v1/questions/{qid}", headers=reader).json()["answers"][0]
    assert (a["helpful_votes"], a["unhelpful_votes"], a["my_vote"]) == (1, 1, "down")
    assert client.put(url, headers=reader, json={"vote": None}).json()["my_vote"] is None
    other = client.put(f"/api/v1/questions/{uuid.uuid4()}/answers/{aid}/vote",
                       headers=reader, json={"vote": "up"})
    assert other.status_code == 404                      # the answer is not under that id


def test_the_database_refuses_a_second_row(client):
    qid, aid, _asker, _answerer, reader = _thread(client)
    client.put(f"/api/v1/questions/{qid}/answers/{aid}/vote", headers=reader, json={"vote": "up"})
    me = client.get("/api/v1/auth/me", headers=reader).json()["id"]
    with SessionLocal() as db:
        db.add(QAVote(user_id=uuid.UUID(me), answer_id=uuid.UUID(aid),
                      direction=VoteDirection.down))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(QAVote(user_id=uuid.UUID(me), question_id=uuid.UUID(qid),
                      direction=VoteDirection.down))           # questions are up-only
        with pytest.raises(IntegrityError):
            db.commit()


def test_replies_nest_three_deep_and_are_counted(client):
    qid, aid, asker, answerer, reader = _thread(client)
    url = f"/api/v1/questions/{qid}/answers/{aid}/replies"
    assert client.post(url, json={"body": "hi"}).status_code == 401
    for bad in ({"body": ""}, {"body": "see https://evil.example"}, {"body": "x" * 1001}):
        assert client.post(url, headers=reader, json=bad).status_code == 422
    one = client.post(url, headers=reader, json={"body": "Level 3 is where it jumps."}).json()
    two = client.post(url, headers=answerer,
                      json={"body": "Thanks!", "parent_id": one["id"]}).json()
    three = client.post(url, headers=asker, json={"body": "Same.", "parent_id": two["id"]}).json()
    four = client.post(url, headers=reader,
                       json={"body": "Deeper?", "parent_id": three["id"]}).json()
    assert [one["depth"], two["depth"], three["depth"], four["depth"]] == [1, 2, 3, 3]
    assert four["parent_id"] == two["id"]                # joins the third level
    detail = client.get(f"/api/v1/questions/{qid}", headers=reader).json()
    assert detail["reply_count"] == 4 and detail["answers"][0]["reply_count"] == 4
    # The answer's author was told about the first reply.
    notes = client.get("/api/v1/notifications?limit=5", headers=answerer).json()
    assert any(n["kind"] == "answer_reply" for n in notes)

    # Reply votes, then removal: the author or staff only.
    rv = f"/api/v1/questions/{qid}/replies/{one['id']}/vote"
    assert client.put(rv, headers=reader, json={"vote": "up"}).status_code == 422  # own reply
    assert client.put(rv, headers=asker, json={"vote": "up"}).json()["up"] == 1
    gone = f"/api/v1/questions/{qid}/replies/{one['id']}"
    assert client.delete(gone, headers=asker).status_code == 403
    assert client.delete(gone, headers=reader).status_code == 204
    rows = client.get(f"/api/v1/questions/{qid}").json()["answers"][0]["replies"]
    assert one["id"] not in [r["id"] for r in rows]
    assert next(r for r in rows if r["id"] == two["id"])["parent_id"] is None  # re-attached
    _, staff, _ = register_and_token(client, "administrator")
    assert client.delete(f"/api/v1/questions/{qid}/replies/{two['id']}",
                         headers=_auth(staff)).status_code == 204


def test_answer_report_goes_to_the_queue(client):
    qid, aid, _asker, answerer, reader = _thread(client)
    url = f"/api/v1/questions/{qid}/answers/{aid}/report"
    assert client.post(url, headers=answerer, json={"reason": "spam"}).status_code == 422
    r = client.post(url, headers=reader, json={"reason": "spam"})
    assert r.status_code == 201, r.text

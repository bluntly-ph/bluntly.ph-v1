"""QA-058, round 2: Best Answer shows only as the asker's recorded pick.

The retest saw an answer marked Best Answer, with a "picked as the best one"
notification, and nothing showing the asker chose it. Production's three Best
Answers all predate the recorded pick (seed data and the old code): no picker,
no audit entry. Business Rules §7 makes Best Answer the asker's alone, so an
unattributed pick is not presented as one; the rows stay untouched.
"""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _question_with_answer(client):
    _, asker, _ = register_and_token(client)
    _, helper, _ = register_and_token(client)
    pid = client.post("/api/v1/products", headers=_h(asker), json={
        "name": f"QA058 fixture {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
    q = client.post("/api/v1/questions", headers=_h(asker),
                    json={"product_id": pid, "body": "Does it rattle at full speed?"}).json()
    a = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_h(helper),
                    json={"body": "Not mine, even after a month.", "rating": 4}).json()
    return asker, helper, q, a


@requires_db
def test_from_a_clean_question_only_the_askers_pick_makes_a_best_answer(client):
    asker, helper, q, a = _question_with_answer(client)

    before = client.get(f"/api/v1/questions/{q['id']}").json()
    assert before["best_answer_id"] is None
    assert not any(x["is_best_answer"] for x in before["answers"])

    _, stranger, _ = register_and_token(client)
    best_url = f"/api/v1/questions/{q['id']}/answers/{a['id']}/best"
    refused = client.post(best_url, headers=_h(stranger))
    assert refused.status_code in (403, 404)
    assert client.get(f"/api/v1/questions/{q['id']}").json()["best_answer_id"] is None

    picked = client.post(best_url, headers=_h(asker))
    assert picked.status_code == 200
    after = client.get(f"/api/v1/questions/{q['id']}").json()   # a reload
    assert after["best_answer_id"] == a["id"]
    assert after["best_answer_picked_by_asker"] is True
    assert [x["is_best_answer"] for x in after["answers"] if x["id"] == a["id"]] == [True]

    notes = client.get("/api/v1/notifications", headers=_h(helper)).json()
    best = [n for n in notes if n["kind"] == "best_answer"]
    assert len(best) == 1 and "person who asked" in best[0]["title"]


@requires_db
def test_an_unattributed_legacy_pick_is_not_presented_as_best_answer(client):
    from app.db.session import SessionLocal
    from app.models.qa import Answer, Question

    asker, _, q, a = _question_with_answer(client)
    db = SessionLocal()
    try:   # what seed data and the pre-release code left behind: no picker
        question = db.get(Question, uuid.UUID(q["id"]))
        answer = db.get(Answer, uuid.UUID(a["id"]))
        question.best_answer_id = answer.id
        answer.is_best_answer = True
        db.commit()
    finally:
        db.close()

    detail = client.get(f"/api/v1/questions/{q['id']}").json()
    assert detail["best_answer_id"] is None
    assert detail["best_answer_picked_by_asker"] is False
    assert not any(x["is_best_answer"] for x in detail["answers"])
    listed = [x for x in client.get("/api/v1/questions?limit=100").json() if x["id"] == q["id"]]
    assert all(x["best_answer_id"] is None for x in listed)

    # The asker can still pick it, properly — and then it shows, attributed.
    assert client.post(f"/api/v1/questions/{q['id']}/answers/{a['id']}/best",
                       headers=_h(asker)).status_code == 200
    assert client.get(f"/api/v1/questions/{q['id']}").json()["best_answer_picked_by_asker"] is True

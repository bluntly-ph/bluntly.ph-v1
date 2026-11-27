"""The question card names who wrote the Best Answer (admin Answers queue,
Figma Screen/Admin/Queue/Answers 7956:11661: asker and answerer side by side)."""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth, _product


@requires_db
def test_the_card_names_the_best_answers_author_once_the_asker_picks_it(client):
    _, asker, _ = register_and_token(client)
    answerer_id, answerer, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    qid = client.post("/api/v1/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "Does the battery last a full shift?"}).json()["id"]
    aid = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(answerer),
                      json={"body": "About nine hours on medium.", "rating": 4}).json()["id"]

    def card() -> dict:
        rows = client.get("/api/v1/questions", params={"product_id": pid}).json()
        return next(r for r in rows if r["id"] == qid)

    assert card()["best_answer_by"] is None, "no pick, no Best Answer author"
    assert client.post(f"/api/v1/questions/{qid}/answers/{aid}/best",
                       headers=_auth(asker)).status_code == 200
    picked = card()
    assert picked["best_answer_by"]["id"] == answerer_id
    assert picked["answer_count"] == 1

"""Rules the full-system QA matrix found without a test (2026-09-24).

§8: a heavily downvoted comment collapses for everyone at net -5.
§10: a store's rating is a MEDIAN, like a product's — a mean is one extreme
rating away from a different answer.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.comment_service import is_collapsed
from tests.conftest import register_and_token, register_commenter, requires_db
from tests.test_business_rules_api import _auth, _product, _review


@pytest.mark.parametrize("helpful,unhelpful,collapsed", [
    (0, 4, False), (0, 5, True), (1, 6, True), (2, 6, False), (10, 0, False)])
def test_a_comment_collapses_at_exactly_net_minus_five(helpful, unhelpful, collapsed):
    assert is_collapsed(helpful, unhelpful) is collapsed


@requires_db
def test_downvotes_collapse_a_comment_for_every_reader(client):
    _, author, _ = register_and_token(client)
    _, commenter, _ = register_commenter(client)
    rid = _review(client, _auth(author), _product(client, _auth(author)))["id"]
    cid = client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(commenter),
                      json={"body": "A take people will disagree with."}).json()["id"]

    def state() -> bool:
        listed = client.get(f"/api/v1/reviews/{rid}/comments").json()
        return next(c for c in listed if c["id"] == cid)["is_collapsed"]

    voters = [register_commenter(client)[1] for _ in range(5)]
    for token in voters[:4]:
        assert client.post(f"/api/v1/comments/{cid}/vote", headers=_auth(token),
                           json={"vote": "down"}).status_code == 200
    assert state() is False                     # net -4
    client.post(f"/api/v1/comments/{cid}/vote", headers=_auth(voters[4]), json={"vote": "down"})
    assert state() is True                      # net -5: collapsed, for anonymous readers too


@requires_db
def test_a_store_rating_is_the_median_not_the_mean(client):
    _, owner, _ = register_and_token(client)
    store = client.post("/api/v1/sellers", headers=_auth(owner), json={
        "display_name": f"Median Store {uuid.uuid4().hex[:6]}", "platform": "shopee"}).json()
    for stars in (5, 1, 4):
        _, buyer, _ = register_and_token(client)
        rated = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(buyer), json={
            "accuracy": True, "order_completeness": True, "customer_service": 3,
            "packaging_quality": 3, "overall_rating": stars, "would_recommend": stars >= 3,
            "comment": f"Rated {stars}."})
        assert rated.status_code == 201, rated.text
    detail = client.get(f"/api/v1/sellers/{store['id']}").json()
    assert detail["overall_average"] == pytest.approx(4.0)     # the mean would be 3.33
    assert detail["summary"]["overall_average"] == pytest.approx(4.0)


@requires_db
def test_a_qa_author_shows_their_own_reputation_not_zero(client):
    """Defense rehearsal: every asker and answerer read "· 0", a Stage 3
    reviewer included, because the Q&A author left the score out."""
    from decimal import Decimal

    from app.db.session import SessionLocal
    from app.models.user import User

    asker_id, asker, _ = register_and_token(client)
    helper_id, helper, _ = register_and_token(client)
    db = SessionLocal()
    try:
        for uid, score in ((asker_id, "31.50"), (helper_id, "62.40")):
            db.get(User, uuid.UUID(uid)).reputation_score = Decimal(score)
        db.commit()
    finally:
        db.close()
    pid = client.post("/api/v1/products", headers=_auth(asker), json={
        "name": f"Reputation fixture {uuid.uuid4().hex[:8]}",
        "category": "electronics"}).json()["id"]
    q = client.post("/api/v1/questions", headers=_auth(asker),
                    json={"product_id": pid, "body": "Does it charge a laptop?"}).json()
    client.post(f"/api/v1/questions/{q['id']}/answers", headers=_auth(helper),
                json={"body": "Slowly, yes.", "rating": 4})

    detail = client.get(f"/api/v1/questions/{q['id']}").json()
    assert Decimal(str(detail["asker"]["reputation_score"])) == Decimal("31.50")
    assert Decimal(str(detail["answers"][0]["responder"]["reputation_score"])) == Decimal("62.40")

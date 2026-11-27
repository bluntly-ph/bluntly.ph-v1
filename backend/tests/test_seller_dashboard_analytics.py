"""The claimed seller's dashboard analytics (owner decision 2026-09-28).

Every figure must match the database exactly, from a store built here with
known reviews, votes, replies, responses, questions and a suspected-fake flag.
"""

from __future__ import annotations

import uuid

from tests.conftest import claim_body, register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _store(client):
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(owner), json={
        "display_name": f"Analytics Store {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                       headers=_auth(mod), json={"decision": "approve"}).status_code == 200
    return store["id"], _auth(owner), _auth(mod)


def _rate(client, store_id, overall, recommend=True) -> tuple[str, dict]:
    _, buyer, _ = register_and_token(client)
    r = client.post(f"/api/v1/sellers/{store_id}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 4,
        "packaging_quality": 4, "overall_rating": overall, "would_recommend": recommend,
        "comment": f"Rated {overall}. " + "Words " * 10})
    assert r.status_code == 201, r.text
    return r.json()["id"], _auth(buyer)


def test_an_empty_store_dashboard(client):
    store, owner, _ = _store(client)
    body = client.get(f"/api/v1/sellers/{store}/dashboard", headers=owner).json()
    a = body["analytics"]
    assert a["review_count"] == 0 and a["median_rating"] is None
    assert a["response_rate"] is None and a["most_engaged"] is None
    assert a["most_discussed"] is None and body["reviews"] == []
    assert len(a["months"]) == 6


def test_analytics_match_the_data(client):
    store, owner, _ = _store(client)
    r5, _ = _rate(client, store, 5)
    r3, b3 = _rate(client, store, 3, recommend=False)
    r4, _ = _rate(client, store, 4)

    # Engagement: r3 gets 2 helpful votes + 1 reply (3); r4 gets 2 replies (2).
    for _ in range(2):
        _, voter, _ = register_and_token(client)
        assert client.put(f"/api/v1/sellers/reviews/{r3}/vote", headers=_auth(voter),
                          json={"direction": "up"}).status_code == 200
    _, replier, _ = register_and_token(client)
    assert client.post(f"/api/v1/sellers/reviews/{r3}/replies", headers=_auth(replier),
                       json={"body": "Same happened to me."}).status_code == 201
    for text in ("Agreed.", "Mine arrived fine."):
        _, other, _ = register_and_token(client)
        assert client.post(f"/api/v1/sellers/reviews/{r4}/replies", headers=_auth(other),
                           json={"body": text}).status_code == 201
    # The store responds once and flags one review as suspected fake.
    assert client.post(f"/api/v1/sellers/reviews/{r5}/response", headers=owner,
                       json={"body": "Thank you!"}).status_code == 200
    assert client.post(f"/api/v1/sellers/reviews/{r3}/appeal", headers=owner,
                       json={"reason": "This order number was never ours."}).status_code == 201
    # A question to the store, answered by it; another unanswered.
    q1 = client.post("/api/v1/questions", headers=b3,
                     json={"seller_id": store, "body": "Do you restock?"}).json()
    client.post("/api/v1/questions", headers=b3, json={"seller_id": store, "body": "COD?"})
    assert client.post(f"/api/v1/questions/{q1['id']}/answers", headers=owner,
                       json={"body": "Every Monday."}).status_code == 201

    body = client.get(f"/api/v1/sellers/{store}/dashboard", headers=owner).json()
    a = body["analytics"]
    assert a["review_count"] == 3 and a["median_rating"] == 4.0
    assert a["rating_distribution"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1}
    assert a["helpful_votes_total"] == 2 and a["replies_total"] == 3
    assert a["responses_total"] == 1 and a["response_rate"] == 0.3333
    assert a["questions_total"] == 2 and a["questions_answered_by_store"] == 1
    assert a["appeals_open"] == 1
    assert a["most_engaged"]["id"] == r3 and a["most_engaged"]["engagement"] == 3
    assert a["most_discussed"]["id"] == r4 and a["most_discussed"]["reply_count"] == 2
    this_month = a["months"][-1]
    assert (this_month["reviews"], this_month["replies"], this_month["questions"]) == (3, 3, 2)

    rows = {r["id"]: r for r in body["reviews"]}
    assert rows[r5]["has_store_response"] is True and rows[r3]["appeal_status"] == "open"
    kinds = {e["kind"] for e in body["recent_activity"]}
    assert {"seller_review", "reply", "question", "store_response"} <= kinds


def test_only_the_owner_sees_the_dashboard(client):
    store, _, mod = _store(client)
    other_store, other_owner, _ = _store(client)
    url = f"/api/v1/sellers/{store}/dashboard"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=other_owner).status_code == 403
    _, member, _ = register_and_token(client)
    assert client.get(url, headers=_auth(member)).status_code == 403
    assert client.get(f"/api/v1/sellers/{other_store}/dashboard",
                      headers=other_owner).status_code == 200

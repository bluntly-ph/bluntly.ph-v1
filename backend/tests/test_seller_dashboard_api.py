"""The store owner's dashboard against a real database (FR-4 review monitoring).

Store names carry a per-test suffix: the isolated CI database is cumulative.
"""

from __future__ import annotations

import uuid

from tests.conftest import claim_body, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _store(client, headers: dict) -> dict:
    resp = client.post("/api/v1/sellers", headers=headers,
                       json={"display_name": f"Dash Store {uuid.uuid4().hex[:10]}",
                             "platform": "lazada"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _review() -> dict:
    return {"accuracy": True, "order_completeness": True, "customer_service": 4,
            "packaging_quality": 5, "overall_rating": 4, "would_recommend": True}


@requires_db
def test_the_owner_monitors_their_store(client):
    _, owner, _ = register_and_token(client)
    _, buyer, _ = register_and_token(client)
    _, moderator, _ = register_and_token(client, role="administrator")
    store = _store(client, _auth(buyer))
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                       headers=_auth(moderator), json={"decision": "approve"}).status_code == 200

    assert client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(buyer),
                       json=_review()).status_code == 201
    question = client.post("/api/v1/questions", headers=_auth(buyer),
                           json={"seller_id": store["id"], "body": "Do you restock?"}).json()

    mine = client.get("/api/v1/sellers/mine", headers=_auth(owner))
    assert mine.status_code == 200, mine.text
    assert [s["id"] for s in mine.json()] == [store["id"]]

    resp = client.get(f"/api/v1/sellers/{store['id']}/dashboard", headers=_auth(owner))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["seller"]["summary"]["review_count"] == 1
    assert len(body["monthly_volume"]) == 6
    assert sum(m["count"] for m in body["monthly_volume"]) == 1
    assert body["unanswered_questions"] == 1
    assert [q["id"] for q in body["waiting_questions"]] == [question["id"]]

    # Answered by the store, the question stops waiting on it.
    assert client.post(f"/api/v1/questions/{question['id']}/answers", headers=_auth(owner),
                       json={"body": "Every Monday."}).status_code == 201
    after = client.get(f"/api/v1/sellers/{store['id']}/dashboard", headers=_auth(owner)).json()
    assert after["unanswered_questions"] == 0
    assert after["waiting_questions"] == []


@requires_db
def test_only_the_approved_owner_opens_the_dashboard(client):
    _, claimant, _ = register_and_token(client)
    _, stranger, _ = register_and_token(client)
    store = _store(client, _auth(stranger))
    client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(claimant),
                json=claim_body("Mine, honestly."))
    url = f"/api/v1/sellers/{store['id']}/dashboard"

    assert client.get(url).status_code == 401
    for token in (claimant, stranger):
        resp = client.get(url, headers=_auth(token))
        assert resp.status_code == 403
        assert resp.json()["code"] == "not_store_owner"
    assert client.get("/api/v1/sellers/mine", headers=_auth(claimant)).json() == []


@requires_db
def test_waiting_reviews_are_the_oldest_still_without_a_response(client):
    """Overview "Waiting on you" is oldest first; the newest-30 list would hide them."""
    _, owner, _ = register_and_token(client)
    _, moderator, _ = register_and_token(client, role="administrator")
    buyers = [register_and_token(client)[1] for _ in range(3)]
    store = _store(client, _auth(buyers[0]))
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                       headers=_auth(moderator), json={"decision": "approve"}).status_code == 200
    ids = []
    for token in buyers:
        resp = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(token),
                           json=_review())
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    # The store answers the middle one: it stops waiting.
    assert client.post(f"/api/v1/sellers/reviews/{ids[1]}/response", headers=_auth(owner),
                       json={"body": "Thanks for the honest review."}).status_code == 200

    body = client.get(f"/api/v1/sellers/{store['id']}/dashboard", headers=_auth(owner)).json()
    assert [r["id"] for r in body["waiting_reviews"]] == [ids[0], ids[2]]
    assert [r["id"] for r in body["reviews"]] == list(reversed(ids))
    assert body["analytics"]["reviews_awaiting_response"] == 2

"""MQA-012: one claim under review per store, and the page says so.

The store page offered "Claim this store" to everyone, including the member
whose own claim was still waiting (the API refused only at submit), and a
second member could file a competing claim on the same store. Now a store with
a claim under review refuses another from anyone, and its public detail says a
claim is under review - never whose.
"""

from __future__ import annotations

import uuid

from tests.conftest import claim_body, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _store(client, headers) -> dict:
    res = client.post("/api/v1/sellers", headers=headers, json={
        "display_name": f"Review Co {uuid.uuid4().hex[:8]}", "platform": "shopee"})
    assert res.status_code == 201, res.text
    return res.json()


def _claim(client, headers, store):
    return client.post(f"/api/v1/sellers/{store['id']}/claims", headers=headers,
                       json=claim_body(shop_name=store["display_name"]))


@requires_db
def test_a_second_member_cannot_claim_a_store_under_review(client):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    store = _store(client, _auth(a))
    assert client.get(f"/api/v1/sellers/{store['id']}").json()["claim_under_review"] is False

    assert _claim(client, _auth(a), store).status_code == 201
    detail = client.get(f"/api/v1/sellers/{store['id']}").json()
    assert detail["claim_under_review"] is True
    assert detail["claim_status"] != "claimed"
    assert "user_id" not in detail and "claimant" not in detail, "never says whose"

    second = _claim(client, _auth(b), store)
    assert second.status_code == 409
    assert second.json()["code"] == "claim_under_review"
    assert "message the Bluntly team" in second.json()["detail"]

    again = _claim(client, _auth(a), store)
    assert again.status_code == 409 and again.json()["code"] == "claim_pending"


@requires_db
def test_once_the_claim_is_decided_or_withdrawn_another_may_claim(client):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    store = _store(client, _auth(a))
    first = _claim(client, _auth(a), store).json()
    withdrawn = client.post(f"/api/v1/sellers/claims/{first['id']}/withdraw", headers=_auth(a))
    assert withdrawn.status_code == 200, withdrawn.text
    assert client.get(f"/api/v1/sellers/{store['id']}").json()["claim_under_review"] is False

    second = _claim(client, _auth(b), store)
    assert second.status_code == 201, second.text
    rejected = client.post(f"/api/v1/admin/seller-claims/{second.json()['id']}/decision",
                           headers=_auth(staff), json={"decision": "reject"})
    assert rejected.status_code == 200, rejected.text
    assert _claim(client, _auth(a), store).status_code == 201


@requires_db
def test_the_claims_and_appeals_lists_page_without_gaps(client):
    """Pagination: the admin lists read every pending claim by offset (they
    stopped at the oldest 200 before), oldest first with a stable order."""
    _, staff, _ = register_and_token(client, role="administrator")
    h = {"Authorization": f"Bearer {staff}"}
    first = client.get("/api/v1/admin/seller-claims", headers=h,
                       params={"limit": 3, "offset": 0}).json()
    second = client.get("/api/v1/admin/seller-claims", headers=h,
                        params={"limit": 3, "offset": 3}).json()
    both = client.get("/api/v1/admin/seller-claims", headers=h,
                      params={"limit": 6, "offset": 0}).json()
    assert [c["id"] for c in first + second] == [c["id"] for c in both]
    assert client.get("/api/v1/admin/seller-claims?offset=-1", headers=h).status_code == 422
    assert client.get("/api/v1/admin/seller-review-appeals?offset=0&limit=5",
                      headers=h).status_code == 200

"""The top bar's search (Figma Search/Admin/Global, Search/Seller/Global)."""

from __future__ import annotations

import uuid

from tests.conftest import claim_body, register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_staff_search_groups_sellers_and_people_and_refuses_members(client):
    tag = uuid.uuid4().hex[:6]
    _, staff, _ = register_and_token(client, role="administrator")
    _, member, _ = register_and_token(client)
    store = client.post("/api/v1/sellers", headers=_auth(member), json={
        "display_name": f"Searchable {tag} Store", "platform": "shopee"}).json()
    groups = client.get("/api/v1/admin/search", headers=_auth(staff),
                        params={"q": f"Searchable {tag}"}).json()
    people = next(g for g in groups if g["key"] == "people")
    hit = next(h for h in people["items"] if h["id"] == store["id"])
    assert hit["tag"] == "Seller" and hit["href"] == f"/sellers/{store['id']}"
    assert hit["sub"] == "Store · not claimed"
    assert client.get("/api/v1/admin/search", headers=_auth(staff), params={"q": "x"}).json() == []
    # A pasted id that is no review finds nothing, and never errors.
    assert client.get("/api/v1/admin/search", headers=_auth(staff),
                      params={"q": str(uuid.uuid4())}).status_code == 200
    assert client.get("/api/v1/admin/search", headers=_auth(member),
                      params={"q": "anything"}).status_code == 403
    assert client.get("/api/v1/admin/search", params={"q": "anything"}).status_code == 401


def test_store_search_is_the_owners_store_only(client):
    tag = uuid.uuid4().hex[:6]
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    _, buyer, _ = register_and_token(client)
    store = client.post("/api/v1/sellers", headers=_auth(owner), json={
        "display_name": f"Store {tag}", "platform": "lazada"}).json()["id"]
    claim = client.post(f"/api/v1/sellers/{store}/claims", headers=_auth(owner),
                        json=claim_body("Mine.")).json()
    client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision", headers=_auth(mod),
                json={"decision": "approve"})
    r = client.post(f"/api/v1/sellers/{store}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 4,
        "packaging_quality": 4, "overall_rating": 3, "would_recommend": True,
        "comment": f"The clip{tag} broke in a week but the seller replied fast. Words words."})
    assert r.status_code == 201, r.text
    client.post("/api/v1/questions", headers=_auth(buyer),
                json={"seller_id": store, "body": f"Does the clip{tag} fit a stroller?"})

    groups = client.get(f"/api/v1/sellers/{store}/search", headers=_auth(owner),
                        params={"q": f"clip{tag}"}).json()
    by = {g["key"]: g for g in groups}
    assert by["reviews"]["items"][0]["sub"].startswith("3★ · Tester")
    assert by["reviews"]["items"][0]["href"] == f"/seller/{store}/reviews"
    assert by["questions"]["items"][0]["sub"] == "Tester · no answer yet"
    # Not the owner: refused.
    assert client.get(f"/api/v1/sellers/{store}/search", headers=_auth(buyer),
                      params={"q": "clip"}).status_code == 403

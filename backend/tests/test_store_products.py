"""Store ↔ product links (0077; Figma Screen/Seller/Products, Overlay/Store/
LinkProduct, Confirm/Store/LinkProduct, Confirm/Store/CancelLink)."""

from __future__ import annotations

import uuid

from tests.conftest import claim_body, register_and_token, requires_db
from tests.test_business_rules_api import _review

pytestmark = requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _store(client) -> tuple[str, dict, dict]:
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_h(owner), json={
        "display_name": f"Link Store {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()["id"]
    claim = client.post(f"/api/v1/sellers/{store}/claims", headers=_h(owner),
                        json=claim_body("Mine.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision", headers=_h(mod),
                       json={"decision": "approve"}).status_code == 200
    return store, _h(owner), _h(mod)


def _product(client, staff: dict, tag: str) -> dict:
    res = client.post("/api/v1/admin/products", headers=staff, json={
        "brand": f"Linko{tag}", "product_line": "Fan", "category": "home-living"})
    assert res.status_code == 201, res.text
    return res.json()


def test_link_request_approval_and_figures(client):
    store, owner, mod = _store(client)
    tag = uuid.uuid4().hex[:6]
    product = _product(client, mod, tag)
    for stars in (4, 5, 4, 3, 5):
        _, author, _ = register_and_token(client)
        _review(client, _h(author), product["id"], stars=stars)

    found = client.get(f"/api/v1/sellers/{store}/products/options", headers=owner,
                       params={"q": f"Linko{tag}"}).json()
    assert [(o["product_id"], o["state"]) for o in found] == [(product["id"], "link")]
    sent = client.post(f"/api/v1/sellers/{store}/products", headers=owner,
                       json={"product_id": product["id"]})
    assert sent.status_code == 201 and sent.json()["status"] == "pending"
    assert client.post(f"/api/v1/sellers/{store}/products", headers=owner,
                       json={"product_id": product["id"]}).status_code == 409
    listed = client.get(f"/api/v1/sellers/{store}/products", headers=owner).json()
    assert listed["waiting"] == 1 and listed["linked"] == 0
    # Not approved yet: no analytics.
    assert client.get(f"/api/v1/sellers/{store}/products/{product['id']}/analytics",
                      headers=owner).status_code == 404

    queue = client.get("/api/v1/admin/store-products", headers=mod).json()
    row = next(r for r in queue if r["id"] == sent.json()["id"])
    assert row["product_name"] == product["canonical_name"]
    ok = client.post(f"/api/v1/admin/store-products/{row['id']}/decision", headers=mod,
                     json={"decision": "approve"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    notes = client.get("/api/v1/notifications", headers=owner).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n["kind"] == "store_product_decided" for n in items)

    listed = client.get(f"/api/v1/sellers/{store}/products", headers=owner).json()
    linked = next(r for r in listed["rows"] if r["product_id"] == product["id"])
    assert listed["linked"] == 1 and linked["status"] == "approved"
    f = linked["figures"]
    assert f["reviews"] == 5 and f["median"] == 4.0
    assert listed["reviews"] == 5
    stats = client.get(f"/api/v1/sellers/{store}/products/{product['id']}/analytics",
                       headers=owner)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert len(body["months"]) == 6 and body["figures"]["median"] == 4.0
    assert client.post(f"/api/v1/admin/store-products/{row['id']}/decision", headers=mod,
                       json={"decision": "reject"}).status_code == 409


def test_cancel_and_who_may_do_what(client):
    store, owner, mod = _store(client)
    tag = uuid.uuid4().hex[:6]
    product = _product(client, mod, tag)
    link = client.post(f"/api/v1/sellers/{store}/products", headers=owner,
                       json={"product_id": product["id"]}).json()
    _, stranger, _ = register_and_token(client)
    assert client.get(f"/api/v1/sellers/{store}/products", headers=_h(stranger)).status_code == 403
    assert client.post(f"/api/v1/sellers/{store}/products/{link['id']}/cancel",
                       headers=_h(stranger)).status_code == 403
    assert client.get("/api/v1/admin/store-products", headers=owner).status_code == 403
    done = client.post(f"/api/v1/sellers/{store}/products/{link['id']}/cancel", headers=owner)
    assert done.status_code == 200 and done.json()["status"] == "cancelled"
    # A cancelled pair can be asked again.
    again = client.post(f"/api/v1/sellers/{store}/products", headers=owner,
                        json={"product_id": product["id"]})
    assert again.status_code == 201
    # A product that isn't in the catalogue cannot be linked.
    assert client.post(f"/api/v1/sellers/{store}/products", headers=owner,
                       json={"product_id": str(uuid.uuid4())}).status_code == 404

"""Overlay/Product/Edit · As is (Figma 8277:29379) and Confirm/Product/Merge
(8287:29648): a generic product named exactly as typed, and two catalogue pages
of one real product merged into one."""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _review

pytestmark = requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, staff: dict, tag: str, **over) -> dict:
    body = {"brand": f"Merge{tag}", "product_line": "Neck Fan", "category": "home-living"}
    body.update(over)
    res = client.post("/api/v1/admin/products", headers=staff, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_a_name_saved_as_is_needs_no_brand_or_line(client):
    _, token, _ = register_and_token(client, role="administrator")
    staff = _h(token)
    tag = uuid.uuid4().hex[:6]
    made = client.post("/api/v1/admin/products", headers=staff, json={
        "name_as_is": f"Portable  neck fan {tag}", "category": "home-living",
        "specs": [{"label": "Speeds", "value": "3", "in_name": True}]})
    assert made.status_code == 201, made.text
    p = made.json()
    # Exactly as typed (spaces tidied); specs are never appended to an as-is name.
    assert p["canonical_name"] == f"Portable neck fan {tag}"
    assert p["brand"] is None and p["line"] is None
    # Without an as-is name, brand and line are still required.
    bad = client.post("/api/v1/admin/products", headers=staff,
                      json={"brand": "", "product_line": "", "category": "home-living"})
    assert bad.status_code == 422
    too_short = client.post("/api/v1/admin/products", headers=staff,
                            json={"name_as_is": " x ", "category": "home-living"})
    assert too_short.status_code == 422


def test_merging_moves_everything_and_keeps_the_name_as_an_alias(client):
    _, token, _ = register_and_token(client, role="administrator")
    staff = _h(token)
    tag = uuid.uuid4().hex[:6]
    source = _product(client, staff, tag, product_line="Portable Fan",
                      aliases=[f"bladeless {tag}"])
    target = _product(client, staff, tag, product_line="Neck Fan Pro2")
    _, author, _ = register_and_token(client)
    review = _review(client, _h(author), source["id"])
    _, member, _ = register_and_token(client)

    assert client.post(f"/api/v1/products/{source['id']}/merge", headers=_h(member),
                       json={"target_product_id": target["id"]}).status_code == 403
    assert client.post(f"/api/v1/products/{source['id']}/merge", headers=staff,
                       json={"target_product_id": source["id"]}).status_code == 422
    merged = client.post(f"/api/v1/products/{source['id']}/merge", headers=staff,
                         json={"target_product_id": target["id"]})
    assert merged.status_code == 200, merged.text
    assert merged.json()["id"] == target["id"]
    assert client.get(f"/api/v1/reviews/{review['id']}").json()["product_id"] == target["id"]
    cat = client.get("/api/v1/admin/products/catalogue", headers=staff,
                     params={"q": f"Merge{tag}"}).json()
    row = next(i for i in cat["items"] if i["id"] == target["id"])
    assert source["canonical_name"] in row["aliases"] and f"bladeless {tag}" in row["aliases"]
    assert source["id"] not in [i["id"] for i in cat["items"]]
    # Merging the closed page again is refused.
    again = client.post(f"/api/v1/products/{source['id']}/merge", headers=staff,
                        json={"target_product_id": target["id"]})
    assert again.status_code == 409

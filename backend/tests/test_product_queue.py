"""The admin Products queue (meeting 2026-10-02, 9:08): submitter, link preview
(never fetched), age."""

from __future__ import annotations

import uuid

from app.services.product_queue_service import preview
from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth


def test_link_preview_reads_the_url_only():
    shop = preview("https://shopee.ph/Jisulife-Life9-i.123.456?sp_atk=x")
    assert (shop.host, shop.marketplace, shop.https) == ("shopee.ph", "shopee", True)
    odd = preview("http://shopee.ph.login-verify.example.com/item")
    assert odd.marketplace is None and odd.https is False   # a look-alike host is not Shopee
    assert preview(None) is None


@requires_db
def test_queue_lists_a_members_submission_for_staff_only(client):
    uid, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    tag = uuid.uuid4().hex[:10]
    made = client.post("/api/v1/products", headers=_auth(member), json={
        "name": f"Queue Test Fan {tag}", "category": "Electronics",
        "source_url": f"https://www.lazada.com.ph/products/queue-fan-{tag}-i999.html"})
    assert made.status_code in (200, 201), made.text
    assert client.get("/api/v1/admin/products/queue", headers=_auth(member)).status_code == 403
    body = client.get("/api/v1/admin/products/queue?sort=newest&limit=200",
                      headers=_auth(admin)).json()
    [row] = [i for i in body["items"] if i["id"] == made.json()["id"]]
    assert row["submitted_by_id"] == uid and row["waiting_days"] == 0
    assert row["link"]["marketplace"] == "lazada" and row["link"]["host"] == "www.lazada.com.ph"
    assert body["total"] >= 1

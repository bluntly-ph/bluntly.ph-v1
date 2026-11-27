"""A store's ratings page by page (?offset=), so the Seller console can reach
every review, not just the newest 100."""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth, _claimed_seller

pytestmark = requires_db


def _rate(client, store_id: str, n: int) -> None:
    _, buyer, _ = register_and_token(client)
    r = client.post(f"/api/v1/sellers/{store_id}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 4,
        "packaging_quality": 4, "overall_rating": 4, "would_recommend": True,
        "comment": f"Order {n} arrived on time.", "order_id": f"ORD-PAGE-{n}"})
    assert r.status_code == 201, r.text


def test_offset_pages_cover_every_review_once(client):
    _, _, store, _ = _claimed_seller(client)
    for n in range(5):
        _rate(client, store["id"], n)
    url = f"/api/v1/sellers/{store['id']}/reviews"
    every = [r["id"] for r in client.get(f"{url}?limit=100").json()]
    assert len(every) == 5
    paged = []
    for offset in (0, 2, 4):
        page = client.get(f"{url}?limit=2&offset={offset}")
        assert page.status_code == 200
        paged += [r["id"] for r in page.json()]
    assert paged == every
    assert client.get(f"{url}?limit=2&offset=6").json() == []
    assert client.get(f"{url}?offset=-1").status_code == 422

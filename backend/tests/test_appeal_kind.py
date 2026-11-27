"""A store's flag says what is wrong with the review (MQA-041, 0090), and the
admin sees it in the appeals queue (MQA-040)."""

from __future__ import annotations

from tests.conftest import all_pages, requires_db
from tests.test_seller_console_api import _auth, _claimed_store, _rate

pytestmark = requires_db


def _appeals(client, mod) -> list[dict]:
    return all_pages(client, "/api/v1/admin/seller-review-appeals", mod)


def test_each_kind_is_kept_and_shown_to_the_admin(client):
    store, owner, mod = _claimed_store(client)
    ids = {}
    for kind in ("never_ordered", "untrue", "breaks_rules"):
        review = _rate(client, store, 1.0)
        r = client.post(f"/api/v1/sellers/reviews/{review}/appeal", headers=owner,
                        json={"reason": f"Flagging this as {kind}, see records.", "kind": kind})
        assert r.status_code == 201, r.text
        assert r.json()["kind"] == kind
        ids[r.json()["id"]] = kind
    listed = {a["id"]: a["kind"] for a in _appeals(client, mod) if a["id"] in ids}
    assert listed == ids
    # The store sees its own flags with the kind too.
    mine = client.get(f"/api/v1/sellers/{store}/appeals", headers=owner).json()
    assert {a["id"]: a["kind"] for a in mine if a["id"] in ids} == ids


def test_kind_defaults_to_never_ordered_and_rejects_anything_else(client):
    store, owner, _ = _claimed_store(client)
    review = _rate(client, store, 2.0)
    bad = client.post(f"/api/v1/sellers/reviews/{review}/appeal", headers=owner,
                      json={"reason": "This buyer never ordered from us.", "kind": "spite"})
    assert bad.status_code == 422
    ok = client.post(f"/api/v1/sellers/reviews/{review}/appeal", headers=owner,
                     json={"reason": "This buyer never ordered from us."})
    assert ok.status_code == 201 and ok.json()["kind"] == "never_ordered"


def test_only_the_store_owner_can_flag(client):
    store, _, _ = _claimed_store(client)
    review = _rate(client, store, 1.0)
    from tests.conftest import register_and_token
    _, stranger, _ = register_and_token(client)
    r = client.post(f"/api/v1/sellers/reviews/{review}/appeal", headers=_auth(stranger),
                    json={"reason": "Not my store but flagging anyway.", "kind": "untrue"})
    assert r.status_code in (403, 404)

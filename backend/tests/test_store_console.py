"""Store Insights, the CSV export, the Store profile and giving a store up
(Figma Screen/Seller/Insights, Overlay/Store/Export, Screen/Seller/StoreProfile,
Confirm/Store/GiveUp; migration 0078)."""

from __future__ import annotations

import csv
import io
import uuid
import zipfile

from sqlalchemy import select

from tests.conftest import claim_body, register_and_token, requires_db

pytestmark = requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _store(client) -> tuple[str, dict, dict, str]:
    owner_id, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_h(owner), json={
        "display_name": f"Console Store {uuid.uuid4().hex[:8]}",
        "platform": "shopee"}).json()["id"]
    claim = client.post(f"/api/v1/sellers/{store}/claims", headers=_h(owner),
                        json=claim_body("Mine.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision", headers=_h(mod),
                       json={"decision": "approve"}).status_code == 200
    return store, _h(owner), _h(mod), owner_id


def _rate(client, store, overall, recommend=True) -> str:
    _, buyer, _ = register_and_token(client)
    r = client.post(f"/api/v1/sellers/{store}/reviews", headers=_h(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 4,
        "packaging_quality": 3, "overall_rating": overall, "would_recommend": recommend,
        "order_id": "260901ABCDEF", "comment": f"Rated {overall}. " + "Words " * 10})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_insights_are_the_owners_store_figures(client):
    store, owner, mod, _ = _store(client)
    first = _rate(client, store, 5)
    _rate(client, store, 3, recommend=False)
    _rate(client, store, 4)
    assert client.post(f"/api/v1/sellers/reviews/{first}/response", headers=owner,
                       json={"body": "Thank you!"}).status_code == 200

    res = client.get(f"/api/v1/sellers/{store}/insights", headers=owner)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["period"] == "6m" and body["reviews"] == 3 and body["reviews_before"] == 0
    assert body["rating"] == 4.0 and body["packaging"] == 3.0
    assert round(body["recommend"], 2) == 0.67 and round(body["responded"], 2) == 0.33
    assert body["matched"] == 1.0 and body["reply_hours"] is not None
    assert body["months"][-1]["reviews"] == 3
    assert body["platform"] == "shopee"
    # An unknown period falls back to six months; "all" has nothing before it.
    assert client.get(f"/api/v1/sellers/{store}/insights", headers=owner,
                      params={"period": "zz"}).json()["period"] == "6m"
    everything = client.get(f"/api/v1/sellers/{store}/insights", headers=owner,
                            params={"period": "all"}).json()
    assert everything["reviews"] == 3 and len(everything["months"]) == 1

    # Staff and strangers read stores in the Admin console, not here.
    _, stranger, _ = register_and_token(client)
    for headers in (mod, _h(stranger)):
        assert client.get(f"/api/v1/sellers/{store}/insights", headers=headers).status_code == 403
        assert client.get(f"/api/v1/sellers/{store}/export", headers=headers).status_code == 403
        assert client.get(f"/api/v1/sellers/{store}/profile", headers=headers).status_code == 403
    assert client.get(f"/api/v1/sellers/{uuid.uuid4()}/insights", headers=owner).status_code == 404


def test_the_export_is_a_zip_without_contact_details_or_order_ids(client):
    store, owner, _, _ = _store(client)
    _rate(client, store, 5)
    _rate(client, store, 2, recommend=False)
    sizes = client.get(f"/api/v1/sellers/{store}/export/sizes", headers=owner).json()
    assert sizes == {"reviews": 2, "questions": 0, "appeals": 0, "products": 0}

    res = client.get(f"/api/v1/sellers/{store}/export", headers=owner,
                     params={"include": "reviews,questions", "period": "all"})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert res.headers["content-disposition"].startswith('attachment; filename="bluntly-store-')
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    assert sorted(zf.namelist()) == ["store-questions.csv", "store-reviews.csv"]
    text = zf.read("store-reviews.csv").decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == 2 and not any("order_id" in k for k in rows[0])
    assert "260901ABCDEF" not in text and "@" not in text
    assert {r["would_recommend"] for r in rows} == {"yes", "no"}

    for bad in ("", "reviews,passwords"):
        assert client.get(f"/api/v1/sellers/{store}/export", headers=owner,
                          params={"include": bad}).status_code == 422


def test_the_profile_shows_only_the_end_of_the_registration_number(client):
    store, owner, _, _ = _store(client)
    _rate(client, store, 4)
    res = client.get(f"/api/v1/sellers/{store}/profile", headers=owner)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["reviews"] == 1 and body["rating"] == 4.0 and body["platform"] == "shopee"
    own = body["ownership"]
    assert own["registration_kind"] == "dti" and own["registration_last4"] == "5678"
    assert own["registered_business_name"] == "Test Trading"
    assert own["shop_name_matches"] is False  # "Test Shop" is not this store's name
    assert own["approved_at"] is not None and own["owner_name"]
    assert "3145678" not in res.text


def test_giving_a_store_up(client, db):
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    from app.models.user import User

    store, owner, mod, owner_id = _store(client)
    product = client.post("/api/v1/admin/products", headers=mod, json={
        "brand": f"Giveup{uuid.uuid4().hex[:6]}", "product_line": "Fan",
        "category": "home-living"}).json()
    link = client.post(f"/api/v1/sellers/{store}/products", headers=owner,
                       json={"product_id": product["id"]}).json()
    assert link["status"] == "pending"

    # Only the owner can give it up.
    assert client.post(f"/api/v1/sellers/{store}/give-up", headers=mod).status_code == 403
    res = client.post(f"/api/v1/sellers/{store}/give-up", headers=owner)
    assert res.status_code == 204, res.text

    detail = client.get(f"/api/v1/sellers/{store}").json()
    assert detail["claim_status"] == "unclaimed"
    for path in ("insights", "profile", "products", "dashboard"):
        assert client.get(f"/api/v1/sellers/{store}/{path}", headers=owner).status_code == 403
    assert client.post(f"/api/v1/sellers/{store}/give-up", headers=owner).status_code == 403
    assert all(s["id"] != store for s in client.get("/api/v1/sellers/mine", headers=owner).json())

    db.expire_all()
    # §9: the limits stay on the account for good.
    assert db.get(User, uuid.UUID(owner_id)).is_claimed_seller is True
    log = db.scalars(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.store_release,
        ModerationLog.target_ref == uuid.UUID(store))).one()
    assert str(log.moderator_id) == owner_id
    pending = client.get("/api/v1/admin/store-products", headers=mod,
                         params={"status": "pending"}).json()
    assert all(r["id"] != link["id"] for r in pending)

    # The store can be claimed again, by anyone.
    _, other, _ = register_and_token(client)
    again = client.post(f"/api/v1/sellers/{store}/claims", headers=_h(other),
                        json=claim_body("We run it now."))
    assert again.status_code == 201, again.text

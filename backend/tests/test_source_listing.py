"""A canonical product's own marketplace link is its listing (§5).

Found while seeding the defense dataset: every product had been submitted with
a Shopee or Lazada link, yet the moderator's affiliate-link queue was empty.
Canonicalization never recorded the product's own link as a product_platforms
listing (only attaching a duplicate did), and the queue lists only reviews of
products with a monetizable listing - so an earnings-approved review of a
product sold on exactly one marketplace never reached it. Migration 0054
records the rows that were never written.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

from tests.conftest import owned_photo_url, register_and_token, requires_db

_MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
              / "0054_record_source_listings.py")


def _backfill_sql() -> str:
    spec = importlib.util.spec_from_file_location("m0054", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.BACKFILL_SQL


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _listings(product_id: str) -> list[tuple[str, str]]:
    from app.db.session import SessionLocal
    from app.models.product import ProductPlatform

    db = SessionLocal()
    try:
        return [(p.platform.value, p.platform_url) for p in db.scalars(
            select(ProductPlatform).where(ProductPlatform.product_id == uuid.UUID(product_id)))]
    finally:
        db.close()


def _submit_and_canonicalize(client, url: str | None) -> tuple[str, dict, dict]:
    _, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    name = f"Listing fixture {uuid.uuid4().hex[:10]}"
    r = client.post("/api/v1/products", headers=_h(token),
                    json={"name": name, "category": "electronics", "source_url": url})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["status"] == "pending"
    r = client.post(f"/api/v1/products/{pid}/canonicalize", headers=_h(mod_token),
                    json={"brand": "Fixture", "product_line": name, "category": "electronics"})
    assert r.status_code == 200, r.text
    return pid, _h(token), _h(mod_token)


@requires_db
@pytest.mark.parametrize("url,platform", [
    ("https://s.shopee.ph/{tag}", "shopee"),
    ("https://www.lazada.com.ph/products/fixture-{tag}.html", "lazada"),
])
def test_canonicalizing_records_the_submitted_marketplace_link_as_a_listing(
        client, url, platform):
    url = url.format(tag=uuid.uuid4().hex[:10])
    pid, _, _ = _submit_and_canonicalize(client, url)
    assert _listings(pid) == [(platform, url)]


@requires_db
@pytest.mark.parametrize("url", [
    None,
    "https://www.anker.com/products/{tag}",          # the maker's own page
    "https://notshopee.ph/product/{tag}",            # a lookalike host
    "https://example.com/{tag}?to=shopee.ph",        # a marketplace only in the query
])
def test_a_link_that_is_not_a_marketplace_listing_is_not_recorded(client, url):
    # Unique per run: the same link twice is a duplicate submission (FR-2 2.8).
    url = url.format(tag=uuid.uuid4().hex[:10]) if url else None
    pid, _, _ = _submit_and_canonicalize(client, url)
    assert _listings(pid) == []


@requires_db
def test_an_approved_review_of_a_single_marketplace_product_reaches_the_link_queue(client):
    url = f"https://s.shopee.ph/{uuid.uuid4().hex[:10]}"
    pid, author, mod = _submit_and_canonicalize(client, url)
    r = client.post("/api/v1/reviews", headers=author, json={
        "product_id": pid, "title": "Solid for the price",
        "discussion": "Used it daily for a month; it held up and charged fast.",
        "verdict": "yes_absolutely", "star_rating": 4,
        "photo_url": owned_photo_url(author)})  # only a verified review earns
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings",
                       headers=mod).status_code == 200

    body = client.get("/api/v1/admin/awaiting-affiliate", headers=mod,
                      params={"limit": 100}).json()
    item = next((i for i in body["items"] if i["review"]["id"] == rid), None)
    assert item is not None, "an approved review of a Shopee product must await a link"
    assert [(p["platform"], p["is_monetizable"]) for p in item["platforms"]] == [("shopee", True)]


@requires_db
def test_recanonicalizing_does_not_duplicate_the_listing(client):
    url = f"https://s.shopee.ph/{uuid.uuid4().hex[:10]}"
    pid, _, mod = _submit_and_canonicalize(client, url)
    r = client.post(f"/api/v1/products/{pid}/canonicalize", headers=mod,
                    json={"brand": "Fixture", "product_line": "Renamed", "category": "electronics"})
    assert r.status_code == 200, r.text
    assert _listings(pid) == [("shopee", url)]


@requires_db
def test_a_moderator_adding_a_product_with_a_listing_records_it(client):
    _, mod_token, _ = register_and_token(client, role="administrator")
    url = f"https://s.lazada.com.ph/s.{uuid.uuid4().hex[:8]}"
    r = client.post("/api/v1/products", headers=_h(mod_token), json={
        "name": f"Moderator fixture {uuid.uuid4().hex[:8]}", "category": "electronics",
        "source_url": url})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "canonicalized"
    assert _listings(r.json()["id"]) == [("lazada", url)]


@requires_db
def test_the_backfill_records_only_canonical_marketplace_products_once(client):
    from app.db.session import SessionLocal
    from app.models.enums import ProductStatus
    from app.models.product import Product

    tag = uuid.uuid4().hex[:10]
    rows = {
        "shopee": (ProductStatus.canonicalized, f"https://shopee.ph/item-{tag}"),
        "lazada": (ProductStatus.canonicalized, f"https://s.lazada.com.ph/s.{tag}"),
        "pending": (ProductStatus.pending, f"https://s.shopee.ph/p{tag}"),
        "maker": (ProductStatus.canonicalized, f"https://www.anker.com/{tag}"),
        "lookalike": (ProductStatus.canonicalized, f"https://notshopee.ph/{tag}"),
    }
    db = SessionLocal()
    try:
        ids = {}
        for key, (status, url) in rows.items():
            p = Product(product_id=f"prd_{uuid.uuid4().hex[:10]}", canonical_name=f"{key} {tag}",
                        category="electronics", status=status, source_url=url)
            db.add(p)
            db.flush()
            ids[key] = str(p.id)
        db.commit()
        for _ in range(2):  # idempotent
            db.execute(text(_backfill_sql()))
            db.commit()
    finally:
        db.close()

    assert _listings(ids["shopee"]) == [("shopee", rows["shopee"][1])]
    assert _listings(ids["lazada"]) == [("lazada", rows["lazada"][1])]
    assert _listings(ids["pending"]) == []     # not in the catalogue yet
    assert _listings(ids["maker"]) == []       # not a marketplace
    assert _listings(ids["lookalike"]) == []   # host must be the marketplace's own


@requires_db
def test_an_attached_submission_is_no_longer_listed_as_a_product(client):
    """Defense rehearsal: after a duplicate was attached, product search listed
    it beside the product it joined, as a second entry with no reviews."""
    _, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    tag = uuid.uuid4().hex[:8]
    target = client.post("/api/v1/products", headers=_h(mod_token), json={
        "name": f"Attachfix Nano {tag}", "category": "electronics"}).json()["id"]
    dup = client.post("/api/v1/products", headers=_h(token), json={
        "name": f"attachfix nano powerbank {tag}", "category": "electronics"}).json()["id"]
    listed = lambda: {p["id"] for p in client.get(  # noqa: E731
        "/api/v1/products", params={"q": f"attachfix {tag}", "limit": 100}).json()}
    assert {target, dup} <= listed()             # a pending submission is visible meanwhile

    r = client.post(f"/api/v1/products/{dup}/attach", headers=_h(mod_token),
                    json={"target_product_id": target})
    assert r.status_code == 200, r.text
    assert target in listed()
    assert dup not in listed()
    assert client.get(f"/api/v1/products/{dup}").status_code == 200   # still on record

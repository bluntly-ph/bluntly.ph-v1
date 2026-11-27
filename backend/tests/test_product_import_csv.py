"""The product CSV import, past the basics (session 12, 2026-10-04): the file
format (docs/PRODUCT_CSV_IMPORT.md), matching by listing and by name, conflicts,
attaching to an existing product, the all-or-nothing apply, the audit entry and
the template. tests/test_product_admin_add_import.py covers preview-then-apply,
in-file duplicates and the unusable-file refusals.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from sqlalchemy import select

from tests.conftest import register_and_token, requires_db

pytestmark = requires_db

HEADER = "brand,line,variant,type,category,aliases,source_url,specs"
URL = "/api/v1/admin/products/import"


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _staff(client, role: str = "administrator") -> dict:
    return _h(register_and_token(client, role=role)[1])


def _csv(*lines: str, name: str = "products.csv") -> dict:
    return {"file": (name, ("\n".join(lines) + "\n").encode(), "text/csv")}


def _post(client, h, *lines, **data):
    res = client.post(URL, headers=h, files=_csv(*lines), data=data)
    assert res.status_code == 200, res.text
    return res.json()


def _product(client, h, tag: str, *, url: str | None = None, **over) -> dict:
    body = {"brand": f"Base{tag}", "product_line": "Fan", "key_spec": "Life 9",
            "category": "home-appliances", "aliases": [], "specs": []}
    body.update(over)
    if url:
        body["source_url"] = url
    res = client.post("/api/v1/admin/products", headers=h, json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _db():
    from app.db.session import SessionLocal
    return SessionLocal()


def _count_products(tag: str) -> int:
    from app.models.product import Product
    with _db() as db:
        return db.query(Product).filter(Product.canonical_name.ilike(f"%{tag}%")).count()


# ---------------------------------------------------------------- the file

def test_template_is_generated_from_the_columns(client):
    from app.services import product_admin_service as svc
    h = _staff(client)
    res = client.get(f"{URL}/template", headers=h)
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.text)))
    assert tuple(rows[0]) == svc.COLUMNS
    assert dict(zip(rows[0], rows[1], strict=True)) == {c: svc.EXAMPLE.get(c, "")
                                                        for c in svc.COLUMNS}
    # The template itself imports cleanly (as new, or as an existing product).
    preview = client.post(URL, headers=h, files={"file": ("t.csv", res.content, "text/csv")})
    assert preview.json()["rows"][0]["outcome"] in ("new", "exists")


def test_headers_are_forgiving_and_unknown_columns_are_reported(client):
    tag = uuid.uuid4().hex[:6]
    body = _post(client, _staff(client),
                 "Brand, Line ,CATEGORY,Listing URL,Colour,EAN-13",
                 f"Hdr{tag},Mixer,home-appliances,https://shopee.ph/mixer-{tag},red,123")
    assert body["rows"][0]["outcome"] == "new"
    assert body["ignored_columns"] == ["colour", "ean_13"]


def test_a_missing_or_repeated_required_column_refuses_the_file(client):
    h = _staff(client)
    missing = client.post(URL, headers=h, files=_csv("brand,line", "A,B"))
    assert missing.status_code == 422 and missing.json()["code"] == "import_columns_missing"
    twice = client.post(URL, headers=h, files=_csv("brand,line,category,brand",
                                                   "A,B,audio,C"))
    assert twice.status_code == 422 and twice.json()["code"] == "import_columns_repeated"


def test_row_errors_name_the_row_and_the_reason(client):
    tag = uuid.uuid4().hex[:6]
    body = _post(client, _staff(client), HEADER,
                 f"Err{tag},Fan,,,keyboards2,,,",                       # line 2
                 f"Err{tag},Lamp,,,home-living,,not a url,",            # line 3
                 f"Err{tag},Desk,,,home-living,,,Width 120 cm",         # line 4: no ':'
                 f"Err{tag},Chair,,,home-living,a|b,,Seat: Mesh|Arms: 4D")  # line 5: fine
    rows = {r["line"]: r for r in body["rows"]}
    assert rows[2]["outcome"] == "error" and "keyboards2" in rows[2]["errors"][0]
    assert rows[3]["outcome"] == "error" and "Listing links" in rows[3]["errors"][0]
    assert rows[4]["outcome"] == "error" and "Label: Value" in rows[4]["errors"][0]
    assert rows[5]["outcome"] == "new"
    assert body["counts"]["invalid"] == 3 and body["counts"]["total"] == 4


# ---------------------------------------------------------------- matching

def test_an_existing_listing_matches_even_when_only_a_listing_of_the_product(client):
    """The listing is on the product as a second marketplace listing, not as its
    own link: still the same product (product_platforms is checked too)."""
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    base = _product(client, h, tag, url=f"https://shopee.ph/base-{tag}")
    lazada = f"https://www.lazada.com.ph/products/base-{tag}.html"
    # Matched by name, the Lazada link is attached as the product's second listing.
    attach = _post(client, h, HEADER, f"Base{tag},Fan,Life 9,,home-appliances,,{lazada},",
                   apply="true", attach="2")
    assert attach["rows"][0]["outcome"] == "attached"
    # The same listing written differently (www., query, trailing slash) matches.
    body = _post(client, h, HEADER,
                 f"Third{tag},Name,,,home-appliances,,{lazada.replace('www.', '')}/?spm=1,")
    row = body["rows"][0]
    assert row["outcome"] == "exists" and row["product_id"] == base["id"]
    assert row["matched_by"] == "listing"


def test_matched_by_name_and_conflicts_are_never_written(client):
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    one = _product(client, h, tag, url=f"https://shopee.ph/one-{tag}")
    two = _product(client, h, tag, brand=f"Two{tag}")
    body = _post(client, h, HEADER,
                 # name of `one`, no link
                 f"Base{tag},Fan,Life 9,,home-appliances,,,",
                 # `one`'s listing with `two`'s name: conflict
                 f"Two{tag},Fan,Life 9,,home-appliances,,https://shopee.ph/one-{tag},",
                 apply="true", attach="2,3")
    by_name, conflict = body["rows"]
    assert by_name["outcome"] == "exists"  # nothing to add: no link, no new alias
    assert by_name["product_id"] == one["id"] and by_name["matched_by"] == "name"
    assert conflict["outcome"] == "conflict"
    assert "belongs to" in conflict["errors"][0] and conflict["product_id"] is None
    assert two["id"]  # untouched below
    with _db() as db:
        from app.models.product import ProductAlias
        aliases = set(db.scalars(select(ProductAlias.alias).where(
            ProductAlias.product_id == uuid.UUID(two["id"]))))
    assert aliases == set()


# ---------------------------------------------------------------- attach

def test_attach_adds_the_listing_and_aliases_and_nothing_else(client):
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    base = _product(client, h, tag, url=f"https://shopee.ph/att-{tag}",
                    specs=[{"label": "Battery", "value": "4000 mAh", "in_name": False}])
    lazada = f"https://www.lazada.com.ph/products/att-{tag}.html"
    lines = (HEADER,
             f"Base{tag},Fan,Life 9,,audio,fan {tag}|life nine {tag},{lazada},Battery: 1 mAh")
    preview = _post(client, h, *lines)
    row = preview["rows"][0]
    # Matched by name (the Lazada link is new); category/specs in the file differ.
    assert row["outcome"] == "exists" and row["matched_by"] == "name"
    assert row["attach_adds"] == [f"listing {lazada}", f"alias “fan {tag}”",
                                  f"alias “life nine {tag}”"]

    skipped = _post(client, h, *lines, apply="true")  # no attach: skipped
    assert skipped["rows"][0]["outcome"] == "exists" and skipped["counts"]["skipped"] == 1

    done = _post(client, h, *lines, apply="true", attach="2")
    assert done["rows"][0]["outcome"] == "attached" and done["counts"]["attached"] == 1
    product = client.get(f"/api/v1/products/{base['id']}").json()
    assert product["canonical_name"] == base["canonical_name"]
    assert product["category"] == "home-appliances"
    assert product["specs"] == [{"label": "Battery", "value": "4000 mAh", "in_name": False}]
    from app.models.product import ProductAlias, ProductPlatform
    with _db() as db:
        urls = set(db.scalars(select(ProductPlatform.platform_url).where(
            ProductPlatform.product_id == uuid.UUID(base["id"]))))
        aliases = set(db.scalars(select(ProductAlias.alias).where(
            ProductAlias.product_id == uuid.UUID(base["id"]))))
    assert lazada in urls and {f"fan {tag}", f"life nine {tag}"} <= aliases

    # Once attached there is nothing left to add: the row can only be skipped.
    again = _post(client, h, *lines, apply="true", attach="2")
    assert again["rows"][0]["outcome"] == "exists" and again["rows"][0]["attach_adds"] == []


# ---------------------------------------------------------------- apply

def test_preview_writes_nothing_and_apply_writes_and_audits(client):
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    lines = (HEADER,
             f"Aud{tag},Kettle,,,home-appliances,,,",
             f"Aud{tag},Toaster,,,home-appliances,,,",
             f"Aud{tag},Lamp,,,nowhere,,,")
    with _db() as db:
        before = db.query(ModerationLog).filter(
            ModerationLog.action == ModerationAction.product_import).count()
    _post(client, h, *lines)
    assert _count_products(f"Aud{tag}") == 0
    body = client.post(URL, headers=h, files=_csv(*lines, name="october.csv"),
                       data={"apply": "true"}).json()
    assert body["applied"] is True
    assert {k: body["counts"][k] for k in ("total", "imported", "attached", "skipped",
                                           "invalid", "failed")} == {
        "total": 3, "imported": 2, "attached": 0, "skipped": 0, "invalid": 1, "failed": 0}
    assert _count_products(f"Aud{tag}") == 2
    with _db() as db:
        logs = db.query(ModerationLog).filter(
            ModerationLog.action == ModerationAction.product_import).order_by(
            ModerationLog.created_at.desc()).all()
    assert len(logs) == before + 1
    entry = logs[0].context
    assert entry["file"] == "october.csv" and entry["imported"] == 2 and entry["invalid"] == 1
    assert sorted(entry["created_ids"]) == sorted(
        r["product_id"] for r in body["rows"] if r["outcome"] == "created")
    assert "Aud" not in str({k: v for k, v in entry.items() if k != "file"})  # no file content


def test_a_failure_while_applying_rolls_back_the_whole_import(client, monkeypatch):
    from app.services import product_admin_service as svc
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    real = svc._build

    def flaky(db, actor, new):
        if "Toaster" in new.name:
            raise RuntimeError("disk full")
        return real(db, actor, new)

    monkeypatch.setattr(svc, "_build", flaky)
    body = _post(client, h, HEADER,
                 f"Txn{tag},Kettle,,,home-appliances,,,",
                 f"Txn{tag},Toaster,,,home-appliances,,,",
                 f"Txn{tag},Lamp,,,home-appliances,,,", apply="true")
    assert body["applied"] is False and "Nothing was imported" in body["failure"]
    assert [r["outcome"] for r in body["rows"]] == ["new", "failed", "new"]
    assert body["counts"]["failed"] == 1
    assert _count_products(f"Txn{tag}") == 0


@pytest.mark.parametrize("role", ["user", "seller"])
def test_members_and_store_owners_cannot_import(client, role):
    _, token, _ = register_and_token(client, role=role)
    h = _h(token)
    assert client.post(URL, headers=h, files=_csv(HEADER)).status_code == 403
    assert client.get(f"{URL}/template", headers=h).status_code == 403
    assert client.get(f"{URL}/template").status_code == 401


def test_super_admin_may_import(client):
    tag = uuid.uuid4().hex[:6]
    body = _post(client, _staff(client, "super_admin"), HEADER,
                 f"Sup{tag},Kettle,,,home-appliances,,,", apply="true")
    assert body["counts"]["imported"] == 1

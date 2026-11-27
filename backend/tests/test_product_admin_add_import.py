"""Add product and Import products (owner request, 2026-10-03).

Staff add a named product, or many from a CSV, into the catalogue — never a
silent duplicate, never by a member or a store owner.
"""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _staff(client, role: str = "administrator") -> dict:
    _, token, _ = register_and_token(client, role=role)
    return _h(token)


def _body(tag: str, **over) -> dict:
    body = {"brand": f"Acme{tag}", "product_line": "Fan", "key_spec": "Life 9",
            "descriptor": "Handheld", "category": "electronics-tech",
            "aliases": [f"acme fan {tag}"],
            "specs": [{"label": "Battery", "value": "4000 mAh", "in_name": False}]}
    body.update(over)
    return body


def _csv(*lines: str) -> dict:
    return {"file": ("products.csv", ("\n".join(lines) + "\n").encode(), "text/csv")}


@requires_db
def test_staff_add_a_named_product_with_its_parts(client):
    tag = uuid.uuid4().hex[:6]
    res = client.post("/api/v1/admin/products", headers=_staff(client), json=_body(
        tag, source_url=f"https://shopee.ph/acme-fan-i.1.{tag}"))
    assert res.status_code == 201, res.text
    p = res.json()
    assert p["canonical_name"] == f"Acme{tag} Fan Life 9 Handheld"
    assert p["status"] == "canonicalized"
    assert (p["brand"], p["line"], p["key_spec"], p["descriptor"]) == (
        f"Acme{tag}", "Fan", "Life 9", "Handheld")
    assert p["specs"] == [{"label": "Battery", "value": "4000 mAh", "in_name": False}]
    # It is in the catalogue at once, with its alias, and editable.
    cat = client.get("/api/v1/admin/products/catalogue", headers=_staff(client),
                     params={"q": f"Acme{tag}"}).json()
    row = next(i for i in cat["items"] if i["id"] == p["id"])
    assert f"acme fan {tag}" in row["aliases"]


@requires_db
def test_a_duplicate_is_refused_with_the_existing_product(client):
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    url = f"https://shopee.ph/dupe-i.1.{tag}"
    first = client.post("/api/v1/admin/products", headers=h, json=_body(tag, source_url=url))
    assert first.status_code == 201, first.text
    # Same name, different case and punctuation.
    by_name = client.post("/api/v1/admin/products", headers=h, json=_body(
        tag, brand=f"ACME{tag}", product_line="fan,", key_spec="life-9"))
    assert by_name.status_code == 409, by_name.text
    assert by_name.json()["code"] == "product_exists"
    assert by_name.json()["product_id"] == first.json()["id"]
    # Same listing link under another name.
    by_link = client.post("/api/v1/admin/products", headers=h, json=_body(
        tag, brand="Other", source_url=url))
    assert by_link.status_code == 409
    assert by_link.json()["product_id"] == first.json()["id"]


@requires_db
def test_category_is_required_and_must_be_known(client):
    h = _staff(client)
    tag = uuid.uuid4().hex[:6]
    none = client.post("/api/v1/admin/products", headers=h, json=_body(tag, category=None))
    assert none.status_code == 422 and none.json()["code"] == "category_required"
    bad = client.post("/api/v1/admin/products", headers=h, json=_body(tag, category="spaceships"))
    assert bad.status_code == 422


@requires_db
def test_only_staff_add_or_import(client):
    tag = uuid.uuid4().hex[:6]
    assert client.post("/api/v1/admin/products", json=_body(tag)).status_code == 401
    _, member, _ = register_and_token(client)
    assert client.post("/api/v1/admin/products", headers=_h(member),
                       json=_body(tag)).status_code == 403
    assert client.post("/api/v1/admin/products/import", headers=_h(member),
                       files=_csv("brand,line,category", "A,B,electronics-tech")).status_code == 403
    # The Super Admin is staff too.
    assert client.post("/api/v1/admin/products", headers=_staff(client, "super_admin"),
                       json=_body(tag)).status_code == 201


@requires_db
def test_import_previews_without_writing_then_applies_only_new_rows(client):
    tag = uuid.uuid4().hex[:6]
    h = _staff(client)
    existing = client.post("/api/v1/admin/products", headers=h, json=_body(tag)).json()
    lines = (
        "brand,line,variant,type,category,aliases,source_url,specs",
        f"Imp{tag},Kettle,1.7L,,home-appliances,kettle {tag}|imp kettle,,Power: 2200 W",
        f"imp{tag},kettle,1.7l,,home-appliances,,,",            # same as the row above
        f"Acme{tag},Fan,Life 9,Handheld,electronics-tech,,,",   # already in the catalogue
        f"Imp{tag},Lamp,,,not-a-category,,,",                    # unknown category
        ",Nameless,,,home-appliances,,,",                         # no brand
        f"Imp{tag},Toaster,,,home-appliances,,ftp://x.example,",  # not a web link
    )
    preview = client.post("/api/v1/admin/products/import", headers=h, files=_csv(*lines))
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["applied"] is False
    assert [r["outcome"] for r in body["rows"]] == [
        "new", "duplicate", "exists", "error", "error", "error"]
    assert body["rows"][1]["duplicate_of_line"] == 2
    assert body["rows"][2]["product_id"] == existing["id"]
    assert "Brand is required." in body["rows"][4]["errors"][0]
    assert body["counts"]["new"] == 1
    # Nothing was written by the preview.
    cat = client.get("/api/v1/admin/products/catalogue", headers=h,
                     params={"q": f"Imp{tag}"}).json()
    assert cat["items"] == []

    applied = client.post("/api/v1/admin/products/import", headers=h, files=_csv(*lines),
                          data={"apply": "true"}).json()
    assert applied["applied"] is True
    assert applied["counts"]["created"] == 1
    created = next(r for r in applied["rows"] if r["outcome"] == "created")
    product = client.get(f"/api/v1/products/{created['product_id']}").json()
    assert product["canonical_name"] == f"Imp{tag} Kettle 1.7L"
    assert product["specs"] == [{"label": "Power", "value": "2200 W", "in_name": False}]

    # The same file again creates nothing: every row now exists.
    again = client.post("/api/v1/admin/products/import", headers=h, files=_csv(*lines),
                        data={"apply": "true"}).json()
    assert again["counts"]["created"] == 0
    assert again["rows"][0]["outcome"] == "exists"


@requires_db
def test_an_unusable_file_is_refused_whole(client):
    h = _staff(client)
    missing = client.post("/api/v1/admin/products/import", headers=h,
                          files=_csv("name,category", "Thing,home-appliances"))
    assert missing.status_code == 422
    assert missing.json()["code"] == "import_columns_missing"
    many = ["brand,line,category"] + [f"B{i},L{i},home-appliances" for i in range(501)]
    assert client.post("/api/v1/admin/products/import", headers=h,
                       files=_csv(*many)).json()["code"] == "import_too_many_rows"
    latin = {"file": ("p.csv", "brand,line,category\nCaf\xe9,X,home-appliances\n".encode("latin-1"),
                      "text/csv")}
    assert client.post("/api/v1/admin/products/import", headers=h,
                       files=latin).json()["code"] == "import_not_utf8"

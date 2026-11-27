"""The Edit product modal (meeting 2026-10-02, 9:00-11:40): the name parts are
kept as parts, and "add spec" stores label / value pairs that tell variants
apart (Jisulife batteries: 3.6K or 4K). Migration 0071."""

from __future__ import annotations

import uuid

from app.schemas.product import ProductCanonicalize
from tests.conftest import requires_db
from tests.test_round3_catalogue_api import _person, _product

pytestmark = requires_db


def _name(client, headers, pid, **extra):
    return client.post(f"/api/v1/products/{pid}/canonicalize", headers=headers,
                       json={"brand": "Aula", "product_line": "F75", "descriptor": "Keyboard",
                             "category": "gaming", **extra})


def test_parts_and_specs_are_stored_and_returned(client):
    _, admin = _person(client, "administrator")
    _, member = _person(client)
    pid = _product(client, member, f"aula f75 {uuid.uuid4().hex[:6]}")["id"]
    res = _name(client, admin, pid, specs=[
        {"label": " Switch ", "value": "Gateron  Brown"},
        {"label": "Battery", "value": "4000 mAh"}])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["canonical_name"] == "Aula F75 Keyboard"
    assert (body["brand"], body["line"], body["key_spec"], body["descriptor"]) == (
        "Aula", "F75", None, "Keyboard")
    assert body["specs"] == [{"label": "Switch", "value": "Gateron Brown", "in_name": False},
                             {"label": "Battery", "value": "4000 mAh", "in_name": False}]
    assert client.get(f"/api/v1/products/{pid}").json()["specs"] == body["specs"]

    # Renaming without specs leaves them; [] clears them.
    kept = _name(client, admin, pid, key_spec="Wireless").json()
    assert kept["canonical_name"] == "Aula F75 Wireless Keyboard" and len(kept["specs"]) == 2
    assert _name(client, admin, pid, specs=[]).json()["specs"] == []


def test_specs_are_validated(client):
    _, admin = _person(client, "administrator")
    _, member = _person(client)
    pid = _product(client, member, f"aula f75 {uuid.uuid4().hex[:6]}")["id"]
    for bad in ([{"label": "Battery", "value": "4K"}, {"label": "battery", "value": "3.6K"}],
                [{"label": "", "value": "4K"}],
                [{"label": "Manual", "value": "https://evil.example/f75"}],
                [{"label": f"S{i}", "value": "x"} for i in range(13)]):
        res = _name(client, admin, pid, specs=bad)
        assert res.status_code == 422, (bad, res.text)
    # A member cannot edit the catalogue.
    assert _name(client, member, pid, specs=[]).status_code == 403


def test_a_new_product_has_no_specs(client):
    _, member = _person(client)
    assert _product(client, member, f"plain {uuid.uuid4().hex[:6]}")["specs"] == []


def test_omitted_specs_mean_unchanged():
    assert ProductCanonicalize(brand="A", product_line="B").specs is None


def test_in_name_specs_join_the_name_and_stay_there(client):
    """Overlay/Product/Catalogue 7970:11467: "Saves as Xiaomi Redmi Note 13 Pro 5G
    8GB 256GB" — specs switched "In name" are part of the canonical name."""
    _, admin = _person(client, "administrator")
    _, member = _person(client)
    pid = _product(client, member, f"redmi note {uuid.uuid4().hex[:6]}")["id"]
    res = client.post(f"/api/v1/products/{pid}/canonicalize", headers=admin, json={
        "brand": "Xiaomi", "product_line": "Redmi Note 13 Pro", "key_spec": "5G",
        "category": "electronics-tech", "specs": [
            {"label": "RAM", "value": "8GB", "in_name": True},
            {"label": "Storage", "value": "256GB", "in_name": True},
            {"label": "Display", "value": "6.67in AMOLED"}]})
    assert res.status_code == 200, res.text
    assert res.json()["canonical_name"] == "Xiaomi Redmi Note 13 Pro 5G 8GB 256GB"
    # Renamed without sending specs: the in-name ones stay in the name.
    again = client.post(f"/api/v1/products/{pid}/canonicalize", headers=admin, json={
        "brand": "Xiaomi", "product_line": "Redmi Note 13 Pro"}).json()
    assert again["canonical_name"] == "Xiaomi Redmi Note 13 Pro 8GB 256GB"


def test_aliases_can_be_removed_and_the_catalogue_reads_them(client):
    _, admin = _person(client, "administrator")
    _, member = _person(client)
    tag = uuid.uuid4().hex[:6]
    pid = _product(client, member, f"aula f75 {tag}")["id"]
    _name(client, admin, pid)
    assert client.post(f"/api/v1/products/{pid}/aliases", headers=admin,
                       json={"aliases": [f"f75 {tag}", f"aula 75% {tag}"]}).status_code == 200
    cat = client.get(f"/api/v1/admin/products/catalogue?q=75%25 {tag}", headers=admin).json()
    row = next(r for r in cat["items"] if r["id"] == pid)
    assert sorted(row["aliases"]) == sorted([f"f75 {tag}", f"aula 75% {tag}"])
    assert row["price_trend"] == [] and row["latest_price"] is None
    assert cat["catalogue_count"] >= 1 and "queue_count" in cat
    url = f"/api/v1/products/{pid}/aliases"
    assert client.delete(url, params={"alias": f"f75 {tag}"}, headers=member).status_code == 403
    assert client.delete(url, params={"alias": f"F75 {tag}"}, headers=admin).status_code == 204
    assert client.delete(url, params={"alias": "nope"}, headers=admin).status_code == 404
    again = client.get(f"/api/v1/admin/products/catalogue?q={tag}", headers=admin).json()
    assert next(r for r in again["items"] if r["id"] == pid)["aliases"] == [f"aula 75% {tag}"]
    assert client.get("/api/v1/admin/products/catalogue", headers=member).status_code == 403

"""QA-001: a moderator can give a product its picture.

Production had 38 of 43 products with no stored image, and nothing in the app
could store one: the owner-run seeder was the only path. These pin the
moderator route that closes that gap, and that it cannot be used to put
anything but a real image, from anyone but staff, onto a public card.

Storage is replaced by a recorder, so the tests prove what would be uploaded
without touching a real bucket; the size and magic-byte checks still run.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.enums import ImageSource, ModerationAction
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.services import storage
from app.services.storage import MAX_PRODUCT_IMAGE_BYTES
from tests.conftest import register_and_token, requires_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class _Bucket:
    def __init__(self, uploads: list):
        self.uploads = uploads

    def upload(self, path, data, options):
        self.uploads.append((path, len(data), options["content-type"]))

    def get_public_url(self, path):
        return f"https://storage.test/{storage.PRODUCT_BUCKET}/{path}"


class _Storage:
    def __init__(self, uploads: list):
        self.uploads = uploads

    def from_(self, bucket):
        assert bucket == storage.PRODUCT_BUCKET
        return _Bucket(self.uploads)


class _Client:
    def __init__(self, uploads: list):
        self.storage = _Storage(uploads)


@pytest.fixture
def uploads(monkeypatch) -> list:
    recorded: list = []
    monkeypatch.setattr(storage, "get_service_client", lambda: _Client(recorded))
    return recorded


def _product(client, mod_token: str) -> dict:
    res = client.post("/api/v1/products", headers=_auth(mod_token), json={
        "name": f"Image Target {uuid.uuid4().hex[:8]}", "category": "electronics"})
    assert res.status_code == 201, res.text
    return res.json()


def _upload(client, token: str, product_id: str, data: bytes, name: str = "p.png"):
    return client.post(f"/api/v1/products/{product_id}/image", headers=_auth(token),
                       files={"file": (name, data, "image/png")})


@requires_db
def test_a_moderator_sets_the_image_and_it_is_served_and_audited(client, db, uploads):
    mod_id, mod, _ = register_and_token(client, role="administrator")
    product = _product(client, mod)
    assert product["image_url"] is None

    res = _upload(client, mod, product["id"], PNG)
    assert res.status_code == 200, res.text
    url = res.json()["image_url"]
    assert url.startswith(f"https://storage.test/{storage.PRODUCT_BUCKET}/{product['id']}/")
    assert uploads == [(url.split(f"{storage.PRODUCT_BUCKET}/", 1)[1], len(PNG), "image/png")]

    # The public read serves it, so cards and search rows stop showing the
    # placeholder for this product.
    assert client.get(f"/api/v1/products/{product['id']}").json()["image_url"] == url

    row = db.get(Product, uuid.UUID(product["id"]))
    db.refresh(row)
    assert row.image_source is ImageSource.moderator
    assert row.image_fetched_at is not None
    log = db.scalars(select(ModerationLog).where(
        ModerationLog.target_ref == row.id,
        ModerationLog.action == ModerationAction.photo_replace)).all()
    assert len(log) == 1
    assert str(log[0].moderator_id) == mod_id
    assert log[0].context == {"subject": "product_image", "replaced": False}

    # Replacing is the same action, recorded as a replacement.
    again = _upload(client, mod, product["id"], PNG)
    assert again.status_code == 200
    assert again.json()["image_url"] != url
    replaced = db.scalars(select(ModerationLog).where(
        ModerationLog.target_ref == row.id,
        ModerationLog.action == ModerationAction.photo_replace)).all()
    assert sorted(entry.context["replaced"] for entry in replaced) == [False, True]


@requires_db
@pytest.mark.parametrize("role", ["user", "seller"])
def test_only_staff_can_set_a_product_image(client, db, uploads, role):
    _, mod, _ = register_and_token(client, role="administrator")
    _, other, _ = register_and_token(client, role=role)
    product = _product(client, mod)

    res = _upload(client, other, product["id"], PNG)
    assert res.status_code == 403
    assert uploads == []
    row = db.get(Product, uuid.UUID(product["id"]))
    assert row.image_url is None


@requires_db
def test_anonymous_callers_are_refused(client, uploads):
    _, mod, _ = register_and_token(client, role="administrator")
    product = _product(client, mod)
    res = client.post(f"/api/v1/products/{product['id']}/image",
                      files={"file": ("p.png", PNG, "image/png")})
    assert res.status_code == 401
    assert uploads == []


@requires_db
def test_the_bytes_decide_not_the_declared_type(client, db, uploads):
    """An HTML page labelled image/png is refused before anything is stored."""
    _, mod, _ = register_and_token(client, role="administrator")
    product = _product(client, mod)

    res = _upload(client, mod, product["id"], b"<html><script>alert(1)</script></html>",
                  name="p.png")
    assert res.status_code == 415
    assert uploads == []
    assert db.get(Product, uuid.UUID(product["id"])).image_url is None


@requires_db
def test_an_oversized_image_is_refused(client, db, uploads):
    _, mod, _ = register_and_token(client, role="administrator")
    product = _product(client, mod)

    res = _upload(client, mod, product["id"], PNG + b"\x00" * MAX_PRODUCT_IMAGE_BYTES)
    assert res.status_code == 413
    assert uploads == []
    assert db.get(Product, uuid.UUID(product["id"])).image_url is None


@requires_db
def test_an_unknown_product_is_a_404(client, uploads):
    _, mod, _ = register_and_token(client, role="administrator")
    res = _upload(client, mod, str(uuid.uuid4()), PNG)
    assert res.status_code == 404
    assert uploads == []

"""QA-062 follow-up: a storage outage is a 503 with a sentence, never a bare 500.

Found while verifying the store-review cropper: on a server with no Supabase
Storage credentials POST /reviews/photo answered "500 Internal Server Error",
because only message attachments translated a storage failure. Every upload
helper now goes through one writer that answers 503 `storage_unavailable`.

What must NOT change: a file that is too big or not an image is still refused
as 413 / 415 before storage is touched, so an outage never hides a bad file.
"""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from app.core.errors import AppError
from app.services import storage
from tests.conftest import register_and_token, requires_db


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(out, "JPEG")
    return out.getvalue()


def _no_credentials():
    raise RuntimeError("Supabase service-role credentials are not configured.")


class _DownBucket:
    def upload(self, path, data, options):
        raise ConnectionError("storage is down")

    def get_public_url(self, path):  # pragma: no cover - never reached
        raise AssertionError("no URL for an object that was not stored")


class _DownClient:
    storage = type("S", (), {"from_": lambda _self, bucket: _DownBucket()})()


UPLOADERS = {
    "avatar": lambda data: storage.upload_avatar(uuid.uuid4(), data),
    "review photo": lambda data: storage.upload_review_photo(uuid.uuid4(), data),
    "receipt": lambda data: storage.upload_receipt(uuid.uuid4(), data),
    "product image": lambda data: storage.upload_product_image(uuid.uuid4(), data),
}


@pytest.mark.parametrize("name", UPLOADERS)
@pytest.mark.parametrize("client_factory", [_no_credentials, _DownClient],
                         ids=["no credentials", "storage down"])
def test_every_upload_helper_reports_an_outage_as_503(monkeypatch, name, client_factory):
    monkeypatch.setattr(storage, "get_service_client", client_factory)
    with pytest.raises(AppError) as err:
        UPLOADERS[name](_jpeg())
    assert err.value.status_code == 503
    assert err.value.code == "storage_unavailable"
    assert "try again" in err.value.detail


@pytest.mark.parametrize("name", UPLOADERS)
def test_validation_still_runs_before_storage(monkeypatch, name):
    """A non-image is a 415 even while storage is down: the outage never
    replaces the real reason a file is refused."""
    monkeypatch.setattr(storage, "get_service_client", _no_credentials)
    with pytest.raises(AppError) as err:
        UPLOADERS[name](b"<html><script>alert(1)</script></html>")
    assert err.value.status_code == 415


def test_size_messages_state_the_cap_that_is_enforced():
    """The photo and receipt messages said 8 MB while the cap is 4 MB."""
    too_big = b"\xff\xd8\xff" + b"0" * storage.UPLOAD_CEILING_BYTES
    mb = storage.UPLOAD_CEILING_BYTES // (1024 * 1024)
    for validate in (storage.validate_review_photo, storage.validate_receipt):
        with pytest.raises(AppError) as err:
            validate(too_big)
        assert err.value.status_code == 413
        assert f"{mb} MB" in err.value.detail


@requires_db
def test_review_photo_route_answers_503_without_storage(client, monkeypatch):
    monkeypatch.setattr(storage, "get_service_client", _no_credentials)
    _, token, _ = register_and_token(client)
    res = client.post("/api/v1/reviews/photo", headers={"Authorization": f"Bearer {token}"},
                      files={"file": ("photo.jpg", _jpeg(), "image/jpeg")})
    assert res.status_code == 503, res.text
    body = res.json()
    assert body["code"] == "storage_unavailable"
    assert "aren't available right now" in body["detail"]

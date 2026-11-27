"""Reused review photos (QA, 2026-09-29): "Reverse Image Search for possible
image plagiarism".

Layer 1, needing no provider, is built: every public review photo is
fingerprinted at upload (SHA-256 + 64-bit dHash) and a published review's
photo is compared with every earlier review's. Layer 2, searching the web,
needs a provider and none is procured; it stays "not_configured".
"""

from __future__ import annotations

import io
import random
import uuid

import pytest
from PIL import Image, ImageDraw, ImageEnhance

from app.core.config import settings
from app.services import image_fingerprint, storage
from app.services.image_fingerprint import NEAR_DISTANCE, UnreadableImage, distance, fingerprint
from tests.conftest import all_report_queue_items, register_and_token, requires_db, unique_text


def _photo(seed: int, size=(1200, 900)) -> Image.Image:
    """A synthetic photo: shapes and colours fixed by the seed."""
    rng = random.Random(seed)
    img = Image.new("RGB", size, tuple(rng.randint(0, 255) for _ in range(3)))
    draw = ImageDraw.Draw(img)
    for _ in range(25):
        x0, y0 = rng.randint(0, size[0]), rng.randint(0, size[1])
        box = (x0, y0, x0 + rng.randint(50, 500), y0 + rng.randint(50, 400))
        fill = tuple(rng.randint(0, 255) for _ in range(3))
        (draw.ellipse if rng.random() < 0.5 else draw.rectangle)(box, fill=fill)
    return img


def _jpeg(img: Image.Image, quality: int = 90) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality)
    return out.getvalue()


# --- the pure fingerprint ------------------------------------------------------------------

def test_an_exact_copy_is_the_same_file():
    data = _jpeg(_photo(1))
    a, b = fingerprint(data), fingerprint(data)
    assert a.sha256 == b.sha256 and distance(a.dhash, b.dhash) == 0


@pytest.mark.parametrize("variant", ["half size", "jpeg quality 30", "png", "10% crop", "brighter"])
def test_a_resized_or_re_encoded_copy_is_near(variant):
    base = _photo(1)
    w, h = base.size
    if variant == "half size":
        data = _jpeg(base.resize((w // 2, h // 2)))
    elif variant == "jpeg quality 30":
        data = _jpeg(base, 30)
    elif variant == "png":
        out = io.BytesIO()
        base.save(out, "PNG")
        data = out.getvalue()
    elif variant == "10% crop":
        data = _jpeg(base.crop((w // 20, h // 20, w - w // 20, h - h // 20)))
    else:
        data = _jpeg(ImageEnhance.Brightness(base).enhance(1.25))
    original, copy = fingerprint(_jpeg(base)), fingerprint(data)
    assert original.sha256 != copy.sha256                   # SHA-256 alone would miss it
    assert distance(original.dhash, copy.dhash) <= NEAR_DISTANCE


def test_unrelated_photos_are_far_apart():
    base = fingerprint(_jpeg(_photo(1))).dhash
    distances = [distance(base, fingerprint(_jpeg(_photo(seed))).dhash) for seed in range(2, 42)]
    assert min(distances) > NEAR_DISTANCE + 5


@pytest.mark.parametrize("data", [
    b"\xff\xd8\xff" + b"not really a jpeg" * 50,
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
    b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x01" * 40,
])
def test_a_corrupt_image_is_refused(data):
    with pytest.raises(UnreadableImage):
        fingerprint(data)


def test_a_decompression_bomb_is_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(image_fingerprint, "MAX_PIXELS", 100)
    with pytest.raises(UnreadableImage, match="too large"):
        fingerprint(_jpeg(_photo(1, size=(20, 20))))


def test_the_signed_bigint_round_trips_all_64_bits():
    for value in (0, 1, (1 << 63) - 1, 1 << 63, (1 << 64) - 1):
        fp = image_fingerprint.Fingerprint("x", value, 1, 1)
        assert -(1 << 63) <= fp.dhash_signed < (1 << 63)
        assert image_fingerprint.from_signed(fp.dhash_signed) == value


# --- on a real database: upload, publish, flag -------------------------------------------------

class _Bucket:
    def __init__(self, uploads):
        self.uploads = uploads

    def upload(self, path, data, options):
        self.uploads.append(path)

    def get_public_url(self, path):
        base = (settings.supabase_url or "https://test.supabase.co").rstrip("/")
        return f"{base}/storage/v1/object/public/{storage.REVIEW_BUCKET}/{path}"


class _Client:
    def __init__(self, uploads):
        self.storage = type("S", (), {"from_": lambda _self, bucket: _Bucket(uploads)})()


@pytest.fixture
def uploads(monkeypatch) -> list:
    recorded: list = []
    monkeypatch.setattr(storage, "get_service_client", lambda: _Client(recorded))
    return recorded


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers, data: bytes):
    return client.post("/api/v1/reviews/photo", headers=headers,
                       files={"file": ("photo.jpg", data, "image/jpeg")})


def _review(client, headers, photo_url: str | None, label: str) -> str:
    pid = client.post("/api/v1/products", headers=headers, json={
        "name": f"{label} {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
    body = {"product_id": pid, "title": label, "discussion": unique_text(label),
            "verdict": "yes_absolutely", "star_rating": 4}
    if photo_url:
        body["photo_url"] = photo_url
    res = client.post("/api/v1/reviews", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _photo_reports(client, admin, rid: str) -> list[dict]:
    return [i for i in all_report_queue_items(client, admin)
            if i["report"]["target_ref"] == rid and i["origin"] == "system_detected"
            and (i.get("explanation") or {}).get("signal") == "duplicate_image"]


@requires_db
def test_a_resized_copy_of_another_reviews_photo_is_flagged_and_stays_published(client, uploads):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    seed = random.randint(10_000, 10_000_000)
    original_photo = _photo(seed)
    first = _upload(client, _auth(a), _jpeg(original_photo))
    assert first.status_code == 200, first.text
    original = _review(client, _auth(a), first.json()["url"], "Original photo")
    w, h = original_photo.size
    copy_upload = _upload(client, _auth(b), _jpeg(original_photo.resize((w // 2, h // 2)), 60))
    assert copy_upload.status_code == 200
    copy = _review(client, _auth(b), copy_upload.json()["url"], "Borrowed photo")

    [item] = _photo_reports(client, _auth(admin), copy)
    why = item["explanation"]
    assert why["summary"].startswith("Possible reused photo")
    lines = {e["label"]: e for e in why["evidence"]}
    assert lines["Matching review"]["link"] == f"/reviews/{original}"
    assert lines["Check"]["value"] == "dhash64-v1"
    assert client.get(f"/api/v1/reviews/{copy}").status_code == 200    # still published
    assert _photo_reports(client, _auth(admin), original) == []        # the source is not flagged


@requires_db
def test_the_same_file_again_is_flagged_as_identical(client, uploads):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    data = _jpeg(_photo(random.randint(10_000, 10_000_000)))
    first = _review(client, _auth(a), _upload(client, _auth(a), data).json()["url"], "First")
    second = _review(client, _auth(b), _upload(client, _auth(b), data).json()["url"], "Second")
    [item] = _photo_reports(client, _auth(admin), second)
    assert "identical file" in item["explanation"]["summary"]
    assert {e["label"]: e for e in item["explanation"]["evidence"]}[
        "Matching review"]["link"] == f"/reviews/{first}"


def _backdate(review_id: str, *, days: int) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.session import SessionLocal
    from app.models.review import Review
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(review_id))
        review.created_at = review.published_at = datetime.now(UTC) - timedelta(days=days)
        db.commit()
    finally:
        db.close()


@requires_db
def test_an_update_keeping_its_own_threads_photo_is_not_a_copy(client, uploads):
    """§4: a dated update restates the same purchase; its photo is its own."""
    _, a, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    data = _jpeg(_photo(random.randint(10_000, 10_000_000)))
    photo = _upload(client, _auth(a), data).json()["url"]
    root = _review(client, _auth(a), photo, "Own photo")
    _backdate(root, days=95)
    update = client.post(f"/api/v1/reviews/{root}/updates", headers=_auth(a), json={
        "title": "Three months on", "discussion": unique_text("Three months on"),
        "verdict": "yes_absolutely", "star_rating": 4, "photo_url": photo})
    assert update.status_code == 201, update.text
    assert _photo_reports(client, _auth(admin), update.json()["id"]) == []


@requires_db
def test_one_members_photo_on_a_second_products_review_is_flagged(client, uploads):
    _, a, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    data = _jpeg(_photo(random.randint(10_000, 10_000_000)))
    photo = _upload(client, _auth(a), data).json()["url"]
    first = _review(client, _auth(a), photo, "First product")
    second = _review(client, _auth(a), photo, "Second product")
    [item] = _photo_reports(client, _auth(admin), second)
    assert "identical file" in item["explanation"]["summary"]
    assert {e["label"]: e for e in item["explanation"]["evidence"]}[
        "Matching review"]["link"] == f"/reviews/{first}"


@requires_db
def test_an_unrelated_photo_is_not_flagged(client, uploads):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _review(client, _auth(a), _upload(client, _auth(a), _jpeg(_photo(
        random.randint(10_000, 10_000_000)))).json()["url"], "Mine")
    other = _review(client, _auth(b), _upload(client, _auth(b), _jpeg(_photo(
        random.randint(10_000, 10_000_000)))).json()["url"], "Theirs")
    assert _photo_reports(client, _auth(admin), other) == []


@requires_db
def test_a_corrupt_upload_is_refused_and_never_stored(client, uploads):
    _, a, _ = register_and_token(client)
    res = _upload(client, _auth(a), b"\xff\xd8\xff" + b"not really a jpeg" * 50)
    assert res.status_code == 415
    assert res.json()["code"] == "unreadable_image"
    assert uploads == []


@requires_db
def test_no_reverse_image_provider_is_reported_honestly_and_blocks_nothing(client, uploads):
    _, a, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    rid = _review(client, _auth(a), _upload(client, _auth(a), _jpeg(_photo(
        random.randint(10_000, 10_000_000)))).json()["url"], "Reverse check")
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200
    providers = client.get("/api/v1/admin/integrity-providers", headers=_auth(admin))
    assert providers.status_code == 200, providers.text
    reverse = providers.json()["reverse_image"]
    assert reverse["configured"] is False and reverse["provider"] is None
    assert "No reverse image provider is configured" in reverse["detail"]


@requires_db
def test_a_failed_photo_check_never_blocks_publication(client, uploads, monkeypatch):
    from app.services import duplicate_images

    def broken(*_args, **_kwargs):
        raise RuntimeError("the fingerprint table is unreachable")

    monkeypatch.setattr(duplicate_images, "review_image_duplicate", broken)
    _, a, _ = register_and_token(client)
    rid = _review(client, _auth(a), _upload(client, _auth(a), _jpeg(_photo(
        random.randint(10_000, 10_000_000)))).json()["url"], "Resilient")
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200

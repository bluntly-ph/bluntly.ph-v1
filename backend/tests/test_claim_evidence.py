"""A file sent as evidence on a store claim (owner report 2026-10-04: "uploading
files as evidence when claiming a Seller results in an error").

Root cause (production storage log, 2026-10-04 13:54-14:28 UTC): every upload went
to `/object/message-attachments/...` and Supabase Storage answered 400 - the
private bucket had never been created. Migration 0086 creates it. These tests pin
the parts that hid it and the guarantees around it:

* the bucket the code writes to is one the migration provisions, private;
* a storage failure is a clear 503 and writes no conversation or message row;
* a message that fails to save after its file was stored removes the object;
* a claimant's evidence lands on the claim's ONE thread, the one the reviewer's
  case window reads, even when the claimant starts it from Messages;
* only the claimant and staff can see it; bad types and sizes are refused.

Storage itself is faked here (CI has no bucket); `test_real_bucket_round_trip`
puts a real object in the TEST project's bucket when credentials exist.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.conftest import claim_body, register_and_token, requires_db, requires_storage

_MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
              / "0086_storage_buckets.py")

PDF = b"%PDF-1.7\n" + b"0" * 256
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _migration():
    spec = importlib.util.spec_from_file_location("m0086", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class _Bucket:
    def __init__(self, store: FakeStorage, name: str):
        self.store, self.name = store, name

    def upload(self, key, data, options):
        if self.name not in self.store.buckets:
            # What Supabase Storage answers for a bucket that does not exist.
            raise RuntimeError("Bucket not found")
        self.store.objects[(self.name, key)] = (data, options["content-type"])

    def remove(self, keys):
        for key in keys:
            self.store.removed.append(key)
            self.store.objects.pop((self.name, key), None)

    def create_signed_url(self, key, expires_in, options=None):
        if (self.name, key) not in self.store.objects:
            raise RuntimeError("Object not found")
        return {"signedURL": f"https://storage.example/sign/{self.name}/{key}"}


class FakeStorage:
    """Just enough of the Supabase client for storage.py."""

    def __init__(self, buckets=("message-attachments",)):
        self.buckets = set(buckets)
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.removed: list[str] = []
        self.storage = self

    def from_(self, name):
        return _Bucket(self, name)


@pytest.fixture
def fake_storage(monkeypatch):
    from app.services import storage
    fake = FakeStorage()
    monkeypatch.setattr(storage, "get_service_client", lambda: fake)
    from app.adapters import email as email_adapter
    monkeypatch.setattr(email_adapter, "send_email", lambda *a, **k: None)
    return fake


def _claim(client) -> tuple[dict, dict, str, str]:
    """(claimant headers, staff headers, claim id, store id)."""
    _, claimant, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(claimant), json={
        "display_name": f"Evidence Co {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(claimant),
                        json=claim_body(shop_name=store["display_name"]))
    assert claim.status_code == 201, claim.text
    return _auth(claimant), _auth(staff), claim.json()["id"], store["id"]


def _start_claim_thread(client, headers, claim_id, store_id, *, file=None, body="Our DTI."):
    return client.post("/api/v1/conversations", headers=headers, data={
        "audience": "seller", "topic": "claim", "body": body, "seller_id": store_id,
        "link_type": "claim", "link_id": claim_id},
        files={"file": file} if file else None)


def _rows(conversation_id: str) -> tuple[int, int]:
    """(messages, messages with a file) stored for a conversation."""
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        return tuple(db.execute(text(
            "SELECT count(*), count(attachment_key) FROM conversation_messages "
            "WHERE conversation_id = :c AND kind = 'message'"), {"c": conversation_id}).one())


# ---------------------------------------------------------------- the bucket

def test_every_bucket_the_code_writes_to_is_provisioned_by_0086():
    from app.services import storage
    spec = {b[0]: b for b in _migration().BUCKETS}
    assert set(spec) == set(storage.BUCKETS)
    for name, public in storage.BUCKETS.items():
        assert spec[name][1] is public, name
    _, public, limit, mimes = spec[storage.MESSAGE_BUCKET]
    assert public is False
    assert limit >= storage.MAX_ATTACHMENT_BYTES
    # Every type validate_attachment accepts is one the bucket accepts.
    for sample in (PDF, PNG, b"\xff\xd8\xff" + b"0" * 8, b"RIFF0000WEBP"):
        assert storage.sniff_attachment_type(sample) in mimes


@requires_db
def test_0086_creates_the_missing_bucket_and_never_changes_an_existing_one():
    from app.db.session import engine
    sql = _migration().BUCKETS_SQL
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            real = conn.execute(text("SELECT to_regclass('storage.buckets')")).scalar()
            if real is None:
                # A plain Postgres: the statement is a no-op, then a stand-in
                # storage.buckets with one bucket configured by hand.
                conn.execute(text(sql))
                conn.execute(text(
                    "CREATE SCHEMA storage; CREATE TABLE storage.buckets (id text PRIMARY KEY,"
                    " name text, public boolean, file_size_limit bigint,"
                    " allowed_mime_types text[]);"
                    "INSERT INTO storage.buckets VALUES ('avatars', 'avatars', true, 1, NULL)"))
            conn.execute(text(sql))
            rows = {r.id: r for r in conn.execute(text(
                "SELECT id, public, file_size_limit, allowed_mime_types FROM storage.buckets"))}
            assert rows["message-attachments"].public is False
            assert "application/pdf" in rows["message-attachments"].allowed_mime_types
            assert rows["review-receipts"].public is False
            if real is None:
                assert rows["avatars"].file_size_limit == 1  # left as it was
        finally:
            trans.rollback()


# ---------------------------------------------------------------- the flow

@requires_db
def test_claimant_evidence_reaches_the_claim_review_and_nobody_else(client, fake_storage):
    claimant, staff, claim_id, store_id = _claim(client)
    other_seller = _auth(register_and_token(client)[1])

    # Started from Messages, with a file: it is the claim's own thread.
    r = _start_claim_thread(client, claimant, claim_id, store_id,
                            file=("DTI_certificate.pdf", PDF, "application/pdf"))
    assert r.status_code == 201, r.text
    conv = r.json()
    assert conv["messages"][-1]["attachment"]["name"] == "DTI_certificate.pdf"
    assert len(fake_storage.objects) == 1
    case_url = f"/api/v1/cases/claim/{claim_id}/messages"
    evidence = client.get(case_url, headers=staff).json()
    assert evidence[-1]["attachment"]["type"] == "application/pdf"
    href = "/api/v1" + evidence[-1]["attachment"]["href"].removeprefix("/api/v1")
    assert client.get(href, headers=staff).json()["url"].startswith("https://storage.example/")
    assert client.get(href, headers=claimant).status_code == 200

    # Staff asks for more on the case; the claimant answers with a photo.
    assert client.post(case_url, headers=staff,
                       json={"body": "Can you add the shop's seller page?"}).status_code == 201
    r = client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=claimant,
                    data={"body": "Screenshot of the seller centre."},
                    files={"file": ("centre.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    files = [m["attachment"]["name"] for m in client.get(case_url, headers=staff).json()
             if m["attachment"]]
    assert files == ["DTI_certificate.pdf", "centre.png"]

    # A second start from Messages does not open a second thread.
    again = _start_claim_thread(client, claimant, claim_id, store_id, body="One more thing.")
    assert again.status_code == 201 and again.json()["id"] == conv["id"]

    # Another seller: not their claim, not their thread, not their file.
    assert client.get(case_url, headers=other_seller).status_code == 403
    assert client.get(f"/api/v1/conversations/{conv['id']}",
                      headers=other_seller).status_code == 404
    assert client.get(href, headers=other_seller).status_code == 404
    assert client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=other_seller,
                       data={"body": "Mine now."},
                       files={"file": ("x.pdf", PDF, "application/pdf")}).status_code == 404
    assert _start_claim_thread(client, other_seller, claim_id, store_id).status_code == 404
    assert len(fake_storage.objects) == 2


@requires_db
def test_a_wrong_type_or_an_oversized_file_is_refused_and_stores_nothing(client, fake_storage):
    from app.services import storage
    claimant, _, claim_id, store_id = _claim(client)
    conv = _start_claim_thread(client, claimant, claim_id, store_id).json()
    url = f"/api/v1/conversations/{conv['id']}/messages"

    html = client.post(url, headers=claimant, data={"body": "See this."},
                       files={"file": ("dti.pdf", b"<html><script>x</script>", "application/pdf")})
    assert html.status_code == 415 and html.json()["code"] == "unsupported_media_type"
    big = client.post(url, headers=claimant, data={"body": "Big scan."},
                      files={"file": ("scan.pdf", b"%PDF-" + b"0" * storage.MAX_ATTACHMENT_BYTES,
                                      "application/pdf")})
    assert big.status_code == 413 and big.json()["code"] == "file_too_large"
    assert fake_storage.objects == {}
    assert _rows(conv["id"]) == (1, 0)


@requires_db
def test_a_missing_bucket_is_a_clear_503_and_writes_no_row(client, fake_storage):
    """The production failure, reproduced: the bucket does not exist."""
    from app.db.session import SessionLocal
    from app.models.conversation import Conversation
    fake_storage.buckets.clear()
    claimant, _, claim_id, store_id = _claim(client)

    r = _start_claim_thread(client, claimant, claim_id, store_id,
                            file=("DTI.pdf", PDF, "application/pdf"))
    assert r.status_code == 503 and r.json()["code"] == "attachments_unavailable"
    with SessionLocal() as db:
        assert db.query(Conversation).filter(Conversation.link_id == uuid.UUID(claim_id)) \
            .count() == 0
    conv = _start_claim_thread(client, claimant, claim_id, store_id).json()
    r = client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=claimant,
                    data={"body": "With the file."},
                    files={"file": ("DTI.pdf", PDF, "application/pdf")})
    assert r.status_code == 503
    assert _rows(conv["id"]) == (1, 0)

    fake_storage.buckets.add("message-attachments")  # what 0086 does
    r = client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=claimant,
                    data={"body": "With the file."},
                    files={"file": ("DTI.pdf", PDF, "application/pdf")})
    assert r.status_code == 201
    assert _rows(conv["id"]) == (2, 1)


@requires_db
def test_a_message_that_fails_to_save_removes_its_uploaded_file(client, fake_storage,
                                                                 monkeypatch):
    from sqlalchemy.orm import Session

    from app.services import conversation_service
    claimant, staff, claim_id, store_id = _claim(client)
    conv = _start_claim_thread(client, claimant, claim_id, store_id).json()

    # Member reply: the commit fails after the file is stored.
    real_commit = Session.commit

    def failing_commit(self):
        if fake_storage.objects:
            raise RuntimeError("database went away")
        return real_commit(self)

    monkeypatch.setattr(Session, "commit", failing_commit)
    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=claimant,
                    data={"body": "Evidence."},
                    files={"file": ("DTI.pdf", PDF, "application/pdf")})
    monkeypatch.setattr(Session, "commit", real_commit)
    assert fake_storage.objects == {} and len(fake_storage.removed) == 1
    assert _rows(conv["id"]) == (1, 0)

    # Staff reply: something between the upload and the commit fails.
    def boom(*args, **kwargs):
        raise RuntimeError("notification failed")

    monkeypatch.setattr(conversation_service, "_tell_member", boom)
    with pytest.raises(RuntimeError):
        client.post(f"/api/v1/admin/inbox/{conv['id']}/messages", headers=staff,
                    data={"body": "Here is the form."},
                    files={"file": ("form.pdf", PDF, "application/pdf")})
    assert fake_storage.objects == {} and len(fake_storage.removed) == 2
    assert _rows(conv["id"]) == (1, 0)


# ---------------------------------------------------------------- real storage

@requires_db
@requires_storage
def test_real_bucket_round_trip(client):
    """A real object in the project's private bucket: the check that would have
    caught the missing bucket. Removes what it uploads."""
    from app.services import storage
    key, mime = storage.upload_attachment(uuid.uuid4(), PDF)
    try:
        assert mime == "application/pdf"
        url = storage.signed_attachment_url(key, 60)
        assert url and url.startswith("http")
    finally:
        storage.delete_attachment_objects([key])

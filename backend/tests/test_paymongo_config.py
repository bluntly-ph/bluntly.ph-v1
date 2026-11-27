"""PayMongo configuration (Figma Overlay/Settings/ConnectPayMongo 8237:25540;
Backend Proposal "PayMongo integration"; migration 0080). Saving keys moves no
money: there is no payout path that uses them."""

from __future__ import annotations

import uuid

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from tests.conftest import register_and_token, requires_db

pytestmark = requires_db

URL = "/api/v1/admin/integrations/paymongo"


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def key(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "integration_secrets_key", Fernet.generate_key().decode())
    yield
    from app.db.session import SessionLocal
    from app.models.triage import PlatformSetting
    db = SessionLocal()
    try:
        row = db.get(PlatformSetting, "integration:paymongo")
        if row is not None:
            db.delete(row)
            db.commit()
    finally:
        db.close()


def test_without_a_storage_key_nothing_is_saved(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "integration_secrets_key", "")
    _, sup, _ = register_and_token(client, role="super_admin")
    assert client.get(URL, headers=_h(sup)).json()["storage_ready"] is False
    res = client.put(URL, headers=_h(sup), json={
        "public_key": "pk_test_abcdefgh", "secret_key": "sk_test_abcdefgh1234",
        "methods": ["gcash"], "test_mode": True})
    assert res.status_code == 503 and res.json()["code"] == "secret_storage_unavailable"


def test_super_admin_saves_tests_and_removes_keys(client, db, key):
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    from app.models.triage import PlatformSetting
    from app.services import paymongo_config

    _, admin, _ = register_and_token(client, role="administrator")
    sup_id, sup, _ = register_and_token(client, role="super_admin")
    body = {"public_key": "pk_test_abcdefgh", "secret_key": "sk_test_secretvalue1234",
            "methods": ["gcash", "maya"], "test_mode": True}
    assert client.put(URL, headers=_h(admin), json=body).status_code == 403
    assert client.get(URL, headers=_h(admin)).json()["connected"] is False

    # Keys must match the mode.
    live = client.put(URL, headers=_h(sup), json={**body, "public_key": "pk_live_abcdefgh"})
    assert live.status_code == 422 and live.json()["code"] == "public_key_mode"
    assert client.put(URL, headers=_h(sup), json={**body, "methods": []}).status_code == 422

    saved = client.put(URL, headers=_h(sup), json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()
    assert out["connected"] and out["secret_hint"] == "sk_test_…1234"
    assert out["methods"] == ["gcash", "maya"] and out["payouts_enabled"] is False
    assert "secretvalue" not in saved.text
    db.expire_all()
    stored = db.get(PlatformSetting, "integration:paymongo").value
    assert "sk_test_secretvalue1234" not in str(stored)        # encrypted at rest
    # An admin reads the state (never the key); a re-save may keep the secret.
    assert client.get(URL, headers=_h(admin)).json()["secret_hint"] == "sk_test_…1234"
    assert client.put(URL, headers=_h(sup), json={**body, "secret_key": None,
                                                  "methods": ["bank"]}).status_code == 200

    # The connection test is one read-only call; PayMongo answers through a stub.
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"data": []})

    from app.db.session import SessionLocal
    from app.models.user import User
    with SessionLocal() as s:
        stub = httpx.MockTransport(handler)
        result = paymongo_config.test_connection(s, s.get(User, uuid.UUID(sup_id)),
                                                 transport=stub)
    assert result.last_test and result.last_test.ok
    assert calls == [("GET", "/v1/payments")]

    settings_view = client.get("/api/v1/admin/settings", headers=_h(admin)).json()
    pm = next(i for i in settings_view["integrations"] if i["key"] == "paymongo")
    assert pm["status"] == "connected" and "Payouts stay manual" in pm["detail"]

    def refused(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": []})

    with SessionLocal() as s:
        result = paymongo_config.test_connection(s, s.get(User, uuid.UUID(sup_id)),
                                                 transport=httpx.MockTransport(refused))
    assert result.last_test and not result.last_test.ok
    assert result.last_test.detail == "PayMongo refused the key."
    settings_view = client.get("/api/v1/admin/settings", headers=_h(admin)).json()
    pm = next(i for i in settings_view["integrations"] if i["key"] == "paymongo")
    assert pm["status"] == "not_connected" and "last test failed" in pm["detail"]

    assert client.delete(URL, headers=_h(admin)).status_code == 403
    assert client.delete(URL, headers=_h(sup)).json()["connected"] is False
    db.expire_all()
    notes = [log.notes for log in db.scalars(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.integration_change,
        ModerationLog.moderator_id == uuid.UUID(sup_id)))]
    assert "PayMongo keys removed" in notes and any("saved" in n for n in notes)
    assert all("sk_test" not in n for n in notes)

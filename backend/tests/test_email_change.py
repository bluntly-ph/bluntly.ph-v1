"""A verified change of the address a member signs in with (0084, owner decision 2026-10-04).

Both ends are proven (a code to the current address, one to the new), nothing changes
until both are right, every other session ends, the old address is told, and the
endpoint never says whether an address is taken to anyone who hasn't proved they
own it.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.email_change import EmailChangeRequest
from app.models.user import User
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db
URL = "/api/v1/users/me/email-change"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def outbox(monkeypatch):
    """Every email the change flow sends: (to, subject, text)."""
    sent: list[tuple[str, str, str]] = []
    from app.services import email_change_service

    monkeypatch.setattr(email_change_service, "send_email",
                        lambda to, subject, text, html=None: sent.append((to, subject, text)))
    return sent


def _code(sent, to: str) -> str:
    text = next(t for (addr, _, t) in reversed(sent) if addr == to)
    return re.search(r"Your code: (\d{6})", text).group(1)


def _old_token(user_id: str) -> str:
    """A token issued a minute ago, as an already signed-in browser holds."""
    now = datetime.now(UTC) - timedelta(minutes=1)
    return jwt.encode({"sub": user_id, "role": "user", "iss": settings.jwt_issuer,
                       "iat": int(now.timestamp()),
                       "exp": int((now + timedelta(hours=1)).timestamp()), "type": "access"},
                      settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _new_address() -> str:
    return f"new_{uuid.uuid4().hex[:10]}@example.com"


def test_a_change_needs_both_codes_ends_other_sessions_and_tells_the_old_address(
        client, outbox):
    uid, token, old_email = register_and_token(client)
    other_browser = _old_token(uid)
    new_email = _new_address()

    started = client.post(URL, headers=_auth(token), json={"new_email": new_email.upper()})
    assert started.status_code == 202, started.text
    assert started.json()["new_email"] == new_email
    assert {to for to, _, _ in outbox} == {old_email, new_email}
    assert client.get(URL, headers=_auth(token)).json()["new_email"] == new_email
    with SessionLocal() as s:
        row = s.scalar(select(EmailChangeRequest).where(
            EmailChangeRequest.user_id == uuid.UUID(uid)))
        current, new = _code(outbox, old_email), _code(outbox, new_email)
        assert current not in row.current_code_hash and new not in row.new_code_hash
        assert s.get(User, uuid.UUID(uid)).email == old_email   # nothing changed yet

    # One right code is not enough, and the reply doesn't say which one was wrong.
    bad = "000000" if new != "000000" else "111111"
    wrong = client.post(f"{URL}/confirm", headers=_auth(token),
                        json={"current_code": current, "new_code": bad})
    assert wrong.status_code == 409 and wrong.json()["code"] == "otp_invalid"

    done = client.post(f"{URL}/confirm", headers=_auth(token),
                       json={"current_code": current, "new_code": new})
    assert done.status_code == 200, done.text
    assert done.json()["email"] == new_email
    fresh = done.json()["access_token"]

    # This browser carries on with its fresh token; the others have to sign in again.
    assert client.get("/api/v1/auth/me", headers=_auth(fresh)).json()["email"] == new_email
    revoked = client.get("/api/v1/auth/me", headers=_auth(other_browser))
    assert revoked.status_code == 401 and revoked.json()["code"] == "session_revoked"
    # The old address is told, without the new one spelled out.
    notice = [(subject, text) for to, subject, text in outbox if to == old_email][-1]
    assert notice[0] == "Your bluntly sign-in email was changed"
    assert new_email not in notice[1] and "•••@example.com" in notice[1]
    notes = client.get("/api/v1/notifications", headers=_auth(fresh)).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n["kind"] == "account_email_changed" for n in items)
    # The codes are spent.
    spent = client.post(f"{URL}/confirm", headers=_auth(fresh),
                        json={"current_code": current, "new_code": new})
    assert spent.status_code == 409 and spent.json()["code"] == "otp_invalid"
    # Signing in with the new address works; with the old one it doesn't.
    login = "/api/v1/auth/login"
    assert client.post(login, data={"username": new_email, "password": "password123"}
                       ).status_code == 200
    assert client.post(login, data={"username": old_email, "password": "password123"}
                       ).status_code == 401


def test_a_taken_address_is_only_revealed_to_its_proven_owner(client, outbox):
    _, token, old_email = register_and_token(client)
    _, _, someone_else = register_and_token(client)
    # Starting does not say the address is taken (no probing which addresses exist).
    assert client.post(URL, headers=_auth(token), json={"new_email": someone_else}
                       ).status_code == 202
    done = client.post(f"{URL}/confirm", headers=_auth(token), json={
        "current_code": _code(outbox, old_email), "new_code": _code(outbox, someone_else)})
    assert done.status_code == 409 and done.json()["code"] == "email_taken"
    assert client.get("/api/v1/auth/me", headers=_auth(token)).json()["email"] == old_email


def test_guards_same_address_attempt_cap_supersede_cancel_and_no_cross_flow(client, outbox):
    _, token, old_email = register_and_token(client)
    same = client.post(URL, headers=_auth(token), json={"new_email": old_email.upper()})
    assert same.status_code == 422 and same.json()["code"] == "email_unchanged"
    assert client.post(URL, headers=_auth(token), json={"new_email": "not-an-address"}
                       ).status_code == 422
    assert client.post(URL, json={"new_email": _new_address()}).status_code == 401

    first = _new_address()
    client.post(URL, headers=_auth(token), json={"new_email": first})
    first_codes = (_code(outbox, old_email), _code(outbox, first))
    # A change code parked under the new address cannot sign anyone in (its own table).
    assert client.post("/api/v1/auth/otp/verify", json={"email": first, "code": first_codes[1]}
                       ).status_code in (401, 404, 409, 422)
    # A second request replaces the first: the first pair no longer works.
    second = _new_address()
    client.post(URL, headers=_auth(token), json={"new_email": second})
    stale = client.post(f"{URL}/confirm", headers=_auth(token),
                        json={"current_code": first_codes[0], "new_code": first_codes[1]})
    assert stale.status_code == 409 and stale.json()["code"] == "otp_invalid"
    # Wrong guesses are capped for the pair (the stale pair above was the first).
    codes = []
    for _ in range(settings.otp_max_attempts):
        codes.append(client.post(f"{URL}/confirm", headers=_auth(token), json={
            "current_code": "123456", "new_code": "654321"}).json()["code"])
    assert codes[-1] == "otp_attempts_exceeded"
    assert codes[:-1] == ["otp_invalid"] * (settings.otp_max_attempts - 1)
    # Once capped, even the right pair is refused: the request is spent.
    late = client.post(f"{URL}/confirm", headers=_auth(token), json={
        "current_code": _code(outbox, old_email), "new_code": _code(outbox, second)})
    assert late.status_code == 409 and late.json()["code"] == "otp_invalid"
    assert client.get("/api/v1/auth/me", headers=_auth(token)).json()["email"] == old_email
    # Cancel drops a pending change.
    client.post(URL, headers=_auth(token), json={"new_email": _new_address()})
    assert client.delete(URL, headers=_auth(token)).status_code == 204
    assert client.get(URL, headers=_auth(token)).json() is None


def test_a_failed_send_leaves_nothing_half_issued(client, monkeypatch):
    from app.adapters.email import EmailSendError
    from app.services import email_change_service

    def boom(*_a, **_k):
        raise EmailSendError("Resend rejected the send (HTTP 500)")

    monkeypatch.setattr(email_change_service, "send_email", boom)
    uid, token, _ = register_and_token(client)
    failed = client.post(URL, headers=_auth(token), json={"new_email": _new_address()})
    assert failed.status_code == 502, failed.text
    with SessionLocal() as s:
        assert s.scalar(select(EmailChangeRequest).where(
            EmailChangeRequest.user_id == uuid.UUID(uid))) is None

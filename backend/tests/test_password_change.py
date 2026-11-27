"""Overlay/Store/Account "Change password" (Backend Proposal item 28)."""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_change_password_needs_the_current_one_and_the_new_one_signs_in(client):
    _, token, email = register_and_token(client)   # registered with "password123"
    me = client.get("/api/v1/auth/me", headers=_h(token)).json()
    assert me["has_password"] is True and "password_hash" not in me
    url = "/api/v1/users/me/password"
    assert client.post(url, json={"current_password": "x", "new_password": "a" * 10}
                       ).status_code == 401
    wrong = client.post(url, headers=_h(token), json={
        "current_password": "nope-nope", "new_password": "longer-password-1"})
    assert wrong.status_code == 422 and wrong.json()["code"] == "current_password_wrong"
    short = client.post(url, headers=_h(token), json={
        "current_password": "password123", "new_password": "short1"})
    assert short.status_code == 422
    same = client.post(url, headers=_h(token), json={
        "current_password": "password123", "new_password": "password123"})
    # Under 10 characters is refused before "unchanged" is even considered.
    assert same.status_code == 422
    ok = client.post(url, headers=_h(token), json={
        "current_password": "password123", "new_password": "a-new-password-2026"})
    assert ok.status_code == 204, ok.text
    assert client.post("/api/v1/auth/login", data={
        "username": email, "password": "password123"}).status_code == 401
    assert client.post("/api/v1/auth/login", data={
        "username": email, "password": "a-new-password-2026"}).status_code == 200


def test_an_email_code_account_has_no_password_to_change(client, db):
    import uuid

    from app.models.user import User
    uid, token, _ = register_and_token(client)
    user = db.get(User, uuid.UUID(uid))
    user.password_hash = None
    db.commit()
    assert client.get("/api/v1/auth/me", headers=_h(token)).json()["has_password"] is False
    res = client.post("/api/v1/users/me/password", headers=_h(token), json={
        "current_password": "anything", "new_password": "a-new-password-2026"})
    assert res.status_code == 409 and res.json()["code"] == "no_password"

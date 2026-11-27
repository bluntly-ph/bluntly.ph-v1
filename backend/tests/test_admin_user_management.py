"""User management and the Super Admin role (owner decisions B-D, 2026-09-28).

The access matrix against the real API, the audit contract, the retired
moderator role, and the last-Super-Admin invariant — including two Super
Admins demoting each other at the same moment.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.session import SessionLocal, engine
from app.models.enums import MemberRole, ModerationAction
from app.models.moderation import ModerationLog
from app.models.user import User
from app.services import staff_roles
from tests.conftest import make_user, requires_db

pytestmark = requires_db


def _headers(user: User, claim: str | None = None) -> dict[str, str]:
    return {"Authorization":
            f"Bearer {create_access_token(user.id, claim or user.role.value)}"}


@pytest.fixture
def accounts(db):
    normal = make_user(db, display_name=f"Directory {uuid.uuid4().hex[:10]}",
                       username=f"target_{uuid.uuid4().hex[:8]}")
    admin = make_user(db, role=MemberRole.administrator, display_name="Administrator")
    super_admin = make_user(db, role=MemberRole.super_admin, display_name="Super Admin")
    other_super = make_user(db, role=MemberRole.super_admin, display_name="Second Super Admin")
    db.commit()
    ids = [normal.id, admin.id, super_admin.id, other_super.id]
    try:
        yield normal, admin, super_admin, other_super
    finally:
        db.rollback()
        db.query(ModerationLog).filter(
            (ModerationLog.target_ref.in_(ids)) | (ModerationLog.moderator_id.in_(ids))
        ).delete(synchronize_session=False)
        db.commit()


def _role(user_id) -> MemberRole:
    with SessionLocal() as s:
        return s.get(User, user_id).role


def _audits(target_id) -> list[ModerationLog]:
    with SessionLocal() as s:
        return list(s.scalars(select(ModerationLog).where(
            ModerationLog.target_ref == target_id,
            ModerationLog.action.in_((ModerationAction.role_grant,
                                      ModerationAction.role_revoke)))
            .order_by(ModerationLog.created_at)))


# ---------------------------------------------------------------- the matrix

def test_members_and_administrators_have_no_user_management(client, accounts):
    normal, admin, super_admin, _ = accounts
    for who in (normal, admin):
        found = client.get(f"/api/v1/admin/users?q={super_admin.staff_ref}",
                           headers=_headers(who))
        assert found.status_code == 403, who.role
        assert super_admin.staff_ref not in found.text
        for role in ("administrator", "super_admin", "user"):
            changed = client.patch(f"/api/v1/admin/users/{normal.id}/role",
                                   json={"role": role}, headers=_headers(who))
            assert changed.status_code == 403, (who.role, role)
        # The legacy membership endpoint is user management too.
        legacy = client.patch(f"/api/v1/users/{normal.id}/role", json={"role": "seller"},
                              headers=_headers(who))
        assert legacy.status_code == 403
    assert client.get("/api/v1/admin/users?q=x").status_code == 401
    assert _role(normal.id) == MemberRole.user


def test_a_role_claim_in_the_token_is_never_trusted(client, accounts):
    normal, admin, _, _ = accounts
    # A member's token claiming super_admin (or the retired moderator) gets nothing.
    for claim in ("super_admin", "administrator", "moderator"):
        assert client.get("/api/v1/admin/users?q=x",
                          headers=_headers(normal, claim)).status_code == 403
        assert client.get("/api/v1/admin/review-queue?limit=1",
                          headers=_headers(normal, claim)).status_code == 403
    # An administrator whose old token still says "moderator" keeps working:
    # authority is the database row, read on every request.
    assert client.get("/api/v1/admin/review-queue?limit=1",
                      headers=_headers(admin, "moderator")).status_code == 200


def test_the_super_admin_finds_people_with_their_email(client, accounts):
    normal, _, super_admin, _ = accounts
    found = client.get(f"/api/v1/admin/users?q={normal.staff_ref.lower()}",
                       headers=_headers(super_admin))
    assert found.status_code == 200
    body = found.json()
    assert body["can_manage_roles"] is True
    row = next(r for r in body["rows"] if r["id"] == str(normal.id))
    assert row["email"] == normal.email and row["role"] == "user"
    assert row["is_super_admin"] is False


# ------------------------------------------------------------- role changes

def test_promote_to_administrator_then_remove_it(client, accounts):
    normal, _, super_admin, _ = accounts
    granted = client.patch(f"/api/v1/admin/users/{normal.id}/role",
                           json={"role": "administrator"}, headers=_headers(super_admin))
    assert granted.status_code == 200, granted.text
    assert granted.json() | {"id": None} == {
        "id": None, "staff_ref": normal.staff_ref, "previous_role": "user",
        "role": "administrator", "changed": True, "detail": None}
    # The new administrator has staff access at once, and still no user management.
    assert client.get("/api/v1/admin/review-queue?limit=1",
                      headers=_headers(normal)).status_code == 200
    assert client.get("/api/v1/admin/users?q=x", headers=_headers(normal)).status_code == 403

    again = client.patch(f"/api/v1/admin/users/{normal.id}/role",
                         json={"role": "administrator"}, headers=_headers(super_admin))
    assert again.json()["changed"] is False  # a no-op, and no audit row for it

    removed = client.patch(f"/api/v1/admin/users/{normal.id}/role",
                           json={"role": "user"}, headers=_headers(super_admin))
    assert removed.status_code == 200 and removed.json()["role"] == "user"
    assert client.get("/api/v1/admin/review-queue?limit=1",
                      headers=_headers(normal)).status_code == 403

    audits = _audits(normal.id)
    assert [a.action for a in audits] == [ModerationAction.role_grant,
                                          ModerationAction.role_revoke]
    assert audits[0].moderator_id == super_admin.id
    assert audits[0].context | {"actor_staff_ref": None} == {
        "from": "user", "to": "administrator", "result": "succeeded",
        "actor_staff_ref": None, "target_staff_ref": normal.staff_ref}
    assert audits[1].context["from"] == "administrator" and audits[1].context["to"] == "user"
    # Never an email, a token or a password in the record.
    assert normal.email not in str([a.context for a in audits])


def test_super_admins_can_promote_and_demote_each_other(client, accounts):
    _, admin, super_admin, other_super = accounts
    up = client.patch(f"/api/v1/admin/users/{admin.id}/role", json={"role": "super_admin"},
                      headers=_headers(super_admin))
    assert up.status_code == 200 and up.json()["role"] == "super_admin"
    down = client.patch(f"/api/v1/admin/users/{other_super.id}/role",
                        json={"role": "administrator"}, headers=_headers(super_admin))
    assert down.status_code == 200 and down.json()["role"] == "administrator"
    # The demoted Super Admin loses user management on their next request.
    assert client.get("/api/v1/admin/users?q=x",
                      headers=_headers(other_super)).status_code == 403
    # A Super Admin may step down while another remains.
    step = client.patch(f"/api/v1/admin/users/{super_admin.id}/role",
                        json={"role": "administrator"}, headers=_headers(super_admin))
    assert step.status_code == 200


def test_what_the_role_endpoint_refuses(client, accounts, db):
    normal, _, super_admin, _ = accounts
    h = _headers(super_admin)
    # The retired role is not a value at all.
    assert client.patch(f"/api/v1/admin/users/{normal.id}/role", json={"role": "moderator"},
                        headers=h).status_code == 422
    # Seller belongs to the claim workflow.
    seller = client.patch(f"/api/v1/admin/users/{normal.id}/role", json={"role": "seller"},
                          headers=h)
    assert seller.status_code == 403 and seller.json()["code"] == "role_not_assignable"
    assert client.patch(f"/api/v1/admin/users/{uuid.uuid4()}/role",
                        json={"role": "administrator"}, headers=h).status_code == 404
    # §9: a claimed seller is never staff.
    store_owner = make_user(db, is_claimed_seller=True)
    db.commit()
    refused = client.patch(f"/api/v1/admin/users/{store_owner.id}/role",
                           json={"role": "administrator"}, headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "claimed_seller_cannot_be_staff"
    # And the legacy endpoint neither grants nor removes a staff role.
    assert client.patch(f"/api/v1/users/{normal.id}/role", json={"role": "administrator"},
                        headers=h).status_code == 422
    admin_row = accounts[1]
    assert client.patch(f"/api/v1/users/{admin_row.id}/role", json={"role": "user"},
                        headers=h).status_code == 403


# ---------------------------------------------------- the last Super Admin

@pytest.fixture
def isolated():
    """A session inside a transaction that is always rolled back.

    `commit()` inside only releases a savepoint, so a test can arrange "only
    one Super Admin is left" in a shared, long-lived database without leaving
    that state behind for anyone.
    """
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def _only_super_admin(session: Session) -> User:
    last = User(email=f"last_{uuid.uuid4().hex}@example.com", password_hash="x",
                role=MemberRole.super_admin, username=f"last_{uuid.uuid4().hex[:8]}")
    session.add(last)
    session.flush()
    session.execute(text("UPDATE users SET role = 'administrator' "
                         "WHERE role = 'super_admin' AND id <> :keep"), {"keep": last.id})
    return last


def test_the_last_super_admin_cannot_be_demoted(isolated):
    last = _only_super_admin(isolated)
    with pytest.raises(AppError) as refused:
        staff_roles.change_role(isolated, last, last.id, MemberRole.administrator)
    assert refused.value.code == "last_super_admin"
    assert isolated.get(User, last.id).role == MemberRole.super_admin


def test_the_database_refuses_it_too(isolated):
    """Migration 0067: whatever bypasses the service, the database says no."""
    last = _only_super_admin(isolated)
    for sql in ("UPDATE users SET role = 'user' WHERE id = :i",
                "UPDATE users SET is_suspended = true WHERE id = :i",
                "DELETE FROM users WHERE id = :i"):
        savepoint = isolated.begin_nested()
        with pytest.raises(Exception, match="last_super_admin"):
            isolated.execute(text(sql), {"i": last.id})
        savepoint.rollback()
    # Adding a second one first makes the demotion fine.
    second = User(email=f"second_{uuid.uuid4().hex}@example.com", password_hash="x",
                  role=MemberRole.super_admin)
    isolated.add(second)
    isolated.flush()
    isolated.execute(text("UPDATE users SET role = 'administrator' WHERE id = :i"),
                     {"i": last.id})


def test_two_super_admins_demoting_each_other_at_once_leave_one(db):
    """The race the invariant exists for: A demotes B while B demotes A."""
    a = make_user(db, role=MemberRole.super_admin)
    b = make_user(db, role=MemberRole.super_admin)
    db.commit()
    others = [row.id for row in db.execute(select(User.id).where(
        User.role == MemberRole.super_admin, User.id.not_in([a.id, b.id]))).all()]
    db.execute(text("UPDATE users SET role = 'administrator' WHERE id = ANY(:ids)"),
               {"ids": others})
    db.commit()
    try:
        barrier = threading.Barrier(2)
        outcomes: dict[str, str] = {}

        def demote(actor_id, target_id, key):
            with SessionLocal() as s:
                actor = s.get(User, actor_id)
                barrier.wait()
                try:
                    staff_roles.change_role(s, actor, target_id, MemberRole.administrator)
                    outcomes[key] = "demoted"
                except AppError as exc:
                    outcomes[key] = exc.code

        threads = [threading.Thread(target=demote, args=(a.id, b.id, "a_demotes_b")),
                   threading.Thread(target=demote, args=(b.id, a.id, "b_demotes_a"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert sorted(outcomes.values()) == ["demoted", "last_super_admin"], outcomes
        roles = {_role(a.id), _role(b.id)}
        assert roles == {MemberRole.super_admin, MemberRole.administrator}
    finally:
        db.execute(text("UPDATE users SET role = 'super_admin' WHERE id = ANY(:ids)"),
                   {"ids": others})
        db.commit()


# ------------------------------------------------------------- the bootstrap

def test_bootstrap_refuses_when_a_super_admin_exists(accounts, capsys):
    from scripts import bootstrap_super_admin as B
    normal = accounts[0]
    assert B.main(["--email", normal.email, "--apply"]) == 1
    assert "already exist" in capsys.readouterr().err
    assert _role(normal.id) == MemberRole.user


def test_bootstrap_makes_the_first_super_admin_and_audits_it(accounts, monkeypatch, capsys):
    from scripts import bootstrap_super_admin as B
    normal = accounts[0]
    monkeypatch.setattr(B, "active_super_admins", lambda db, lock=False: 0)
    assert B.main(["--staff-ref", normal.staff_ref]) == 0          # dry run
    assert _role(normal.id) == MemberRole.user
    assert B.main(["--staff-ref", normal.staff_ref, "--apply"]) == 0
    assert _role(normal.id) == MemberRole.super_admin
    audit = _audits(normal.id)[-1]
    assert audit.action == ModerationAction.role_grant and audit.moderator_id is None
    assert audit.context["event"] == "bootstrap" and audit.context["to"] == "super_admin"


def test_bootstrap_refuses_production_even_with_the_flag_missing(accounts, monkeypatch):
    from app.core import env_guard
    from scripts import bootstrap_super_admin as B
    monkeypatch.setattr(env_guard, "production_signals",
                        lambda extra=None: ["DATABASE_URL references the production project"])
    with pytest.raises(SystemExit):
        B.main(["--email", accounts[0].email, "--apply"])
    assert _role(accounts[0].id) == MemberRole.user

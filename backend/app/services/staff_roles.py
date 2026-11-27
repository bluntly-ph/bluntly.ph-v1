"""Staff role changes (owner decisions B-D, 2026-09-28).

Only a Super Admin changes roles, and only between these three:

    user  <->  administrator  <->  super_admin

`seller` is not reachable from here: a store owner's standing comes from an
approved claim (and a claimed seller can never hold a staff role — §9 says they
never earn, vote or moderate their own criticism). The legacy membership
endpoint, PATCH /users/{id}/role, keeps user <-> seller and refuses staff.

THE LAST-SUPER-ADMIN INVARIANT. At least one active (not suspended) Super Admin
always remains. Enforced twice:

  * here, for the API: every role change first takes one transaction-scoped
    advisory lock (the trigger's own key), then reads the target and counts
    the other Super Admins. Two Super Admins demoting each other at the same
    moment serialise on it, and the second sees the first's result;
  * in the database (migration 0067's trigger), for anything that bypasses this
    service — a script, a console, a future endpoint.

Every change is audited in the same transaction as the change itself:
`role_grant` when the new role outranks the old, `role_revoke` otherwise, with
who, whom, from and to. Never an email, a token or a password.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.models.enums import MemberRole, ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.user import User

#: The roles this surface moves an account between.
ASSIGNABLE_ROLES: tuple[MemberRole, ...] = (
    MemberRole.user, MemberRole.administrator, MemberRole.super_admin)

_RANK = {MemberRole.user: 0, MemberRole.seller: 0, MemberRole.administrator: 1,
         MemberRole.super_admin: 2}


def _conflict(message: str, code: str) -> AppError:
    return AppError(message, code=code, status_code=409, title="Conflicting state")


#: The same key migration 0067's trigger locks on, so the service and the
#: database guard serialise against each other as well as among themselves.
_INVARIANT_LOCK = "SELECT pg_advisory_xact_lock(hashtext('bluntly.users.last_super_admin'))"


def serialize_role_changes(db: Session) -> None:
    """Take the invariant's lock for the rest of this transaction.

    Before any row lock, always: locking the target row first and the Super
    Admin set second deadlocks when two Super Admins demote each other (each
    holds the row the other wants). One lock, taken first, has no order to get
    wrong — and role changes are rare enough that serialising them costs nothing.
    """
    db.execute(text(_INVARIANT_LOCK))


def active_super_admins(db: Session, *, lock: bool = False,
                        excluding: uuid.UUID | None = None) -> int:
    """Active Super Admins; with `lock`, after taking the invariant's lock.

    Under READ COMMITTED each statement reads a fresh snapshot, so a count
    taken after the lock sees whatever the previous holder committed.
    """
    if lock:
        serialize_role_changes(db)
    stmt = select(func.count(User.id)).where(
        User.role == MemberRole.super_admin, User.is_suspended.is_not(True))
    if excluding is not None:
        stmt = stmt.where(User.id != excluding)
    return db.scalar(stmt) or 0


def audit_role_change(db: Session, actor: User | None, target: User, previous: MemberRole,
                      new: MemberRole, *, event: str | None = None) -> None:
    granting = _RANK[new] > _RANK[previous]
    context = {"from": previous.value, "to": new.value, "result": "succeeded",
               "actor_staff_ref": actor.staff_ref if actor is not None else None,
               "target_staff_ref": target.staff_ref}
    if event:
        context["event"] = event
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", target_type=ModerationTargetType.user,
        target_ref=target.id, moderator_id=actor.id if actor is not None else None,
        action=ModerationAction.role_grant if granting else ModerationAction.role_revoke,
        notes=f"role {previous.value} -> {new.value}", context=context))


def change_role(db: Session, actor: User, target_id: uuid.UUID,
                new_role: MemberRole) -> tuple[User, MemberRole, bool]:
    """Move `target_id` to `new_role`. Returns (target, previous role, changed).

    Commits. The caller has already established that `actor` is a Super Admin;
    this re-checks nothing about the actor except that they are not trying to
    remove the last Super Admin — themselves included.
    """
    if new_role not in ASSIGNABLE_ROLES:
        raise ForbiddenError(
            "Only user, administrator and super_admin are assigned here.",
            code="role_not_assignable",
            extra={"assignable": [r.value for r in ASSIGNABLE_ROLES]})

    serialize_role_changes(db)
    target = db.scalar(select(User).where(User.id == target_id).with_for_update()
                       .execution_options(populate_existing=True))
    if target is None:
        raise NotFoundError("User not found.", code="user_not_found")
    previous = target.role
    if previous not in ASSIGNABLE_ROLES:
        raise ForbiddenError(
            f"This account's role is '{previous.value}' and is not managed here.",
            code="role_not_managed_here", extra={"actual": previous.value})
    if previous == new_role:
        return target, previous, False
    if new_role != MemberRole.user and bool(getattr(target, "is_claimed_seller", False)):
        # §9: a store's approved owner can never moderate, approve or route.
        raise _conflict("A claimed seller's account can't hold a staff role.",
                        "claimed_seller_cannot_be_staff")

    if previous == MemberRole.super_admin \
            and active_super_admins(db, excluding=target.id) == 0:
        raise _conflict("This is the last Super Admin. Make another account a Super Admin "
                        "first.", "last_super_admin")

    target.role = new_role
    audit_role_change(db, actor, target, previous, new_role)
    try:
        db.commit()
    except DBAPIError as exc:
        # The database's own guard (0067) — reached only if the check above
        # was bypassed. Same answer, never a 500.
        db.rollback()
        if "last_super_admin" in str(exc.orig):
            raise _conflict("This is the last Super Admin. Make another account a Super "
                            "Admin first.", "last_super_admin") from None
        raise
    db.refresh(target)
    return target, previous, True

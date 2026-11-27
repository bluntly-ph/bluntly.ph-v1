"""User management: Super Admin only (owner decisions C and D, 2026-09-28).

    GET   /admin/users                  find an account (staff ref, id, email, name)
    PATCH /admin/users/{user_id}/role   user <-> administrator <-> super_admin

An Administrator gets 403 from both, whatever the UI shows: user management is
not an operational approval, and an Administrator who could promote would make
the role self-propagating. Administrators still browse reviewers through
GET /admin/reviewers, an operational queue.

Role changes, the last-Super-Admin invariant and their audit records live in
app/services/staff_roles.py, shared with scripts/bootstrap_super_admin.py.
Authorization is re-derived from the database on every request; the UI hides
what a caller may not do, but nothing here trusts that.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import require_super_admin
from app.db.session import get_db
from app.models.enums import MemberRole
from app.models.user import User
from app.schemas.admin_users import (
    RoleChangeIn,
    RoleChangeResult,
    StaffUserPage,
    StaffUserRow,
)
from app.services import staff_roles
from app.services.staff_directory_service import normalise_staff_ref, search_users

log = get_logger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin: users"])


@router.get("", response_model=StaffUserPage,
            summary="Find an account by staff reference, id, email or name (Super Admin)")
def search(
    q: str = Query(default="", max_length=320,
                   description="Staff ref (USR-000123), UUID, exact email, or name"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
) -> StaffUserPage:
    """Lookup, not enumeration: an empty query returns nothing."""
    rows, total = search_users(db, q, limit=limit, offset=offset)
    return StaffUserPage(
        total=total,
        resolved_staff_ref=normalise_staff_ref(q),
        can_manage_roles=True,
        rows=[
            StaffUserRow(
                id=u.id,
                staff_ref=u.staff_ref,
                display_name=u.display_name,
                username=u.username,
                role=u.role,
                is_suspended=u.is_suspended,
                trust_stage=u.trust_stage,
                created_at=u.created_at,
                email=u.email,
                is_super_admin=u.role == MemberRole.super_admin,
                is_under_investigation=bool(u.is_under_investigation),
                is_claimed_seller=bool(u.is_claimed_seller),
            )
            for u in rows
        ],
    )


@router.patch("/{user_id}/role", response_model=RoleChangeResult,
              summary="Assign user, administrator or super_admin (Super Admin)")
def set_role(
    user_id: uuid.UUID,
    payload: RoleChangeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_super_admin),
) -> RoleChangeResult:
    """The change and its audit record commit together, or neither does."""
    target, previous, changed = staff_roles.change_role(db, actor, user_id, payload.role)
    if not changed:
        # Not an error and not an audit entry: nothing changed.
        return RoleChangeResult(id=target.id, staff_ref=target.staff_ref,
                                previous_role=previous, role=previous, changed=False,
                                detail="already in that role")
    log.info("staff role change", extra={"extra_fields": {
        "from": previous.value, "to": target.role.value}})
    return RoleChangeResult(id=target.id, staff_ref=target.staff_ref,
                            previous_role=previous, role=target.role, changed=True)

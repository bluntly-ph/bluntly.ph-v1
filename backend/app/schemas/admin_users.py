"""Staff user administration payloads.

These are the ONLY schemas in the codebase that carry `staff_ref`, and they are
reachable only behind require_staff / require_super_admin. Every
public schema — UserOut, FeedAuthor, ReviewerRow and the rest — is an
allow-list of declared fields, so adding a column to the User model does not
leak into them; `tests/test_staff_ref_privacy.py` asserts that rather than
trusting it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MemberRole


class StaffUserRow(BaseModel):
    """One account, as staff see it.

    Carries identity and standing, and deliberately not: password hash,
    wallet balance, payout account, tokens, session data or anything about
    authentication. Finding a person does not need their money.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    staff_ref: str | None = None
    display_name: str | None = None
    username: str | None = None
    role: MemberRole
    is_suspended: bool
    trust_stage: int
    created_at: datetime
    #: Only ever filled for a Super Admin caller (the one route that returns
    #: this schema requires one).
    email: str | None = None
    #: `role == super_admin`, kept as its own field for the console's badge.
    is_super_admin: bool = False
    #: Business Rules §11: an administrator-set flag that halves vote weight.
    is_under_investigation: bool = False
    #: §9: an approved store owner — no earning, no vote weight.
    is_claimed_seller: bool = False


class StaffUserPage(BaseModel):
    rows: list[StaffUserRow] = Field(default_factory=list)
    total: int = 0
    #: Echoed back so the UI can show what was actually searched for after
    #: normalisation — "123" resolving to USR-000123 is otherwise invisible.
    resolved_staff_ref: str | None = None
    #: Derived from the freshly loaded database row, never a token or a
    #: client-supplied role. The UI uses it only to hide controls the PATCH
    #: endpoint independently refuses.
    can_manage_roles: bool = False


class RoleChangeIn(BaseModel):
    """user, administrator or super_admin. `seller` is refused (403)."""

    role: MemberRole


class RoleChangeResult(BaseModel):
    id: uuid.UUID
    staff_ref: str | None = None
    previous_role: MemberRole
    role: MemberRole
    changed: bool
    detail: str | None = None

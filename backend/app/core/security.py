"""Authentication & RBAC — FastAPI-native JWT/OAuth2 (ADR-010, ADR-011).

Supersedes the M0 Supabase-Auth model (ADR-001). Identity is now owned by this
service: passwords are hashed with **Argon2id** (ADR-011), and we mint & validate
our own **HS256 JWT** access tokens. Supabase remains only for Postgres/Storage.

- `hash_password` / `verify_password` — Argon2id.
- `create_access_token` / `decode_token` — app JWTs.
- `get_current_user` — resolves the ORM `User` from the token `sub`.
- `require_role(...)` — RBAC from the DB `users.role`, never trusted from claims.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthError, ForbiddenError
from app.db.session import get_db
from app.models.enums import STAFF_ROLES, MemberRole
from app.models.user import User

_ph = PasswordHasher()

# tokenUrl documents the login endpoint for OpenAPI's OAuth2 flow; auto_error off
# so we can raise our own RFC 9457 problem responses.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/login", auto_error=False
)


# --- Passwords (Argon2id) ---
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001 — malformed hash, etc.
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


# --- JWT ---
def create_access_token(user_id: uuid.UUID, role: str,
                        expires_minutes: int | None = None) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer, options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Access token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid access token.", code="token_invalid") from exc


# --- Dependencies ---
def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise AuthError("Missing or malformed Authorization header.")
    claims = decode_token(token)
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise AuthError("Token subject is invalid.", code="token_invalid") from exc
    user = db.get(User, user_id)
    if user is None:
        raise AuthError("User no longer exists.", code="user_not_found")
    ended = user.sessions_valid_after
    if ended is not None and not _issued_after(claims, ended):
        # A verified email change (0084) ended every session issued before it.
        raise AuthError("This session has ended. Sign in again.", code="session_revoked")
    if user.is_suspended:
        raise ForbiddenError("Account is suspended.", code="account_suspended")
    return user


def _issued_after(claims: dict, valid_after: datetime) -> bool:
    """Whether the token was issued at or after `valid_after` (whole seconds, as `iat`)."""
    try:
        issued = int(claims["iat"])
    except (KeyError, TypeError, ValueError):
        return False
    moment = valid_after if valid_after.tzinfo else valid_after.replace(tzinfo=UTC)
    return issued >= int(moment.timestamp())


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return get_current_user(token=token.strip(), db=db)


def require_role(*allowed_roles: str):
    """Dependency factory enforcing RBAC from the DB role."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role.value not in allowed_roles:
            raise ForbiddenError(
                f"Requires one of roles: {', '.join(allowed_roles)}.",
                code="role_forbidden",
                extra={"required": list(allowed_roles), "actual": user.role.value},
            )
        return user

    return _guard


# --- Staff roles (owner decisions B-D, 2026-09-28) ---------------------------
#
#   administrator  operational approvals: queues, claims, links, takedowns,
#                  support, reports. No user management.
#   super_admin    everything an administrator does, plus user and role
#                  management and the 2.5-star special routing decision.
#
# Both are read from the users row on every request (never from a token
# claim), so a demotion takes effect on the caller's next request.

STAFF_ROLE_VALUES: tuple[str, ...] = tuple(r.value for r in STAFF_ROLES)


def is_staff(user: User | None) -> bool:
    """An administrator or a Super Admin."""
    return user is not None and user.role in STAFF_ROLES


def is_super_admin(user: User | None) -> bool:
    return user is not None and user.role == MemberRole.super_admin


#: Every operational staff endpoint. A Super Admin inherits all of them.
require_staff = require_role(*STAFF_ROLE_VALUES)


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """User and role management, and the 2.5-star routing decision.

    Deliberately terse on refusal: no `actual` role in the error, since the
    one caller who probes this is the expected case rather than the unusual.
    """
    if not is_super_admin(user):
        raise ForbiddenError("Requires a Super Admin.", code="super_admin_required")
    return user

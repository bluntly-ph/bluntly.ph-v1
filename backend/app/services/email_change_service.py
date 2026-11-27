"""A verified change of the address a member signs in with (0084).

Owner decision 2026-10-04 (store owners first; Figma Overlay/Store/Account 8232:25342).

    start(user, new_email)          one code to the CURRENT address (it is really them),
                                    one to the NEW address (they own it); both sent
                                    before anything is committed
    confirm(user, current, new)     both codes right → the address changes, every other
                                    session ends, the old address is told
    cancel(user)                    drop a pending change

Security posture, mirroring otp_service:
  * codes are Argon2id hashes; the plaintext lives only in memory and the two emails;
  * one attempts counter for the PAIR, in Postgres, in the same transaction as the
    check, so the cap holds when Redis is down;
  * a per-member send cap (the OTP window and limit) in Postgres;
  * "already taken" is answered only at confirm time, to someone who has just proved
    they own the new inbox — so the endpoint cannot be used to probe which addresses
    have accounts;
  * the users.email unique constraint is the final word on a race.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.email import EmailNotConfigured, EmailSendError, send_email
from app.adapters.email_templates import email_change_code, email_changed_notice
from app.core.config import settings
from app.core.errors import (
    AppError,
    EmailDeliveryError,
    OtpAttemptsExceededError,
    OtpExpiredError,
    OtpInvalidError,
    RateLimitError,
)
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.email_change import EmailChangeRequest
from app.models.user import User

log = get_logger("services.email_change")


def _normalize(email: str) -> str:
    return email.strip().lower()


def _code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _ttl_minutes() -> int:
    return max(settings.otp_ttl_seconds // 60, 1)


def pending(db: Session, user: User) -> EmailChangeRequest | None:
    """The member's live request, if any (not consumed, not expired)."""
    row = db.scalar(select(EmailChangeRequest)
                    .where(EmailChangeRequest.user_id == user.id,
                           EmailChangeRequest.consumed_at.is_(None))
                    .order_by(EmailChangeRequest.created_at.desc()).limit(1))
    if row is None or _utc(row.expires_at) <= datetime.now(UTC):
        return None
    return row


def start(db: Session, user: User, new_email: str) -> EmailChangeRequest:
    new_email = _normalize(new_email)
    if new_email == _normalize(user.email):
        raise AppError("That's already the address you sign in with.", code="email_unchanged",
                       status_code=422, title="Same address")
    now = datetime.now(UTC)
    window_start = now - timedelta(seconds=settings.otp_send_window_seconds)
    recent = db.scalar(select(func.count(EmailChangeRequest.id)).where(
        EmailChangeRequest.user_id == user.id,
        EmailChangeRequest.created_at >= window_start)) or 0
    if recent >= settings.otp_max_sends_per_window:
        raise RateLimitError("You've asked for too many codes. Try again later.",
                             extra={"retry_after_seconds": settings.otp_send_window_seconds})

    for row in db.scalars(select(EmailChangeRequest).where(
            EmailChangeRequest.user_id == user.id, EmailChangeRequest.consumed_at.is_(None))):
        row.consumed_at = now          # a new request replaces any outstanding one

    current_code, new_code = _code(), _code()
    while new_code == current_code:
        new_code = _code()
    request = EmailChangeRequest(
        user_id=user.id, new_email=new_email,
        current_code_hash=hash_password(current_code), new_code_hash=hash_password(new_code),
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds))
    db.add(request)

    # Send both BEFORE committing: if either fails, nothing is left half-issued.
    try:
        for to, code, to_new in ((user.email, current_code, False), (new_email, new_code, True)):
            subject, text, html = email_change_code(code=code, ttl_minutes=_ttl_minutes(),
                                                    to_new=to_new, new_email=new_email)
            send_email(to, subject, text, html)
    except (EmailNotConfigured, EmailSendError) as exc:
        db.rollback()
        log.error("email change: code delivery failed",
                  extra={"extra_fields": {"user_id": str(user.id), "error": str(exc)}})
        raise EmailDeliveryError(
            "We couldn't send the codes right now. Please try again shortly.") from exc
    db.commit()
    db.refresh(request)
    return request


def confirm(db: Session, user: User, current_code: str, new_code: str) -> User:
    now = datetime.now(UTC)
    row = db.scalar(select(EmailChangeRequest)
                    .where(EmailChangeRequest.user_id == user.id,
                           EmailChangeRequest.consumed_at.is_(None))
                    .order_by(EmailChangeRequest.created_at.desc()).limit(1)
                    .with_for_update())
    if row is None:
        raise OtpInvalidError("There is no email change waiting. Start again.")
    if row.attempts >= settings.otp_max_attempts:
        row.consumed_at = now
        db.commit()
        raise OtpAttemptsExceededError("Too many incorrect attempts. Start again.")
    if _utc(row.expires_at) <= now:
        row.consumed_at = now
        db.commit()
        raise OtpExpiredError("These codes have expired. Start again.")
    # Both are always checked, so a reply never says which of the two was wrong.
    ok_current = verify_password(current_code.strip(), row.current_code_hash)
    ok_new = verify_password(new_code.strip(), row.new_code_hash)
    if not (ok_current and ok_new):
        row.attempts += 1
        db.commit()
        raise OtpInvalidError("Those codes don't match. Check both emails and try again.")

    row.consumed_at = now
    taken = db.scalar(select(User.id).where(func.lower(User.email) == row.new_email,
                                            User.id != user.id))
    if taken is not None:
        db.commit()
        raise AppError("That address already has a bluntly account.", code="email_taken",
                       status_code=409, title="Address in use")
    old_email = user.email
    user.email = row.new_email
    # Whole seconds, like a token's `iat`: the token issued for this browser right
    # after this still counts; every earlier one is refused.
    user.sessions_valid_after = now.replace(microsecond=0)
    from app.services import notification_service
    notification_service.notify(
        db, user.id, "account_email_changed", "Your sign-in email was changed",
        body=f"You now sign in with {row.new_email}. Other browsers were signed out.",
        link="/settings")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("That address already has a bluntly account.", code="email_taken",
                       status_code=409, title="Address in use") from exc
    db.refresh(user)
    _tell_old_address(old_email, row.new_email)
    return user


def cancel(db: Session, user: User) -> None:
    now = datetime.now(UTC)
    for row in db.scalars(select(EmailChangeRequest).where(
            EmailChangeRequest.user_id == user.id, EmailChangeRequest.consumed_at.is_(None))):
        row.consumed_at = now
    db.commit()


def _tell_old_address(old_email: str, new_email: str) -> None:
    """Best effort: the change is done; a failed notice must not undo or hide it."""
    site = settings.public_site_url
    subject, text, html = email_changed_notice(
        new_email=new_email, support_url=f"{site}/messages?new=1" if site else "")
    try:
        send_email(old_email, subject, text, html)
    except (EmailNotConfigured, EmailSendError) as exc:
        log.error("email change: notice to the old address failed",
                  extra={"extra_fields": {"error": str(exc)}})

"""The email outbox (0085): queue in the event's transaction, send from a scheduled task.

    enqueue(...)        add a message to the caller's session (no commit), so it is
                        sent only if the event that caused it commits
    drain(db)           send what is due (hourly `send_emails`, internal_cron):
                        success -> sent; a failure retries with backoff and gives up
                        after MAX_ATTEMPTS; settled rows older than RETAIN_DAYS go
    unsubscribe_*       signed one-click links (RFC 8058 List-Unsubscribe-Post) that
                        turn a channel off without signing in

Each row's id is Resend's Idempotency-Key: a send retried after a timeout (the email
may in fact have gone) is a no-op at the provider rather than a duplicate.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.adapters.email import EmailNotConfigured, EmailSendError, send_email
from app.core.config import settings
from app.core.logging import get_logger
from app.models.email_outbox import EmailOutbox

log = get_logger("services.email_outbox")

MAX_ATTEMPTS = 5
#: First retry after 5 minutes, then 10, 20, 40.
BACKOFF = timedelta(minutes=5)
RETAIN_DAYS = 30
DRAIN_LIMIT = 200

#: What a one-click unsubscribe can turn off (notification_service.STORE_PREFS keys).
UNSUBSCRIBE_SCOPES = ("email", "weekly_summary")


def enqueue(db: Session, *, to: str, kind: str, subject: str, text: str,
            html: str | None = None, user_id: uuid.UUID | None = None,
            headers: dict[str, str] | None = None, dedupe_key: str | None = None) -> bool:
    """Queue one message on the caller's session. Does not commit.

    With a `dedupe_key` already queued (a job run twice), nothing is added and
    this returns False."""
    inserted = db.scalar(insert(EmailOutbox).values(
        id=uuid.uuid4(), user_id=user_id, to_email=to, kind=kind[:40], subject=subject[:200],
        text_body=text, html_body=html, headers=headers, dedupe_key=dedupe_key,
    ).on_conflict_do_nothing(index_elements=["dedupe_key"],
                             index_where=EmailOutbox.dedupe_key.is_not(None))
        .returning(EmailOutbox.id))
    # RETURNING, not rowcount: through the ORM session rowcount is -1 either way.
    return inserted is not None


def drain(db: Session, *, now: datetime | None = None, limit: int = DRAIN_LIMIT) -> dict:
    """Send what is due. One commit per message, so a crash loses at most one."""
    now = now or datetime.now(UTC)
    sent = failed = retried = 0
    rows = db.scalars(select(EmailOutbox)
                      .where(EmailOutbox.status == "pending",
                             EmailOutbox.next_attempt_at <= now)
                      .order_by(EmailOutbox.next_attempt_at)
                      .limit(limit).with_for_update(skip_locked=True)).all()
    for row in rows:
        try:
            send_email(row.to_email, row.subject, row.text_body, row.html_body,
                       headers=row.headers or None, idempotency_key=str(row.id))
        except (EmailNotConfigured, EmailSendError) as exc:
            row.attempts += 1
            row.last_error = f"{type(exc).__name__}: {str(exc)[:150]}"
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "failed"
                failed += 1
            else:
                row.next_attempt_at = now + BACKOFF * (2 ** (row.attempts - 1))
                retried += 1
            log.warning("outbox send failed", extra={"extra_fields": {
                "outbox_id": str(row.id), "kind": row.kind, "attempts": row.attempts,
                "error": type(exc).__name__}})
        else:
            row.status = "sent"
            row.sent_at = now
            row.attempts += 1
            sent += 1
        db.commit()
    purged = db.execute(delete(EmailOutbox).where(
        EmailOutbox.status.in_(("sent", "failed", "skipped")),
        EmailOutbox.created_at < now - timedelta(days=RETAIN_DAYS))).rowcount or 0
    db.commit()
    return {"sent": sent, "retried": retried, "failed": failed, "purged": purged}


# --- one-click unsubscribe ------------------------------------------------------

def _signature(user_id: uuid.UUID, scope: str) -> str:
    message = f"unsubscribe:{user_id}:{scope}".encode()
    return hmac.new(settings.jwt_secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def unsubscribe_token(user_id: uuid.UUID, scope: str) -> str:
    if scope not in UNSUBSCRIBE_SCOPES:
        raise ValueError(f"unknown unsubscribe scope {scope!r}")
    return f"{user_id}.{scope}.{_signature(user_id, scope)}"


def read_unsubscribe_token(token: str) -> tuple[uuid.UUID, str] | None:
    """(user id, scope) for a genuine token; None for anything else."""
    try:
        raw_id, scope, sig = token.split(".")
        user_id = uuid.UUID(raw_id)
    except ValueError:
        return None
    if scope not in UNSUBSCRIBE_SCOPES:
        return None
    if not hmac.compare_digest(sig, _signature(user_id, scope)):
        return None
    return user_id, scope


def unsubscribe_headers(user_id: uuid.UUID, scope: str) -> dict[str, str]:
    """List-Unsubscribe (+ One-Click, RFC 8058): mail apps show an Unsubscribe button
    that POSTs here without opening the site."""
    site = settings.public_site_url
    if not site.startswith("https://"):
        return {}
    url = f"{site}/api/v1/email/unsubscribe?token={unsubscribe_token(user_id, scope)}"
    return {"List-Unsubscribe": f"<{url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def unsubscribe_page(user_id: uuid.UUID, scope: str) -> str:
    """The link in the email's footer: a page on the site that confirms the choice."""
    return f"{settings.public_site_url}/unsubscribe?token={unsubscribe_token(user_id, scope)}"

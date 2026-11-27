"""In-app notifications (FR-1 1.6).

`notify` adds a row to the caller's session and never commits: the event that
caused it commits both together, so a notification cannot announce a decision
that was rolled back. Every message's wording lives here, in one place, rather
than being composed at each call site.

Two rules hold for every notification, whoever writes it:

* **the link stays on the site** — only a same-site path is stored; an absolute,
  protocol-relative or backslash URL is dropped and the notification is
  delivered without a link (`safe_internal_link`);
* **the body is an excerpt** — whitespace collapsed, cut on a word boundary at
  `EXCERPT_LIMIT` characters (`excerpt`).

Interaction notices (QA-067) add three more:

* **nobody is told about their own action** — `interaction` drops a recipient
  who is the actor;
* **one action is announced once** — each carries an event key (who did what to
  which item) recorded in `notification_receipts`; a vote taken back and cast
  again, or a retried request, finds the receipt and stays silent. Taking a
  vote back never notifies at all;
* **repeats group while unread** — a second upvote on the same review while
  the first notice is unread updates that row ("2 people found your review
  helpful") instead of adding another.

A store owner may turn some store notices off (Figma Screen/Seller/Settings
8218:24151; `users.notification_prefs`, 0083): `notify` drops a kind listed in
`STORE_PREFS` whose switch is off, and a review of more than 3★ when "Only low
reviews" is on. Nothing else can be turned off: decisions about the account,
messages from staff and payouts always arrive.

A member clears a notice with a soft dismissal (`dismiss`, QA-065): the row and
the event it describes stay; only their list stops showing it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.notification import Notification, NotificationReceipt
from app.models.user import User
from app.schemas.notification import NotificationOut

EXCERPT_LIMIT = 140

_WHITESPACE = re.compile(r"\s+")


def excerpt(text: str | None, limit: int = EXCERPT_LIMIT) -> str:
    """Whitespace collapsed; cut on a word boundary with an ellipsis when long."""
    if not text:
        return ""
    flat = _WHITESPACE.sub(" ", text).strip()
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    space = cut.rfind(" ")
    if space > 0:
        cut = cut[:space]
    return cut.rstrip() + "…"


def safe_internal_link(link: str | None) -> str | None:
    """A same-site path, or None. Rendered as an href, so nothing else survives."""
    if not link:
        return None
    if not link.startswith("/") or link.startswith("//") or "\\" in link:
        return None
    if any(ch.isspace() or ord(ch) < 32 for ch in link):
        return None
    return link


#: Store-owner switches (key -> default) and the notification kinds each one covers.
STORE_PREFS: dict[str, bool] = {
    "store_reviews": True,
    "store_reviews_low_only": False,
    "store_questions": True,
    "appeal_updates": True,
    "product_links": True,
    #: Channels (0085): each store notice above also by email, and the Monday summary.
    "email": True,
    "weekly_summary": True,
}
_KIND_PREF = {
    "store_review_new": "store_reviews",
    "store_question_new": "store_questions",
    "seller_appeal_decided": "appeal_updates",
    "store_product_decided": "product_links",
}
#: "Only low reviews": a review of this many stars or fewer still notifies.
LOW_REVIEW_MAX = 3


def prefs_of(user: User) -> dict[str, bool]:
    """The account's switches with defaults filled in (unknown keys ignored)."""
    saved = user.notification_prefs or {}
    return {k: bool(saved.get(k, default)) for k, default in STORE_PREFS.items()}


def _decide(db: Session, user_id: uuid.UUID, kind: str,
            rating: float | None) -> tuple[bool, User | None]:
    """(show it in the app?, the account to email it to, or None)."""
    pref = _KIND_PREF.get(kind)
    if pref is None:
        return True, None
    user = db.get(User, user_id)
    if user is None:
        return False, None
    saved = user.notification_prefs or {}
    prefs = {k: bool(saved.get(k, d)) for k, d in STORE_PREFS.items()}
    if not prefs[pref]:
        return False, None
    if kind == "store_review_new" and prefs["store_reviews_low_only"] and not (
            rating is not None and rating <= LOW_REVIEW_MAX):
        return False, None
    return True, (user if prefs["email"] and user.email else None)


def notify(db: Session, user_id: uuid.UUID | None, kind: str, title: str, *,
           body: str | None = None, link: str | None = None,
           rating: float | None = None) -> None:
    """Queue one notification on the caller's session. Does not commit.

    `rating` matters only for a new store review ("Only low reviews"). A store
    notice whose owner has email on is also queued in the email outbox (0085), in
    the same transaction, so a rolled-back event emails nobody."""
    if user_id is None:
        return
    wanted, email_to = _decide(db, user_id, kind, rating)
    if not wanted:
        return
    short = excerpt(body) or None
    safe_link = safe_internal_link(link)
    db.add(Notification(user_id=user_id, kind=kind, title=title[:160], body=short,
                        link=safe_link))
    if email_to is not None:
        _email_notice(db, email_to, kind, title[:160], short, safe_link)


def _email_notice(db: Session, user: User, kind: str, title: str, body: str | None,
                  link: str | None) -> None:
    from app.adapters.email_templates import notification_email
    from app.core.config import settings
    from app.services import email_outbox_service as outbox

    site = settings.public_site_url
    subject, text, html = notification_email(
        title=title, body=body, open_url=f"{site}{link}" if (site and link) else None,
        settings_url=f"{site}/seller/dashboard",
        unsubscribe_url=outbox.unsubscribe_page(user.id, "email"))
    outbox.enqueue(db, to=user.email, kind=f"notice:{kind}", subject=subject, text=text,
                   html=html, user_id=user.id,
                   headers=outbox.unsubscribe_headers(user.id, "email") or None)


def _first_time(db: Session, user_id: uuid.UUID, event_key: str) -> bool:
    """Record that `user_id` is being told about `event_key`; False if already told.

    `ON CONFLICT DO NOTHING` rather than read-then-write, so two concurrent
    requests for the same event cannot both see "not yet" and both notify.
    """
    inserted = db.execute(
        insert(NotificationReceipt)
        .values(user_id=user_id, event_key=event_key[:160])
        .on_conflict_do_nothing()
        .returning(NotificationReceipt.user_id)
    ).first()
    return inserted is not None


def interaction(db: Session, user_id: uuid.UUID | None, actor_id: uuid.UUID | None,
                kind: str, title: str | Callable[[int], str], *, event_key: str,
                body: str | None = None, link: str | None = None) -> bool:
    """One interaction notice (QA-067): never to the actor, once per event key.

    `title` may be a function of a count; the notice then groups — while an
    unread, undismissed notice of the same kind about the same link exists, it
    is updated (count + 1, moved to the top) rather than joined by another.
    Returns whether anything was written. Does not commit.
    """
    if user_id is None or user_id == actor_id:
        return False
    if not _first_time(db, user_id, event_key):
        return False
    if not callable(title):
        notify(db, user_id, kind, title, body=body, link=link)
        return True
    link = safe_internal_link(link)
    open_row = db.scalar(
        select(Notification).where(
            Notification.user_id == user_id, Notification.kind == kind,
            Notification.link == link if link is not None else Notification.link.is_(None),
            Notification.read_at.is_(None), Notification.dismissed_at.is_(None))
        .order_by(Notification.created_at.desc()).limit(1).with_for_update())
    if open_row is None:
        notify(db, user_id, kind, title(1), body=body, link=link)
        return True
    open_row.group_count = (open_row.group_count or 1) + 1
    open_row.title = title(open_row.group_count)[:160]
    open_row.created_at = datetime.now(UTC)
    return True


# ------------------------------------------------------------ messages

def review_decided(db: Session, review, outcome: str, reason: str | None = None) -> None:
    """Staff decided the author's review's earnings, or took it down or
    restored it. Publication itself happens at submission and needs no notice.
    """
    if outcome == "earnings_approved":
        honesty = getattr(review.earn_eligible_status, "value",
                          review.earn_eligible_status) == "honesty_fund"
        notify(db, review.author_id, "earnings_approved",
               "Your review joins the Honesty Fund" if honesty
               else "Your review can now earn",
               body=review.title, link=f"/reviews/{review.id}")
    elif outcome == "routed_platform":
        # Owner decision A: said plainly, because this review will not pay its
        # author and the author should hear that from us, not from a statement.
        notify(db, review.author_id, "earnings_approved",
               "Your review's earnings go to the platform",
               body=reason or review.title, link=f"/reviews/{review.id}")
    elif outcome == "earnings_rejected":
        notify(db, review.author_id, "earnings_rejected",
               "Your review won't earn — it stays public",
               body=reason or review.title, link=f"/reviews/{review.id}")
    elif outcome == "restored":
        notify(db, review.author_id, "review_restored", "Your review is back up",
               body=review.title, link=f"/reviews/{review.id}")
    elif outcome == "unpublished":
        notify(db, review.author_id, "review_unpublished",
               "Your review was taken down for another look",
               body=reason or review.title, link=f"/reviews/{review.id}")


def review_upvoted(db: Session, review, voter_id: uuid.UUID) -> None:
    """Someone found the author's review helpful. Votes are private, so the
    notice never names the voter — only how many."""
    interaction(
        db, review.author_id, voter_id, "review_upvoted",
        lambda n: ("Someone found your review helpful" if n == 1
                   else f"{n} people found your review helpful"),
        event_key=f"review_upvoted:{review.id}:{voter_id}",
        body=review.title, link=f"/reviews/{review.id}")


def comment_upvoted(db: Session, comment, voter_id: uuid.UUID) -> None:
    interaction(
        db, comment.author_id, voter_id, "comment_upvoted",
        lambda n: ("Someone found your comment helpful" if n == 1
                   else f"{n} people found your comment helpful"),
        event_key=f"comment_upvoted:{comment.id}:{voter_id}",
        body=comment.body, link=f"/reviews/{comment.review_id}#comment-{comment.id}")


def _handle(user: User | None) -> str:
    if user is None:
        return "Someone"
    return f"@{user.username}" if getattr(user, "username", None) else (
        user.display_name or "Someone")


def new_comment(db: Session, review, comment, author: User, *,
                parent=None, followers: Iterable[uuid.UUID] = (),
                mentioned: Iterable[User] = ()) -> None:
    """Everyone a new comment concerns, each told once and at most once.

    The review's author (a comment on their review), the parent's author (a
    reply to their comment), the parent's followers (QA-069), and anyone
    @mentioned — in that order, so a person who is several of these hears the
    most specific version and nothing else.
    """
    link = f"/reviews/{review.id}#comment-{comment.id}"
    who = _handle(author)
    told: set[uuid.UUID] = {author.id}

    def tell(user_id, kind, title):
        if user_id is None or user_id in told:
            return
        told.add(user_id)
        interaction(db, user_id, author.id, kind, title,
                    event_key=f"{kind}:{comment.id}", body=comment.body, link=link)

    if parent is not None:
        tell(parent.author_id, "comment_reply", f"{who} replied to your comment")
    for user in mentioned:
        tell(user.id, "comment_mention", f"{who} mentioned you in a comment")
    if parent is not None:
        for follower in followers:
            tell(follower, "followed_comment_reply",
                 f"{who} replied to a comment you follow")
    tell(review.author_id, "review_comment", f"{who} commented on your review")


def request_link(req) -> str:
    """Every request notice opens the request's own page (dev/QA sync
    2026-09-29): the question, every answer, and the Best Answer control for
    its asker. The board anchor it used to open can be gone by the time the
    notice is read, since an answered request leaves the board."""
    return f"/requests/{req.id}"


def request_upvoted(db: Session, req, voter_id: uuid.UUID) -> None:
    interaction(
        db, req.requester_id, voter_id, "request_upvoted",
        lambda n: ("Someone else wants your request answered" if n == 1
                   else f"{n} more people want your request answered"),
        event_key=f"request_upvoted:{req.id}:{voter_id}",
        # Per request: the link is also what groups repeats, so two requests'
        # up-votes never merge into one count.
        body=req.title, link=request_link(req))


def request_answered(db: Session, req, review) -> None:
    """The asker hears about every answer (grouped while unread); picking the
    Best Answer is theirs to do on the request's page."""
    interaction(
        db, req.requester_id, review.author_id, "request_answered",
        lambda n: ("Someone answered your request" if n == 1
                   else f"{n} people answered your request"),
        event_key=f"request_answered:{req.id}:{review.id}",
        body=req.title, link=request_link(req))


def request_fulfilled(db: Session, req, review, recipient_id: uuid.UUID,
                      *, requester: bool) -> None:
    interaction(
        db, recipient_id, review.author_id, "request_fulfilled",
        "Your review request was answered" if requester
        else "A review you were waiting for is up",
        event_key=f"request_fulfilled:{req.id}", body=req.title,
        link=request_link(req))


def request_best_answer(db: Session, req, review) -> None:
    """The answer's author hears that the asker picked their review."""
    interaction(
        db, review.author_id, req.requester_id, "request_best_answer",
        "Your review was picked as the Best Answer to a request",
        event_key=f"request_best_answer:{req.id}", body=req.title,
        link=request_link(req))


# ---------------------------------------------------------------- reads

def _visible(stmt, user: User):
    return stmt.where(Notification.user_id == user.id, Notification.dismissed_at.is_(None))


def list_for(db: Session, user: User, *, unread_only: bool, limit: int,
             kinds: list[str] | None = None) -> list[NotificationOut]:
    """Newest first. `kinds` narrows to those kinds on the server, so a filtered
    tab (the Seller's Reviews / Questions / Appeals) is never just the part of
    the latest page that happens to match."""
    stmt = _visible(select(Notification), user)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    if kinds:
        stmt = stmt.where(Notification.kind.in_(kinds))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
    return [NotificationOut.model_validate(n) for n in db.scalars(stmt).all()]


def unread_count(db: Session, user: User) -> int:
    return db.scalar(
        _visible(select(func.count(Notification.id)), user)
        .where(Notification.read_at.is_(None))
    ) or 0


def _own(db: Session, user: User, notification_id: uuid.UUID) -> Notification:
    """The caller's own, not-dismissed notification. Another account's is
    reported as not found, so its existence is not confirmed to someone it does
    not belong to; a dismissed one is gone from the member's point of view."""
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user.id or row.dismissed_at is not None:
        raise NotFoundError("Notification not found.", code="notification_not_found")
    return row


def mark_read(db: Session, user: User, notification_id: uuid.UUID) -> NotificationOut:
    """Mark one read."""
    row = _own(db, user, notification_id)
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
    return NotificationOut.model_validate(row)


def mark_unread(db: Session, user: User, notification_id: uuid.UUID) -> NotificationOut:
    """QA-065: put one back in the unread count, to come back to it later."""
    row = _own(db, user, notification_id)
    if row.read_at is not None:
        row.read_at = None
        db.commit()
        db.refresh(row)
    return NotificationOut.model_validate(row)


def dismiss(db: Session, user: User, notification_id: uuid.UUID) -> None:
    """QA-065: clear one from the member's list. Soft — the row stays, and so
    does whatever it announced; a second call is a 404 like any missing one."""
    row = _own(db, user, notification_id)
    now = datetime.now(UTC)
    row.dismissed_at = now
    if row.read_at is None:
        row.read_at = now
    db.commit()


def mark_all_read(db: Session, user: User) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None),
               Notification.dismissed_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    db.commit()
    return result.rowcount or 0

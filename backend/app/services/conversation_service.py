"""The Inbox and Messages (0076; Figma Screen/Admin/Inbox 8291:30461,
Screen/Seller/Inbox 8304:32524, Screen/Messages 8296:31219).

A member writes to the Bluntly team; any Administrator or Super Admin reads
and answers. Who may do what is decided here, never by the caller:

* a member reads and writes only their own conversations (404 otherwise, so a
  conversation id cannot be probed);
* a seller conversation is about a store the member owns (an approved claim),
  or about the member's own claim;
* a link (appeal, claim, payout, review, report) must be the member's own; a
  product link must be a product that exists;
* staff may read, answer, assign, change status, close, reopen and move a
  seller conversation to Queue → Support. Every staff action but a reply is
  audited (moderation_logs, action 'conversation').

A claim's or an appeal's chat is ONE conversation (owner decision 2026-10-03):
`case_conversation` finds or opens it by `case_key`, and case_chat_service
reads and writes through it. A member who starts a claim or appeal conversation
from Messages writes into that same thread, so a file sent as evidence is on the
case the reviewer opens.

Attachments: the file goes to storage before the row is committed. If the
message then fails to save, the object is removed again (`_saving`), so a
failed write never leaves evidence nobody can reach; a failed upload raises
before any row is written.

Email: a staff reply and a close are also emailed to the member ("They also
get it by email"); a member can ask for a copy of the thread. Email is best
effort and never fails the request — the message is saved either way.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, object_session

from app.core.constants import MANILA
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.security import STAFF_ROLES, is_staff
from app.models.conversation import (
    LINK_TYPES,
    Conversation,
    ConversationMessage,
    ConversationMessageHide,
    ConversationMessageRevision,
)
from app.models.enums import (
    ConversationAudience,
    ConversationMessageKind,
    ConversationStatus,
    ConversationTopic,
    ModerationAction,
    PayoutStatus,
    SellerClaimStatus,
    SupportRequestCategory,
    SupportRequestStatus,
)
from app.models.moderation import ModerationLog
from app.models.payout import Payout
from app.models.product import Product
from app.models.review import Review
from app.models.seller import Seller, SellerClaim, SellerReview, SellerReviewAppeal
from app.models.support import SellerSupportRequest
from app.models.user import User
from app.schemas.conversation import (
    ConversationAttachmentOut,
    ConversationDetailOut,
    ConversationLinkOut,
    ConversationMemberSummary,
    ConversationMessageOut,
    ConversationPartyOut,
    ConversationRowOut,
    InboxCounts,
    InboxListOut,
    LinkOptionOut,
    MemberCounts,
    MemberListOut,
    StaffOptionOut,
)
from app.services import notification_service

log = get_logger("services.conversations")

#: Figma "0 / 500" on a new message; replies may run longer.
MAX_FIRST = 500
MAX_REPLY = 2000
#: A member's open conversations at once: enough for real use, a wall for a flood.
MAX_OPEN_PER_MEMBER = 20
MAX_MESSAGES = 500
#: MQA-011: how long after sending its sender may edit or unsend a message.
CHANGE_WINDOW = timedelta(minutes=15)
PAGE_SIZES = (10, 25, 50)
#: The appeal's proof window (seller_service: the reviewer has 7 days).
PROOF_DAYS = 7

TOPIC_LABEL = {
    ConversationTopic.appeal: "Appeal",
    ConversationTopic.claim: "Claim",
    ConversationTopic.product: "Product request",
    ConversationTopic.payout: "Payout",
    ConversationTopic.review: "Review",
    ConversationTopic.report: "Report",
    ConversationTopic.account: "Account",
    ConversationTopic.other: "General",
}
#: Which topics each side may start (Menu/Store/Chat/Topic, Screen/Messages/New).
SELLER_TOPICS = (ConversationTopic.appeal, ConversationTopic.claim, ConversationTopic.product,
                 ConversationTopic.account, ConversationTopic.other)
REVIEWER_TOPICS = (ConversationTopic.payout, ConversationTopic.review, ConversationTopic.report,
                   ConversationTopic.account, ConversationTopic.other)
#: The link each topic may carry.
TOPIC_LINK = {
    ConversationTopic.appeal: "appeal",
    ConversationTopic.claim: "claim",
    ConversationTopic.product: "product",
    ConversationTopic.payout: "payout",
    ConversationTopic.review: "review",
    ConversationTopic.report: "report",
}

OPEN = (ConversationStatus.open, ConversationStatus.waiting)


# ------------------------------------------------------------------ helpers

def _now() -> datetime:
    return datetime.now(UTC)


def _day(moment: datetime | None) -> str:
    if moment is None:
        return ""
    local = moment.astimezone(MANILA)
    return f"{local.day} {local.strftime('%b')}"


def _money(amount: Decimal | None) -> str:
    return f"₱{(amount or Decimal(0)):,.2f}"


def _name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or (f"@{user.username}" if user.username else None)


def _party(user: User | None) -> ConversationPartyOut:
    if user is None:
        return ConversationPartyOut()
    return ConversationPartyOut(id=user.id, name=_name(user), trust_stage=user.trust_stage,
                                avatar_url=getattr(user, "avatar_url", None))


def _clean(body: str | None, limit: int, *, file: Attachment | None = None) -> str:
    """The message text. A reply may be a file alone (MQA-009: proof sent with
    nothing to add); a message with neither words nor a file is refused."""
    text = (body or "").strip()
    if not text and file is not None:
        return ""
    if not text:
        raise AppError("Write a message or attach a file before sending.", code="message_empty",
                       status_code=422, title="Invalid message")
    if len(text) > limit:
        raise AppError(f"A message is at most {limit} characters.", code="message_too_long",
                       status_code=422, title="Invalid message")
    return text


_TEMPLATE_TAG = re.compile(r"\{\{\s*[A-Za-z0-9_ .-]*?\s*\}\}")


def no_template_tags(text: str) -> None:
    """MQA-028: the team never sends a reply with a template tag left in it
    ("Hi {{store_name}}"). The composers say so before Send; this is the rule."""
    found = list(dict.fromkeys(m.group(0) for m in _TEMPLATE_TAG.finditer(text or "")))
    if found:
        listed = found[0] if len(found) == 1 else ", ".join(found[:-1]) + " and " + found[-1]
        raise AppError(f"Fill in {listed} before sending.", code="template_unfilled",
                       status_code=422, title="Invalid message")


def _said(m: ConversationMessage) -> str:
    """A message as one line of text: its words, or the file it carried alone."""
    if m.unsent_at is not None:
        return "Message unsent"
    if m.body:
        return m.body
    return f"Sent a file: {m.attachment_name}" if m.attachment_name else ""


def _audit(db: Session, actor: User, conv: Conversation, event: str, **extra) -> None:
    context = {"event": event, "reference": conv.reference, "status": conv.status.value}
    context.update({k: v for k, v in extra.items() if v is not None})
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=actor.id,
                         action=ModerationAction.conversation, target_ref=conv.id,
                         notes=f"conversation {event}", context=context))


def _owns_store(db: Session, user: User, seller_id: uuid.UUID) -> Seller:
    seller = db.get(Seller, seller_id)
    if seller is None or seller.claim_status != SellerClaimStatus.claimed \
            or seller.claimed_by_id != user.id:
        raise ForbiddenError("Only the store's approved owner can write about it.",
                             code="not_store_owner")
    return seller


def _member_link(conv: Conversation) -> str:
    """Where the member reads this conversation (MQA-027: a notice opens the
    conversation itself, not the store's page).

    A store's threads open in the seller console's Messages. A claim's thread
    opens there too once the claim is approved; while it is pending the
    claimant has no console yet, so it opens in their own Messages."""
    if conv.audience == ConversationAudience.seller and conv.seller_id is not None:
        if conv.topic != ConversationTopic.claim:
            return f"/seller/{conv.seller_id}/messages?c={conv.id}"
        db = object_session(conv)
        seller = db.get(Seller, conv.seller_id) if db is not None else None
        if seller is not None and seller.claim_status == SellerClaimStatus.claimed \
                and seller.claimed_by_id == conv.member_id:
            return f"/seller/{conv.seller_id}/messages?c={conv.id}"
    return f"/messages/{conv.id}"


def member_link(conv: Conversation) -> str:
    return _member_link(conv)


def _unread_for(conv: Conversation, staff_view: bool) -> bool:
    if conv.status == ConversationStatus.closed and staff_view:
        return False
    if staff_view:
        at, seen = conv.last_member_message_at, conv.staff_read_at
    else:
        at, seen = conv.last_staff_message_at, conv.member_read_at
    return at is not None and (seen is None or at > seen)


# ------------------------------------------------------------------ links

def _reviewer_label(db: Session, review: SellerReview | None) -> str:
    if review is None:
        return "a reviewer"
    return _name(db.get(User, review.reviewer_id)) or "a reviewer"


def _appeal_status(appeal: SellerReviewAppeal) -> str:
    if appeal.status == "open":
        return "Waiting for an admin"
    if appeal.status == "substantiation_requested":
        if appeal.substantiated_at is not None:
            return "Proof sent, waiting for a decision"
        due = (appeal.substantiation_requested_at or _now()) + timedelta(days=PROOF_DAYS)
        if due < _now():
            return f"Proof requested, overdue since {_day(due)}"
        return f"Proof requested, due {_day(due)}"
    if appeal.status == "upheld":
        return "Upheld: the review was removed"
    if appeal.status == "dismissed":
        return "Dismissed: the review stays up"
    return appeal.status


def _report_target(db: Session, report: ModerationLog) -> str:
    if report.target_ref is not None and report.target_type is not None:
        if report.target_type.value == "review":
            review = db.get(Review, report.target_ref)
            if review is not None:
                return review.title
        if report.target_type.value == "seller_review":
            sr = db.get(SellerReview, report.target_ref)
            if sr is not None:
                seller = db.get(Seller, sr.seller_id)
                return f"a review of {seller.display_name}" if seller else "a store review"
    return "a post"


def _link(db: Session, conv: Conversation, viewer: str) -> ConversationLinkOut | None:
    """The context bar for `viewer` in staff | seller | reviewer."""
    if conv.link_type is None or conv.link_id is None:
        return None
    t, i = conv.link_type, conv.link_id
    if t == "appeal":
        appeal = db.get(SellerReviewAppeal, i)
        if appeal is None:
            return None
        review = db.get(SellerReview, appeal.seller_review_id)
        rating = f"{float(review.overall_rating):g}★ " if review is not None else ""
        if viewer == "reviewer":
            seller = db.get(Seller, appeal.seller_id)
            label = f"{seller.display_name if seller else 'A store'}’s appeal on your review"
            href = f"/sellers/appeals/{appeal.id}"
        else:
            label = f"Appeal on {_reviewer_label(db, review)}’s {rating}review"
            href = ("/admin/sellers?tab=appeals" if viewer == "staff"
                    else f"/seller/{appeal.seller_id}/appeals")
        return ConversationLinkOut(type="appeal", id=i, label=label, status=_appeal_status(appeal),
                                   href=href, action="Open appeal")
    if t == "claim":
        claim = db.get(SellerClaim, i)
        if claim is None:
            return None
        seller = db.get(Seller, claim.seller_id)
        status = {SellerClaimStatus.pending: "In review", SellerClaimStatus.claimed: "Approved",
                  SellerClaimStatus.rejected: "Not approved",
                  SellerClaimStatus.withdrawn: "Withdrawn"}.get(claim.status, claim.status.value)
        return ConversationLinkOut(
            type="claim", id=i, label=f"Claim on {seller.display_name if seller else 'a store'}",
            status=status, href="/admin/sellers" if viewer == "staff" else None,
            action="Open claim" if viewer == "staff" else None)
    if t == "payout":
        payout = db.get(Payout, i)
        if payout is None:
            return None
        if payout.status == PayoutStatus.failed:
            status = f"Failed on {_day(payout.updated_at)}" + (
                f": {payout.failure_reason}" if payout.failure_reason else "")
            if viewer != "staff":
                status = (f"{_money(payout.amount)} back in your wallet · "
                          f"failed {_day(payout.updated_at)}")
        elif payout.status == PayoutStatus.paid:
            status = f"Paid on {_day(payout.paid_at)}"
        elif payout.status == PayoutStatus.cancelled:
            status = f"Cancelled on {_day(payout.updated_at)}"
        else:
            when = datetime.combine(payout.scheduled_for, datetime.min.time(), tzinfo=MANILA)
            status = f"Scheduled for {_day(when)}"
        return ConversationLinkOut(
            type="payout", id=i, label=f"Payout {_money(payout.amount)}", status=status,
            href="/admin/payouts" if viewer == "staff" else "/dashboard/history",
            action="Open payout" if viewer == "staff" else "View")
    if t == "review":
        review = db.get(Review, i)
        if review is None:
            return None
        product = db.get(Product, review.product_id)
        live = review.published_at is not None and not review.is_removed
        return ConversationLinkOut(
            type="review", id=i, label=f"Review · {review.title}",
            status=(product.canonical_name if product and product.canonical_name else None)
            if live else "Taken down",
            href=f"/reviews/{review.id}" if live else (
                "/admin/review-queue?tab=all" if viewer == "staff" else None),
            action="Open review")
    if t == "report":
        report = db.get(ModerationLog, i)
        if report is None:
            return None
        status = (report.resolution.value.replace("_", " ").capitalize()
                  if report.resolution is not None else "Open")
        return ConversationLinkOut(
            type="report", id=i, label=f"Report · {_report_target(db, report)}",
            status=f"{status} · sent {_day(report.created_at)}",
            href="/admin/review-queue?tab=report" if viewer == "staff" else None,
            action="Open report" if viewer == "staff" else None)
    if t == "product":
        product = db.get(Product, i)
        if product is None:
            return None
        name = product.canonical_name or "Product"
        return ConversationLinkOut(
            type="product", id=i, label=name, status=None,
            href=f"/admin/products?q={name}" if viewer == "staff" else None,
            action="Open product" if viewer == "staff" else None)
    return None


def _check_link(db: Session, user: User, audience: ConversationAudience,
                seller_id: uuid.UUID | None, link_type: str, link_id: uuid.UUID) -> str:
    """Raise unless the member may link this; return the subject it implies."""
    missing = NotFoundError("That isn't one of yours.", code="link_not_found")
    if link_type == "appeal":
        appeal = db.get(SellerReviewAppeal, link_id)
        if appeal is None or appeal.appellant_id != user.id \
                or (seller_id is not None and appeal.seller_id != seller_id):
            raise missing
        review = db.get(SellerReview, appeal.seller_review_id)
        return f"{_reviewer_label(db, review)}’s review"
    if link_type == "claim":
        claim = db.get(SellerClaim, link_id)
        if claim is None or claim.user_id != user.id:
            raise missing
        seller = db.get(Seller, claim.seller_id)
        return seller.display_name if seller else "Store claim"
    if link_type == "payout":
        payout = db.get(Payout, link_id)
        if payout is None or payout.user_id != user.id:
            raise missing
        return f"{_money(payout.amount)} {payout.status.value}"
    if link_type == "review":
        review = db.get(Review, link_id)
        if review is None or review.author_id != user.id:
            raise missing
        return review.title
    if link_type == "report":
        report = db.get(ModerationLog, link_id)
        if report is None or report.reporter_id != user.id \
                or report.action != ModerationAction.report:
            raise missing
        return f"Your report on {_report_target(db, report)}"
    if link_type == "product":
        product = db.get(Product, link_id)
        if product is None:
            raise NotFoundError("Product not found.", code="product_not_found")
        return product.canonical_name or "A product page"
    raise missing


# ------------------------------------------------------------------ output

def _attachment(conv_id: uuid.UUID, m: ConversationMessage) -> ConversationAttachmentOut | None:
    if not m.attachment_key:
        return None
    return ConversationAttachmentOut(
        name=m.attachment_name or "Attachment", type=m.attachment_type or "",
        size=m.attachment_size,
        href=f"/api/v1/conversations/{conv_id}/messages/{m.id}/attachment")


#: Public name for the case chat (services/case_chat_service.py).
attachment_out = _attachment


def _change_until(m: ConversationMessage) -> datetime | None:
    """MQA-011: until when the sender may edit or unsend `m` (None: no longer)."""
    if m.kind != ConversationMessageKind.message or m.unsent_at is not None:
        return None
    until = m.created_at + CHANGE_WINDOW
    return until if until > _now() else None


def _message_out(conv_id: uuid.UUID, m: ConversationMessage,
                 users: dict[uuid.UUID, User]) -> ConversationMessageOut:
    author = users.get(m.author_id) if m.author_id else None
    return ConversationMessageOut(
        id=m.id, kind=m.kind, from_staff=m.from_staff, author_id=m.author_id,
        author_name=_name(author), body=m.body, created_at=m.created_at,
        attachment=_attachment(conv_id, m), edited_at=m.edited_at,
        unsent=m.unsent_at is not None, change_until=_change_until(m))


def _last_messages(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, ConversationMessage]:
    if not ids:
        return {}
    ranked = (select(ConversationMessage,
                     func.row_number().over(partition_by=ConversationMessage.conversation_id,
                                            order_by=ConversationMessage.created_at.desc())
                     .label("rn"))
              .where(ConversationMessage.conversation_id.in_(ids),
                     ConversationMessage.kind == ConversationMessageKind.message)
              .subquery())
    rows = db.execute(select(ConversationMessage)
                      .join(ranked, ranked.c.id == ConversationMessage.id)
                      .where(ranked.c.rn == 1)).scalars().all()
    return {m.conversation_id: m for m in rows}


def _rows(db: Session, convs: list[Conversation], viewer: str) -> list[ConversationRowOut]:
    ids = [c.id for c in convs]
    last = _last_messages(db, ids)
    user_ids = {c.member_id for c in convs} | {c.assigned_admin_id for c in convs}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(
        [u for u in user_ids if u is not None])))} if user_ids else {}
    seller_ids = {c.seller_id for c in convs if c.seller_id is not None}
    sellers = {s.id: s for s in db.scalars(select(Seller).where(Seller.id.in_(seller_ids)))} \
        if seller_ids else {}
    support_ids = {c.support_request_id for c in convs if c.support_request_id is not None}
    refs = {r.id: r.reference for r in db.scalars(select(SellerSupportRequest).where(
        SellerSupportRequest.id.in_(support_ids)))} if support_ids else {}
    out = []
    for c in convs:
        m = last.get(c.id)
        seller = sellers.get(c.seller_id) if c.seller_id else None
        out.append(ConversationRowOut(
            id=c.id, reference=c.reference, audience=c.audience, topic=c.topic, subject=c.subject,
            status=c.status, seller_id=c.seller_id,
            seller_name=seller.display_name if seller else None,
            seller_platform=seller.platform.value if seller else None,
            member=_party(users.get(c.member_id) if c.member_id else None),
            assigned_admin=(_party(users[c.assigned_admin_id])
                            if c.assigned_admin_id in users else None),
            last_message_at=c.last_message_at,
            preview=notification_service.excerpt(_said(m)) if m else None,
            preview_from_staff=bool(m and m.from_staff),
            unread=_unread_for(c, viewer == "staff"),
            link=_link(db, c, viewer), closed_at=c.closed_at,
            support_reference=refs.get(c.support_request_id) if c.support_request_id else None))
    return out


def _summary(db: Session, conv: Conversation,
             member: User | None) -> ConversationMemberSummary | None:
    if member is None:
        return None
    if conv.audience == ConversationAudience.seller:
        seller = db.get(Seller, conv.seller_id) if conv.seller_id else None
        owner = seller is not None and seller.claim_status == SellerClaimStatus.claimed \
            and seller.claimed_by_id == member.id
        return ConversationMemberSummary(
            role="seller", label="Store owner" if owner else "Claimant",
            store_name=seller.display_name if seller else None)
    reviews = db.scalar(select(func.count()).select_from(Review).where(
        Review.author_id == member.id, Review.published_at.is_not(None),
        Review.is_removed.is_(False))) or 0
    earned = None
    try:
        from app.services.reporting import earnings_statement, periods
        earned = earnings_statement.build(db, member, periods.resolve()).summary.lifetime_earned
    except Exception:  # noqa: BLE001 - the header stands without its money figure
        db.rollback()
    return ConversationMemberSummary(role="reviewer", label=member.trust_level_name,
                                     reviews=reviews, earned=earned)


def _detail(db: Session, conv: Conversation, viewer: str,
            viewer_id: uuid.UUID | None = None) -> ConversationDetailOut:
    stmt = (select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conv.id)
            .order_by(ConversationMessage.created_at, ConversationMessage.id))
    if viewer_id is not None:
        # MQA-011: what this person deleted for themselves is not shown to them.
        stmt = stmt.where(~select(ConversationMessageHide.message_id).where(
            ConversationMessageHide.message_id == ConversationMessage.id,
            ConversationMessageHide.user_id == viewer_id).exists())
    msgs = db.scalars(stmt).all()
    ids = {m.author_id for m in msgs if m.author_id} | {conv.closed_by_id, conv.member_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(
        [i for i in ids if i is not None])))}
    row = _rows(db, [conv], viewer)[0]
    member = users.get(conv.member_id) if conv.member_id else None
    return ConversationDetailOut(
        **row.model_dump(),
        messages=[_message_out(conv.id, m, users) for m in msgs],
        closed_by=_party(users.get(conv.closed_by_id)) if conv.closed_by_id else None,
        member_summary=_summary(db, conv, member) if viewer == "staff" else None,
        support_status=(db.scalar(select(SellerSupportRequest.status).where(
            SellerSupportRequest.id == conv.support_request_id)).value
            if conv.support_request_id else None))


# ------------------------------------------------------------------ writing

@dataclass
class Attachment:
    data: bytes
    name: str


#: Keys uploaded in the session's current transaction, not yet committed.
_UPLOADED = "conversation_uploads"


def _store_attachment(db: Session, conv: Conversation, file: Attachment | None) -> dict:
    if file is None or not file.data:
        return {}
    from app.services import storage
    key, mime = storage.upload_attachment(conv.id, file.data)
    db.info.setdefault(_UPLOADED, []).append(key)
    return {"attachment_key": key, "attachment_type": mime,
            "attachment_name": (file.name or "attachment")[:160],
            "attachment_size": len(file.data)}


@contextmanager
def _saving(db: Session) -> Iterator[None]:
    """Wrap a write that may upload a file, up to and including its commit: if
    anything in it fails, the files it uploaded are removed (best effort) and
    the error goes on to the caller."""
    try:
        yield
    except BaseException:
        keys = db.info.pop(_UPLOADED, None)
        if keys:
            from app.services import storage
            storage.delete_attachment_objects(keys)
            log.warning("Conversation upload discarded",
                        extra={"extra_fields": {"objects": len(keys)}})
        raise
    db.info.pop(_UPLOADED, None)


def _event(db: Session, conv: Conversation, actor: User | None, body: str) -> None:
    db.add(ConversationMessage(conversation_id=conv.id, kind=ConversationMessageKind.event,
                               author_id=actor.id if actor else None,
                               from_staff=bool(actor and is_staff(actor)
                                               and actor.id != conv.member_id),
                               body=body, created_at=_now()))


def _write(db: Session, conv: Conversation, author: User, body: str, *, as_staff: bool,
           file: Attachment | None = None) -> ConversationMessage:
    count = db.scalar(select(func.count()).select_from(ConversationMessage).where(
        ConversationMessage.conversation_id == conv.id)) or 0
    if count >= MAX_MESSAGES:
        raise AppError("This conversation is full. Start a new one.", code="conversation_full",
                       status_code=422, title="Invalid message")
    now = _now()
    msg = ConversationMessage(conversation_id=conv.id, kind=ConversationMessageKind.message,
                              author_id=author.id, from_staff=as_staff, body=body, created_at=now,
                              **_store_attachment(db, conv, file))
    db.add(msg)
    conv.last_message_at = now
    if as_staff:
        conv.last_staff_message_at = now
        conv.staff_read_at = now
    else:
        conv.last_member_message_at = now
        conv.member_read_at = now
        # A member's reply reopens a closed conversation and ends "waiting on them".
        if conv.status == ConversationStatus.closed:
            conv.status = ConversationStatus.open
            conv.closed_at = None
            conv.closed_by_id = None
            _event(db, conv, author, "reopened")
        elif conv.status == ConversationStatus.waiting:
            conv.status = ConversationStatus.open
    return msg


def _email(to: User | None, subject: str, text: str) -> None:
    """Best effort: a failed email never undoes or fails what was saved."""
    if to is None or not to.email:
        return
    from app.adapters import email as email_adapter
    try:
        email_adapter.send_email(to.email, subject, text)
    except Exception as exc:  # noqa: BLE001
        log.warning("Conversation email not sent", extra={"extra_fields": {
            "subject": subject, "error": type(exc).__name__}})


def _site(path: str) -> str:
    from app.core.config import settings
    return f"{settings.public_site_url}{path}"


def _tell_member(db: Session, conv: Conversation, staff: User, body: str, *,
                 kind: str = "message_reply") -> None:
    if conv.member_id is None or conv.member_id == staff.id:
        return
    title = f"Bluntly replied: {TOPIC_LABEL[conv.topic]} · {conv.subject}"
    notification_service.notify(db, conv.member_id, kind, title, body=body,
                                link=_member_link(conv))


# ------------------------------------------------------------------ member side

def _own(db: Session, user: User, conversation_id: uuid.UUID, *,
         lock: bool = False) -> Conversation:
    conv = db.get(Conversation, conversation_id, with_for_update=lock)
    if conv is None or conv.member_id != user.id:
        raise NotFoundError("Conversation not found.", code="conversation_not_found")
    return conv


def list_mine(db: Session, user: User, *, seller_id: uuid.UUID | None = None,
              status: str = "open") -> MemberListOut:
    """The member's conversations. With `seller_id` (the Seller console): that
    store's conversations and the member's claims; without (Messages): all."""
    base = select(Conversation).where(Conversation.member_id == user.id)
    if seller_id is not None:
        _owns_store(db, user, seller_id)
        base = base.where(Conversation.audience == ConversationAudience.seller, or_(
            Conversation.seller_id == seller_id, Conversation.topic == ConversationTopic.claim))
    every = db.scalars(base.order_by(Conversation.last_message_at.desc())).all()
    open_ = [c for c in every if c.status in OPEN]
    closed = [c for c in every if c.status == ConversationStatus.closed]
    shown = closed if status == "closed" else open_
    return MemberListOut(
        items=_rows(db, shown[:100], "seller" if seller_id else "reviewer"),
        counts=MemberCounts(open=len(open_), closed=len(closed),
                            unread=sum(1 for c in every if _unread_for(c, False))))


def unread_for_member(db: Session, user: User, seller_id: uuid.UUID | None = None) -> int:
    stmt = select(Conversation).where(Conversation.member_id == user.id,
                                      Conversation.last_staff_message_at.is_not(None))
    if seller_id is not None:
        stmt = stmt.where(or_(Conversation.seller_id == seller_id,
                              Conversation.topic == ConversationTopic.claim),
                          Conversation.audience == ConversationAudience.seller)
    return sum(1 for c in db.scalars(stmt) if _unread_for(c, False))


def get_mine(db: Session, user: User, conversation_id: uuid.UUID) -> ConversationDetailOut:
    conv = _own(db, user, conversation_id)
    conv.member_read_at = _now()
    db.commit()
    return _detail(db, conv, "seller" if conv.audience == ConversationAudience.seller
                   and conv.topic != ConversationTopic.claim else "reviewer", user.id)


def start(db: Session, user: User, *, audience: ConversationAudience,
          seller_id: uuid.UUID | None, topic: ConversationTopic, link_type: str | None,
          link_id: uuid.UUID | None, body: str,
          file: Attachment | None = None) -> ConversationDetailOut:
    # A conversation about a linked case (a claim's proof, MQA-013) is named by
    # its link, so a file may open it alone; an unlinked one needs words.
    text = _clean(body, MAX_FIRST, file=file if link_id is not None else None)
    allowed = SELLER_TOPICS if audience == ConversationAudience.seller else REVIEWER_TOPICS
    if topic not in allowed:
        raise AppError("That topic isn't available here.", code="topic_invalid",
                       status_code=422, title="Invalid message")
    if audience == ConversationAudience.seller:
        if seller_id is None:
            raise AppError("Choose the store this is about.", code="seller_required",
                           status_code=422, title="Invalid message")
        if topic != ConversationTopic.claim:
            _owns_store(db, user, seller_id)
    else:
        seller_id = None
    if (link_type is None) != (link_id is None):
        raise AppError("A link needs both its type and its id.", code="link_invalid",
                       status_code=422, title="Invalid message")
    if link_type is not None and (link_type not in LINK_TYPES
                                  or TOPIC_LINK.get(topic) != link_type):
        raise AppError("That link doesn't fit the topic.", code="link_invalid",
                       status_code=422, title="Invalid message")
    if topic == ConversationTopic.claim and link_type is None:
        raise AppError("Choose the claim this is about.", code="link_required",
                       status_code=422, title="Invalid message")
    subject = (_check_link(db, user, audience, seller_id if topic != ConversationTopic.claim
                           else None, link_type, link_id)
               if link_type is not None and link_id is not None
               else text.splitlines()[0][:80])
    if topic == ConversationTopic.claim:
        claim = db.get(SellerClaim, link_id)
        seller_id = claim.seller_id
    viewer = "seller" if audience == ConversationAudience.seller else "reviewer"
    # A claim or an appeal already has (or gets) ONE thread, the one the
    # reviewer's case window reads; a second thread would hide this message and
    # its file from them. _check_link has made sure the case is the member's.
    case_kind = CASE_TOPICS.get(topic) if link_id is not None else None
    conv = (case_conversation(db, case_kind, link_id, user.id, create=False, lock=True)
            if case_kind else None)
    if conv is None:
        open_count = db.scalar(select(func.count()).select_from(Conversation).where(
            Conversation.member_id == user.id, Conversation.status.in_(OPEN))) or 0
        if open_count >= MAX_OPEN_PER_MEMBER:
            raise AppError("You have many open conversations. Reply in one of them, or mark "
                           "one resolved first.", code="too_many_open", status_code=429,
                           title="Too many conversations")
    with _saving(db):
        if conv is None and case_kind:
            conv = case_conversation(db, case_kind, link_id, user.id, create=True)
        elif conv is None:
            conv = Conversation(reference=f"MSG-{uuid.uuid4().hex[:8].upper()}",
                                member_id=user.id, audience=audience, seller_id=seller_id,
                                topic=topic, subject=subject[:160], link_type=link_type,
                                link_id=link_id, status=ConversationStatus.open,
                                last_message_at=_now())
            db.add(conv)
            db.flush()
        _write(db, conv, user, text, as_staff=False, file=file)
        db.commit()
    db.refresh(conv)
    return _detail(db, conv, viewer, user.id)


def reply_mine(db: Session, user: User, conversation_id: uuid.UUID, body: str,
               file: Attachment | None = None) -> ConversationMessageOut:
    conv = _own(db, user, conversation_id, lock=True)
    with _saving(db):
        msg = _write(db, conv, user, _clean(body, MAX_REPLY, file=file), as_staff=False,
                     file=file)
        _member_answered_request(db, conv, user)
        db.commit()
    db.refresh(msg)
    return _message_out(conv.id, msg, {user.id: user})


def _member_answered_request(db: Session, conv: Conversation, user: User) -> None:
    """MQA-023: the seller's reply in a request's thread puts the request back in
    review - it is the moderator's turn again."""
    if conv.support_request_id is None:
        return
    from app.services import support_service
    req = db.get(SellerSupportRequest, conv.support_request_id, with_for_update=True)
    if req is None or req.status in (SupportRequestStatus.open, SupportRequestStatus.in_review):
        return
    previous = req.status
    req.status = SupportRequestStatus.in_review
    req.resolved_at = None
    support_service._audit(db, user.id, req, "seller_replied",  # noqa: SLF001
                           previous_status=previous.value)


def resolve_mine(db: Session, user: User, conversation_id: uuid.UUID) -> ConversationDetailOut:
    """Confirm/Messages/Resolve: the member closes it; a reply opens it again."""
    conv = _own(db, user, conversation_id, lock=True)
    if conv.status != ConversationStatus.closed:
        conv.status = ConversationStatus.closed
        conv.closed_at = _now()
        conv.closed_by_id = user.id
        _event(db, conv, user, "closed")
        db.commit()
    return get_mine(db, user, conversation_id)


def email_copy(db: Session, user: User, conversation_id: uuid.UUID) -> None:
    """Sheet/Messages/More "Email me a copy" (Toast/Messages/Copy sent)."""
    conv = _own(db, user, conversation_id)
    msgs = db.scalars(select(ConversationMessage).where(
        ConversationMessage.conversation_id == conv.id,
        ConversationMessage.kind == ConversationMessageKind.message)
        .order_by(ConversationMessage.created_at)).all()
    lines = [f"{TOPIC_LABEL[conv.topic]} · {conv.subject} ({conv.reference})", ""]
    for m in msgs:
        who = "Bluntly team" if m.from_staff else "You"
        lines += [f"{who} · {_day(m.created_at)}", _said(m), ""]
    lines.append(f"Open it: {_site(_member_link(conv))}")
    from app.adapters import email as email_adapter
    try:
        email_adapter.send_email(user.email, f"Your conversation with Bluntly ({conv.reference})",
                                 "\n".join(lines))
    except Exception as exc:  # noqa: BLE001
        raise AppError("We couldn't email a copy right now. Try again later.",
                       code="email_unavailable", status_code=503,
                       title="Email unavailable") from exc


def link_options(db: Session, user: User, *, audience: ConversationAudience,
                 seller_id: uuid.UUID | None = None) -> list[LinkOptionOut]:
    """Sheet/Messages/Link and Menu/Store/Chat/Appeal: the member's own things."""
    out: list[LinkOptionOut] = []
    if audience == ConversationAudience.seller:
        if seller_id is not None:
            _owns_store(db, user, seller_id)
            for a in db.scalars(select(SellerReviewAppeal).where(
                    SellerReviewAppeal.seller_id == seller_id,
                    SellerReviewAppeal.appellant_id == user.id)
                    .order_by(SellerReviewAppeal.created_at.desc()).limit(20)):
                review = db.get(SellerReview, a.seller_review_id)
                rating = f"{float(review.overall_rating):g}★ " if review is not None else ""
                out.append(LinkOptionOut(
                    type="appeal", id=a.id, topic=ConversationTopic.appeal,
                    label=f"{_reviewer_label(db, review)}’s {rating}review",
                    sublabel=_appeal_status(a)))
        for c in db.scalars(select(SellerClaim).where(SellerClaim.user_id == user.id)
                            .order_by(SellerClaim.created_at.desc()).limit(20)):
            seller = db.get(Seller, c.seller_id)
            out.append(LinkOptionOut(
                type="claim", id=c.id, topic=ConversationTopic.claim,
                label=seller.display_name if seller else "Store claim",
                sublabel={SellerClaimStatus.pending: "In review",
                          SellerClaimStatus.claimed: "Approved",
                          SellerClaimStatus.rejected: "Not approved",
                          SellerClaimStatus.withdrawn: "Withdrawn"}.get(c.status, "")))
        return out
    for p in db.scalars(select(Payout).where(Payout.user_id == user.id)
                        .order_by(Payout.created_at.desc()).limit(10)):
        out.append(LinkOptionOut(type="payout", id=p.id, topic=ConversationTopic.payout,
                                 label=f"Payout · {_money(p.amount)}",
                                 sublabel=f"{p.status.value.capitalize()} {_day(p.updated_at)}"))
    for r in db.scalars(select(Review).where(Review.author_id == user.id,
                                             Review.published_at.is_not(None))
                        .order_by(Review.published_at.desc()).limit(20)):
        product = db.get(Product, r.product_id)
        name = product.canonical_name if product and product.canonical_name else "Product"
        out.append(LinkOptionOut(
            type="review", id=r.id, topic=ConversationTopic.review, label=f"Review · {r.title}",
            sublabel=f"{name} · posted {_day(r.published_at)}"))
    for rep in db.scalars(select(ModerationLog).where(
            ModerationLog.reporter_id == user.id, ModerationLog.action == ModerationAction.report)
            .order_by(ModerationLog.created_at.desc()).limit(10)):
        out.append(LinkOptionOut(type="report", id=rep.id, topic=ConversationTopic.report,
                                 label=f"Report · {_report_target(db, rep)}",
                                 sublabel=f"Sent {_day(rep.created_at)}"))
    return out


def attachment_url(db: Session, user: User, conversation_id: uuid.UUID,
                   message_id: uuid.UUID, *, download: bool = False) -> str:
    """A 5-minute signed link. `download` asks storage to send it as a file
    under its original name (the image viewer's Download)."""
    conv = db.get(Conversation, conversation_id)
    if conv is None or (conv.member_id != user.id and not is_staff(user)):
        raise NotFoundError("Attachment not found.", code="attachment_not_found")
    msg = db.get(ConversationMessage, message_id)
    if msg is None or msg.conversation_id != conv.id or not msg.attachment_key:
        raise NotFoundError("Attachment not found.", code="attachment_not_found")
    from app.services import storage
    url = storage.signed_attachment_url(
        msg.attachment_key, 300,
        download=(msg.attachment_name or "attachment") if download else None)
    if url is None:
        raise NotFoundError("That file is no longer available.", code="attachment_not_found")
    return url


# ------------------------------------------------------------------ edit, unsend, hide

def _party_to(db: Session, user: User, conversation_id: uuid.UUID, *, staff: bool,
              lock: bool = False) -> Conversation:
    """The conversation, if `user` is in it on this side: its member, or staff."""
    if staff:
        return _staff_get(db, conversation_id, lock=lock)
    return _own(db, user, conversation_id, lock=lock)


def _message_in(db: Session, conv: Conversation, message_id: uuid.UUID, *,
                lock: bool = False) -> ConversationMessage:
    msg = db.get(ConversationMessage, message_id, with_for_update=lock)
    if msg is None or msg.conversation_id != conv.id \
            or msg.kind != ConversationMessageKind.message:
        raise NotFoundError("Message not found.", code="message_not_found")
    return msg


def _changeable(user: User, msg: ConversationMessage, *, staff: bool) -> None:
    """MQA-011: only its sender, on the side they sent it from, within the window."""
    if msg.author_id != user.id or msg.from_staff != staff:
        raise ForbiddenError("You can only change messages you sent.",
                             code="message_not_yours")
    if msg.unsent_at is not None:
        raise AppError("That message was unsent.", code="message_unsent", status_code=409,
                       title="Conflicting state")
    if _change_until(msg) is None:
        minutes = int(CHANGE_WINDOW.total_seconds() // 60)
        raise AppError(f"A message can be edited or unsent for {minutes} minutes after "
                       "sending. Send a new message to correct it.",
                       code="message_change_closed", status_code=409,
                       title="Conflicting state")


def edit_message(db: Session, user: User, conversation_id: uuid.UUID, message_id: uuid.UUID,
                 body: str, *, staff: bool) -> ConversationMessageOut:
    """Its sender rewrites a message (MQA-011). What it said before is kept in
    `conversation_message_revisions`; the thread shows "Edited". Nothing is
    sent again: a notice or an email already sent keeps the first words."""
    conv = _party_to(db, user, conversation_id, staff=staff, lock=True)
    msg = _message_in(db, conv, message_id, lock=True)
    _changeable(user, msg, staff=staff)
    # A message that carries a file may be left with no words, as it could be sent.
    text = _clean(body, MAX_REPLY, file=Attachment(b"", msg.attachment_name or "")
                  if msg.attachment_key else None)
    if staff:
        no_template_tags(text)
    if text != msg.body:
        db.add(ConversationMessageRevision(message_id=msg.id, action="edit", body=msg.body,
                                           attachment_name=msg.attachment_name,
                                           actor_id=user.id))
        msg.body = text
        msg.edited_at = _now()
        if staff:
            _audit(db, user, conv, "message_edited", message_id=str(msg.id))
        db.commit()
        db.refresh(msg)
    return _message_out(conv.id, msg, {user.id: user})


def unsend_message(db: Session, user: User, conversation_id: uuid.UUID,
                   message_id: uuid.UUID, *, staff: bool) -> ConversationMessageOut:
    """Its sender takes a message back for everyone (MQA-011): its words and
    file leave the thread ("This message was unsent") and the file leaves
    storage. The words are kept in the revisions table as an audit record."""
    conv = _party_to(db, user, conversation_id, staff=staff, lock=True)
    msg = _message_in(db, conv, message_id, lock=True)
    _changeable(user, msg, staff=staff)
    key = msg.attachment_key
    db.add(ConversationMessageRevision(message_id=msg.id, action="unsend", body=msg.body,
                                       attachment_name=msg.attachment_name, actor_id=user.id))
    msg.body = ""
    msg.attachment_key = msg.attachment_name = msg.attachment_type = None
    msg.attachment_size = None
    msg.unsent_at = _now()
    if staff:
        _audit(db, user, conv, "message_unsent", message_id=str(msg.id))
    db.commit()
    db.refresh(msg)
    if key:
        from app.services import storage
        storage.delete_attachment_objects([key])
    return _message_out(conv.id, msg, {user.id: user})


def hide_message(db: Session, user: User, conversation_id: uuid.UUID,
                 message_id: uuid.UUID, *, staff: bool) -> None:
    """"Delete for me" (MQA-011): the message leaves this person's view of the
    thread only. Anyone in the thread may do it to any message, at any time."""
    conv = _party_to(db, user, conversation_id, staff=staff)
    msg = _message_in(db, conv, message_id)
    if db.get(ConversationMessageHide, (msg.id, user.id)) is None:
        db.add(ConversationMessageHide(message_id=msg.id, user_id=user.id))
        db.commit()


# ------------------------------------------------------------------ staff side

def _staff_get(db: Session, conversation_id: uuid.UUID, *, lock: bool = False) -> Conversation:
    conv = db.get(Conversation, conversation_id, with_for_update=lock)
    if conv is None:
        raise NotFoundError("Conversation not found.", code="conversation_not_found")
    return conv


def inbox(db: Session, staff: User, *, tab: str = "all", topic: ConversationTopic | None = None,
          status: ConversationStatus | None = None, handled: str | None = None,
          q: str | None = None, sort: str = "latest", page: int = 1,
          size: int = 25) -> InboxListOut:
    size = size if size in PAGE_SIZES else 25
    is_open = Conversation.status.in_(OPEN)
    staff_unread = and_(Conversation.last_member_message_at.is_not(None), or_(
        Conversation.staff_read_at.is_(None),
        Conversation.last_member_message_at > Conversation.staff_read_at))

    def count(*where) -> int:
        return db.scalar(select(func.count()).select_from(Conversation).where(*where)) or 0

    counts = InboxCounts(
        all=count(is_open),
        sellers=count(is_open, Conversation.audience == ConversationAudience.seller),
        reviewers=count(is_open, Conversation.audience == ConversationAudience.reviewer),
        closed=count(Conversation.status == ConversationStatus.closed),
        unread=count(is_open, staff_unread))

    stmt = select(Conversation)
    if tab == "closed":
        stmt = stmt.where(Conversation.status == ConversationStatus.closed)
    else:
        stmt = stmt.where(is_open)
        if tab == "sellers":
            stmt = stmt.where(Conversation.audience == ConversationAudience.seller)
        elif tab == "reviewers":
            stmt = stmt.where(Conversation.audience == ConversationAudience.reviewer)
    if topic is not None:
        stmt = stmt.where(Conversation.topic == topic)
    if status is not None and tab != "closed":
        stmt = stmt.where(Conversation.status == status)
    if handled == "unassigned":
        stmt = stmt.where(Conversation.assigned_admin_id.is_(None))
    elif handled == "me":
        stmt = stmt.where(Conversation.assigned_admin_id == staff.id)
    elif handled == "others":
        stmt = stmt.where(Conversation.assigned_admin_id.is_not(None),
                          Conversation.assigned_admin_id != staff.id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        member_ids = select(User.id).where(or_(User.display_name.ilike(like),
                                               User.username.ilike(like)))
        seller_ids = select(Seller.id).where(Seller.display_name.ilike(like))
        thread_ids = select(ConversationMessage.conversation_id).where(
            ConversationMessage.body.ilike(like))
        stmt = stmt.where(or_(Conversation.subject.ilike(like), Conversation.reference.ilike(like),
                              Conversation.member_id.in_(member_ids),
                              Conversation.seller_id.in_(seller_ids),
                              Conversation.id.in_(thread_ids)))
    if sort == "waiting":
        stmt = stmt.order_by(Conversation.last_member_message_at.asc().nulls_last(),
                             Conversation.last_message_at.desc())
    elif sort == "unread":
        stmt = stmt.order_by(case((staff_unread, 0), else_=1), Conversation.last_message_at.desc())
    else:
        stmt = stmt.order_by(Conversation.last_message_at.desc())
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    page = max(1, min(page, max(1, -(-total // size))))
    convs = db.scalars(stmt.offset((page - 1) * size).limit(size)).all()
    return InboxListOut(items=_rows(db, list(convs), "staff"), total=total, counts=counts)


def inbox_unread(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.status.in_(OPEN), Conversation.last_member_message_at.is_not(None),
        or_(Conversation.staff_read_at.is_(None),
            Conversation.last_member_message_at > Conversation.staff_read_at))) or 0


def staff_get(db: Session, staff: User, conversation_id: uuid.UUID) -> ConversationDetailOut:
    conv = _staff_get(db, conversation_id)
    conv.staff_read_at = _now()
    db.commit()
    return _detail(db, conv, "staff", staff.id)


def staff_reply(db: Session, staff: User, conversation_id: uuid.UUID, body: str,
                file: Attachment | None = None) -> ConversationMessageOut:
    conv = _staff_get(db, conversation_id, lock=True)
    if conv.status == ConversationStatus.closed:
        raise AppError("Reopen the conversation to reply.", code="conversation_closed",
                       status_code=409, title="Conversation closed")
    text = _clean(body, MAX_REPLY, file=file)
    no_template_tags(text)
    # What the notice and the email say when the reply is a file alone.
    said = (text or f"Sent a file: {file.name}") if file is not None else text
    with _saving(db):
        msg = _write(db, conv, staff, text, as_staff=True, file=file)
        if conv.support_request_id is not None and text:
            # The request shows the team's last reply, wherever it was written.
            req = db.get(SellerSupportRequest, conv.support_request_id)
            if req is not None:
                req.admin_response = text
                req.admin_responded_at = _now()
                if req.status == SupportRequestStatus.open:
                    req.status = SupportRequestStatus.in_review
        # A reply on a claim's or an appeal's case is that case's news (the
        # seller's Notifications → Appeals tab, and the claimant's own case line).
        _tell_member(db, conv, staff, said,
                     kind="case_message" if conv.topic in (ConversationTopic.appeal,
                                                           ConversationTopic.claim)
                     else "message_reply")
        db.commit()
    db.refresh(msg)
    member = db.get(User, conv.member_id) if conv.member_id else None
    _email(member, f"Bluntly replied: {TOPIC_LABEL[conv.topic]} · {conv.subject}",
           f"{_name(staff) or 'The Bluntly team'} wrote:\n\n{said}\n\n"
           f"Reply here: {_site(_member_link(conv))}\n({conv.reference})")
    return _message_out(conv.id, msg, {staff.id: staff})


def staff_options(db: Session) -> list[StaffOptionOut]:
    rows = db.scalars(select(User).where(User.role.in_(STAFF_ROLES))
                      .order_by(User.display_name, User.username)).all()
    return [StaffOptionOut(id=u.id, name=_name(u) or "Staff") for u in rows]


def assign(db: Session, staff: User, conversation_id: uuid.UUID,
           admin_id: uuid.UUID | None) -> ConversationDetailOut:
    conv = _staff_get(db, conversation_id, lock=True)
    if admin_id is not None:
        target = db.get(User, admin_id)
        if target is None or not is_staff(target):
            raise AppError("Only an Administrator or Super Admin can handle a conversation.",
                           code="assignee_invalid", status_code=422, title="Invalid assignee")
    conv.assigned_admin_id = admin_id
    _audit(db, staff, conv, "assigned", assignee=str(admin_id) if admin_id else "none")
    db.commit()
    return _detail(db, conv, "staff", staff.id)


def set_status(db: Session, staff: User, conversation_id: uuid.UUID,
               status: ConversationStatus) -> ConversationDetailOut:
    conv = _staff_get(db, conversation_id, lock=True)
    if conv.status == status:
        return _detail(db, conv, "staff", staff.id)
    was = conv.status
    conv.status = status
    if status == ConversationStatus.closed:
        conv.closed_at = _now()
        conv.closed_by_id = staff.id
        _event(db, conv, staff, "closed")
        if conv.member_id is not None:
            notification_service.notify(
                db, conv.member_id, "message_closed",
                f"Conversation closed: {TOPIC_LABEL[conv.topic]} · {conv.subject}",
                body="If you reply, it opens again.", link=_member_link(conv))
    elif was == ConversationStatus.closed:
        conv.closed_at = None
        conv.closed_by_id = None
        _event(db, conv, staff, "reopened")
    if conv.support_request_id is not None:
        # MQA-024: one status. Closing the thread resolves its request, waiting
        # on them waits for the seller, reopening puts it back in review.
        req = db.get(SellerSupportRequest, conv.support_request_id)
        if req is not None:
            req.status = {ConversationStatus.closed: SupportRequestStatus.resolved,
                          ConversationStatus.waiting: SupportRequestStatus.waiting_for_seller,
                          ConversationStatus.open: SupportRequestStatus.in_review}[status]
            req.resolved_at = _now() if status == ConversationStatus.closed else None
    _audit(db, staff, conv, f"status:{status.value}", previous=was.value)
    db.commit()
    if status == ConversationStatus.closed:
        member = db.get(User, conv.member_id) if conv.member_id else None
        _email(member, f"Closed: {TOPIC_LABEL[conv.topic]} · {conv.subject}",
               "The Bluntly team closed this conversation. If you reply, it opens again.\n\n"
               f"{_site(_member_link(conv))}\n({conv.reference})")
    return _detail(db, conv, "staff", staff.id)


#: Menu/Inbox/More "Move to Queue → Support": the topic's nearest category.
SUPPORT_CATEGORY = {
    ConversationTopic.appeal: SupportRequestCategory.fake_review_dispute,
    ConversationTopic.claim: SupportRequestCategory.account_claim,
    ConversationTopic.product: SupportRequestCategory.listing_product,
    ConversationTopic.account: SupportRequestCategory.account_claim,
}


def move_to_support(db: Session, staff: User, conversation_id: uuid.UUID) -> ConversationDetailOut:
    """A seller conversation becomes a support request in Queue → Support.

    The conversation STAYS the one thread (MQA-021): it is not closed (a request
    still being handled stays in the seller's Open list, MQA-024), replies from
    the request are written into it, and the seller answers there. The request
    is titled by the thread's subject and carries the seller's first message as
    they wrote it - no "Store · 5 Oct:" prefix (MQA-026)."""
    from app.models.store_change import StoreChangeRequest
    conv = _staff_get(db, conversation_id, lock=True)
    if conv.audience != ConversationAudience.seller or conv.seller_id is None:
        raise AppError("Only a store's conversation can move to Support.",
                       code="support_needs_store", status_code=422, title="Can't move")
    if conv.support_request_id is not None:
        raise AppError("This conversation is already in Support.", code="already_in_support",
                       status_code=409, title="Already moved")
    first = db.scalar(select(ConversationMessage).where(
        ConversationMessage.conversation_id == conv.id,
        ConversationMessage.kind == ConversationMessageKind.message,
        ConversationMessage.from_staff.is_(False))
        .order_by(ConversationMessage.created_at).limit(1))
    is_change = db.scalar(select(StoreChangeRequest.id).where(
        StoreChangeRequest.conversation_id == conv.id).limit(1)) is not None
    req = SellerSupportRequest(
        reference=f"SUP-{uuid.uuid4().hex[:8].upper()}", seller_id=conv.seller_id,
        created_by_id=conv.member_id,
        category=(SupportRequestCategory.store_change if is_change
                  else SUPPORT_CATEGORY.get(conv.topic, SupportRequestCategory.general)),
        subject=conv.subject[:160], message=(_said(first) if first else conv.subject),
        related_product_id=conv.link_id if conv.link_type == "product" else None,
        status=SupportRequestStatus.open, assigned_admin_id=conv.assigned_admin_id)
    db.add(req)
    db.flush()
    conv.support_request_id = req.id
    if conv.status == ConversationStatus.closed:
        conv.status = ConversationStatus.open
        conv.closed_at = None
        conv.closed_by_id = None
    _event(db, conv, staff, f"support:{req.reference}")
    _audit(db, staff, conv, "moved_to_support", support_reference=req.reference)
    db.commit()
    return _detail(db, conv, "staff", staff.id)


# ------------------------------------------------------------------ case chats

CASE_KINDS = ("claim", "appeal", "appeal-reviewer")
#: A member's own claim or appeal, started from Messages, is that case's thread.
CASE_TOPICS = {ConversationTopic.claim: "claim", ConversationTopic.appeal: "appeal"}


def case_conversation(db: Session, kind: str, case_id: uuid.UUID, member_id: uuid.UUID | None,
                      *, create: bool, lock: bool = False) -> Conversation | None:
    """The one conversation of a claim or an appeal (case_chat_service's store)."""
    key = f"{kind}:{case_id}"
    stmt = select(Conversation).where(Conversation.case_key == key)
    if lock:
        stmt = stmt.with_for_update()
    conv = db.scalar(stmt)
    if conv is not None or not create:
        return conv
    if kind == "claim":
        claim = db.get(SellerClaim, case_id)
        seller = db.get(Seller, claim.seller_id)
        conv = Conversation(audience=ConversationAudience.seller, seller_id=claim.seller_id,
                            topic=ConversationTopic.claim, subject=seller.display_name,
                            link_type="claim", link_id=claim.id)
    elif kind == "appeal":
        appeal = db.get(SellerReviewAppeal, case_id)
        review = db.get(SellerReview, appeal.seller_review_id)
        conv = Conversation(audience=ConversationAudience.seller, seller_id=appeal.seller_id,
                            topic=ConversationTopic.appeal,
                            subject=f"{_reviewer_label(db, review)}’s review",
                            link_type="appeal", link_id=appeal.id)
    else:
        appeal = db.get(SellerReviewAppeal, case_id)
        seller = db.get(Seller, appeal.seller_id)
        conv = Conversation(audience=ConversationAudience.reviewer, seller_id=None,
                            topic=ConversationTopic.review,
                            subject="Your review of "
                                    + (seller.display_name if seller else "a store"),
                            link_type="appeal", link_id=appeal.id)
    conv.reference = f"MSG-{uuid.uuid4().hex[:8].upper()}"
    conv.member_id = member_id
    conv.case_key = key
    conv.status = ConversationStatus.open
    conv.last_message_at = _now()
    db.add(conv)
    db.flush()
    return conv


def case_write(db: Session, conv: Conversation, author: User, body: str) -> ConversationMessage:
    """A case chat message: written like any other, without the Inbox's email
    (the case chat sends its own notification)."""
    as_staff = is_staff(author) and author.id != conv.member_id
    if as_staff:
        no_template_tags(body)
    return _write(db, conv, author, body, as_staff=as_staff)


def case_messages(db: Session, conv: Conversation | None) -> list[ConversationMessage]:
    if conv is None:
        return []
    return list(db.scalars(select(ConversationMessage).where(
        ConversationMessage.conversation_id == conv.id,
        ConversationMessage.kind == ConversationMessageKind.message)
        .order_by(ConversationMessage.created_at, ConversationMessage.id)))

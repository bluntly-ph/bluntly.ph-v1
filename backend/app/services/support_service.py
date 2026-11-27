"""Seller support requests (owner decision 2026-09-28).

The store's approved owner writes to the administrators about their store; an
administrator reads it, claims it, answers, and moves it through

    open -> in_review -> resolved | rejected

Nothing here lets a seller act on content. A request is words and a status;
what follows — a takedown, a substantiation request, nothing — is an
administrator's separate, separately audited action.

Every state change is audited (`ModerationAction.support_request`, the event in
the context) and the seller is notified of each answer and status change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import ModerationAction, SupportRequestStatus
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review
from app.models.seller import Seller, SellerReview
from app.models.support import SellerSupportRequest
from app.models.user import User
from app.schemas.support import (
    AdminSupportRequestOut,
    SupportRequestCreate,
    SupportRequestOut,
)
from app.services import notification_service
from app.services.seller_service import require_store_owner

CLOSED = (SupportRequestStatus.resolved, SupportRequestStatus.rejected)

#: The words the seller and the team both see for a status (MQA-024: one status,
#: the same words in Messages and on the request).
STATUS_WORDS = {
    SupportRequestStatus.open: "Open",
    SupportRequestStatus.in_review: "In review",
    SupportRequestStatus.waiting_for_seller: "Waiting for you",
    SupportRequestStatus.resolved: "Resolved",
    SupportRequestStatus.rejected: "Rejected",
}

#: MQA-022: what a reply does next, chosen once, when replying.
REPLY_ACTIONS = {
    "ask": SupportRequestStatus.waiting_for_seller,
    "review": SupportRequestStatus.in_review,
    "resolve": SupportRequestStatus.resolved,
}


def linked_conversation(db: Session, req: SellerSupportRequest):
    """The Messages thread a request was moved from, if any (MQA-021: one
    thread, one history - the request is that thread, not a copy of it)."""
    from app.models.conversation import Conversation
    return db.scalar(select(Conversation).where(Conversation.support_request_id == req.id))


def _conversation_ids(db: Session, request_ids) -> dict[uuid.UUID, uuid.UUID]:
    from app.models.conversation import Conversation
    ids = list(request_ids)
    if not ids:
        return {}
    return dict(db.execute(select(Conversation.support_request_id, Conversation.id).where(
        Conversation.support_request_id.in_(ids))).all())


def mirror_to_conversation(req: SellerSupportRequest, conv) -> None:
    """The thread shows the request's state: waiting for the seller reads as
    waiting on them, resolved or rejected closes it, anything else is open -
    so a request still being handled stays in the seller's Open list (MQA-024)."""
    from app.models.enums import ConversationStatus
    if conv is None:
        return
    if req.status in CLOSED:
        if conv.status != ConversationStatus.closed:
            conv.status = ConversationStatus.closed
            conv.closed_at = _now()
    elif req.status == SupportRequestStatus.waiting_for_seller:
        conv.status = ConversationStatus.waiting
        conv.closed_at = None
        conv.closed_by_id = None
    else:
        conv.status = ConversationStatus.open
        conv.closed_at = None
        conv.closed_by_id = None
MAX_LIST = 200


def _now() -> datetime:
    return datetime.now(UTC)


def _audit(db: Session, actor_id: uuid.UUID | None, req: SellerSupportRequest, event: str,
           **extra) -> None:
    context = {"event": event, "reference": req.reference, "seller_id": str(req.seller_id),
               "status": req.status.value}
    context.update({k: v for k, v in extra.items() if v is not None})
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=actor_id,
                         action=ModerationAction.support_request, target_ref=req.id,
                         notes=f"support {event}", context=context))


def _out(req: SellerSupportRequest, seller_name: str | None,
         conversation_id: uuid.UUID | None = None) -> SupportRequestOut:
    return SupportRequestOut(
        conversation_id=conversation_id,
        id=req.id, reference=req.reference, seller_id=req.seller_id, seller_name=seller_name,
        category=req.category, subject=req.subject, message=req.message,
        related_seller_review_id=req.related_seller_review_id,
        related_review_id=req.related_review_id, related_product_id=req.related_product_id,
        status=req.status, admin_response=req.admin_response,
        admin_responded_at=req.admin_responded_at, created_at=req.created_at,
        updated_at=req.updated_at, resolved_at=req.resolved_at)


def _admin_out(db: Session, req: SellerSupportRequest, seller_name: str | None = None,
               users: dict[uuid.UUID, User] | None = None,
               conversations: dict[uuid.UUID, uuid.UUID] | None = None) -> AdminSupportRequestOut:
    """`users` and `conversations` are the queue's batched loads; a single read
    may omit them."""
    conv_id = (conversations.get(req.id) if conversations is not None
               else _conversation_ids(db, [req.id]).get(req.id))
    base = _out(req, seller_name, conv_id).model_dump()

    def _user(uid: uuid.UUID | None) -> User | None:
        if uid is None:
            return None
        return users.get(uid) if users is not None else db.get(User, uid)

    creator = _user(req.created_by_id)
    admin = _user(req.assigned_admin_id)
    return AdminSupportRequestOut(
        **base,
        created_by=f"@{creator.username}" if creator and creator.username else None,
        assigned_admin=(admin.display_name or admin.username) if admin else None,
        assigned_admin_id=req.assigned_admin_id, internal_note=req.internal_note)


# ------------------------------------------------------------------ seller side

def create(db: Session, seller: Seller, user: User,
           payload: SupportRequestCreate) -> SupportRequestOut:
    require_store_owner(seller, user)
    if payload.related_seller_review_id is not None:
        related = db.get(SellerReview, payload.related_seller_review_id)
        # Only a review OF THIS STORE: a seller cannot file about another
        # store's reviews through their own support channel.
        if related is None or related.seller_id != seller.id:
            raise NotFoundError("That review is not one of this store's.",
                                code="seller_review_not_found")
    if payload.related_review_id is not None:
        review = db.get(Review, payload.related_review_id)
        if review is None or review.is_removed:
            raise NotFoundError("Review not found.", code="review_not_found")
    if payload.related_product_id is not None \
            and db.get(Product, payload.related_product_id) is None:
        raise NotFoundError("Product not found.", code="product_not_found")
    req = SellerSupportRequest(
        reference=f"SUP-{uuid.uuid4().hex[:8].upper()}", seller_id=seller.id,
        created_by_id=user.id, category=payload.category, subject=payload.subject,
        message=payload.message, related_seller_review_id=payload.related_seller_review_id,
        related_review_id=payload.related_review_id,
        related_product_id=payload.related_product_id, status=SupportRequestStatus.open)
    db.add(req)
    db.flush()
    _audit(db, user.id, req, "created", category=payload.category.value)
    db.commit()
    db.refresh(req)
    return _out(req, seller.display_name)


def list_for_store(db: Session, seller: Seller, user: User) -> list[SupportRequestOut]:
    require_store_owner(seller, user)
    rows = db.scalars(select(SellerSupportRequest)
                      .where(SellerSupportRequest.seller_id == seller.id)
                      .order_by(SellerSupportRequest.created_at.desc()).limit(MAX_LIST)).all()
    convs = _conversation_ids(db, [r.id for r in rows])
    return [_out(r, seller.display_name, convs.get(r.id)) for r in rows]


def get_for_store(db: Session, seller: Seller, user: User,
                  request_id: uuid.UUID) -> SupportRequestOut:
    require_store_owner(seller, user)
    req = db.get(SellerSupportRequest, request_id)
    # Another store's request, asked for through this store's path, is simply
    # not here — the same 404 as one that never existed.
    if req is None or req.seller_id != seller.id:
        raise NotFoundError("Support request not found.", code="support_request_not_found")
    return _out(req, seller.display_name, _conversation_ids(db, [req.id]).get(req.id))


def open_count(db: Session, seller_id: uuid.UUID) -> int:
    from sqlalchemy import func
    return db.scalar(select(func.count(SellerSupportRequest.id)).where(
        SellerSupportRequest.seller_id == seller_id,
        SellerSupportRequest.status.not_in(CLOSED))) or 0


# ------------------------------------------------------------------ staff side

def _get(db: Session, request_id: uuid.UUID, *, lock: bool = False) -> SellerSupportRequest:
    stmt = select(SellerSupportRequest).where(SellerSupportRequest.id == request_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    req = db.scalar(stmt)
    if req is None:
        raise NotFoundError("Support request not found.", code="support_request_not_found")
    return req


def _seller_names(db: Session, ids) -> dict:
    ids = list(set(ids))
    if not ids:
        return {}
    return dict(db.execute(select(Seller.id, Seller.display_name).where(Seller.id.in_(ids))).all())


def admin_list(db: Session, status: SupportRequestStatus | None = None,
               limit: int = 100) -> list[AdminSupportRequestOut]:
    """Waiting requests first, oldest first; then closed ones, newest first.

    Ordered that way so a long tail of closed requests can never push a
    waiting one past the limit. Three queries whatever the page size: the
    requests, their stores' names and every creator/assignee at once.
    """
    stmt = select(SellerSupportRequest)
    if status is not None:
        stmt = stmt.where(SellerSupportRequest.status == status)
    closed = SellerSupportRequest.status.in_(CLOSED)
    rows = db.scalars(stmt.order_by(
        case((closed, 1), else_=0),
        case((closed, None), else_=SellerSupportRequest.created_at).asc(),
        SellerSupportRequest.updated_at.desc()).limit(min(limit, MAX_LIST))).all()
    names = _seller_names(db, [r.seller_id for r in rows])
    user_ids = {uid for r in rows for uid in (r.created_by_id, r.assigned_admin_id) if uid}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))} \
        if user_ids else {}
    convs = _conversation_ids(db, [r.id for r in rows])
    return [_admin_out(db, r, names.get(r.seller_id), users, convs) for r in rows]


def admin_get(db: Session, request_id: uuid.UUID) -> AdminSupportRequestOut:
    req = _get(db, request_id)
    return _admin_out(db, req, _seller_names(db, [req.seller_id]).get(req.seller_id))


def _tell_seller(db: Session, req: SellerSupportRequest, title: str, body: str | None,
                 conv=None) -> None:
    """One sender ("Bluntly") and a subject the seller recognises; the code only
    in small print (MQA-026/029). A request moved from Messages opens its
    thread, where the seller can answer (MQA-021/023)."""
    from app.services import conversation_service
    seller = db.get(Seller, req.seller_id)
    recipient = seller.claimed_by_id if seller is not None else req.created_by_id
    link = (conversation_service.member_link(conv) if conv is not None
            else f"/sellers/{req.seller_id}/support/{req.id}")
    small = f"Request {req.reference}"
    notification_service.notify(db, recipient, "support_request", title,
                                body=f"{body}\n\n{small}" if body else small, link=link)


def _set_status(req: SellerSupportRequest, status: SupportRequestStatus) -> None:
    req.status = status
    req.resolved_at = _now() if status in CLOSED else None


def assign(db: Session, request_id: uuid.UUID, admin: User) -> AdminSupportRequestOut:
    req = _get(db, request_id, lock=True)
    if req.status in CLOSED:
        raise AppError("A closed request can't be assigned.", code="support_request_closed",
                       status_code=409, title="Conflicting state")
    previous = req.status
    req.assigned_admin_id = admin.id
    if req.status == SupportRequestStatus.open:
        _set_status(req, SupportRequestStatus.in_review)
    _audit(db, admin.id, req, "assigned", previous_status=previous.value)
    if previous != req.status:
        conv = linked_conversation(db, req)
        mirror_to_conversation(req, conv)
        _tell_seller(db, req, f"Bluntly is reviewing your request: {req.subject}", None, conv)
    db.commit()
    return admin_get(db, req.id)


def respond(db: Session, request_id: uuid.UUID, admin: User, response: str,
            status: SupportRequestStatus | None,
            action: str | None = None) -> AdminSupportRequestOut:
    """Answer the seller. `action` (MQA-022) says what happens next in one
    choice: ask for more (waiting for the seller), keep in review, or resolve.
    The reply goes into the request's Messages thread too, so the seller reads
    it where they can answer (MQA-021)."""
    from app.services import conversation_service
    conversation_service.no_template_tags(response)   # MQA-028
    req = _get(db, request_id, lock=True)
    previous = req.status
    req.admin_response = response.strip()
    req.admin_responded_at = _now()
    if req.assigned_admin_id is None:
        req.assigned_admin_id = admin.id
    target = REPLY_ACTIONS.get(action) if action else status
    if target is not None:
        _set_status(req, target)
    elif req.status == SupportRequestStatus.open:
        _set_status(req, SupportRequestStatus.in_review)
    conv = linked_conversation(db, req)
    if conv is not None:
        conversation_service._write(db, conv, admin, req.admin_response,  # noqa: SLF001
                                    as_staff=True)
        mirror_to_conversation(req, conv)
    _audit(db, admin.id, req, "responded", previous_status=previous.value,
           action=action)
    waiting = req.status == SupportRequestStatus.waiting_for_seller
    _tell_seller(db, req,
                 f"Bluntly replied: {req.subject}" + (" · your reply is needed" if waiting else ""),
                 req.admin_response, conv)
    db.commit()
    return admin_get(db, req.id)


def set_status(db: Session, request_id: uuid.UUID, admin: User, status: SupportRequestStatus,
               internal_note: str | None) -> AdminSupportRequestOut:
    req = _get(db, request_id, lock=True)
    previous = req.status
    _set_status(req, status)
    if internal_note is not None:
        req.internal_note = internal_note.strip() or None
    if req.assigned_admin_id is None:
        req.assigned_admin_id = admin.id
    _audit(db, admin.id, req, "status", previous_status=previous.value)
    if previous != status:
        conv = linked_conversation(db, req)
        mirror_to_conversation(req, conv)
        _tell_seller(db, req, f"{req.subject}: {STATUS_WORDS[status].lower()}", None, conv)
    db.commit()
    return admin_get(db, req.id)

"""Store change requests (MQA-017/018/019/020/025).

A claimed store's owner asks for one or more changes - its name, its link, its
registration - in one go. They land as one conversation in the admin Inbox
(MQA-018: not one thread per change) and as one row per change, each with the
value the store had, the value asked for and a status. A moderator approves or
rejects each; approving APPLIES it to the store (MQA-019/025), records the old
and new values in the Activity log, and tells the owner in the same thread.

MQA-020: a store's link must be on the store's own marketplace - checked when
the change is asked for, again when it is approved, and before a claim is
approved (seller_service.decide_claim uses `link_mismatch`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import (
    ConversationAudience,
    ConversationTopic,
    ModerationAction,
    Platform,
    SellerClaimStatus,
)
from app.models.moderation import ModerationLog
from app.models.seller import Seller, SellerClaim
from app.models.store_change import CHANGE_FIELDS, StoreChangeRequest
from app.models.user import User

FIELD_LABEL = {
    "display_name": "Store name",
    "store_url": "Store link",
    "registration": "Registration details",
}
PLATFORM_LABEL = {"shopee": "Shopee", "lazada": "Lazada", "amazon": "Amazon",
                  "other": "another site"}
NOTE_MAX = 300


@dataclass(frozen=True)
class ChangeIn:
    field: str
    value: str
    #: Registration only: "dti" or "sec".
    kind: str | None = None


def link_mismatch(platform: Platform, url: str | None) -> str | None:
    """Why `url` cannot be this store's link, or None when it can (MQA-020).

    Only a link on ANOTHER known marketplace is refused - a Shopee store with a
    lazada.com.ph link. A link on no marketplace we know is left to the
    moderator, who opens it before approving."""
    from app.services.canonical_service import marketplace_for_url
    if not url:
        return None
    on = marketplace_for_url(url)
    if on is None or platform == Platform.other or on == platform:
        return None
    return (f"That link is a {PLATFORM_LABEL[on.value]} page, but this store is on "
            f"{PLATFORM_LABEL[platform.value]}.")


def _registration(seller: Seller, db: Session) -> SellerClaim | None:
    """The approved claim that holds the store's registration."""
    return db.scalar(select(SellerClaim).where(
        SellerClaim.seller_id == seller.id,
        SellerClaim.status == SellerClaimStatus.claimed,
    ).order_by(SellerClaim.decided_at.desc().nullslast()).limit(1))


def _current(db: Session, seller: Seller, field: str) -> str | None:
    if field == "display_name":
        return seller.display_name
    if field == "store_url":
        return seller.store_url
    claim = _registration(seller, db)
    if claim is None or not claim.registration_number:
        return None
    return f"{(claim.registration_kind or 'dti')}:{claim.registration_number}"


def _clean(db: Session, seller: Seller, change: ChangeIn) -> str:
    """The value to store for one change, or a 422 that says what is wrong."""
    from app.schemas.urls import web_url_or_none
    from app.services.seller_service import normalize_seller_name

    def bad(msg: str, code: str = "change_invalid") -> AppError:
        return AppError(msg, code=code, status_code=422, title="Invalid change")

    value = (change.value or "").strip()
    if change.field not in CHANGE_FIELDS:
        raise bad("That can't be changed here.")
    if change.field == "display_name":
        if not 2 <= len(value) <= 160:
            raise bad("A store name is 2 to 160 characters.")
        try:
            normalize_seller_name(value)
        except ValueError as exc:
            raise bad(str(exc)) from exc
        if value == seller.display_name:
            raise bad("That is already the store's name.")
        return value
    if change.field == "store_url":
        try:
            url = web_url_or_none(value, field="Store links")
        except ValueError as exc:
            raise bad(str(exc)) from exc
        if not url:
            raise bad("Paste the store's link.")
        if len(url) > 2000:
            raise bad("That link is too long.")
        problem = link_mismatch(seller.platform, url)
        if problem:
            raise bad(problem, "store_link_mismatch")
        if url == seller.store_url:
            raise bad("That is already the store's link.")
        return url
    # registration
    from app.core.registration_format import format_error
    kind = (change.kind or "").lower()
    if kind not in ("dti", "sec"):
        raise bad("Say whether it is a DTI or an SEC registration.")
    problem = format_error(kind, value)
    if problem:
        raise bad(problem)
    return f"{kind}:{value}"   # stored as entered (trimmed), as a claim stores it


def display(field: str, value: str | None) -> str | None:
    """A stored value as a person reads it: "DTI 3318207"."""
    if value is None or field != "registration":
        return value
    kind, _, number = value.partition(":")
    return f"{kind.upper()} {number}"


def submit(db: Session, user: User, seller_id: uuid.UUID, changes: list[ChangeIn],
           note: str | None, file=None) -> tuple[uuid.UUID, list[StoreChangeRequest]]:
    """One request, one conversation, one row per change (MQA-017/018)."""
    from app.services import conversation_service as conv_svc

    seller = conv_svc._owns_store(db, user, seller_id)  # noqa: SLF001 - the one owner rule
    if not changes:
        raise AppError("Choose at least one change.", code="change_empty", status_code=422,
                       title="Invalid change")
    if len({c.field for c in changes}) != len(changes):
        raise AppError("Each change can be asked once per request.", code="change_repeated",
                       status_code=422, title="Invalid change")
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise AppError(f"The note is at most {NOTE_MAX} characters.", code="change_note_long",
                       status_code=422, title="Invalid change")
    cleaned = [(c.field, _clean(db, seller, c)) for c in changes]
    waiting = set(db.scalars(select(StoreChangeRequest.field).where(
        StoreChangeRequest.seller_id == seller.id, StoreChangeRequest.status == "pending")))
    clash = [f for f, _ in cleaned if f in waiting]
    if clash:
        raise AppError(f"A {FIELD_LABEL[clash[0]].lower()} change is already waiting for a "
                       "moderator. You'll hear back in Messages.", code="change_pending",
                       status_code=409, title="Change already waiting")

    # The first line names the request (the thread's title); the rest is exactly
    # what the owner entered (MQA-026).
    labels = [FIELD_LABEL[f] for f, _ in cleaned]
    labels = labels[:1] + [label.lower() for label in labels[1:]]
    title = (labels[0] if len(labels) == 1 else
             ", ".join(labels[:-1]) + " and " + labels[-1]) + " change"
    body = "\n".join([title, ""]
                     + [f"{FIELD_LABEL[f]}: {display(f, v)}" for f, v in cleaned]
                     + ([f"\n{note}"] if note else []))
    detail = conv_svc.start(db, user, audience=ConversationAudience.seller, seller_id=seller.id,
                            topic=ConversationTopic.account, link_type=None, link_id=None,
                            body=body, file=file)
    rows = [StoreChangeRequest(seller_id=seller.id, requested_by_id=user.id,
                               conversation_id=detail.id, field=f,
                               current_value=_current(db, seller, f), requested_value=v)
            for f, v in cleaned]
    db.add_all(rows)
    try:
        db.commit()
    except IntegrityError as exc:  # a second request for the same field won the race
        db.rollback()
        raise AppError("That change is already waiting for a moderator.",
                       code="change_pending", status_code=409,
                       title="Change already waiting") from exc
    for r in rows:
        db.refresh(r)
    return detail.id, rows


def for_conversation(db: Session, conversation_id: uuid.UUID) -> list[StoreChangeRequest]:
    return list(db.scalars(select(StoreChangeRequest).where(
        StoreChangeRequest.conversation_id == conversation_id)
        .order_by(StoreChangeRequest.created_at, StoreChangeRequest.field)))


def for_store(db: Session, seller_id: uuid.UUID, limit: int = 20) -> list[StoreChangeRequest]:
    return list(db.scalars(select(StoreChangeRequest).where(
        StoreChangeRequest.seller_id == seller_id)
        .order_by(StoreChangeRequest.created_at.desc()).limit(limit)))


def _apply(db: Session, seller: Seller, row: StoreChangeRequest) -> str | None:
    """Write the change to the store; return the value it replaced."""
    from app.services.seller_service import normalize_seller_name

    if row.field == "display_name":
        key = normalize_seller_name(row.requested_value)
        other = db.scalar(select(Seller.id).where(
            Seller.platform == seller.platform, Seller.normalized_name == key,
            Seller.id != seller.id))
        if other is not None:
            raise AppError("Another store on this marketplace already has that name.",
                           code="store_name_taken", status_code=409, title="Name taken")
        old = seller.display_name
        seller.display_name = row.requested_value
        seller.normalized_name = key
        return old
    if row.field == "store_url":
        problem = link_mismatch(seller.platform, row.requested_value)
        if problem:
            raise AppError(problem, code="store_link_mismatch", status_code=409,
                           title="Link on another marketplace")
        old = seller.store_url
        seller.store_url = row.requested_value
        return old
    claim = _registration(seller, db)
    if claim is None:
        raise AppError("This store has no approved claim to update.", code="no_claim",
                       status_code=409, title="No registration")
    old = _current(db, seller, "registration")
    kind, _, number = row.requested_value.partition(":")
    claim.registration_kind = kind
    claim.registration_number = number
    return old


def decide(db: Session, staff: User, request_id: uuid.UUID, decision: str,
           note: str | None) -> StoreChangeRequest:
    """Approve (apply it) or reject one change; tell the owner in its thread."""
    from app.models.conversation import Conversation
    from app.services import conversation_service as conv_svc
    from app.services import notification_service

    row = db.get(StoreChangeRequest, request_id, with_for_update=True)
    if row is None:
        raise NotFoundError("Change request not found.", code="change_not_found")
    if row.status != "pending":
        raise AppError("This change has already been decided.", code="change_decided",
                       status_code=409, title="Already decided")
    note = (note or "").strip() or None
    if decision == "reject" and not note:
        raise AppError("Say why, so the owner knows what to do next.", code="reason_required",
                       status_code=422, title="Reason required")
    seller = db.get(Seller, row.seller_id, with_for_update=True)
    old = _apply(db, seller, row) if decision == "approve" else None
    row.status = "approved" if decision == "approve" else "rejected"
    row.decided_by_id = staff.id
    row.decided_at = datetime.now(UTC)
    row.decision_note = note
    label = FIELD_LABEL[row.field]
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=staff.id,
        action=ModerationAction.approve if decision == "approve" else ModerationAction.reject,
        target_type=None, target_ref=seller.id, notes=note,
        context={"store_change_id": str(row.id), "field": row.field,
                 "old": display(row.field, old) if decision == "approve" else None,
                 "new": display(row.field, row.requested_value),
                 "outcome": f"store_change_{row.status}"}))
    said = (f"{label} change approved: it is now {display(row.field, row.requested_value)}."
            if decision == "approve" else f"{label} change not approved.")
    if note:
        said += f"\n\n{note}"
    conv = db.get(Conversation, row.conversation_id) if row.conversation_id else None
    if conv is not None:
        conv_svc._write(db, conv, staff, said, as_staff=True)  # noqa: SLF001
    if row.requested_by_id:
        notification_service.notify(
            db, row.requested_by_id,
            "store_change_approved" if decision == "approve" else "store_change_rejected",
            f"Your {label.lower()} change was "
            + ("approved" if decision == "approve" else "not approved"),
            body=said,
            link=(f"/seller/{seller.id}/messages?c={conv.id}" if conv is not None
                  else f"/seller/{seller.id}/profile"))
    db.commit()
    db.refresh(row)
    return row


def staff_edit(db: Session, staff: User, seller_id: uuid.UUID, change: ChangeIn,
               note: str | None) -> StoreChangeRequest:
    """A moderator corrects a store directly (MQA-020: a link on the wrong
    marketplace that would otherwise block its claim). Recorded as a change
    request a moderator made and approved, so the store has one history."""
    seller = db.get(Seller, seller_id, with_for_update=True)
    if seller is None:
        raise NotFoundError("Store not found.", code="seller_not_found")
    value = _clean(db, seller, change)
    row = StoreChangeRequest(seller_id=seller.id, requested_by_id=staff.id, field=change.field,
                             current_value=_current(db, seller, change.field),
                             requested_value=value, status="approved", decided_by_id=staff.id,
                             decided_at=datetime.now(UTC),
                             decision_note=(note or "").strip() or None)
    old = _apply(db, seller, row)
    db.add(row)
    db.flush()
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=staff.id,
        action=ModerationAction.approve, target_type=None, target_ref=seller.id,
        notes=row.decision_note,
        context={"store_change_id": str(row.id), "field": row.field,
                 "old": display(row.field, old), "new": display(row.field, value),
                 "outcome": "store_change_approved", "by_staff": True}))
    db.commit()
    db.refresh(row)
    return row

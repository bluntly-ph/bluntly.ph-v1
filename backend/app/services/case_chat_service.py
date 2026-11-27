"""Chat on a seller claim or a review appeal (meeting 2026-10-02, 11:40: "chat
in case we want to know more ... let's include it").

Two parties per case: the member who filed it (the claimant, or the store
owner who appealed) and staff (an Administrator or a Super Admin). Nobody else
can read or write a thread, which is checked here, not by the caller.

Stored as ONE Inbox conversation per case since 0076 (owner decision
2026-10-03, "merge into Inbox"): `conversations.case_key` is `claim:<id>`,
`appeal:<id>` or `appeal-reviewer:<id>`, so the case overlays and the Inbox read
and write the same thread. (Before 0076: one `platform_settings` row per case;
0076 copied those rows in and left them in place.) Capped at MAX_MESSAGES.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.security import is_staff
from app.models.seller import SellerClaim, SellerReview, SellerReviewAppeal
from app.models.user import User
from app.services import conversation_service, notification_service

#: "appeal-reviewer" is the appeal's second thread (Figma 7996:11826, Seller /
#: Reviewer): staff and the review's author. Its first staff message is the
#: request to back the review up; the reviewer's reply is their answer.
KINDS = ("claim", "appeal", "appeal-reviewer")
MAX_MESSAGES = 200
MAX_LENGTH = 2000


@dataclass(frozen=True)
class ChatMessage:
    id: str
    author_id: uuid.UUID | None
    author_name: str | None
    from_staff: bool
    body: str
    sent_at: datetime
    #: A file sent in the case's Inbox thread (private bucket; a signed link on
    #: request), so the claim / appeal window can list it as evidence.
    attachment: Any = None


def _case(db: Session, kind: str, case_id: uuid.UUID) -> tuple[uuid.UUID | None, str]:
    """(the member party, the link to the case for that member)."""
    if kind == "claim":
        claim = db.get(SellerClaim, case_id)
        if claim is None:
            raise NotFoundError("Claim not found.", code="claim_not_found")
        return claim.user_id, f"/sellers/{claim.seller_id}"
    if kind == "appeal":
        appeal = db.get(SellerReviewAppeal, case_id)
        if appeal is None:
            raise NotFoundError("Appeal not found.", code="appeal_not_found")
        return appeal.appellant_id, f"/sellers/{appeal.seller_id}/dashboard"
    if kind == "appeal-reviewer":
        appeal = db.get(SellerReviewAppeal, case_id)
        review = db.get(SellerReview, appeal.seller_review_id) if appeal is not None else None
        if appeal is None or review is None:
            raise NotFoundError("Appeal not found.", code="appeal_not_found")
        return review.reviewer_id, f"/sellers/appeals/{appeal.id}"
    raise NotFoundError("Unknown case.", code="case_not_found")


def _authorise(db: Session, kind: str, case_id: uuid.UUID,
               user: User) -> tuple[uuid.UUID | None, str]:
    member, link = _case(db, kind, case_id)
    if not is_staff(user) and user.id != member:
        raise ForbiddenError("Only the people on this case can read its messages.",
                             code="not_case_party")
    return member, link


def _name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or (f"@{user.username}" if user.username else None)


def _out(m, users: dict) -> ChatMessage:
    return ChatMessage(id=m.legacy_id or m.id.hex[:12], author_id=m.author_id,
                       author_name=_name(users.get(m.author_id)) if m.author_id else None,
                       from_staff=m.from_staff,
                       # MQA-011: a message its sender took back says so here too.
                       body="This message was unsent." if m.unsent_at else m.body,
                       sent_at=m.created_at,
                       attachment=conversation_service.attachment_out(m.conversation_id, m))


def messages(db: Session, kind: str, case_id: uuid.UUID, user: User) -> list[ChatMessage]:
    member, _ = _authorise(db, kind, case_id, user)
    conv = conversation_service.case_conversation(db, kind, case_id, member, create=False)
    rows = conversation_service.case_messages(db, conv)
    ids = {m.author_id for m in rows if m.author_id}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids))} if ids else {}
    return [_out(m, users) for m in rows]


def send(db: Session, kind: str, case_id: uuid.UUID, user: User, body: str) -> ChatMessage:
    member, link = _authorise(db, kind, case_id, user)
    text = (body or "").strip()
    if not text or len(text) > MAX_LENGTH:
        raise AppError(f"A message is 1 to {MAX_LENGTH} characters.", code="chat_message_invalid",
                       status_code=422, title="Invalid message")
    conv = conversation_service.case_conversation(db, kind, case_id, member, create=True,
                                                  lock=True)
    count = len(conversation_service.case_messages(db, conv))
    if count >= MAX_MESSAGES:
        raise AppError("This conversation is full; continue by support request.",
                       code="chat_full", status_code=422, title="Invalid message")
    staff = is_staff(user)
    msg = conversation_service.case_write(db, conv, user, text)
    # The reviewer thread drives the existing substantiation states, so the
    # appeal's status (Not asked / Waiting / Answered) and its removal lock
    # read the same record whichever screen wrote it.
    substantiation = None
    if kind == "appeal-reviewer":
        appeal = db.get(SellerReviewAppeal, case_id)
        if staff and appeal.status == "open":
            substantiation = ("request", text)
        elif not staff and appeal.status == "substantiation_requested" \
                and appeal.substantiated_at is None:
            substantiation = ("answer", text)
    if staff and member is not None and member != user.id and substantiation is None:
        # MQA-027: the notice opens the case's conversation (the claim's thread
        # in Messages), not the store's page. The reviewer's side of an appeal
        # keeps its own page, where the substantiation form is.
        notification_service.notify(
            db, member, "case_message",
            "Bluntly replied about your " + ("store claim" if kind == "claim" else "appeal"),
            body=text,
            link=link if kind == "appeal-reviewer" else conversation_service.member_link(conv))
    db.commit()
    db.refresh(msg)
    if substantiation is not None:
        from app.services import seller_service
        if substantiation[0] == "request":
            seller_service.request_substantiation(db, case_id, user, substantiation[1])
        else:
            seller_service.substantiate(db, case_id, user, substantiation[1])
    return _out(msg, {user.id: user})

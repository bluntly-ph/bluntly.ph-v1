"""The Inbox and Messages (0076; Figma Screen/Admin/Inbox, Screen/Seller/Inbox,
Screen/Messages)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models.enums import (
    ConversationAudience,
    ConversationMessageKind,
    ConversationStatus,
    ConversationTopic,
)


class ConversationPartyOut(BaseModel):
    id: uuid.UUID | None = None
    name: str | None = None
    trust_stage: int | None = None
    avatar_url: str | None = None


class ConversationAttachmentOut(BaseModel):
    name: str
    type: str
    size: int | None = None
    #: An API path that answers with a short-lived signed URL (never the object).
    href: str


class ConversationMessageOut(BaseModel):
    id: uuid.UUID
    kind: ConversationMessageKind
    from_staff: bool
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    #: Events: closed | reopened | support:<reference>. Messages: the text.
    body: str
    created_at: datetime
    attachment: ConversationAttachmentOut | None = None
    #: MQA-011: when its sender last edited it ("Edited").
    edited_at: datetime | None = None
    #: Its sender unsent it: the words and file are gone ("This message was unsent").
    unsent: bool = False
    #: Until when its sender may still edit or unsend it (null: no longer).
    change_until: datetime | None = None


class ConversationLinkOut(BaseModel):
    type: Literal["appeal", "claim", "payout", "review", "report", "product"]
    id: uuid.UUID
    #: "Appeal on Rico T.'s 2★ review", "Payout ₱509.50".
    label: str
    #: "Proof requested, due 10 Oct", "Failed on 3 Oct: PayPal returned the payment".
    status: str | None = None
    #: Where "Open appeal" / "View" goes, for this viewer (None: nowhere to go).
    href: str | None = None
    action: str | None = None


class ConversationRowOut(BaseModel):
    id: uuid.UUID
    reference: str
    audience: ConversationAudience
    topic: ConversationTopic
    subject: str
    status: ConversationStatus
    seller_id: uuid.UUID | None = None
    seller_name: str | None = None
    #: The store's marketplace ("shopee"), for the Inbox's reply templates (MQA-028).
    seller_platform: str | None = None
    member: ConversationPartyOut
    assigned_admin: ConversationPartyOut | None = None
    last_message_at: datetime
    preview: str | None = None
    preview_from_staff: bool = False
    #: For the viewer: the other side wrote since the viewer last opened it.
    unread: bool = False
    link: ConversationLinkOut | None = None
    closed_at: datetime | None = None
    support_reference: str | None = None


class ConversationMemberSummary(BaseModel):
    """The header line under the member's name in the Inbox."""

    role: Literal["seller", "reviewer"]
    #: "Store owner" / "Claimant" for a seller; the trust level for a reviewer.
    label: str
    store_name: str | None = None
    reviews: int | None = None
    earned: Decimal | None = None


class ConversationDetailOut(ConversationRowOut):
    messages: list[ConversationMessageOut]
    closed_by: ConversationPartyOut | None = None
    member_summary: ConversationMemberSummary | None = None
    #: The support request's status when this thread is one (MQA-024: one
    #: status, the same words in Messages and on the request).
    support_status: str | None = None


class InboxCounts(BaseModel):
    all: int
    sellers: int
    reviewers: int
    closed: int
    #: Open conversations with a member message the team has not opened.
    unread: int


class InboxListOut(BaseModel):
    items: list[ConversationRowOut]
    total: int
    counts: InboxCounts


class MemberCounts(BaseModel):
    open: int
    closed: int
    unread: int


class MemberListOut(BaseModel):
    items: list[ConversationRowOut]
    counts: MemberCounts


class LinkOptionOut(BaseModel):
    """Sheet/Messages/Link, Menu/Store/Chat/Appeal: what a new conversation can
    be linked to, the member's own things only."""

    type: Literal["appeal", "claim", "payout", "review", "report", "product"]
    id: uuid.UUID
    topic: ConversationTopic
    label: str
    sublabel: str | None = None


class StaffOptionOut(BaseModel):
    id: uuid.UUID
    name: str


class ConversationAssign(BaseModel):
    admin_id: uuid.UUID | None = None


class ConversationStatusIn(BaseModel):
    status: ConversationStatus

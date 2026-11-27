"""conversations + conversation_messages (0076; Figma Screen/Admin/Inbox,
Screen/Seller/Inbox, Screen/Messages).

One conversation is a thread between ONE member (a store's owner or claimant,
or a reviewer) and the Bluntly team. Staff are not participants by name: any
Administrator or Super Admin may read and answer, and one may be assigned.

A conversation can be linked to the thing it is about (`link_type` +
`link_id`: an appeal, a claim, a payout, a review, a report or a product), so
the Inbox shows its context bar ("Open appeal", "Open payout").

`case_key` makes a claim's or an appeal's chat ONE conversation (owner
decision 2026-10-03, "merge into Inbox"): `claim:<id>`, `appeal:<id>` (the
store's side) and `appeal-reviewer:<id>` (the review author's side). The case
chat endpoints read and write the same rows the Inbox does.

Read state is per side: `member_read_at` for the member, `staff_read_at` for
the team (shared by every staff member, like a shared mailbox).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    ConversationAudience,
    ConversationMessageKind,
    ConversationStatus,
    ConversationTopic,
)

#: What a conversation may be linked to.
LINK_TYPES = ("appeal", "claim", "payout", "review", "report", "product")


class Conversation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_member", "member_id", "last_message_at"),
        Index("ix_conversations_inbox", "status", "last_message_at"),
        Index("ix_conversations_seller", "seller_id", "last_message_at"),
        CheckConstraint(
            "link_type IS NULL OR link_type IN "
            "('appeal', 'claim', 'payout', 'review', 'report', 'product')",
            name="ck_conversations_link_type"),
    )

    #: Human reference quoted in emails, "MSG-3F9A2C1B".
    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    audience: Mapped[ConversationAudience] = mapped_column(
        Enum(ConversationAudience, name="conversation_audience"), nullable=False)
    #: The store a seller conversation is about (None for a reviewer's).
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="SET NULL"))
    topic: Mapped[ConversationTopic] = mapped_column(
        Enum(ConversationTopic, name="conversation_topic"), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    link_type: Mapped[str | None] = mapped_column(String(16))
    link_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    case_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"),
        default=ConversationStatus.open, server_default=ConversationStatus.open.value,
        nullable=False)
    assigned_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    #: The member's latest message: "Waiting longest" and the team's unread state.
    last_member_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The team's latest message: the member's unread state.
    last_staff_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    member_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    staff_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    #: Set when an administrator moved it to Queue → Support.
    support_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_support_requests.id", ondelete="SET NULL"))


class ConversationMessage(UUIDPrimaryKey, Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("ix_conversation_messages_thread", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[ConversationMessageKind] = mapped_column(
        Enum(ConversationMessageKind, name="conversation_message_kind"),
        default=ConversationMessageKind.message,
        server_default=ConversationMessageKind.message.value, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    #: Written by an Administrator or Super Admin (shown as "Bluntly").
    from_staff: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false",
                                             nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Object key in the PRIVATE message-attachments bucket — never a URL.
    attachment_key: Mapped[str | None] = mapped_column(String(255))
    attachment_name: Mapped[str | None] = mapped_column(String(160))
    attachment_type: Mapped[str | None] = mapped_column(String(64))
    attachment_size: Mapped[int | None] = mapped_column(Integer)
    #: The case chat's own short id, for threads copied in by 0076.
    legacy_id: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    #: MQA-011 (0093): when its sender last edited it...
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: ...and when they unsent it: its words and file are then gone from the thread.
    unsent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationMessageRevision(UUIDPrimaryKey, Base):
    """What a message said before an edit or an unsend (MQA-011): an audit
    trail no screen reads, kept because a case thread is evidence."""

    __tablename__ = "conversation_message_revisions"
    __table_args__ = (
        CheckConstraint("action IN ('edit', 'unsend')", name="ck_message_revision_action"),
        Index("ix_message_revisions_message", "message_id", "created_at"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_name: Mapped[str | None] = mapped_column(String(160))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConversationMessageHide(Base):
    """One person deleted one message for themselves (MQA-011)."""

    __tablename__ = "conversation_message_hides"
    __table_args__ = (Index("ix_message_hides_user", "user_id"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

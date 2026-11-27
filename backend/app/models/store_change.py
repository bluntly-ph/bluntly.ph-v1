"""A store owner's request to change the store (MQA-017/018/019/025).

The store's name and link come from the marketplace and its registration was
checked by a moderator, so an owner cannot edit them: they ask. Each change is
a row - the field, what it was, what they asked for, and what a moderator
decided - so approving one applies it to the store and leaves a record, and the
owner, the Inbox thread and the store profile all read the same status. Every
change sent together shares one conversation (`conversation_id`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: What an owner may ask to change.
CHANGE_FIELDS = ("display_name", "store_url", "registration")
CHANGE_STATUSES = ("pending", "approved", "rejected")


class StoreChangeRequest(Base):
    __tablename__ = "store_change_requests"
    __table_args__ = (
        CheckConstraint("field IN ('display_name', 'store_url', 'registration')",
                        name="ck_store_change_field"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected')",
                        name="ck_store_change_status"),
        Index("ix_store_change_seller", "seller_id", "created_at"),
        Index("ix_store_change_conversation", "conversation_id"),
        # One open request per store and field: a second waits for the first.
        Index("uq_store_change_pending", "seller_id", "field", unique=True,
              postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    field: Mapped[str] = mapped_column(String(24), nullable=False)
    #: The store's value when the request was sent (the live value may move on).
    current_value: Mapped[str | None] = mapped_column(Text)
    requested_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending",
                                        server_default="pending")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The moderator's reason, shown to the owner.
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"))

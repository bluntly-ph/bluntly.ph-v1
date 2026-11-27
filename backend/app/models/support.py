"""seller_support_requests (0063; owner decision 2026-09-28).

A claimed store's owner contacts the administrators about their store. It is a
request, not a power: the seller gains no control over content, and an
administrator decides what, if anything, follows. See the migration for why this
is its own table rather than a report or an appeal.

`internal_note` is staff-only; the seller-facing schema never carries it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import SupportRequestCategory, SupportRequestStatus


class SellerSupportRequest(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "seller_support_requests"
    __table_args__ = (
        Index("ix_support_requests_seller", "seller_id", "created_at"),
        Index("ix_support_requests_status", "status", "created_at"),
    )

    #: Human reference the seller and staff can quote, "SUP-3F9A2C1B".
    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    category: Mapped[SupportRequestCategory] = mapped_column(
        Enum(SupportRequestCategory, name="support_request_category"), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_seller_review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_reviews.id", ondelete="SET NULL"))
    related_review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL"))
    related_product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"))
    status: Mapped[SupportRequestStatus] = mapped_column(
        Enum(SupportRequestStatus, name="support_request_status"),
        default=SupportRequestStatus.open, server_default=SupportRequestStatus.open.value,
        nullable=False)
    assigned_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    #: The administrator's reply the seller reads.
    admin_response: Mapped[str | None] = mapped_column(Text)
    admin_responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Staff-only. Never returned to the seller.
    internal_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))



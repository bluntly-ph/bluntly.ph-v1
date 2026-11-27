"""Tunable platform settings and the admin-queue triage record (0056).

`PlatformSetting` holds one JSON value per key. It exists for values the owner
expects to retune against real volume without a redeploy — today the priority
tier thresholds (services/priority_settings.py). A missing row means "use the
code default".

`QueueTriage` is one row per item currently sitting in an admin queue
("earnings" or "reports"). It records when the item's aging clock started, when
the hourly job aged it one tier, and the tier last computed. It is a triage
annotation only: nothing reads it to decide whether an item is IN a queue.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class QueueTriage(UUIDPrimaryKey, Base):
    __tablename__ = "queue_triage"
    __table_args__ = (
        UniqueConstraint("queue", "target_type", "target_ref", name="uq_queue_triage_item"),
    )

    #: "earnings" (the earn_eligible review queue) or "reports".
    queue: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), nullable=False)
    target_ref: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: When the item entered the queue — the start of its aging clock unless a
    #: later decision restarted it.
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Set by the hourly job once the clock has run past the aging window.
    aged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tier: Mapped[str | None] = mapped_column(String(16))
    base_tier: Mapped[str | None] = mapped_column(String(16))
    reasons: Mapped[list | None] = mapped_column(JSONB)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

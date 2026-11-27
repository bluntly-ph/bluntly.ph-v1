"""An unfinished review, kept with the account rather than the device (QA-003).

The composer autosaved to the browser's localStorage only, so a draft begun on
a laptop was invisible on the reviewer's phone. A draft is the author's alone:
it is never published, never shown to anyone else, and carries no earning or
moderation state. Publishing is still the one POST /reviews (Business Rules §2);
this table only holds the form until then.

One row per (author, slot). The slot is the composer's own key: the chosen
product's id, or a fixed marker for work begun before a product was picked —
so two drafts for two products never compete for one slot, and two devices
editing the same product's draft converge on one row (the newer save wins).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class ReviewDraft(Base, UUIDPrimaryKey):
    __tablename__ = "review_drafts"
    __table_args__ = (UniqueConstraint("user_id", "slot", name="uq_review_draft_slot"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot: Mapped[str] = mapped_column(String(64), nullable=False)
    # The composer's form state, opaque to the server beyond its size.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # The client's own save time (ms since epoch). Newer wins, so an older save
    # arriving late from a second device cannot overwrite newer work.
    saved_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

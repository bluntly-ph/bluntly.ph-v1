"""email_change_requests (0084): a verified change of the address a member signs in with.

One row per attempt. Both codes are Argon2id hashes (app.core.security). `attempts`
caps wrong guesses for the PAIR, in Postgres, so the limit holds when Redis is down.
See app/services/email_change_service.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailChangeRequest(Base):
    __tablename__ = "email_change_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    new_email: Mapped[str] = mapped_column(String(320), nullable=False)
    current_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    new_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False)

"""Integrity fingerprints (QA, 2026-09-29): what the anti-plagiarism and
anti-farming checks compare, and nothing more.

`ImageFingerprint` is one row per uploaded public review photo: its SHA-256
and 64-bit difference hash (`services/image_fingerprint.py`). It is derived
from an image already public on the review, identifies no one, and is read by
staff tooling only.

`VoteNetworkFingerprint` is one row per up-vote: a keyed hash of the voter's
network, never an address, kept 30 days.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKey


class ImageFingerprint(UUIDPrimaryKey, Base):
    __tablename__ = "image_fingerprints"
    __table_args__ = (UniqueConstraint("url", name="uq_image_fingerprints_url"),)

    #: The public URL the upload returned: what `reviews.photo_url` holds.
    url: Mapped[str] = mapped_column(Text, nullable=False)
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    #: The 64 hash bits as a signed BIGINT (`Fingerprint.dhash_signed`).
    dhash: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False)


class VoteNetworkFingerprint(UUIDPrimaryKey, Base):
    """One up-vote's network, as a keyed hash (QA 2026-09-29).

    No IP address is stored, ever: `network` is HMAC-SHA256 under a server
    secret of the trusted client IP (IPv4) or its /64 (IPv6), truncated. It
    cannot be reversed without the secret, is never returned by any API, and is
    deleted after `vote_network_retention_days` (30) by the retention sweep.
    Its only use is to notice several accounts on one network up-voting one
    author (`services/vote_network.py`).
    """

    __tablename__ = "vote_network_fingerprints"
    __table_args__ = (
        UniqueConstraint("review_id", "voter_id", name="uq_vote_network_review_voter"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    voter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    #: The review's author when the vote was cast: what the signal groups by.
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    network: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Whether the voter's account was under 30 days old when they voted.
    new_account: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False)

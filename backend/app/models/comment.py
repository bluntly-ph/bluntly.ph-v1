"""review_comments + review_comment_votes (FR-9b, BUG-014).

Discussion under a published review. Distinct from Q&A `answers`, which hang off
a *product* question and carry Best Answer / First Responder semantics; a comment
carries none of that and never earns.

Threading is deliberately one level deep: a comment either sits at the top level
or replies to a top-level comment. Unbounded nesting has no design to render it
and turns the read query into a recursive walk for no product gain.

Removal is soft (`is_removed`) so a moderator action stays auditable and a reply
never loses its parent — the same posture as `reviews.is_removed`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import VoteDirection


class ReviewComment(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "review_comments"
    __table_args__ = (
        # The read path is always "every comment on this review, oldest first".
        Index("ix_review_comments_review_created", "review_id", "created_at"),
        Index("ix_review_comments_parent_id", "parent_id"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL rather than CASCADE, matching `reviews.author_id`: deleting an
    # account must not silently rewrite a conversation other people took part in.
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # A reply's parent. CASCADE: deleting a thread root takes its replies, which
    # is the only sane reading of a deleted parent.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_comments.id", ondelete="CASCADE")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    helpful_votes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unhelpful_votes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    is_removed: Mapped[bool] = mapped_column(default=False, server_default="false")

    replies: Mapped[list[ReviewComment]] = relationship(
        back_populates="parent", cascade="all, delete-orphan",
    )
    parent: Mapped[ReviewComment | None] = relationship(
        back_populates="replies", remote_side="ReviewComment.id",
    )


class ReviewCommentVote(Base, UUIDPrimaryKey, Timestamps):
    """One vote per (comment, voter); changing direction is an upsert.

    Equal weight, like `ReviewVote` — comment votes order a discussion, they do
    not feed trust, ranking, or earnings, so none of the gate-vote snapshotting
    applies here.
    """

    __tablename__ = "review_comment_votes"
    __table_args__ = (
        UniqueConstraint("comment_id", "voter_id", name="uq_review_comment_vote_once"),
        Index("ix_review_comment_votes_comment_id", "comment_id"),
    )

    comment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_comments.id", ondelete="CASCADE"),
        nullable=False,
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    vote: Mapped[VoteDirection] = mapped_column(
        Enum(VoteDirection, name="vote_direction"), nullable=False
    )


class _CommentMark:
    """One member's private mark on one comment (0057, QA-069)."""

    comment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("review_comments.id", ondelete="CASCADE"),
        nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class CommentFollow(_CommentMark, UUIDPrimaryKey, Base):
    """Follow a comment: hear about replies to it. Never shown to others."""

    __tablename__ = "comment_follows"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_comment_follows_once"),
        Index("ix_comment_follows_user", "user_id", "created_at"),
    )


class CommentSave(_CommentMark, UUIDPrimaryKey, Base):
    """Save a comment privately, to read again later. Never shown to others."""

    __tablename__ = "comment_saves"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_comment_saves_once"),
        Index("ix_comment_saves_user", "user_id", "created_at"),
    )

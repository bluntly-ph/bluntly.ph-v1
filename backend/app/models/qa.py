"""questions, answers (FR-5).

Best Answer (one per question) and First Responder badge (first answer < 24h).
`answers.earn_eligible` exists per the Data Dictionary but is intentionally
UNWIRED in this build (ADR-006 / A5: answer-level earning is out of scope).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import QuestionDirectedTo, VoteDirection


class Question(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "questions"
    __table_args__ = (
        # A question is about a product or a store (0045). The schema refuses
        # both-or-neither too; this is the guard that survives a direct write.
        CheckConstraint("product_id IS NOT NULL OR seller_id IS NOT NULL",
                        name="ck_question_subject"),
        Index("ix_questions_seller", "seller_id", "created_at"),
    )

    question_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    #: Null for a question asked of a store.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    #: The store asked, from its seller page (0045). Null for a product question.
    seller_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE")
    )
    asker_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    directed_to: Mapped[QuestionDirectedTo] = mapped_column(
        Enum(QuestionDirectedTo, name="question_directed_to"), nullable=False
    )
    # FK set once a Best Answer is awarded; use_alter avoids a create-order cycle.
    best_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("answers.id", ondelete="SET NULL", use_alter=True,
                   name="fk_questions_best_answer"),
    )
    is_removed: Mapped[bool] = mapped_column(default=False, server_default="false")
    #: Who picked the Best Answer and when (QA-058). Only the asker can.
    best_answer_picked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    best_answer_picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    answers: Mapped[list[Answer]] = relationship(
        back_populates="question", cascade="all, delete-orphan",
        foreign_keys="Answer.question_id",
    )


class Answer(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "answers"

    answer_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    responder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)

    is_best_answer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_first_responder: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    #: Written by the moderator-approved owner of the store the question was
    #: asked of (0045). Set once, from the claim as it stood when answering.
    is_seller_answer: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    #: When the store's owner last edited the store's answer (0081); buyers see
    #: "Edited". Null for an answer never edited.
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    helpful_votes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unhelpful_votes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wilson_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 5), default=0, nullable=False, server_default="0"
    )

    # Present per Data Dictionary; NOT wired to any earning logic in this build.
    earn_eligible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    question: Mapped[Question] = relationship(
        back_populates="answers", foreign_keys=[question_id]
    )


class QuestionSubscription(Base):
    """ "Notify me!" on a question (QA-045): a new answer notifies subscribers."""

    __tablename__ = "question_subscriptions"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class AnswerReply(Base, UUIDPrimaryKey, Timestamps):
    """A reply in an answer's thread (0073; Figma Question Detail v6B). Depth
    1..3: the frame draws three levels, then "Continue this thread"."""

    __tablename__ = "answer_replies"
    __table_args__ = (
        CheckConstraint("depth BETWEEN 1 AND 3", name="ck_answer_reply_depth"),
        Index("ix_answer_replies_answer_created", "answer_id", "created_at"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answers.id", ondelete="CASCADE"), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_replies.id", ondelete="CASCADE"))
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_removed: Mapped[bool] = mapped_column(default=False, server_default="false")


class QAVote(Base, UUIDPrimaryKey):
    """One member's vote on a question (up only), an answer or a reply (0073).
    Exactly one target per row; one row per (target, member)."""

    __tablename__ = "qa_votes"
    __table_args__ = (
        CheckConstraint("num_nonnulls(question_id, answer_id, reply_id) = 1",
                        name="ck_qa_vote_one_target"),
        CheckConstraint("question_id IS NULL OR direction = 'up'",
                        name="ck_qa_vote_question_up_only"),
        Index("uq_qa_votes_question_id_user", "question_id", "user_id", unique=True,
              postgresql_where=text("question_id IS NOT NULL")),
        Index("uq_qa_votes_answer_id_user", "answer_id", "user_id", unique=True,
              postgresql_where=text("answer_id IS NOT NULL")),
        Index("uq_qa_votes_reply_id_user", "reply_id", "user_id", unique=True,
              postgresql_where=text("reply_id IS NOT NULL")),
        Index("ix_qa_votes_user", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"))
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answers.id", ondelete="CASCADE"))
    reply_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answer_replies.id", ondelete="CASCADE"))
    direction: Mapped[VoteDirection] = mapped_column(
        Enum(VoteDirection, name="vote_direction", create_type=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False)

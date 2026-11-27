"""Community Q&A schemas (FR-5).

Questions are product-scoped and directed at either other buyers or the seller.
Answer-level earning (`answers.earn_eligible`) stays unwired (ADR-006 / A5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.link_policy import reject_links
from app.services import answer_parts


class QuestionCreate(BaseModel):
    """A question about exactly one subject: a product, or a store (0045)."""

    product_id: uuid.UUID | None = None
    seller_id: uuid.UUID | None = None
    body: str = Field(min_length=1, max_length=2000)
    # No audience (owner decision 2026-09-28): the asker no longer chooses
    # whether buyers or the seller should answer — anyone eligible may, under
    # the Q&A rules. A client still sending `directed_to` is ignored, not
    # refused, so an older page cannot fail on it.

    @field_validator("body")
    @classmethod
    def _no_links(cls, value: str) -> str:
        return reject_links(value, field="questions")

    @model_validator(mode="after")
    def _exactly_one_subject(self) -> QuestionCreate:
        if (self.product_id is None) == (self.seller_id is None):
            raise ValueError("A question is about a product or a store: give exactly one.")
        return self


class AnswerCreate(BaseModel):
    """An answer: its own words and, like a review (meeting 2026-10-02), the
    specifics the asker asked for — experience, the good, the bad, whether you
    recommend it, whether it is right for them, a rating — and photos you
    uploaded (POST /reviews/photos). At least some words are required."""

    body: str = Field(default="", max_length=4000)
    experience: str | None = Field(default=None, max_length=1000)
    good: str | None = Field(default=None, max_length=1000)
    bad: str | None = Field(default=None, max_length=1000)
    recommend: bool | None = None
    #: "Your verdict" (answer flow step 4); when given it decides `recommend`.
    verdict: Literal["yes", "on_sale", "other_variant", "no"] | None = None
    #: "Why? (optional)" under the verdict (Answer Step 4.1). Never required.
    verdict_reason: str | None = Field(default=None, max_length=1000)
    right_for_you: str | None = Field(default=None, max_length=1000)
    rating: Decimal | None = Field(default=None, ge=Decimal("0.5"), le=Decimal("5"))
    photo_urls: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("body", "experience", "good", "bad", "right_for_you", "verdict_reason")
    @classmethod
    def _no_links(cls, value: str | None) -> str | None:
        return reject_links(value, field="answers")

    @field_validator("rating")
    @classmethod
    def _half_stars(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value * 2) % 1 != 0:
            raise ValueError("A rating is in half stars, 0.5 to 5.")
        return value

    @model_validator(mode="after")
    def _has_words(self) -> AnswerCreate:
        words = [self.body, self.experience, self.good, self.bad, self.right_for_you,
                 self.verdict_reason]
        if not any(w and w.strip() for w in words):
            raise ValueError("An answer needs some words: write it, or fill in a part.")
        return self


class QAAuthor(BaseModel):
    """The public author fields a Q&A card needs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    trust_stage: int = 0
    trust_level_name: str | None = None
    # See FeedAuthor.reputation_score — the badge reads the same everywhere.
    reputation_score: Decimal = Decimal("0")
    #: The profile photo the Author header draws (Figma Author 7659:5991), as
    #: comment authors carry it. None draws the initial — never a default photo.
    avatar_url: str | None = None


class AnswerPartsOut(BaseModel):
    text: str = ""
    experience: str | None = None
    good: str | None = None
    bad: str | None = None
    recommend: bool | None = None
    verdict: str | None = None
    verdict_reason: str | None = None
    right_for_you: str | None = None
    rating: Decimal | None = None
    photo_urls: list[str] = []


class ReplyOut(BaseModel):
    """A reply in an answer's thread (0073). `parent_id` null = under the answer."""

    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    depth: int = 1
    body: str
    created_at: datetime
    author: QAAuthor | None = None
    up: int = 0
    down: int = 0
    my_vote: Literal["up", "down"] | None = None


class StoreAnswerEdit(BaseModel):
    """The store's owner rewrites the store's answer (Figma Overlay/Store/
    EditAnswer 8202:22530). Store answers are plain words: the same 1,000
    characters and no-links rule as answering in the console."""

    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def _words(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Write the answer.")
        return reject_links(value, field="answers")


class AnswerOut(BaseModel):
    id: uuid.UUID
    answer_id: str | None = None
    body: str
    is_best_answer: bool = False
    is_first_responder: bool = False
    helpful_votes: int = 0
    #: Down-votes, from the vote rows (0073), as `helpful_votes` is.
    unhelpful_votes: int = 0
    #: The viewer's own vote on this answer, when signed in.
    my_vote: Literal["up", "down"] | None = None
    #: The thread under the answer, oldest first (flat; `parent_id` builds the tree).
    replies: list[ReplyOut] = []
    reply_count: int = 0
    created_at: datetime
    responder: QAAuthor | None = None
    #: True when the store's claimed owner wrote this, on a store question.
    is_seller_answer: bool = False
    #: The store's name, set only on a seller answer, so it is shown as the store.
    seller_name: str | None = None
    #: Set when the store edited its answer (0081): buyers see "Edited".
    edited_at: datetime | None = None
    #: The answer's structured parts, read from its body (services/answer_parts);
    #: null for a plain answer.
    parts: AnswerPartsOut | None = None

    @model_validator(mode="after")
    def _read_parts(self) -> AnswerOut:
        if self.parts is None:
            parsed = answer_parts.parse(self.body)
            if parsed.structured:
                self.parts = AnswerPartsOut(**parsed.__dict__)
        return self


class QuestionOut(BaseModel):
    id: uuid.UUID
    question_id: str | None = None
    #: Null for a question asked of a store.
    product_id: uuid.UUID | None = None
    product_name: str | None = None
    #: The product's stored image, for the Questions tab's 100px tile (Figma
    #: "QuestionPreviewCard" 7158:4877). Null when none is stored.
    product_image_url: str | None = None
    seller_id: uuid.UUID | None = None
    seller_name: str | None = None
    body: str
    best_answer_id: uuid.UUID | None = None
    answer_count: int = 0
    created_at: datetime
    asker: QAAuthor | None = None
    #: Who wrote the Best Answer (the asker's recorded pick), for the admin
    #: Answers queue's "Best answer" column; null when none is picked.
    best_answer_by: QAAuthor | None = None
    #: The specifics the asker asked for ("Looking for:" line), for the answer form.
    requirements: list[str] = []

    @model_validator(mode="after")
    def _read_requirements(self) -> QuestionOut:
        if not self.requirements:
            self.requirements = answer_parts.requirements_of(self.body)
        return self


class MyQuestionOut(QuestionOut):
    """A question on the dashboard's Answers tab."""

    #: The newest answers (the asker's Best Answer first), at most two.
    latest_answers: list[AnswerOut] = []
    #: On the "answered" list: the viewer's own answer.
    my_answer: AnswerOut | None = None


class QuestionDetailOut(QuestionOut):
    answers: list[AnswerOut] = []
    #: QA-058: the Best Answer is the asker's pick, and says so.
    best_answer_picked_at: datetime | None = None
    best_answer_picked_by_asker: bool = False
    #: QA-045: whether the viewer asked to be notified of new answers.
    is_subscribed: bool = False
    #: The question's up-votes (0073) and whether the viewer gave one.
    upvotes: int = 0
    my_upvote: bool = False
    #: Replies across all its answers (the question footer's comment count).
    reply_count: int = 0


class SubscriptionIn(BaseModel):
    subscribed: bool


class VoteSet(BaseModel):
    """Cast or change a vote; null takes it back."""

    vote: Literal["up", "down"] | None = None


class VoteTally(BaseModel):
    up: int
    down: int = 0
    my_vote: Literal["up", "down"] | None = None


class QuestionVoteIn(BaseModel):
    up: bool


class QuestionVoteOut(BaseModel):
    upvotes: int
    my_upvote: bool


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    parent_id: uuid.UUID | None = None

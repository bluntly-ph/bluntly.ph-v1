"""Seller schemas (FR-4).

The four review dimensions carry FR-4's types at the boundary: accuracy and
order completeness are binary judgements, customer service and packaging are
graded 1-5, and the overall rating is 0 to 5 in half steps (owner requirement,
migration 0048) with zero meaning a real "this was bad" rather than an
unanswered question. The database holds the same ranges as CHECK constraints;
validating here as well turns a bad request into a 422 with a field name
instead of an IntegrityError.

The public seller shape exposes whether a store is claimed, never *who* claimed
it: that is an account id, and a reader deciding whether to trust a store does
not need it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.link_policy import reject_links
from app.models.enums import Platform, SellerClaimStatus, VoteDirection
from app.schemas.qa import QAAuthor
from app.schemas.review import HALF_STEP_HINT, half_step
from app.schemas.urls import web_url_or_none

#: The composer draws one "Add more" tile beside the photos; four keeps a
#: seller review a rating with evidence rather than a gallery.
MAX_SELLER_REVIEW_PHOTOS = 4


class SellerCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    platform: Platform
    store_url: str | None = Field(default=None, max_length=2000)

    # A store link is rendered as an href on the seller page and in the
    # moderator's claim queue, so a `javascript:` URL here is script execution
    # in whichever session clicks it. http(s) only, via the shared rule every
    # other user-supplied URL uses (app/schemas/urls.py).
    @field_validator("store_url")
    @classmethod
    def _only_web_store_url(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Store links")

    @model_validator(mode="after")
    def _link_on_its_marketplace(self) -> SellerCreate:
        """MQA-020: a Shopee store's link is a Shopee page."""
        from app.services.store_change_service import link_mismatch
        problem = link_mismatch(self.platform, self.store_url)
        if problem:
            raise ValueError(problem)
        return self


class SellerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    platform: Platform
    store_url: str | None = None
    claim_status: SellerClaimStatus
    #: Visible ratings only; a removed review no longer counts.
    review_count: int = 0
    #: Mean overall rating of the visible reviews; null until there is one.
    overall_average: float | None = None
    #: The store's questions that have at least one answer — the "39 questions
    #: answered" of Figma "SellerPreviewCard" (7159:4873), QA-052.
    answered_question_count: int = 0
    created_at: datetime


class SellerReviewCreate(BaseModel):
    #: true = matched the advertisement, false = not the same.
    accuracy: bool
    #: true = exact order, false = something missing.
    order_completeness: bool
    customer_service: int = Field(ge=1, le=5)
    packaging_quality: int = Field(ge=1, le=5)
    #: 0 to 5 in half steps; the two dimensions above stay whole-number chips.
    overall_rating: float = Field(ge=0, le=5, description=HALF_STEP_HINT)
    would_recommend: bool

    _overall_step = field_validator("overall_rating")(classmethod(lambda cls, v: half_step(v)))

    #: What was bought, when the reviewer says.
    product_id: uuid.UUID | None = None
    #: The composer caps this at 30; 200 here, the same split product reviews
    #: use, so a copy change in the composer never needs a migration.
    title: str | None = Field(default=None, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)
    #: Public photos from POST /reviews/photo. Ownership is checked by the route.
    photo_urls: list[str] = Field(default_factory=list, max_length=MAX_SELLER_REVIEW_PHOTOS)

    #: Business Rules §10: the order ID, self-reported and never "verified".
    order_id: str | None = Field(default=None, max_length=64)

    @field_validator("title", "comment")
    @classmethod
    def _no_links(cls, value: str | None) -> str | None:
        return reject_links(value, field="seller reviews")

    @field_validator("order_id")
    @classmethod
    def _order_id_shape(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if not all(ch.isalnum() or ch in "-_#" for ch in value):
            raise ValueError("An order ID uses letters, digits, '-', '_' or '#'.")
        return value

    # Drawn as image sources on the seller page, so the same http(s)-only rule
    # as every other user-supplied URL applies to each one.
    @field_validator("photo_urls")
    @classmethod
    def _only_web_photos(cls, value: list[str]) -> list[str]:
        return [url for url in (web_url_or_none(v, field="Photo links") for v in value) if url]


class SellerReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seller_id: uuid.UUID
    product_id: uuid.UUID | None = None
    title: str | None = None
    accuracy: bool
    order_completeness: bool
    customer_service: int
    packaging_quality: int
    overall_rating: float
    would_recommend: bool
    comment: str | None = None
    photo_urls: list[str] = Field(default_factory=list)
    #: Always false on public reads, which never return a removed review.
    is_removed: bool = False
    reviewer: QAAuthor | None = None
    created_at: datetime
    #: The claimed seller's public response, if any (§8, §9).
    seller_response: str | None = None
    seller_response_at: datetime | None = None
    #: Set when the store edited its response (0082): buyers see "Edited".
    seller_response_edited_at: datetime | None = None
    #: True when the reviewer gave an order ID. The ID itself is never public:
    #: it is self-reported, unverified, and only an appeal ever looks at it.
    order_id_provided: bool = False
    #: QA-043: helpfulness votes (moving no rating), and the viewer's own.
    helpful_votes: int = 0
    unhelpful_votes: int = 0
    my_vote: VoteDirection | None = None
    #: QA-043: members' replies, oldest first (the store's response is separate).
    replies: list[SellerReplyOut] = Field(default_factory=list)
    reply_count: int = 0


class SellerReplyOut(BaseModel):
    id: uuid.UUID
    body: str
    created_at: datetime
    author: QAAuthor | None = None


class SellerReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)

    @field_validator("body")
    @classmethod
    def _no_links(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A reply cannot be empty.")
        return reject_links(value, field="replies")


class SellerVoteIn(BaseModel):
    direction: VoteDirection


class SellerVoteOut(BaseModel):
    helpful_votes: int
    unhelpful_votes: int
    my_vote: VoteDirection | None = None


class SellerResponseIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _no_links(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A response cannot be empty.")
        return reject_links(value, field="seller responses")


AppealKind = Literal["never_ordered", "untrue", "breaks_rules"]


class SellerAppealIn(BaseModel):
    """A claimed seller flags one review of their store (§10): the buyer never
    ordered, the details are untrue, or it breaks the rules (MQA-041, 0090)."""

    reason: str = Field(min_length=10, max_length=2000)
    kind: AppealKind = "never_ordered"

    @field_validator("reason")
    @classmethod
    def _no_links(cls, value: str) -> str:
        return reject_links(value.strip(), field="appeals")


class SubstantiationRequestIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class SubstantiationIn(BaseModel):
    response: str = Field(min_length=1, max_length=4000)

    @field_validator("response")
    @classmethod
    def _no_links(cls, value: str) -> str:
        return reject_links(value.strip(), field="your response")


class AppealDecisionIn(BaseModel):
    decision: Literal["uphold", "dismiss"]
    note: str | None = Field(default=None, max_length=2000)


class SellerAppealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seller_review_id: uuid.UUID
    seller_id: uuid.UUID
    reason: str
    kind: str = "never_ordered"
    status: str
    substantiation_request: str | None = None
    substantiation_requested_at: datetime | None = None
    substantiation_response: str | None = None
    substantiated_at: datetime | None = None
    #: Store-facing: the decision's explanation, also the body of the store's
    #: "seller_appeal_decided" notice. Not a place for internal notes.
    decision_note: str | None = None
    decided_at: datetime | None = None
    created_at: datetime
    #: Admin-only context: the reviewer's self-reported order ID.
    order_id: str | None = None
    #: Admin-only context for the Appeals table and modal (Figma 7992:11823,
    #: 7996:11826); left empty on the reviewer's own view.
    seller_name: str | None = None
    seller_platform: str | None = None
    store_url: str | None = None
    review_rating: float | None = None
    review_title: str | None = None
    review_comment: str | None = None
    review_created_at: datetime | None = None
    reviewer: QAAuthor | None = None


class SellerReviewRemoval(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


def _empty_distribution() -> dict[int, int]:
    return {star: 0 for star in range(1, 6)}


class SellerSummary(BaseModel):
    """The public aggregate for one store.

    Every rate and average is nullable, and null when there is nothing to
    aggregate. A store nobody has rated has no accuracy rate; reporting 0.0
    would state that none of its orders matched the listing. The star breakdown
    is counts, not rates, so zeroes there are true.
    """

    review_count: int = 0
    accuracy_rate: float | None = None
    order_completeness_rate: float | None = None
    recommend_rate: float | None = None
    #: Business Rules §10: these three are MEDIANS (the same manipulation-
    #: resistant aggregate product ratings use); the names are kept for clients.
    customer_service_average: float | None = None
    packaging_quality_average: float | None = None
    overall_average: float | None = None
    #: Overall rating -> number of reviews, keys 1..5 always present.
    rating_distribution: dict[int, int] = Field(default_factory=_empty_distribution)


class SellerDetailOut(SellerOut):
    summary: SellerSummary
    #: A claim on this store is waiting for an administrator (MQA-012). Says
    #: only that one exists - never whose - so the page can show the status
    #: instead of offering a form the API would refuse.
    claim_under_review: bool = False


class SellerClaimCreate(BaseModel):
    """Business Rules §9: ownership is proved by a DTI or SEC business
    registration, cross-checked against the shop name on the marketplace."""

    registration_kind: Literal["dti", "sec"]
    registration_number: str = Field(min_length=3, max_length=64)
    registered_business_name: str = Field(min_length=2, max_length=200)
    #: The shop name exactly as the marketplace shows it.
    marketplace_shop_name: str = Field(min_length=1, max_length=160)
    #: Anything else the moderator should see. Optional now.
    evidence: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _registration_format(self) -> SellerClaimCreate:
        """QA-075: the exact rule the claim form runs before Submit enables
        (`lib/registration-format.ts`, one case table for both). A format
        check only — a moderator still checks the registration itself (§9)."""
        from app.core.registration_format import format_error
        problem = format_error(self.registration_kind, self.registration_number)
        if problem:
            raise ValueError(problem)
        self.registration_number = self.registration_number.strip()
        return self


class SellerClaimOut(BaseModel):
    id: uuid.UUID
    seller_id: uuid.UUID
    seller_display_name: str | None = None
    status: SellerClaimStatus
    evidence: str | None = None
    decision_note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    registration_kind: str | None = None
    registration_number: str | None = None
    registered_business_name: str | None = None
    marketplace_shop_name: str | None = None
    #: The §9 cross-check: does the shop name given match this store's name?
    shop_name_matches: bool | None = None
    #: Admin context for the Claims table and modal (Figma 7992:11327, 7996:11538).
    claimant: QAAuthor | None = None
    seller_platform: str | None = None
    store_url: str | None = None
    #: MQA-020: why the store's link cannot be approved as it is (on another
    #: marketplace than the store), or None. Approval is refused while set.
    link_problem: str | None = None


class ClaimDecision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)


class MonthCount(BaseModel):
    #: "YYYY-MM", a Manila calendar month.
    month: str
    count: int


class WaitingQuestion(BaseModel):
    id: uuid.UUID
    body: str
    created_at: datetime
    #: "asked by Mara L." (Figma Screen/Seller/Overview): the asker's public name.
    asker: str | None = None


class DashboardReviewRow(BaseModel):
    """One review of the store, as its owner's dashboard lists it."""

    id: uuid.UUID
    created_at: datetime
    reviewer: str | None = None
    #: The reviewer's public name and trust stage, as the console's Person cell shows them.
    reviewer_name: str | None = None
    reviewer_trust_stage: int | None = None
    title: str | None = None
    excerpt: str | None = None
    overall_rating: float
    helpful_votes: int = 0
    unhelpful_votes: int = 0
    reply_count: int = 0
    #: helpful votes + replies — the dashboard's one engagement measure.
    engagement: int = 0
    has_store_response: bool = False
    #: The store's "suspected fake" flag on this review, if raised:
    #: open | substantiation_requested | upheld | dismissed.
    appeal_status: str | None = None


class DashboardActivity(BaseModel):
    kind: str
    at: datetime
    label: str
    link: str | None = None


class DashboardMonth(BaseModel):
    month: str
    reviews: int = 0
    replies: int = 0
    questions: int = 0


class SellerDashboardAnalytics(BaseModel):
    """Counts from data the platform already stores — nothing modelled.

    `engagement` = a review's helpful votes + its replies (documented in
    docs/SELLER_DASHBOARD.md). Moderation priority is deliberately NOT used:
    it is an internal triage signal, not a public ranking.
    """

    review_count: int
    median_rating: float | None = None
    rating_distribution: dict[str, int] = Field(default_factory=dict)
    replies_total: int = 0
    helpful_votes_total: int = 0
    questions_total: int = 0
    questions_answered_by_store: int = 0
    responses_total: int = 0
    response_rate: float | None = None
    appeals_open: int = 0
    support_open: int = 0
    #: Visible reviews with no response from the store yet (the Reviews pill).
    reviews_awaiting_response: int = 0
    #: Median hours from a review or a store question to the store's response
    #: or answer; None before the first one.
    median_reply_hours: float | None = None
    #: The same median over every store on Bluntly ("Most stores reply within").
    platform_median_reply_hours: float | None = None
    months: list[DashboardMonth] = Field(default_factory=list)
    most_engaged: DashboardReviewRow | None = None
    most_discussed: DashboardReviewRow | None = None


class StoreAnswerOut(BaseModel):
    id: uuid.UUID
    body: str
    created_at: datetime
    edited_at: datetime | None = None


class StoreQuestionOut(BaseModel):
    """A question about the store, as its owner works through them
    (Figma Screen/Seller/Questions 8196:21469)."""

    id: uuid.UUID
    body: str
    created_at: datetime
    asker: QAAuthor | None = None
    answer_count: int = 0
    #: Answers from buyers (the store's own left out): Figma's "Community answers".
    community_answers: int = 0
    #: Members following the question ("Notify me"): Figma's "Following".
    followers: int = 0
    #: The store's own answer (the first one), if it has answered.
    store_answer: StoreAnswerOut | None = None


DashboardPeriod = Literal["30d", "3m", "6m", "12m", "all"]


class SellerDashboardOut(BaseModel):
    """What a store's approved owner sees about their own store."""

    seller: SellerDetailOut
    #: Visible reviews per month, oldest first, zero-filled.
    monthly_volume: list[MonthCount]
    #: Store questions with no answer from the store yet.
    unanswered_questions: int
    #: Oldest first, at most 20: the ones that have waited longest come first.
    waiting_questions: list[WaitingQuestion]
    #: Owner decision 2026-09-28: the rudimentary seller dashboard.
    analytics: SellerDashboardAnalytics | None = None
    #: Newest first, at most 30.
    reviews: list[DashboardReviewRow] = Field(default_factory=list)
    #: Visible reviews still without the store's response, OLDEST first, at most 20
    #: (the newest-30 list above would hide the ones that have waited longest).
    #: The total is analytics.reviews_awaiting_response.
    waiting_reviews: list[DashboardReviewRow] = Field(default_factory=list)
    #: Newest first, at most 15.
    recent_activity: list[DashboardActivity] = Field(default_factory=list)
    #: The Overview's period (Figma Menu/Store/Period) and the store's figures
    #: over the visible reviews posted in it: the tiles and the rating breakdown.
    period: DashboardPeriod = "6m"
    period_summary: SellerSummary | None = None


# SellerReviewOut names SellerReplyOut before it is defined.
SellerReviewOut.model_rebuild()

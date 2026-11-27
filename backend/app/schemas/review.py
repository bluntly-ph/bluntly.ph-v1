"""Review + version-history schemas (M1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.core.link_policy import reject_links, reject_links_in_list
from app.models.enums import (
    EarnEligibleStatus,
    MaterialRelationship,
    Platform,
    Verdict,
    VerificationStatus,
    VoteDirection,
)
from app.models.review import MAX_REVIEW_PHOTOS
from app.schemas.urls import web_url_or_none
from app.services.trust_badge import has_trust_badge

#: Ratings are 0 to 5 in half steps (owner requirement, 2026-09-16). Zero is a
#: real answer — "this was bad" — not an unanswered question, so the floor is 0
#: rather than 1. The step is checked here as well as by the column's CHECK,
#: because a 400 with a reason is a better answer than a 500 from the database.
HALF_STEP_HINT = "Rating must be between 0 and 5 in steps of 0.5."


def half_step(value: float | None) -> float | None:
    """0, 0.5, 1 … 5. Returns the value so it can be used as a validator."""
    if value is None:
        return value
    if value < 0 or value > 5 or (value * 2) != int(value * 2):
        raise ValueError(HALF_STEP_HINT)
    return value

class VoteIn(BaseModel):
    """Community helpfulness vote (M2 slice 2)."""

    vote: VoteDirection


# Ceiling on the review body (BUG-022). QA submitted ~5,100 characters with no
# limit, warning, or truncation. Roughly 800 words — generous for a product
# review, and enforced here as well as in the form so the cap is a property of
# the API rather than a courtesy of one client.
MAX_DISCUSSION_CHARS = 5000


def _photo_list(urls: list[str] | None, single: str | None) -> list[str] | None:
    """The photos a request means, in order, each once: `photo_urls` when sent,
    else the single-photo field's one photo (or none). None = not sent."""
    if urls is None:
        return None if single is None else ([single] if single else [])
    out: list[str] = []
    for url in urls:
        clean = web_url_or_none(url, field="Photo links")
        if clean and clean not in out:
            out.append(clean)
    return out


class ReviewEntryIn(BaseModel):
    """One entry of a review thread: an original review, or a later update (§4).

    Every free-text field refuses links (Business Rules §1): the only link a
    review ever carries is the affiliate link a moderator attaches.
    """

    title: str = Field(min_length=1, max_length=200)
    discussion: str = Field(min_length=1, max_length=MAX_DISCUSSION_CHARS)
    verdict: Verdict
    #: Why the reviewer chose the verdict (QA-037). Part of the frozen content.
    verdict_explanation: str | None = Field(default=None, max_length=2000)
    target_audience: str | None = Field(default=None, max_length=2000)
    anti_target_audience: str | None = Field(default=None, max_length=2000)
    star_rating: float = Field(ge=0, le=5, description=HALF_STEP_HINT)
    pros: list[str] = Field(default_factory=list, max_length=10)
    cons: list[str] = Field(default_factory=list, max_length=10)
    #: The reviewer's own photos of the item, in display order (0094): public
    #: URLs from POST /reviews/photo, at most MAX_REVIEW_PHOTOS. Empty = no
    #: photos; nothing is ever filled in for them.
    photo_urls: list[str] | None = Field(default=None, max_length=MAX_REVIEW_PHOTOS)
    #: Single-photo clients: the same as photo_urls=[photo_url]. Ignored when
    #: photo_urls is sent; on responses, the first photo.
    photo_url: str | None = None

    _star_step = field_validator("star_rating")(classmethod(lambda cls, v: half_step(v)))

    @model_validator(mode="after")
    def _one_photo_list(self):
        self.photo_urls = _photo_list(self.photo_urls, self.photo_url) or []
        self.photo_url = self.photo_urls[0] if self.photo_urls else None
        return self

    @field_validator("title", "discussion", "verdict_explanation", "target_audience",
                     "anti_target_audience")
    @classmethod
    def _no_links(cls, value: str | None, info) -> str | None:
        return reject_links(value, field="reviews")

    @field_validator("pros", "cons")
    @classmethod
    def _no_links_in_lists(cls, value: list[str]) -> list[str]:
        return reject_links_in_list(value, field="pros and cons")

    # http(s) only. The route also proves the object is this author's upload
    # (_own_photo_or_403), which is the stronger check - but a scheme guard at
    # the boundary costs nothing and does not depend on a route remembering.
    @field_validator("photo_url")
    @classmethod
    def _only_web_photo(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Photo links")
    # Object key from POST /reviews/receipt, not a URL. The route verifies the
    # key was uploaded by this caller before it is stored.
    receipt_key: str | None = None
    price_paid: Decimal | None = None
    #: Where the price was paid. With `price_paid`, the review also files a
    #: price observation attached to it; without it the price stays on the
    #: review alone, because guessing a marketplace would invent one.
    price_platform: Platform | None = None
    #: Disclosure (X.1). The composer always asks; a client that does not send
    #: it is recorded as never asked (NULL), not as "none".
    material_relationship: MaterialRelationship | None = None


class ReviewCreate(ReviewEntryIn):
    product_id: uuid.UUID


class ReviewUpdate(BaseModel):
    """Only `photo_url` may change after publishing, once, within 72 hours (§4).

    The other fields stay in the schema so a client sending them gets a clear
    409 `review_content_frozen` instead of a silent drop."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    discussion: str | None = Field(default=None, min_length=1)
    verdict: Verdict | None = None
    verdict_explanation: str | None = None
    target_audience: str | None = None
    anti_target_audience: str | None = None
    star_rating: float | None = Field(default=None, ge=0, le=5, description=HALF_STEP_HINT)
    pros: list[str] | None = Field(default=None, max_length=10)
    cons: list[str] | None = Field(default=None, max_length=10)
    #: The replacement photo set, in order (the one swap; see ReviewEntryIn).
    photo_urls: list[str] | None = Field(default=None, max_length=MAX_REVIEW_PHOTOS)
    photo_url: str | None = None

    _star_step = field_validator("star_rating")(classmethod(lambda cls, v: half_step(v)))

    def photos(self) -> list[str] | None:
        """The replacement photos asked for, or None when none was asked."""
        fields = self.model_fields_set
        if "photo_urls" in fields:
            return _photo_list(self.photo_urls, None) or []
        if "photo_url" in fields:
            return _photo_list(None, self.photo_url or "")
        return None

    # http(s) only. The route also proves the object is this author's upload
    # (_own_photo_or_403), which is the stronger check - but a scheme guard at
    # the boundary costs nothing and does not depend on a route remembering.
    @field_validator("photo_url")
    @classmethod
    def _only_web_photo(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Photo links")
    receipt_key: str | None = None
    price_paid: Decimal | None = None
    material_relationship: MaterialRelationship | None = None
    change_note: str | None = None


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # The requesting viewer's own vote, or None for signed-out readers and for
    # anyone who hasn't voted (BUG-013). Not a column — the route fills it in
    # after validation, because it is a fact about the *viewer*, not the review.
    # Without it the vote buttons had no way to know they were already pressed,
    # so the highlight vanished on every refresh and voting again looked broken.
    my_vote: VoteDirection | None = None

    id: uuid.UUID
    review_id: str | None = None
    product_id: uuid.UUID
    author_id: uuid.UUID | None = None
    title: str
    discussion: str
    verdict: Verdict
    verdict_explanation: str | None = None
    target_audience: str | None = None
    anti_target_audience: str | None = None
    star_rating: float
    pros: list | None = None
    cons: list | None = None
    #: The reviewer's own photos, in display order. EMPTY when they added none:
    #: the product's listing image is `product.image_url`, never here.
    photo_urls: list[str] = Field(default_factory=list)
    #: The first of photo_urls (single-photo clients), or null.
    photo_url: str | None = None

    # http(s) only. The route also proves the object is this author's upload
    # (_own_photo_or_403), which is the stronger check - but a scheme guard at
    # the boundary costs nothing and does not depend on a route remembering.
    @field_validator("photo_url")
    @classmethod
    def _only_web_photo(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Photo links")
    # Deliberately NO receipt locator on any response model.
    #
    # This schema is returned by GET /reviews and GET /reviews/{id}, both of
    # which accept anonymous callers, so anything on it is public for every
    # published review. `has_receipt` is the harmless half of the fact - it
    # says evidence was submitted without saying where it lives. A moderator
    # or the author fetches the object itself from GET /reviews/{id}/receipt.
    has_receipt: bool = False
    price_paid: Decimal | None = None
    #: The reviewer's disclosure (X.1); null when the review predates the question.
    material_relationship: MaterialRelationship | None = None
    verification_status: VerificationStatus
    # Community visibility voting (M2 slice 2).
    helpful_votes: int = 0
    unhelpful_votes: int = 0
    wilson_score: Decimal = Decimal("0")
    current_version: int
    # When the review went public: its submission (Business Rules §2). NULL
    # only while a moderator has it taken down.
    published_at: datetime | None = None
    earn_eligible_status: EarnEligibleStatus
    created_at: datetime
    updated_at: datetime
    # Threads (§4): the root's id on every entry; the root is its own thread.
    thread_id: uuid.UUID | None = None
    #: The one allowed photo swap was used at this time (§4).
    photo_replaced_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_thread_root(self) -> bool:
        return self.thread_id is None or self.thread_id == self.id

    @computed_field  # type: ignore[prop-decorator]
    @property
    def photo_provided(self) -> bool:
        """Business Rules §3: what the badge says — a photo of the item, or a
        receipt. Possession, never proof of purchase."""
        return self.verification_status == VerificationStatus.verified or self.has_receipt

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_trust_badge(self) -> bool:
        """X.2: proof + a recorded moderator decision + publication.

        Decided here, once, so every card and page shows the same answer; the
        rule itself is `services/trust_badge.py`.
        """
        return has_trust_badge(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def referral_redirect_url(self) -> str | None:
        """Public attribution link — exposed instead of the raw affiliate URL.
        Only present once the review is published AND monetized."""
        monetized = self.earn_eligible_status == EarnEligibleStatus.monetized
        if self.published_at is not None and monetized:
            return f"/r/{self.id}"
        return None


class FeedAuthor(BaseModel):
    """The author fields a public card needs (never email or wallet data)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    trust_stage: int = 0
    trust_level_name: str | None = None
    # 0..100 (ADR-003). The card shows the number beside the level name, because
    # the level name alone is not a score — stage 2 is literally called
    # "Verified Buyer", which is what BUG-004 was reading as a hardcoded label.
    reputation_score: Decimal = Decimal("0")


class FeedProduct(BaseModel):
    """The product fields a public card needs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_name: str | None = None
    category: str | None = None
    #: Median of each reviewer's latest entry (Business Rules §4).
    median_rating: Decimal = Decimal("0")
    #: Deprecated alias of `median_rating`, kept one release for API clients.
    avg_rating: Decimal = Decimal("0")
    review_count: int = 0
    # The listing image (BUG-009). The column and its seeding script have existed
    # since the product-image work, but nothing ever put it on the wire, so every
    # card fell through to the placeholder no matter how well-populated the
    # database was. Distinct from a review's own photo, which takes precedence.
    image_url: str | None = None


class FeedItemOut(BaseModel):
    """A published review joined with its author and product.

    The reviews list returns a bare ReviewOut (no author/product), which every
    card surface (landing, search, category, profile) then cannot render. This
    is the read-side join for those surfaces; the raw ReviewOut is unchanged.
    """

    review: ReviewOut
    author: FeedAuthor | None = None
    product: FeedProduct | None = None
    # Populated by the route (BUG-006). The card draws an upvote count beside a
    # comment count; the comment half had no source on the wire at all, so the
    # frontend hardcoded it empty and the stat silently never appeared.
    comment_count: int = 0
    #: QA-054: the moderator's reason when this review's earnings were
    #: rejected. Filled only for the review's own author on the single-review
    #: read; None for everyone else and on every list.
    author_rejection_reason: str | None = None
    #: QA-006 (owner 2026-09-28): the product's own marketplace listing, on the
    #: single-review read, for when there is no approved affiliate link. Only a
    #: link on a known marketplace host; never an affiliate link, so it earns
    #: nobody anything and is labelled as such.
    listing_url: str | None = None
    listing_platform: str | None = None
    #: QA-054: the moderator's reason for taking this review down, while it is
    #: down. The review's own author only, on the single-review read.
    author_takedown_reason: str | None = None


class FeedCardReview(BaseModel):
    """The review fields a card reads (E1), for every card list.

    Derived from what lib/reviews.ts `toCard`, `toFeedCard` and `toFeatured`
    read: no discussion (an `excerpt` of at most 200 characters, cut in SQL,
    stands in for it), no verdict explanation, no audiences, no pros or cons.
    The single-review read (`/reviews/{id}/full`) keeps the full ReviewOut.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    verdict: Verdict
    star_rating: float
    #: The discussion's first 200 characters, whitespace collapsed.
    excerpt: str
    photo_urls: list[str] = Field(default_factory=list)
    photo_url: str | None = None
    helpful_votes: int = 0
    unhelpful_votes: int = 0
    created_at: datetime
    #: The viewer's own vote; the route fills it in (BUG-013).
    my_vote: VoteDirection | None = None
    # The trust badge's inputs. Read to decide `has_trust_badge`, not sent.
    verification_status: VerificationStatus = Field(exclude=True)
    published_at: datetime | None = Field(default=None, exclude=True)
    earn_eligible_status: EarnEligibleStatus = Field(exclude=True)

    @field_validator("photo_urls", mode="before")
    @classmethod
    def _no_null_list(cls, value):
        return value or []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_trust_badge(self) -> bool:
        return has_trust_badge(self)


class FeedCardProduct(BaseModel):
    """The product fields a card reads (E2)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    canonical_name: str | None = None
    category: str | None = None


class FeedCardOut(BaseModel):
    """One card: a review's card fields, its author and product (display
    columns only) and its live comment count."""

    review: FeedCardReview
    author: FeedAuthor | None = None
    product: FeedCardProduct | None = None
    comment_count: int = 0


class FeedPageOut(BaseModel):
    """A page of cards and the filters' total, in one response
    (GET /reviews/feed/page)."""

    items: list[FeedCardOut]
    total: int


class OwnReviewOut(FeedItemOut):
    """One of the caller's own reviews, in any state (GET /reviews/mine).

    Only ever served to the review's author. `status` is what the author sees:
    `pending` (held for moderation), `published`, or `rejected` with the
    moderator's reason. Public surfaces keep reading the publication-gated feed.
    """

    status: Literal["pending", "published", "rejected"]
    rejection_reason: str | None = None
    #: When this thread may take its next entry (§4); None when it's not the
    #: thread's newest entry.
    next_update_at: datetime | None = None


class ThreadEntryOut(BaseModel):
    """One entry in a review thread's history (§4). The latest one counts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    verdict: Verdict
    star_rating: float
    published_at: datetime | None = None
    created_at: datetime
    is_root: bool
    is_latest: bool


class ThreadOut(BaseModel):
    thread_id: uuid.UUID
    entries: list[ThreadEntryOut]
    #: The author may add the next entry from this moment (author only).
    next_update_at: datetime | None = None


class ThreadDeleted(BaseModel):
    removed_ids: list[uuid.UUID]


class ReviewVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_number: int
    snapshot: dict
    edited_by: uuid.UUID | None = None
    change_note: str | None = None
    created_at: datetime

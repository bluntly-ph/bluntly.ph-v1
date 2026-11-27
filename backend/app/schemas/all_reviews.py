"""The Administrator's All Reviews list (QA, 2026-09-29).

Every review that still exists, with its current vote counts and both Wilson
figures, for staff only. The Review Queue is the work list (reviews awaiting an
earnings decision, and take-downs); this is the inventory beside it.

Carries no money: no earnings, commissions, payouts, affiliate URLs, sub-IDs,
receipts or order details.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import EarnEligibleStatus, Verdict

ReviewState = Literal["published", "taken_down", "removed", "deleted_by_author"]
AllReviewsSort = Literal["newest", "oldest", "wilson_desc", "wilson_asc"]


class AllReviewAuthor(BaseModel):
    id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    trust_stage: int


class AllReviewProduct(BaseModel):
    id: uuid.UUID
    canonical_name: str | None = None
    #: The product's listing image, for the row's product thumbnail (Figma
    #: Queue/AllReviews 8060:15564). Product context only: never the review's photo.
    image_url: str | None = None


class AllReviewGate(BaseModel):
    """The earnings gate's Wilson (Business Rules §2): trust-weighted votes on
    effective n, no time decay. What decides whether a review joins the Review
    Queue under Post-Seeding. `earn_gate.gate_states`, the one implementation."""

    wilson_lower_bound: float = 0
    effective_total: float = 0
    stage2_plus_voters: int = 0
    passes: bool = False


class AllReviewRow(BaseModel):
    id: uuid.UUID
    #: The public reference ("BR-…"), when the review has one.
    reference: str | None = None
    title: str
    star_rating: Decimal
    verdict: Verdict
    state: ReviewState
    earn_eligible_status: EarnEligibleStatus
    #: Whether the Review Queue holds it right now (the queue's own rule).
    in_review_queue: bool = False
    #: False for a dated update inside a thread (§4); earning lives on the root.
    is_thread_root: bool = True
    helpful_votes: int = 0
    unhelpful_votes: int = 0
    #: The public Wilson (ADR-004): every vote counts equally, decayed with a
    #: 45-day half-life. Refreshed on every vote and by the nightly sweep; the
    #: same figure the public "Most helpful" order uses.
    wilson_score: Decimal
    gate: AllReviewGate = Field(default_factory=AllReviewGate)
    #: Reports on this review that nobody has decided yet.
    open_reports: int = 0
    author: AllReviewAuthor | None = None
    product: AllReviewProduct
    created_at: datetime
    published_at: datetime | None = None


class AllReviewsPage(BaseModel):
    items: list[AllReviewRow] = Field(default_factory=list)
    #: Every review matching the filters, not just this page.
    total: int = 0
    limit: int
    offset: int
    #: Which earnings-gate phase is running, so the screen can say why a new
    #: review is here but not (yet) in the Review Queue.
    earn_gate_phase: Literal["seeding", "post_seeding"]
    #: The gate's own rule (`ranking.GATE_WILSON_LB`, `GATE_MIN_STAGE2_VOTERS`),
    #: served so the screen never restates it from memory.
    gate_threshold: float
    gate_min_stage2_voters: int

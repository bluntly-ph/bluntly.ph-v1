"""Referral-link flow schemas (M2 slice 1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Platform, ReferralLinkStatus
from app.schemas.review import ReviewOut
from app.services.integrity_checks import ExternalCheckStatus
from app.services.moderation_priority import PriorityBand, PriorityLane, SlaState


class AttachLinkRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    platform: Platform
    # The affiliate sub-ID actually set in the dashboard when generating this
    # link. Defaults to the review's suggested sub-ID (see QueueItem). It is what
    # the monthly report echoes back, so it is how the commission gets attributed.
    sub_id: str | None = Field(default=None, max_length=64)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ReferralLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    platform: Platform
    url: str
    status: ReferralLinkStatus
    sub_id: str | None = None
    # False = the pasted URL doesn't visibly carry the sub-ID, so this link's
    # commissions will most likely come back unattributable.
    sub_id_in_url: bool = False
    review_version: int
    created_by: uuid.UUID | None = None
    revoked_by: uuid.UUID | None = None
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    created_at: datetime


# --- Moderator queue ---
class MomentumWindow(BaseModel):
    """Raw engagement counts for one time window. No score, no threshold:
    what these numbers should trigger is a pending business rule."""
    #: Page opens of the review (`review_view_buckets`, the traffic counter —
    #: not reading telemetry). Counts every opening, refreshes included;
    #: author, staff and declared-bot opens are excluded at record time from
    #: 2026-09-22 on, but older buckets were counted before that.
    #: Reading-session (dwell) counts are deliberately absent: reading
    #: telemetry is collection-only by the approved design (§8, §15).
    opens: int = 0
    upvotes: int = 0
    downvotes: int = 0
    #: Comments and replies, removed ones excluded.
    comments: int = 0
    #: Distinct people who voted or commented (the author excluded).
    participants: int = 0


class MomentumFacts(BaseModel):
    last_24h: MomentumWindow = Field(default_factory=MomentumWindow)
    last_7d: MomentumWindow = Field(default_factory=MomentumWindow)
    open_reports: int = 0


class GateStateOut(BaseModel):
    """Post-Seeding earn_eligible gate progress (FR-6), from gate votes."""
    phase: Literal["seeding", "post_seeding"]
    voters: int = 0
    stage2_plus_voters: int = 0
    effective_positive: float = 0
    effective_total: float = 0
    wilson_lower_bound: float = 0
    passes: bool = False
    threshold: float
    min_stage2_voters: int


class QueuePlatform(BaseModel):
    platform: Platform
    is_monetizable: bool


class QueueProduct(BaseModel):
    id: uuid.UUID
    canonical_name: str | None = None
    source_url: str | None = None
    platforms: list[QueuePlatform] = Field(default_factory=list)


class QueueAuthor(BaseModel):
    id: uuid.UUID
    display_name: str | None = None
    trust_stage: int
    reputation_score: Decimal
    #: The reviewer snapshot's fourth figure (contract §17). It was the one the
    #: console had to draw as unavailable: the column has always existed on
    #: `users`, and this schema simply never carried it. Not telemetry — it
    #: counts published reviews that carry proof, which is content, so the
    #: telemetry-isolation gate is untouched.
    verified_review_count: int = 0


class QueueSignals(BaseModel):
    """Advisory fraud signals (M2 slice 5) — moderator queue only, never public,
    never auto-blocking."""

    velocity: bool = False
    collusion: bool = False
    duplicate_content: bool = False
    duplicate_of: str | None = None
    author_account_age_days: int = 0
    author_review_count: int = 0


class QueueVotingEvidence(BaseModel):
    """The voting facts behind the collusion signal, for the Voting
    Distribution panel (dev/QA sync 2026-09-29, ENG-0929-D).

    Relationships between accounts only: who up-voted, and whether the author
    up-votes them back. No IP address or location is collected for votes, so
    none is shown. A sibling of `signals`, which stays frozen at the six.
    """

    upvoters: int = 0
    #: Up-voters whose own reviews this review's author has up-voted.
    reciprocal_upvoters: int = 0
    #: The collusion rule: at least `min_upvoters`, and more than `threshold`
    #: of them reciprocal.
    min_upvoters: int = 5
    threshold: float = 0.6
    #: The most up-votes inside any one velocity window, and that window's rule.
    max_upvotes_in_velocity_window: int = 0
    velocity_window_seconds: int = 3600
    velocity_threshold: int = 10


class QueueIntegrityChecks(BaseModel):
    """External integrity checks, FR-8 layers 2 and 3 — a sibling of
    ``QueueSignals``, whose advisory six are frozen by the telemetry-isolation
    gate. No provider is procured, so both stay "not_configured", deliberately
    not "clear" (app/services/integrity_checks.py)."""

    plagiarism_status: ExternalCheckStatus = "not_configured"
    reverse_image_status: ExternalCheckStatus = "not_configured"


# --- Canonical priority assessment (design §5; policy in
# app/services/moderation_priority.py) ---
class QueuePriorityFactor(BaseModel):
    """One explainable contribution to a review's integrity score."""

    code: str
    observed: bool | int | str
    contribution: int
    explanation: str


class QueuePriorityAssessment(BaseModel):
    """Serialized ``PriorityAssessment`` — the moderator-visible reason a review
    sits where it does in the queue. Pure policy output: no telemetry, no PII."""

    policy_version: str
    lane: PriorityLane
    score: int
    band: PriorityBand
    sla_state: SlaState
    due_at: datetime
    factors: list[QueuePriorityFactor] = Field(default_factory=list)
    #: Business Rules §12: where the evidence came from — "user_reported"
    #: and/or "system_detected". Every card says; none is left ambiguous.
    origins: list[str] = Field(default_factory=list)


class TierReasonOut(BaseModel):
    code: str
    label: str
    detail: str


class TriageOut(BaseModel):
    """The admin priority tier (dev note 2026-09-26) — a triage label for an
    item already in a queue. It never decides whether the item is in one."""

    tier: Literal["highest", "high", "neutral", "low", "lowest"]
    base_tier: Literal["highest", "high", "neutral", "low", "lowest"]
    #: True once the hourly job aged it one tier (untouched past the window).
    aged: bool = False
    aged_at: datetime | None = None
    #: When the item's aging clock started: queue entry, or the last decision.
    clock_started_at: datetime
    #: Lowest is shown as a routine spot-check (a label, not a different check).
    routine_spot_check: bool = False
    reasons: list[TierReasonOut] = Field(default_factory=list)


class QueueCounts(BaseModel):
    """Totals over the filtered, ordered candidate set — computed before the
    requested page is sliced, so the UI can show queue depth truthfully even
    while looking at page one."""

    total: int = 0
    by_lane: dict[str, int] = Field(default_factory=dict)
    by_band: dict[str, int] = Field(default_factory=dict)
    by_sla: dict[str, int] = Field(default_factory=dict)
    #: Admin priority tiers: per facet. Each tier counts what choosing it would
    #: show, with every other filter applied and the tier filter left out.
    by_tier: dict[str, int] = Field(default_factory=dict)
    #: MQA-015: how many each view ("waiting", "taken_down") would show, with
    #: every other filter applied.
    by_view: dict[str, int] = Field(default_factory=dict)


class QueueItem(BaseModel):
    review: ReviewOut
    product: QueueProduct
    author: QueueAuthor | None = None
    suggested_platform: Platform | None = None
    edited_since_monetized: bool = False
    #: How many comments the review has, removed ones excluded. The frame
    #: draws it beside the vote counts; `FeedItemOut` has carried the same
    #: number for the public cards since BUG-006, and the console was the one
    #: surface left printing "no source". Content, not telemetry.
    comment_count: int = 0
    signals: QueueSignals = Field(default_factory=QueueSignals)
    # FR-8 layers 2 and 3: whether plagiarism and reverse image checks ran. A
    # sibling of `signals` for the same reason `priority` is.
    integrity: QueueIntegrityChecks = Field(default_factory=QueueIntegrityChecks)
    #: The voting relationships behind `signals.collusion` / `signals.velocity`.
    voting: QueueVotingEvidence = Field(default_factory=QueueVotingEvidence)
    # The canonical priority assessment for this card (design §5). A sibling of
    # `signals`, never a field inside it — `QueueSignals` stays frozen at the
    # advisory six.
    priority: QueuePriorityAssessment
    # Which review timestamp stood in for the (not-yet-migrated) queue-entry
    # time when priority was evaluated: `review.created_at` for an initial
    # pending review, `review.updated_at` for a monetized-but-edited one. The UI
    # must not present either as precise lifecycle timing.
    queue_time_basis: Literal["review_created_at", "review_updated_at"] = "review_created_at"
    # Put THIS in the affiliate dashboard's sub-ID field when generating the link.
    # The marketplace echoes it back in the monthly report and it is the only way
    # the commission can be attributed to this review (M3 slice 12).
    suggested_sub_id: str | None = None
    #: The admin priority tier for triage (sorting, filtering, labelling).
    triage: TriageOut | None = None


class QueuePage(BaseModel):
    """What ``referral_service.get_prioritized_queue`` returns: one policy-ordered
    page plus the pre-slice totals. The route widens this into
    ``ReviewQueueResponse`` for the compatibility window."""

    items: list[QueueItem] = Field(default_factory=list)
    total: int = 0
    next_cursor: str | None = None
    counts: QueueCounts = Field(default_factory=QueueCounts)


class ReviewQueueResponse(BaseModel):
    # Canonical, server-prioritized slice (design §5). `items` is the full
    # queue ordered by policy — a high-priority review is on page one even if it
    # was created after the first fifty.
    items: list[QueueItem] = Field(default_factory=list)
    total: int = 0
    # Nullable in this compatibility slice: ordering correctness does not depend
    # on the cursor, and offset paging is still accepted. Real cursor paging
    # lands with the queue-entry migration.
    next_cursor: str | None = None
    counts: QueueCounts = Field(default_factory=QueueCounts)
    #: Which earnings-gate phase decides membership (Business Rules §2). Under
    #: Post-Seeding a new review joins only once its trust-weighted votes pass
    #: the gate, so the screen says so instead of looking like it missed one.
    earn_gate_phase: Literal["seeding", "post_seeding"] = "post_seeding"
    # The deprecated `pending` / `edited_since_monetized` arrays are gone. They
    # duplicated `items` under a split the policy does not use — two orderings
    # of one backlog, which is what let the console rank the queue differently
    # from the server. The console reads `items`; "edited" is now a filter on
    # the `edited_after_monetization` factor, and the per-card boolean of the
    # same name stays on `QueueItem`.


class AwaitingPlatform(BaseModel):
    """One marketplace a review's product is listed on. A list, not a single
    field, so a future one-link-per-marketplace rule needs no schema change."""
    platform: Platform
    platform_url: str | None = None
    is_monetizable: bool = True
    has_active_link: bool = False


class AwaitingAffiliateItem(BaseModel):
    review: ReviewOut
    product: QueueProduct
    author_display_name: str | None = None
    platforms: list[AwaitingPlatform] = Field(default_factory=list)
    suggested_platform: Platform | None = None
    suggested_sub_id: str
    #: When the moderator approved earnings (the audit row), if recorded.
    earnings_approved_at: datetime | None = None
    momentum: MomentumFacts


class AwaitingAffiliatePage(BaseModel):
    items: list[AwaitingAffiliateItem]
    total: int

"""reviews + review_versions + referral_links.

Business Rules (Full Record, 2026-09-23) §2: a review is public the moment it is
submitted (`published_at` = submission). Earning is a separate, later decision
(`earn_eligible_status`). §4: published content is frozen; later information is
a new entry in the same thread (`thread_id`). A photo of the item or a receipt is
what `verification_status=verified` records — "Photo provided", never proof of
purchase (§3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    EarnEligibleStatus,
    MaterialRelationship,
    Platform,
    ReferralLinkStatus,
    SpecialRoute,
    Verdict,
    VerificationStatus,
    VerificationTier,
)


class Review(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "reviews"

    review_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # Structured format (FR-3).
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    discussion: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[Verdict] = mapped_column(Enum(Verdict, name="verdict"), nullable=False)
    verdict_explanation: Mapped[str | None] = mapped_column(Text)
    target_audience: Mapped[str | None] = mapped_column(Text)
    anti_target_audience: Mapped[str | None] = mapped_column(Text)
    #: 0 to 5 in half steps (0048). Zero is a real answer, not a missing one.
    star_rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    pros: Mapped[list | None] = mapped_column(JSONB)   # max 10 (app-validated)
    cons: Mapped[list | None] = mapped_column(JSONB)   # max 10 (app-validated)

    # The PUBLIC photos of the item, drawn on the published review (FR-3),
    # in display order (0094). Reviewer uploads only: a review without photos
    # has an EMPTY list - never the product's listing image.
    photo_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'::text[]"), nullable=False)
    # The first of `photo_urls`, kept for every reader written for one photo.
    # `_sync_photos` below keeps the two in step on every flush.
    photo_url: Mapped[str | None] = mapped_column(Text)     # public bucket URL
    # Proof of purchase: an object key into the PRIVATE review-receipts bucket,
    # never a URL. Optional, post-publish, and scoped to moderator evaluation of
    # the earn_eligible gate - readers never see it, so no public API field
    # carries it. Access goes through GET /reviews/{id}/receipt, which
    # authorizes first and then mints a short-lived signed URL.
    receipt_key: Mapped[str | None] = mapped_column(Text)

    @property
    def has_receipt(self) -> bool:
        """Whether proof of purchase was submitted, without saying where.

        This is what the public schema is allowed to know. Serializers read it
        by name via `from_attributes`, so the locator never has to be present
        on a response model for the boolean to be available.
        """
        return bool(self.receipt_key)
    price_paid: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # Disclosure of a material relationship (completion contract X.1, 0046).
    # NULL means the review predates the question - never defaulted to "none",
    # which would record a declaration its author did not make.
    material_relationship: Mapped[MaterialRelationship | None] = mapped_column(
        Enum(MaterialRelationship, name="material_relationship")
    )

    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status"),
        default=VerificationStatus.unverified, nullable=False,
        server_default=VerificationStatus.unverified.value,
    )
    verification_tier: Mapped[VerificationTier] = mapped_column(
        Enum(VerificationTier, name="verification_tier"),
        default=VerificationTier.tier_0, nullable=False,
        server_default=VerificationTier.tier_0.value,
    )

    # Equal-weight community visibility votes (independent of gate voting, FR-7).
    helpful_votes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unhelpful_votes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wilson_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 5), default=0, nullable=False, server_default="0"
    )

    is_removed: Mapped[bool] = mapped_column(default=False, server_default="false")

    # Publication gate (M2 slice 1): NULL = hidden from public; set = live. A new
    # review is created hidden and is published by a moderator action.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # earn_eligible pipeline (FR-6).
    earn_eligible_status: Mapped[EarnEligibleStatus] = mapped_column(
        Enum(EarnEligibleStatus, name="earn_eligible_status"),
        default=EarnEligibleStatus.none, nullable=False,
        server_default=EarnEligibleStatus.none.value,
    )
    affiliate_link: Mapped[str | None] = mapped_column(Text)  # attached manually (§3.2)

    # Version history (M1). Published content is frozen now (Business Rules §4),
    # so the only thing that still moves it is the one allowed photo swap.
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # Threads (Business Rules §4). An original review is its own thread root
    # (`thread_id == id`); a later update is a NEW row carrying the root's id.
    # NULL only on rows written before 0050 by something that bypassed the
    # service; readers treat NULL as "own thread" (see `thread_key`).
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL")
    )
    #: The one photo replacement allowed within 72 hours of publishing; set = spent.
    photo_replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The author deleted this entry. Never a hard delete: see review_service.delete_entry.
    removed_by_author_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The deleted thread had paid out, so it counts in the product's aggregate note.
    removed_after_payout: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    #: Owner decision A (0066): a Super Admin's destination for this thread's
    #: earnings while its latest entry is "It depends" at exactly 2.5 stars.
    #: NULL on every other thread. Set once per 2.5 decision, with its audit row
    #: (ModerationAction.special_routing); cleared when the thread moves off 2.5.
    special_route: Mapped[SpecialRoute | None] = mapped_column(
        Enum(SpecialRoute, name="special_route"))
    special_routed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    special_routed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    @property
    def thread_key(self) -> uuid.UUID:
        return self.thread_id or self.id

    @property
    def is_thread_root(self) -> bool:
        return self.thread_id is None or self.thread_id == self.id


#: The most photos one review entry carries (0094's CHECK says the same).
MAX_REVIEW_PHOTOS = 4


@event.listens_for(Review, "before_insert")
@event.listens_for(Review, "before_update")
def _sync_photos(_mapper, _connection, target: Review) -> None:
    """Keep `photo_url` = the first of `photo_urls`.

    A writer that set only `photo_url` (the single-photo API, scripts) has its
    list follow it - one photo, or none; otherwise the list is the truth and
    `photo_url` is its first entry, or NULL for an empty list. Never a default:
    no photos stays no photos.
    """
    state = inspect(target)
    list_changed = state.attrs.photo_urls.history.has_changes()
    one_changed = state.attrs.photo_url.history.has_changes()
    if one_changed and not list_changed:
        target.photo_urls = [target.photo_url] if target.photo_url else []
    else:
        urls = [u for u in (target.photo_urls or []) if u]
        target.photo_urls = urls
        target.photo_url = urls[0] if urls else None


class ReviewVersion(Base, UUIDPrimaryKey, Timestamps):
    """Immutable snapshot of a review at a point in time (M1 version history)."""

    __tablename__ = "review_versions"
    __table_args__ = (
        UniqueConstraint("review_id", "version_number", name="uq_review_version"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Full snapshot of the editable review fields at this version.
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    edited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    change_note: Mapped[str | None] = mapped_column(Text)


class ReferralLink(Base, UUIDPrimaryKey, Timestamps):
    """Affiliate/referral link history for a review (M2 slice 1).

    `reviews.affiliate_link` mirrors the single active link for fast reads; this
    table is the full audit trail. A partial unique index (in the migration)
    enforces exactly one `active` link per review.
    """

    __tablename__ = "referral_links"

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # Our affiliate sub-ID (M3 slice 12). The moderator sets this in their
    # affiliate dashboard when generating the link, and the marketplace echoes it
    # back in the monthly report (Shopee `Sub_id1..5`, Lazada `Aff Sub ID` /
    # `Sub ID 1..6`). It is the ONLY field that survives the round trip, so it is
    # what reconciliation matches on — without it a report row cannot be
    # attributed to a reviewer at all. See docs/AFFILIATE_REPORT_FORMATS.md.
    # Not globally unique: a review's links share its sub-ID across revoke ->
    # re-attach. A partial unique index (migration) keeps it unique among ACTIVE
    # links only.
    sub_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # True when the pasted URL visibly contains the sub-ID (best-effort check).
    sub_id_in_url: Mapped[bool] = mapped_column(Boolean, default=False,
                                                server_default="false")
    status: Mapped[ReferralLinkStatus] = mapped_column(
        Enum(ReferralLinkStatus, name="referral_link_status"),
        default=ReferralLinkStatus.active, nullable=False,
        server_default=ReferralLinkStatus.active.value,
    )
    # reviews.current_version at attach time — powers the "edited since monetized" flag.
    review_version: Mapped[int] = mapped_column(Integer, nullable=False)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(Text)

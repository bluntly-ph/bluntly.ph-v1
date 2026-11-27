"""Sellers, the claim workflow, and seller reviews (FR-4).

Built as M2 slice 4, withdrawn by owner decision on 2026-07-28 (migration 0024
dropped `seller_reviews`), and reinstated by the completion contract, which
requires the seller flow rather than treating it as optional.

**A seller is not a user.** The withdrawn design hung `seller_reviews.seller_id`
off `users.id`, which works only if every seller has an account. FR-4 requires
*unclaimed* profiles — a store that has been reviewed by buyers but has never
signed up — so the store is its own row and `claimed_by_id` is the nullable
link to whoever proved they run it. Reusing `users` would have made "unclaimed"
unrepresentable.

**Claims are moderator-approved, never automatic.** FR-4 limits seller
verification to "cross-checking store names on submitted proof of purchase
against publicly visible marketplace listings", and the completion contract
says not to invent identity verification. So a claim is a request with evidence
that a moderator decides; nothing in this module grants ownership on its own.

**One seller review per (seller, reviewer).** Enforced in the database, not
only in the service, because a duplicate rating is the cheapest way to move an
aggregate and a service-only guard loses every race.

The four dimensions are FR-4's, and their types carry the specification: the
two binary judgements are booleans (accuracy: accurate / not the same;
completeness: exact order / missing item) and the two graded ones are 1-5, as
is the overall rating.
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
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import Platform, SellerClaimStatus, StoreProductStatus, VoteDirection


class Seller(UUIDPrimaryKey, Timestamps, Base):
    """A store on a marketplace. May exist with nobody behind it."""

    __tablename__ = "sellers"
    __table_args__ = (
        # The same store name on two marketplaces is two sellers; the same name
        # twice on one marketplace is a duplicate, and duplicates split a
        # rating in half.
        UniqueConstraint("platform", "normalized_name", name="uq_seller_platform_name"),
        Index("ix_sellers_claimed_by", "claimed_by_id"),
    )

    #: As the store writes it, for display.
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Casefolded and whitespace-collapsed, for the uniqueness constraint. The
    #: service owns the normalisation so the rule is one function, not a habit.
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)

    platform: Mapped[Platform] = mapped_column(
        Enum(Platform, name="platform"), nullable=False
    )
    #: The store's own page, when a reviewer supplied one. Never scraped.
    store_url: Mapped[str | None] = mapped_column(Text)

    #: Null until a moderator approves a claim. This is the only field that
    #: says a real person speaks for this store.
    claimed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    claim_status: Mapped[SellerClaimStatus] = mapped_column(
        Enum(SellerClaimStatus, name="seller_claim_status"),
        default=SellerClaimStatus.unclaimed,
        server_default=SellerClaimStatus.unclaimed.value,
        nullable=False,
    )



class SellerClaim(UUIDPrimaryKey, Base):
    """A request to speak for a store, and the moderator's decision on it.

    Kept separate from `sellers.claim_status` on purpose: the seller row holds
    the current answer, this holds how it was reached and who decided. A
    rejected claimant can try again with better evidence without the first
    attempt disappearing.
    """

    __tablename__ = "seller_claims"
    __table_args__ = (
        # One *live* request per person per store. A decided one does not block
        # a retry, which is why this is partial rather than a plain unique.
        Index(
            "uq_seller_claim_pending",
            "seller_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_seller_claims_status", "status"),
    )

    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    #: What the claimant says makes them the owner. Free text on purpose: the
    #: moderator cross-checks it against the public listing, and a fixed set of
    #: fields would only invite a fixed set of lies.
    evidence: Mapped[str | None] = mapped_column(Text)

    status: Mapped[SellerClaimStatus] = mapped_column(
        Enum(SellerClaimStatus, name="seller_claim_status"),
        default=SellerClaimStatus.pending,
        server_default=SellerClaimStatus.pending.value,
        nullable=False,
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    # Business Rules §9: ownership is proved by a DTI or SEC business
    # registration, cross-checked against the shop name on the marketplace.
    # NULL on claims filed before 0050 (free-text evidence only).
    registration_kind: Mapped[str | None] = mapped_column(String(8))  # 'dti' | 'sec'
    registration_number: Mapped[str | None] = mapped_column(String(64))
    registered_business_name: Mapped[str | None] = mapped_column(String(200))
    marketplace_shop_name: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SellerReview(UUIDPrimaryKey, Timestamps, Base):
    """A verified buyer's rating of a store, on FR-4's four dimensions.

    Displayed separately from product reviews and carrying no affiliate link:
    nothing here earns, which is why these publish without the moderation gate
    that product reviews go through (`docs/DEVIATIONS.md` §37).
    """

    __tablename__ = "seller_reviews"
    __table_args__ = (
        UniqueConstraint("seller_id", "reviewer_id", name="uq_seller_review_once"),
        CheckConstraint(
            "customer_service BETWEEN 1 AND 5", name="ck_seller_review_service_range"
        ),
        CheckConstraint(
            "packaging_quality BETWEEN 1 AND 5", name="ck_seller_review_packaging_range"
        ),
        CheckConstraint(
            "overall_rating >= 0 AND overall_rating <= 5"
            " AND (overall_rating * 2) = trunc(overall_rating * 2)",
            name="ck_seller_review_overall_range",
        ),
        Index("ix_seller_reviews_seller", "seller_id", "created_at"),
    )

    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    #: SET NULL rather than CASCADE: a deleted account should not silently
    #: revise a store's rating history.
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: What was bought, when the reviewer said. Context for a reader, and the
    #: link back to the purchase the rating is about.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL")
    )

    #: true = matched the advertisement, false = not the same.
    accuracy: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: true = exact order, false = something missing.
    order_completeness: Mapped[bool] = mapped_column(Boolean, nullable=False)
    customer_service: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    packaging_quality: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: 0 to 5 in half steps (0048); the two graded dimensions above stay
    #: whole numbers, because the frame draws them as numbered chips.
    overall_rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    would_recommend: Mapped[bool] = mapped_column(Boolean, nullable=False)

    #: Added by 0043. The composer caps it at 30; the column allows 200.
    title: Mapped[str | None] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(Text)
    #: Public URLs from POST /reviews/photo, each checked as the reviewer's own.
    photo_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default=text("'{}'"), nullable=False
    )

    #: Moderator removal (0043). A flag rather than a delete, so the audit trail
    #: survives and the unique constraint still blocks a straight re-post.
    is_removed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    removal_note: Mapped[str | None] = mapped_column(Text)
    #: Self-reported at submission (Business Rules §10). Never checked against
    #: the marketplace and never presented as verified.
    order_id: Mapped[str | None] = mapped_column(String(64))
    #: The claimed seller's public response (§8, §9). Responding is all a claim
    #: grants over a review: never removal, hiding or suppression.
    seller_response: Mapped[str | None] = mapped_column(Text)
    seller_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when the owner edits the response (0082); seller_response_at keeps the
    #: first response's time, which the median reply time reads.
    seller_response_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SellerReviewAppeal(UUIDPrimaryKey, Timestamps, Base):
    """A claimed seller's "suspected fake" flag on one seller review (§10).

    Only once a seller appeals does an admin ask the reviewer to substantiate
    the review. Statuses: open -> substantiation_requested -> upheld (the review
    is removed) or dismissed (it stays).
    """

    __tablename__ = "seller_review_appeals"

    seller_review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_reviews.id", ondelete="CASCADE"), nullable=False
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False
    )
    appellant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: What the store says is wrong (0090): never_ordered | untrue | breaks_rules.
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="never_ordered",
                                      default="never_ordered")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="open",
                                        default="open")
    substantiation_request: Mapped[str | None] = mapped_column(Text)
    substantiation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    substantiation_response: Mapped[str | None] = mapped_column(Text)
    substantiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class SellerReviewVote(UUIDPrimaryKey, Base):
    """One member's up or down vote on a seller review (QA-043, owner 2026-09-28).

    Helpfulness only: equal weight, no effect on the store's rating, on trust
    or on earnings. One row per (review, member); the author and the store's
    claimed owner cannot vote on it.
    """

    __tablename__ = "seller_review_votes"
    __table_args__ = (
        UniqueConstraint("seller_review_id", "user_id", name="uq_seller_review_vote_once"),
        Index("ix_seller_review_votes_review", "seller_review_id"),
    )

    seller_review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_reviews.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    direction: Mapped[VoteDirection] = mapped_column(
        Enum(VoteDirection, name="vote_direction", create_type=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False)


class SellerReviewReply(UUIDPrimaryKey, Timestamps, Base):
    """A member's reply under a seller review (QA-043): one flat thread.

    The store's own voice stays the single "Response from the store"; this is
    everyone else. Removal is soft, so the thread keeps its shape.
    """

    __tablename__ = "seller_review_replies"
    __table_args__ = (Index("ix_seller_review_replies_review", "seller_review_id", "created_at"),)

    seller_review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_reviews.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_removed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False)


class StoreProduct(UUIDPrimaryKey, Timestamps, Base):
    """A store's link to a product page it sells (0077; Screen/Seller/Products).

    pending → approved | rejected by an Administrator, or cancelled by the
    owner. One live (pending or approved) row per store and product.
    """

    __tablename__ = "store_products"
    __table_args__ = (
        Index("ix_store_products_seller", "seller_id", "status"),
        Index("ix_store_products_status", "status", "created_at"),
        Index("uq_store_products_live", "seller_id", "product_id", unique=True,
              postgresql_where=text("status IN ('pending', 'approved')")),
    )

    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[StoreProductStatus] = mapped_column(
        Enum(StoreProductStatus, name="store_product_status"),
        default=StoreProductStatus.pending, server_default=StoreProductStatus.pending.value,
        nullable=False)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)

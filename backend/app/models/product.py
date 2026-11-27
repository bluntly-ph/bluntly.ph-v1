"""products, product_platforms, price_history.

Manual-first canonicalization (§3.1): a product is submitted via `source_url`
with status `pending`; an admin sets the canonical name fields and flips it to
`canonicalized`. No automated fetch of the URL ever happens.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import (
    ImageSource,
    Platform,
    PriceObservationSource,
    PriceObservationStatus,
    ProductStatus,
)


class Product(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "products"

    product_id: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)

    # Canonical name components (Brand, Line/Series, Key Spec/Variant, Descriptor).
    canonical_name: Mapped[str | None] = mapped_column(String(255), index=True)
    brand: Mapped[str | None] = mapped_column(String(120))
    line: Mapped[str | None] = mapped_column(String(120))
    key_spec: Mapped[str | None] = mapped_column(String(120))
    descriptor: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(120), index=True)

    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status"),
        default=ProductStatus.pending, nullable=False,
        server_default=ProductStatus.pending.value,
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    # Product listing imagery. Distinct from a review's proof photo: this is the
    # merchant's picture of the item, not evidence that a reviewer owns one.
    image_url: Mapped[str | None] = mapped_column(Text)
    image_source: Mapped[ImageSource] = mapped_column(
        Enum(ImageSource, name="image_source"),
        default=ImageSource.none, nullable=False,
        server_default=ImageSource.none.value,
    )
    image_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # Denormalized aggregates (updated in service-layer transactions — ADR/changelog).
    # Median of each reviewer's LATEST entry per thread (Business Rules §4),
    # not a mean over every row. The COLUMN keeps its old name, `avg_rating`:
    # renaming it would break the deployed build during a rollout that migrates
    # before it deploys (0051). Only the attribute says what the value is now.
    median_rating: Mapped[Decimal] = mapped_column(
        "avg_rating", Numeric(3, 2), default=0, nullable=False, server_default="0"
    )

    @property
    def avg_rating(self) -> Decimal:
        """Deprecated alias of `median_rating`, kept for one release of API clients."""
        return self.median_rating
    review_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Time-decayed Wilson trust over published reviews' star_rating >= 4 (M2 slice 4).
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 5), default=0, nullable=False, server_default="0"
    )
    aggregated_pros: Mapped[dict | None] = mapped_column(JSONB)
    aggregated_cons: Mapped[dict | None] = mapped_column(JSONB)
    #: The Edit modal's specs (0071): [{"label": "Battery", "value": "4000 mAh"}, ...].
    specs: Mapped[list | None] = mapped_column(JSONB)

    platforms: Mapped[list[ProductPlatform]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductPlatform(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "product_platforms"
    __table_args__ = (
        UniqueConstraint("product_id", "platform", "platform_url", name="uq_product_platform"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    platform_url: Mapped[str | None] = mapped_column(Text)
    # A6: Lazada may have no affiliate relationship -> not monetizable until resolved.
    is_monetizable: Mapped[bool] = mapped_column(default=True, server_default="true")

    product: Mapped[Product] = relationship(back_populates="platforms")


class PriceHistory(Base, UUIDPrimaryKey, Timestamps):
    """Community-submitted price observations (§3.4). Never scraped."""

    __tablename__ = "price_history"
    __table_args__ = (
        Index("ix_price_history_product_status", "product_id", "status"),
        # One observation per review: editing or resubmitting a review must not
        # multiply the price it reported.
        Index("uq_price_history_review", "review_id", unique=True,
              postgresql_where=text("review_id IS NOT NULL")),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    variant: Mapped[str | None] = mapped_column(String(120))
    observed_at: Mapped[date] = mapped_column(Date, nullable=False)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    #: Pending until a moderator decides (0044). The panel counts approved rows
    #: only; see price_service.panel_from.
    status: Mapped[PriceObservationStatus] = mapped_column(
        Enum(PriceObservationStatus, name="price_observation_status"),
        default=PriceObservationStatus.pending,
        server_default=PriceObservationStatus.pending.value,
        nullable=False,
    )
    source: Mapped[PriceObservationSource] = mapped_column(
        Enum(PriceObservationSource, name="price_observation_source"),
        default=PriceObservationSource.manual,
        server_default=PriceObservationSource.manual.value,
        nullable=False,
    )
    #: The review whose "Let's talk money" card reported this price, if any.
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL")
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    #: Why this observation waits for an admin (Business Rules §16): an outlier
    #: against the product's recent range, or no baseline yet. NULL when it
    #: published on the normal path.
    hold_reason: Mapped[str | None] = mapped_column(String(40))


class ProductAlias(Base, UUIDPrimaryKey):
    """Another name for a canonical product (Business Rules §5, §6).

    Maintained through the admin canonicalization workflow, so search learns a
    synonym at the moment a product is named rather than as a separate chore.
    `normalized` is what search matches, trigram-indexed in migration 0050.
    """

    __tablename__ = "product_aliases"
    __table_args__ = (UniqueConstraint("product_id", "normalized", name="uq_product_alias"),)

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

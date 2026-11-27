"""Minimal product schemas (M1 — enough to support review submission)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.categories import CATEGORIES, normalize_category
from app.core.constants import MANILA
from app.core.link_policy import reject_links
from app.models.enums import (
    Platform,
    PriceObservationSource,
    PriceObservationStatus,
    ProductStatus,
)
from app.schemas.urls import web_url_or_none

# Published in the OpenAPI schema so the contract states what a category may
# be. The server also accepts the legacy spellings in `ALIASES` and normalises
# them, which is deliberately more lenient than what is documented here.
CATEGORY_FIELD = Field(
    default=None,
    description=("Product category. One of the slugs in "
                 "`backend/app/core/categories.py`, which the frontend renders "
                 "as chips on /categories. Null means uncategorised."),
    json_schema_extra={"enum": [*CATEGORIES, None]},
)


def _ph_today() -> date:
    """Today, as the reader experiences it.

    The platform is Philippines-specific by design (PRD S1), so "today" means
    today in Manila. Server-local `date.today()` is UTC in production and is a
    different day for a third of every one.
    """
    return datetime.now(MANILA).date()


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str | None = CATEGORY_FIELD

    # QA-072: a pasted link is not a name. It used to be stored as one — the
    # write-review picker sent the URL itself when nothing was typed — and
    # then shown as the product's title everywhere until a moderator renamed it.
    @field_validator("name")
    @classmethod
    def _not_a_link(cls, value: str) -> str:
        from app.services.listing_names import looks_like_url
        value = value.strip()
        if not value:
            raise ValueError("Give the product a name.")
        if looks_like_url(value):
            raise ValueError("Give the product a name, not a link. The link goes in "
                             "source_url.")
        return value

    brand: str | None = None
    # Required in practice for reviewer submissions (BUG-020) — the route
    # enforces it by role, because a moderator adding a product directly has no
    # marketplace listing to point at.
    source_url: str | None = Field(default=None, max_length=2048)

    # The moderator queue renders this as a clickable link (ModerationQueue.tsx),
    # so it is a submitter-chosen string that a moderator activates.
    @field_validator("source_url")
    @classmethod
    def _only_web_source(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Listing links")

    # A category the frontend cannot render is worse than none: the product
    # simply vanishes from category navigation, silently. See app/core/categories.py.
    @field_validator("category")
    @classmethod
    def _canonical_category(cls, v: str | None) -> str | None:
        return normalize_category(v)


MAX_SPECS = 12


class ProductSpec(BaseModel):
    """One of a product's specifics (0071), e.g. "Battery" / "4000 mAh": what
    tells one variant of a product from another (meeting 2026-10-02, 10:45)."""

    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=120)
    #: The Edit modal's "In name" switch: this value is part of the canonical
    #: name ("Xiaomi Redmi Note 13 Pro 5G 8GB 256GB").
    in_name: bool = False

    @field_validator("label", "value")
    @classmethod
    def _plain_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("A spec needs a label and a value.")
        return reject_links(value, field="product specs")


class ProductCanonicalize(BaseModel):
    """A moderator's canonical naming of a pending submission (BUG-020).

    The four parts the naming convention asks for are separate fields rather
    than one free-text box, because that is what keeps two people naming the
    same product the same way — which is the entire point of consolidating
    reviews under one entry.
    """

    #: Required unless the name is saved "As is" (Overlay/Product/Edit · As is,
    #: Figma 8277:29379): a generic product has no brand, line or model.
    brand: str = Field(default="", max_length=120)
    product_line: str = Field(default="", max_length=160)
    #: "As is": the name exactly as typed; brand / line / spec parts are then
    #: optional and never added to it.
    name_as_is: str | None = Field(default=None, max_length=255)
    key_spec: str | None = Field(default=None, max_length=120)
    descriptor: str | None = Field(default=None, max_length=120)
    category: str | None = CATEGORY_FIELD
    #: Business Rules §6: synonyms maintained as products are named ("jisulife
    #: fan", "life 9"). Searched alongside the canonical name.
    aliases: list[str] = Field(default_factory=list, max_length=20)
    #: The full spec list, in order (0071). Omitted (null) leaves the product's
    #: specs as they are; [] clears them.
    specs: list[ProductSpec] | None = Field(default=None, max_length=MAX_SPECS)

    @field_validator("specs")
    @classmethod
    def _one_value_per_label(cls, v: list[ProductSpec] | None) -> list[ProductSpec] | None:
        if v is not None:
            labels = [s.label.casefold() for s in v]
            if len(labels) != len(set(labels)):
                raise ValueError("Each spec label appears once.")
        return v

    # A category the frontend cannot render is worse than none: the product
    # simply vanishes from category navigation, silently. See app/core/categories.py.
    @field_validator("category")
    @classmethod
    def _canonical_category(cls, v: str | None) -> str | None:
        return normalize_category(v)

    @model_validator(mode="after")
    def _parts_or_as_is(self) -> ProductCanonicalize:
        as_is = (self.name_as_is or "").strip()
        if self.name_as_is is not None and len(as_is) < 2:
            raise ValueError("A name saved as is needs at least 2 characters.")
        if not as_is and (not self.brand.strip() or not self.product_line.strip()):
            raise ValueError("Brand and line are required unless the name is saved as is.")
        return self

    @property
    def as_is(self) -> bool:
        return bool((self.name_as_is or "").strip())

    def canonical_name(self) -> str:
        if self.as_is:
            return " ".join((self.name_as_is or "").split())
        parts = [self.brand, self.product_line, self.key_spec, self.descriptor]
        parts += [s.value for s in (self.specs or []) if s.in_name]
        return " ".join(p.strip() for p in parts if p and p.strip())


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: str | None = None
    canonical_name: str | None = None
    #: The name parts the canonical name was built from (null before naming).
    brand: str | None = None
    line: str | None = None
    key_spec: str | None = None
    descriptor: str | None = None
    specs: list[ProductSpec] = Field(default_factory=list)
    category: str | None = None
    status: ProductStatus
    #: Median of each reviewer's latest entry (Business Rules §4).
    median_rating: Decimal = Decimal("0")
    #: Deprecated alias of `median_rating`, kept one release for API clients.
    avg_rating: Decimal
    review_count: int
    #: Paid threads their authors deleted: shown only as this aggregate (§4).
    removed_after_payout_count: int = 0
    # See FeedProduct.image_url (BUG-009).
    image_url: str | None = None
    # Trust rating + computed visibility flag (M2 slice 4).
    trust_score: Decimal = Decimal("0")
    low_trust: bool = False
    created_at: datetime

    @field_validator("specs", mode="before")
    @classmethod
    def _none_is_empty(cls, v):
        return v or []


class PriceObservationIn(BaseModel):
    """A price report (Business Rules §16): always attached to the reporter's
    own review of the product, whose photo or receipt backs it."""

    review_id: uuid.UUID | None = None
    platform: Platform
    price: Decimal = Field(gt=0, le=Decimal("10000000"),
                           description="Price actually paid, in PHP.")
    observed_at: date = Field(description="The date this price was seen or paid.")
    variant: str | None = Field(default=None, max_length=120)

    @field_validator("observed_at")
    @classmethod
    def _not_in_the_future(cls, value: date) -> date:
        # A price cannot have been paid tomorrow. Cheap to check here, and it
        # keeps `latest_observed_at` on the panel honest.
        #
        # Against the *Philippine* date, not the server's. `date.today()` is
        # UTC on Vercel, and Manila is UTC+8 - so for eight hours of every day
        # (UTC 16:00-23:59, i.e. midnight to 08:00 in Manila) a reader entering
        # the price they paid today was told it was in the future. A third of
        # each day, for the only audience this platform has.
        if value > _ph_today():
            raise ValueError("observed_at cannot be in the future.")
        return value


class PriceObservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    platform: Platform
    price: Decimal
    observed_at: date
    variant: str | None = None
    #: "approved" on the normal path; "pending" while held for an admin glance.
    status: PriceObservationStatus
    source: PriceObservationSource
    #: Why it is held (`outlier`, `no_baseline`), or None.
    hold_reason: str | None = None
    review_id: uuid.UUID | None = None
    created_at: datetime


class PricePointOut(BaseModel):
    observed_at: date
    price: Decimal


class PricePanelOut(BaseModel):
    """Price history for a product (Business Rules §16).

    `sufficient` is true once any approved observation exists; prices are null
    before that. `required_independent` is kept for API compatibility and now
    means the baseline size below which new prices get an admin glance.
    """

    product_id: uuid.UUID
    sufficient: bool
    observation_count: int
    independent_count: int
    required_independent: int
    currency: str = "PHP"
    low: Decimal | None = None
    high: Decimal | None = None
    median: Decimal | None = None
    latest_observed_at: date | None = None
    platforms: list[str] = Field(default_factory=list)
    #: Observations waiting for a moderator: counted so the page can say so,
    #: never priced.
    pending_count: int = 0
    #: §16 price history: one line per marketplace, never blended. A marketplace
    #: with no observations is absent, so the UI shows no toggle for it.
    series: dict[str, list[PricePointOut]] = Field(default_factory=dict)


class PriceObservationQueueItem(BaseModel):
    """One observation as the moderator's queue shows it."""

    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str | None = None
    platform: Platform
    price: Decimal
    variant: str | None = None
    observed_at: date
    source: PriceObservationSource
    status: PriceObservationStatus
    #: Who reported it, so a moderator can notice one person reporting repeatedly.
    submitter_username: str | None = None
    decision_note: str | None = None
    #: Why it waits: `outlier` or `no_baseline` (§16).
    hold_reason: str | None = None
    created_at: datetime
    #: What the product usually costs on this marketplace: the median of its
    #: approved prices in the hold rule's window, and how many there are
    #: (MQA-042: a ₱24,444 fan next to "usually ₱699"). None when there are none.
    usual_median: Decimal | None = None
    usual_count: int = 0
    #: The viewer reported it, so they cannot decide it.
    reported_by_viewer: bool = False


class PriceObservationCount(BaseModel):
    total: int


class PriceObservationDecision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)


class ComparisonEntry(BaseModel):
    """One column of the side-by-side comparison (FR-2)."""

    product: ProductOut
    price: PricePanelOut
    # Verified review signal. Seller ratings are deliberately absent: FR-2 named
    # them, but seller reviews were withdrawn from contract on 2026-07-28
    # (MILESTONES.md), so there is nothing truthful to put here.
    review_count: int
    median_rating: Decimal | None = None
    avg_rating: Decimal | None = None
    trust_score: Decimal | None = None
    verified_review_count: int = 0


class ComparisonOut(BaseModel):
    entries: list[ComparisonEntry]
    not_found: list[uuid.UUID] = Field(default_factory=list)


class ProductAttachIn(BaseModel):
    """Attach a pending submission to an existing canonical product (§5)."""

    target_product_id: uuid.UUID


class ProductAliasesIn(BaseModel):
    aliases: list[str] = Field(min_length=1, max_length=20)


class ListingLinkOut(BaseModel):
    """What a pasted listing link tells us without fetching it (QA-072)."""

    url: str
    #: "shopee" / "lazada" / … when the host is a known marketplace; else null.
    marketplace: str | None = None
    #: The product name written into the link's path, for the reviewer to
    #: edit. Null when the link carries none — then the reviewer types it.
    proposed_name: str | None = None
    #: The product already on bluntly for this exact listing, if any.
    existing_product: ProductOut | None = None

"""The search filter sheet's review filters, step 2 (Figma 7762:9999, 2026-10-07).

Screen/Search/Reviews/Filters draws three groups the feed did not serve:

  Rating     All · 5★ · 4★ · 3★ · 2★ · 1★   — several may be picked; a review
             is in the "4★" group when its stars are 4 or 4.5 (whole-star
             buckets, the way the seller page's half stars are counted, QA-057).
  Show only  With photos · Verified buyers · Recommends it — each narrows.
             "Verified buyers" is verification_status = verified (a checked
             proof of purchase); "Recommends it" is the verdict "Yes,
             absolutely" — "It depends" is not a recommendation.
  Variant    All · one product's variants. A review's variant is the one its
             reviewer gave with the price they paid (price_history.variant on
             the review's own observation); rejected observations do not count.
             Offered only with one product (the search's product bar), since a
             variant name means nothing across products.

Each is a WHERE on the same statement the page and its count share
(review_service._feed_stmt), so "Show 42 reviews" never disagrees with the list.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Integer

from app.models.enums import PriceObservationStatus, Verdict, VerificationStatus
from app.models.product import PriceHistory
from app.models.review import Review

STARS = (1, 2, 3, 4, 5)
#: How many variant chips a product offers at most (the frame draws three).
MAX_VARIANTS = 12


@dataclass(frozen=True)
class FeedShow:
    """The sheet's Rating, Show only and Variant choices. Empty = no filter."""

    stars: tuple[int, ...] = ()
    photos: bool = False
    verified: bool = False
    recommends: bool = False
    variant: str | None = None

    @classmethod
    def of(cls, *, stars: Sequence[int] | None = None, photos: bool = False,
           verified: bool = False, recommends: bool = False,
           variant: str | None = None) -> FeedShow:
        picked = tuple(sorted({s for s in (stars or ()) if s in STARS}))
        # All five buckets is the same as none: every review has 0.5-5 stars...
        # except a 0-star one, which "All" (no filter) keeps and 1★ would not.
        if len(picked) == len(STARS):
            picked = ()
        return cls(stars=picked, photos=photos, verified=verified,
                   recommends=recommends, variant=(variant or "").strip() or None)


def _variant_rows():
    """Each review's own reported variant, when it gave one."""
    return (select(PriceHistory.review_id, PriceHistory.variant)
            .where(PriceHistory.review_id.isnot(None), PriceHistory.variant.isnot(None),
                   PriceHistory.status != PriceObservationStatus.rejected))


def apply(stmt, show: FeedShow | None):
    """`stmt` narrowed to the reviews `show` keeps."""
    if show is None:
        return stmt
    if show.stars:
        # 4.5 is in the 4★ bucket; 5.0 is the only 5★.
        stmt = stmt.where(cast(func.floor(Review.star_rating), Integer).in_(show.stars))
    if show.photos:
        stmt = stmt.where(func.cardinality(Review.photo_urls) > 0)
    if show.verified:
        stmt = stmt.where(Review.verification_status == VerificationStatus.verified)
    if show.recommends:
        stmt = stmt.where(Review.verdict == Verdict.yes_absolutely)
    if show.variant:
        rows = _variant_rows().subquery()
        stmt = stmt.where(Review.id.in_(
            select(rows.c.review_id).where(func.lower(rows.c.variant) == show.variant.lower())))
    return stmt


def variants_for_product(db: Session, product_id: uuid.UUID) -> list[str]:
    """The variants a product's published reviews report, most-reviewed first.

    Spelling differences of one variant ("4000mAh" / "4000 mAh") stay separate:
    folding them would be guessing, and the chip shows what reviewers wrote.
    """
    rows = _variant_rows().subquery()
    name = func.min(rows.c.variant)
    stmt = (select(name, func.count())
            .select_from(rows)
            .join(Review, Review.id == rows.c.review_id)
            .where(Review.product_id == product_id, Review.is_removed.is_(False),
                   Review.published_at.isnot(None))
            .group_by(func.lower(rows.c.variant))
            .order_by(func.count().desc(), name)
            .limit(MAX_VARIANTS))
    return [v for v, _ in db.execute(stmt).all()]

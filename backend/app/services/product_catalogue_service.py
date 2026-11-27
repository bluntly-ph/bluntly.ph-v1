"""The admin Products catalogue (Figma Screen/Admin/Products/Catalogue 7967:11173):
every named product with its picture, its "Also:" aliases, category, review
count and a price trend — the community prices moderators approved (FR-2),
oldest to newest, ending on the latest. Searchable, filterable by category,
sortable, paged. Nothing is stored here; it reads the catalogue as it is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import PriceObservationStatus, ProductStatus
from app.models.product import PriceHistory, Product, ProductAlias

TREND_POINTS = 8
SORTS = ("reviews", "name", "newest")


@dataclass
class CatalogueRow:
    id: uuid.UUID
    name: str
    image_url: str | None
    category: str | None
    review_count: int
    aliases: list[str] = field(default_factory=list)
    #: Approved prices, oldest first (at most TREND_POINTS); empty = no data.
    price_trend: list[Decimal] = field(default_factory=list)
    latest_price: Decimal | None = None


def counts(db: Session) -> tuple[int, int]:
    """(in the catalogue, waiting in the queue) — the two tabs' badges."""
    rows = dict(db.execute(select(Product.status, func.count(Product.id))
                           .group_by(Product.status)).all())
    return int(rows.get(ProductStatus.canonicalized, 0)), int(rows.get(ProductStatus.pending, 0))


def catalogue(db: Session, *, q: str | None = None, category: str | None = None,
              sort: str = "reviews", limit: int = 10,
              offset: int = 0) -> tuple[list[CatalogueRow], int]:
    where = [Product.status == ProductStatus.canonicalized]
    if category:
        where.append(Product.category == category)
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        where.append(or_(
            Product.canonical_name.ilike(like),
            exists().where(ProductAlias.product_id == Product.id, ProductAlias.alias.ilike(like))))
    total = int(db.scalar(select(func.count(Product.id)).where(*where)) or 0)
    order = {"reviews": (Product.review_count.desc(), Product.canonical_name.asc()),
             "name": (Product.canonical_name.asc(),),
             "newest": (Product.created_at.desc(),)}[sort if sort in SORTS else "reviews"]
    products = list(db.scalars(select(Product).where(*where).order_by(*order, Product.id)
                               .limit(max(1, min(limit, 100))).offset(max(0, offset))))
    ids = [p.id for p in products]
    aliases: dict[uuid.UUID, list[str]] = {}
    trend: dict[uuid.UUID, list[Decimal]] = {}
    if ids:
        for pid, alias in db.execute(select(ProductAlias.product_id, ProductAlias.alias)
                                     .where(ProductAlias.product_id.in_(ids))
                                     .order_by(ProductAlias.alias)).all():
            aliases.setdefault(pid, []).append(alias)
        ranked = (select(PriceHistory.product_id, PriceHistory.price, PriceHistory.observed_at,
                         func.row_number().over(
                             partition_by=PriceHistory.product_id,
                             order_by=(PriceHistory.observed_at.desc(),
                                       PriceHistory.id.desc())).label("n"))
                  .where(PriceHistory.product_id.in_(ids),
                         PriceHistory.status == PriceObservationStatus.approved)
                  .subquery())
        for pid, price, _seen in db.execute(
                select(ranked.c.product_id, ranked.c.price, ranked.c.observed_at)
                .where(ranked.c.n <= TREND_POINTS)
                .order_by(ranked.c.product_id, ranked.c.observed_at.asc())).all():
            trend.setdefault(pid, []).append(Decimal(price))
    rows = [CatalogueRow(id=p.id, name=p.canonical_name or "Unnamed product",
                         image_url=p.image_url, category=p.category,
                         review_count=int(p.review_count or 0), aliases=aliases.get(p.id, []),
                         price_trend=trend.get(p.id, []),
                         latest_price=trend[p.id][-1] if trend.get(p.id) else None)
            for p in products]
    return rows, total

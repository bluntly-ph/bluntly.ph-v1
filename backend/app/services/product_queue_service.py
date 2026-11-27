"""The admin Products queue (meeting 2026-10-02, 9:08): products members
submitted that are not in the catalogue yet — who submitted each, where its
link points, and how long it has waited.

The link is previewed from the URL alone, never fetched (the owner's
no-scraping rule; and an unknown link is exactly what not to open): its host,
whether that host is one of the marketplaces Bluntly links to, and whether it
is https. "To avoid phishing", as the meeting put it, is the point.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ProductStatus
from app.models.product import Product
from app.models.user import User
from app.services.canonical_service import marketplace_for_url

LEVEL_NAMES = ("Newcomer", "Contributor", "Verified Buyer", "Established Reviewer",
               "Trusted Reviewer", "Community Expert")


@dataclass(frozen=True)
class LinkPreview:
    url: str
    host: str | None
    #: shopee | lazada | amazon — a marketplace Bluntly links to; None otherwise.
    marketplace: str | None
    https: bool


@dataclass(frozen=True)
class QueueProduct:
    id: uuid.UUID
    name: str | None
    category: str | None
    image_url: str | None
    link: LinkPreview | None
    submitted_by_id: uuid.UUID | None
    submitted_by_name: str | None
    submitter_trust_stage: int | None
    submitter_level_name: str | None
    submitted_at: datetime
    waiting_days: int
    review_count: int


def preview(url: str | None) -> LinkPreview | None:
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return LinkPreview(url=url, host=None, marketplace=None, https=False)
    market = marketplace_for_url(url)
    return LinkPreview(url=url, host=(parts.hostname or None), https=parts.scheme == "https",
                       marketplace=market.value if market is not None else None)


def queue(db: Session, *, sort: str = "oldest", limit: int = 100,
          now: datetime | None = None) -> tuple[list[QueueProduct], int]:
    now = now or datetime.now(UTC)
    total = int(db.scalar(select(func.count(Product.id))
                          .where(Product.status == ProductStatus.pending)) or 0)
    order = Product.created_at.asc() if sort == "oldest" else Product.created_at.desc()
    rows = db.execute(
        select(Product, User)
        .outerjoin(User, User.id == Product.submitted_by)
        .where(Product.status == ProductStatus.pending)
        .order_by(order, Product.id).limit(max(1, min(limit, 200)))).all()
    out = []
    for product, user in rows:
        stage = int(user.trust_stage or 0) if user is not None else None
        created = product.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        name = None
        if user is not None:
            name = user.display_name or (f"@{user.username}" if user.username else None)
        out.append(QueueProduct(
            id=product.id, name=product.canonical_name, category=product.category,
            image_url=product.image_url, link=preview(product.source_url),
            submitted_by_id=user.id if user is not None else None,
            submitted_by_name=name,
            submitter_trust_stage=stage,
            submitter_level_name=LEVEL_NAMES[stage] if stage is not None else None,
            submitted_at=product.created_at, waiting_days=max(0, (now - created).days),
            review_count=int(product.review_count or 0)))
    return out, total

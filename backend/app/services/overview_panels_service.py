"""The redesigned admin Overview's two data panels (Figma "Draft/Admin/Overview v3",
meeting 2026-10-02): the Review queue card and the Affiliate earnings card.

REVIEW QUEUE. Four tabs: Earn eligible, Flagged, First review, New product.
Membership is exactly the rule `admin_overview_service._breakdown` already
counts by, over the same assessed backlog the queue lists, so a tab's number
equals the Overview breakdown bar of the same name. The tabs overlap on purpose
(one review can be verified and a first submission). Each tab previews its five
most urgent cards, by SLA due time.

AFFILIATE EARNINGS. Read from the canonical affiliate store
(`affiliate_postbacks`), the same table the affiliate ledger and the CSV
imports write:

  verified   commission (`reported_payout`) on orders the marketplace marked
             completed, dated by `completed_at` (import time when missing)
  returned   commission on orders later returned, dated by `returned_at`
  absorbed   what a return could not claw back because it was already paid out
             (`unrecovered_amount`): the platform's loss
  pending    orders still pending, by marketplace, whatever their date

Nothing is estimated. With no imports, every figure is zero and the bars are
flat, which is the truth of an empty ledger.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import AffiliateTxStatus, VerificationStatus
from app.models.postback import AffiliatePostback
from app.models.product import Product
from app.models.review import Review
from app.services import referral_service

MANILA = ZoneInfo("Asia/Manila")
ZERO = Decimal("0")

#: Cards previewed per tab on the Overview.
PREVIEW_LIMIT = 5

QueueTabKey = Literal["earn_eligible", "flagged", "first_review", "new_product"]
QUEUE_TABS: tuple[tuple[QueueTabKey, str], ...] = (
    ("earn_eligible", "Earn eligible"),
    ("flagged", "Flagged"),
    ("first_review", "First review"),
    ("new_product", "New product"),
)

EarningsRange = Literal["1M", "6M", "1Y"]


@dataclass(frozen=True)
class QueuePreviewItem:
    review_id: uuid.UUID
    product_name: str | None
    image_url: str | None
    author_name: str | None
    star_rating: int
    entered_at: datetime
    due_at: datetime
    sla_state: str


@dataclass(frozen=True)
class QueuePreviewTab:
    key: str
    label: str
    count: int
    items: list[QueuePreviewItem] = field(default_factory=list)


def _usable(url: str | None) -> str | None:
    """`usablePhoto` (lib/image.ts): an http(s) URL that is not a placeholder."""
    if url and url.startswith("http") and "example.com" not in url:
        return url
    return None


def queue_preview(db: Session, *, now: datetime | None = None) -> list[QueuePreviewTab]:
    cards = referral_service.open_queue_cards(db, now=now)
    if not cards:
        return [QueuePreviewTab(key, label, 0) for key, label in QUEUE_TABS]

    rows = [row for _, row, _ in cards]
    author_ids = {r.author_id for r in rows if r.author_id}
    product_ids = {r.product_id for r in rows if r.product_id}

    # The same two questions `_breakdown` asks: has this author published
    # anything yet, and has this product any published review yet.
    published_authors = set(db.scalars(
        select(Review.author_id).where(
            Review.author_id.in_(author_ids),
            Review.published_at.is_not(None),
            Review.is_removed.is_(False),
        )
    )) if author_ids else set()
    reviewed_products = set(db.scalars(
        select(Review.product_id).where(
            Review.product_id.in_(product_ids),
            Review.published_at.is_not(None),
            Review.is_removed.is_(False),
        )
    )) if product_ids else set()
    product_images = dict(db.execute(
        select(Product.id, Product.image_url).where(Product.id.in_(product_ids))
    ).all()) if product_ids else {}

    def member(key: str, row: Review, reports: int) -> bool:
        if key == "earn_eligible":
            return row.verification_status == VerificationStatus.verified
        if key == "flagged":
            return reports > 0
        if key == "first_review":
            return row.author_id not in published_authors
        return row.product_id not in reviewed_products

    tabs: list[QueuePreviewTab] = []
    for key, label in QUEUE_TABS:
        chosen = [(item, row) for item, row, reports in cards if member(key, row, reports)]
        chosen.sort(key=lambda pair: pair[0].priority.due_at)
        items = []
        for item, row in chosen[:PREVIEW_LIMIT]:
            entered = (row.updated_at if item.queue_time_basis == "review_updated_at"
                       else row.created_at)
            items.append(QueuePreviewItem(
                review_id=row.id,
                product_name=item.product.canonical_name,
                image_url=_usable(product_images.get(row.product_id))
                or _usable(item.review.photo_url),
                author_name=item.author.display_name if item.author else None,
                star_rating=int(item.review.star_rating),
                entered_at=entered,
                due_at=item.priority.due_at,
                sla_state=item.priority.sla_state.value,
            ))
        tabs.append(QueuePreviewTab(key, label, len(chosen), items))
    return tabs


# Affiliate earnings ------------------------------------------------------------

@dataclass(frozen=True)
class EarningsBucket:
    label: str
    start: date
    end: date  # exclusive
    verified: Decimal = ZERO
    returned: Decimal = ZERO


@dataclass(frozen=True)
class PendingPlatform:
    platform: str
    orders: int
    amount: Decimal


@dataclass(frozen=True)
class AffiliateEarnings:
    range: str
    verified: Decimal
    previous_verified: Decimal
    returned: Decimal
    absorbed: Decimal
    pending: list[PendingPlatform]
    buckets: list[EarningsBucket]

    @property
    def delta_pct(self) -> float | None:
        """Change against the equal period before; None when there was nothing
        to compare against (a percentage of zero is not a number)."""
        if self.previous_verified <= 0:
            return None
        return float((self.verified - self.previous_verified) / self.previous_verified * 100)

    @property
    def returned_pct(self) -> float | None:
        if self.verified <= 0:
            return None
        return float(self.returned / self.verified * 100)

    @property
    def pending_orders(self) -> int:
        return sum(p.orders for p in self.pending)


def _month_start(d: date, back: int = 0) -> date:
    """The first of the month `back` months before `d` (negative: after)."""
    y, m = divmod(d.year * 12 + (d.month - 1) - back, 12)
    return date(y, m + 1, 1)


def _buckets(rng: EarningsRange, today: date) -> list[tuple[str, date, date]]:
    """Calendar months for 6M and 1Y (the current month last); the current week
    and the three before it for 1M, each starting on a Monday."""
    if rng == "1M":
        monday = today - timedelta(days=today.weekday())
        starts = [monday - timedelta(weeks=n) for n in range(3, -1, -1)]
        return [(s.strftime("%b %-d"), s, s + timedelta(weeks=1)) for s in starts]
    months = 6 if rng == "6M" else 12
    out = []
    for back in range(months - 1, -1, -1):
        start = _month_start(today, back)
        out.append((start.strftime("%b"), start, _month_start(start, -1)))
    return out


def _manila_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (datetime.combine(start, datetime.min.time(), tzinfo=MANILA),
            datetime.combine(end, datetime.min.time(), tzinfo=MANILA))


def _sum_payout(db: Session, status: AffiliateTxStatus, dated, start: date, end: date) -> Decimal:
    lo, hi = _manila_bounds(start, end)
    return Decimal(db.scalar(
        select(func.coalesce(func.sum(AffiliatePostback.reported_payout), 0)).where(
            AffiliatePostback.canonical_status == status, dated >= lo, dated < hi)
    ) or 0)


def affiliate_earnings(db: Session, rng: EarningsRange = "6M", *,
                       today: date | None = None) -> AffiliateEarnings:
    today = today or datetime.now(MANILA).date()
    completed_on = func.coalesce(AffiliatePostback.completed_at, AffiliatePostback.received_at)
    returned_on = func.coalesce(AffiliatePostback.returned_at, AffiliatePostback.received_at)

    buckets = [
        EarningsBucket(
            label=label, start=start, end=end,
            verified=_sum_payout(db, AffiliateTxStatus.completed, completed_on, start, end),
            returned=_sum_payout(db, AffiliateTxStatus.returned, returned_on, start, end),
        )
        for label, start, end in _buckets(rng, today)
    ]
    first, last = buckets[0].start, buckets[-1].end
    previous = _sum_payout(db, AffiliateTxStatus.completed, completed_on,
                           first - (last - first), first)

    lo, hi = _manila_bounds(first, last)
    absorbed = Decimal(db.scalar(
        select(func.coalesce(func.sum(AffiliatePostback.unrecovered_amount), 0)).where(
            returned_on >= lo, returned_on < hi)
    ) or 0)

    pending_rows = db.execute(
        select(AffiliatePostback.platform, func.count(),
               func.coalesce(func.sum(AffiliatePostback.reported_payout), 0))
        .where(AffiliatePostback.canonical_status == AffiliateTxStatus.pending)
        .group_by(AffiliatePostback.platform)
        .order_by(AffiliatePostback.platform)
    ).all()
    pending = [
        PendingPlatform(platform=p.value if hasattr(p, "value") else str(p),
                        orders=int(n), amount=Decimal(amount))
        for p, n, amount in pending_rows
    ]

    return AffiliateEarnings(
        range=rng,
        verified=sum((b.verified for b in buckets), ZERO),
        previous_verified=previous,
        returned=sum((b.returned for b in buckets), ZERO),
        absorbed=absorbed,
        pending=pending,
        buckets=buckets,
    )

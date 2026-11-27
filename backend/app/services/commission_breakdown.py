"""The reviewer's "Commission breakdown" sheet (Figma 9057:47088, Proposals
section 35; opened from the ⓘ on "Where the commission went").

One read, every figure a sum over what the marketplaces reported:

    gross to net   Gross sales -> Gross commission -> Reversals -> Net commission
    split          You 30% / Honesty Fund 30% / Bluntly 40% of the net, plus
                   Pending (reported, not finalised, not counted)
    marketplace    Shopee and Lazada: gross commission and orders
    product        net commission per catalogue product, most first

The labels are Admin > Financial reports' own: Gross commission, Net
commission, Reversals, Net earnings.

SOURCES. The canonical transaction store (`affiliate_postbacks`, one row per
marketplace item) for every row credited to this member — `reviewer_id`, or an
attributed review they wrote. Ledger entries with no report row behind them
(the older CSV path and seeded demo entries) are counted as completed items
with their stored gross and no sales figure, so nothing the member was
credited disappears from the sheet.

RULES (owner dev note, 2026-10-19):

- An item counts when its ORDER is completed. Its commission is the report's
  per-item figure (never the order total, never rate x price — Shopee caps it
  per item). Items of a completed order that the marketplace then cancelled or
  returned are Reversals; their commission comes off.
- Pending items are shown apart and never counted.
- Cancelled orders are counted for the Reversals line ("3 cancelled") but carry
  no commission; "refunded" counts the items with a refund amount.
- Sums run at the report's precision and are rounded once, half up: the
  total of 123 Shopee items is ₱1,962.70265, shown ₱1,962.70.
- The split is the platform's flat rule (`earnings.split_commission`) applied
  to the net, so the three always add up to it.
- Products group by our catalogue product; an item no product carries yet
  groups by its marketplace item and shows the marketplace's title.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.commission import Commission
from app.models.enums import AffiliateTxStatus
from app.models.postback import AffiliatePostback
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.services.earnings import split_commission

CENT = Decimal("0.01")
ZERO = Decimal("0")
#: Every marketplace the sheet draws a tile for, in its order, even at zero.
MARKETPLACES = ("shopee", "lazada")
#: The rows "By product" shows before "See all N products".
TOP_PRODUCTS = 5


def _cents(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class MarketplaceTotal:
    platform: str
    gross_commission: Decimal
    orders: int


@dataclass
class ProductTotal:
    #: The catalogue product, or None for an item no product carries yet.
    product_id: uuid.UUID | None
    name: str
    net_commission: Decimal
    orders: int
    #: None when no row reports a sales figure (ledger entries carry none).
    sales: Decimal | None


@dataclass
class CommissionBreakdown:
    #: The span of the completed orders counted (Manila time), or None.
    first_completed: datetime | None = None
    last_completed: datetime | None = None
    gross_sales: Decimal = Decimal("0.00")
    orders: int = 0
    items: int = 0
    #: The orders and items Gross sales is summed over: those that report a
    #: sales figure (a ledger entry has none, so it counts in `orders` only).
    sales_orders: int = 0
    sales_items: int = 0
    gross_commission: Decimal = Decimal("0.00")
    #: A positive amount; the sheet draws it as −₱.
    reversals: Decimal = Decimal("0.00")
    cancelled_items: int = 0
    refunded_items: int = 0
    net_commission: Decimal = Decimal("0.00")
    #: The split of the net: the reviewer's Net earnings, the Honesty Fund, Bluntly.
    you: Decimal = Decimal("0.00")
    honesty_fund: Decimal = Decimal("0.00")
    bluntly: Decimal = Decimal("0.00")
    pending_commission: Decimal = Decimal("0.00")
    pending_orders: int = 0
    #: What the ledger actually credited the member (their stored shares,
    #: reversals netted) — the part of `you` that is money in their wallet.
    #: The rest is reported sales no review is tied to yet (Business Rules §15).
    credited: Decimal = Decimal("0.00")
    marketplaces: list[MarketplaceTotal] = field(default_factory=list)
    #: Every product, most net commission first; the sheet shows TOP_PRODUCTS.
    products: list[ProductTotal] = field(default_factory=list)


@dataclass
class _Item:
    order: str
    platform: str
    order_completed: bool
    status: AffiliateTxStatus
    commission: Decimal
    sales: Decimal
    #: False for a ledger entry: it records commission, not what was sold.
    has_sales: bool
    refunded: bool
    completed_at: datetime | None
    product_key: str
    product_id: uuid.UUID | None
    name: str


def _platform(value) -> str:
    return getattr(value, "value", value) or "other"


def _report_items(db: Session, user: User, review_ids: list[uuid.UUID],
                  product_id: uuid.UUID | None) -> list[_Item]:
    credited = [AffiliatePostback.reviewer_id == user.id]
    if review_ids:
        credited.append(AffiliatePostback.review_id.in_(review_ids))
    query = select(AffiliatePostback).where(or_(*credited))
    if product_id is not None:
        query = query.where(AffiliatePostback.product_id == product_id)
    items = []
    for p in db.scalars(query):
        order_word = (p.order_status or "").strip().lower()
        status = p.canonical_status
        # Lazada reports no separate order word: its item status is the order's.
        order_completed = (order_word == "completed" if p.platform.value == "shopee"
                           else status in (AffiliateTxStatus.completed,
                                           AffiliateTxStatus.returned))
        commission = p.item_commission if p.item_commission is not None else (
            p.reported_payout or ZERO)
        key = (f"product:{p.product_id}" if p.product_id
               else f"item:{_platform(p.platform)}:{p.source_item_id or p.external_sub_order_id}")
        items.append(_Item(
            order=p.external_order_id or p.external_sub_order_id or str(p.id),
            platform=_platform(p.platform), order_completed=order_completed, status=status,
            commission=Decimal(commission), sales=Decimal(p.purchase_value or ZERO),
            has_sales=p.purchase_value is not None, refunded=(p.refund_amount or ZERO) > 0,
            completed_at=p.completed_at,
            product_key=key, product_id=p.product_id, name=p.product_name or "Product"))
    return items


def _ledger_items(db: Session, user: User, product_id: uuid.UUID | None) -> list[_Item]:
    """Credited entries with no report row behind them: completed items at
    their stored gross; one a reversal entry undoes is a returned item."""
    backed = select(AffiliatePostback.reconciled_commission_id).where(
        AffiliatePostback.reconciled_commission_id.is_not(None))
    reversed_ids = set(db.scalars(select(Commission.reverses_commission_id).where(
        Commission.reviewer_id == user.id, Commission.reverses_commission_id.is_not(None))))
    query = (select(Commission, Review.product_id)
             .outerjoin(Review, Review.id == Commission.review_id)
             .where(Commission.reviewer_id == user.id, Commission.is_test.is_(False),
                    Commission.reverses_commission_id.is_(None),
                    Commission.id.not_in(backed)))
    if product_id is not None:
        query = query.where(Review.product_id == product_id)
    return [_Item(
        order=f"ledger:{c.id}", platform=_platform(c.platform), order_completed=True,
        status=(AffiliateTxStatus.returned if c.id in reversed_ids
                else AffiliateTxStatus.completed),
        commission=Decimal(c.gross_amount), sales=ZERO, has_sales=False, refunded=False,
        # When the sale was recorded: the entry has no completion time of its own.
        completed_at=c.created_at,
        product_key=f"product:{pid}" if pid else f"ledger:{c.id}", product_id=pid,
        name="Product") for c, pid in db.execute(query).all()]


def breakdown(db: Session, user: User, *, review_ids: list[uuid.UUID] | None = None,
              product_id: uuid.UUID | None = None) -> CommissionBreakdown:
    """The sheet for `user`: all of their credited sales, or one product's."""
    if review_ids is None:
        review_ids = list(db.scalars(select(Review.id).where(Review.author_id == user.id)))
    items = _report_items(db, user, review_ids, product_id) + _ledger_items(db, user, product_id)
    out = CommissionBreakdown()

    counted = [i for i in items if i.order_completed]
    gross = sum((i.commission for i in counted), ZERO)
    reversed_ = sum((i.commission for i in counted
                     if i.status in (AffiliateTxStatus.cancelled, AffiliateTxStatus.returned)),
                    ZERO)
    out.gross_sales = _cents(sum((i.sales for i in counted), ZERO))
    out.orders = len({(i.platform, i.order) for i in counted})
    out.items = len(counted)
    with_sales = [i for i in counted if i.has_sales]
    out.sales_orders = len({(i.platform, i.order) for i in with_sales})
    out.sales_items = len(with_sales)
    out.gross_commission = _cents(gross)
    out.reversals = _cents(reversed_)
    out.net_commission = out.gross_commission - out.reversals
    out.cancelled_items = sum(1 for i in items
                              if not i.order_completed and i.status is AffiliateTxStatus.cancelled)
    out.refunded_items = sum(1 for i in items if i.refunded)
    stamps = [i.completed_at for i in counted if i.completed_at]
    out.first_completed = min(stamps, default=None)
    out.last_completed = max(stamps, default=None)

    split = split_commission(max(out.net_commission, ZERO))
    out.you, out.honesty_fund, out.bluntly = (
        split["reviewer_share"], split["honesty_fund_share"], split["platform_share"])

    credited = (select(func.coalesce(func.sum(Commission.reviewer_share), 0))
                .where(Commission.reviewer_id == user.id, Commission.is_test.is_(False)))
    if product_id is not None:
        credited = credited.join(Review, Review.id == Commission.review_id).where(
            Review.product_id == product_id)
    out.credited = _cents(db.scalar(credited) or ZERO)

    pending = [i for i in items if i.status is AffiliateTxStatus.pending]
    out.pending_commission = _cents(sum((i.commission for i in pending), ZERO))
    out.pending_orders = len({(i.platform, i.order) for i in pending})

    platforms = list(MARKETPLACES) + sorted({i.platform for i in counted} - set(MARKETPLACES))
    out.marketplaces = [MarketplaceTotal(
        platform=name,
        gross_commission=_cents(sum((i.commission for i in counted if i.platform == name), ZERO)),
        orders=len({i.order for i in counted if i.platform == name})) for name in platforms]

    groups: dict[str, list[_Item]] = {}
    for i in counted:
        groups.setdefault(i.product_key, []).append(i)
    names = dict(db.execute(select(Product.id, Product.canonical_name).where(
        Product.id.in_({i.product_id for i in counted if i.product_id})))
        .all()) if any(i.product_id for i in counted) else {}
    products = []
    for rows in groups.values():
        net = sum((i.commission for i in rows if i.status is AffiliateTxStatus.completed), ZERO)
        pid = rows[0].product_id
        products.append(ProductTotal(
            product_id=pid, name=names.get(pid) or rows[0].name, net_commission=_cents(net),
            orders=len({(i.platform, i.order) for i in rows}),
            sales=(_cents(sum((i.sales for i in rows), ZERO))
                   if any(i.has_sales for i in rows) else None)))
    out.products = sorted(products, key=lambda p: (-p.net_commission, -(p.sales or ZERO),
                                                   p.name.lower()))
    return out

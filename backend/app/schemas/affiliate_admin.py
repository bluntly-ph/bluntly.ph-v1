"""The admin Affiliate screen (meeting 2026-10-02): transactions, months, imports."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.qa import QAAuthor


class AffiliateTransactionOut(BaseModel):
    id: uuid.UUID
    platform: str
    order_ref: str | None = None
    #: pending | completed | cancelled | returned
    status: str
    #: not_earned | earned | paid | reversed
    settlement: str
    commission: Decimal | None = None
    order_amount: Decimal | None = None
    product_name: str | None = None
    seller_name: str | None = None
    review_id: uuid.UUID | None = None
    review_title: str | None = None
    #: A return that could not be clawed back (already paid out): Bluntly bears it.
    unrecovered: Decimal | None = None
    import_id: str | None = None
    recorded_at: datetime
    #: The latest of imported / completed / returned (the table's "Updated").
    updated_at: datetime | None = None
    #: The review's author the sale is attributed to; None when unattributed.
    reviewer: QAAuthor | None = None


class AffiliateTransactionPageOut(BaseModel):
    rows: list[AffiliateTransactionOut]
    total: int
    #: By lifecycle status, before the status filter, for the filter chips.
    counts: dict[str, int]
    #: The Filter menu's chip counts (Figma 8019:12742): platform, status,
    #: settlement, attribution (attributed / unattributed) and updated
    #: (7d / 30d / year), under the search but before any filter.
    facets: dict[str, dict[str, int]] = {}


class AffiliateMonthOut(BaseModel):
    platform: str
    cycle_month: date
    commissions: int
    earned: Decimal
    reversed: Decimal
    net: Decimal
    remitted: Decimal | None = None
    remitted_on: date | None = None
    status: str


class AffiliateImportOut(BaseModel):
    id: str
    imported_at: datetime
    imported_by: str | None = None
    filename: str | None = None
    #: "lifecycle" (the provider export path) | "commission" (the older CSV path)
    kind: str
    format: str | None = None
    total_rows: int
    recognised: int
    reversed: int
    unattributed: int
    held_pending_routing: int
    recognised_amount: Decimal | None = None
    reversed_amount: Decimal | None = None
    unrecovered_amount: Decimal | None = None
    import_id: str | None = None


class AffiliateImportDetailOut(BaseModel):
    summary: AffiliateImportOut
    lifecycle: dict[str, int]
    #: The rows this file last wrote (up to 200).
    transactions: list[AffiliateTransactionOut]

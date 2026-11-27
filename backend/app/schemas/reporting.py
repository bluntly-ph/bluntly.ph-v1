"""Report payloads (the four system reports).

Money fields are `Decimal` and serialise as strings ("1234.50"): a report is a
financial document and a float anywhere between the ledger and the reader is a
rounding error waiting for a large enough number.

Every schema here is an allow-list. A row is built field by field in the
service; nothing is `from_attributes` over an ORM object, so a column added to
a table later cannot reach a report (or its CSV) by accident.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ReportPeriod(BaseModel):
    kind: str
    label: str
    start: date
    end: date
    timezone: str = "Asia/Manila"
    #: Commissions belong to a cycle month; these are the months included.
    cycle_months: list[str] = Field(default_factory=list)


class ReportMeta(BaseModel):
    title: str
    period: ReportPeriod
    generated_at: datetime
    currency: str = "PHP"
    notes: list[str] = Field(default_factory=list)


class ReportPage(BaseModel):
    """Paging for a report's detail table. Totals always cover the whole period."""

    total: int
    limit: int
    offset: int


# --------------------------------------------------------------------- 4. reviewer

class StatementReviewer(BaseModel):
    id: uuid.UUID
    username: str | None = None
    display_name: str | None = None


class StatementSummary(BaseModel):
    lifetime_earned: Decimal
    earned_in_period: Decimal
    #: Credited but the marketplace has not paid Bluntly yet (§15).
    clearing: Decimal
    #: Cleared and not yet withdrawn: what a cashout may draw on (§19).
    withdrawable: Decimal
    paid_lifetime: Decimal
    paid_in_period: Decimal
    #: Requested and reserved, not yet paid (scheduled or processing).
    in_flight: Decimal
    wallet_balance: Decimal
    minimum_cashout: Decimal
    can_cash_out: bool


class StatementReviewRow(BaseModel):
    review_id: uuid.UUID | None = None
    review_ref: str | None = None
    title: str | None = None
    product: str | None = None
    verdict: str | None = None
    star_rating: Decimal | None = None
    earning_status: str | None = None
    marketplaces: list[str] = Field(default_factory=list)
    sales: int
    #: The marketplace commission these sales carried (gross, before the split).
    commission_gross: Decimal
    reviewer_earning: Decimal
    cleared: Decimal
    clearing: Decimal
    first_recognised: datetime | None = None
    last_recognised: datetime | None = None


class StatementEntry(BaseModel):
    commission_id: str | None = None
    recognised_at: datetime
    cycle_month: date
    review_ref: str | None = None
    review_title: str | None = None
    product: str | None = None
    marketplace: str | None = None
    order_status: str | None = None
    commission_gross: Decimal
    reviewer_earning: Decimal
    #: clearing | cleared | returned | reversal | qa_test
    status: str
    cleared_at: datetime | None = None


class StatementFundEntry(BaseModel):
    distribution_id: str | None = None
    cycle_month: date
    review_ref: str | None = None
    amount: Decimal


class StatementPayout(BaseModel):
    payout_id: str | None = None
    requested_at: datetime
    amount: Decimal
    method: str
    #: Masked: j***@gmail.com. Never the full address.
    destination: str | None = None
    batch_id: str | None = None
    reference: str | None = None
    status: str
    processed_at: datetime | None = None


class EarningsStatementOut(BaseModel):
    meta: ReportMeta
    reviewer: StatementReviewer
    summary: StatementSummary
    reviews: list[StatementReviewRow] = Field(default_factory=list)
    entries: list[StatementEntry] = Field(default_factory=list)
    entries_truncated: bool = False
    fund_distributions: list[StatementFundEntry] = Field(default_factory=list)
    payouts: list[StatementPayout] = Field(default_factory=list)


# --------------------------------------------------------------------- 3. seller

class RatingDimension(BaseModel):
    key: str
    label: str
    #: "graded" (1-5 / 0-5) or "yes_no".
    kind: str
    #: Median — the approved seller aggregate (Business Rules §10). Graded only.
    median: float | None = None
    #: Arithmetic mean, for reference only; the approved figure is the median.
    mean: float | None = None
    #: Share of "yes" answers, 0..1. Yes/no dimensions only.
    rate: float | None = None
    answered: int = 0


class SellerRatingSummaryBlock(BaseModel):
    review_count: int
    overall_median: float | None = None
    overall_mean: float | None = None
    #: Share of reviewers who said they would recommend the store (a stored
    #: yes/no answer, `seller_reviews.would_recommend`), 0..1.
    recommendation_rate: float | None = None
    distribution: dict[str, int] = Field(default_factory=dict)
    dimensions: list[RatingDimension] = Field(default_factory=list)
    responded: int = 0


class SellerRatingRow(BaseModel):
    seller_review_id: uuid.UUID
    created_at: datetime
    reviewer: str | None = None
    title: str | None = None
    overall_rating: Decimal
    customer_service: int
    packaging_quality: int
    accuracy: bool
    order_completeness: bool
    would_recommend: bool
    has_store_response: bool


class SellerRatingStore(BaseModel):
    id: uuid.UUID
    display_name: str
    platform: str
    claim_status: str


class SellerRatingSummaryOut(BaseModel):
    meta: ReportMeta
    seller: SellerRatingStore
    period_summary: SellerRatingSummaryBlock
    all_time_summary: SellerRatingSummaryBlock
    rows: list[SellerRatingRow] = Field(default_factory=list)
    rows_truncated: bool = False


# --------------------------------------------------------------------- 2. commissions

class PlatformTotals(BaseModel):
    marketplace: str
    commissions: int
    gross: Decimal
    platform_share: Decimal
    reviewer_share: Decimal
    honesty_fund_share: Decimal
    cleared_gross: Decimal
    clearing_gross: Decimal


class CommissionTotals(BaseModel):
    commissions: int
    reversals: int
    qa_test_entries: int
    gross: Decimal
    platform_share: Decimal
    reviewer_share: Decimal
    honesty_fund_share: Decimal
    cleared_gross: Decimal
    clearing_gross: Decimal
    by_marketplace: list[PlatformTotals] = Field(default_factory=list)


class RemittanceRow(BaseModel):
    marketplace: str
    cycle_month: date
    #: Gross the imported reports attributed to this platform and cycle.
    attributed_gross: Decimal
    #: What the marketplace actually paid Bluntly, if recorded.
    amount_received: Decimal | None = None
    difference: Decimal | None = None
    received_on: date | None = None
    reference: str | None = None
    #: reconciled | awaiting_remittance
    status: str


class CommissionRow(BaseModel):
    commission_id: str | None = None
    import_source: str | None = None
    row_reference: str | None = None
    cycle_month: date
    recognised_at: datetime
    marketplace: str | None = None
    sub_id: str | None = None
    review_ref: str | None = None
    review_title: str | None = None
    product: str | None = None
    reviewer: str | None = None
    verdict: str | None = None
    star_rating: Decimal | None = None
    order_status: str | None = None
    imported_commission: Decimal
    #: The row's gross once its platform-cycle remittance is recorded; else null.
    reconciled_amount: Decimal | None = None
    #: cleared | awaiting_remittance | reversal | qa_test
    reconciliation_status: str
    reconciled_at: datetime | None = None
    #: reviewer | honesty_fund — where the reviewer's 30% went for this sale.
    allocation: str
    platform_share: Decimal
    reviewer_share: Decimal
    honesty_fund_share: Decimal


class ReviewerPayoutRow(BaseModel):
    reviewer_id: uuid.UUID
    reviewer: str | None = None
    wallet_balance: Decimal
    clearing: Decimal
    withdrawable: Decimal
    threshold: Decimal
    eligible_for_cashout: bool
    payout_account_on_file: bool
    #: Scheduled or processing: requested, reserved, not paid yet.
    requested_amount: Decimal
    paid_in_period: Decimal
    latest_payout_status: str | None = None
    latest_payout_batch: str | None = None
    latest_payout_at: datetime | None = None


class PeriodPayoutRow(BaseModel):
    payout_id: str | None = None
    reviewer: str | None = None
    amount: Decimal
    method: str
    batch_id: str | None = None
    reference: str | None = None
    status: str
    requested_at: datetime
    processed_at: datetime | None = None


class CommissionPayoutReportOut(BaseModel):
    meta: ReportMeta
    totals: CommissionTotals
    remittances: list[RemittanceRow] = Field(default_factory=list)
    commissions: list[CommissionRow] = Field(default_factory=list)
    page: ReportPage
    payout_summary: list[ReviewerPayoutRow] = Field(default_factory=list)
    payouts: list[PeriodPayoutRow] = Field(default_factory=list)
    threshold: Decimal
    provider: dict = Field(default_factory=dict)


# --------------------------------------------------------------------- 1. honesty fund

class FundCycleRow(BaseModel):
    cycle_month: date
    commissions: int
    #: Honesty Fund shares recorded in the ledger for this cycle.
    fund_inflow: Decimal
    #: The part whose marketplace remittance has been recorded.
    fund_inflow_cleared: Decimal
    #: Paid out of the pool for this cycle (actual distribution rows).
    distributed: Decimal
    #: distributed | not_distributed
    distribution_status: str


class FundReviewRow(BaseModel):
    review_id: uuid.UUID
    review_ref: str | None = None
    title: str
    product: str | None = None
    reviewer: str | None = None
    verdict: str
    star_rating: Decimal
    #: When the review was routed to the fund (approval or track flip), if logged.
    routed_at: datetime | None = None
    routed_in_period: bool
    earning_status: str
    #: eligible | excluded
    eligibility: str
    exclusion_reason: str | None = None
    photo_provided: bool
    #: §11-weighted helpful votes feeding the Honesty Score.
    weighted_helpful_votes: Decimal
    #: Distinct-voter evidence (ADR-016), in people.
    voter_evidence: float
    evidence_floor: float
    meets_evidence_floor: bool
    price_paid: Decimal | None = None
    honesty_score: Decimal
    #: The review's own sales in the period: their gross commission.
    commission_base: Decimal
    #: Honesty Fund shares those sales put into the pool.
    fund_attributable: Decimal
    #: Always null until the owner approves a formula (§14).
    computed_share: Decimal | None = None
    computed_share_status: str
    distributed_amount: Decimal
    distribution_status: str


class FundFormulaStatus(BaseModel):
    defined: bool
    distribution_enabled: bool
    holding_period_defined: bool
    note: str


class HonestyFundReportOut(BaseModel):
    meta: ReportMeta
    formula: FundFormulaStatus
    fund_total: Decimal
    fund_total_cleared: Decimal
    distributed_total: Decimal
    cycles: list[FundCycleRow] = Field(default_factory=list)
    reviews: list[FundReviewRow] = Field(default_factory=list)
    eligible_count: int
    excluded_count: int
    #: "It depends" at exactly 2.5 stars awaiting a Super Admin's routing
    #: (owner decision A): counted and left out rather than guessed.
    pending_routing_count: int


# --------------------------------------------------------------------- 5. financial

class FinancialShare(BaseModel):
    """One side of the 40/30/30 split, as the ledger stored it."""

    key: str  # "bluntly" | "reviewers" | "honesty_fund"
    label: str
    amount: Decimal
    #: Its part of net commission, in percent; null when net is zero or less.
    rate: float | None = None


class FinancialMarketplaceRow(BaseModel):
    marketplace: str
    #: Commissions recognised for the period plus affiliate orders recorded in
    #: the period that earned none (pending, cancelled, unattributed).
    orders: int
    #: Commission entries recognised for the period's cycle months.
    commissions: int
    earned: Decimal


class FinancialRevenue(BaseModel):
    """Recognised for the period's cycle months; QA sandbox test money excluded."""

    earned: Decimal
    reversed: Decimal
    #: The part of `reversed` already paid out to the reviewer, which Bluntly
    #: bears. Shown for reconciliation; it is not deducted from net again.
    absorbed: Decimal
    net: Decimal
    shares: list[FinancialShare] = Field(default_factory=list)
    by_marketplace: list[FinancialMarketplaceRow] = Field(default_factory=list)
    orders_total: int = 0
    commissions_total: int = 0


class FinancialMoneyInRow(BaseModel):
    marketplace: str
    cycle_month: date
    #: What the imports attributed to that marketplace and cycle (net of returns).
    expected: Decimal
    #: Received within the period; null when it was not.
    received: Decimal | None = None
    received_on: date | None = None
    shortfall: Decimal | None = None
    #: "cleared" (remittance recorded by the period's end) | "clearing"
    status: str


class FinancialMoneyIn(BaseModel):
    rows: list[FinancialMoneyInRow] = Field(default_factory=list)
    received_total: Decimal
    shortfall_total: Decimal


class FinancialCountAmount(BaseModel):
    count: int
    amount: Decimal


class FinancialFundCredit(BaseModel):
    """An Honesty Fund distribution: credited to members' wallets."""

    cycle_month: date
    credited_on: date
    count: int
    amount: Decimal


class FinancialMoneyOut(BaseModel):
    #: Payouts marked sent in the period: the money that left Bluntly.
    sent: FinancialCountAmount
    #: Requested by the period's end and still waiting to be sent.
    to_send: FinancialCountAmount
    failed: FinancialCountAmount
    cancelled: FinancialCountAmount
    honesty_fund: list[FinancialFundCredit] = Field(default_factory=list)
    paid_out_total: Decimal
    #: Payouts marked sent through the PayPal SANDBOX in the period: no real
    #: money moved (QA test money), so they are left out of `sent` and
    #: `paid_out_total` and shown here instead.
    sandbox_excluded: FinancialCountAmount | None = None


class FinancialLiabilities(BaseModel):
    """As of the moment the report was generated (balances have no history)."""

    as_of: datetime
    #: Cleared money in members' wallets they have not asked for yet.
    cleared_in_wallets: Decimal
    payouts_to_send: Decimal
    #: Reviewer shares credited but awaiting the marketplace's remittance.
    still_clearing: Decimal
    #: Completed sales whose sub-ID matches no review: nobody to pay.
    unattributed: Decimal
    unattributed_count: int


class FinancialKpis(BaseModel):
    net_commission: Decimal
    money_in: Decimal
    money_out: Decimal
    still_owed: Decimal


class FinancialReportOut(BaseModel):
    meta: ReportMeta
    #: "1–30 September 2026"
    span: str
    #: "1–30 Sep 2026"
    span_short: str
    kpis: FinancialKpis
    revenue: FinancialRevenue
    money_in: FinancialMoneyIn
    money_out: FinancialMoneyOut
    liabilities: FinancialLiabilities


class FinancialReportEntryOut(BaseModel):
    """One generated PDF in the Reports table."""

    id: str
    title: str
    period_label: str
    period_kind: str
    span_short: str
    sections: list[str]
    pages: int
    generated_at: datetime
    generated_by: str | None = None
    download_path: str


class FinancialGenerateIn(BaseModel):
    """The Generate report modal: a period and the sections to include."""

    kind: str = Field(pattern="^(month|quarter|year|custom)$")
    year: int | None = None
    month: int | None = Field(default=None, ge=1, le=12)
    quarter: int | None = Field(default=None, ge=1, le=4)
    start_date: date | None = None
    end_date: date | None = None
    sections: list[str] = Field(min_length=1, max_length=4)

"""Report 4 — the Reviewer Earnings Statement.

One reviewer's own money: what each review earned, what has cleared and what
is still clearing, what they asked to withdraw and what was paid. Built for the
reviewer themself; staff read the same statement through the finance guard.

SOURCES (all ledger rows, nothing estimated):
    commissions                  every recognised sale (and its reversal), with
                                 the reviewer's share fixed when it was imported
    honesty_fund_distributions   money paid to the reviewer out of the fund
    payouts                      cashout requests and their outcome
    users.wallet_balance         the running balance those three maintain

DEFINITIONS:
    lifetime_earned    SUM(commissions.reviewer_share) + SUM(fund payouts), all
                       time, net of reversals (a return writes a negative row)
    earned_in_period   the same over the period's cycle months
    clearing           payout_service.uncleared_share — credited, but the
                       marketplace has not paid Bluntly for that cycle yet
    withdrawable       payout_service.withdrawable — the cashout rule itself
    paid               payouts in `paid`, lifetime and by paid date in period
    in_flight          payouts `scheduled` or `processing`

Period membership: commissions and fund payouts by cycle month; payouts by the
Manila date they were requested (and `paid_in_period` by the date paid).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commission import Commission
from app.models.enums import PayoutStatus
from app.models.honesty_fund import HonestyFundDistribution
from app.models.payout import Payout
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.schemas.reporting import (
    EarningsStatementOut,
    ReportMeta,
    ReportPeriod,
    StatementEntry,
    StatementFundEntry,
    StatementPayout,
    StatementReviewer,
    StatementReviewRow,
    StatementSummary,
)
from app.services import payout_service
from app.services.reporting.common import (
    ZERO,
    Column,
    Table,
    mask_destination,
    money,
)
from app.services.reporting.periods import Period

TITLE = "Reviewer Earnings Statement"
#: Line items returned in one statement. A reviewer's month is far below this;
#: the cap exists so a year-long statement of a very busy account stays bounded.
MAX_ENTRIES = 2000

_METHOD_LABELS = {"manual": "Bank transfer (manual)", "paypal_sandbox": "PayPal (sandbox)",
                  "paypal_live": "PayPal"}


def _entry_status(c: Commission, reversed_ids: set) -> str:
    if c.is_test:
        return "qa_test"
    if c.reverses_commission_id is not None:
        return "reversal"
    if c.id in reversed_ids:
        return "returned"
    return "cleared" if c.cleared_at is not None else "clearing"


def _in_cycles(period: Period):
    return and_(Commission.cycle_month >= period.first_cycle,
                Commission.cycle_month <= period.last_cycle)


def build(db: Session, reviewer: User, period: Period, *,
          now: datetime | None = None) -> EarningsStatementOut:
    now = now or datetime.now(UTC)
    uid = reviewer.id

    # --- summary -----------------------------------------------------------
    lifetime_commissions = money(db.scalar(
        select(func.coalesce(func.sum(Commission.reviewer_share), 0))
        .where(Commission.reviewer_id == uid)))
    lifetime_fund = money(db.scalar(
        select(func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
        .where(HonestyFundDistribution.reviewer_id == uid)))
    period_commissions = money(db.scalar(
        select(func.coalesce(func.sum(Commission.reviewer_share), 0))
        .where(Commission.reviewer_id == uid, _in_cycles(period))))
    period_fund = money(db.scalar(
        select(func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
        .where(HonestyFundDistribution.reviewer_id == uid,
               HonestyFundDistribution.cycle_month >= period.first_cycle,
               HonestyFundDistribution.cycle_month <= period.last_cycle)))

    payout_totals = dict(db.execute(
        select(Payout.status, func.coalesce(func.sum(Payout.amount), 0))
        .where(Payout.user_id == uid).group_by(Payout.status)).all())
    paid_in_period = money(db.scalar(
        select(func.coalesce(func.sum(Payout.amount), 0))
        .where(Payout.user_id == uid, Payout.status == PayoutStatus.paid,
               Payout.paid_at >= period.starts_at, Payout.paid_at < period.ends_before)))

    clearing = payout_service.uncleared_share(db, uid)
    withdrawable = payout_service.withdrawable_from(reviewer.wallet_balance, clearing)
    minimum = money(settings.payout_min_php)

    summary = StatementSummary(
        lifetime_earned=lifetime_commissions + lifetime_fund,
        earned_in_period=period_commissions + period_fund,
        clearing=clearing,
        withdrawable=withdrawable,
        paid_lifetime=money(payout_totals.get(PayoutStatus.paid, 0)),
        paid_in_period=paid_in_period,
        in_flight=money(payout_totals.get(PayoutStatus.scheduled, 0))
        + money(payout_totals.get(PayoutStatus.processing, 0)),
        wallet_balance=money(reviewer.wallet_balance),
        minimum_cashout=minimum,
        can_cash_out=(withdrawable >= minimum and not reviewer.is_claimed_seller),
    )

    # --- line items (one query, joined) --------------------------------------
    reversed_ids = set(db.scalars(
        select(Commission.reverses_commission_id)
        .where(Commission.reviewer_id == uid, Commission.reverses_commission_id.is_not(None))))
    rows = db.execute(
        select(Commission, Review.review_id, Review.title, Review.verdict, Review.star_rating,
               Review.earn_eligible_status, Product.canonical_name)
        .outerjoin(Review, Review.id == Commission.review_id)
        .outerjoin(Product, Product.id == Review.product_id)
        .where(Commission.reviewer_id == uid, _in_cycles(period))
        .order_by(Commission.created_at, Commission.id)
        .limit(MAX_ENTRIES + 1)).all()
    truncated = len(rows) > MAX_ENTRIES
    rows = rows[:MAX_ENTRIES]

    entries: list[StatementEntry] = []
    per_review: dict = defaultdict(lambda: {
        "sales": 0, "gross": ZERO, "earned": ZERO, "cleared": ZERO, "clearing": ZERO,
        "platforms": set(), "first": None, "last": None})
    review_meta: dict = {}
    for c, review_ref, title, verdict, stars, earn_status, product in rows:
        status = _entry_status(c, reversed_ids)
        platform = c.platform.value if c.platform is not None else None
        entries.append(StatementEntry(
            commission_id=c.commission_id, recognised_at=c.created_at,
            cycle_month=c.cycle_month, review_ref=review_ref, review_title=title,
            product=product, marketplace=platform, order_status=c.order_status,
            commission_gross=money(c.gross_amount), reviewer_earning=money(c.reviewer_share),
            status=status, cleared_at=c.cleared_at))
        key = c.review_id
        agg = per_review[key]
        if c.reverses_commission_id is None:
            agg["sales"] += 1
        agg["gross"] += money(c.gross_amount)
        agg["earned"] += money(c.reviewer_share)
        if c.cleared_at is not None or c.is_test:
            agg["cleared"] += money(c.reviewer_share)
        else:
            agg["clearing"] += money(c.reviewer_share)
        if platform:
            agg["platforms"].add(platform)
        agg["first"] = min(filter(None, [agg["first"], c.created_at]))
        agg["last"] = max(filter(None, [agg["last"], c.created_at]))
        review_meta[key] = (review_ref, title, verdict, stars, earn_status, product)

    reviews = []
    for key, agg in per_review.items():
        review_ref, title, verdict, stars, earn_status, product = review_meta[key]
        reviews.append(StatementReviewRow(
            review_id=key, review_ref=review_ref, title=title, product=product,
            verdict=getattr(verdict, "value", verdict),
            star_rating=stars, earning_status=getattr(earn_status, "value", earn_status),
            marketplaces=sorted(agg["platforms"]), sales=agg["sales"],
            commission_gross=agg["gross"], reviewer_earning=agg["earned"],
            cleared=agg["cleared"], clearing=agg["clearing"],
            first_recognised=agg["first"], last_recognised=agg["last"]))
    reviews.sort(key=lambda r: (r.reviewer_earning, r.sales), reverse=True)

    # --- Honesty Fund payouts to this reviewer --------------------------------
    fund = db.execute(
        select(HonestyFundDistribution, Review.review_id)
        .outerjoin(Review, Review.id == HonestyFundDistribution.review_id)
        .where(HonestyFundDistribution.reviewer_id == uid,
               HonestyFundDistribution.cycle_month >= period.first_cycle,
               HonestyFundDistribution.cycle_month <= period.last_cycle)
        .order_by(HonestyFundDistribution.cycle_month)).all()
    fund_rows = [StatementFundEntry(distribution_id=d.distribution_id, cycle_month=d.cycle_month,
                                    review_ref=ref, amount=money(d.payout_amount))
                 for d, ref in fund]

    # --- payouts requested in the period --------------------------------------
    destination = mask_destination(reviewer.payout_account)
    payouts = db.scalars(
        select(Payout).where(Payout.user_id == uid, Payout.created_at >= period.starts_at,
                             Payout.created_at < period.ends_before)
        .order_by(Payout.created_at)).all()
    payout_rows = [StatementPayout(
        payout_id=p.payout_id, requested_at=p.created_at, amount=money(p.amount),
        method=_METHOD_LABELS.get(p.method.value, p.method.value),
        destination=destination, batch_id=p.batch_id, reference=p.provider_ref,
        status=p.status.value,
        processed_at=(p.paid_at if p.status == PayoutStatus.paid
                      else p.updated_at if p.status in (PayoutStatus.failed,
                                                        PayoutStatus.cancelled)
                      else None))
        for p in payouts]

    notes = ["Commissions are dated by their cycle month (Manila); a returned sale "
             "appears as a negative reversal line.",
             "Only cleared money can be withdrawn: the marketplace must have paid "
             "Bluntly for that cycle first."]
    if truncated:
        notes.append(f"Line items are limited to the first {MAX_ENTRIES}; totals cover "
                     "the whole period.")

    return EarningsStatementOut(
        meta=ReportMeta(title=TITLE, period=ReportPeriod(**period.as_dict()), generated_at=now,
                        notes=notes),
        reviewer=StatementReviewer(id=uid, username=reviewer.username,
                                   display_name=reviewer.display_name),
        summary=summary, reviews=reviews, entries=entries, entries_truncated=truncated,
        fund_distributions=fund_rows, payouts=payout_rows)


# ------------------------------------------------------------------ CSV tables

def csv_tables(report: EarningsStatementOut) -> dict[str, Table]:
    return {
        "entries": Table("entries", [
            Column("recognised_at", "Recognised at", "datetime"),
            Column("cycle_month", "Cycle month", "date"),
            Column("commission_id", "Commission ID"),
            Column("review_ref", "Review ID"),
            Column("review_title", "Review"),
            Column("product", "Product"),
            Column("marketplace", "Marketplace"),
            Column("order_status", "Order status"),
            Column("commission_gross", "Commission (gross)", "money"),
            Column("reviewer_earning", "Your earning", "money"),
            Column("status", "Status"),
            Column("cleared_at", "Cleared at", "datetime"),
        ], [e.model_dump() for e in report.entries]),
        "reviews": Table("reviews", [
            Column("review_ref", "Review ID"),
            Column("title", "Review"),
            Column("product", "Product"),
            Column("verdict", "Verdict"),
            Column("star_rating", "Rating", "number"),
            Column("earning_status", "Earning status"),
            Column("marketplaces_joined", "Marketplaces"),
            Column("sales", "Sales", "number"),
            Column("commission_gross", "Commission (gross)", "money"),
            Column("reviewer_earning", "Your earning", "money"),
            Column("cleared", "Cleared", "money"),
            Column("clearing", "Clearing", "money"),
        ], [{**r.model_dump(), "marketplaces_joined": ", ".join(r.marketplaces)}
            for r in report.reviews]),
        "payouts": Table("payouts", [
            Column("requested_at", "Requested at", "datetime"),
            Column("payout_id", "Payout ID"),
            Column("amount", "Amount", "money"),
            Column("method", "Method"),
            Column("destination", "Destination"),
            Column("batch_id", "Batch"),
            Column("reference", "Reference"),
            Column("status", "Status"),
            Column("processed_at", "Processed at", "datetime"),
        ], [p.model_dump() for p in report.payouts]),
    }


def reviewer_or_404(db: Session, user_id: uuid.UUID) -> User:
    from app.core.errors import NotFoundError
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Reviewer not found.", code="user_not_found")
    return user

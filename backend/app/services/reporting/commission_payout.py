"""Report 2 — the Commission and Payout Report (staff).

Every marketplace commission recognised for the period's cycle months, how it
was split, whether the marketplace has paid Bluntly for it, and where each
reviewer stands against the ₱300 cashout minimum.

SOURCES:
    commissions               imported Shopee/Lazada report rows, matched to a
                              review by the link's sub-ID (commission_service,
                              affiliate_ingest); shares fixed at import
    referral_links            the sub-ID and marketplace of the matched link
    marketplace_remittances   what each marketplace actually paid per cycle
    payouts                   cashout requests and their outcome
    users.wallet_balance      the balance the above maintain

NO SECOND FORMULA. The 40/30/30 split (and the fund-track redirect of the
reviewer's 30%) was applied by `earnings.split_for_review` when the row was
recognised, and is read here from the row. Withdrawable is
`payout_service.withdrawable_from`, the rule a cashout is checked against.

RECONCILIATION. A remittance is recorded per marketplace per cycle, not per
order, so a commission is "cleared" when its platform-cycle remittance exists
(`cleared_at`), and the remittance table beside it shows the cycle's
attributed gross against the amount actually received, with the difference.

QA sandbox test earnings (`is_test`) are listed and labelled but carry no
platform or fund revenue by construction (ck_commission_test_no_revenue).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import PayoutStatus
from app.models.payout import Payout
from app.models.product import Product
from app.models.review import ReferralLink, Review
from app.models.user import User
from app.schemas.reporting import (
    CommissionPayoutReportOut,
    CommissionRow,
    CommissionTotals,
    PeriodPayoutRow,
    PlatformTotals,
    RemittanceRow,
    ReportMeta,
    ReportPage,
    ReportPeriod,
    ReviewerPayoutRow,
)
from app.services import payout_service
from app.services.reporting.common import ZERO, Column, Table, money
from app.services.reporting.periods import Period

TITLE = "Commission and Payout Report"
DEFAULT_LIMIT = 200
MAX_LIMIT = 5000


def _in_cycles(period: Period):
    return and_(Commission.cycle_month >= period.first_cycle,
                Commission.cycle_month <= period.last_cycle)


def _reconciliation(c: Commission) -> str:
    if c.is_test:
        return "qa_test"
    if c.reverses_commission_id is not None:
        return "reversal"
    return "cleared" if c.cleared_at is not None else "awaiting_remittance"


def _totals(db: Session, period: Period) -> CommissionTotals:
    """All sums in two grouped queries, whatever the page size."""
    cleared = Commission.cleared_at.is_not(None)
    agg = (func.count(Commission.id),
           func.coalesce(func.sum(Commission.gross_amount), 0),
           func.coalesce(func.sum(Commission.platform_share), 0),
           func.coalesce(func.sum(Commission.reviewer_share), 0),
           func.coalesce(func.sum(Commission.honesty_fund_share), 0),
           func.coalesce(func.sum(case((cleared, Commission.gross_amount), else_=0)), 0),
           func.coalesce(func.sum(case((cleared, 0), else_=Commission.gross_amount)), 0))
    by_platform = db.execute(
        select(Commission.platform, *agg).where(_in_cycles(period))
        .group_by(Commission.platform)).all()
    counts = db.execute(
        select(func.count(Commission.id).filter(Commission.reverses_commission_id.is_not(None)),
               func.count(Commission.id).filter(Commission.is_test.is_(True)))
        .where(_in_cycles(period))).one()

    platforms = []
    total = {"n": 0, "gross": ZERO, "platform": ZERO, "reviewer": ZERO, "fund": ZERO,
             "cleared": ZERO, "clearing": ZERO}
    for platform, n, gross, p_share, r_share, f_share, cleared_gross, clearing_gross in by_platform:
        platforms.append(PlatformTotals(
            marketplace=platform.value if platform is not None else "unattributed",
            commissions=n, gross=money(gross), platform_share=money(p_share),
            reviewer_share=money(r_share), honesty_fund_share=money(f_share),
            cleared_gross=money(cleared_gross), clearing_gross=money(clearing_gross)))
        total["n"] += n
        total["gross"] += money(gross)
        total["platform"] += money(p_share)
        total["reviewer"] += money(r_share)
        total["fund"] += money(f_share)
        total["cleared"] += money(cleared_gross)
        total["clearing"] += money(clearing_gross)
    platforms.sort(key=lambda p: p.marketplace)
    return CommissionTotals(
        commissions=total["n"], reversals=counts[0], qa_test_entries=counts[1],
        gross=total["gross"], platform_share=total["platform"],
        reviewer_share=total["reviewer"], honesty_fund_share=total["fund"],
        cleared_gross=total["cleared"], clearing_gross=total["clearing"],
        by_marketplace=platforms)


def _remittances(db: Session, period: Period) -> list[RemittanceRow]:
    attributed = db.execute(
        select(Commission.platform, Commission.cycle_month,
               func.coalesce(func.sum(Commission.gross_amount), 0))
        .where(_in_cycles(period), Commission.platform.is_not(None),
               Commission.is_test.is_(False))
        .group_by(Commission.platform, Commission.cycle_month)).all()
    received = {(r.platform, r.cycle_month): r for r in db.scalars(
        select(MarketplaceRemittance).where(
            MarketplaceRemittance.cycle_month >= period.first_cycle,
            MarketplaceRemittance.cycle_month <= period.last_cycle))}
    keys = {(p, m) for p, m, _ in attributed} | set(received)
    gross_by = {(p, m): money(g) for p, m, g in attributed}
    out = []
    for platform, cycle in sorted(keys, key=lambda k: (k[1], k[0].value)):
        r = received.get((platform, cycle))
        gross = gross_by.get((platform, cycle), ZERO)
        out.append(RemittanceRow(
            marketplace=platform.value, cycle_month=cycle, attributed_gross=gross,
            amount_received=money(r.amount_received) if r else None,
            difference=(money(r.amount_received) - gross) if r else None,
            received_on=r.received_on if r else None, reference=r.reference if r else None,
            status="reconciled" if r else "awaiting_remittance"))
    return out


def _commission_rows(db: Session, period: Period, limit: int, offset: int) -> list[CommissionRow]:
    # The link that attributed the sale: the review's referral link on the same
    # marketplace, newest first. One LATERAL-free correlated scalar per column
    # would be N+1-shaped in the plan; a DISTINCT ON subquery joins once.
    link = (select(ReferralLink.review_id, ReferralLink.platform, ReferralLink.sub_id)
            .distinct(ReferralLink.review_id, ReferralLink.platform)
            .order_by(ReferralLink.review_id, ReferralLink.platform,
                      ReferralLink.created_at.desc())
            .subquery())
    rows = db.execute(
        select(Commission, Review.review_id, Review.title, Review.verdict, Review.star_rating,
               Product.canonical_name, User.username, link.c.sub_id)
        .outerjoin(Review, Review.id == Commission.review_id)
        .outerjoin(Product, Product.id == Review.product_id)
        .outerjoin(User, User.id == Commission.reviewer_id)
        .outerjoin(link, and_(link.c.review_id == Commission.review_id,
                              link.c.platform == Commission.platform))
        .where(_in_cycles(period))
        .order_by(Commission.cycle_month, Commission.created_at, Commission.id)
        .limit(limit).offset(offset)).all()
    out = []
    for c, review_ref, title, verdict, stars, product, username, sub_id in rows:
        status = _reconciliation(c)
        # Where the reviewer's 30% went. A fund-track thread or a claimed seller
        # is imported with reviewer_share_bps = 0 and the share added to the
        # fund's (earnings.split_for_review); a test earning is the reviewer's.
        to_fund = (not c.is_test and c.reviewer_share_bps == 0
                   and c.reverses_commission_id is None)
        out.append(CommissionRow(
            commission_id=c.commission_id, import_source=c.csv_source,
            row_reference=c.row_reference, cycle_month=c.cycle_month,
            recognised_at=c.created_at,
            marketplace=c.platform.value if c.platform is not None else None,
            sub_id=sub_id, review_ref=review_ref, review_title=title, product=product,
            reviewer=f"@{username}" if username else None,
            verdict=getattr(verdict, "value", verdict), star_rating=stars,
            order_status=c.order_status, imported_commission=money(c.gross_amount),
            reconciled_amount=money(c.gross_amount) if status == "cleared" else None,
            reconciliation_status=status, reconciled_at=c.cleared_at,
            allocation="honesty_fund" if to_fund else "reviewer",
            platform_share=money(c.platform_share), reviewer_share=money(c.reviewer_share),
            honesty_fund_share=money(c.honesty_fund_share)))
    return out


def _payout_summary(db: Session, period: Period) -> list[ReviewerPayoutRow]:
    """Reviewers with a commission in the period or a payout still open."""
    in_period = select(Commission.reviewer_id).where(
        _in_cycles(period), Commission.reviewer_id.is_not(None))
    open_payouts = select(Payout.user_id).where(
        Payout.status.in_((PayoutStatus.scheduled, PayoutStatus.processing)))
    ids = set(db.scalars(in_period.distinct())) | set(db.scalars(open_payouts.distinct()))
    if not ids:
        return []
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))}
    uncleared = payout_service.uncleared_shares(db, ids)

    requested = dict(db.execute(
        select(Payout.user_id, func.coalesce(func.sum(Payout.amount), 0))
        .where(Payout.user_id.in_(ids),
               Payout.status.in_((PayoutStatus.scheduled, PayoutStatus.processing)))
        .group_by(Payout.user_id)).all())
    paid = dict(db.execute(
        select(Payout.user_id, func.coalesce(func.sum(Payout.amount), 0))
        .where(Payout.user_id.in_(ids), Payout.status == PayoutStatus.paid,
               Payout.paid_at >= period.starts_at, Payout.paid_at < period.ends_before)
        .group_by(Payout.user_id)).all())
    latest = {p.user_id: p for p in db.scalars(
        select(Payout).where(Payout.user_id.in_(ids))
        .distinct(Payout.user_id).order_by(Payout.user_id, Payout.created_at.desc()))}

    threshold = money(settings.payout_min_php)
    out = []
    for uid in ids:
        user = users.get(uid)
        if user is None:
            continue
        clearing = uncleared.get(uid, ZERO)
        withdrawable = payout_service.withdrawable_from(user.wallet_balance, clearing)
        last = latest.get(uid)
        out.append(ReviewerPayoutRow(
            reviewer_id=uid, reviewer=f"@{user.username}" if user.username else None,
            wallet_balance=money(user.wallet_balance), clearing=clearing,
            withdrawable=withdrawable, threshold=threshold,
            eligible_for_cashout=(withdrawable >= threshold and not user.is_claimed_seller),
            payout_account_on_file=bool(user.payout_account),
            requested_amount=money(requested.get(uid, 0)),
            paid_in_period=money(paid.get(uid, 0)),
            latest_payout_status=last.status.value if last else None,
            latest_payout_batch=last.batch_id if last else None,
            latest_payout_at=last.created_at if last else None))
    out.sort(key=lambda r: (not r.eligible_for_cashout, -r.withdrawable, r.reviewer or ""))
    return out


def _period_payouts(db: Session, period: Period) -> list[PeriodPayoutRow]:
    rows = db.execute(
        select(Payout, User.username).outerjoin(User, User.id == Payout.user_id)
        .where(Payout.created_at >= period.starts_at, Payout.created_at < period.ends_before)
        .order_by(Payout.created_at)).all()
    return [PeriodPayoutRow(
        payout_id=p.payout_id, reviewer=f"@{username}" if username else None,
        amount=money(p.amount), method=p.method.value, batch_id=p.batch_id,
        reference=p.provider_ref, status=p.status.value, requested_at=p.created_at,
        processed_at=p.paid_at) for p, username in rows]


def build(db: Session, period: Period, *, limit: int = DEFAULT_LIMIT, offset: int = 0,
          now: datetime | None = None) -> CommissionPayoutReportOut:
    now = now or datetime.now(UTC)
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    totals = _totals(db, period)
    provider = payout_service.provider_status()
    notes = [
        "Shares are read from each commission as recognised (40% platform / 30% reviewer / "
        "30% Honesty Fund; a fund-track review's reviewer share goes to the fund).",
        "A commission clears when its marketplace's payout for that cycle is recorded; only "
        "cleared money is withdrawable.",
        f"Cashout minimum: PHP {money(settings.payout_min_php)}. No reviewer cooldown.",
    ]
    if period.kind == "range":
        notes.append("Commissions are grouped by cycle month; this range includes every "
                     "cycle month it touches.")
    return CommissionPayoutReportOut(
        meta=ReportMeta(title=TITLE, period=ReportPeriod(**period.as_dict()), generated_at=now,
                        notes=notes),
        totals=totals,
        remittances=_remittances(db, period),
        commissions=_commission_rows(db, period, limit, offset),
        page=ReportPage(total=totals.commissions, limit=limit, offset=offset),
        payout_summary=_payout_summary(db, period),
        payouts=_period_payouts(db, period),
        threshold=money(settings.payout_min_php),
        provider={k: provider[k] for k in ("method", "api_base_is_sandbox",
                                            "api_submission_available")})


def csv_tables(report: CommissionPayoutReportOut) -> dict[str, Table]:
    return {
        "commissions": Table("commissions", [
            Column("commission_id", "Commission ID"),
            Column("cycle_month", "Cycle month", "date"),
            Column("recognised_at", "Recognised at", "datetime"),
            Column("marketplace", "Marketplace"),
            Column("sub_id", "Sub ID"),
            Column("review_ref", "Review ID"),
            Column("review_title", "Review"),
            Column("product", "Product"),
            Column("reviewer", "Reviewer"),
            Column("verdict", "Verdict"),
            Column("star_rating", "Rating", "number"),
            Column("order_status", "Order status"),
            Column("imported_commission", "Imported commission", "money"),
            Column("reconciled_amount", "Reconciled amount", "money"),
            Column("reconciliation_status", "Reconciliation status"),
            Column("reconciled_at", "Reconciled at", "datetime"),
            Column("allocation", "Reviewer share goes to"),
            Column("platform_share", "Platform share", "money"),
            Column("reviewer_share", "Reviewer share", "money"),
            Column("honesty_fund_share", "Honesty Fund share", "money"),
            Column("import_source", "Import file"),
            Column("row_reference", "Import row"),
        ], [r.model_dump() for r in report.commissions]),
        "payout-summary": Table("payout-summary", [
            Column("reviewer", "Reviewer"),
            Column("wallet_balance", "Wallet balance", "money"),
            Column("clearing", "Clearing", "money"),
            Column("withdrawable", "Cleared / withdrawable", "money"),
            Column("threshold", "Threshold", "money"),
            Column("eligible_for_cashout", "Eligible for cashout", "bool"),
            Column("payout_account_on_file", "Payout account on file", "bool"),
            Column("requested_amount", "Requested (in flight)", "money"),
            Column("paid_in_period", "Paid in period", "money"),
            Column("latest_payout_status", "Latest payout status"),
            Column("latest_payout_batch", "Latest payout batch"),
            Column("latest_payout_at", "Latest payout requested", "datetime"),
        ], [r.model_dump() for r in report.payout_summary]),
        "remittances": Table("remittances", [
            Column("marketplace", "Marketplace"),
            Column("cycle_month", "Cycle month", "date"),
            Column("attributed_gross", "Attributed gross", "money"),
            Column("amount_received", "Amount received", "money"),
            Column("difference", "Difference", "money"),
            Column("received_on", "Received on", "date"),
            Column("reference", "Reference"),
            Column("status", "Status"),
        ], [r.model_dump() for r in report.remittances]),
    }

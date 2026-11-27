"""Report 1 — the Honesty Fund Distribution Report (staff).

TWO LAYERS, deliberately:

A. FUND INPUTS — complete. What entered the pool in the period's cycle months
   (the ledger's `honesty_fund_share`, and how much of it has cleared), and
   every review on the fund track with the values a distribution would be
   computed from: its Honesty Score and that score's inputs (§11-weighted
   helpful votes, distinct-voter evidence against the floor, price paid), its
   own sales' commission base, and what those sales put into the pool.

B. COMPUTED DISTRIBUTION — NOT computed. The distribution formula and holding
   period are an open owner decision (Business Rules §14). `computed_share` is
   null on every row with status `pending_formula`, whatever
   `honesty_fund_distribution_enabled` says: that setting switches the existing
   mechanism on for tests, it does not approve a formula. Money that HAS been
   distributed (rows in `honesty_fund_distributions`) is real ledger and is
   shown as such.

ELIGIBILITY is the domain's, not re-derived: a review is on the fund track when
its `earn_eligible_status` is `honesty_fund` (hard pass, or "it depends" at
2 stars or fewer, decided by `earning_track.track_for`), and it is eligible
when `honesty_fund_service.eligible_reviews` says so (public, not removed, not
a claimed seller, not under a concentration hold). Excluded fund-track reviews
are listed with the reason.

"It depends" at exactly 2.5 stars goes to neither track by itself (owner
decision A): once an administrator approves it, it waits for a Super Admin
(`pending_superadmin_routing`) and is counted here as pending routing, never
guessed into the fund. Routed to the Honesty Fund, it is on the fund track like
any other; routed to the platform, it is not.

TOTALS count real, non-test ledger rows only — never a hypothetical commission.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.commission import Commission
from app.models.enums import EarnEligibleStatus, ModerationAction, VerificationStatus
from app.models.honesty_fund import HonestyFundDistribution
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.schemas.reporting import (
    FundCycleRow,
    FundFormulaStatus,
    FundReviewRow,
    HonestyFundReportOut,
    ReportMeta,
    ReportPeriod,
)
from app.services import honesty_fund_service
from app.services.reporting.common import ZERO, Column, Table, money
from app.services.reporting.periods import Period

TITLE = "Honesty Fund Distribution Report"
PENDING_FORMULA = "pending_formula"
FORMULA_NOTE = ("The Honesty Fund distribution formula and holding period are not yet "
                "defined (Business Rules §14). Computed shares are not calculated; every "
                "input a formula would need is listed.")


def _in_cycles(period: Period):
    return and_(Commission.cycle_month >= period.first_cycle,
                Commission.cycle_month <= period.last_cycle)


def _cycles(db: Session, period: Period) -> list[FundCycleRow]:
    cleared = Commission.cleared_at.is_not(None)
    inflow = {m: (n, money(f), money(fc)) for m, n, f, fc in db.execute(
        select(Commission.cycle_month, func.count(Commission.id),
               func.coalesce(func.sum(Commission.honesty_fund_share), 0),
               func.coalesce(func.sum(case((cleared, Commission.honesty_fund_share),
                                           else_=0)), 0))
        .where(_in_cycles(period), Commission.is_test.is_(False))
        .group_by(Commission.cycle_month)).all()}
    distributed = {m: money(t) for m, t in db.execute(
        select(HonestyFundDistribution.cycle_month,
               func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
        .where(HonestyFundDistribution.cycle_month >= period.first_cycle,
               HonestyFundDistribution.cycle_month <= period.last_cycle)
        .group_by(HonestyFundDistribution.cycle_month)).all()}
    out = []
    for month in period.cycle_months:
        n, fund, fund_cleared = inflow.get(month, (0, ZERO, ZERO))
        dist = distributed.get(month)
        out.append(FundCycleRow(
            cycle_month=month, commissions=n, fund_inflow=fund,
            fund_inflow_cleared=fund_cleared, distributed=dist or ZERO,
            distribution_status="distributed" if dist is not None else "not_distributed"))
    return out


def _routed_at(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    """When each review was last routed to the fund, from the audit log."""
    if not ids:
        return {}
    rows = db.execute(
        select(ModerationLog.target_ref, func.max(ModerationLog.created_at))
        .where(ModerationLog.target_ref.in_(ids),
               or_(and_(ModerationLog.action == ModerationAction.approve,
                        ModerationLog.context["routed_to"].astext == "honesty_fund"),
                   and_(ModerationLog.action == ModerationAction.track_flip,
                        ModerationLog.context["to"].astext == "honesty_fund")))
        .group_by(ModerationLog.target_ref)).all()
    return dict(rows)


def pending_routing_count(db: Session) -> int:
    """Threads waiting on a Super Admin's 2.5-star routing decision."""
    return db.scalar(select(func.count(Review.id)).where(
        Review.earn_eligible_status == EarnEligibleStatus.pending_superadmin_routing,
        Review.is_removed.is_(False))) or 0


def build(db: Session, period: Period, *, now: datetime | None = None) -> HonestyFundReportOut:
    now = now or datetime.now(UTC)
    cycles = _cycles(db, period)

    # Every review on the fund track, with its author and product, in one query.
    fund_track = db.execute(
        select(Review, User.username, User.is_claimed_seller, Product.canonical_name)
        .outerjoin(User, User.id == Review.author_id)
        .outerjoin(Product, Product.id == Review.product_id)
        .where(Review.earn_eligible_status == EarnEligibleStatus.honesty_fund)).all()
    eligible_ids = {r.id for r in honesty_fund_service.eligible_reviews(db)}
    held = set()
    if fund_track:
        from app.services.trust_service import held_by_concentration
        held = held_by_concentration(db, {r.author_id for r, *_ in fund_track if r.author_id})

    ids = [r.id for r, *_ in fund_track]
    routed = _routed_at(db, ids)
    # Only reviews that were on the track by the end of the period.
    in_scope = [(r, u, cs, p) for r, u, cs, p in fund_track
                if routed.get(r.id) is None or routed[r.id] < period.ends_before]
    reviews = [r for r, *_ in in_scope]
    inputs = honesty_fund_service.score_inputs(db, reviews, now) if reviews else {}

    scope_ids = [r.id for r in reviews]
    base = {rid: (money(g), money(f)) for rid, g, f in db.execute(
        select(Commission.review_id, func.coalesce(func.sum(Commission.gross_amount), 0),
               func.coalesce(func.sum(Commission.honesty_fund_share), 0))
        .where(Commission.review_id.in_(scope_ids), _in_cycles(period),
               Commission.is_test.is_(False))
        .group_by(Commission.review_id)).all()} if scope_ids else {}
    distributed = {rid: money(t) for rid, t in db.execute(
        select(HonestyFundDistribution.review_id,
               func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
        .where(HonestyFundDistribution.review_id.in_(scope_ids),
               HonestyFundDistribution.cycle_month >= period.first_cycle,
               HonestyFundDistribution.cycle_month <= period.last_cycle)
        .group_by(HonestyFundDistribution.review_id)).all()} if scope_ids else {}

    floor = float(honesty_fund_service.FUND_MIN_REVIEW_EVIDENCE)
    rows: list[FundReviewRow] = []
    for review, username, claimed, product in in_scope:
        reason = None
        if review.id not in eligible_ids:
            if review.published_at is None:
                reason = "not_public"
            elif review.is_removed:
                reason = "removed"
            elif claimed:
                reason = "claimed_seller"
            elif review.author_id in held:
                reason = "concentration_hold"
            else:
                reason = "not_eligible"
        si = inputs.get(review.id)
        gross, fund = base.get(review.id, (ZERO, ZERO))
        dist = distributed.get(review.id)
        routed_at = routed.get(review.id)
        rows.append(FundReviewRow(
            review_id=review.id, review_ref=review.review_id, title=review.title,
            product=product, reviewer=f"@{username}" if username else None,
            verdict=review.verdict.value, star_rating=review.star_rating,
            routed_at=routed_at,
            routed_in_period=bool(routed_at and period.starts_at <= routed_at
                                  < period.ends_before),
            earning_status=review.earn_eligible_status.value,
            eligibility="eligible" if reason is None else "excluded",
            exclusion_reason=reason,
            photo_provided=(review.verification_status == VerificationStatus.verified
                            or bool(review.receipt_key)),
            weighted_helpful_votes=(si.weighted_up_votes if si else ZERO).quantize(
                Decimal("0.0001")),
            voter_evidence=round(si.voter_evidence if si else 0.0, 4),
            evidence_floor=floor,
            meets_evidence_floor=bool(si and si.voter_evidence >= floor),
            price_paid=money(review.price_paid) if review.price_paid is not None else None,
            honesty_score=(si.score if si else ZERO).quantize(Decimal("0.0001")),
            commission_base=gross, fund_attributable=fund,
            computed_share=None, computed_share_status=PENDING_FORMULA,
            distributed_amount=dist or ZERO,
            distribution_status="distributed" if dist is not None else "not_distributed"))
    rows.sort(key=lambda r: (r.eligibility != "eligible", -r.honesty_score, r.title))

    fund_total = sum((c.fund_inflow for c in cycles), ZERO)
    notes = [FORMULA_NOTE,
             "Fund totals are the Honesty Fund shares recorded on real (non-test) commissions "
             "for the period's cycle months; 'cleared' is the part whose marketplace payout "
             "has been received.",
             "\"It depends\" at exactly 2.5 stars awaits routing and is not included."]
    return HonestyFundReportOut(
        meta=ReportMeta(title=TITLE, period=ReportPeriod(**period.as_dict()), generated_at=now,
                        notes=notes),
        formula=FundFormulaStatus(
            defined=False, distribution_enabled=bool(settings.honesty_fund_distribution_enabled),
            holding_period_defined=False, note=FORMULA_NOTE),
        fund_total=fund_total,
        fund_total_cleared=sum((c.fund_inflow_cleared for c in cycles), ZERO),
        distributed_total=sum((c.distributed for c in cycles), ZERO),
        cycles=cycles, reviews=rows,
        eligible_count=sum(1 for r in rows if r.eligibility == "eligible"),
        excluded_count=sum(1 for r in rows if r.eligibility == "excluded"),
        pending_routing_count=pending_routing_count(db))


def csv_tables(report: HonestyFundReportOut) -> dict[str, Table]:
    return {
        "reviews": Table("reviews", [
            Column("review_ref", "Review ID"),
            Column("title", "Review"),
            Column("product", "Product"),
            Column("reviewer", "Reviewer"),
            Column("verdict", "Verdict"),
            Column("star_rating", "Rating", "number"),
            Column("routed_at", "Routed to fund", "datetime"),
            Column("eligibility", "Eligibility"),
            Column("exclusion_reason", "Exclusion reason"),
            Column("photo_provided", "Photo provided", "bool"),
            Column("weighted_helpful_votes", "Weighted helpful votes", "number"),
            Column("voter_evidence", "Voter evidence (people)", "number"),
            Column("evidence_floor", "Evidence floor", "number"),
            Column("meets_evidence_floor", "Meets floor", "bool"),
            Column("price_paid", "Price paid", "money"),
            Column("honesty_score", "Honesty Score", "number"),
            Column("commission_base", "Commission base", "money"),
            Column("fund_attributable", "Fund attributable", "money"),
            Column("computed_share_display", "Computed share"),
            Column("distributed_amount", "Distributed", "money"),
            Column("distribution_status", "Distribution status"),
        ], [{**r.model_dump(), "computed_share_display": "Pending distribution formula"}
            for r in report.reviews]),
        "cycles": Table("cycles", [
            Column("cycle_month", "Cycle month", "date"),
            Column("commissions", "Commissions", "number"),
            Column("fund_inflow", "Fund inflow", "money"),
            Column("fund_inflow_cleared", "Fund inflow cleared", "money"),
            Column("distributed", "Distributed", "money"),
            Column("distribution_status", "Distribution status"),
        ], [c.model_dump() for c in report.cycles]),
    }

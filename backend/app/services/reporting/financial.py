"""Report 5 — the Financial Report (staff).

Figma Screen/Admin/Reports (8028:12886), Overlay/Report/Generate (8028:13346)
and the PDF template pages (8029:12942, 8029:13078); meeting 2026-10-02, 18:06:
"generate a PDF for a chosen month or period with selected sections".

Four sections, every figure read from the ledger the other reports read:

REVENUE & SPLIT    commissions recognised for the period's cycle months (QA
                   sandbox test money excluded: it is not marketplace money).
                   earned = forward entries, reversed = their reversal entries,
                   net = earned - reversed. The Bluntly / Reviewers / Honesty
                   Fund shares are the stored shares summed (no second formula;
                   a fund-track review's reviewer share is already in the fund's).
                   absorbed = what a return could not claw back from a wallet
                   already paid out (`affiliate_postbacks.unrecovered_amount`):
                   part of `reversed`, borne by Bluntly, never deducted twice.
MONEY IN           marketplace remittances received in the period, beside what
                   the imports attributed to that marketplace and cycle; the
                   period's own cycles are listed too, "Clearing" until paid.
MONEY OUT          payouts marked sent in the period (the money that left) —
                   except those sent through the PayPal SANDBOX, which move no
                   real money (QA test money, Vash's sandbox design): they are
                   counted apart as `sandbox_excluded`, never as paid out — and
                   beside them what waits, failed and was cancelled (both went
                   back to wallets). An Honesty Fund distribution is CREDITED TO
                   WALLETS, so it is listed but not added to "paid out": it
                   leaves Bluntly when those wallets are paid, and adding it
                   again would count the same peso twice.
LIABILITIES        as of now — balances have no history to read a past day from,
                   which the modal says ("Figures as of now, Manila time"):
                   cleared money in wallets, payouts to send, reviewer shares
                   still clearing, and completed sales no review can be paid for.

A generated PDF is logged with the report's figures (`platform_settings`, key
`financial_report_log`, newest 24), so "Download" re-renders the same document
rather than today's numbers under an old date. No migration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import AppError, NotFoundError
from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import AffiliateTxStatus, PayoutMethod, PayoutStatus
from app.models.honesty_fund import HonestyFundDistribution
from app.models.payout import Payout
from app.models.postback import AffiliatePostback
from app.models.review import ReferralLink
from app.models.triage import PlatformSetting
from app.models.user import User
from app.schemas.reporting import (
    FinancialCountAmount,
    FinancialFundCredit,
    FinancialKpis,
    FinancialLiabilities,
    FinancialMarketplaceRow,
    FinancialMoneyIn,
    FinancialMoneyInRow,
    FinancialMoneyOut,
    FinancialReportEntryOut,
    FinancialReportOut,
    FinancialRevenue,
    FinancialShare,
    ReportMeta,
    ReportPeriod,
)
from app.services import payout_service
from app.services.reporting.common import ZERO, money
from app.services.reporting.periods import Period

TITLE = "Financial report"

#: The modal's four switches, in the order the PDF prints them.
SECTIONS: tuple[str, ...] = ("revenue", "money_in", "money_out", "liabilities")
SECTION_LABELS = {
    "revenue": "Revenue & split",
    "money_in": "Money in",
    "money_out": "Money out",
    "liabilities": "Liabilities",
}

MARKETPLACE_LABELS = {"shopee": "Shopee", "lazada": "Lazada", "amazon": "Amazon",
                      "other": "Other"}
_MARKETPLACE_ORDER = ("shopee", "lazada", "amazon", "other")

LOG_KEY = "financial_report_log"
LOG_LIMIT = 24

_OPEN = (PayoutStatus.scheduled, PayoutStatus.processing)


# --------------------------------------------------------------------- labels

def _mon(d: date, short: bool) -> str:
    return d.strftime("%b" if short else "%B")


def span(period: Period, *, short: bool = False) -> str:
    """'1–30 September 2026', '1 April – 30 June 2026', '28 Dec 2025 – 3 Jan 2026'."""
    s, e = period.start, period.end
    if (s.year, s.month) == (e.year, e.month):
        return f"{s.day}–{e.day} {_mon(s, short)} {s.year}"
    if s.year == e.year:
        return f"{s.day} {_mon(s, short)} – {e.day} {_mon(e, short)} {s.year}"
    return f"{s.day} {_mon(s, short)} {s.year} – {e.day} {_mon(e, short)} {e.year}"


def title_for(period: Period) -> str:
    """The PDF's big title: 'September 2026', 'Q2 2026', '2026', or the range."""
    if period.kind in ("month", "quarter", "year"):
        return period.label
    return span(period, short=True)


def period_column(period: Period) -> str:
    """The Reports table's Period cell: '1–31 Aug 2026', 'Apr–Jun 2026'."""
    if period.kind in ("quarter", "year"):
        return f"{period.start.strftime('%b')}–{period.end.strftime('%b')} {period.start.year}"
    return span(period, short=True)


def in_label(period: Period) -> str:
    """'in September', 'in Q2 2026', 'in 2026', 'in the period'."""
    if period.kind == "month":
        return f"in {period.start.strftime('%B')}"
    if period.kind in ("quarter", "year"):
        return f"in {period.label}"
    return "in the period"


def marketplace_label(value: str | None) -> str:
    return MARKETPLACE_LABELS.get(value or "other", (value or "Other").title())


def _platform_key(platform) -> str:
    if platform is None:
        return "other"
    return platform.value if hasattr(platform, "value") else str(platform)


def _order(key: str) -> int:
    return _MARKETPLACE_ORDER.index(key) if key in _MARKETPLACE_ORDER else len(_MARKETPLACE_ORDER)


# --------------------------------------------------------------------- figures

def _real_cycles(period: Period):
    """Real (non-test) ledger entries for the period's cycle months."""
    return and_(Commission.cycle_month >= period.first_cycle,
                Commission.cycle_month <= period.last_cycle,
                Commission.is_test.is_(False))


def _revenue(db: Session, period: Period) -> FinancialRevenue:
    forward = Commission.reverses_commission_id.is_(None)
    reversal = Commission.reverses_commission_id.is_not(None)
    rows = db.execute(
        select(Commission.platform,
               func.count(Commission.id).filter(forward),
               func.coalesce(func.sum(Commission.gross_amount).filter(forward), 0),
               func.coalesce(func.sum(Commission.gross_amount).filter(reversal), 0),
               func.coalesce(func.sum(Commission.platform_share), 0),
               func.coalesce(func.sum(Commission.reviewer_share), 0),
               func.coalesce(func.sum(Commission.honesty_fund_share), 0))
        .where(_real_cycles(period))
        .group_by(Commission.platform)).all()

    # Orders that earned nothing (pending, cancelled, unattributed, held): an
    # affiliate transaction with no recognised commission, dated by when
    # Bluntly recorded it. Those that did earn are counted by their commission.
    uncommissioned = {
        _platform_key(p): int(n) for p, n in db.execute(
            select(AffiliatePostback.platform, func.count(AffiliatePostback.id))
            .where(AffiliatePostback.reconciled_commission_id.is_(None),
                   AffiliatePostback.received_at >= period.starts_at,
                   AffiliatePostback.received_at < period.ends_before)
            .group_by(AffiliatePostback.platform)).all()}

    earned = reversed_ = bluntly = reviewers = fund = ZERO
    per: dict[str, dict] = {}
    for platform, n, fwd, rev, p_share, r_share, f_share in rows:
        key = _platform_key(platform)
        slot = per.setdefault(key, {"commissions": 0, "earned": ZERO})
        slot["commissions"] += int(n)
        slot["earned"] += money(fwd)
        earned += money(fwd)
        reversed_ += -money(rev)
        bluntly += money(p_share)
        reviewers += money(r_share)
        fund += money(f_share)
    for key in uncommissioned:
        per.setdefault(key, {"commissions": 0, "earned": ZERO})

    by_marketplace = [
        FinancialMarketplaceRow(
            marketplace=key, orders=slot["commissions"] + uncommissioned.get(key, 0),
            commissions=slot["commissions"], earned=slot["earned"])
        for key, slot in sorted(per.items(), key=lambda kv: _order(kv[0]))
    ]

    absorbed = money(db.scalar(
        select(func.coalesce(func.sum(AffiliatePostback.unrecovered_amount), 0))
        .join(Commission, Commission.id == AffiliatePostback.reconciled_commission_id)
        .where(_real_cycles(period))))

    net = earned - reversed_

    def share(key: str, label: str, amount: Decimal) -> FinancialShare:
        rate = float(amount / net * 100) if net > 0 else None
        return FinancialShare(key=key, label=label, amount=amount, rate=rate)

    return FinancialRevenue(
        earned=earned, reversed=reversed_, absorbed=absorbed, net=net,
        shares=[share("bluntly", "Bluntly", bluntly),
                share("reviewers", "Reviewers", reviewers),
                share("honesty_fund", "Honesty Fund", fund)],
        by_marketplace=by_marketplace,
        orders_total=sum(r.orders for r in by_marketplace),
        commissions_total=sum(r.commissions for r in by_marketplace))


def _money_in(db: Session, period: Period) -> FinancialMoneyIn:
    received_in_period = db.scalars(select(MarketplaceRemittance).where(
        MarketplaceRemittance.received_on >= period.start,
        MarketplaceRemittance.received_on <= period.end)).all()
    keys = {(r.platform, r.cycle_month) for r in received_in_period}
    keys |= {(p, m) for p, m in db.execute(
        select(Commission.platform, Commission.cycle_month)
        .where(_real_cycles(period), Commission.platform.is_not(None))
        .group_by(Commission.platform, Commission.cycle_month)).all()}
    if not keys:
        return FinancialMoneyIn(rows=[], received_total=ZERO, shortfall_total=ZERO)

    cycles = sorted({m for _, m in keys})
    # The same rule as the commission report's remittance table: what the
    # imports attributed to that marketplace and cycle, returns included.
    expected = {(p, m): money(g) for p, m, g in db.execute(
        select(Commission.platform, Commission.cycle_month,
               func.coalesce(func.sum(Commission.gross_amount), 0))
        .where(Commission.is_test.is_(False), Commission.platform.is_not(None),
               Commission.cycle_month.in_(cycles))
        .group_by(Commission.platform, Commission.cycle_month)).all()}
    remitted = {(r.platform, r.cycle_month): r for r in db.scalars(
        select(MarketplaceRemittance).where(MarketplaceRemittance.cycle_month.in_(cycles)))}

    rows: list[FinancialMoneyInRow] = []
    received_total = shortfall_total = ZERO
    for platform, cycle in sorted(keys, key=lambda k: (k[1], _order(_platform_key(k[0])))):
        r = remitted.get((platform, cycle))
        exp = expected.get((platform, cycle), ZERO)
        in_period = r is not None and period.start <= r.received_on <= period.end
        received = money(r.amount_received) if in_period else None
        shortfall = (exp - received) if received is not None and exp > received else None
        if received is not None:
            received_total += received
        if shortfall is not None:
            shortfall_total += shortfall
        rows.append(FinancialMoneyInRow(
            marketplace=_platform_key(platform), cycle_month=cycle, expected=exp,
            received=received, received_on=r.received_on if in_period else None,
            shortfall=shortfall,
            status="cleared" if r is not None and r.received_on <= period.end else "clearing"))
    return FinancialMoneyIn(rows=rows, received_total=received_total,
                            shortfall_total=shortfall_total)


def _count_amount(db: Session, *where) -> FinancialCountAmount:
    n, total = db.execute(
        select(func.count(Payout.id), func.coalesce(func.sum(Payout.amount), 0))
        .where(*where)).one()
    return FinancialCountAmount(count=int(n), amount=money(total))


def _money_out(db: Session, period: Period) -> FinancialMoneyOut:
    lo, hi = period.starts_at, period.ends_before
    paid_in_period = (Payout.status == PayoutStatus.paid,
                      Payout.paid_at >= lo, Payout.paid_at < hi)
    sandbox = Payout.method == PayoutMethod.paypal_sandbox
    sent = _count_amount(db, *paid_in_period, ~sandbox)
    sandbox_excluded = _count_amount(db, *paid_in_period, sandbox)
    to_send = _count_amount(db, Payout.status.in_(_OPEN), Payout.created_at < hi)
    # A failed or cancelled payout is terminal until retried, so the row's last
    # update is when it failed or was cancelled.
    failed = _count_amount(db, Payout.status == PayoutStatus.failed,
                           Payout.updated_at >= lo, Payout.updated_at < hi)
    cancelled = _count_amount(db, Payout.status == PayoutStatus.cancelled,
                              Payout.updated_at >= lo, Payout.updated_at < hi)
    credits = [
        FinancialFundCredit(cycle_month=cycle, credited_on=first.astimezone(MANILA).date(),
                            count=int(n), amount=money(total))
        for cycle, first, n, total in db.execute(
            select(HonestyFundDistribution.cycle_month,
                   func.min(HonestyFundDistribution.created_at),
                   func.count(HonestyFundDistribution.id).filter(
                       HonestyFundDistribution.payout_amount > 0),
                   func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
            .where(HonestyFundDistribution.created_at >= lo,
                   HonestyFundDistribution.created_at < hi)
            .group_by(HonestyFundDistribution.cycle_month)
            .order_by(HonestyFundDistribution.cycle_month)).all()
    ]
    return FinancialMoneyOut(sent=sent, to_send=to_send, failed=failed, cancelled=cancelled,
                             honesty_fund=credits, paid_out_total=sent.amount,
                             sandbox_excluded=sandbox_excluded)


def _liabilities(db: Session, now: datetime) -> FinancialLiabilities:
    wallets = db.execute(
        select(User.id, User.wallet_balance).where(User.wallet_balance > 0)).all()
    uncleared = payout_service.uncleared_shares(db, [uid for uid, _ in wallets])
    cleared = clearing = ZERO
    for uid, balance in wallets:
        balance = money(balance)
        withdrawable = payout_service.withdrawable_from(balance, uncleared.get(uid, ZERO))
        cleared += withdrawable
        # The rest of the wallet is the part still waiting on its remittance.
        clearing += balance - withdrawable
    to_send = money(db.scalar(
        select(func.coalesce(func.sum(Payout.amount), 0)).where(Payout.status.in_(_OPEN))))
    linked = select(ReferralLink.sub_id).where(ReferralLink.sub_id.is_not(None))
    n, unattributed = db.execute(
        select(func.count(AffiliatePostback.id),
               func.coalesce(func.sum(AffiliatePostback.reported_payout), 0))
        .where(AffiliatePostback.canonical_status == AffiliateTxStatus.completed,
               AffiliatePostback.reconciled_commission_id.is_(None),
               or_(AffiliatePostback.review_sub_id.is_(None),
                   AffiliatePostback.review_sub_id.not_in(linked)))).one()
    return FinancialLiabilities(
        as_of=now, cleared_in_wallets=cleared, payouts_to_send=to_send,
        still_clearing=clearing, unattributed=money(unattributed),
        unattributed_count=int(n))


def build(db: Session, period: Period, *, now: datetime | None = None) -> FinancialReportOut:
    now = now or datetime.now(UTC)
    revenue = _revenue(db, period)
    money_in = _money_in(db, period)
    money_out = _money_out(db, period)
    liabilities = _liabilities(db, now)
    notes = [
        "Revenue is recognised by cycle month; QA sandbox test earnings are excluded.",
        "Absorbed is the part of a return already paid out to the reviewer. Bluntly bears "
        "it; it is part of the reversed amount and is not deducted again.",
        "Orders: commissions recognised for the period plus affiliate orders recorded in "
        "the period that earned none (pending, cancelled or unattributed).",
        "Paid out counts payouts marked sent. An Honesty Fund distribution is credited to "
        "wallets and leaves Bluntly when those wallets are paid out, so it is not added again.",
        "Liabilities are as of the moment the report was generated.",
    ]
    if money_out.sandbox_excluded and money_out.sandbox_excluded.count:
        sx = money_out.sandbox_excluded
        notes.append(
            f"{sx.count} payout{'s' if sx.count != 1 else ''} (₱{sx.amount:,.2f}) went through the "
            "PayPal sandbox: no real money moved, so they are not in Paid out.")
    if period.kind == "range":
        notes.append("Commissions are grouped by cycle month; this range includes every "
                     "cycle month it touches.")
    return FinancialReportOut(
        meta=ReportMeta(title=TITLE, period=ReportPeriod(**period.as_dict()),
                        generated_at=now, notes=notes),
        span=span(period), span_short=span(period, short=True),
        kpis=FinancialKpis(net_commission=revenue.net, money_in=money_in.received_total,
                           money_out=money_out.paid_out_total,
                           still_owed=liabilities.cleared_in_wallets),
        revenue=revenue, money_in=money_in, money_out=money_out, liabilities=liabilities)


# --------------------------------------------------------------------- history

def clean_sections(sections: list[str]) -> list[str]:
    """The chosen sections in print order; unknown or empty is a 422."""
    chosen = [s for s in SECTIONS if s in set(sections)]
    unknown = sorted(set(sections) - set(SECTIONS))
    if unknown or not chosen:
        raise AppError("Choose at least one of: " + ", ".join(SECTIONS) + ".",
                       code="report_section_unknown", status_code=422,
                       title="Invalid report request", extra={"sections": list(SECTIONS)})
    return chosen


def period_of(report: FinancialReportOut) -> Period:
    p = report.meta.period
    return Period(start=p.start, end=p.end, kind=p.kind)


def author_name(user: User) -> str:
    if user.display_name:
        return user.display_name
    return f"@{user.username}" if user.username else "Staff"


def _entries(db: Session, *, lock: bool = False) -> tuple[PlatformSetting | None, list[dict]]:
    row = db.get(PlatformSetting, LOG_KEY, with_for_update=lock) if lock else db.get(
        PlatformSetting, LOG_KEY)
    entries = list((row.value or {}).get("entries", [])) if row is not None else []
    return row, entries


def entry_out(entry: dict) -> FinancialReportEntryOut:
    report = FinancialReportOut.model_validate(entry["report"])
    period = period_of(report)
    return FinancialReportEntryOut(
        id=entry["id"], title=f"{TITLE} · {title_for(period)}", period_label=period.label,
        period_kind=period.kind, span_short=period_column(period),
        sections=list(entry["sections"]), pages=int(entry["pages"]),
        generated_at=datetime.fromisoformat(entry["generated_at"]),
        generated_by=entry.get("generated_by"),
        download_path=f"/api/v1/admin/reports/financial/history/{entry['id']}/pdf")


def record(db: Session, report: FinancialReportOut, sections: list[str], pages: int,
           user: User) -> FinancialReportEntryOut:
    """Log a generated PDF with its figures; keeps the newest LOG_LIMIT."""
    row, entries = _entries(db, lock=True)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "sections": sections,
        "pages": pages,
        "generated_at": report.meta.generated_at.isoformat(),
        "generated_by": author_name(user),
        "generated_by_id": str(user.id),
        "report": report.model_dump(mode="json"),
    }
    entries = [entry, *entries][:LOG_LIMIT]
    if row is None:
        db.add(PlatformSetting(key=LOG_KEY, value={"entries": entries}, updated_by=user.id))
    else:
        row.value = {"entries": entries}
        row.updated_by = user.id
        row.updated_at = datetime.now(UTC)
    db.commit()
    return entry_out(entry)


def history(db: Session) -> list[FinancialReportEntryOut]:
    _, entries = _entries(db)
    out = []
    for entry in entries:
        try:
            out.append(entry_out(entry))
        except (KeyError, ValueError):  # pragma: no cover - a hand-edited row
            continue
    return out


def find(db: Session, entry_id: str) -> tuple[dict, FinancialReportOut]:
    _, entries = _entries(db)
    for entry in entries:
        if entry.get("id") == entry_id:
            return entry, FinancialReportOut.model_validate(entry["report"])
    raise NotFoundError("That report is no longer in the list.", code="report_not_found")

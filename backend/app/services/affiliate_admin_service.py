"""The admin Affiliate screen's reads (meeting 2026-10-02, 15:50-16:50): the
transactions imported from the Shopee and Lazada reports, the breakdown per
month, and the history of imports — each one openable to see what that file
did without opening the file.

Nothing new is stored. Transactions are the canonical affiliate store
(`affiliate_postbacks`); the months are the commission ledger and the recorded
remittances; an import is the audit row every import already writes
(`moderation_logs`, action `csv_import`, with its summary), and the rows a
lifecycle import last wrote carry its id (`source_import_id`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import AffiliateTxStatus, ModerationAction, Platform, SettlementStatus
from app.models.moderation import ModerationLog
from app.models.postback import AffiliatePostback
from app.models.review import Review
from app.models.user import User

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_LIMIT = 200


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT)


def _platform(value) -> str | None:
    return value.value if hasattr(value, "value") else value


@dataclass(frozen=True)
class TransactionRow:
    id: uuid.UUID
    platform: str
    order_ref: str | None
    status: str
    settlement: str
    commission: Decimal | None
    order_amount: Decimal | None
    product_name: str | None
    seller_name: str | None
    review_id: uuid.UUID | None
    review_title: str | None
    unrecovered: Decimal | None
    import_id: str | None
    recorded_at: datetime
    #: The latest thing that happened to the order: imported, completed or returned.
    updated_at: datetime | None = None
    #: The review's author, who the sale is attributed to (None: unattributed).
    reviewer: User | None = None


@dataclass
class TransactionPage:
    rows: list[TransactionRow]
    total: int
    counts: dict[str, int] = field(default_factory=dict)
    #: Chip counts for the Filter menu (Figma 8019:12742), each facet counted
    #: under the search but before any filter.
    facets: dict[str, dict[str, int]] = field(default_factory=dict)


_P = AffiliatePostback
SORTS = {
    "newest": (_P.received_at.desc(), _P.id),
    "oldest": (_P.received_at.asc(), _P.id),
    "commission_desc": (_P.reported_payout.desc().nulls_last(), _P.id),
    "commission_asc": (_P.reported_payout.asc().nulls_last(), _P.id),
}
UPDATED_WINDOWS = {"7d": 7, "30d": 30}


def _updated_since(window: str, now: datetime):
    if window == "year":
        return datetime(now.year, 1, 1, tzinfo=UTC)
    return now - timedelta(days=UPDATED_WINDOWS[window])


def transactions(db: Session, *, platform: str | None = None, status: str | None = None,
                 q: str | None = None, limit: int = 50, offset: int = 0,
                 settlement: str | None = None, attribution: str | None = None,
                 updated: str | None = None, sort: str = "newest",
                 now: datetime | None = None) -> TransactionPage:
    now = now or datetime.now(UTC)
    # The search narrows everything, the facet counts included; each filter
    # below narrows only the list.
    where = []
    if q:
        needle = f"%{q.strip()}%"
        where.append(or_(AffiliatePostback.external_order_id.ilike(needle),
                         AffiliatePostback.external_sub_order_id.ilike(needle),
                         AffiliatePostback.product_name.ilike(needle),
                         AffiliatePostback.seller_name.ilike(needle)))
    search = list(where)
    updated_at = func.greatest(AffiliatePostback.received_at, AffiliatePostback.completed_at,
                               AffiliatePostback.returned_at)
    facets: dict[str, dict[str, int]] = {}
    for name, col in (("platform", AffiliatePostback.platform),
                      ("status", AffiliatePostback.canonical_status),
                      ("settlement", AffiliatePostback.settlement_status)):
        facets[name] = {_platform(v): int(n) for v, n in db.execute(
            select(col, func.count(AffiliatePostback.id)).where(*search).group_by(col)).all()}
    attributed = AffiliatePostback.review_id.is_not(None)
    facets["attribution"] = {
        "attributed": int(db.scalar(select(func.count(AffiliatePostback.id))
                                    .where(*search, attributed)) or 0),
        "unattributed": int(db.scalar(select(func.count(AffiliatePostback.id))
                                      .where(*search, ~attributed)) or 0)}
    facets["updated"] = {w: int(db.scalar(select(func.count(AffiliatePostback.id)).where(
        *search, updated_at >= _updated_since(w, now))) or 0) for w in ("7d", "30d", "year")}
    counts = facets["status"]
    if platform:
        where.append(AffiliatePostback.platform == Platform(platform))
    if status:
        where.append(AffiliatePostback.canonical_status == AffiliateTxStatus(status))
    if settlement:
        where.append(AffiliatePostback.settlement_status == SettlementStatus(settlement))
    if attribution:
        where.append(attributed if attribution == "attributed" else ~attributed)
    if updated:
        where.append(updated_at >= _updated_since(updated, now))
    total = int(db.scalar(select(func.count(AffiliatePostback.id)).where(*where)) or 0)
    rows = db.execute(
        select(AffiliatePostback, Review.title, User)
        .outerjoin(Review, Review.id == AffiliatePostback.review_id)
        .outerjoin(User, User.id == Review.author_id)
        .where(*where)
        .order_by(*SORTS.get(sort, SORTS["newest"]))
        .limit(max(1, min(limit, MAX_LIMIT))).offset(max(0, offset))).all()
    return TransactionPage(
        rows=[TransactionRow(
            id=p.id, platform=_platform(p.platform), order_ref=p.external_order_id,
            status=_platform(p.canonical_status), settlement=_platform(p.settlement_status),
            commission=_money(p.reported_payout) if p.reported_payout is not None else None,
            order_amount=_money(p.reported_amount) if p.reported_amount is not None else None,
            product_name=p.product_name, seller_name=p.seller_name, review_id=p.review_id,
            review_title=title,
            unrecovered=_money(p.unrecovered_amount) if p.unrecovered_amount else None,
            import_id=p.source_import_id, recorded_at=p.received_at,
            updated_at=max(t for t in (p.received_at, p.completed_at, p.returned_at) if t),
            reviewer=author)
            for p, title, author in rows],
        total=total, counts={k: counts.get(k, 0) for k in
                             ("pending", "completed", "cancelled", "returned")},
        facets=facets)


@dataclass(frozen=True)
class MonthRow:
    platform: str
    cycle_month: date
    commissions: int
    earned: Decimal
    reversed: Decimal
    net: Decimal
    remitted: Decimal | None
    remitted_on: date | None
    status: str  # "remitted" | "awaiting_remittance"


def months(db: Session, *, platform: str | None = None, limit: int = 24) -> list[MonthRow]:
    """Per marketplace and cycle month: what was recognised, reversed, and paid
    to Bluntly. Real (non-test) money only; newest month first."""
    forward = Commission.reverses_commission_id.is_(None)
    where = [Commission.is_test.is_(False), Commission.platform.is_not(None)]
    if platform:
        where.append(Commission.platform == Platform(platform))
    rows = db.execute(
        select(Commission.platform, Commission.cycle_month,
               func.count(Commission.id).filter(forward),
               func.coalesce(func.sum(Commission.gross_amount).filter(forward), 0),
               func.coalesce(func.sum(Commission.gross_amount).filter(~forward), 0))
        .where(*where).group_by(Commission.platform, Commission.cycle_month)
        .order_by(Commission.cycle_month.desc(), Commission.platform)
        .limit(max(1, min(limit, 600)))).all()
    remitted = {(r.platform, r.cycle_month): r for r in db.scalars(select(MarketplaceRemittance))}
    out = []
    for plat, cycle, n, fwd, rev in rows:
        r = remitted.get((plat, cycle))
        earned, reversed_ = _money(fwd), -_money(rev)
        out.append(MonthRow(
            platform=_platform(plat), cycle_month=cycle, commissions=int(n), earned=earned,
            reversed=reversed_, net=earned - reversed_,
            remitted=_money(r.amount_received) if r else None,
            remitted_on=r.received_on if r else None,
            status="remitted" if r else "awaiting_remittance"))
    return out


@dataclass(frozen=True)
class ImportRow:
    id: str
    imported_at: datetime
    imported_by: str | None
    filename: str | None
    kind: str  # "lifecycle" | "commission"
    format: str | None
    total_rows: int
    recognised: int
    reversed: int
    unattributed: int
    held_pending_routing: int
    recognised_amount: Decimal | None
    reversed_amount: Decimal | None
    unrecovered_amount: Decimal | None
    import_id: str | None


def _import_row(log: ModerationLog, by: str | None) -> ImportRow:
    c = log.context or {}
    lifecycle = "import_id" in c

    def num(key: str) -> int:
        # The older commission path logs some of these as the rows themselves.
        value = c.get(key) or 0
        return len(value) if isinstance(value, (list, dict)) else int(value)

    def amount(key: str) -> Decimal | None:
        return _money(c[key]) if c.get(key) not in (None, "") else None

    return ImportRow(
        id=log.log_id or str(log.id), imported_at=log.created_at, imported_by=by,
        filename=c.get("filename"), kind="lifecycle" if lifecycle else "commission",
        format=c.get("format"), total_rows=num("total_rows"),
        recognised=num("recognised") if lifecycle else num("imported"),
        reversed=num("reversed"),
        unattributed=num("unattributed") if lifecycle else num("unmatched"),
        held_pending_routing=num("held_pending_routing"),
        recognised_amount=amount("recognised_amount"), reversed_amount=amount("reversed_amount"),
        unrecovered_amount=amount("unrecovered_amount"), import_id=c.get("import_id"))


def _by_names(db: Session, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: (u.display_name or (f"@{u.username}" if u.username else None))
            for u in db.scalars(select(User).where(User.id.in_(ids)))}


def imports(db: Session, *, limit: int = 50) -> list[ImportRow]:
    logs = list(db.scalars(
        select(ModerationLog).where(ModerationLog.action == ModerationAction.csv_import)
        .order_by(ModerationLog.created_at.desc()).limit(max(1, min(limit, MAX_LIMIT)))))
    names = _by_names(db, [log.moderator_id for log in logs])
    return [_import_row(log, names.get(log.moderator_id)) for log in logs]


@dataclass
class ImportDetail:
    summary: ImportRow
    lifecycle: dict[str, int]
    transactions: list[TransactionRow]


def import_detail(db: Session, log_id: str) -> ImportDetail:
    log = db.scalar(select(ModerationLog).where(
        ModerationLog.log_id == log_id, ModerationLog.action == ModerationAction.csv_import))
    if log is None:
        raise NotFoundError("That import is not in the history.", code="import_not_found")
    row = _import_row(log, _by_names(db, [log.moderator_id]).get(log.moderator_id))
    rows: list[TransactionRow] = []
    if row.import_id:
        page = db.execute(
            select(AffiliatePostback, Review.title)
            .outerjoin(Review, Review.id == AffiliatePostback.review_id)
            .where(AffiliatePostback.source_import_id == row.import_id)
            .order_by(AffiliatePostback.received_at, AffiliatePostback.id)
            .limit(MAX_LIMIT)).all()
        rows = [TransactionRow(
            id=p.id, platform=_platform(p.platform), order_ref=p.external_order_id,
            status=_platform(p.canonical_status), settlement=_platform(p.settlement_status),
            commission=_money(p.reported_payout) if p.reported_payout is not None else None,
            order_amount=_money(p.reported_amount) if p.reported_amount is not None else None,
            product_name=p.product_name,
            seller_name=p.seller_name, review_id=p.review_id, review_title=title,
            unrecovered=_money(p.unrecovered_amount) if p.unrecovered_amount else None,
            import_id=p.source_import_id, recorded_at=p.received_at) for p, title in page]
    lifecycle = {k: int(v) for k, v in ((log.context or {}).get("lifecycle") or {}).items()}
    return ImportDetail(summary=row, lifecycle=lifecycle, transactions=rows)


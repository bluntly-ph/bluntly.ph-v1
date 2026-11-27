"""Community price observations and the price panel (FR-2).

FR-2 verbatim: *"Price panel from community-submitted purchase price
observations — displayed only when ≥ 3 independent observations exist;
partial-data empty states specified."*

Four decisions follow from that wording and the completion contract, and each
one could reasonably have gone the other way:

**"Independent" means distinct submitters, not distinct rows.** Otherwise one
person could post three observations and unlock the panel alone, which is the
exact failure mode the threshold exists to prevent. `price_history` allows many
rows per user, so the count is over `DISTINCT submitted_by`. A NULL submitter
(a row whose author was deleted) cannot be shown to be independent of anything,
so it never counts toward the threshold — but its price still participates in
the summary once the panel is unlocked, because it was a real observation.

**Only approved observations count.** The completion contract makes every
observation pending until a moderator approves or rejects it (migration 0044),
and the panel is built from approved rows alone. A pending price is counted —
so the UI can say something is waiting — but never priced; a rejected one is
neither.

**Nothing here is scraped.** `price_history` is community-submitted by design
(`docs/schema.md`: "Never scraped"), and the anti-scraping mandate is permanent
(`MILESTONES.md`, owner decision 2026-07-15). This module reads the database and
nothing else; there is no marketplace call anywhere in it.

**The panel reports a range and a median, not an average.** Prices across
platforms and variants are a skewed sample with occasional nonsense at the
edges; a median is what survives one person typing 1 peso or 100,000. The mean
is deliberately not offered, so nobody builds a "market price" claim on it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import Platform, PriceObservationSource, PriceObservationStatus
from app.models.product import PriceHistory, Product
from app.models.user import User
from app.schemas.product import (
    PriceObservationDecision,
    PriceObservationQueueItem,
    _ph_today,
)
from app.services import notification_service

#: §16: a submitted price "wildly outside the product's recent range gets held
#: for a quick admin glance". Recent = observed within this window; the range is
#: judged against that marketplace's median, never a blend of marketplaces.
BASELINE_WINDOW_DAYS = 180
#: Until this many approved observations exist for a product on a marketplace,
#: there is no real baseline and every new price gets an admin glance.
BASELINE_MIN_OBSERVATIONS = 3
#: Outside [median / OUTLIER_FACTOR, median * OUTLIER_FACTOR] is "wildly outside".
OUTLIER_FACTOR = Decimal(2)

HOLD_NO_BASELINE = "no_baseline"
HOLD_OUTLIER = "outlier"

#: Kept for API compatibility: the old FR-2 "3 independent reporters" rule is
#: superseded by the baseline rule above (Business Rules §16).
MIN_INDEPENDENT_OBSERVATIONS = BASELINE_MIN_OBSERVATIONS


@dataclass(frozen=True)
class PricePoint:
    observed_at: date
    price: Decimal


@dataclass(frozen=True)
class PricePanel:
    """Price history for a product: one series per marketplace (§16)."""

    observation_count: int
    independent_count: int
    sufficient: bool
    low: Decimal | None = None
    high: Decimal | None = None
    median: Decimal | None = None
    currency: str = "PHP"
    latest_observed_at: date | None = None
    platforms: tuple[str, ...] = ()
    #: Observations still waiting for an admin glance: counted, never priced.
    pending_count: int = 0
    #: One line per marketplace, never merged or averaged across them.
    series: dict[str, tuple[PricePoint, ...]] = field(default_factory=dict)


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal(2)


def series_from(approved) -> dict[str, tuple[PricePoint, ...]]:
    """Per marketplace, one point per day: that day's median on that marketplace.

    Grouped by platform FIRST, so two marketplaces never blend into one line —
    the "cheaper on one platform" signal §16 exists to keep.
    """
    by_platform: dict[str, dict[date, list[Decimal]]] = {}
    for row in approved:
        days = by_platform.setdefault(row.platform.value, {})
        days.setdefault(row.observed_at, []).append(Decimal(row.price))
    return {
        platform: tuple(PricePoint(day, _median(prices)) for day, prices in sorted(days.items()))
        for platform, days in sorted(by_platform.items())
    }


def panel_from(rows) -> PricePanel:
    """Build price history from observations. No database, on purpose.

    Takes anything with `submitted_by`, `price`, `observed_at`, `platform` and
    `status`, so a test can pass plain objects and exercise the rule directly.
    Only approved observations are priced; pending ones are counted.
    """
    rows = list(rows)
    approved = [r for r in rows if r.status == PriceObservationStatus.approved]
    pending = sum(1 for r in rows if r.status == PriceObservationStatus.pending)
    independent = len({r.submitted_by for r in approved if r.submitted_by is not None})
    if not approved:
        return PricePanel(observation_count=0, independent_count=0, sufficient=False,
                          pending_count=pending)
    prices = [Decimal(r.price) for r in approved]
    series = series_from(approved)
    return PricePanel(
        observation_count=len(approved),
        independent_count=independent,
        sufficient=True,
        low=min(prices),
        high=max(prices),
        median=_median(prices),
        latest_observed_at=max(r.observed_at for r in approved),
        platforms=tuple(series.keys()),
        pending_count=pending,
        series=series,
    )


def hold_reason_for(baseline: list[Decimal], price: Decimal) -> str | None:
    """Why a new price waits for an admin, or None when it may publish (§16)."""
    if len(baseline) < BASELINE_MIN_OBSERVATIONS:
        return HOLD_NO_BASELINE
    median = _median(baseline)
    if median <= 0:
        return HOLD_OUTLIER
    if price > median * OUTLIER_FACTOR or price < median / OUTLIER_FACTOR:
        return HOLD_OUTLIER
    return None


def _baseline(db: Session, product_id: uuid.UUID, platform: Platform) -> list[Decimal]:
    since = _ph_today() - timedelta(days=BASELINE_WINDOW_DAYS)
    return [Decimal(p) for p in db.scalars(
        select(PriceHistory.price).where(
            PriceHistory.product_id == product_id,
            PriceHistory.platform == platform,
            PriceHistory.status == PriceObservationStatus.approved,
            PriceHistory.observed_at >= since,
        ))]


def new_observation(db: Session, product_id: uuid.UUID, user_id: uuid.UUID | None,
                    platform: Platform, price: Decimal, observed_at: date,
                    variant: str | None, *,
                    source: PriceObservationSource = PriceObservationSource.manual,
                    review_id: uuid.UUID | None = None) -> PriceHistory:
    """An unsaved observation, published or held per §16. Callers own the transaction.

    Separate from `submit_observation` so review submission can add one inside
    its own transaction: a review and the price it reports either both land or
    neither does.
    """
    hold = hold_reason_for(_baseline(db, product_id, platform), Decimal(price))
    return PriceHistory(product_id=product_id, submitted_by=user_id,
                        platform=platform, price=price, observed_at=observed_at,
                        variant=variant, source=source, review_id=review_id,
                        status=(PriceObservationStatus.pending if hold
                                else PriceObservationStatus.approved),
                        hold_reason=hold)


def submit_observation(db: Session, product_id: uuid.UUID, user_id: uuid.UUID,
                       platform: Platform, price: Decimal,
                       observed_at: date, variant: str | None,
                       review_id: uuid.UUID | None = None) -> PriceHistory:
    """A price report, which always belongs to one of the reporter's reviews (§16).

    "User-submitted price reports are always attached to an existing review,
    never standalone, leaning on that review's own verification photo or
    receipt for backing rather than needing separate proof."
    """
    from app.models.review import Review
    review = db.get(Review, review_id) if review_id is not None else None
    if (review is None or review.product_id != product_id or review.author_id != user_id
            or review.is_removed or review.published_at is None):
        raise AppError(
            "Report a price from your own review of this product.",
            code="price_needs_review", status_code=422, title="Invalid price report")
    row = new_observation(db, product_id, user_id, platform, price, observed_at, variant,
                          review_id=review.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_panel(db: Session, product_id: uuid.UUID) -> PricePanel:
    """The price panel for a product, or an insufficient-data result.

    Always returns a panel object rather than None: "not enough observations
    yet" is a state the UI has to render (FR-2 asks for partial-data empty
    states), and it needs the counts to say how far off it is.
    """
    rows = db.scalars(
        select(PriceHistory).where(PriceHistory.product_id == product_id)
    ).all()
    return panel_from(rows)


def panels_for(db: Session, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, PricePanel]:
    """Panels for several products in one query - the comparison view's need.

    Comparison shows up to four products; asking per product would be four
    round trips to a database in another region for data that one grouped read
    already has. Each group goes through `panel_from`, so the comparison and
    the product page cannot disagree about the threshold.
    """
    if not product_ids:
        return {}
    rows = db.scalars(
        select(PriceHistory).where(PriceHistory.product_id.in_(product_ids))
    ).all()

    grouped: dict[uuid.UUID, list[PriceHistory]] = {pid: [] for pid in product_ids}
    for row in rows:
        grouped.setdefault(row.product_id, []).append(row)
    return {pid: panel_from(items) for pid, items in grouped.items()}


def observation_count(db: Session, product_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count(PriceHistory.id))
        .where(PriceHistory.product_id == product_id)
    ) or 0


# ------------------------------------------------------------- moderation

def _queue_item(row: PriceHistory, product_name: str | None,
                submitter: str | None, usual: list[Decimal] | None = None,
                viewer_id: uuid.UUID | None = None) -> PriceObservationQueueItem:
    usual = usual or []
    return PriceObservationQueueItem(
        id=row.id, product_id=row.product_id, product_name=product_name,
        platform=row.platform, price=row.price, variant=row.variant,
        observed_at=row.observed_at, source=row.source, status=row.status,
        submitter_username=submitter, decision_note=row.decision_note,
        hold_reason=row.hold_reason, created_at=row.created_at,
        usual_median=_median(usual) if usual else None, usual_count=len(usual),
        reported_by_viewer=(viewer_id is not None and row.submitted_by == viewer_id),
    )


#: The Prices screen's orders (MQA-007). Oldest first stays the default - a
#: price reported earlier is checked earlier - and the newest are one choice away.
#: "product" keeps one product's prices together so they can be compared (MQA-042).
PRICE_QUEUE_SORTS = ("oldest", "newest", "product")


@dataclass(frozen=True)
class PendingQuery:
    """What the Prices screen asks for. The list and its count read the same
    one, so "164 waiting" is always the number the pages add up to (MQA-043)."""

    product_id: uuid.UUID | None = None
    platform: Platform | None = None
    source: PriceObservationSource | None = None
    #: "outlier" or "no_baseline" - why the price is waiting.
    held: str | None = None
    #: Words in the product's name.
    q: str | None = None
    #: "hide" leaves out the viewer's own reports (they cannot decide them).
    mine: str | None = None
    viewer_id: uuid.UUID | None = None
    sort: str = "oldest"


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _pending(stmt, query: PendingQuery):
    stmt = (stmt.join(Product, Product.id == PriceHistory.product_id)
            .where(PriceHistory.status == PriceObservationStatus.pending))
    if query.product_id is not None:
        stmt = stmt.where(PriceHistory.product_id == query.product_id)
    if query.platform is not None:
        stmt = stmt.where(PriceHistory.platform == query.platform)
    if query.source is not None:
        stmt = stmt.where(PriceHistory.source == query.source)
    if query.held:
        stmt = stmt.where(PriceHistory.hold_reason == query.held)
    if query.q and query.q.strip():
        stmt = stmt.where(Product.canonical_name.ilike(_like(query.q.strip()), escape="\\"))
    if query.mine == "hide" and query.viewer_id is not None:
        stmt = stmt.where(or_(PriceHistory.submitted_by.is_(None),
                              PriceHistory.submitted_by != query.viewer_id))
    return stmt


def count_pending(db: Session, query: PendingQuery = PendingQuery()) -> int:
    return int(db.scalar(_pending(select(func.count(PriceHistory.id)).select_from(PriceHistory),
                                  query)) or 0)


def _usual_prices(db: Session, pairs: set[tuple[uuid.UUID, Platform]]) -> dict:
    """The approved recent prices per (product, marketplace) - the same window
    and marketplace split as the hold rule (`_baseline`) - for a whole page in
    one query, so each row can show what the product usually costs there."""
    if not pairs:
        return {}
    since = _ph_today() - timedelta(days=BASELINE_WINDOW_DAYS)
    out: dict[tuple[uuid.UUID, Platform], list[Decimal]] = {}
    for product_id, platform, price in db.execute(
            select(PriceHistory.product_id, PriceHistory.platform, PriceHistory.price).where(
                tuple_(PriceHistory.product_id, PriceHistory.platform).in_(list(pairs)),
                PriceHistory.status == PriceObservationStatus.approved,
                PriceHistory.observed_at >= since)):
        out.setdefault((product_id, platform), []).append(Decimal(price))
    return out


def list_pending(db: Session, *, product_id: uuid.UUID | None = None,
                 limit: int = 50, offset: int = 0,
                 query: PendingQuery | None = None) -> list[PriceObservationQueueItem]:
    """One page of the prices waiting for a decision, in the asked order."""
    query = query or PendingQuery(product_id=product_id)
    stmt = _pending(select(PriceHistory, Product.canonical_name, User.username)
                    .select_from(PriceHistory)
                    .outerjoin(User, User.id == PriceHistory.submitted_by), query)
    order = {
        "newest": (PriceHistory.created_at.desc(), PriceHistory.id),
        "product": (func.lower(Product.canonical_name), PriceHistory.platform,
                    PriceHistory.price, PriceHistory.created_at, PriceHistory.id),
    }.get(query.sort, (PriceHistory.created_at, PriceHistory.id))
    rows = db.execute(stmt.order_by(*order).limit(limit).offset(offset)).all()
    usual = _usual_prices(db, {(r.product_id, r.platform) for r, _, _ in rows})
    return [_queue_item(row, name, username, usual.get((row.product_id, row.platform)),
                        query.viewer_id)
            for row, name, username in rows]


def decide_observation(db: Session, observation_id: uuid.UUID, moderator: User,
                       decision: PriceObservationDecision) -> PriceObservationQueueItem:
    """Approve or reject one observation.

    Refuses a moderator deciding their own price — the same self-dealing rule
    as `self_report` and seller claims — and a second decision on a decided
    row, so an approval cannot be silently flipped.
    """
    row = db.get(PriceHistory, observation_id, with_for_update=True)
    if row is None:
        raise NotFoundError("Price observation not found.")
    if row.submitted_by is not None and row.submitted_by == moderator.id:
        raise AppError("You cannot decide a price you submitted.", code="self_decision",
                       status_code=422, title="Invalid decision")
    if row.status != PriceObservationStatus.pending:
        raise AppError("This price has already been decided.",
                       code="price_observation_already_decided", status_code=409,
                       title="Price already decided")

    row.status = (PriceObservationStatus.approved if decision.decision == "approve"
                  else PriceObservationStatus.rejected)
    row.decided_by_id = moderator.id
    row.decided_at = datetime.now(UTC)
    row.decision_note = decision.note
    approved = row.status == PriceObservationStatus.approved
    notification_service.notify(
        db, row.submitted_by,
        "price_approved" if approved else "price_rejected",
        "Your price report was approved" if approved else "Your price report was not approved",
        body=decision.note)
    # MQA-008: the decision is audited like every other moderation action, so the
    # Overview's Recent Activity and the Activity log show it.
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    db.add(ModerationLog(
        target_type=None, target_ref=row.id, moderator_id=moderator.id,
        action=ModerationAction.approve if approved else ModerationAction.reject,
        notes=decision.note,
        context={"price_observation_id": str(row.id), "product_id": str(row.product_id),
                 "outcome": "price_approved" if approved else "price_rejected"}))
    db.commit()
    db.refresh(row)

    product = db.get(Product, row.product_id)
    submitter = db.get(User, row.submitted_by) if row.submitted_by else None
    return _queue_item(row, product.canonical_name if product else None,
                       submitter.username if submitter else None)

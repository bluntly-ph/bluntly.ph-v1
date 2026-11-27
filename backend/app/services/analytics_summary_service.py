"""The admin Analytics screen (Figma Screen/Admin/Analytics 8071:16115).

One read per range (7d / 30d / 90d / 12m), each figure beside the same figure
for the period before. Every number counts rows that are actually recorded:

  reviews published   reviews.published_at (not removed)
  votes cast          review_votes.created_at
  review views        review_reading_sessions.started_at (one per reading)
  affiliate clicks    sessions.clicked_at (an affiliate click-through)
  orders              affiliate_postbacks.received_at (marketplace-reported)
  commission          commissions.created_at, real money only, net of reversals
  where readers are   request_geo_buckets (edge-resolved city; no IP; 90 days)

Nothing is estimated. A figure with no source would be left out, not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.models.commission import Commission
from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    PayoutStatus,
)
from app.models.integrity import ImageFingerprint
from app.models.moderation import ModerationLog
from app.models.payout import Payout
from app.models.postback import AffiliatePostback
from app.models.product import Product
from app.models.review import Review
from app.models.session import Session as ClickSession
from app.models.telemetry import ReviewReadingSession
from app.models.traffic import RequestGeoBucket
from app.models.user import User
from app.models.vote import ReviewVote

RANGES = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}
DECISIONS = (ModerationAction.approve, ModerationAction.reject, ModerationAction.unpublish,
             ModerationAction.remove)
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Kpi:
    key: str
    current: Decimal
    previous: Decimal


@dataclass
class Summary:
    range: str
    start: datetime
    end: datetime
    kpis: list[Kpi]
    #: Reviews published per day (or per week for 90d / 12m), with the period before.
    series: list[dict]
    series_unit: str
    funnel: dict[str, Decimal]
    moderation: dict
    community: dict
    top_products: list[dict]
    places: list[dict]
    places_total: int
    needs_a_look: dict[str, int] = field(default_factory=dict)


def _count(db: Session, col, start: datetime, end: datetime, *where) -> int:
    return int(db.scalar(select(func.count()).where(col >= start, col < end, *where)) or 0)


def _commission(db: Session, start: datetime, end: datetime) -> Decimal:
    value = db.scalar(select(func.coalesce(func.sum(Commission.gross_amount), 0)).where(
        Commission.is_test.is_(False), Commission.created_at >= start,
        Commission.created_at < end))
    return Decimal(value or 0).quantize(CENT)


def _figures(db: Session, start: datetime, end: datetime) -> dict[str, Decimal]:
    published = (Review.published_at.is_not(None), Review.is_removed.is_(False))
    return {
        "reviews_published": Decimal(_count(db, Review.published_at, start, end, *published)),
        "votes_cast": Decimal(_count(db, ReviewVote.created_at, start, end)),
        "review_views": Decimal(_count(db, ReviewReadingSession.started_at, start, end)),
        "affiliate_clicks": Decimal(_count(db, ClickSession.clicked_at, start, end)),
        "orders": Decimal(_count(db, AffiliatePostback.received_at, start, end)),
        "commission": _commission(db, start, end),
    }


def _series(db: Session, start: datetime, end: datetime, prev_start: datetime,
            days: int) -> tuple[list[dict], str]:
    step = 1 if days <= 31 else 7
    unit = "day" if step == 1 else "week"
    published = (Review.published_at.is_not(None), Review.is_removed.is_(False))

    def buckets(a: datetime, b: datetime) -> dict[int, int]:
        bucket = func.floor(func.extract("epoch", Review.published_at - a) / (86400 * step))
        rows = db.execute(select(bucket, func.count())
                          .where(Review.published_at >= a, Review.published_at < b, *published)
                          .group_by(bucket)).all()
        return {int(k): int(n) for k, n in rows}

    # Steps count from each period's own start, so both periods align bucket for bucket.
    now_b, prev_b = buckets(start, end), buckets(prev_start, start)
    out = []
    for i in range((days + step - 1) // step):
        at = start + timedelta(days=i * step)
        out.append({"start": at, "current": now_b.get(i, 0), "previous": prev_b.get(i, 0)})
    return out, unit


def _median_hours(db: Session, start: datetime, end: datetime) -> float | None:
    """Published -> first earnings / take-down decision, for decisions in range."""
    first = (select(ModerationLog.target_ref.label("rid"),
                    func.min(ModerationLog.created_at).label("at"))
             .where(ModerationLog.action.in_(DECISIONS), ModerationLog.created_at >= start,
                    ModerationLog.created_at < end, ModerationLog.moderator_id.is_not(None))
             .group_by(ModerationLog.target_ref).subquery())
    value = db.scalar(select(func.percentile_cont(0.5).within_group(
        func.extract("epoch", first.c.at - Review.published_at)))
        .select_from(first).join(Review, Review.id == first.c.rid)
        .where(Review.published_at.is_not(None), first.c.at >= Review.published_at))
    # Two decimals (36 s): the screen shows minutes, and 0.1 h hid anything under 6 min.
    return round(float(value) / 3600, 2) if value is not None else None


def summary(db: Session, range_: str = "30d", now: datetime | None = None) -> Summary:
    now = now or datetime.now(MANILA)
    days = RANGES.get(range_, 30)
    end = now
    start = end - timedelta(days=days)
    prev_start = start - timedelta(days=days)

    cur, prev = _figures(db, start, end), _figures(db, prev_start, start)
    kpis = [Kpi(k, cur[k], prev[k]) for k in
            ("reviews_published", "votes_cast", "affiliate_clicks", "orders", "commission")]
    series, unit = _series(db, start, end, prev_start, days)

    # Moderation: decisions by staff in range, the queue now, reports.
    mix = {a.value: int(n) for a, n in db.execute(
        select(ModerationLog.action, func.count()).where(
            ModerationLog.action.in_(DECISIONS), ModerationLog.moderator_id.is_not(None),
            ModerationLog.created_at >= start, ModerationLog.created_at < end)
        .group_by(ModerationLog.action)).all()}
    deciders = int(db.scalar(select(func.count(func.distinct(ModerationLog.moderator_id))).where(
        ModerationLog.action.in_(DECISIONS), ModerationLog.created_at >= start,
        ModerationLog.created_at < end)) or 0)
    queued = select(Review).where(Review.earn_eligible_status == EarnEligibleStatus.pending,
                                  Review.is_removed.is_(False))
    in_queue = int(db.scalar(select(func.count()).select_from(queued.subquery())) or 0)
    oldest = db.scalar(select(func.min(Review.published_at)).where(
        Review.earn_eligible_status == EarnEligibleStatus.pending, Review.is_removed.is_(False)))
    report = (ModerationLog.action == ModerationAction.report)
    opened = _count(db, ModerationLog.created_at, start, end, report)
    closed = _count(db, ModerationLog.resolved_at, start, end, report,
                    ModerationLog.resolution.is_not(None))
    close_h = db.scalar(select(func.percentile_cont(0.5).within_group(
        func.extract("epoch", ModerationLog.resolved_at - ModerationLog.created_at)))
        .where(report, ModerationLog.resolved_at >= start, ModerationLog.resolved_at < end))
    moderation = {
        "median_decision_hours": _median_hours(db, start, end),
        "previous_median_decision_hours": _median_hours(db, prev_start, start),
        "in_queue": in_queue, "oldest_waiting_at": oldest,
        "decisions": sum(mix.values()), "deciders": deciders,
        "approved": mix.get("approve", 0), "rejected": mix.get("reject", 0),
        "taken_down": mix.get("unpublish", 0) + mix.get("remove", 0),
        "reports_opened": opened, "reports_closed": closed,
        "median_report_close_hours": round(float(close_h) / 3600, 1) if close_h else None,
    }

    # Community.
    real = User.role.is_not(None)
    new_members = _count(db, User.created_at, start, end, real)
    prev_members = _count(db, User.created_at, prev_start, start, real)
    published = (Review.published_at.is_not(None), Review.is_removed.is_(False))
    active = int(db.scalar(select(func.count(func.distinct(Review.author_id))).where(
        Review.published_at >= start, Review.published_at < end, *published)) or 0)
    voters_now = select(ReviewVote.voter_id).where(ReviewVote.created_at >= start,
                                                   ReviewVote.created_at < end).distinct()
    voters_before = select(ReviewVote.voter_id).where(ReviewVote.created_at >= prev_start,
                                                      ReviewVote.created_at < start).distinct()
    n_now = int(db.scalar(select(func.count()).select_from(voters_now.subquery())) or 0)
    returning = int(db.scalar(select(func.count()).select_from(
        voters_now.where(ReviewVote.voter_id.in_(voters_before)).subquery())) or 0)
    authors = select(Review.author_id).where(*published).distinct()
    stages = {int(s): int(n) for s, n in db.execute(
        select(User.trust_stage, func.count()).where(User.id.in_(authors))
        .group_by(User.trust_stage)).all()}
    community = {"new_members": new_members, "previous_new_members": prev_members,
                 "active_reviewers": active,
                 "returning_voters_pct": round(100 * returning / n_now) if n_now else None,
                 "reviewers_by_stage": {str(k): v for k, v in sorted(stages.items())}}

    # Top products by commission in range.
    top = db.execute(
        select(Product.id, Product.canonical_name,
               func.coalesce(func.sum(Commission.gross_amount), 0).label("commission"))
        .join(Review, Review.product_id == Product.id)
        .join(Commission, Commission.review_id == Review.id)
        .where(Commission.is_test.is_(False), Commission.created_at >= start,
               Commission.created_at < end)
        .group_by(Product.id).order_by(func.sum(Commission.gross_amount).desc()).limit(5)).all()
    top_products = []
    for pid, name, commission in top:
        reviews = int(db.scalar(select(func.count()).where(Review.product_id == pid, *published))
                      or 0)
        clicks = _count(db, ClickSession.clicked_at, start, end, ClickSession.product_id == pid)
        orders = int(db.scalar(select(func.count()).select_from(AffiliatePostback).join(
            Review, Review.id == AffiliatePostback.review_id).where(
            Review.product_id == pid, AffiliatePostback.received_at >= start,
            AffiliatePostback.received_at < end)) or 0)
        top_products.append({"id": pid, "name": name, "reviews": reviews, "clicks": clicks,
                             "orders": orders, "commission": Decimal(commission).quantize(CENT)})

    # Where readers are (edge-resolved city, request buckets).
    places_rows = db.execute(
        select(RequestGeoBucket.city, RequestGeoBucket.country,
               func.sum(RequestGeoBucket.request_count))
        .where(RequestGeoBucket.bucket_start >= start, RequestGeoBucket.city.is_not(None))
        .group_by(RequestGeoBucket.city, RequestGeoBucket.country)
        .order_by(func.sum(RequestGeoBucket.request_count).desc()).limit(5)).all()
    places_total = int(db.scalar(select(func.coalesce(func.sum(RequestGeoBucket.request_count), 0))
                                 .where(RequestGeoBucket.bucket_start >= start)) or 0)
    places = [{"city": c, "country": cc, "requests": int(n)} for c, cc, n in places_rows]

    # Needs a look: what the nightly integrity sweep and the ledgers raised.
    open_system = (ModerationLog.action == ModerationAction.report,
                   ModerationLog.reporter_id.is_(None), ModerationLog.resolution.is_(None))
    rings = int(db.scalar(select(func.count()).where(
        *open_system, ModerationLog.context["signal"].astext == "collusion")) or 0)
    reused = int(db.scalar(select(func.count()).select_from(
        select(ImageFingerprint.sha256).group_by(ImageFingerprint.sha256)
        .having(func.count(func.distinct(ImageFingerprint.uploader_id)) > 1).subquery())) or 0)
    investigating = int(db.scalar(select(func.count(User.id)).where(
        User.is_under_investigation.is_(True), User.is_suspended.is_(False))) or 0)
    failed = int(db.scalar(select(func.count(Payout.id)).where(
        Payout.status == PayoutStatus.failed)) or 0)
    return Summary(range=range_, start=start, end=end, kpis=kpis, series=series,
                   series_unit=unit,
                   funnel={k: cur[k] for k in ("review_views", "affiliate_clicks", "orders",
                                               "commission")},
                   moderation=moderation, community=community, top_products=top_products,
                   places=places, places_total=places_total,
                   needs_a_look={"voting_rings": rings, "reused_photos": reused,
                                 "under_investigation": investigating,
                                 "failed_payouts": failed})


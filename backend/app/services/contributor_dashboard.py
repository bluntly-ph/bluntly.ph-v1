"""The redesigned contributor dashboard (Figma Screen/Dashboard 7833:9534;
meeting 2026-10-02, 3:00-5:20): one read for the whole screen.

    wallet     total balance, and what it is made of: Honesty Fund credits and
               commission; "pending" is the part still clearing (credited, but
               the marketplace has not paid Bluntly for it yet, §15/§19)
    earnings   earned vs returned, by day for a week or by week for a month,
               and the products that earned most in that window
    trust      the stage ladder (Newcomer .. Community Expert) and what the
               NEXT stage asks for, read from the same thresholds that
               promote (services/trust.py), so the rings cannot promise a
               promotion the recompute would refuse
    honesty    the Honesty Score (reputation_score, the number every profile
               shows) and the Honesty Fund credited so far
    reach      this month's funnel: views -> people helped -> link clicks ->
               purchases, against last month

Every figure is read from what the platform records. The wallet is one pot of
money, so "Honesty Fund" in it is the fund credits, capped at the balance, and
"Commission" is the rest: payouts are counted against commission first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import MANILA
from app.models.comment import ReviewComment
from app.models.commission import Commission
from app.models.enums import VoteDirection
from app.models.honesty_fund import HonestyFundDistribution
from app.models.product import Product
from app.models.review import Review
from app.models.session import Session as ClickSession
from app.models.traffic import ReviewViewBucket
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import commission_breakdown, payout_service
from app.services import trust as ladder
from app.services.commission_breakdown import CommissionBreakdown
from app.services.trust_service import held_by_concentration, voter_records

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

#: The level names, as `users.trust_level_name` writes them (lib/trust.ts).
LEVEL_NAMES = ("Newcomer", "Contributor", "Verified Buyer", "Established Reviewer",
               "Trusted Reviewer", "Community Expert")

PERIODS = ("week", "month")
#: Reach: this month so far (against the same days of last month), or last
#: month (against the whole month before it).
REACH_MONTHS = ("this", "last")
BEST_LIMIT = 3


@dataclass(frozen=True)
class Bucket:
    label: str
    start: date
    end: date  # inclusive
    earned: Decimal
    returned: Decimal
    current: bool


@dataclass(frozen=True)
class BestRow:
    review_id: uuid.UUID
    product_id: uuid.UUID | None
    product_name: str
    image_url: str | None
    views: int
    helped: int
    earned: Decimal


@dataclass(frozen=True)
class Requirement:
    key: str
    label: str
    have: float
    needed: float
    done: bool


@dataclass(frozen=True)
class ReachFigures:
    views: int
    helped: int
    clicks: int
    bought: int


@dataclass
class ContributorDashboard:
    total_balance: Decimal
    commission_balance: Decimal
    honesty_fund_balance: Decimal
    pending: Decimal
    withdrawable: Decimal
    minimum_cashout: Decimal
    period: str
    earned: Decimal
    returned: Decimal
    buckets: list[Bucket] = field(default_factory=list)
    best: list[BestRow] = field(default_factory=list)
    stage: int = 0
    level_name: str = LEVEL_NAMES[0]
    next_stage: int | None = None
    next_level_name: str | None = None
    requirements: list[Requirement] = field(default_factory=list)
    #: A promotion the requirements allow but the vote-concentration check
    #: holds for a moderator (ADR-016): said plainly rather than implied.
    held_for_review: bool = False
    honesty_score: int = 0
    honesty_fund_earned: Decimal = ZERO
    #: Any commission or Honesty Fund credit on record, ever: the dashboard's
    #: "No earnings yet" state (Figma 7855:10383) is for an account with none.
    has_earned: bool = False
    reach_choice: str = "this"
    reach_month: str = ""
    reach_previous_month: str = ""
    reach: ReachFigures | None = None
    reach_previous: ReachFigures | None = None


def _today(now: datetime | None) -> date:
    return (now or datetime.now(UTC)).astimezone(MANILA).date()


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Manila days [start, end] as UTC instants [lo, hi)."""
    return (datetime.combine(start, time.min, MANILA).astimezone(UTC),
            datetime.combine(end + timedelta(days=1), time.min, MANILA).astimezone(UTC))


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT)


def _windows(period: str, today: date) -> list[tuple[str, date, date]]:
    """A week: the last 7 days, one bar each (M T W ...). A month: the last 4
    weeks, one bar each, labelled by their first day."""
    if period == "week":
        return [((today - timedelta(days=i)).strftime("%a")[0],
                 today - timedelta(days=i), today - timedelta(days=i))
                for i in range(6, -1, -1)]
    out = []
    for i in range(3, -1, -1):
        end = today - timedelta(days=7 * i)
        start = end - timedelta(days=6)
        out.append((f"{start.strftime('%b')} {start.day}", start, end))
    return out


def _manila_day(column):
    return func.date(func.timezone("Asia/Manila", column))


def _earnings(db: Session, user_id: uuid.UUID, period: str,
              today: date) -> tuple[list[Bucket], Decimal, Decimal]:
    windows = _windows(period, today)
    first, last = windows[0][1], windows[-1][2]
    lo, hi = _bounds(first, last)
    day = _manila_day(Commission.created_at)
    forward = Commission.reverses_commission_id.is_(None)
    rows = db.execute(
        select(day,
               func.coalesce(func.sum(Commission.reviewer_share).filter(forward), 0),
               func.coalesce(func.sum(Commission.reviewer_share).filter(~forward), 0))
        .where(Commission.reviewer_id == user_id, Commission.created_at >= lo,
               Commission.created_at < hi)
        .group_by(day)).all()
    earned_by: dict[date, Decimal] = {d: _money(e) for d, e, _ in rows}
    returned_by: dict[date, Decimal] = {d: -_money(r) for d, _, r in rows}
    # Honesty Fund credits are earnings too: money into this member's wallet.
    fund_day = _manila_day(HonestyFundDistribution.created_at)
    for d, amount in db.execute(
            select(fund_day, func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
            .where(HonestyFundDistribution.reviewer_id == user_id,
                   HonestyFundDistribution.created_at >= lo,
                   HonestyFundDistribution.created_at < hi)
            .group_by(fund_day)).all():
        earned_by[d] = earned_by.get(d, ZERO) + _money(amount)

    buckets = []
    for label, start, end in windows:
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        buckets.append(Bucket(
            label=label, start=start, end=end,
            earned=sum((earned_by.get(d, ZERO) for d in days), ZERO),
            returned=sum((returned_by.get(d, ZERO) for d in days), ZERO),
            current=start <= today <= end))
    return (buckets, sum((b.earned for b in buckets), ZERO),
            sum((b.returned for b in buckets), ZERO))


def _best(db: Session, user_id: uuid.UUID, start: date, end: date) -> list[BestRow]:
    lo, hi = _bounds(start, end)
    earned = dict(db.execute(
        select(Commission.review_id, func.coalesce(func.sum(Commission.reviewer_share), 0))
        .where(Commission.reviewer_id == user_id, Commission.review_id.is_not(None),
               Commission.created_at >= lo, Commission.created_at < hi)
        .group_by(Commission.review_id)).all())
    views = dict(db.execute(
        select(ReviewViewBucket.review_id, func.coalesce(func.sum(ReviewViewBucket.view_count), 0))
        .join(Review, Review.id == ReviewViewBucket.review_id)
        .where(Review.author_id == user_id, ReviewViewBucket.bucket_start >= lo,
               ReviewViewBucket.bucket_start < hi)
        .group_by(ReviewViewBucket.review_id)).all())
    helped = dict(db.execute(
        select(ReviewVote.review_id, func.count(ReviewVote.id))
        .join(Review, Review.id == ReviewVote.review_id)
        .where(Review.author_id == user_id, ReviewVote.vote == VoteDirection.up,
               ReviewVote.created_at >= lo, ReviewVote.created_at < hi)
        .group_by(ReviewVote.review_id)).all())
    ids = {k for k, v in earned.items() if v} | {k for k, v in views.items() if v} | {
        k for k, v in helped.items() if v}
    if not ids:
        return []
    rows = db.execute(
        select(Review.id, Review.product_id, Review.photo_url, Product.canonical_name,
               Product.image_url, Review.title)
        .outerjoin(Product, Product.id == Review.product_id)
        .where(Review.id.in_(ids), Review.is_removed.is_(False))).all()
    out = [BestRow(review_id=rid, product_id=pid,
                   product_name=name or title or "Review",
                   image_url=_usable(product_image) or _usable(photo),
                   views=int(views.get(rid, 0)), helped=int(helped.get(rid, 0)),
                   earned=_money(earned.get(rid, 0)))
           for rid, pid, photo, name, product_image, title in rows]
    out.sort(key=lambda r: (r.earned, r.views, r.helped), reverse=True)
    return out[:BEST_LIMIT]


def _usable(url: str | None) -> str | None:
    """`usablePhoto` (lib/image.ts): an http(s) URL that is not a placeholder."""
    if url and url.startswith("http") and "example.com" not in url:
        return url
    return None


def _requirements(db: Session, user: User, review_count: int) -> list[Requirement]:
    """What the next stage asks for — the thresholds `determine_stage` and
    `evidence_capped_stage` promote on, read forwards."""
    nxt = user.trust_stage + 1
    if nxt > ladder.TOP_STAGE:
        return []
    verified = int(user.verified_review_count or 0)
    if nxt == 1:
        return [Requirement("reviews", "Published reviews", review_count, 1, review_count >= 1)]
    if nxt == 2:
        return [Requirement("receipt_reviews", "Receipt reviews", verified, 1, verified >= 1)]
    helpfulness = float(user.helpfulness_ratio or 0)
    evidence = sum(v.evidence for v in voter_records(db, user.id))
    need_reviews = ladder.STAGE_MIN_VERIFIED_REVIEWS[nxt]
    need_help = {3: ladder.STAGE3_HELPFULNESS, 4: ladder.STAGE4_HELPFULNESS,
                 5: ladder.STAGE5_HELPFULNESS}[nxt]
    need_people = ladder.stage_evidence_required(nxt)
    out = [
        Requirement("receipt_reviews", "Receipt reviews", verified, need_reviews,
                    verified >= need_reviews),
        Requirement("helpful_votes", "Helpful votes", round(evidence, 1), need_people,
                    evidence >= need_people),
        Requirement("helpfulness", "Helpfulness Score", round(helpfulness, 1), need_help,
                    helpfulness >= need_help),
    ]
    if nxt == 4:
        best = int(user.best_answer_count or 0)
        out.append(Requirement("best_answers", "Best answers", best, 3, best >= 3))
        out.append(Requirement("no_strikes", "No strikes", int(user.strikes or 0), 0,
                               int(user.strikes or 0) == 0))
    if nxt == 5:
        created = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=UTC)
        months = round((datetime.now(UTC) - created).days / 30, 1)
        out.append(Requirement("months_active", "Months active", months, 6, months >= 6))
    return out


def _month_start(d: date, back: int = 0) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) - back, 12)
    return date(y, m + 1, 1)


def _reach(db: Session, user_id: uuid.UUID, start: date, end: date) -> ReachFigures:
    lo, hi = _bounds(start, end)
    views = db.scalar(
        select(func.coalesce(func.sum(ReviewViewBucket.view_count), 0))
        .join(Review, Review.id == ReviewViewBucket.review_id)
        .where(Review.author_id == user_id, ReviewViewBucket.bucket_start >= lo,
               ReviewViewBucket.bucket_start < hi)) or 0
    # People helped: distinct members who marked a review helpful.
    helped = db.scalar(
        select(func.count(func.distinct(ReviewVote.voter_id)))
        .join(Review, Review.id == ReviewVote.review_id)
        .where(Review.author_id == user_id, ReviewVote.vote == VoteDirection.up,
               ReviewVote.created_at >= lo, ReviewVote.created_at < hi)) or 0
    clicked = func.coalesce(ClickSession.clicked_at, ClickSession.created_at)
    clicks = db.scalar(
        select(func.count(ClickSession.id))
        .join(Review, Review.id == ClickSession.review_id)
        .where(Review.author_id == user_id, clicked >= lo, clicked < hi)) or 0
    bought = db.scalar(
        select(func.count(Commission.id))
        .where(Commission.reviewer_id == user_id, Commission.reverses_commission_id.is_(None),
               Commission.is_test.is_(False), Commission.created_at >= lo,
               Commission.created_at < hi)) or 0
    return ReachFigures(views=int(views), helped=int(helped), clicks=int(clicks),
                        bought=int(bought))


def build(db: Session, user: User, *, period: str = "week", reach_month: str = "this",
          now: datetime | None = None) -> ContributorDashboard:
    if period not in PERIODS:
        raise ValueError(f"unknown period: {period}")
    if reach_month not in REACH_MONTHS:
        raise ValueError(f"unknown reach month: {reach_month}")
    today = _today(now)

    balance = _money(user.wallet_balance)
    clearing = _money(payout_service.uncleared_share(db, user.id))
    withdrawable = payout_service.withdrawable_from(balance, clearing)
    fund_earned = _money(db.scalar(
        select(func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
        .where(HonestyFundDistribution.reviewer_id == user.id)))
    fund_in_wallet = min(balance, fund_earned)

    buckets, earned, returned = _earnings(db, user.id, period, today)
    best = _best(db, user.id, buckets[0].start, buckets[-1].end)

    review_count = db.scalar(select(func.count(Review.id)).where(
        Review.author_id == user.id, Review.published_at.is_not(None),
        Review.is_removed.is_(False))) or 0
    stage = int(user.trust_stage or 0)
    nxt = stage + 1 if stage < ladder.TOP_STAGE else None

    back = 0 if reach_month == "this" else 1
    month = _month_start(today, back)
    before = _month_start(today, back + 1)
    month_end = today if back == 0 else _month_start(today, back - 1) - timedelta(days=1)
    reach = _reach(db, user.id, month, month_end)
    # Like for like: this month so far against the same days of last month
    # (2 days of October against 30 of September would read as a collapse).
    before_end = month - timedelta(days=1)
    if back == 0:
        before_end = min(before_end, before + (month_end - month))
    previous = _reach(db, user.id, before, before_end)
    requirements = _requirements(db, user, int(review_count))
    held = bool(requirements) and all(r.done for r in requirements) and bool(
        held_by_concentration(db, [user.id]))

    return ContributorDashboard(
        total_balance=balance, commission_balance=balance - fund_in_wallet,
        honesty_fund_balance=fund_in_wallet, pending=min(clearing, balance),
        withdrawable=withdrawable, minimum_cashout=_money(settings.payout_min_php),
        period=period, earned=earned, returned=returned, buckets=buckets, best=best,
        stage=stage, level_name=LEVEL_NAMES[stage],
        next_stage=nxt, next_level_name=LEVEL_NAMES[nxt] if nxt is not None else None,
        requirements=requirements, held_for_review=held,
        honesty_score=round(float(user.reputation_score or 0)),
        honesty_fund_earned=fund_earned,
        has_earned=_has_earned(db, user.id),
        reach_choice=reach_month, reach_month=month.strftime("%B"),
        reach_previous_month=before.strftime("%b"),
        reach=reach, reach_previous=previous)


# Performance (Figma Screen/Performance 7848:9542; meeting 4:58) ----------------

@dataclass(frozen=True)
class PerformanceProduct:
    product_id: uuid.UUID
    name: str
    image_url: str | None
    reviews: int
    #: "Your reviews" rows (Figma 7848:9831), over the selected period.
    views: int = 0
    helped: int = 0
    earned: Decimal = ZERO
    #: When the member last published a review of it (the chooser's date).
    published_at: datetime | None = None


@dataclass(frozen=True)
class PerformanceBucket:
    label: str
    start: date
    end: date
    views: int
    helped: int
    earned: Decimal
    returned: Decimal
    current: bool
    #: Card/Votes (7848:9606): helpful and not-helpful votes cast in the bucket.
    up: int = 0
    down: int = 0


@dataclass(frozen=True)
class DayEarned:
    day: date
    earned: Decimal


@dataclass(frozen=True)
class MarketplaceOrders:
    platform: str
    orders: int


@dataclass
class Performance:
    period: str
    product_id: uuid.UUID | None
    products: list[PerformanceProduct]
    totals: ReachFigures
    earned: Decimal
    returned: Decimal
    buckets: list[PerformanceBucket]
    #: Card/Review header: the average star rating of these reviews and how many.
    rating: Decimal | None = None
    review_count: int = 0
    #: Card/Review community row: helpful votes and comments, all time.
    upvotes: int = 0
    comments: int = 0
    #: Card/Votes totals over the period.
    helpful: int = 0
    not_helpful: int = 0
    #: Card/Earnings: earned per Manila day over the last 30 days, oldest first.
    daily: list[DayEarned] = field(default_factory=list)
    earned_30d: Decimal = ZERO
    earned_7d: Decimal = ZERO
    #: Card/From view to buy chips: the last 7 days against the 7 before.
    reach_week: ReachFigures | None = None
    reach_prev_week: ReachFigures | None = None
    #: Card/Commission: the split of the breakdown's net commission (yours, the
    #: Honesty Fund's, Bluntly's), every credited sale, not just the period's.
    share_you: Decimal = ZERO
    share_honesty_fund: Decimal = ZERO
    share_platform: Decimal = ZERO
    #: Card/Buyers: completed orders per marketplace (the breakdown's).
    orders: list[MarketplaceOrders] = field(default_factory=list)
    #: The ⓘ sheet (commission_breakdown): gross to net, split, marketplaces,
    #: products. "Earned", the donut and Card/Buyers read it too, so the sheet
    #: and the cards can never disagree.
    commission: CommissionBreakdown = field(default_factory=CommissionBreakdown)


def _reach_for(db: Session, user_id: uuid.UUID, review_ids: list, lo: datetime,
               hi: datetime) -> ReachFigures:
    if not review_ids:
        return ReachFigures(views=0, helped=0, clicks=0, bought=0)
    clicked = func.coalesce(ClickSession.clicked_at, ClickSession.created_at)
    return ReachFigures(
        views=int(db.scalar(
            select(func.coalesce(func.sum(ReviewViewBucket.view_count), 0))
            .where(ReviewViewBucket.review_id.in_(review_ids),
                   ReviewViewBucket.bucket_start >= lo, ReviewViewBucket.bucket_start < hi)) or 0),
        helped=int(db.scalar(
            select(func.count(func.distinct(ReviewVote.voter_id)))
            .where(ReviewVote.review_id.in_(review_ids), ReviewVote.vote == VoteDirection.up,
                   ReviewVote.created_at >= lo, ReviewVote.created_at < hi)) or 0),
        clicks=int(db.scalar(
            select(func.count(ClickSession.id))
            .where(ClickSession.review_id.in_(review_ids), clicked >= lo, clicked < hi)) or 0),
        bought=int(db.scalar(
            select(func.count(Commission.id))
            .where(Commission.review_id.in_(review_ids), Commission.reviewer_id == user_id,
                   Commission.reverses_commission_id.is_(None), Commission.is_test.is_(False),
                   Commission.created_at >= lo, Commission.created_at < hi)) or 0))


def performance(db: Session, user: User, *, product_id: uuid.UUID | None = None,
                period: str = "month", now: datetime | None = None) -> Performance:
    """How the member's reviews perform: all of them, or the ones on one
    product (the screen's product switcher), over a week or four weeks."""
    if period not in PERIODS:
        raise ValueError(f"unknown period: {period}")
    from app.core.errors import NotFoundError

    today = _today(now)
    rows = db.execute(
        select(Review.id, Review.product_id, Product.canonical_name, Product.image_url,
               Review.photo_url, Review.star_rating, Review.published_at)
        .outerjoin(Product, Product.id == Review.product_id)
        .where(Review.author_id == user.id, Review.is_removed.is_(False),
               Review.published_at.is_not(None))).all()
    products: dict[uuid.UUID, PerformanceProduct] = {}
    for _rid, pid, name, image, photo, _stars, published in rows:
        if pid is None:
            continue
        prev = products.get(pid)
        products[pid] = PerformanceProduct(
            product_id=pid, name=name or "Product",
            image_url=(prev.image_url if prev else None) or _usable(image) or _usable(photo),
            reviews=(prev.reviews if prev else 0) + 1,
            published_at=max(filter(None, (prev.published_at if prev else None, published)),
                             default=None))
    if product_id is not None and product_id not in products:
        raise NotFoundError("You have no published review of that product.",
                            code="performance_product_not_found")
    review_ids = [rid for rid, pid, *_ in rows if product_id is None or pid == product_id]
    product_of = {rid: pid for rid, pid, *_ in rows}
    stars = [r[5] for r in rows if (product_id is None or r[1] == product_id) and r[5] is not None]

    windows = _windows(period, today)
    lo, hi = _bounds(windows[0][1], windows[-1][2])
    by_day_views: dict[date, int] = {}
    by_day_helped: dict[date, int] = {}
    by_day_down: dict[date, int] = {}
    by_day_earned: dict[date, Decimal] = {}
    by_day_returned: dict[date, Decimal] = {}
    if review_ids:
        vday = _manila_day(ReviewViewBucket.bucket_start)
        for d, n in db.execute(
                select(vday, func.coalesce(func.sum(ReviewViewBucket.view_count), 0))
                .where(ReviewViewBucket.review_id.in_(review_ids),
                       ReviewViewBucket.bucket_start >= lo, ReviewViewBucket.bucket_start < hi)
                .group_by(vday)).all():
            by_day_views[d] = int(n)
        hday = _manila_day(ReviewVote.created_at)
        for d, n in db.execute(
                select(hday, func.count(ReviewVote.id))
                .where(ReviewVote.review_id.in_(review_ids), ReviewVote.vote == VoteDirection.up,
                       ReviewVote.created_at >= lo, ReviewVote.created_at < hi)
                .group_by(hday)).all():
            by_day_helped[d] = int(n)
        for d, n in db.execute(
                select(hday, func.count(ReviewVote.id))
                .where(ReviewVote.review_id.in_(review_ids),
                       ReviewVote.vote == VoteDirection.down,
                       ReviewVote.created_at >= lo, ReviewVote.created_at < hi)
                .group_by(hday)).all():
            by_day_down[d] = int(n)
        cday = _manila_day(Commission.created_at)
        forward = Commission.reverses_commission_id.is_(None)
        for d, e, r in db.execute(
                select(cday,
                       func.coalesce(func.sum(Commission.reviewer_share).filter(forward), 0),
                       func.coalesce(func.sum(Commission.reviewer_share).filter(~forward), 0))
                .where(Commission.review_id.in_(review_ids), Commission.reviewer_id == user.id,
                       Commission.created_at >= lo, Commission.created_at < hi)
                .group_by(cday)).all():
            by_day_earned[d] = _money(e)
            by_day_returned[d] = -_money(r)

    buckets = []
    for label, start, end in windows:
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        buckets.append(PerformanceBucket(
            label=label, start=start, end=end,
            views=sum(by_day_views.get(d, 0) for d in days),
            helped=sum(by_day_helped.get(d, 0) for d in days),
            earned=sum((by_day_earned.get(d, ZERO) for d in days), ZERO),
            returned=sum((by_day_returned.get(d, ZERO) for d in days), ZERO),
            current=start <= today <= end,
            up=sum(by_day_helped.get(d, 0) for d in days),
            down=sum(by_day_down.get(d, 0) for d in days)))

    totals = _reach_for(db, user.id, review_ids, lo, hi)
    out = Performance(
        period=period, product_id=product_id,
        products=sorted(products.values(), key=lambda p: p.name.lower()),
        totals=totals, earned=sum((b.earned for b in buckets), ZERO),
        returned=sum((b.returned for b in buckets), ZERO), buckets=buckets,
        review_count=len(review_ids),
        rating=(sum(stars, Decimal(0)) / len(stars)).quantize(Decimal("0.1")) if stars else None,
        helpful=sum(b.up for b in buckets), not_helpful=sum(b.down for b in buckets))

    # The last 30 Manila days, earned per day (Card/Earnings line).
    first = today - timedelta(days=29)
    lo30, hi30 = _bounds(first, today)
    daily: dict[date, Decimal] = {}
    if review_ids:
        cday = _manila_day(Commission.created_at)
        for d, e in db.execute(
                select(cday, func.coalesce(func.sum(Commission.reviewer_share), 0))
                .where(Commission.review_id.in_(review_ids), Commission.reviewer_id == user.id,
                       Commission.reverses_commission_id.is_(None),
                       Commission.created_at >= lo30, Commission.created_at < hi30)
                .group_by(cday)).all():
            daily[d] = _money(e)
    days30 = [first + timedelta(days=i) for i in range(30)]
    out.daily = [DayEarned(day=d, earned=daily.get(d, ZERO)) for d in days30]
    out.earned_30d = sum(daily.values(), ZERO)
    out.earned_7d = sum((v for d, v in daily.items() if d > today - timedelta(days=7)), ZERO)

    # "Where the commission went", its ⓘ sheet and Card/Buyers: every sale
    # credited to the member (all of them, or this product's), whatever the period.
    out.commission = commission_breakdown.breakdown(
        db, user, review_ids=[rid for rid, *_ in rows], product_id=product_id)
    out.share_you = out.commission.you
    out.share_honesty_fund = out.commission.honesty_fund
    out.share_platform = out.commission.bluntly
    out.orders = [MarketplaceOrders(platform=m.platform, orders=m.orders)
                  for m in out.commission.marketplaces]

    wk_lo, wk_hi = _bounds(today - timedelta(days=6), today)
    pw_lo, pw_hi = _bounds(today - timedelta(days=13), today - timedelta(days=7))
    out.reach_week = _reach_for(db, user.id, review_ids, wk_lo, wk_hi)
    out.reach_prev_week = _reach_for(db, user.id, review_ids, pw_lo, pw_hi)
    if not review_ids:
        return out

    out.upvotes = int(db.scalar(select(func.count(ReviewVote.id)).where(
        ReviewVote.review_id.in_(review_ids), ReviewVote.vote == VoteDirection.up)) or 0)
    out.comments = int(db.scalar(select(func.count(ReviewComment.id)).where(
        ReviewComment.review_id.in_(review_ids), ReviewComment.is_removed.is_(False))) or 0)

    in_period = [Commission.review_id.in_(review_ids), Commission.reviewer_id == user.id,
                 Commission.is_test.is_(False), Commission.created_at >= lo,
                 Commission.created_at < hi]

    # "Your reviews": each product's views, helped and earned in the period.
    per: dict[uuid.UUID, dict] = {}
    for rid, n in db.execute(
            select(ReviewViewBucket.review_id,
                   func.coalesce(func.sum(ReviewViewBucket.view_count), 0))
            .where(ReviewViewBucket.review_id.in_(review_ids),
                   ReviewViewBucket.bucket_start >= lo, ReviewViewBucket.bucket_start < hi)
            .group_by(ReviewViewBucket.review_id)).all():
        per.setdefault(product_of[rid], {}).setdefault("views", 0)
        per[product_of[rid]]["views"] += int(n)
    for rid, n in db.execute(
            select(ReviewVote.review_id, func.count(func.distinct(ReviewVote.voter_id)))
            .where(ReviewVote.review_id.in_(review_ids), ReviewVote.vote == VoteDirection.up,
                   ReviewVote.created_at >= lo, ReviewVote.created_at < hi)
            .group_by(ReviewVote.review_id)).all():
        per.setdefault(product_of[rid], {}).setdefault("helped", 0)
        per[product_of[rid]]["helped"] += int(n)
    for rid, e in db.execute(
            select(Commission.review_id, func.coalesce(func.sum(Commission.reviewer_share), 0))
            .where(*in_period).group_by(Commission.review_id)).all():
        per.setdefault(product_of[rid], {}).setdefault("earned", ZERO)
        per[product_of[rid]]["earned"] += _money(e)
    out.products = [PerformanceProduct(
        product_id=p.product_id, name=p.name, image_url=p.image_url, reviews=p.reviews,
        views=per.get(p.product_id, {}).get("views", 0),
        helped=per.get(p.product_id, {}).get("helped", 0),
        earned=per.get(p.product_id, {}).get("earned", ZERO),
        published_at=p.published_at) for p in out.products]
    return out


def _has_earned(db: Session, uid: uuid.UUID) -> bool:
    commission = db.scalar(select(Commission.id).where(Commission.reviewer_id == uid).limit(1))
    if commission is not None:
        return True
    return db.scalar(select(HonestyFundDistribution.id)
                     .where(HonestyFundDistribution.reviewer_id == uid).limit(1)) is not None

"""Store insights and the store's CSV export (Figma Screen/Seller/Insights
8208:22905, Overlay/Store/Export 8213:23286).

Store reviews only (product figures are under Products). Every rating figure
is a median, as everywhere on Bluntly; the shares are plain proportions of the
period's reviews. "Since <month>" compares the newest month with the first
month of the period that has reviews; the period itself is compared with the
period of the same length before it.

The frame's "What buyers say about your store" themes need tagged store
reviews, which do not exist (a store review is free text): the screen says so
instead of inventing themes.

The export is the owner's own data: buyer names shortened, no contact details
and no order IDs (as the frame promises).
"""

from __future__ import annotations

import csv
import io
import statistics
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import NotFoundError
from app.models.qa import Answer, Question
from app.models.seller import Seller, SellerReview, SellerReviewAppeal
from app.models.user import User
from app.services.seller_service import PERIOD_DAYS, require_store_owner

MIN_STORE_REVIEWS = 5


def _owned(db: Session, seller_id: uuid.UUID, user: User) -> Seller:
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise NotFoundError("Seller not found.", code="seller_not_found")
    require_store_owner(seller, user)
    return seller


def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 2) if values else None


def _share(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


@dataclass
class Month:
    month: str
    reviews: int = 0
    rating: float | None = None
    recommend: float | None = None
    responded: float | None = None
    matched: float | None = None
    complete: float | None = None
    service: float | None = None
    packaging: float | None = None


@dataclass
class Peer:
    stores: int
    rating: float | None
    recommend: float | None
    packaging: float | None
    responded: float | None


@dataclass
class Insights:
    period: str
    reviews: int
    reviews_before: int
    rating: float | None
    recommend: float | None
    responded: float | None
    matched: float | None
    complete: float | None
    service: float | None
    packaging: float | None
    reply_hours: float | None
    reply_hours_first: float | None
    months: list[Month] = field(default_factory=list)
    peers: Peer | None = None
    platform: str = ""


def _month_keys(since: datetime, now: datetime) -> list[str]:
    keys, cur = [], since.astimezone(MANILA).replace(day=1)
    end = now.astimezone(MANILA)
    while (cur.year, cur.month) <= (end.year, end.month):
        keys.append(cur.strftime("%Y-%m"))
        cur = (cur + timedelta(days=32)).replace(day=1)
    return keys


def _summary(rows: list[SellerReview]) -> dict:
    return {
        "rating": _median([float(r.overall_rating) for r in rows]),
        "recommend": _share([r.would_recommend for r in rows]),
        "responded": _share([r.seller_response is not None for r in rows]),
        "matched": _share([r.accuracy for r in rows]),
        "complete": _share([r.order_completeness for r in rows]),
        "service": _median([float(r.customer_service) for r in rows]),
        "packaging": _median([float(r.packaging_quality) for r in rows]),
    }


def _reply_hours(rows: list[SellerReview]) -> float | None:
    hours = [(r.seller_response_at - r.created_at).total_seconds() / 3600
             for r in rows if r.seller_response_at is not None]
    return round(statistics.median(hours), 1) if hours else None


def _peers(db: Session, seller: Seller, since: datetime | None) -> Peer | None:
    """The median store on the same marketplace with 5+ store reviews in the
    period (stores carry no category, so "similar" is the marketplace)."""
    stmt = (select(SellerReview.seller_id, SellerReview.overall_rating,
                   SellerReview.would_recommend, SellerReview.packaging_quality,
                   SellerReview.seller_response)
            .join(Seller, Seller.id == SellerReview.seller_id)
            .where(Seller.platform == seller.platform, SellerReview.is_removed.is_(False)))
    if since is not None:
        stmt = stmt.where(SellerReview.created_at >= since)
    by: dict[uuid.UUID, list] = {}
    for sid, rating, rec, packaging, response in db.execute(stmt).all():
        by.setdefault(sid, []).append((float(rating), rec, float(packaging), response is not None))
    stores = [v for v in by.values() if len(v) >= MIN_STORE_REVIEWS]
    if not stores:
        return None
    return Peer(
        stores=len(stores),
        rating=_median([statistics.median([x[0] for x in s]) for s in stores]),
        recommend=_median([sum(x[1] for x in s) / len(s) for s in stores]),
        packaging=_median([statistics.median([x[2] for x in s]) for s in stores]),
        responded=_median([sum(x[3] for x in s) / len(s) for s in stores]))


def insights(db: Session, seller_id: uuid.UUID, user: User, period: str = "6m") -> Insights:
    """Menu/Store/Period like the Overview. "All time" has no earlier period to
    compare with, and its months start at the store's first review."""
    seller = _owned(db, seller_id, user)
    period = period if period in PERIOD_DAYS else "6m"
    days = PERIOD_DAYS[period]
    now = datetime.now(UTC)
    rows = list(db.scalars(select(SellerReview).where(
        SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False))
        .order_by(SellerReview.created_at)))
    if days is None:
        since = rows[0].created_at if rows else now
        current, earlier = rows, []
    else:
        since = now - timedelta(days=days)
        current = [r for r in rows if r.created_at >= since]
        earlier = [r for r in rows if since - timedelta(days=days) <= r.created_at < since]
    months = []
    for key in _month_keys(since, now):
        in_month = [r for r in current if r.created_at.astimezone(MANILA).strftime("%Y-%m") == key]
        months.append(Month(month=key, reviews=len(in_month), **_summary(in_month)))
    first = next((m for m in months if m.reviews), None)
    first_rows = [r for r in current if first and
                  r.created_at.astimezone(MANILA).strftime("%Y-%m") == first.month]
    s = _summary(current)
    return Insights(
        period=period, reviews=len(current),
        reviews_before=len(earlier), reply_hours=_reply_hours(current),
        reply_hours_first=_reply_hours(first_rows), months=months,
        peers=_peers(db, seller, since if days is not None else None),
        platform=getattr(seller.platform, "value", str(seller.platform)), **s)


# ------------------------------------------------------------------ export

def _short(user: User | None) -> str:
    """"Carla M." — a buyer's first name and initial, never more."""
    if user is None:
        return "A buyer"
    name = (user.display_name or user.username or "").replace("@", "").split()
    if not name:
        return "A buyer"
    return f"{name[0]} {name[1][0]}." if len(name) > 1 else name[0]


def _yn(value: bool | None) -> str:
    return "" if value is None else ("yes" if value else "no")


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def export(db: Session, seller_id: uuid.UUID, user: User, include: set[str],
           period: str = "6m") -> tuple[str, bytes]:
    """(filename, zip bytes) of the chosen CSVs for the period."""
    seller = _owned(db, seller_id, user)
    days = PERIOD_DAYS.get(period)
    since = datetime.now(UTC) - timedelta(days=days) if days else None
    files: dict[str, bytes] = {}

    def when(col):
        return [col >= since] if since is not None else []

    if "reviews" in include:
        reviews = db.execute(
            select(SellerReview, User).outerjoin(User, User.id == SellerReview.reviewer_id)
            .where(SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False),
                   *when(SellerReview.created_at))
            .order_by(SellerReview.created_at)).all()
        files["store-reviews.csv"] = _csv(
            ["date", "buyer", "overall", "matched_listing", "complete_order", "customer_service",
             "packaging", "would_recommend", "title", "comment", "your_response",
             "responded_at"],
            [[r.created_at.astimezone(MANILA).date().isoformat(), _short(u),
              float(r.overall_rating), _yn(r.accuracy), _yn(r.order_completeness),
              r.customer_service, r.packaging_quality, _yn(r.would_recommend), r.title or "",
              r.comment or "",
              r.seller_response or "",
              r.seller_response_at.astimezone(MANILA).isoformat() if r.seller_response_at else ""]
             for r, u in reviews])
    if "questions" in include:
        questions = db.execute(
            select(Question, User).outerjoin(User, User.id == Question.asker_id)
            .where(Question.seller_id == seller.id, Question.is_removed.is_(False),
                   *when(Question.created_at))
            .order_by(Question.created_at)).all()
        answers = {a.question_id: a for a in db.scalars(select(Answer).where(
            Answer.question_id.in_([q.id for q, _ in questions]),
            Answer.is_seller_answer.is_(True)))} if questions else {}
        counts = dict(db.execute(select(Answer.question_id, func.count()).where(
            Answer.question_id.in_([q.id for q, _ in questions])).group_by(Answer.question_id)
        ).all()) if questions else {}
        files["store-questions.csv"] = _csv(
            ["date", "asked_by", "question", "answers", "your_answer"],
            [[q.created_at.astimezone(MANILA).date().isoformat(), _short(u), q.body,
              counts.get(q.id, 0), answers[q.id].body if q.id in answers else ""]
             for q, u in questions])
    if "appeals" in include:
        appeals = db.scalars(select(SellerReviewAppeal).where(
            SellerReviewAppeal.seller_id == seller.id, *when(SellerReviewAppeal.created_at))
            .order_by(SellerReviewAppeal.created_at)).all()
        files["store-appeals.csv"] = _csv(
            ["date", "reason", "status", "decided_at", "decision_note"],
            [[a.created_at.astimezone(MANILA).date().isoformat(), a.reason, a.status,
              a.decided_at.astimezone(MANILA).date().isoformat() if a.decided_at else "",
              a.decision_note or ""] for a in appeals])
    if "products" in include:
        from app.services import store_product_service
        listed = store_product_service.list_for_store(db, seller.id, user)
        files["store-products.csv"] = _csv(
            ["product", "status", "reviews", "median_rating", "worth_it", "complicated",
             "not_worth_it", "change_30d", "questions", "open_questions"],
            [[r.name, r.status, r.figures.reviews, r.figures.median or "",
              r.figures.worth_it if r.figures.worth_it is not None else "",
              r.figures.complicated if r.figures.complicated is not None else "",
              r.figures.not_worth if r.figures.not_worth is not None else "",
              r.figures.change_30d if r.figures.change_30d is not None else "",
              r.figures.questions, r.figures.open_questions]
             for r in listed.rows if r.status == "approved"])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    stamp = datetime.now(MANILA).strftime("%Y%m%d")
    return f"bluntly-store-{stamp}.zip", out.getvalue()


def export_sizes(db: Session, seller_id: uuid.UUID, user: User, period: str = "6m") -> dict:
    """Row counts per file for the Export overlay ("128 rows")."""
    seller = _owned(db, seller_id, user)
    days = PERIOD_DAYS.get(period)
    since = datetime.now(UTC) - timedelta(days=days) if days else None

    def count(model, *where):
        stmt = select(func.count()).select_from(model).where(*where)
        if since is not None:
            stmt = stmt.where(model.created_at >= since)
        return int(db.scalar(stmt) or 0)

    from app.models.enums import StoreProductStatus
    from app.models.seller import StoreProduct
    return {
        "reviews": count(SellerReview, SellerReview.seller_id == seller.id,
                         SellerReview.is_removed.is_(False)),
        "questions": count(Question, Question.seller_id == seller.id,
                           Question.is_removed.is_(False)),
        "appeals": count(SellerReviewAppeal, SellerReviewAppeal.seller_id == seller.id),
        "products": int(db.scalar(select(func.count()).select_from(StoreProduct).where(
            StoreProduct.seller_id == seller.id,
            StoreProduct.status == StoreProductStatus.approved)) or 0),
    }

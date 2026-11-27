"""Report 3 — the Seller Rating Summary.

What buyers said about one store over a period, for the store's approved owner
(and staff). Read from `seller_reviews`, which stores FR-4's FOUR dimensions:

    accuracy             yes/no  matched the listing
    order_completeness   yes/no  nothing missing
    customer_service     1-5
    packaging_quality    1-5

plus `overall_rating` (0-5 in half steps) and `would_recommend` (yes/no).
Recommendation rate is therefore a stored answer, never inferred from stars.

AGGREGATION. The approved seller aggregate is the MEDIAN (Business Rules §10),
computed by `seller_service.summarize_reviews` — the same function the public
store page uses, so the report and the page cannot disagree. The arithmetic
mean is shown beside it for reference and labelled as such. Yes/no dimensions
are the share of "yes".

Removed reviews are excluded, as they are from the public page. The order ID a
reviewer self-reports is private and never part of this report.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.seller import Seller, SellerReview
from app.models.user import User
from app.schemas.reporting import (
    RatingDimension,
    ReportMeta,
    ReportPeriod,
    SellerRatingRow,
    SellerRatingStore,
    SellerRatingSummaryBlock,
    SellerRatingSummaryOut,
)
from app.services.reporting.common import Column, Table
from app.services.reporting.periods import Period
from app.services.seller_service import summarize_reviews

TITLE = "Seller Rating Summary"
MAX_ROWS = 2000

_COLUMNS = (SellerReview.id, SellerReview.created_at, SellerReview.title,
            SellerReview.overall_rating, SellerReview.customer_service,
            SellerReview.packaging_quality, SellerReview.accuracy,
            SellerReview.order_completeness, SellerReview.would_recommend,
            SellerReview.seller_response, User.username)


def _mean(rows, attribute: str) -> float | None:
    if not rows:
        return None
    total = sum(Decimal(str(getattr(r, attribute))) for r in rows)
    return round(float(total / len(rows)), 2)


def _block(rows) -> SellerRatingSummaryBlock:
    s = summarize_reviews(rows)
    count = s.review_count
    return SellerRatingSummaryBlock(
        review_count=count,
        overall_median=s.overall_average,
        overall_mean=_mean(rows, "overall_rating"),
        recommendation_rate=s.recommend_rate,
        distribution={str(k): v for k, v in s.rating_distribution.items()},
        dimensions=[
            RatingDimension(key="accuracy", label="Item matched the listing", kind="yes_no",
                            rate=s.accuracy_rate, answered=count),
            RatingDimension(key="order_completeness", label="Order was complete",
                            kind="yes_no", rate=s.order_completeness_rate, answered=count),
            RatingDimension(key="customer_service", label="Customer service", kind="graded",
                            median=s.customer_service_average,
                            mean=_mean(rows, "customer_service"), answered=count),
            RatingDimension(key="packaging_quality", label="Packaging", kind="graded",
                            median=s.packaging_quality_average,
                            mean=_mean(rows, "packaging_quality"), answered=count),
        ],
        responded=sum(1 for r in rows if r.seller_response),
    )


def build(db: Session, seller: Seller, period: Period, *,
          now: datetime | None = None) -> SellerRatingSummaryOut:
    now = now or datetime.now(UTC)
    base = (select(*_COLUMNS)
            .outerjoin(User, User.id == SellerReview.reviewer_id)
            .where(SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False)))
    all_rows = db.execute(base.order_by(SellerReview.created_at)).all()
    in_period = [r for r in all_rows
                 if period.starts_at <= r.created_at < period.ends_before]
    truncated = len(in_period) > MAX_ROWS

    rows = [SellerRatingRow(
        seller_review_id=r.id, created_at=r.created_at,
        reviewer=f"@{r.username}" if r.username else None, title=r.title,
        overall_rating=r.overall_rating, customer_service=r.customer_service,
        packaging_quality=r.packaging_quality, accuracy=r.accuracy,
        order_completeness=r.order_completeness, would_recommend=r.would_recommend,
        has_store_response=bool(r.seller_response))
        for r in in_period[:MAX_ROWS]]

    notes = ["Overall and graded dimensions are MEDIANS, the approved seller aggregate "
             "(Business Rules §10). Means are shown for reference only.",
             "Recommendation rate is the share of reviewers who answered "
             "\"would recommend\" — a stored answer, not derived from stars.",
             "Removed reviews are excluded, as on the public store page."]
    return SellerRatingSummaryOut(
        meta=ReportMeta(title=TITLE, period=ReportPeriod(**period.as_dict()), generated_at=now,
                        notes=notes),
        seller=SellerRatingStore(id=seller.id, display_name=seller.display_name,
                                 platform=seller.platform.value,
                                 claim_status=seller.claim_status.value),
        period_summary=_block(in_period),
        all_time_summary=_block(all_rows),
        rows=rows, rows_truncated=truncated)


def csv_tables(report: SellerRatingSummaryOut) -> dict[str, Table]:
    return {"reviews": Table("reviews", [
        Column("created_at", "Date", "datetime"),
        Column("reviewer", "Reviewer"),
        Column("title", "Title"),
        Column("overall_rating", "Overall rating", "number"),
        Column("customer_service", "Customer service", "number"),
        Column("packaging_quality", "Packaging", "number"),
        Column("accuracy", "Matched listing", "bool"),
        Column("order_completeness", "Complete order", "bool"),
        Column("would_recommend", "Would recommend", "bool"),
        Column("has_store_response", "Store responded", "bool"),
    ], [r.model_dump() for r in report.rows])}

"""All Reviews: every review that still exists, for staff (QA, 2026-09-29).

The Review Queue holds work, not inventory: reviews awaiting an earnings
decision, and take-downs. Under Post-Seeding (the deployed default) a brand-new
review joins it only once its trust-weighted votes pass the §2 gate, so a
review written a minute ago is, correctly, not in it. That is what QA saw as
"the queue does not fetch the new review". This list shows every review, new
ones included, with its current counts and both Wilson figures.

A page costs five queries whatever its size: the page, the count, and one batch
each for gate votes, take-downs and open reports. Nothing here queries per row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationTargetType,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.schemas.all_reviews import (
    AllReviewAuthor,
    AllReviewGate,
    AllReviewProduct,
    AllReviewRow,
    AllReviewsPage,
    AllReviewsSort,
    ReviewState,
)
from app.services import earn_gate
from app.services.ranking import GATE_MIN_STAGE2_VOTERS, GATE_WILSON_LB

MAX_LIMIT = 100


@dataclass(frozen=True)
class AllReviewsQuery:
    q: str | None = None
    state: ReviewState | None = None
    earn: EarnEligibleStatus | None = None
    product_id: uuid.UUID | None = None
    created_from: date | None = None
    created_to: date | None = None
    sort: AllReviewsSort = "newest"
    limit: int = 50
    offset: int = 0


def _state_clause(state: ReviewState):
    if state == "deleted_by_author":
        return Review.removed_by_author_at.isnot(None)
    if state == "removed":
        return and_(Review.is_removed.is_(True), Review.removed_by_author_at.is_(None))
    if state == "taken_down":
        return and_(Review.published_at.is_(None), Review.is_removed.is_(False))
    return and_(Review.published_at.isnot(None), Review.is_removed.is_(False))


def _state_of(review: Review) -> ReviewState:
    if review.removed_by_author_at is not None:
        return "deleted_by_author"
    if review.is_removed:
        return "removed"
    if review.published_at is None:
        return "taken_down"
    return "published"


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filtered(query: AllReviewsQuery, author: type[User]) -> Select:
    # The author's four public columns, never the whole row: a users row also
    # holds the email, password hash, wallet and payout account.
    stmt = (select(Review, Product.canonical_name, Product.image_url, author.id, author.username,
                   author.display_name, author.trust_stage)
            .join(Product, Product.id == Review.product_id)
            .outerjoin(author, author.id == Review.author_id))
    if query.q and query.q.strip():
        pattern = _like(query.q.strip())
        stmt = stmt.where(or_(
            Review.title.ilike(pattern, escape="\\"),
            Review.discussion.ilike(pattern, escape="\\"),
            Product.canonical_name.ilike(pattern, escape="\\"),
            author.username.ilike(pattern, escape="\\"),
            Review.review_id.ilike(pattern, escape="\\"),
        ))
    if query.state is not None:
        stmt = stmt.where(_state_clause(query.state))
    if query.earn is not None:
        stmt = stmt.where(Review.earn_eligible_status == query.earn)
    if query.product_id is not None:
        stmt = stmt.where(Review.product_id == query.product_id)
    # Dates are whole days in UTC, both ends inclusive.
    if query.created_from is not None:
        stmt = stmt.where(Review.created_at >= datetime.combine(query.created_from, time.min)
                          .replace(tzinfo=UTC))
    if query.created_to is not None:
        stmt = stmt.where(Review.created_at < datetime.combine(
            query.created_to + timedelta(days=1), time.min).replace(tzinfo=UTC))
    return stmt


_ORDER = {
    # The id breaks every tie, so the same filter always pages the same way.
    # Each pair is the exact reverse of the other, so one index serves both
    # directions (migration 0068).
    "newest": (Review.created_at.desc(), Review.id.desc()),
    "oldest": (Review.created_at.asc(), Review.id.asc()),
    "wilson_desc": (Review.wilson_score.desc(), Review.created_at.desc(), Review.id.desc()),
    "wilson_asc": (Review.wilson_score.asc(), Review.created_at.asc(), Review.id.asc()),
}


def list_reviews(db: Session, query: AllReviewsQuery) -> AllReviewsPage:
    limit = max(1, min(query.limit, MAX_LIMIT))
    offset = max(0, query.offset)
    author = aliased(User)
    base = _filtered(query, author)
    total = int(db.scalar(select(func.count()).select_from(
        base.with_only_columns(Review.id).subquery())) or 0)
    rows = db.execute(base.order_by(*_ORDER[query.sort]).limit(limit).offset(offset)).all()

    ids = [row[0].id for row in rows]
    gates = earn_gate.gate_states(db, ids)
    taken_down: set[uuid.UUID] = set()
    open_reports: dict[uuid.UUID, int] = {}
    if ids:
        taken_down = set(db.scalars(
            select(ModerationLog.target_ref).where(
                ModerationLog.action == ModerationAction.unpublish,
                ModerationLog.target_ref.in_(ids)).distinct()))
        open_reports = dict(db.execute(
            select(ModerationLog.target_ref, func.count())
            .where(ModerationLog.action == ModerationAction.report,
                   ModerationLog.target_type == ModerationTargetType.review,
                   ModerationLog.target_ref.in_(ids),
                   ModerationLog.resolution.is_(None))
            .group_by(ModerationLog.target_ref)).all())

    items = []
    for review, product_name, product_image, author_id, username, display_name, trust_stage in rows:
        gate = gates[review.id]
        items.append(AllReviewRow(
            id=review.id,
            reference=review.review_id,
            title=review.title,
            star_rating=review.star_rating,
            verdict=review.verdict,
            state=_state_of(review),
            earn_eligible_status=review.earn_eligible_status,
            in_review_queue=_in_review_queue(review, review.id in taken_down),
            is_thread_root=review.is_thread_root,
            helpful_votes=review.helpful_votes,
            unhelpful_votes=review.unhelpful_votes,
            wilson_score=review.wilson_score,
            gate=AllReviewGate(
                wilson_lower_bound=gate.wilson_lower_bound,
                effective_total=gate.effective_total,
                stage2_plus_voters=gate.stage2_plus_voters,
                passes=gate.passes,
            ),
            open_reports=int(open_reports.get(review.id, 0)),
            author=(AllReviewAuthor(id=author_id, username=username,
                                    display_name=display_name, trust_stage=trust_stage)
                    if author_id is not None else None),
            product=AllReviewProduct(id=review.product_id, canonical_name=product_name,
                                     image_url=product_image),
            created_at=review.created_at,
            published_at=review.published_at,
        ))
    return AllReviewsPage(items=items, total=total, limit=limit, offset=offset,
                          earn_gate_phase=earn_gate.current_phase(db),
                          gate_threshold=GATE_WILSON_LB,
                          gate_min_stage2_voters=GATE_MIN_STAGE2_VOTERS)


def _in_review_queue(review: Review, taken_down: bool) -> bool:
    """The Review Queue's membership rule (`referral_service._all_queue_candidates`),
    for one row: awaiting a first earnings decision, or taken down by staff."""
    if review.is_removed:
        return False
    if review.published_at is None and taken_down:
        return True
    return (review.earn_eligible_status == EarnEligibleStatus.pending
            and (review.published_at is not None or not taken_down))


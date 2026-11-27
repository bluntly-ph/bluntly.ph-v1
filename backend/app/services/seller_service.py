"""Seller service (FR-4).

The rules that decide whether a seller is a duplicate, and what a store's
public numbers say, are plain functions so they are tested on every machine
(`tests/test_seller_rules.py`). The database-backed flow below is tested in
`tests/test_sellers_api.py`.

Two integrity rules carry the weight here, both refusals of self-dealing in the
same shape as `self_report` and Q&A's `cannot_pick_own_answer`:

* a store's claimed owner cannot rate their own store;
* a moderator cannot decide a claim they submitted themselves, nor remove a
  rating of a store they run or a rating they wrote.

Claiming never grants ownership by itself. FR-4 limits seller verification to a
moderator cross-checking the store name against the public listing, so a claim
stays `pending` until a moderator decides it.

Seller reviews publish without the product-review gate (DEVIATIONS §37), so
removal after the fact is the moderation hook, and every public read — the
review list, the summary, the review count in search — filters removed rows.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Float, cast, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    Platform,
    SellerClaimStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.qa import Answer, Question, QuestionSubscription
from app.models.seller import Seller, SellerClaim, SellerReview, SellerReviewAppeal
from app.models.user import User
from app.schemas.qa import QAAuthor
from app.schemas.seller import (
    ClaimDecision,
    SellerAppealOut,
    SellerClaimCreate,
    SellerClaimOut,
    SellerCreate,
    SellerDashboardOut,
    SellerDetailOut,
    SellerOut,
    SellerReplyOut,
    SellerReviewCreate,
    SellerReviewOut,
    SellerSummary,
    StoreAnswerOut,
    StoreQuestionOut,
    WaitingQuestion,
)
from app.services import notification_service

_WHITESPACE = re.compile(r"\s+")

#: The one predicate every public read of seller reviews shares.
_VISIBLE = SellerReview.is_removed.is_(False)


def normalize_seller_name(name: str) -> str:
    """The key the `(platform, normalized_name)` uniqueness constraint sees.

    Casefolded with every run of whitespace collapsed to one space, so a
    reviewer typing "Anker  Official Store " finds the existing store instead
    of creating a second one and splitting its rating in half.
    """
    collapsed = _WHITESPACE.sub(" ", name).strip().casefold()
    if not collapsed:
        raise ValueError("A seller needs a name.")
    return collapsed


def summarize_reviews(reviews: Iterable[Any]) -> SellerSummary:
    """Aggregate seller reviews into the public summary.

    Rates are the share of positive answers; averages are the mean of the
    graded dimensions, rounded for display. With no reviews every rate and
    average is None rather than zero — see SellerSummary.
    """
    rows = list(reviews)
    count = len(rows)
    # Five bars, as the store page draws them. Ratings are half steps since
    # 0048, so a 4.5 belongs to a bar rather than to a key of its own: each
    # rating counts in the star at or below it, and a 0 (a real answer) counts
    # in the first bar because there is no zero bar to put it in.
    distribution = {star: 0 for star in range(1, 6)}
    for row in rows:
        bar = max(1, min(5, int(row.overall_rating)))
        distribution[bar] += 1
    if count == 0:
        return SellerSummary(review_count=0, rating_distribution=distribution)

    def rate(attribute: str) -> float:
        return round(sum(1 for row in rows if getattr(row, attribute)) / count, 4)

    def mean(attribute: str) -> float:
        # Business Rules §10: the seller aggregate "uses the same median-based
        # approach as product ratings, for the same manipulation-resistance
        # reasons". Named `mean` for its callers; it is a median.
        values = sorted(float(getattr(row, attribute)) for row in rows)
        mid = len(values) // 2
        median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
        return round(median, 2)

    return SellerSummary(
        review_count=count,
        accuracy_rate=rate("accuracy"),
        order_completeness_rate=rate("order_completeness"),
        recommend_rate=rate("would_recommend"),
        customer_service_average=mean("customer_service"),
        packaging_quality_average=mean("packaging_quality"),
        overall_average=mean("overall_rating"),
        rating_distribution=distribution,
    )


# ---------------------------------------------------------------- sellers

def _by_key(db: Session, platform: Platform, key: str) -> Seller | None:
    return db.scalar(
        select(Seller).where(Seller.platform == platform, Seller.normalized_name == key)
    )


def find_or_create_seller(db: Session, payload: SellerCreate) -> tuple[Seller, bool]:
    """Return the store, creating it only if no matching one exists.

    The second element says whether a row was created. Two reviewers adding
    the same store at the same moment both reach the INSERT; the unique
    constraint refuses the second, and that caller is handed the first's row
    rather than an error.
    """
    try:
        key = normalize_seller_name(payload.display_name)
    except ValueError as exc:
        raise AppError(str(exc), code="seller_name_blank", status_code=422,
                       title="Invalid seller") from exc

    existing = _by_key(db, payload.platform, key)
    if existing is not None:
        return existing, False

    seller = Seller(
        display_name=_WHITESPACE.sub(" ", payload.display_name).strip(),
        normalized_name=key,
        platform=payload.platform,
        store_url=payload.store_url,
    )
    db.add(seller)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _by_key(db, payload.platform, key)
        if existing is None:
            raise
        return existing, False
    db.refresh(seller)
    return seller, True


def get_seller_or_404(db: Session, seller_id: uuid.UUID) -> Seller:
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise NotFoundError("Seller not found.")
    return seller


def _answered_questions():
    """Per store: its live questions that have at least one answer."""
    answered = select(Answer.question_id)
    return (
        select(Question.seller_id, func.count(Question.id).label("answered"))
        .where(Question.seller_id.isnot(None), Question.is_removed.is_(False),
               Question.id.in_(answered))
        .group_by(Question.seller_id)
        .subquery()
    )


def answered_question_count(db: Session, seller_id: uuid.UUID) -> int:
    answered = _answered_questions()
    return int(db.scalar(select(answered.c.answered)
                         .where(answered.c.seller_id == seller_id)) or 0)


#: MQA-033's ranking. A store's score is the Wilson lower bound (95%) of the
#: share of its visible reviews that are positive (4 stars or more) - so three
#: 5-star reviews rank below thirty mostly-5-star ones, and one review proves
#: little - plus up to RECENT_BONUS for reviews in the last RECENT_DAYS, capped
#: at RECENT_CAP of them so activity nudges the order without outweighing the
#: evidence. A store with no reviews scores 0 and sorts by name among its peers.
RANK_POSITIVE_AT = 4
RANK_Z = 1.96
RECENT_DAYS = 90
RECENT_CAP = 5
RECENT_BONUS = 0.1


def seller_rank_score(n: int, positive: int, recent: int) -> float:
    """The ranked order's score, in Python (the SQL below computes the same)."""
    if n <= 0:
        return 0.0
    z, p = RANK_Z, positive / n
    lower = (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) \
        / (1 + z * z / n)
    return lower + RECENT_BONUS * min(recent, RECENT_CAP) / RECENT_CAP


#: "Answers buyers" (Sheet/Filter sellers 8462:36591): the store's median time
#: from a buyer's question to the store's own first answer.
ANSWER_WINDOWS = {"day": timedelta(days=1), "week": timedelta(days=7)}


def _store_answer_times():
    """Per store: the median seconds from a question to the store's first own
    answer (is_seller_answer), over the questions it answered. Unanswered
    questions do not count; a store that never answers has no row."""
    first = (select(Answer.question_id, func.min(Answer.created_at).label("at"))
             .where(Answer.is_seller_answer.is_(True))
             .group_by(Answer.question_id)
             .subquery())
    waited = func.extract("epoch", first.c.at - Question.created_at)
    return (select(Question.seller_id,
                   func.percentile_cont(0.5).within_group(waited.asc()).label("median_s"))
            .join(first, first.c.question_id == Question.id)
            .where(Question.seller_id.isnot(None), Question.is_removed.is_(False))
            .group_by(Question.seller_id)
            .subquery())


def _sellers_stmt(*, q: str | None, platform: Platform | None, claimed: bool | None,
                  min_rating: int | None, answers_within: str | None):
    """The Sellers tab's query, unordered: the list and its count share it, so
    "Show 24 sellers" never disagrees with the list."""
    since = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    counts = (
        select(SellerReview.seller_id,
               func.count(SellerReview.id).label("n"),
               func.count(SellerReview.id).filter(
                   SellerReview.overall_rating >= RANK_POSITIVE_AT).label("positive"),
               func.count(SellerReview.id).filter(
                   SellerReview.created_at >= since).label("recent"),
               func.percentile_cont(0.5).within_group(
                   SellerReview.overall_rating.asc()).label("average"))
        .where(_VISIBLE)
        .group_by(SellerReview.seller_id)
        .subquery()
    )
    answered = _answered_questions()
    n = func.coalesce(counts.c.n, 0)
    stmt = (select(Seller, n, counts.c.average, func.coalesce(answered.c.answered, 0))
            .outerjoin(counts, counts.c.seller_id == Seller.id)
            .outerjoin(answered, answered.c.seller_id == Seller.id))
    if platform is not None:
        stmt = stmt.where(Seller.platform == platform)
    if claimed is True:
        stmt = stmt.where(Seller.claim_status == SellerClaimStatus.claimed)
    elif claimed is False:
        stmt = stmt.where(Seller.claim_status != SellerClaimStatus.claimed)
    if min_rating is not None:
        # The same figure the card shows (overall_average); no reviews, no rating.
        stmt = stmt.where(counts.c.average >= min_rating)
    if answers_within is not None:
        times = _store_answer_times()
        stmt = stmt.join(times, times.c.seller_id == Seller.id).where(
            times.c.median_s <= ANSWER_WINDOWS[answers_within].total_seconds())
    if q:
        needle = _WHITESPACE.sub(" ", q).strip().casefold()
        if needle:
            stmt = stmt.where(Seller.normalized_name.contains(needle, autoescape=True))
    return stmt, counts, n


def list_sellers(db: Session, *, q: str | None, platform: Platform | None,
                 limit: int, claimed_only: bool = False,
                 sort: str = "ranked", claimed: bool | None = None,
                 min_rating: int | None = None,
                 answers_within: str | None = None) -> list[SellerOut]:
    """Store search. `platform`, `claimed` and `sort` are the Sellers tab's
    filter and order (QA-052): "ranked" (the default, MQA-033: the
    best-evidenced stores first, see `seller_rank_score`), "reviews" (the
    most-reviewed first) or "name". `claimed` is Sheet/Filter sellers' Profile:
    true claimed only, false unclaimed only (`claimed_only` is the older spelling
    of true). `min_rating` (3 or 4) and `answers_within` ("day" or "week") are
    its Rating and Answers buyers (2026-10-07)."""
    stmt, counts, n = _sellers_stmt(q=q, platform=platform,
                                    claimed=True if claimed_only else claimed,
                                    min_rating=min_rating, answers_within=answers_within)
    if sort == "ranked":
        # NULL for a store with no reviews (no division by zero); scored 0 below.
        nn = func.nullif(cast(func.coalesce(counts.c.n, 0), Float), 0)
        p = cast(func.coalesce(counts.c.positive, 0), Float) / nn
        z = RANK_Z
        lower = (p + z * z / (2 * nn) - z * func.sqrt((p * (1 - p) + z * z / (4 * nn)) / nn)) \
            / (1 + z * z / nn)
        bonus = RECENT_BONUS * func.least(func.coalesce(counts.c.recent, 0), RECENT_CAP) \
            / float(RECENT_CAP)
        score = func.coalesce(lower + bonus, 0.0)
        order = (score.desc(), n.desc(), Seller.display_name, Seller.id)
    elif sort == "reviews":
        order = (n.desc(), Seller.display_name, Seller.id)
    else:
        order = (Seller.display_name, Seller.id)
    stmt = stmt.order_by(*order).limit(limit)
    return [
        SellerOut.model_validate(seller).model_copy(update={
            "review_count": count,
            "overall_average": None if average is None else round(float(average), 2),
            "answered_question_count": answered_n,
        })
        for seller, count, average, answered_n in db.execute(stmt).all()
    ]


def count_sellers(db: Session, *, q: str | None, platform: Platform | None,
                  claimed: bool | None = None, min_rating: int | None = None,
                  answers_within: str | None = None) -> int:
    """How many stores `list_sellers` would find with these filters."""
    stmt, _, _ = _sellers_stmt(q=q, platform=platform, claimed=claimed,
                               min_rating=min_rating, answers_within=answers_within)
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def get_seller_detail(db: Session, seller_id: uuid.UUID) -> SellerDetailOut:
    seller = get_seller_or_404(db, seller_id)
    reviews = db.scalars(
        select(SellerReview).where(SellerReview.seller_id == seller.id, _VISIBLE)
    ).all()
    summary = summarize_reviews(reviews)
    data = SellerOut.model_validate(seller).model_dump()
    data["review_count"] = summary.review_count
    data["overall_average"] = summary.overall_average
    data["answered_question_count"] = answered_question_count(db, seller.id)
    under_review = db.scalar(select(SellerClaim.id).where(
        SellerClaim.seller_id == seller.id,
        SellerClaim.status == SellerClaimStatus.pending).limit(1)) is not None
    return SellerDetailOut(**data, summary=summary, claim_under_review=under_review)


# ------------------------------------------------------------ dashboard

#: Months of review volume on the owner's dashboard.
DASHBOARD_MONTHS = 6


def monthly_volume(reviews: Iterable[Any], *, months: int = DASHBOARD_MONTHS,
                   today: date | None = None) -> list[dict]:
    """Reviews per Manila calendar month, zero-filled, oldest first.

    A month with no reviews is a zero rather than a missing entry, so a chart
    drawn from this cannot silently close the gap and imply steady volume.
    """
    current = today or datetime.now(MANILA).date()
    keys: list[str] = []
    year, month = current.year, current.month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    keys.reverse()
    counts = dict.fromkeys(keys, 0)
    for row in reviews:
        local = row.created_at.astimezone(MANILA)
        key = f"{local.year:04d}-{local.month:02d}"
        if key in counts:
            counts[key] += 1
    return [{"month": key, "count": counts[key]} for key in keys]


def _require_owner(seller: Seller, user: User) -> None:
    """The approved owner only. A pending claim is a request, not ownership."""
    if seller.claim_status != SellerClaimStatus.claimed or seller.claimed_by_id != user.id:
        raise ForbiddenError("Only the store's approved owner can open its dashboard.",
                             code="not_store_owner")


#: Public name for the owner test, shared by the dashboard and the rating report.
require_store_owner = _require_owner


def list_my_stores(db: Session, user: User) -> list[SellerDetailOut]:
    """Stores this account runs: claims a moderator approved, nothing pending."""
    stores = db.scalars(
        select(Seller)
        .where(Seller.claimed_by_id == user.id,
               Seller.claim_status == SellerClaimStatus.claimed)
        .order_by(Seller.display_name)
    ).all()
    return [get_seller_detail(db, store.id) for store in stores]


#: Menu/Store/Period: how far back the Overview's tiles and breakdown look.
PERIOD_DAYS = {"30d": 30, "3m": 91, "6m": 182, "12m": 365, "all": None}


def get_dashboard(db: Session, seller_id: uuid.UUID, user: User,
                  period: str = "6m") -> SellerDashboardOut:
    """Review monitoring for the store's approved owner (FR-4).

    Everything here is already public on the store page except the waiting
    list's framing: which store questions have no answer from the store yet,
    oldest first, because those are the ones the owner is expected to act on.
    """
    seller = get_seller_or_404(db, seller_id)
    _require_owner(seller, user)

    reviews = db.scalars(
        select(SellerReview).where(SellerReview.seller_id == seller.id, _VISIBLE)
    ).all()
    answered_by_store = select(Answer.question_id).where(Answer.is_seller_answer.is_(True))
    waiting = select(Question).where(
        Question.seller_id == seller.id,
        Question.is_removed.is_(False),
        Question.id.not_in(answered_by_store),
    )
    unanswered = db.scalar(select(func.count()).select_from(waiting.subquery())) or 0
    oldest_first = db.execute(
        select(Question, User.display_name, User.username)
        .outerjoin(User, User.id == Question.asker_id)
        .where(Question.id.in_(waiting.with_only_columns(Question.id)))
        .order_by(Question.created_at).limit(20)).all()

    from app.services import seller_dashboard
    analytics, review_rows, activity, waiting_reviews = seller_dashboard.build(db, seller)
    days = PERIOD_DAYS.get(period, PERIOD_DAYS["6m"])
    since = datetime.now(UTC) - timedelta(days=days) if days else None
    in_period = [r for r in reviews if since is None or r.created_at >= since]
    return SellerDashboardOut(
        seller=get_seller_detail(db, seller.id),
        monthly_volume=monthly_volume(reviews),
        unanswered_questions=unanswered,
        waiting_questions=[
            WaitingQuestion(id=q.id, body=q.body, created_at=q.created_at,
                            asker=name or (f"@{handle}" if handle else None))
            for q, name, handle in oldest_first
        ],
        analytics=analytics,
        reviews=review_rows,
        waiting_reviews=waiting_reviews,
        recent_activity=activity,
        period=period if period in PERIOD_DAYS else "6m",
        period_summary=summarize_reviews(in_period),
    )


# ---------------------------------------------------------------- reviews

def _review_out(review: SellerReview, reviewer: User | None) -> SellerReviewOut:
    return SellerReviewOut(
        id=review.id,
        seller_id=review.seller_id,
        product_id=review.product_id,
        title=review.title,
        accuracy=review.accuracy,
        order_completeness=review.order_completeness,
        customer_service=review.customer_service,
        packaging_quality=review.packaging_quality,
        overall_rating=review.overall_rating,
        would_recommend=review.would_recommend,
        comment=review.comment,
        photo_urls=list(review.photo_urls or []),
        is_removed=bool(review.is_removed),
        reviewer=QAAuthor.model_validate(reviewer) if reviewer is not None else None,
        created_at=review.created_at,
        seller_response=review.seller_response,
        seller_response_at=review.seller_response_at,
        seller_response_edited_at=review.seller_response_edited_at,
        order_id_provided=bool(review.order_id),
    )


def create_seller_review(db: Session, seller: Seller, reviewer: User,
                         payload: SellerReviewCreate) -> SellerReviewOut:
    if seller.claimed_by_id is not None and seller.claimed_by_id == reviewer.id:
        raise AppError("You cannot rate a store you run.", code="self_review",
                       status_code=422, title="Invalid seller review")
    if reviewer.is_claimed_seller:
        # §9: a claimed seller account never submits reviews, on anything.
        raise ForbiddenError("A claimed seller account can't submit reviews.",
                             code="seller_cannot_review")

    duplicate = AppError("You have already rated this store.",
                         code="seller_review_exists", status_code=409,
                         title="Seller review exists")
    already = db.scalar(select(SellerReview.id).where(
        SellerReview.seller_id == seller.id, SellerReview.reviewer_id == reviewer.id))
    if already is not None:
        raise duplicate

    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise NotFoundError("Product not found.")

    review = SellerReview(
        seller_id=seller.id,
        reviewer_id=reviewer.id,
        product_id=payload.product_id,
        title=(payload.title or "").strip() or None,
        accuracy=payload.accuracy,
        order_completeness=payload.order_completeness,
        customer_service=payload.customer_service,
        packaging_quality=payload.packaging_quality,
        overall_rating=payload.overall_rating,
        would_recommend=payload.would_recommend,
        comment=payload.comment,
        photo_urls=list(payload.photo_urls),
        # §10: self-reported, no upfront check; only an appeal ever reads it.
        order_id=payload.order_id,
    )
    db.add(review)
    # The store's approved owner hears of every new review of it (Seller console
    # Overlay/Store/Notifications, "New 2★ review"), in the same transaction.
    if seller.claim_status == SellerClaimStatus.claimed and seller.claimed_by_id is not None:
        rating = float(payload.overall_rating)
        notification_service.notify(
            db, seller.claimed_by_id, "store_review_new",
            f"New {int(rating) if rating.is_integer() else rating}★ review",
            body=f"{reviewer.display_name or reviewer.username or 'A buyer'}"
                 f"{' · ' + review.title if review.title else ''}",
            link=f"/seller/{seller.id}/reviews", rating=rating)
    try:
        db.commit()
    except IntegrityError as exc:
        # The service check above loses a race; `uq_seller_review_once` does not.
        db.rollback()
        raise duplicate from exc
    db.refresh(review)
    return _review_out(review, reviewer)


def list_seller_reviews(db: Session, seller_id: uuid.UUID, limit: int,
                        viewer_id: uuid.UUID | None = None, *,
                        offset: int = 0) -> list[SellerReviewOut]:
    """Newest first, one page at a time (`offset`). The id breaks ties, so a
    review is never on two pages or none."""
    from app.services import seller_review_engagement as engagement

    get_seller_or_404(db, seller_id)
    rows = db.execute(
        select(SellerReview, User)
        .outerjoin(User, User.id == SellerReview.reviewer_id)
        .where(SellerReview.seller_id == seller_id, _VISIBLE)
        .order_by(SellerReview.created_at.desc(), SellerReview.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    ids = [review.id for review, _ in rows]
    votes = engagement.counts(db, ids)
    mine = engagement.my_votes(db, viewer_id, ids)
    replies = engagement.replies_for(db, ids)
    reply_counts = engagement.reply_counts(db, ids)
    out = []
    for review, reviewer in rows:
        item = _review_out(review, reviewer)
        item.helpful_votes, item.unhelpful_votes = votes.get(review.id, (0, 0))
        item.my_vote = mine.get(review.id)
        item.replies = [SellerReplyOut(**r) for r in replies.get(review.id, [])]
        item.reply_count = reply_counts.get(review.id, 0)
        out.append(item)
    return out


def remove_seller_review(db: Session, review_id: uuid.UUID, moderator: User,
                         note: str | None) -> SellerReviewOut:
    """Take a rating off the store's page and out of its numbers.

    A flag, not a delete: the row stays for the audit trail, and the unique
    constraint keeps the same reviewer from simply posting it again.
    """
    review = db.get(SellerReview, review_id, with_for_update=True)
    if review is None:
        raise NotFoundError("Seller review not found.")
    seller = db.get(Seller, review.seller_id)
    if review.reviewer_id == moderator.id or (
            seller is not None and seller.claimed_by_id == moderator.id):
        raise AppError("You cannot moderate a rating you wrote or a store you run.",
                       code="self_decision", status_code=422, title="Invalid decision")
    if review.is_removed:
        raise AppError("This seller review has already been removed.",
                       code="seller_review_already_removed", status_code=409,
                       title="Seller review already removed")

    review.is_removed = True
    review.removed_at = datetime.now(UTC)
    review.removed_by_id = moderator.id
    review.removal_note = note
    notification_service.notify(
        db, review.reviewer_id, "seller_review_removed",
        "An administrator removed your seller review",
        body=note, link=f"/sellers/{review.seller_id}")
    db.commit()
    db.refresh(review)
    reviewer = db.get(User, review.reviewer_id) if review.reviewer_id else None
    return _review_out(review, reviewer)


# ----------------------------------------------------------------- claims

def _claim_out(claim: SellerClaim, seller: Seller | None) -> SellerClaimOut:
    return SellerClaimOut(
        id=claim.id,
        seller_id=claim.seller_id,
        seller_display_name=seller.display_name if seller is not None else None,
        status=claim.status,
        evidence=claim.evidence,
        decision_note=claim.decision_note,
        created_at=claim.created_at,
        decided_at=claim.decided_at,
        registration_kind=claim.registration_kind,
        registration_number=claim.registration_number,
        registered_business_name=claim.registered_business_name,
        marketplace_shop_name=claim.marketplace_shop_name,
        shop_name_matches=(
            None if not claim.marketplace_shop_name or seller is None
            else normalize_seller_name(claim.marketplace_shop_name) == seller.normalized_name),
    )


def submit_claim(db: Session, seller: Seller, user: User,
                 payload: SellerClaimCreate) -> SellerClaimOut:
    if seller.claim_status == SellerClaimStatus.claimed:
        raise AppError("This store has already been claimed.",
                       code="seller_already_claimed", status_code=409,
                       title="Seller already claimed")

    pending = AppError("You already have a claim waiting on this store.",
                       code="claim_pending", status_code=409, title="Claim pending")
    # MQA-012: one claim under review per store, from anyone. A second claim
    # while the first is open gives the moderators two conflicting cases for one
    # store; the second claimant is told it is being reviewed and can write to
    # the team. The store row is locked so two first claims cannot both pass.
    db.scalar(select(Seller.id).where(Seller.id == seller.id).with_for_update())
    waiting = db.execute(select(SellerClaim.id, SellerClaim.user_id).where(
        SellerClaim.seller_id == seller.id,
        SellerClaim.status == SellerClaimStatus.pending,
    ).limit(1)).first()
    if waiting is not None and waiting.user_id == user.id:
        raise pending
    if waiting is not None:
        raise AppError("A claim on this store is already being reviewed. If you run this "
                       "store, message the Bluntly team and we will look at both.",
                       code="claim_under_review", status_code=409, title="Claim under review")

    claim = SellerClaim(
        seller_id=seller.id, user_id=user.id, evidence=payload.evidence,
        registration_kind=payload.registration_kind,
        registration_number=payload.registration_number,
        registered_business_name=payload.registered_business_name.strip(),
        marketplace_shop_name=payload.marketplace_shop_name.strip(),
    )
    db.add(claim)
    try:
        db.commit()
    except IntegrityError as exc:
        # `uq_seller_claim_pending` — the partial index — wins the race.
        db.rollback()
        raise pending from exc
    db.refresh(claim)
    return _claim_out(claim, seller)


def list_my_claims(db: Session, user: User) -> list[SellerClaimOut]:
    """The caller's own store claims, newest first, with the store's marketplace
    and link: the Seller console's store switcher ("in review") and its Claim
    status window (Figma Menu/Store/Switcher, Overlay/Store/ClaimStatus)."""
    rows = db.execute(
        select(SellerClaim, Seller)
        .join(Seller, Seller.id == SellerClaim.seller_id)
        .where(SellerClaim.user_id == user.id)
        .order_by(SellerClaim.created_at.desc())
    ).all()
    return [_claim_out(claim, seller).model_copy(update={
        "seller_platform": getattr(seller.platform, "value", seller.platform),
        "store_url": seller.store_url}) for claim, seller in rows]


def withdraw_claim(db: Session, claim_id: uuid.UUID, user: User) -> SellerClaimOut:
    """The claimant takes back their own pending claim (Confirm/Store/WithdrawClaim:
    "The moderator stops checking it. You can claim the store again later.").

    Someone else's claim is not found (404), never forbidden, so claim ids are
    not enumerable. A decided claim cannot be withdrawn (409). Row-locked, so a
    moderator deciding at the same moment either sees it withdrawn or wins.
    """
    claim = db.get(SellerClaim, claim_id, with_for_update=True)
    if claim is None or claim.user_id != user.id:
        raise NotFoundError("Claim not found.", code="claim_not_found")
    if claim.status != SellerClaimStatus.pending:
        raise AppError("This claim has already been decided.",
                       code="claim_already_decided", status_code=409,
                       title="Claim already decided")
    claim.status = SellerClaimStatus.withdrawn
    claim.decided_at = datetime.now(UTC)
    claim.decision_note = None
    db.commit()
    db.refresh(claim)
    seller = db.get(Seller, claim.seller_id)
    return _claim_out(claim, seller).model_copy(update={
        "seller_platform": getattr(seller.platform, "value", seller.platform) if seller else None,
        "store_url": seller.store_url if seller else None})


def list_store_appeals(db: Session, seller_id: uuid.UUID, user: User) -> list[SellerAppealOut]:
    """Every flag the store's owner raised, newest first (Screen/Seller/Appeals)."""
    seller = get_seller_or_404(db, seller_id)
    _require_owner(seller, user)
    rows = db.execute(
        select(SellerReviewAppeal, SellerReview, User)
        .join(SellerReview, SellerReview.id == SellerReviewAppeal.seller_review_id)
        .outerjoin(User, User.id == SellerReview.reviewer_id)
        .where(SellerReviewAppeal.seller_id == seller.id)
        .order_by(SellerReviewAppeal.created_at.desc())
    ).all()
    # The reviewer's thread with the administrators is not the store's to read:
    # neither the admin's request (the thread's first message) nor the reviewer's
    # proof, nor the order id. The owner sees where the case stands (the dates).
    return [SellerAppealOut.model_validate(appeal).model_copy(update={
        "substantiation_request": None, "substantiation_response": None, "order_id": None,
        "review_rating": float(review.overall_rating), "review_title": review.title,
        "review_comment": review.comment, "review_created_at": review.created_at,
        "reviewer": QAAuthor.model_validate(reviewer) if reviewer is not None else None,
        "seller_name": seller.display_name,
        "seller_platform": getattr(seller.platform, "value", seller.platform),
        "store_url": seller.store_url}) for appeal, review, reviewer in rows]


def list_store_questions(db: Session, seller_id: uuid.UUID, user: User, *,
                         status: str = "all", limit: int = 100) -> list[StoreQuestionOut]:
    """The store's questions for its owner: newest first, each with the store's
    own answer when it has one. `needs` = no answer from the store yet."""
    seller = get_seller_or_404(db, seller_id)
    _require_owner(seller, user)
    store_answers = (select(Answer.question_id, func.min(Answer.created_at).label("first"))
                     .where(Answer.is_seller_answer.is_(True)).group_by(Answer.question_id)
                     .subquery())
    stmt = (select(Question, User, store_answers.c.first)
            .outerjoin(User, User.id == Question.asker_id)
            .outerjoin(store_answers, store_answers.c.question_id == Question.id)
            .where(Question.seller_id == seller.id, Question.is_removed.is_(False)))
    if status == "needs":
        stmt = stmt.where(store_answers.c.first.is_(None))
    elif status == "answered":
        stmt = stmt.where(store_answers.c.first.is_not(None))
    rows = db.execute(stmt.order_by(Question.created_at.desc()).limit(limit)).all()
    ids = [q.id for q, _, _ in rows]
    counts = dict(db.execute(
        select(Answer.question_id, func.count()).where(Answer.question_id.in_(ids))
        .group_by(Answer.question_id)).all()) if ids else {}
    community = dict(db.execute(
        select(Answer.question_id, func.count()).where(
            Answer.question_id.in_(ids), Answer.is_seller_answer.is_(False))
        .group_by(Answer.question_id)).all()) if ids else {}
    # Followers besides the asker (who is told on their own), as the answer's
    # notifications count them: "Mara and 8 followers are notified".
    followers = dict(db.execute(
        select(QuestionSubscription.question_id, func.count())
        .join(Question, Question.id == QuestionSubscription.question_id)
        .where(QuestionSubscription.question_id.in_(ids),
               or_(Question.asker_id.is_(None),
                   QuestionSubscription.user_id != Question.asker_id))
        .group_by(QuestionSubscription.question_id)).all()) if ids else {}
    firsts = {a.question_id: a for a in db.scalars(
        select(Answer).where(Answer.question_id.in_(ids), Answer.is_seller_answer.is_(True))
        .order_by(Answer.created_at.desc()))} if ids else {}
    return [StoreQuestionOut(
        id=q.id, body=q.body, created_at=q.created_at,
        asker=QAAuthor.model_validate(asker) if asker is not None else None,
        answer_count=int(counts.get(q.id, 0)),
        community_answers=int(community.get(q.id, 0)),
        followers=int(followers.get(q.id, 0)),
        store_answer=(StoreAnswerOut(id=firsts[q.id].id, body=firsts[q.id].body,
                                     created_at=firsts[q.id].created_at,
                                     edited_at=firsts[q.id].edited_at)
                      if q.id in firsts else None))
        for q, asker, _ in rows]


def link_mismatch(platform, url):
    from app.services.store_change_service import link_mismatch as _mismatch
    return _mismatch(platform, url)


def list_pending_claims(db: Session, limit: int, offset: int = 0) -> list[SellerClaimOut]:
    """Oldest first: a claimant who asked earlier is answered earlier. With the
    claimant and the store's marketplace, for the admin Claims table. Paged
    (`offset`, a stable id tiebreak) so no claim sits past a cap unseen."""
    rows = db.execute(
        select(SellerClaim, Seller, User)
        .join(Seller, Seller.id == SellerClaim.seller_id)
        .outerjoin(User, User.id == SellerClaim.user_id)
        .where(SellerClaim.status == SellerClaimStatus.pending)
        .order_by(SellerClaim.created_at, SellerClaim.id)
        .offset(offset).limit(limit)
    ).all()
    return [_claim_out(claim, seller).model_copy(update={
        "claimant": QAAuthor.model_validate(user) if user is not None else None,
        "seller_platform": getattr(seller.platform, "value", seller.platform),
        "store_url": seller.store_url,
        "link_problem": link_mismatch(seller.platform, seller.store_url)})
        for claim, seller, user in rows]


def decide_claim(db: Session, claim_id: uuid.UUID, moderator: User,
                 decision: ClaimDecision) -> SellerClaimOut:
    claim = db.get(SellerClaim, claim_id)
    if claim is None:
        raise NotFoundError("Claim not found.")
    if claim.user_id == moderator.id:
        raise AppError("You cannot decide a claim you submitted.",
                       code="self_decision", status_code=422, title="Invalid decision")
    if claim.status != SellerClaimStatus.pending:
        raise AppError("This claim has already been decided.",
                       code="claim_already_decided", status_code=409,
                       title="Claim already decided")

    # Locked so two moderators approving rival claims at once cannot both win.
    seller = db.get(Seller, claim.seller_id, with_for_update=True)

    if decision.decision == "approve":
        if (seller.claim_status == SellerClaimStatus.claimed
                and seller.claimed_by_id != claim.user_id):
            raise AppError("This store has already been claimed.",
                           code="seller_already_claimed", status_code=409,
                           title="Seller already claimed")
        # MQA-020: a verified store with a link to another marketplace sends
        # buyers to the wrong shop. Correct the link first (Edit store link).
        problem = link_mismatch(seller.platform, seller.store_url)
        if problem:
            raise AppError(f"{problem} Correct the store's link before approving the claim.",
                           code="store_link_mismatch", status_code=409,
                           title="Store link on another marketplace")
        seller.claimed_by_id = claim.user_id
        seller.claim_status = SellerClaimStatus.claimed
        claim.status = SellerClaimStatus.claimed
        bar_claimed_seller(db, claim.user_id, moderator.id)
    else:
        claim.status = SellerClaimStatus.rejected

    claim.decided_by_id = moderator.id
    claim.decided_at = datetime.now(UTC)
    claim.decision_note = decision.note
    if claim.status == SellerClaimStatus.claimed:
        notification_service.notify(
            db, claim.user_id, "seller_claim_approved", "Your store claim was approved",
            body=decision.note or seller.display_name, link=f"/sellers/{seller.id}/dashboard")
    else:
        notification_service.notify(
            db, claim.user_id, "seller_claim_rejected", "Your store claim was not approved",
            body=decision.note or seller.display_name, link=f"/sellers/{seller.id}")
    db.commit()
    db.refresh(claim)
    return _claim_out(claim, seller)


# ------------------------------------------------ claimed-seller restrictions

def bar_claimed_seller(db: Session, user_id: uuid.UUID, moderator_id: uuid.UUID) -> None:
    """Business Rules §9: a claimed seller account is permanently barred from
    voting, downvoting, reviewing and earning — "past, present, and future,
    regardless of any voting history the account had before it was claimed".

    The flag is one-way. Existing vote weight drops to zero (the visible counts
    stay: they record what happened), and any active affiliate link on the
    account's own reviews is revoked so no future sale earns for it. Money
    already credited is never clawed back.
    """
    from app.models.enums import EarnEligibleStatus, ReferralLinkStatus
    from app.models.review import ReferralLink, Review
    from app.models.vote import ReviewVote
    user = db.get(User, user_id)
    if user is None:
        return
    user.is_claimed_seller = True
    db.execute(update(ReviewVote).where(ReviewVote.voter_id == user_id)
               .values(vote_weight=0))
    # Their votes stop being stage evidence for everyone they voted for, now,
    # not at those members' next vote (QA, 2026-09-29).
    from app.services.trust_service import recompute_authors_voted_on_by
    recompute_authors_voted_on_by(db, user_id)
    now = datetime.now(UTC)
    links = db.scalars(
        select(ReferralLink).join(Review, Review.id == ReferralLink.review_id)
        .where(Review.author_id == user_id, ReferralLink.status == ReferralLinkStatus.active)
    ).all()
    for link in links:
        link.status = ReferralLinkStatus.revoked
        link.revoked_by = moderator_id
        link.revoked_at = now
        link.revoke_reason = "author became a claimed seller"
        review = db.get(Review, link.review_id)
        if review is not None:
            review.affiliate_link = None
            if review.earn_eligible_status == EarnEligibleStatus.monetized:
                review.earn_eligible_status = EarnEligibleStatus.approved


# ------------------------------------------------ responses and appeals (§10)

def _own_store_review(db: Session, review_id: uuid.UUID, user: User) -> tuple[SellerReview, Seller]:
    review = db.get(SellerReview, review_id)
    if review is None or review.is_removed:
        raise NotFoundError("Seller review not found.")
    seller = db.get(Seller, review.seller_id)
    if (seller is None or seller.claim_status != SellerClaimStatus.claimed
            or seller.claimed_by_id != user.id):
        raise ForbiddenError("Only the store's claimed owner can do this.",
                             code="not_store_owner")
    return review, seller


def respond_to_review(db: Session, review_id: uuid.UUID, user: User, body: str) -> SellerReviewOut:
    """The claimed seller's public response. Responding is ALL a claim grants
    over a review — never removal, hiding or suppression (§9)."""
    review, _ = _own_store_review(db, review_id, user)
    now = datetime.now(UTC)
    if review.seller_response and review.seller_response_at is not None:
        # An edit (Confirm/Store/SaveResponse): keep the first response's time,
        # which the store's reply time is measured by, mark it edited, and
        # don't notify the reviewer a second time.
        review.seller_response = body
        review.seller_response_edited_at = now
    else:
        review.seller_response = body
        review.seller_response_at = now
        notification_service.notify(
            db, review.reviewer_id, "seller_responded", "The store responded to your review",
            body=body, link=f"/sellers/{review.seller_id}")
    db.commit()
    db.refresh(review)
    reviewer = db.get(User, review.reviewer_id) if review.reviewer_id else None
    return _review_out(review, reviewer)


def appeal_review(db: Session, review_id: uuid.UUID, user: User, reason: str,
                  kind: str = "never_ordered") -> SellerAppealOut:
    """A claimed seller flags one review of their store as suspected fake (§10).

    Only then does an admin ask the reviewer to substantiate it. One open
    appeal per review at a time (`uq_seller_review_appeal_open`).
    """
    review, seller = _own_store_review(db, review_id, user)
    open_one = db.scalar(select(SellerReviewAppeal.id).where(
        SellerReviewAppeal.seller_review_id == review.id,
        SellerReviewAppeal.status.in_(("open", "substantiation_requested"))))
    if open_one is not None:
        raise AppError("This review already has an open appeal.", code="appeal_open",
                       status_code=409, title="Appeal open")
    appeal = SellerReviewAppeal(seller_review_id=review.id, seller_id=seller.id,
                                appellant_id=user.id, reason=reason, kind=kind, status="open")
    db.add(appeal)
    db.add(ModerationLog(target_type=ModerationTargetType.seller_review, target_ref=review.id,
                         moderator_id=None, action=ModerationAction.seller_appeal,
                         notes=reason, context={"seller_id": str(seller.id), "kind": kind}))
    db.commit()
    db.refresh(appeal)
    return SellerAppealOut.model_validate(appeal)


def list_open_appeals(db: Session, limit: int,
                      decided: bool = False, offset: int = 0) -> list[SellerAppealOut]:
    """Open appeals, oldest first; with `decided`, the upheld and dismissed ones
    instead, newest first (Menu/Sellers/Appeals/Filter, Figma 8288:29871)."""
    statuses = ("upheld", "dismissed") if decided else ("open", "substantiation_requested")
    order = SellerReviewAppeal.decided_at.desc() if decided else SellerReviewAppeal.created_at
    rows = db.execute(
        select(SellerReviewAppeal, SellerReview, Seller, User)
        .join(SellerReview, SellerReview.id == SellerReviewAppeal.seller_review_id)
        .join(Seller, Seller.id == SellerReviewAppeal.seller_id)
        .outerjoin(User, User.id == SellerReview.reviewer_id)
        .where(SellerReviewAppeal.status.in_(statuses))
        .order_by(order, SellerReviewAppeal.id).offset(offset).limit(limit)
    ).all()
    return [SellerAppealOut.model_validate(appeal).model_copy(update={
        "order_id": review.order_id, "seller_name": seller.display_name,
        "seller_platform": getattr(seller.platform, "value", seller.platform),
        "store_url": seller.store_url, "review_rating": float(review.overall_rating),
        "review_title": review.title, "review_comment": review.comment,
        "review_created_at": review.created_at,
        "reviewer": QAAuthor.model_validate(user) if user is not None else None})
        for appeal, review, seller, user in rows]


def _appeal_or_404(db: Session, appeal_id: uuid.UUID) -> SellerReviewAppeal:
    appeal = db.get(SellerReviewAppeal, appeal_id, with_for_update=True)
    if appeal is None:
        raise NotFoundError("Appeal not found.")
    return appeal


def request_substantiation(db: Session, appeal_id: uuid.UUID, moderator: User,
                           note: str) -> SellerAppealOut:
    """Only after a seller's appeal does an admin ask the reviewer to back it up."""
    appeal = _appeal_or_404(db, appeal_id)
    if appeal.status != "open":
        raise AppError("Substantiation can only be requested on an open appeal.",
                       code="appeal_not_open", status_code=409, title="Invalid appeal state")
    review = db.get(SellerReview, appeal.seller_review_id)
    appeal.status = "substantiation_requested"
    appeal.substantiation_request = note
    appeal.substantiation_requested_at = datetime.now(UTC)
    db.add(ModerationLog(target_type=ModerationTargetType.seller_review,
                         target_ref=appeal.seller_review_id, moderator_id=moderator.id,
                         action=ModerationAction.substantiation_request, notes=note))
    notification_service.notify(
        db, review.reviewer_id if review else None, "seller_review_substantiation",
        "Please back up your store review", body=note,
        link=f"/sellers/appeals/{appeal.id}")
    db.commit()
    db.refresh(appeal)
    return SellerAppealOut.model_validate(appeal)


def appeal_for_reviewer(db: Session, appeal_id: uuid.UUID, user: User) -> SellerAppealOut:
    """The reviewer's own view of an appeal against their store review (§10):
    what the store said and what the admin asked, so they can answer it.

    Only the review's author may read it — anyone else gets the same 404 as a
    missing appeal. The order ID stays admin context and is not echoed."""
    appeal = _appeal_or_404(db, appeal_id)
    review = db.get(SellerReview, appeal.seller_review_id)
    if review is None or review.reviewer_id != user.id:
        raise NotFoundError("Appeal not found.")
    return SellerAppealOut.model_validate(appeal).model_copy(update={"order_id": None})


def substantiate(db: Session, appeal_id: uuid.UUID, user: User, response: str) -> SellerAppealOut:
    """The reviewer answers the admin's substantiation request."""
    appeal = _appeal_or_404(db, appeal_id)
    review = db.get(SellerReview, appeal.seller_review_id)
    if review is None or review.reviewer_id != user.id:
        raise ForbiddenError("Only the reviewer can respond to this request.",
                             code="not_review_author")
    if appeal.status != "substantiation_requested":
        raise AppError("No substantiation was requested.", code="appeal_not_awaiting",
                       status_code=409, title="Invalid appeal state")
    appeal.substantiation_response = response
    appeal.substantiated_at = datetime.now(UTC)
    db.commit()
    db.refresh(appeal)
    return SellerAppealOut.model_validate(appeal)


def decide_appeal(db: Session, appeal_id: uuid.UUID, moderator: User,
                  decision: str, note: str | None) -> SellerAppealOut:
    """Uphold (the review comes down) or dismiss (it stays). The seller never decides."""
    appeal = _appeal_or_404(db, appeal_id)
    if appeal.status not in ("open", "substantiation_requested"):
        raise AppError("This appeal has already been decided.", code="appeal_decided",
                       status_code=409, title="Appeal decided")
    seller = db.get(Seller, appeal.seller_id)
    if seller is not None and seller.claimed_by_id == moderator.id:
        raise AppError("You cannot decide an appeal on a store you run.",
                       code="self_decision", status_code=422, title="Invalid decision")
    # Figma Overlay/Seller/Appeal (7996:11826): "Ask the reviewer first to
    # unlock removal" — a review never comes down unheard.
    if decision == "uphold" and appeal.substantiation_requested_at is None:
        raise AppError("Ask the reviewer to back up their review before removing it.",
                       code="reviewer_not_asked", status_code=422, title="Invalid decision")
    appeal.status = "upheld" if decision == "uphold" else "dismissed"
    appeal.decided_by_id = moderator.id
    appeal.decided_at = datetime.now(UTC)
    appeal.decision_note = note
    db.add(ModerationLog(target_type=ModerationTargetType.seller_review,
                         target_ref=appeal.seller_review_id, moderator_id=moderator.id,
                         action=ModerationAction.appeal_decision, notes=note,
                         context={"decision": appeal.status}))
    # The store owner who flagged it hears the outcome (Overlay/Store/Notifications
    # → Appeals 8232:25614).
    notification_service.notify(
        db, appeal.appellant_id, "seller_appeal_decided",
        "Your appeal was upheld: the review comes down" if appeal.status == "upheld"
        else "Your appeal was dismissed: the review stays",
        body=note, link=f"/seller/{appeal.seller_id}/appeals?tab=decided")
    db.commit()
    if appeal.status == "upheld":
        review = db.get(SellerReview, appeal.seller_review_id)
        if review is not None and not review.is_removed:
            remove_seller_review(db, review.id, moderator, note or "Appeal upheld")
    db.refresh(appeal)
    return SellerAppealOut.model_validate(appeal)

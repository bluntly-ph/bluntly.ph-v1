"""The claimed seller's dashboard analytics (owner decision 2026-09-28).

Rudimentary on purpose: counts from data the platform already stores, nothing
modelled or predicted. Every figure is computed with a handful of grouped
queries over the store's own rows — no per-review query.

DEFINITIONS (docs/SELLER_DASHBOARD.md):

    engagement        helpful votes + replies on a seller review
    most engaged      the visible review with the highest engagement
                      (ties: the newer one)
    most discussed    the visible review with the most replies (ties: newer)
    response rate     reviews with the store's response / visible reviews
    months            the last six Manila months, zero-filled: new reviews,
                      new replies under them, new store questions

Moderation priority is NOT used anywhere here: it is an internal triage signal
for staff, not a ranking to show a seller.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.models.enums import VoteDirection
from app.models.qa import Answer, Question
from app.models.seller import (
    Seller,
    SellerReview,
    SellerReviewAppeal,
    SellerReviewReply,
    SellerReviewVote,
)
from app.models.user import User
from app.schemas.seller import (
    DashboardActivity,
    DashboardMonth,
    DashboardReviewRow,
    SellerDashboardAnalytics,
)
from app.services.seller_service import summarize_reviews

MONTHS = 6
LIST_LIMIT = 30
ACTIVITY_LIMIT = 15
#: Reviews still without the store's response, oldest first (Overview "Waiting on you").
WAITING_LIMIT = 20
_OPEN_APPEALS = ("open", "substantiation_requested")


def _month_keys(today: date) -> list[str]:
    keys, year, month = [], today.year, today.month
    for _ in range(MONTHS):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return list(reversed(keys))


def _key(moment: datetime) -> str:
    local = moment.astimezone(MANILA)
    return f"{local.year:04d}-{local.month:02d}"


def _excerpt(text: str | None, limit: int = 160) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit].rsplit(" ", 1)[0] + "…"


def _median_reply_hours(db: Session, seller_id: uuid.UUID | None) -> float | None:
    """Median hours from a review (or a store question) to the store's response
    (or answer): one store's, or every store's when `seller_id` is None.

    Only what is stored: a review's seller_response_at, and a store answer's
    created_at against its question's. None until there is one.
    """
    review_q = (select(func.extract("epoch", SellerReview.seller_response_at
                                    - SellerReview.created_at).label("s"))
                .where(SellerReview.seller_response_at.is_not(None),
                       SellerReview.is_removed.is_(False)))
    answer_q = (select(func.extract("epoch", Answer.created_at - Question.created_at).label("s"))
                .join(Question, Question.id == Answer.question_id)
                .where(Answer.is_seller_answer.is_(True), Question.seller_id.is_not(None)))
    if seller_id is not None:
        review_q = review_q.where(SellerReview.seller_id == seller_id)
        answer_q = answer_q.where(Question.seller_id == seller_id)
    both = review_q.union_all(answer_q).subquery()
    seconds = db.scalar(select(func.percentile_cont(0.5).within_group(both.c.s)))
    return round(float(seconds) / 3600, 1) if seconds is not None else None


def build(db: Session, seller: Seller, *, now: datetime | None = None
          ) -> tuple[SellerDashboardAnalytics, list[DashboardReviewRow], list[DashboardActivity],
           list[DashboardReviewRow]]:
    now = now or datetime.now(MANILA)
    visible = db.execute(
        select(SellerReview, User.username, User.display_name, User.trust_stage)
        .outerjoin(User, User.id == SellerReview.reviewer_id)
        .where(SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False))
        .order_by(SellerReview.created_at.desc())).all()
    ids = [r.id for r, *_ in visible]

    votes = {rid: (up, down) for rid, up, down in db.execute(
        select(SellerReviewVote.seller_review_id,
               func.count().filter(SellerReviewVote.direction == VoteDirection.up),
               func.count().filter(SellerReviewVote.direction == VoteDirection.down))
        .where(SellerReviewVote.seller_review_id.in_(ids))
        .group_by(SellerReviewVote.seller_review_id)).all()} if ids else {}
    reply_rows = db.execute(
        select(SellerReviewReply.seller_review_id, SellerReviewReply.created_at,
               SellerReviewReply.id)
        .where(SellerReviewReply.seller_review_id.in_(ids),
               SellerReviewReply.is_removed.is_(False))).all() if ids else []
    replies: dict[uuid.UUID, int] = {}
    for rid, _, _ in reply_rows:
        replies[rid] = replies.get(rid, 0) + 1
    appeals = {sid: status for sid, status in db.execute(
        select(SellerReviewAppeal.seller_review_id, SellerReviewAppeal.status)
        .where(SellerReviewAppeal.seller_id == seller.id)
        .order_by(SellerReviewAppeal.created_at)).all()}

    rows: list[DashboardReviewRow] = []
    for review, username, display_name, stage in visible:
        up, down = votes.get(review.id, (0, 0))
        n_replies = replies.get(review.id, 0)
        rows.append(DashboardReviewRow(
            id=review.id, created_at=review.created_at,
            reviewer=f"@{username}" if username else None,
            reviewer_name=display_name or (f"@{username}" if username else None),
            reviewer_trust_stage=stage, title=review.title,
            excerpt=_excerpt(review.comment), overall_rating=float(review.overall_rating),
            helpful_votes=up, unhelpful_votes=down, reply_count=n_replies,
            engagement=up + n_replies, has_store_response=bool(review.seller_response),
            appeal_status=appeals.get(review.id)))

    questions = db.execute(
        select(Question.id, Question.created_at, Question.body)
        .where(Question.seller_id == seller.id, Question.is_removed.is_(False))
        .order_by(Question.created_at.desc())).all()
    answered_by_store = db.scalar(
        select(func.count(func.distinct(Answer.question_id)))
        .join(Question, Question.id == Answer.question_id)
        .where(Question.seller_id == seller.id, Answer.is_seller_answer.is_(True))) or 0

    keys = _month_keys(now.astimezone(MANILA).date())
    months = {k: DashboardMonth(month=k) for k in keys}
    for review, *_ in visible:
        if (k := _key(review.created_at)) in months:
            months[k].reviews += 1
    for _, created, _ in reply_rows:
        if (k := _key(created)) in months:
            months[k].replies += 1
    for _, created, _ in questions:
        if (k := _key(created)) in months:
            months[k].questions += 1

    summary = summarize_reviews([r for r, *_ in visible])
    count = len(rows)
    responses = sum(1 for r in rows if r.has_store_response)
    newest_first = rows  # already newest first, so max() keeps the newer on ties
    most_engaged = max(newest_first, key=lambda r: r.engagement, default=None)
    most_discussed = max(newest_first, key=lambda r: r.reply_count, default=None)
    from app.services.support_service import open_count
    analytics = SellerDashboardAnalytics(
        review_count=count, median_rating=summary.overall_average,
        rating_distribution={str(k): v for k, v in summary.rating_distribution.items()},
        replies_total=len(reply_rows), helpful_votes_total=sum(v[0] for v in votes.values()),
        questions_total=len(questions), questions_answered_by_store=answered_by_store,
        responses_total=responses,
        response_rate=round(responses / count, 4) if count else None,
        appeals_open=sum(1 for s in appeals.values() if s in _OPEN_APPEALS),
        support_open=open_count(db, seller.id),
        months=[months[k] for k in keys],
        reviews_awaiting_response=count - responses,
        median_reply_hours=_median_reply_hours(db, seller.id),
        platform_median_reply_hours=_median_reply_hours(db, None),
        most_engaged=most_engaged if most_engaged and most_engaged.engagement > 0 else None,
        most_discussed=most_discussed if most_discussed and most_discussed.reply_count > 0
        else None)

    activity: list[DashboardActivity] = []
    for review, username, *_ in visible[:ACTIVITY_LIMIT]:
        activity.append(DashboardActivity(
            kind="seller_review", at=review.created_at,
            label=f"New {float(review.overall_rating):g}★ review"
                  + (f" by @{username}" if username else ""),
            link=f"/sellers/{seller.id}#review-{review.id}"))
        if review.seller_response_at:
            activity.append(DashboardActivity(kind="store_response", at=review.seller_response_at,
                                              label="You responded to a review",
                                              link=f"/sellers/{seller.id}#review-{review.id}"))
    for rid, created, _ in sorted(reply_rows, key=lambda r: r[1], reverse=True)[:ACTIVITY_LIMIT]:
        activity.append(DashboardActivity(kind="reply", at=created,
                                          label="New reply under a review",
                                          link=f"/sellers/{seller.id}#review-{rid}"))
    for qid, created, body in questions[:ACTIVITY_LIMIT]:
        activity.append(DashboardActivity(kind="question", at=created,
                                          label=f"New question: {_excerpt(body, 60)}",
                                          link=f"/questions/{qid}"))
    from app.models.support import SellerSupportRequest
    for req in db.scalars(select(SellerSupportRequest)
                          .where(SellerSupportRequest.seller_id == seller.id)
                          .order_by(SellerSupportRequest.updated_at.desc())
                          .limit(ACTIVITY_LIMIT)):
        activity.append(DashboardActivity(
            kind="support_request", at=req.updated_at,
            label=f"Support request {req.reference}: {req.status.value.replace('_', ' ')}",
            link=f"/sellers/{seller.id}/support/{req.id}"))
    activity.sort(key=lambda a: a.at, reverse=True)
    # The newest-30 list would hide the reviews that have waited longest.
    waiting = [r for r in reversed(rows) if not r.has_store_response][:WAITING_LIMIT]
    return analytics, rows[:LIST_LIMIT], activity[:ACTIVITY_LIMIT], waiting

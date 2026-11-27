"""Activity surge relative to a review's OWN baseline (Business Rules §18).

    "Raw engagement counts - views, comments, upvotes, reports - feed into
    moderation priority, but only as a surge relative to that specific item's
    own baseline, never as raw total volume."

Reports have their own velocity check (report_service.is_surge). This covers
the other three raw counts: page views (traffic buckets — not reading
telemetry, which stays outside every decision), comments and upvotes. Nothing
here reads who the author is: reputation, trust stage and verification stay out
of moderation priority.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.comment import ReviewComment
from app.models.enums import VoteDirection
from app.models.traffic import ReviewViewBucket
from app.models.vote import ReviewVote

RECENT = timedelta(hours=24)
BASELINE_DAYS = 7
#: A handful of events is never a surge, however quiet the review was.
MIN_RECENT_EVENTS = 10
SURGE_FACTOR = 3.0


def is_activity_surge(recent: int, prior: int, *, baseline_days: int = BASELINE_DAYS) -> bool:
    """Pure: `recent` events in the last day against `prior` over the days before."""
    daily = prior / max(1, baseline_days)
    return recent >= MIN_RECENT_EVENTS and recent >= SURGE_FACTOR * daily + 1


def surges_for(db: Session, review_ids: Collection[uuid.UUID],
               *, now: datetime | None = None) -> dict[uuid.UUID, bool]:
    """Batched: which of these reviews are surging now. Three grouped queries."""
    ids = list(dict.fromkeys(review_ids))
    if not ids:
        return {}
    now = now or datetime.now(UTC)
    recent_from = now - RECENT
    prior_from = recent_from - timedelta(days=BASELINE_DAYS)
    recent: dict[uuid.UUID, int] = {}
    prior: dict[uuid.UUID, int] = {}

    def add(rows, target: dict[uuid.UUID, int]) -> None:
        for review_id, n in rows:
            target[review_id] = target.get(review_id, 0) + int(n or 0)

    for window_from, window_to, target in ((recent_from, now, recent),
                                           (prior_from, recent_from, prior)):
        add(db.execute(
            select(ReviewViewBucket.review_id, func.sum(ReviewViewBucket.view_count))
            .where(ReviewViewBucket.review_id.in_(ids),
                   ReviewViewBucket.bucket_start >= window_from,
                   ReviewViewBucket.bucket_start < window_to)
            .group_by(ReviewViewBucket.review_id)).all(), target)
        add(db.execute(
            select(ReviewComment.review_id, func.count(ReviewComment.id))
            .where(ReviewComment.review_id.in_(ids),
                   ReviewComment.created_at >= window_from,
                   ReviewComment.created_at < window_to)
            .group_by(ReviewComment.review_id)).all(), target)
        add(db.execute(
            select(ReviewVote.review_id, func.count(ReviewVote.id))
            .where(ReviewVote.review_id.in_(ids), ReviewVote.vote == VoteDirection.up,
                   ReviewVote.created_at >= window_from,
                   ReviewVote.created_at < window_to)
            .group_by(ReviewVote.review_id)).all(), target)
    return {rid: is_activity_surge(recent.get(rid, 0), prior.get(rid, 0)) for rid in ids}

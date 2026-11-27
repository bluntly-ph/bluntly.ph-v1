"""Fake/shill + collusion fraud signals (M2 slice 5).

ADVISORY ONLY — these signals are surfaced on the moderator queue card and never
auto-block anything (capstone FR-8 invariant). They are computed on read in
bounded batches and are NOT exposed on any public endpoint.

Copied text is `duplicate_text` (normalised comparison, meaningful-length
floor). Reused photos are `duplicate_images` (a 64-bit difference hash taken
at upload), checked when a review is published. A web reverse image search
still has no provider (`integrity_checks`, ADR-007).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterator, Mapping
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import VoteDirection
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from app.services.ranking import (
    COLLUSION_MIN_VOTERS,
    COLLUSION_THRESHOLD,
    max_in_window,
    velocity_exceeded,
)


def _now() -> datetime:
    return datetime.now(UTC)


_QUERY_CHUNK_SIZE = 500


def _chunks(values: Collection[uuid.UUID]) -> Iterator[tuple[uuid.UUID, ...]]:
    items = tuple(dict.fromkeys(values))
    for start in range(0, len(items), _QUERY_CHUNK_SIZE):
        yield items[start : start + _QUERY_CHUNK_SIZE]


def compute_signals_by_review(
    db: Session,
    reviews: Collection[Review],
    authors: Mapping[uuid.UUID, User],
    *,
    now: datetime | None = None,
    evidence: dict[uuid.UUID, dict] | None = None,
) -> dict[uuid.UUID, dict]:
    """Compute the existing six advisory fields for a review batch.

    Each fact source is queried once per bounded chunk, so evaluating a global
    queue does not add four or five round trips for every candidate. The
    collusion definition and duplicate threshold are identical to the original
    one-review implementation; only acquisition is batched.

    `evidence`, when given, is filled with the facts behind each signal, read
    from the same rows (no extra query): how many up-voters, how many of them
    the author up-votes back, the most up-votes inside one velocity window,
    and the matched review's similarity. The six signal fields stay frozen
    (telemetry isolation); the evidence is what an administrator reads to see
    WHY a signal fired (dev/QA sync 2026-09-29).
    """
    review_by_id = {review.id: review for review in reviews}
    if not review_by_id:
        return {}

    evaluated_at = now or _now()
    if evaluated_at.tzinfo is None:
        evaluated_at = evaluated_at.replace(tzinfo=UTC)
    else:
        evaluated_at = evaluated_at.astimezone(UTC)

    review_ids = tuple(review_by_id)
    vote_times: dict[uuid.UUID, list[datetime]] = {}
    voters: dict[uuid.UUID, set[uuid.UUID]] = {}
    for chunk in _chunks(review_ids):
        rows = db.execute(
            select(ReviewVote.review_id, ReviewVote.voter_id, ReviewVote.created_at).where(
                ReviewVote.review_id.in_(chunk),
                ReviewVote.vote == VoteDirection.up,
            )
        ).all()
        for review_id, voter_id, created_at in rows:
            vote_times.setdefault(review_id, []).append(created_at)
            voters.setdefault(review_id, set()).add(voter_id)

    author_ids = {
        review.author_id
        for review in review_by_id.values()
        if review.author_id is not None
    }
    reciprocated_by_author: dict[uuid.UUID, set[uuid.UUID]] = {}
    author_review_counts: dict[uuid.UUID, int] = {}
    for chunk in _chunks(author_ids):
        reciprocal_rows = db.execute(
            select(ReviewVote.voter_id, Review.author_id)
            .join(Review, ReviewVote.review_id == Review.id)
            .where(
                ReviewVote.voter_id.in_(chunk),
                ReviewVote.vote == VoteDirection.up,
                Review.author_id.is_not(None),
            )
            .distinct()
        ).all()
        for author_id, reciprocated_author_id in reciprocal_rows:
            reciprocated_by_author.setdefault(author_id, set()).add(
                reciprocated_author_id
            )

        count_rows = db.execute(
            select(Review.author_id, func.count(Review.id))
            .where(
                Review.author_id.in_(chunk),
                Review.is_removed.is_(False),
            )
            .group_by(Review.author_id)
        ).all()
        author_review_counts.update(
            (author_id, int(count)) for author_id, count in count_rows
        )

    # The one duplicate-text detector (`duplicate_text`): normalised text, a
    # meaningful-length floor, and only an EARLIER review as the source.
    from app.services.duplicate_text import review_duplicates
    duplicates = {}
    for chunk in _chunks(review_ids):
        duplicates.update(review_duplicates(db, [review_by_id[rid] for rid in chunk]))

    signals_by_review: dict[uuid.UUID, dict] = {}
    for review_id, review in review_by_id.items():
        ages = [
            max(
                0.0,
                (
                    evaluated_at
                    - (created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC))
                ).total_seconds(),
            )
            for created_at in vote_times.get(review_id, ())
        ]
        review_voters = voters.get(review_id, set())
        reciprocated: set[uuid.UUID] = set()
        if review.author_id is not None:
            reciprocated = review_voters & reciprocated_by_author.get(
                review.author_id, set()
            )
        collusion = (review.author_id is not None
                     and len(review_voters) >= COLLUSION_MIN_VOTERS
                     and (len(reciprocated) / len(review_voters)) > COLLUSION_THRESHOLD)

        author = authors.get(review.author_id) if review.author_id is not None else None
        account_age_days = 0
        if author is not None:
            created = (
                author.created_at
                if author.created_at.tzinfo
                else author.created_at.replace(tzinfo=UTC)
            )
            account_age_days = max(0, (evaluated_at - created).days)

        finding = duplicates.get(review_id)
        duplicate_id = finding.matched_id if finding is not None else None
        if evidence is not None:
            evidence[review_id] = {
                "upvoters": len(review_voters),
                "reciprocal_upvoters": len(reciprocated),
                "max_upvotes_in_velocity_window": max_in_window(ages),
                "duplicate_of": str(duplicate_id) if duplicate_id else None,
                "duplicate_similarity": (round(finding.comparison.score, 3)
                                         if finding is not None else None),
                "duplicate_evidence": (finding.evidence(evaluated_at)
                                       if finding is not None else None),
            }
        signals_by_review[review_id] = {
            "velocity": velocity_exceeded(ages),
            "collusion": collusion,
            "duplicate_content": duplicate_id is not None,
            "duplicate_of": str(duplicate_id) if duplicate_id else None,
            "author_account_age_days": account_age_days,
            "author_review_count": author_review_counts.get(review.author_id, 0),
        }
    return signals_by_review


def compute_signals(
    db: Session,
    review: Review,
    author: User | None,
    *,
    now: datetime | None = None,
) -> dict:
    """Signals payload for one moderator-queue card."""
    authors = {author.id: author} if author is not None else {}
    return compute_signals_by_review(db, [review], authors, now=now)[review.id]

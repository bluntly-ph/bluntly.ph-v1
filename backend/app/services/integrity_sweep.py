"""File automated integrity signals into the report queue (Business Rules §12).

    "Automated fraud/collusion signals feed the same admin queue as human
    reports, weighted by severity the same way - but every queue item is
    explicitly labeled by origin, system-detected versus user-reported."

The signals themselves (`fraud_service`) are advisory and pure reads; reading
the moderator queue must never write. This sweep is the one place they become
queue items: a scheduled task (and an admin button) evaluates recently active
public reviews and files one SYSTEM_DETECTED report per review per signal,
never twice while one is still open. Nothing here changes a review, a vote or
money, and nothing reads the author's reputation, trust stage or verification.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import ModerationReason, ModerationTargetType
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import fraud_service
from app.services.earning_track import verdict_star_mismatch
from app.services.report_service import file_system_report

#: Reviews submitted or voted on within this window are evaluated.
WINDOW = timedelta(days=14)
#: Severity is the report's weight toward the one escalation threshold (1.0).
SEVERITY = {
    "collusion": 1.0,
    "duplicate_content": 0.8,
    "vote_velocity": 0.5,
    "verdict_star_mismatch": 0.5,
}
REASONS = {
    "collusion": ModerationReason.other,
    "duplicate_content": ModerationReason.plagiarized,
    "vote_velocity": ModerationReason.other,
    "verdict_star_mismatch": ModerationReason.other,
}


def sweep(db: Session, *, now: datetime | None = None, limit: int = 500) -> dict:
    now = now or datetime.now(UTC)
    since = now - WINDOW
    recently_voted = select(ReviewVote.review_id).where(ReviewVote.created_at >= since)
    reviews = list(db.scalars(
        select(Review).where(
            Review.published_at.isnot(None), Review.is_removed.is_(False),
            or_(Review.created_at >= since, Review.id.in_(recently_voted)),
        ).order_by(Review.created_at.desc()).limit(limit)))
    if not reviews:
        return {"evaluated": 0, "filed": 0}
    author_ids = {r.author_id for r in reviews if r.author_id}
    authors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids)))} \
        if author_ids else {}
    evidence: dict = {}
    signals = fraud_service.compute_signals_by_review(db, reviews, authors, now=now,
                                                      evidence=evidence)
    _search_new_reviews_platform_wide(db, reviews, signals, evidence, now)
    filed = 0
    for review in reviews:
        fired = []
        found = signals.get(review.id, {})
        facts = evidence.get(review.id, {})
        if found.get("collusion"):
            fired.append("collusion")
        if found.get("duplicate_content"):
            fired.append("duplicate_content")
        if found.get("velocity"):
            fired.append("vote_velocity")
        if verdict_star_mismatch(review.verdict, review.star_rating):
            fired.append("verdict_star_mismatch")
        for signal in fired:
            report, created = file_system_report(
                db, target_type=ModerationTargetType.review, target_ref=review.id,
                signal=signal, reason=REASONS[signal], severity=SEVERITY[signal])
            if created:
                # What the check saw when it fired, so the report can say WHY
                # without anyone re-deriving it (dev/QA sync 2026-09-29).
                report.context = {**(report.context or {}),
                                  "evidence": _evidence(signal, review, facts)}
            filed += int(created)
    db.commit()
    return {"evaluated": len(reviews), "filed": filed}


#: Copied text is searched across EVERY product and author only here, and only
#: for reviews written in the last two days (two, so one missed daily run is
#: covered), newest first and at most this many a run. The search costs about
#: 120 ms a review at 50,000 reviews, and this sweep is one request inside the
#: scheduler's 8-second budget. Every other review keeps the same-product,
#: same-author check the submission and the queue use.
PLATFORM_WIDE_DAYS = timedelta(days=2)
PLATFORM_WIDE_MAX = 50


def _search_new_reviews_platform_wide(db: Session, reviews: list[Review], signals: dict,
                                      evidence: dict, now: datetime) -> None:
    from app.services.duplicate_text import review_duplicates

    fresh = [r for r in reviews
             if not signals.get(r.id, {}).get("duplicate_content")
             and _aware(r.created_at) >= now - PLATFORM_WIDE_DAYS][:PLATFORM_WIDE_MAX]
    for review_id, finding in review_duplicates(db, fresh, platform_wide=True).items():
        signals.setdefault(review_id, {})["duplicate_content"] = True
        facts = evidence.setdefault(review_id, {})
        facts["duplicate_of"] = str(finding.matched_id)
        facts["duplicate_similarity"] = round(finding.comparison.score, 3)
        facts["duplicate_evidence"] = finding.evidence(now)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _evidence(signal: str, review: Review, facts: dict) -> dict:
    """The stored facts behind one fired signal: counts and ids, never a name."""
    from app.services.ranking import (
        COLLUSION_MIN_VOTERS,
        COLLUSION_THRESHOLD,
        VELOCITY_THRESHOLD,
        VELOCITY_WINDOW_SECONDS,
    )
    if signal == "duplicate_content":
        return facts.get("duplicate_evidence") or {
            "duplicate_of": facts.get("duplicate_of"),
            "similarity": facts.get("duplicate_similarity")}
    if signal == "collusion":
        return {"upvoters": facts.get("upvoters", 0),
                "reciprocal_upvoters": facts.get("reciprocal_upvoters", 0),
                "min_upvoters": COLLUSION_MIN_VOTERS, "threshold": COLLUSION_THRESHOLD}
    if signal == "vote_velocity":
        return {"max_upvotes_in_window": facts.get("max_upvotes_in_velocity_window", 0),
                "window_seconds": VELOCITY_WINDOW_SECONDS, "threshold": VELOCITY_THRESHOLD}
    if signal == "verdict_star_mismatch":
        return {"verdict": review.verdict.value if review.verdict else None,
                "star_rating": float(review.star_rating) if review.star_rating is not None
                else None}
    return {}

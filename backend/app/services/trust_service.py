"""Trust progression wiring (M2 slice 3).

Recomputes a user's reputation_score / trust_stage from their actual review and
vote history using the pure ADR-003 functions, and awards stage badges. Stages
move ONLY through this recompute — there is no manual stage-set endpoint.

Triggers: review publish/unpublish/reject (referral_service), vote writes
(vote_service), and the nightly `recompute_all_trust` Celery sweep.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationReason,
    ModerationTargetType,
    ReportResolution,
    VerificationStatus,
)
from app.models.moderation import ModerationLog
from app.models.review import Review
from app.models.user import Badge, User, UserBadge
from app.models.vote import ReviewVote
from app.services.trust import (
    Concentration,
    VoterRecord,
    determine_stage,
    evidence_capped_stage,
    helpfulness_score,
    reputation_score,
    vote_concentration,
    voter_evidence_weight,
)

#: The SYSTEM_DETECTED report signal a concentration hold files (ADR-016). A
#: moderator's `dismissed` on it releases the promotion it held.
CONCENTRATION_SIGNAL = "vote_concentration"

# trust_stage -> seeded badge_id awarded on reaching it (no removal on drop).
#: Reviews that count toward trust: public AND decided by a moderator.
#:
#: Before 2026-09-22 a review became public only when a moderator published
#: it, and publishing set exactly these statuses, so "published" meant
#: "a moderator looked at it" and trust counted published reviews. Reviews are
#: public from submission now; counting every public review would let a single
#: photo-bearing submission reach Stage 2 (Verified Buyer, gate-vote weight)
#: with nobody having looked at it. Counting the moderator-decided ones keeps
#: trust exactly where it was — every review published under the old flow
#: carries one of these — so deploying this changes nobody's stage.
#: Whether undecided public reviews should count is a pending business rule.
TRUST_COUNTED_STATUSES = (
    EarnEligibleStatus.approved,
    EarnEligibleStatus.monetized,
    EarnEligibleStatus.honesty_fund,
)

STAGE_BADGES = {
    2: "verified_buyer",
    3: "established_reviewer",
    4: "trusted_reviewer",
    5: "community_expert",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _award_stage_badges(db: Session, user: User, old_stage: int, new_stage: int) -> None:
    for stage in range(max(2, old_stage + 1), new_stage + 1):
        code = STAGE_BADGES.get(stage)
        if code is None:
            continue
        badge = db.scalar(select(Badge).where(Badge.badge_id == code))
        if badge is None:
            continue  # badge not seeded in this environment
        already = db.scalar(select(UserBadge.id).where(
            UserBadge.user_id == user.id, UserBadge.badge_id == badge.id))
        if already is None:
            db.add(UserBadge(user_id=user.id, badge_id=badge.id))


def _counted_reviews():
    """The reviews whose votes are trust evidence: public, moderator-decided."""
    public = Review.published_at.isnot(None) & Review.is_removed.is_(False)
    return public & Review.earn_eligible_status.in_(TRUST_COUNTED_STATUSES)


def voter_records(db: Session, user_id: uuid.UUID) -> list[VoterRecord]:
    """One record per DISTINCT person who voted on the member's counted reviews.

    One grouped query: the member's counted reviews (tens, rarely hundreds)
    joined to their votes by the review index, grouped by voter. Eligibility
    is the voter's standing now — a later claim, probation or suspension
    withdraws their evidence (§9: "regardless of any voting history") — except
    account age, which is taken at their latest vote, as §11's weight is.
    """
    rows = db.execute(
        select(ReviewVote.voter_id, func.count(ReviewVote.id),
               func.max(ReviewVote.created_at), User.created_at, User.trust_stage,
               User.is_on_probation, User.is_under_investigation,
               User.is_claimed_seller, User.is_suspended)
        .join(Review, Review.id == ReviewVote.review_id)
        .join(User, User.id == ReviewVote.voter_id)
        .where(Review.author_id == user_id, _counted_reviews())
        .group_by(ReviewVote.voter_id, User.id)
    ).all()
    records = []
    for (_, reviews_voted, last_vote_at, created_at, stage, probation,
         investigating, claimed, suspended) in rows:
        age_at_vote = max(0, (_aware(last_vote_at) - _aware(created_at)).days)
        records.append(VoterRecord(
            reviews_voted=int(reviews_voted),
            evidence=voter_evidence_weight(
                stage, age_at_vote, bool(probation), bool(investigating),
                bool(claimed), bool(suspended))))
    return records


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _concentration_reports(db: Session, user_ids) -> list[ModerationLog]:
    return list(db.scalars(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.report,
        ModerationLog.target_type == ModerationTargetType.user,
        ModerationLog.target_ref.in_(list(user_ids)),
        ModerationLog.reporter_id.is_(None),
        ModerationLog.context["signal"].astext == CONCENTRATION_SIGNAL,
    )))


def _covered_stage(report: ModerationLog) -> int:
    return int((report.context or {}).get("candidate_stage") or 0)


def concentration_review_state(
        reports: list[ModerationLog]) -> tuple[int, int, ModerationLog | None]:
    """`(cleared_through, upheld_through, open_report)` for one member.

    A dismissed report clears promotion up to the stage it covered. Any other
    resolution — for a member, the queue offers only `escalated` besides
    `dismissed` — clears nothing; an unresolved report is the hold waiting.
    """
    cleared = max((_covered_stage(r) for r in reports
                   if r.resolution == ReportResolution.dismissed), default=0)
    upheld = max((_covered_stage(r) for r in reports
                  if r.resolution not in (None, ReportResolution.dismissed)), default=0)
    open_report = next((r for r in reports if r.resolution is None), None)
    return cleared, upheld, open_report


def held_by_concentration(db: Session, user_ids) -> set:
    """Members whose vote concentration is awaiting, or failed, a moderator's
    review — the ones a Honesty Fund cycle must pass over (ADR-016)."""
    by_user: dict = {}
    for report in _concentration_reports(db, user_ids) if user_ids else []:
        by_user.setdefault(report.target_ref, []).append(report)
    held = set()
    for user_id, reports in by_user.items():
        cleared, upheld, open_report = concentration_review_state(reports)
        pending = open_report is not None and _covered_stage(open_report) > cleared
        if pending or upheld > cleared:
            held.add(user_id)
    return held


def _concentration_hold(db: Session, user: User, old_stage: int, candidate: int,
                        c: Concentration) -> int:
    """The stage a member keeps while a concentrated cohort awaits review.

    Holds only a PROMOTION into the evidence-gated stages, never below Stage 2
    (which gates on posting). A member already at or above `candidate` keeps
    it: the report is filed for a moderator, and nothing is taken away — the
    signal is evidence to look at, not a penalty (Business Rules §12).
    """
    cleared, _, open_report = concentration_review_state(
        _concentration_reports(db, [user.id]))
    if candidate <= cleared:
        return candidate
    facts = {
        "candidate_stage": candidate,
        "held_at_stage": min(candidate, max(old_stage, 2)),
        "distinct_voters": c.distinct_voters,
        "eligible_voters": c.eligible_voters,
        "voter_evidence": round(c.voter_evidence, 2),
        "eligible_rows": c.eligible_rows,
        "cohort_size": c.cohort_size,
        "cohort_rows": c.cohort_rows,
        "cohort_share": round(c.cohort_share, 4),
        "top_voter_reviews": c.top_voter_reviews,
    }
    if open_report is not None:
        facts["candidate_stage"] = max(candidate, _covered_stage(open_report))
        open_report.context = {**(open_report.context or {}), **facts}
    else:
        # Nothing open: first detection, or a report escalated rather than
        # dismissed. Escalation has no later decision step, so the hold goes
        # back in the queue (the super admin reads the same queue) instead of
        # stranding the member at a stage nobody can release.
        from app.services.report_service import file_system_report
        report, _ = file_system_report(
            db, target_type=ModerationTargetType.user, target_ref=user.id,
            signal=CONCENTRATION_SIGNAL, reason=ModerationReason.other, severity=1.0)
        report.context = {**(report.context or {}), **facts}
    return facts["held_at_stage"] if candidate > old_stage else candidate


def recompute_user_trust(db: Session, user_id: uuid.UUID) -> None:
    """Recompute reputation inputs -> score -> stage -> badges. Does NOT commit;
    runs inside the caller's transaction (vote write / publish / sweep).

    Sessions run with autoflush=False: flush so the SELECTs below see the
    caller's pending writes (vote counters, published_at, ...).
    """
    db.flush()
    user = db.get(User, user_id)
    if user is None:
        return

    public = Review.published_at.isnot(None) & Review.is_removed.is_(False)
    published = _counted_reviews()
    # Business Rules §8: Stage 1 is "posted at least one review" — any public
    # review counts, no moderator decision needed. Every stage above it still
    # counts only verified, moderator-decided reviews, so a bare submission can
    # unlock commenting but never Stage 2.
    review_count = db.scalar(
        select(func.count(Review.id)).where(Review.author_id == user_id, public)) or 0
    verified_count = db.scalar(
        select(func.count(Review.id)).where(
            Review.author_id == user_id, published,
            Review.verification_status == VerificationStatus.verified)) or 0

    helpful, unhelpful = db.execute(
        select(func.coalesce(func.sum(Review.helpful_votes), 0),
               func.coalesce(func.sum(Review.unhelpful_votes), 0))
        .where(Review.author_id == user_id, published)
    ).one()
    helpfulness = helpfulness_score(helpful, unhelpful)

    created_at = user.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    months_active = (_now() - created_at).days / 30

    user.verified_review_count = verified_count
    user.helpfulness_ratio = helpfulness
    user.computed_reputation_score = round(reputation_score(
        helpfulness_ratio=helpfulness,
        verified_review_count=verified_count,
        best_answer_count=user.best_answer_count,
        strikes=user.strikes,
    ), 2)
    # Effective score: an administrator's override stands in for the
    # computed value until it is cleared (0095, trust_override).
    user.reputation_score = (user.reputation_score_override
                             if user.reputation_score_override is not None
                             else user.computed_reputation_score)

    old_stage = user.trust_stage
    new_stage = determine_stage(
        review_count=review_count,
        verified_review_count=verified_count,
        helpfulness_ratio=helpfulness,
        best_answer_count=user.best_answer_count,
        strikes=user.strikes,
        months_active=months_active,
    )
    if new_stage >= 3:
        # Only the evidence-gated stages need the per-voter read, so the vote
        # write path stays one aggregate for everyone below Stage 3.
        voters = voter_records(db, user_id)
        new_stage = evidence_capped_stage(
            new_stage, voter_evidence=sum(v.evidence for v in voters))
        if new_stage >= 3:
            concentration = vote_concentration(voters, verified_count)
            if concentration.holds_promotion:
                new_stage = _concentration_hold(db, user, old_stage, new_stage, concentration)
    user.trust_stage = new_stage
    if new_stage > old_stage:
        _award_stage_badges(db, user, old_stage, new_stage)


def recompute_authors_voted_on_by(db: Session, voter_id: uuid.UUID) -> int:
    """A voter's standing changed: recompute every member they voted for.

    Stage evidence reads each voter's standing NOW (`voter_records`): a store
    claim, probation or an investigation changes what that person's votes are
    worth to every member they voted on. Those members used to keep a stage
    the withdrawn evidence had supported until their own next vote, or the
    nightly sweep, which skips anyone inactive for 90 days (QA, 2026-09-29).
    Bounded by one voter's votes. Does not commit, like `recompute_user_trust`.
    """
    db.flush()
    authors = db.scalars(
        select(Review.author_id).join(ReviewVote, ReviewVote.review_id == Review.id)
        .where(ReviewVote.voter_id == voter_id, Review.author_id.isnot(None),
               Review.author_id != voter_id)
        .distinct()).all()
    for author_id in authors:
        recompute_user_trust(db, author_id)
    return len(authors)


def recently_active_user_ids(db: Session, active_days: int = 90,
                             created_before=None) -> set:
    """Who the nightly sweep considers active: profile touched, review written,
    or vote cast within `active_days`.

    Split out from the sweep so the selection can be named and tested on its
    own. It is the same query the sweep has always run.

    `created_before` bounds the population to rows that already existed at a
    given instant. It defaults to None, which is exactly the historical
    behaviour — the manual admin route passes nothing. Only the resumable
    scheduler sets it, because a traversal spread across several requests needs
    a boundary that cannot move underneath it: this selector keys off
    `User.updated_at`, and the sweep itself writes User rows, so without a
    boundary the eligible set could keep growing for as long as the run lasted.
    """
    cutoff = _now() - timedelta(days=active_days)
    profile = [User.updated_at >= cutoff]
    authored = [Review.created_at >= cutoff, Review.author_id.isnot(None)]
    voted = [ReviewVote.created_at >= cutoff]
    if created_before is not None:
        profile.append(User.created_at <= created_before)
        authored.append(Review.created_at <= created_before)
        voted.append(ReviewVote.created_at <= created_before)

    user_ids = set(db.scalars(select(User.id).where(*profile)))
    user_ids.update(db.scalars(
        select(Review.author_id).where(*authored).distinct()))
    user_ids.update(db.scalars(
        select(ReviewVote.voter_id).where(*voted).distinct()))
    return user_ids


def recompute_recently_active_users(db: Session, active_days: int = 90) -> int:
    """Nightly sweep: recompute trust for users active in the last `active_days`
    (profile updated, authored a review, or cast a vote). Commits once."""
    user_ids = recently_active_user_ids(db, active_days)
    for user_id in user_ids:
        recompute_user_trust(db, user_id)
    db.commit()
    return len(user_ids)

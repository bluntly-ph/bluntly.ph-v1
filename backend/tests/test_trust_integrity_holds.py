"""Cumulative concentration holds (ADR-016).

The distinct-voter gate forces a ring to be as large as the stage it wants.
These cover the second layer: a stable cohort that keeps showing up across a
member's history — with no reciprocity required — holds a PROMOTION for a
moderator instead of granting it. Nothing here demotes, strikes, freezes or
bans anyone.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from tests.conftest import register_and_token, requires_db
from tests.test_trust_ring_exploit import (
    _recompute,
    _target,
    _vote,
    _voters,
)

pytestmark = requires_db


def _holds(db, user):
    from app.models.enums import ModerationTargetType
    from app.models.moderation import ModerationLog
    from app.services.trust_service import CONCENTRATION_SIGNAL

    return list(db.scalars(select(ModerationLog).where(
        ModerationLog.target_type == ModerationTargetType.user,
        ModerationLog.target_ref == user.id,
        ModerationLog.context["signal"].astext == CONCENTRATION_SIGNAL)))


def _resolve(db, report, resolution):
    """What `resolve_report` records, without its commit (the fixture rolls back)."""
    report.resolution = resolution
    report.resolved_at = datetime.now(UTC)
    db.flush()


def _cohort_member(db):
    """20 eligible people who each vote on every one of 5 reviews: enough
    distinct evidence for Stage 3, all of it from one repeating cohort."""
    author, reviews = _target(db, reviews=5)
    _vote(db, reviews, _voters(db, 20))
    return author


# ---------------------------------------------------------------------------
# The hold
# ---------------------------------------------------------------------------

def test_a_concentrated_cohort_holds_promotion_for_a_moderator(db):
    author = _cohort_member(db)

    assert _recompute(db, author) == 2
    [report] = _holds(db, author)
    assert report.resolution is None
    assert report.reporter_id is None                        # system-detected
    ctx = report.context
    assert ctx["candidate_stage"] == 3 and ctx["held_at_stage"] == 2
    assert (ctx["cohort_size"], ctx["cohort_rows"], ctx["eligible_rows"]) == (20, 100, 100)
    assert ctx["cohort_share"] == 1.0
    # Aggregates only — no voter identities travel in the queue item.
    assert not any("voter_id" in key or key == "voters" for key in ctx)
    assert author.strikes == 0 and not author.is_on_probation


def test_the_hold_needs_no_reciprocity(db):
    """The cohort never received a vote back from the member — the shape the
    per-review reciprocity signal cannot see."""
    from app.models.review import Review
    from app.models.vote import ReviewVote

    author = _cohort_member(db)
    reciprocated = db.scalar(select(ReviewVote.id).join(
        Review, Review.id == ReviewVote.review_id).where(ReviewVote.voter_id == author.id))
    assert reciprocated is None
    assert _recompute(db, author) == 2


def test_recomputing_does_not_file_twice(db):
    author = _cohort_member(db)
    for _ in range(3):
        _recompute(db, author)
    assert len(_holds(db, author)) == 1


def test_a_dismissal_releases_the_promotion(db):
    from app.models.enums import ReportResolution

    author = _cohort_member(db)
    _recompute(db, author)
    [report] = _holds(db, author)
    _resolve(db, report, ReportResolution.dismissed)

    assert _recompute(db, author) == 3
    assert len(_holds(db, author)) == 1, "a cleared stage is not re-reported"


def test_an_escalated_hold_stays_held_and_returns_to_the_queue(db):
    """For a member, the queue's only other answer is `escalated`, which has
    no later decision step. The hold stays, and a fresh report puts it back in
    front of a moderator rather than stranding the member."""
    from app.models.enums import ReportResolution

    author = _cohort_member(db)
    _recompute(db, author)
    [first] = _holds(db, author)
    _resolve(db, first, ReportResolution.escalated)

    assert _recompute(db, author) == 2
    reports = _holds(db, author)
    assert len(reports) == 2
    assert [r.resolution for r in reports if r.id != first.id] == [None]
    _recompute(db, author)
    assert len(_holds(db, author)) == 2, "one open report at a time"


def test_neutralising_the_cohort_ends_the_hold_without_a_ruling(db):
    """A moderator's real remedy for a confirmed ring is probation on the ring
    accounts; their evidence then goes to zero and the candidate stage with it."""
    author, reviews = _target(db, reviews=5)
    ring = _voters(db, 20)
    _vote(db, reviews, ring)
    _recompute(db, author)
    for voter in ring:
        voter.is_on_probation = True
    db.flush()
    assert _recompute(db, author) == 2


def test_a_member_already_at_the_stage_keeps_it_and_is_reported(db):
    """Retrospective, not punitive: the sweep flags an existing stage for a
    moderator without taking it away."""
    author = _cohort_member(db)
    author.trust_stage = 3
    db.flush()

    assert _recompute(db, author) == 3
    assert len(_holds(db, author)) == 1


def test_broad_support_is_never_held(db):
    author, reviews = _target(db, reviews=5)
    for review in reviews:
        _vote(db, [review], _voters(db, 4))
    _vote(db, reviews, _voters(db, 2))          # two regulars on everything

    assert _recompute(db, author) == 3
    assert _holds(db, author) == []


def test_held_by_concentration_reports_pending_and_escalated_only(db):
    from app.models.enums import ReportResolution
    from app.services.trust_service import held_by_concentration

    pending, escalated, cleared = (_cohort_member(db) for _ in range(3))
    for author in (pending, escalated, cleared):
        _recompute(db, author)
    _resolve(db, _holds(db, escalated)[0], ReportResolution.escalated)
    _resolve(db, _holds(db, cleared)[0], ReportResolution.dismissed)

    ids = {pending.id, escalated.id, cleared.id}
    assert held_by_concentration(db, ids) == {pending.id, escalated.id}
    assert held_by_concentration(db, set()) == set()


# ---------------------------------------------------------------------------
# Through the real admin queue
# ---------------------------------------------------------------------------

@requires_db
def test_a_moderator_finds_the_hold_in_the_queue_and_releases_it(client):
    from app.db.session import SessionLocal
    from app.models.user import User
    from app.services.trust_service import recompute_user_trust

    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = {"Authorization": f"Bearer {mod_token}"}
    db = SessionLocal()
    try:
        author = _cohort_member(db)
        recompute_user_trust(db, author.id)
        db.commit()
        author_id = author.id
        assert db.get(User, author_id).trust_stage == 2

        queue = client.get("/api/v1/admin/reports?target_type=user&limit=100", headers=mh)
        assert queue.status_code == 200, queue.text
        [item] = [i for i in queue.json()["items"]
                  if i["report"]["target_ref"] == str(author_id)]
        assert item["origin"] == "system_detected"
        assert item["reporter"] is None

        # A member has no publish state: "remove" is refused, dismiss is not.
        refused = client.post(f"/api/v1/admin/reports/{item['report']['id']}/decision",
                              headers=mh, json={"resolution": "content_removed"})
        assert refused.status_code == 422
        decided = client.post(f"/api/v1/admin/reports/{item['report']['id']}/decision",
                              headers=mh, json={"resolution": "dismissed",
                                                "notes": "Known reading group; checked."})
        assert decided.status_code == 200, decided.text

        db.expire_all()
        recompute_user_trust(db, author_id)
        db.commit()
        assert db.get(User, author_id).trust_stage == 3
    finally:
        db.close()

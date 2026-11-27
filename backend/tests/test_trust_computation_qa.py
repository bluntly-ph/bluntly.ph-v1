"""Trust Score computation (QA, 2026-09-29): "document and implement the defined
computational method for calculating and updating the user Trust Score".

The method is ADR-003 / ADR-014 / ADR-016 and Business Rules §11, written out
in docs/TRUST_SCORE_COMPUTATION.md. These tests pin what that document states,
on a real database, where the existing suites (test_trust*.py) did not already:

* the stage boundaries at exactly 20 / 60 / 200 distinct eligible people, and
  one person short of each;
* WHEN a member is recalculated. The audit found three moments that recomputed
  nobody: a store claim and an investigation, which change what a voter's past
  votes are worth, and a moderator dismissing a concentration hold. Each left
  members at a stage the evidence no longer supported (or still held) until
  their own next vote or the nightly sweep, which skips anyone inactive for
  90 days;
* that a member cannot set their own trust, that concurrent votes are counted
  once each, and that recomputing is deterministic.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.enums import VoteDirection
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote
from tests.conftest import make_user, register_and_token, requires_db
from tests.test_trust_integrity_holds import _cohort_member, _holds
from tests.test_trust_ring_exploit import MATURE, NOW, _recompute, _target, _vote, _voters

pytestmark = requires_db


def _spread(db, reviews, voters):
    """Each voter up-votes ONE review, round-robin: distinct people with no
    repeating cohort, so no concentration hold can apply."""
    from app.services.vote_service import recompute_review_vote_aggregates

    for i, voter in enumerate(voters):
        db.add(ReviewVote(review_id=reviews[i % len(reviews)].id, voter_id=voter.id,
                          vote=VoteDirection.up, created_at=NOW))
    db.flush()
    for review in reviews:
        recompute_review_vote_aggregates(db, review)


# --- the ladder at its exact boundaries ---------------------------------------------

def test_stage_3_needs_exactly_20_distinct_eligible_people(db):
    author, reviews = _target(db, reviews=5)
    _spread(db, reviews, _voters(db, 19))
    assert _recompute(db, author) == 2
    _spread(db, reviews, _voters(db, 1))
    assert _recompute(db, author) == 3


def test_stage_4_needs_exactly_60_distinct_eligible_people(db):
    author, reviews = _target(db, reviews=15, best_answers=3)
    _spread(db, reviews, _voters(db, 59))
    assert _recompute(db, author) == 3          # 59: Stage 3's 20 cleared, not Stage 4's 60
    _spread(db, reviews, _voters(db, 1))
    assert _recompute(db, author) == 4


def test_stage_5_needs_exactly_200_distinct_eligible_people(db):
    author, reviews = _target(db, reviews=50, best_answers=3)
    _spread(db, reviews, _voters(db, 199))
    assert _recompute(db, author) == 4
    _spread(db, reviews, _voters(db, 1))
    assert _recompute(db, author) == 5


def test_half_weight_voters_need_twice_the_people(db):
    """§11: under 30 days old at the vote, 0.5 of a person each."""
    author, reviews = _target(db, reviews=5)
    _spread(db, reviews, _voters(db, 39, created_at=NOW - timedelta(days=5)))
    assert _recompute(db, author) == 2          # 19.5
    _spread(db, reviews, _voters(db, 1, created_at=NOW - timedelta(days=5)))
    assert _recompute(db, author) == 3          # 20.0


# --- when a member is recalculated --------------------------------------------------

def test_a_store_claim_recalculates_everyone_the_sellers_votes_supported(db):
    from app.services.seller_service import bar_claimed_seller

    author, reviews = _target(db, reviews=5)
    voters = _voters(db, 20)
    _spread(db, reviews, voters)
    assert _recompute(db, author) == 3
    moderator = make_user(db, display_name="Claim moderator")
    # §9: the claimed seller's votes weigh 0, past ones included. The author is
    # inactive; before the fix nothing recomputed them and Stage 3 stood.
    bar_claimed_seller(db, voters[0].id, moderator.id)
    db.flush()
    db.refresh(author)
    assert author.trust_stage == 2
    weights = db.scalars(select(ReviewVote.vote_weight).where(
        ReviewVote.voter_id == voters[0].id)).all()
    assert weights and all(w == 0 for w in weights)


def test_an_investigation_set_and_cleared_recalculates_the_members_voted_for(client):
    _, admin_token, _ = register_and_token(client, role="administrator")
    ah = {"Authorization": f"Bearer {admin_token}"}
    db = SessionLocal()
    try:
        author, reviews = _target(db, reviews=5)
        voters = _voters(db, 20)
        _spread(db, reviews, voters)
        _recompute(db, author)
        db.commit()
        author_id, suspect = author.id, voters[0].id
        assert db.get(User, author_id).trust_stage == 3
    finally:
        db.close()

    def stage() -> int:
        check = SessionLocal()
        try:
            return check.get(User, author_id).trust_stage
        finally:
            check.close()

    res = client.put(f"/api/v1/admin/users/{suspect}/investigation", headers=ah,
                     json={"under_investigation": True, "note": "Checking a vote pattern."})
    assert res.status_code == 200, res.text
    assert stage() == 2                          # 19.5 people of evidence, at once
    res = client.put(f"/api/v1/admin/users/{suspect}/investigation", headers=ah,
                     json={"under_investigation": False, "note": "Nothing found."})
    assert res.status_code == 200, res.text
    assert stage() == 3                          # restored, at once


def test_dismissing_a_hold_releases_the_member_at_once(client):
    """ADR-016: a dismissal releases the promotion. The existing API test had to
    recompute by hand after dismissing; an inactive member stayed held."""
    _, admin_token, _ = register_and_token(client, role="administrator")
    ah = {"Authorization": f"Bearer {admin_token}"}
    db = SessionLocal()
    try:
        author = _cohort_member(db)
        _recompute(db, author)
        db.commit()
        author_id = author.id
        assert db.get(User, author_id).trust_stage == 2
        [hold] = _holds(db, author)
        hold_id = hold.id
    finally:
        db.close()
    decided = client.post(f"/api/v1/admin/reports/{hold_id}/decision", headers=ah,
                          json={"resolution": "dismissed", "notes": "A real reading group."})
    assert decided.status_code == 200, decided.text
    db = SessionLocal()
    try:
        assert db.get(User, author_id).trust_stage == 3
    finally:
        db.close()


def test_a_vote_taken_back_stops_counting_at_once(db):
    from app.services.vote_service import remove_vote

    author, reviews = _target(db, reviews=5)
    voters = _voters(db, 20)
    _spread(db, reviews, voters)
    assert _recompute(db, author) == 3
    review = db.get(Review, reviews[0].id)
    remove_vote(db, review, voters[0].id)       # the service's own write path
    db.refresh(author)
    assert author.trust_stage == 2
    assert db.scalar(select(func.count(ReviewVote.id)).where(
        ReviewVote.voter_id == voters[0].id)) == 0


# --- integrity of the inputs ---------------------------------------------------------

def test_a_member_cannot_set_their_own_trust(client):
    uid, token, _ = register_and_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.patch("/api/v1/users/me", headers=headers, json={
        "display_name": "Still me", "trust_stage": 5, "reputation_score": 100,
        "is_on_probation": False, "is_claimed_seller": False, "helpfulness_ratio": 100,
        "verified_review_count": 99})
    assert res.status_code in (200, 422)
    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(uid))
        assert user.trust_stage == 0 and Decimal(user.reputation_score) == 0
        assert user.verified_review_count == 0
    finally:
        db.close()


def _author_and_review() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    db = SessionLocal()
    try:
        author, reviews = _target(db, reviews=1)
        db.commit()
        return author.id, reviews[0].id, reviews[0].product_id
    finally:
        db.close()


def test_one_person_voting_twice_at_the_same_moment_is_one_vote(client):
    _, review_id, _ = _author_and_review()
    db = SessionLocal()
    try:
        voter = make_user(db, created_at=MATURE, trust_stage=2, reputation_score=100)
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(str(voter.id), "user")}"}
    finally:
        db.close()
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def cast():
        barrier.wait()
        codes.append(client.post(f"/api/v1/reviews/{review_id}/vote", headers=headers,
                                 json={"vote": "up"}).status_code)

    threads = [threading.Thread(target=cast) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) in ([200, 200], [200, 409])
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(ReviewVote.id)).where(
            ReviewVote.review_id == review_id)) == 1
        assert db.get(Review, review_id).helpful_votes == 1
    finally:
        db.close()


def test_many_people_voting_at_once_are_each_counted(client):
    """The review's counters are recounted from the vote rows on every write.
    Recounted concurrently without a lock, two writers could each see only
    their own vote and leave the counter short of the rows.

    Two writers are enough for that race; more only need more connections. Each
    request can hold two (its session, and the Postgres rate limiter when Redis
    is absent), so the writers are sized to the pool: CI caps it at 2 + 3 for the
    Supabase session pooler, and twelve writers there timed out waiting for a
    connection (main run 37183348786), which says nothing about the counter."""
    from app.core.config import settings
    writers = max(2, min(12, (settings.db_pool_size + settings.db_max_overflow) // 2))
    _, review_id, _ = _author_and_review()
    db = SessionLocal()
    try:
        voters = [make_user(db, created_at=MATURE, trust_stage=2, reputation_score=100)
                  for _ in range(writers)]
        db.commit()
        tokens = [create_access_token(str(v.id), "user") for v in voters]
    finally:
        db.close()
    barrier = threading.Barrier(len(tokens))
    codes: list[int] = []

    def cast(token):
        barrier.wait()
        codes.append(client.post(f"/api/v1/reviews/{review_id}/vote",
                                 headers={"Authorization": f"Bearer {token}"},
                                 json={"vote": "up"}).status_code)

    threads = [threading.Thread(target=cast, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert codes == [200] * len(tokens)
    db = SessionLocal()
    try:
        rows = db.scalar(select(func.count(ReviewVote.id)).where(
            ReviewVote.review_id == review_id))
        review = db.get(Review, review_id)
        assert rows == len(tokens)
        assert review.helpful_votes == rows
    finally:
        db.close()


def test_recomputing_is_deterministic(db):
    from app.services.trust_service import recompute_user_trust

    author, reviews = _target(db, reviews=5)
    _vote(db, reviews[:2], _voters(db, 7))
    _spread(db, reviews, _voters(db, 11))
    snapshots = []
    for _ in range(3):
        recompute_user_trust(db, author.id)
        db.flush()
        db.refresh(author)
        snapshots.append((author.trust_stage, Decimal(author.reputation_score),
                          Decimal(author.helpfulness_ratio), author.verified_review_count))
    assert snapshots[0] == snapshots[1] == snapshots[2]
    assert datetime.now(UTC) > MATURE              # the fixture's clock is sane


# --- the formula's exact values (pure; docs/TRUST_SCORE_COMPUTATION.md §3–§5) --------

def test_reputation_score_at_its_documented_caps():
    from app.services.trust import reputation_score

    # helpfulness 0.60 x ratio, volume 10 x log10(1 + n) capped at 25,
    # best answers 3 each capped at 15, minus 15 a strike, clamped to 0..100.
    assert reputation_score(100, 0, 0, 0) == 60.0
    assert round(reputation_score(0, 9, 0, 0), 6) == 10.0          # log10(10) = 1
    assert reputation_score(0, 316, 0, 0) == 25.0                   # 10 x log10(317) > 25: capped
    assert reputation_score(0, 0, 5, 0) == 15.0
    assert reputation_score(0, 0, 9, 0) == 15.0                     # capped
    assert reputation_score(100, 316, 5, 0) == 100.0
    assert reputation_score(100, 316, 5, 1) == 85.0
    assert reputation_score(10, 0, 0, 1) == 0.0                     # 6 - 15, clamped


def test_helpfulness_is_the_wilson_lower_bound_of_the_counters():
    from app.services.trust import helpfulness_score

    assert helpfulness_score(0, 0) == 0.0
    assert helpfulness_score(1, 0) == 20.65                          # not 100
    assert helpfulness_score(0, 4) == 0.0
    assert helpfulness_score(3, 1) == 30.06


def test_one_vote_weighs_what_business_rules_11_says():
    from pytest import approx

    from app.services.trust import gate_vote_weight

    # (stage, reputation, account age days, probation, investigation, claimed)
    assert gate_vote_weight(0, 100, 400, False) == approx(0.0)
    assert gate_vote_weight(1, 0, 400, False) == approx(0.25)
    assert gate_vote_weight(2, 60, 400, False) == approx(0.6)              # 1.0 x 60%
    assert gate_vote_weight(3, 60, 400, False) == approx(0.9)              # 1.5 x 60%
    assert gate_vote_weight(5, 100, 400, False) == approx(3.0)
    assert gate_vote_weight(2, 60, 29, False) == approx(0.3)               # under 30 days: half
    assert gate_vote_weight(2, 60, 30, False) == approx(0.6)               # day 30: full
    assert gate_vote_weight(2, 60, 400, False, True) == approx(0.3)        # investigation: half
    assert gate_vote_weight(2, 60, 5, False, True) == approx(0.15)         # both: a quarter
    assert gate_vote_weight(5, 100, 400, True, True) == approx(0.0)        # probation wins
    assert gate_vote_weight(5, 100, 400, False, False, True) == approx(0.0)  # claimed seller

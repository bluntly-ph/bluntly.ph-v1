"""An administrator's or super admin's upvote nominates the review for the
earnings queue (owner, 2026-10-06).

"ADMIN / SUPER ADMIN UPVOTE -> REVIEW IS NOMINATED / ROUTED TO THE EARNINGS
REVIEW QUEUE." Not a heavier community vote: the first fix (PR #16) only
weighted staff votes, so a review still waited for the members' threshold and
Zient found admin-upvoted reviews missing from the queue. Members keep the
existing gate exactly. Queueing is not approval, and nothing is paid from it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import EarnEligibleStatus, VoteDirection
from app.models.review import Review
from app.models.triage import QueueTriage
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import earn_gate
from tests.conftest import make_established, register_and_token, requires_db
from tests.test_priority_triage_api import _auth, _queue, _review

pytestmark = requires_db


@pytest.fixture(autouse=True)
def _post_seeding(monkeypatch):
    # The deployed phase: without a nomination a review earns its place in the
    # queue only through members' votes.
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")


def _fresh_review(client) -> tuple[str, str]:
    token = uuid.uuid4().hex[:10]
    _, author_tok, _ = register_and_token(client)
    return _review(client, _auth(author_tok), token), token


def _status(rid: str) -> EarnEligibleStatus:
    db = SessionLocal()
    try:
        return db.get(Review, uuid.UUID(rid)).earn_eligible_status
    finally:
        db.close()


def _count(model, **where) -> int:
    db = SessionLocal()
    try:
        q = select(func.count()).select_from(model)
        for col, val in where.items():
            q = q.where(getattr(model, col) == val)
        return int(db.scalar(q) or 0)
    finally:
        db.close()


def _vote(client, rid: str, direction: str, headers: dict) -> dict:
    res = client.post(f"/api/v1/reviews/{rid}/vote", headers=headers, json={"vote": direction})
    assert res.status_code == 200, res.text
    return res.json()


def _member(client, stage: int | None = None) -> dict:
    uid, tok, _ = register_and_token(client)
    if stage is not None:
        make_established(uid, stage=stage)
    return _auth(tok)


def _queued_once(client, admin: dict, rid: str, token: str) -> None:
    assert [i["review"]["id"] for i in _queue(client, admin, token)].count(rid) == 1
    assert _count(QueueTriage, target_ref=uuid.UUID(rid)) == 1


# 1. Members keep the existing gate.
def test_a_members_upvotes_still_wait_for_the_community_gate(client):
    rid, _ = _fresh_review(client)
    _vote(client, rid, "up", _member(client, stage=5))     # 3.0
    _vote(client, rid, "up", _member(client, stage=4))     # 2.0
    assert _status(rid) == EarnEligibleStatus.none          # 2 voters, 5.0: short
    _vote(client, rid, "up", _member(client, stage=5))     # 3 voters, 8.0: LB 0.68
    assert _status(rid) == EarnEligibleStatus.pending


# 2, 4, 5, 6: an administrator's upvote queues at once, once, unapproved, unpaid.
@pytest.mark.parametrize("role", ["administrator", "super_admin"])  # 3: both staff roles
def test_a_staff_upvote_nominates_the_review_into_the_queue_once(client, role):
    rid, token = _fresh_review(client)
    _, tok, _ = register_and_token(client, role=role)
    admin = _auth(tok)

    body = _vote(client, rid, "up", admin)
    assert body["my_vote"] == "up"
    assert _status(rid) == EarnEligibleStatus.pending      # queued, not approved
    _queued_once(client, admin, rid, token)

    _vote(client, rid, "up", admin)                        # pressed again
    assert _count(ReviewVote, review_id=uuid.UUID(rid)) == 1
    assert _status(rid) == EarnEligibleStatus.pending
    _queued_once(client, admin, rid, token)

    assert _count(Commission, review_id=uuid.UUID(rid)) == 0   # nothing paid


# The staff vote itself is an ordinary vote again: no extra gate weight.
def test_a_staff_vote_carries_the_voters_own_trust_weight(client):
    rid, _ = _fresh_review(client)
    admin_id, tok, _ = register_and_token(client, role="administrator")
    _vote(client, rid, "up", _auth(tok))
    db = SessionLocal()
    try:
        row = db.scalar(select(ReviewVote).where(ReviewVote.review_id == uuid.UUID(rid)))
        assert row.voter_id == uuid.UUID(admin_id)
        assert row.vote_weight == Decimal("0.0000") and row.trust_stage_snapshot == 0
    finally:
        db.close()


def test_a_staff_downvote_nominates_nothing(client):
    rid, _ = _fresh_review(client)
    _, tok, _ = register_and_token(client, role="administrator")
    _vote(client, rid, "down", _auth(tok))
    assert _status(rid) == EarnEligibleStatus.none


# 7. No self-vote.
def test_an_admin_cannot_upvote_their_own_review(client):
    _, tok, _ = register_and_token(client, role="administrator")
    headers = _auth(tok)
    rid = _review(client, headers, uuid.uuid4().hex[:10])
    res = client.post(f"/api/v1/reviews/{rid}/vote", headers=headers, json={"vote": "up"})
    assert res.status_code == 409
    assert res.json()["code"] == "cannot_vote_own_review"
    assert _status(rid) == EarnEligibleStatus.none


# 8. Taking the vote back or flipping it leaves the queue as it was.
def test_removing_or_changing_the_vote_does_not_disturb_the_queue(client):
    rid, token = _fresh_review(client)
    _, tok, _ = register_and_token(client, role="super_admin")
    admin = _auth(tok)
    _vote(client, rid, "up", admin)
    _vote(client, rid, "down", admin)
    assert _status(rid) == EarnEligibleStatus.pending
    _queued_once(client, admin, rid, token)
    assert client.delete(f"/api/v1/reviews/{rid}/vote", headers=admin).status_code == 200
    assert _status(rid) == EarnEligibleStatus.pending
    _queued_once(client, admin, rid, token)
    _vote(client, rid, "up", admin)                        # and back again
    _queued_once(client, admin, rid, token)


def test_a_decided_review_is_not_reopened_by_a_staff_upvote(client):
    rid, _ = _fresh_review(client)
    db = SessionLocal()
    try:
        db.get(Review, uuid.UUID(rid)).earn_eligible_status = EarnEligibleStatus.rejected
        db.commit()
    finally:
        db.close()
    _, tok, _ = register_and_token(client, role="administrator")
    _vote(client, rid, "up", _auth(tok))
    assert _status(rid) == EarnEligibleStatus.rejected


# 9, 10. Upvotes cast before the rule: reconciled, once, however often it runs.
def _old_staff_upvote(rid: str, admin_id: str, weight: str = "3.0", stage: int = 5) -> None:
    """A vote row exactly as production holds it: cast before upvotes nominated
    (and, from PR #16, snapshotted at 3.0 / Stage 5)."""
    db = SessionLocal()
    try:
        db.add(ReviewVote(review_id=uuid.UUID(rid), voter_id=uuid.UUID(admin_id),
                          vote=VoteDirection.up, vote_weight=Decimal(weight),
                          trust_stage_snapshot=stage))
        db.commit()
    finally:
        db.close()


def test_the_backfill_queues_old_staff_upvotes_once_and_is_idempotent(client):
    old, token = _fresh_review(client)
    member_only, _ = _fresh_review(client)
    admin_id, tok, _ = register_and_token(client, role="administrator")
    admin = _auth(tok)
    _old_staff_upvote(old, admin_id)
    _vote(client, member_only, "up", _member(client, stage=2))
    assert _status(old) == EarnEligibleStatus.none

    db = SessionLocal()
    try:
        first = earn_gate.reconcile_staff_upvotes(db)
        db.commit()
        again = earn_gate.reconcile_staff_upvotes(db)
        db.commit()
        row = db.scalar(select(ReviewVote).where(ReviewVote.review_id == uuid.UUID(old)))
        admin = db.get(User, uuid.UUID(admin_id))
        assert row.vote_weight == Decimal("0.0000")          # PR #16's 3.0 undone
        assert row.trust_stage_snapshot == admin.trust_stage
    finally:
        db.close()

    assert first >= 1 and again == 0
    assert _status(old) == EarnEligibleStatus.pending
    assert _status(member_only) == EarnEligibleStatus.none   # members untouched
    _queued_once(client, _auth(tok), old, token)
    assert _count(Commission, review_id=uuid.UUID(old)) == 0


def test_the_backfill_is_the_allow_listed_maintenance_task(client):
    """Production runs it through the scheduler endpoint (workflow_dispatch
    task `reconcile_admin_upvotes`); this is that task's body."""
    from app.api.v1.routes import internal_cron
    rid, token = _fresh_review(client)
    admin_id, tok, _ = register_and_token(client, role="super_admin")
    _old_staff_upvote(rid, admin_id)
    db = SessionLocal()
    try:
        assert internal_cron.TASKS["reconcile_admin_upvotes"].run(db) >= 1
        db.commit()
    finally:
        db.close()
    assert _status(rid) == EarnEligibleStatus.pending
    _queued_once(client, _auth(tok), rid, token)

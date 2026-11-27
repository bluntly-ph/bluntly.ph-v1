"""Admin queue priority tiers on a real database (dev note 2026-09-26).

What the pure matrix (test_priority_tiers.py) cannot show:

* the tiers ride on the real earn_eligible and report queues, sort and filter
  there, and explain themselves;
* computing tiers and running the hourly job NEVER put an item into a queue,
  take one out, or change any review's earning state — the most important
  regression of the brief;
* aging moves an item exactly one tier after the window, is set by the
  scheduled job and not by reads, is not reset by a moderator opening the item,
  and IS reset by a decision;
* the thresholds are read by moderators and changed only by the site owner.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.enums import (
    EarnEligibleStatus,
    MemberRole,
    ModerationReason,
    ModerationTargetType,
    VoteDirection,
)
from app.models.review import Review
from app.models.triage import PlatformSetting, QueueTriage
from app.models.user import User
from app.models.vote import ReviewVote
from app.services import priority_triage, report_service
from app.services.referral_service import _all_queue_candidates
from tests.conftest import (
    make_user,
    owned_photo_url,
    register_and_token,
    requires_db,
    set_trust_stage,
)

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _review(client, headers, token: str) -> str:
    pid = client.post("/api/v1/products", headers=headers,
                      json={"name": f"Tier {token}", "category": "electronics"}).json()["id"]
    res = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": pid, "title": "Tiered", "discussion": f"Fixture {token}. Solid for weeks.",
        "verdict": "yes_absolutely", "star_rating": 4, "photo_url": owned_photo_url(headers)})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _queue(client, mh, token: str, **params) -> list[dict]:
    query = "&".join(f"{k}={v}" for k, v in {"q": token, "limit": 100, **params}.items())
    res = client.get(f"/api/v1/admin/review-queue?{query}", headers=mh)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _all_reports(client, mh, query: str) -> list[dict]:
    """Every open report for `query`, page by page — a shared database may
    hold hundreds of older open reports ahead of this test's own."""
    items: list[dict] = []
    offset = 0
    while True:
        page = client.get(f"/api/v1/admin/reports?{query}&limit=100&offset={offset}",
                          headers=mh).json()
        items += page["items"]
        offset += 100
        if offset >= page["total"]:
            return items


def _mod(client) -> dict:
    _, token, _ = register_and_token(client, role="administrator")
    return _auth(token)


def _upvote(review_id: str, voter: User, *, weight: str = "1.0") -> None:
    db = SessionLocal()
    try:
        db.add(ReviewVote(review_id=uuid.UUID(review_id), voter_id=voter.id,
                          vote=VoteDirection.up, vote_weight=Decimal(weight),
                          trust_stage_snapshot=2))
        db.commit()
    finally:
        db.close()


def _report(review_id: str, author_id: str, reason: ModerationReason) -> None:
    db = SessionLocal()
    try:
        reporter = make_user(db)
        db.commit()
        report_service.file_report(
            db, reporter_id=reporter.id, author_id=uuid.UUID(author_id),
            target_type=ModerationTargetType.review, target_ref=uuid.UUID(review_id),
            reason=reason)
    finally:
        db.close()


def test_new_account_first_review_is_high_and_trusted_author_is_low_sorted_by_tier(client):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    new_id, new_tok, _ = register_and_token(client)
    first = _review(client, _auth(new_tok), token)
    set_trust_stage(new_id, 0)

    old_id, old_tok, _ = register_and_token(client)
    _review(client, _auth(old_tok), f"{token} earlier")
    trusted = _review(client, _auth(old_tok), token)
    set_trust_stage(old_id, 3)

    items = {i["review"]["id"]: i for i in _queue(client, mh, token)}
    assert items[first]["triage"]["tier"] == "high"
    assert [r["code"] for r in items[first]["triage"]["reasons"]] == ["stage0_first_submission"]
    assert items[trusted]["triage"]["tier"] == "low"

    ordered = [i["review"]["id"] for i in _queue(client, mh, token, sort="tier")]
    assert ordered.index(first) < ordered.index(trusted)
    only_low = [i["review"]["id"] for i in _queue(client, mh, token, tier="low")]
    assert trusted in only_low and first not in only_low


def test_a_flagged_upvoter_and_two_fraud_reports_converge_to_highest(client):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    author_id, author_tok, _ = register_and_token(client)
    _review(client, _auth(author_tok), f"{token} earlier")
    rid = _review(client, _auth(author_tok), token)
    set_trust_stage(author_id, 2)

    db = SessionLocal()
    try:
        risky = make_user(db, is_under_investigation=True)
        db.commit()
        _upvote(rid, risky, weight="0.5")
    finally:
        db.close()
    _report(rid, author_id, ModerationReason.fake_proof)
    _report(rid, author_id, ModerationReason.counterfeit)

    card = _queue(client, mh, token)[0]
    assert card["review"]["id"] == rid
    triage = card["triage"]
    assert triage["tier"] == "highest", triage
    codes = {r["code"] for r in triage["reasons"]}
    assert {"risky_upvoter", "fraud_reports"} <= codes

    mine = [r for r in _all_reports(client, mh, "sort=tier") if r["report"]["target_ref"] == rid]
    assert len(mine) == 2 and all(r["triage"]["tier"] == "highest" for r in mine)
    filtered = _all_reports(client, mh, "tier=highest")
    assert {r["report"]["target_ref"] for r in filtered} >= {rid}
    assert all(r["triage"]["tier"] == "highest" for r in filtered)


def test_priority_never_puts_an_item_into_a_queue_or_changes_its_state(client, monkeypatch):
    """The most important regression: tiers are computed only for what is
    already queued. A Post-Seeding review with votes squarely in the Wilson
    band, which the gate has NOT queued, stays out of every queue through the
    tier reads and the hourly job, and nothing's earning state moves."""
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    _, author_tok, _ = register_and_token(client)
    rid = _review(client, _auth(author_tok), token)

    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(rid))
        assert review.earn_eligible_status == EarnEligibleStatus.none
        voters = [make_user(db) for _ in range(3)]
        db.commit()
    finally:
        db.close()
    for voter in voters:   # weighted into the 0.60-0.70 band the tiers flag
        _upvote(rid, voter, weight="2.0")
    db = SessionLocal()
    try:
        before = {(r.id, kind, r.earn_eligible_status) for r, kind in _all_queue_candidates(db)}
        statuses_before = dict(db.execute(
            Review.__table__.select().with_only_columns(
                Review.id, Review.earn_eligible_status)).all())
    finally:
        db.close()

    assert _queue(client, mh, token) == []
    client.get("/api/v1/admin/reports", headers=mh)
    db = SessionLocal()
    try:
        priority_triage.recalculate(db, now=datetime.now(UTC) + timedelta(days=10))
        after = {(r.id, kind, r.earn_eligible_status) for r, kind in _all_queue_candidates(db)}
        statuses_after = dict(db.execute(
            Review.__table__.select().with_only_columns(
                Review.id, Review.earn_eligible_status)).all())
        assert after == before
        assert statuses_after == statuses_before
        assert db.get(Review, uuid.UUID(rid)).earn_eligible_status == EarnEligibleStatus.none
        assert db.query(QueueTriage).filter(
            QueueTriage.target_ref == uuid.UUID(rid)).count() == 0
    finally:
        db.close()


def test_aging_moves_one_tier_after_the_window_and_viewing_does_not_reset_it(client):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    author_id, author_tok, _ = register_and_token(client)
    _review(client, _auth(author_tok), f"{token} earlier")
    rid = _review(client, _auth(author_tok), token)
    set_trust_stage(author_id, 2)

    assert _queue(client, mh, token)[0]["triage"]["tier"] == "neutral"

    db = SessionLocal()
    try:
        # Before the window: the job records the item and ages nothing.
        priority_triage.recalculate(db, now=datetime.now(UTC) + timedelta(hours=10))
        row = db.query(QueueTriage).filter(QueueTriage.target_ref == uuid.UUID(rid)).one()
        assert row.aged_at is None
        entered = row.entered_at
        # Past it: aged once.
        priority_triage.recalculate(db, now=datetime.now(UTC) + timedelta(hours=73))
        db.refresh(row)
        assert row.aged_at is not None
        aged_at = row.aged_at
    finally:
        db.close()

    card = _queue(client, mh, token)[0]
    assert card["triage"]["tier"] == "high"          # Neutral -> High, not Highest
    assert card["triage"]["base_tier"] == "neutral"
    assert card["triage"]["aged"] is True
    assert card["triage"]["reasons"][-1]["code"] == "aged"

    # A moderator opening and previewing the item is not a decision.
    assert client.get(f"/api/v1/reviews/{rid}", headers=mh).status_code == 200
    assert client.get(f"/api/v1/reviews/{rid}/full", headers=mh).status_code == 200
    _queue(client, mh, token)
    db = SessionLocal()
    try:
        # Running the job again much later still ages it only ONE tier.
        priority_triage.recalculate(db, now=datetime.now(UTC) + timedelta(hours=400))
        row = db.query(QueueTriage).filter(QueueTriage.target_ref == uuid.UUID(rid)).one()
        assert row.entered_at == entered and row.aged_at == aged_at
    finally:
        db.close()
    assert _queue(client, mh, token)[0]["triage"]["tier"] == "high"


def test_a_decision_restarts_the_clock_and_voids_the_aging(client):
    """Reports queue: two open reports, aged; a moderator dismisses one. The
    item stays in the queue on the other report, and its clock restarts."""
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    author_id, author_tok, _ = register_and_token(client)
    _review(client, _auth(author_tok), f"{token} earlier")
    rid = _review(client, _auth(author_tok), token)
    set_trust_stage(author_id, 2)
    _report(rid, author_id, ModerationReason.spam)
    _report(rid, author_id, ModerationReason.spam)

    db = SessionLocal()
    try:
        # Filed 80 hours ago, then the hourly job runs now: past the window.
        from app.models.moderation import ModerationLog
        db.query(ModerationLog).filter(ModerationLog.target_ref == uuid.UUID(rid)).update(
            {ModerationLog.created_at: datetime.now(UTC) - timedelta(hours=80)},
            synchronize_session=False)
        db.commit()
        priority_triage.recalculate(db)
    finally:
        db.close()

    def mine():
        items = client.get("/api/v1/admin/reports?sort=oldest&limit=100",
                           headers=mh).json()["items"]
        return [r for r in items if r["report"]["target_ref"] == rid]

    aged = mine()
    assert len(aged) == 2 and all(r["triage"]["aged"] for r in aged)
    first = aged[0]["report"]["id"]
    dismissed = client.post(f"/api/v1/admin/reports/{first}/decision", headers=mh,
                            json={"resolution": "dismissed", "notes": "Not spam."})
    assert dismissed.status_code == 200, dismissed.text

    left = mine()
    assert len(left) == 1
    assert left[0]["triage"]["aged"] is False
    db = SessionLocal()
    try:
        priority_triage.recalculate(db, now=datetime.now(UTC) + timedelta(hours=1))
        row = db.query(QueueTriage).filter(QueueTriage.target_ref == uuid.UUID(rid),
                                           QueueTriage.queue == "reports").one()
        assert row.aged_at is None
    finally:
        db.close()


@pytest.fixture
def owner(db):
    """A Super Admin: the one role that retunes the tiers (owner decision D)."""
    user = make_user(db, role=MemberRole.super_admin)
    db.commit()
    try:
        yield {"Authorization": f"Bearer {create_access_token(user.id, 'super_admin')}"}
    finally:
        db.query(PlatformSetting).filter(PlatformSetting.key == "priority_tiers").delete()
        db.commit()


def test_moderators_read_the_thresholds_and_only_the_owner_changes_them(client, owner):
    mh = _mod(client)
    read = client.get("/api/v1/admin/priority-settings", headers=mh)
    assert read.status_code == 200
    assert read.json()["wilson_band_low"] == 0.6 and read.json()["aging_hours"] == 72

    _, user_tok, _ = register_and_token(client)
    assert client.get("/api/v1/admin/priority-settings",
                      headers=_auth(user_tok)).status_code == 403
    assert client.put("/api/v1/admin/priority-settings", headers=mh,
                      json={"aging_hours": 48}).status_code == 403

    bad = client.put("/api/v1/admin/priority-settings", headers=owner,
                     json={"wilson_band_low": 0.9})
    assert bad.status_code == 422
    ok = client.put("/api/v1/admin/priority-settings", headers=owner, json={"aging_hours": 48})
    assert ok.status_code == 200 and ok.json()["aging_hours"] == 48
    assert ok.json()["wilson_band_low"] == 0.6   # untouched keys keep their value
    assert client.get("/api/v1/admin/priority-settings",
                      headers=mh).json()["aging_hours"] == 48

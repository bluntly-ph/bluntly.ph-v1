"""Investigate a review (Figma Overlay/Review/Investigate 8109–8117)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.models.enums import VoteDirection
from app.models.integrity import VoteNetworkFingerprint
from app.models.vote import ReviewVote
from app.services import review_investigation as ri
from tests.conftest import register_and_token, requires_db
from tests.test_payout_tips import _review, _user

pytestmark = requires_db

NOW = datetime(2030, 5, 1, 4, 0, tzinfo=UTC)


def _vote(db, review, voter, at, up=True, stage=2):
    db.add(ReviewVote(review_id=review.id, voter_id=voter.id,
                      vote=VoteDirection.up if up else VoteDirection.down,
                      vote_weight=D("1.0"), trust_stage_snapshot=stage, created_at=at))
    db.flush()


def test_flags_shared_networks_and_the_voting_circle_and_recomputes_the_gate(db):
    author = _user(db)
    older = [_review(db, author, published=NOW - timedelta(days=10 - i)) for i in range(5)]
    target = _review(db, author, published=NOW)
    a, b, circle, honest, late = (_user(db, trust_stage=2, created_at=NOW - timedelta(days=400))
                                  for _ in range(5))
    for r in older:
        _vote(db, r, circle, (r.published_at or NOW) + timedelta(minutes=1))
    _vote(db, older[0], honest, NOW - timedelta(days=9))
    _vote(db, target, a, NOW + timedelta(minutes=1))
    _vote(db, target, b, NOW + timedelta(minutes=2))
    _vote(db, target, circle, NOW + timedelta(minutes=3))
    _vote(db, target, honest, NOW + timedelta(hours=5))
    _vote(db, target, late, NOW + timedelta(hours=6), up=False)
    for v in (a, b):
        db.add(VoteNetworkFingerprint(review_id=target.id, voter_id=v.id, author_id=author.id,
                                      network="n" * 32, new_account=False))
    db.flush()

    i = ri.build(db, target, now=NOW + timedelta(days=1))
    flagged = {v.voter_id for v in i.voters if v.flagged}
    assert flagged == {a.id, b.id, circle.id}
    assert (i.votes_total, i.up, i.down, i.first_10_min, i.flagged) == (5, 4, 1, 3, 3)
    assert i.voters[0].flagged and not i.voters[-1].flagged
    row = {v.voter_id: v for v in i.voters}
    assert [s.kind for s in row[a.id].signals] == ["same_network"]
    assert "voting_circle" in [s.kind for s in row[circle.id].signals]
    assert "always_quick" in [s.kind for s in row[circle.id].signals]
    # The strip covers the author's 6 reviews, oldest first: the circle up-voted all.
    assert i.history_size == 6 and row[circle.id].agreement == 6
    assert row[honest.id].history[0] == "up" and row[honest.id].agreement == 2
    assert row[late.id].vote == "down" and row[late.id].seconds_after == 6 * 3600
    # Overlay/Review/Voters/All: each vote's weight in the score.
    assert row[honest.id].weight == 1.0
    # Without the three flagged voters only one up and one down remain.
    assert i.gate_all.voters == 5 and i.gate_without_flagged.voters == 2
    assert i.gate_without_flagged.wilson_lower_bound < i.gate_all.wilson_lower_bound


def test_new_accounts_are_named_but_not_flagged_on_age_alone(db):
    author = _user(db)
    target = _review(db, author, published=NOW)
    fresh = _user(db, created_at=NOW - timedelta(days=9))
    _vote(db, target, fresh, NOW + timedelta(minutes=30), stage=0)
    i = ri.build(db, target, now=NOW)
    (row,) = i.voters
    assert [s.label for s in row.signals] == ["9-day-old account"] and not row.flagged


def test_endpoint_is_staff_only(client, db):
    _, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    author = _user(db)
    review = _review(db, author, published=NOW)
    product = review.product_id
    db.commit()  # the API reads through its own session
    try:
        url = f"/api/v1/admin/reviews/{review.id}/investigation"
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": f"Bearer {member}"}).status_code == 403
        body = client.get(url, headers={"Authorization": f"Bearer {admin}"}).json()
        assert body["votes_total"] == 0 and body["gate_all"]["threshold"] == 0.65
    finally:
        from app.models.product import Product
        db.delete(review)
        db.flush()
        db.delete(db.get(Product, product))
        db.delete(author)
        db.commit()
    missing = "/api/v1/admin/reviews/00000000-0000-0000-0000-000000000000/investigation"
    assert client.get(missing, headers={"Authorization": f"Bearer {admin}"}).status_code == 404

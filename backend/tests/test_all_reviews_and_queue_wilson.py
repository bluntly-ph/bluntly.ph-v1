"""Review Queue / Wilson Score / All Reviews (QA, 2026-09-29).

The report: "The Review Queue displays the Wilson Score from an older review
record and does not appear to fetch the newly submitted review."

Reproduced on a real database before any change:

* Under Post-Seeding, the deployed default, a review written a minute ago is
  NOT in the Review Queue: its earning state is `none` until its trust-weighted
  votes pass the Business Rules §2 gate. The rows the queue does show are
  older reviews, each with ITS OWN Wilson. Nothing leaks between rows. The
  engineering suites never showed this because they run the Seeding phase,
  where every new review is queued at once (tests/conftest.py).
* Membership is the business rule and stays. The fix is an All Reviews list
  beside the queue, with every review and both of its Wilson figures, and the
  queue saying which phase it runs under.

Found on the way: a review whose votes vanished (a voter's account deleted,
`review_votes.voter_id` cascades) was never re-counted, because the nightly
sweep only visited reviews that still had a vote.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.review import Review
from app.models.user import User
from app.services import vote_service
from tests.conftest import register_and_token, requires_db, set_trust_stage
from tests.test_priority_triage_api import _auth, _mod, _queue, _review

pytestmark = requires_db


def _voter(client, stage: int | None = None, reputation: int = 0) -> tuple[str, dict]:
    uid, tok, _ = register_and_token(client)
    if stage is not None:
        set_trust_stage(uid, stage)
    if reputation:
        db = SessionLocal()
        try:
            db.get(User, uuid.UUID(uid)).reputation_score = Decimal(reputation)
            db.commit()
        finally:
            db.close()
    return uid, _auth(tok)


def _vote(client, rid: str, direction: str, stage: int | None = None,
          reputation: int = 0) -> tuple[str, dict]:
    uid, headers = _voter(client, stage, reputation)
    res = client.post(f"/api/v1/reviews/{rid}/vote", headers=headers, json={"vote": direction})
    assert res.status_code == 200, res.text
    return uid, headers


def _all(client, mh, **params) -> dict:
    query = "&".join(f"{k}={v}" for k, v in {"limit": 100, **params}.items())
    res = client.get(f"/api/v1/admin/reviews?{query}", headers=mh)
    assert res.status_code == 200, res.text
    return res.json()


def _row(page: dict, rid: str) -> dict:
    return next(i for i in page["items"] if i["id"] == rid)


def _stored(rid: str) -> Review:
    db = SessionLocal()
    try:
        return db.get(Review, uuid.UUID(rid))
    finally:
        db.close()


def _recomputed_wilson(rid: str) -> Decimal:
    """The canonical recompute (`vote_service`), run without committing."""
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(rid))
        vote_service.recompute_review_vote_aggregates(db, review)
        value = Decimal(str(review.wilson_score))
        db.rollback()
        return value
    finally:
        db.close()


def test_a_new_review_is_in_all_reviews_with_its_own_wilson_but_not_yet_in_the_queue(
        client, monkeypatch):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    # A: older, queued, 3 up / 1 down.
    monkeypatch.setattr(settings, "earn_gate_phase", "seeding")
    _, a_tok, _ = register_and_token(client)
    a = _review(client, _auth(a_tok), token)
    for d in ("up", "up", "up", "down"):
        _vote(client, a, d)
    # B: written afterwards under the deployed default, 1 up / 2 down.
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    _, b_tok, _ = register_and_token(client)
    b = _review(client, _auth(b_tok), f"{token} later")
    for d in ("up", "down", "down"):
        _vote(client, b, d)

    queue = client.get(f"/api/v1/admin/review-queue?q={token}&limit=100", headers=mh).json()
    assert [i["review"]["id"] for i in queue["items"]] == [a]      # B is not queued...
    assert queue["earn_gate_phase"] == "post_seeding"              # ...and the page says why
    assert _stored(b).earn_eligible_status.value == "none"

    page = _all(client, mh, q=token)
    assert {i["id"] for i in page["items"]} == {a, b}              # ...but All Reviews has it
    row_a, row_b = _row(page, a), _row(page, b)
    assert row_a["in_review_queue"] is True and row_b["in_review_queue"] is False
    assert (row_a["helpful_votes"], row_a["unhelpful_votes"]) == (3, 1)
    assert (row_b["helpful_votes"], row_b["unhelpful_votes"]) == (1, 2)
    # Each row's Wilson is that review's own: the stored figure, which the
    # canonical recompute reproduces, and never the other row's.
    for rid, row in ((a, row_a), (b, row_b)):
        public = client.get(f"/api/v1/reviews/{rid}").json()["wilson_score"]
        assert Decimal(row["wilson_score"]) == Decimal(public)
        assert abs(Decimal(row["wilson_score"]) - _recomputed_wilson(rid)) < Decimal("0.0001")
    assert Decimal(row_a["wilson_score"]) > Decimal(row_b["wilson_score"]) > 0
    queued_a = queue["items"][0]
    assert Decimal(queued_a["review"]["wilson_score"]) == Decimal(row_a["wilson_score"])


def test_every_queue_row_carries_its_own_wilson(client, monkeypatch):
    """Five reviews with five vote patterns: no row shows another's figure."""
    monkeypatch.setattr(settings, "earn_gate_phase", "seeding")
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    patterns = [("up",), ("up", "up"), ("down",), ("up", "down"), ()]
    ids = []
    for n, pattern in enumerate(patterns):
        _, tok, _ = register_and_token(client)
        rid = _review(client, _auth(tok), f"{token} {n}")
        for d in pattern:
            _vote(client, rid, d)
        ids.append(rid)
    queue = {i["review"]["id"]: i for i in _queue(client, mh, token)}
    assert set(queue) == set(ids)
    for rid in ids:
        assert Decimal(queue[rid]["review"]["wilson_score"]) == Decimal(
            str(_stored(rid).wilson_score))
    values = [Decimal(queue[rid]["review"]["wilson_score"]) for rid in ids]
    assert len(set(values[:2] + values[3:4])) == 3        # distinct patterns, distinct figures


def test_wilson_at_the_edges_and_after_votes_disappear(client):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    _, tok, _ = register_and_token(client)
    none_ = _review(client, _auth(tok), f"{token} none")
    _, tok, _ = register_and_token(client)
    ups = _review(client, _auth(tok), f"{token} ups")
    _, tok, _ = register_and_token(client)
    downs = _review(client, _auth(tok), f"{token} downs")
    for _ in range(3):
        _vote(client, ups, "up")
        _vote(client, downs, "down")
    page = _all(client, mh, q=token)
    assert Decimal(_row(page, none_)["wilson_score"]) == 0          # no votes
    assert Decimal(_row(page, ups)["wilson_score"]) > Decimal("0.4")  # 3/3 up: LB 0.438
    assert Decimal(_row(page, downs)["wilson_score"]) == 0          # only down-votes

    # A vote taken back counts no more, at once.
    _, voter = _vote(client, none_, "up")
    assert Decimal(_row(_all(client, mh, q=token), none_)["wilson_score"]) > 0
    assert client.delete(f"/api/v1/reviews/{none_}/vote", headers=voter).status_code == 200
    row = _row(_all(client, mh, q=token), none_)
    assert (row["helpful_votes"], Decimal(row["wilson_score"])) == (0, 0)

    # A voter's account deleted: the vote row cascades away. The nightly sweep
    # used to skip the review (no vote left to find it by), keeping 1 up for ever.
    uid, _ = _vote(client, none_, "up")
    db = SessionLocal()
    try:
        db.execute(delete(User).where(User.id == uuid.UUID(uid)))
        db.commit()
        assert db.get(Review, uuid.UUID(none_)).helpful_votes == 1      # stale until the sweep
        assert uuid.UUID(none_) in set(vote_service.voted_review_ids(db))
        vote_service.recompute_all_wilson_scores(db)
    finally:
        db.close()
    row = _row(_all(client, mh, q=token), none_)
    assert (row["helpful_votes"], Decimal(row["wilson_score"])) == (0, 0)


def test_the_public_wilson_counts_every_vote_and_the_gate_wilson_weighs_them(client):
    """ADR-004: visibility votes are equal-weight; the §2 gate is trust-weighted.
    A Stage 0 reader's up-vote moves the public figure, and weighs 0 in the gate."""
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    _, tok, _ = register_and_token(client)
    rid = _review(client, _auth(tok), token)
    _vote(client, rid, "up", stage=0)
    row = _row(_all(client, mh, q=token), rid)
    assert Decimal(row["wilson_score"]) > 0
    assert row["gate"] == {"wilson_lower_bound": 0.0, "effective_total": 0.0,
                           "stage2_plus_voters": 0, "passes": False}
    for _ in range(3):   # §11: Stage 2 weighs multiplier x reputation/100
        _vote(client, rid, "up", stage=2, reputation=60)
    gate = _row(_all(client, mh, q=token), rid)["gate"]
    assert gate["stage2_plus_voters"] == 3 and gate["effective_total"] > 0
    # The same arithmetic as the per-review gate endpoint: one implementation.
    single = client.get(f"/api/v1/admin/reviews/{rid}/gate", headers=mh).json()
    assert {k: single[k] for k in gate} == gate


def test_sorting_by_wilson_both_ways_and_paging_one_at_a_time(client):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    by_votes = {}
    for n, pattern in enumerate([("up",) * 4, ("up", "down"), ("down", "down")]):
        _, tok, _ = register_and_token(client)
        rid = _review(client, _auth(tok), f"{token} {n}")
        for d in pattern:
            _vote(client, rid, d)
        by_votes[n] = rid
    high_to_low = [i["id"] for i in _all(client, mh, q=token, sort="wilson_desc")["items"]]
    assert high_to_low == [by_votes[0], by_votes[1], by_votes[2]]
    low_to_high = [i["id"] for i in _all(client, mh, q=token, sort="wilson_asc")["items"]]
    assert low_to_high == [by_votes[2], by_votes[1], by_votes[0]]
    newest = [i["id"] for i in _all(client, mh, q=token, sort="newest")["items"]]
    assert newest == [by_votes[2], by_votes[1], by_votes[0]]
    # One per page, the same order, and the total counts every match.
    paged = []
    for offset in range(3):
        page = _all(client, mh, q=token, sort="wilson_desc", limit=1, offset=offset)
        assert page["total"] == 3 and len(page["items"]) == 1
        paged.append(page["items"][0]["id"])
    assert paged == high_to_low
    assert _all(client, mh, q=token, limit=1, offset=3)["items"] == []
    assert client.get("/api/v1/admin/reviews?limit=101", headers=mh).status_code == 422


def test_filters_by_state_earning_product_and_day(client, monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", "seeding")
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    _, tok, _ = register_and_token(client)
    kept = _review(client, _auth(tok), token)
    _, tok, _ = register_and_token(client)
    down = _review(client, _auth(tok), f"{token} down")
    assert client.post(f"/api/v1/admin/reviews/{down}/unpublish", headers=mh,
                       json={"reason": "Test take-down for the All Reviews filter."}
                       ).status_code == 200
    assert {i["id"] for i in _all(client, mh, q=token, state="taken_down")["items"]} == {down}
    assert {i["id"] for i in _all(client, mh, q=token, state="published")["items"]} == {kept}
    taken = _row(_all(client, mh, q=token), down)
    assert taken["state"] == "taken_down" and taken["in_review_queue"] is True
    assert {i["id"] for i in _all(client, mh, q=token, earn="pending")["items"]} >= {kept}
    product = _stored(kept).product_id
    assert [i["id"] for i in _all(client, mh, product_id=product)["items"]] == [kept]
    today = datetime.now(UTC).date()
    assert {i["id"] for i in _all(client, mh, q=token, created_from=today,
                                  created_to=today)["items"]} == {kept, down}
    assert _all(client, mh, q=token, created_to=today - timedelta(days=1))["items"] == []
    # A search is text, never a pattern: "%" matches only a literal "%".
    assert _all(client, mh, q=f"{token}%25")["items"] == []


@pytest.mark.parametrize("role, expected", [("user", 403), ("seller", 403),
                                            ("administrator", 200), ("super_admin", 200)])
def test_only_staff_see_all_reviews(client, role, expected):
    _, tok, _ = register_and_token(client, role=role)
    assert client.get("/api/v1/admin/reviews", headers=_auth(tok)).status_code == expected


def test_all_reviews_needs_a_session(client):
    assert client.get("/api/v1/admin/reviews").status_code == 401


def test_all_reviews_carries_no_money_or_private_fields(client):
    token = uuid.uuid4().hex[:10]
    mh = _mod(client)
    _, tok, _ = register_and_token(client)
    rid = _review(client, _auth(tok), token)
    row = _row(_all(client, mh, q=token), rid)
    # The whole field list, so a money or private field cannot slip in unseen.
    assert set(row) == {
        "id", "reference", "title", "star_rating", "verdict", "state",
        "earn_eligible_status", "in_review_queue", "is_thread_root", "helpful_votes",
        "unhelpful_votes", "wilson_score", "gate", "open_reports", "author", "product",
        "created_at", "published_at"}
    assert set(row["author"]) == {"id", "username", "display_name", "trust_stage"}
    # image_url: the product thumbnail of Figma Queue/AllReviews (public listing image).
    assert set(row["product"]) == {"id", "canonical_name", "image_url"}

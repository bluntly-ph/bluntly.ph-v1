"""Exact rule boundaries (full-system QA, 2026-09-24).

The scenario suites prove each rule far from its edge (a 4-day-old photo, a
95-day-old thread, a 10-day-old account). These pin the edges themselves, so an
off-by-one in either direction fails a test: 72 hours, 3 calendar months, the
30-day account age, and the ₱300 minimum.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.trust import gate_vote_weight
from tests.conftest import owned_photo_url, register_and_token, requires_db
from tests.test_business_rules_api import _auth, _product, _review
from tests.test_payouts_api import _set_wallet

# --- §11: the 30-day account age ------------------------------------------------

@pytest.mark.parametrize("age_days,factor", [(0, 0.5), (29, 0.5), (29.99, 0.5),
                                             (30, 1.0), (31, 1.0), (3650, 1.0)])
def test_the_new_account_halving_ends_at_exactly_thirty_days(age_days, factor):
    full = gate_vote_weight(2, 100.0, 365, False)
    assert gate_vote_weight(2, 100.0, age_days, False) == pytest.approx(full * factor)


# --- §4: the 72-hour photo window and the 3-month cooldown --------------------------

def _set_times(review_id: str, *, published: datetime) -> None:
    from app.db.session import SessionLocal
    from app.models.review import Review
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(review_id))
        review.published_at = published
        review.created_at = published
        db.commit()
    finally:
        db.close()


@requires_db
@pytest.mark.parametrize("age,allowed", [(timedelta(hours=71, minutes=59), True),
                                         (timedelta(hours=72, minutes=1), False)])
def test_the_photo_swap_window_is_exactly_seventy_two_hours(client, age, allowed):
    _, token, _ = register_and_token(client)
    h = _auth(token)
    rid = _review(client, h, _product(client, h))["id"]
    _set_times(rid, published=datetime.now(UTC) - age)
    swap = client.patch(f"/api/v1/reviews/{rid}", headers=h,
                        json={"photo_url": owned_photo_url(h)})
    if allowed:
        assert swap.status_code == 200, swap.text
        assert swap.json()["photo_replaced_at"] is not None
    else:
        assert swap.status_code == 409 and swap.json()["code"] == "photo_swap_window_closed"


@requires_db
@pytest.mark.parametrize("opens_in,allowed", [(timedelta(minutes=5), False),
                                              (timedelta(minutes=-5), True)])
def test_the_update_cooldown_is_exactly_three_calendar_months(client, opens_in, allowed):
    """The root is back-dated so the service's own opening time lands 5 minutes
    from now: 5 minutes early is refused, 5 minutes late is accepted."""
    from app.services.review_service import _add_months
    _, token, _ = register_and_token(client)
    h = _auth(token)
    rid = _review(client, h, _product(client, h))["id"]
    opens = datetime.now(UTC) + opens_in
    published = _add_months(opens, -3)
    if _add_months(published, 3) != opens:
        pytest.skip("month-end day clamping: this date has no exact 3-month preimage")
    _set_times(rid, published=published)
    update = client.post(f"/api/v1/reviews/{rid}/updates", headers=h, json={
        "title": "Three months on", "discussion": "Still going, with one new scratch.",
        "verdict": "yes_absolutely", "star_rating": 4})
    if allowed:
        assert update.status_code == 201, update.text
    else:
        assert update.status_code == 409 and update.json()["code"] == "thread_update_cooldown"


# --- §15: the ₱300 minimum ------------------------------------------------------

@requires_db
@pytest.mark.parametrize("amount,accepted", [("299.99", False), ("300.00", True),
                                             ("300.01", True)])
def test_the_cashout_minimum_is_exactly_three_hundred_pesos(client, amount, accepted):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.payout import Payout
    from app.models.user import User

    uid, token, _ = register_and_token(client)
    _set_wallet(uid, "1000.00")        # a real, cleared inflow — never a bare balance
    resp = client.post("/api/v1/payouts/cashout", headers=_auth(token), json={"amount": amount})
    db = SessionLocal()
    try:
        wallet = db.get(User, uuid.UUID(uid)).wallet_balance
        rows = list(db.scalars(select(Payout).where(Payout.user_id == uuid.UUID(uid))))
    finally:
        db.close()
    if accepted:
        assert resp.status_code == 201, resp.text
        assert [r.amount for r in rows] == [Decimal(amount)]
        assert wallet == Decimal("1000.00") - Decimal(amount)
    else:
        assert resp.status_code == 422 and resp.json()["code"] == "below_payout_minimum"
        assert rows == [] and wallet == Decimal("1000.00")

"""Concurrency invariants (full-system QA, 2026-09-24).

Each test races two real database sessions through a barrier so both reach the
decision point together, then asserts on the rows — not on one lucky
interleaving. Every race here was reproducible before its fix.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from tests.conftest import register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _race(*calls):
    """Run each callable in its own thread, released together. Returns results
    (the value, or the exception it raised) in call order."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def run(i, fn):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 — the test inspects it
            results[i] = exc

    threads = [threading.Thread(target=run, args=(i, fn)) for i, fn in enumerate(calls)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def _product(client, headers) -> str:
    return client.post("/api/v1/products", headers=headers, json={
        "name": f"RaceWidget {uuid.uuid4().hex[:8]}", "category": "electronics",
        "source_url": f"https://shopee.ph/x-i.1.{uuid.uuid4().int % 10**12}"}).json()["id"]


def _payload(product_id: str, n: int):
    from app.schemas.review import ReviewCreate
    return ReviewCreate(product_id=product_id, title=f"Race entry {n}",
                        discussion=f"Concurrency fixture {n} {uuid.uuid4().hex[:6]}.",
                        verdict="yes_absolutely", star_rating=4)


def _create_in_own_session(author_id: str, payload):
    from app.db.session import SessionLocal
    from app.services import review_service
    db = SessionLocal()
    try:
        return review_service.create_review(db, uuid.UUID(author_id), payload).id
    finally:
        db.close()


@requires_db
def test_two_concurrent_first_reviews_make_one_thread(client):
    """§4, D1: a double submit that beats the composer's own guard must still
    leave one thread for the product, and the loser is told why."""
    from app.core.errors import AppError
    from app.db.session import SessionLocal
    from app.models.review import Review

    uid, token, _ = register_and_token(client)
    pid = _product(client, _auth(token))
    results = _race(lambda: _create_in_own_session(uid, _payload(pid, 1)),
                    lambda: _create_in_own_session(uid, _payload(pid, 2)))

    created = [r for r in results if isinstance(r, uuid.UUID)]
    refused = [r for r in results if isinstance(r, AppError)]
    assert len(created) == 1, results
    assert len(refused) == 1 and refused[0].code == "review_thread_exists", results
    db = SessionLocal()
    try:
        roots = db.scalar(select(func.count()).select_from(Review).where(
            Review.author_id == uuid.UUID(uid), Review.product_id == uuid.UUID(pid)))
    finally:
        db.close()
    assert roots == 1


@requires_db
def test_two_concurrent_updates_make_one_entry_per_cooldown(client):
    """§4, D1: two updates racing past the 3-month mark must not both land."""
    from app.core.errors import AppError
    from app.db.session import SessionLocal
    from app.models.review import Review
    from app.schemas.review import ReviewEntryIn
    from app.services import review_service

    uid, token, _ = register_and_token(client)
    pid = _product(client, _auth(token))
    root_id = _create_in_own_session(uid, _payload(pid, 0))
    db = SessionLocal()
    try:                                   # the root is four months old
        root = db.get(Review, root_id)
        root.created_at = datetime.now(UTC) - timedelta(days=125)
        root.published_at = root.created_at
        db.commit()
    finally:
        db.close()

    def update(n):
        def go():
            s = SessionLocal()
            try:
                entry = s.get(Review, root_id)
                return review_service.add_thread_update(s, entry, uuid.UUID(uid), ReviewEntryIn(
                    title=f"Update {n}", discussion=f"Four months on, entry {n}.",
                    verdict="it_depends", star_rating=3)).id
            finally:
                s.close()
        return go

    results = _race(update(1), update(2))
    assert sum(isinstance(r, uuid.UUID) for r in results) == 1, results
    assert any(isinstance(r, AppError) and r.code == "thread_update_cooldown"
               for r in results), results
    db = SessionLocal()
    try:
        entries = db.scalar(select(func.count()).select_from(Review).where(
            Review.thread_id == root_id, Review.id != root_id))
    finally:
        db.close()
    assert entries == 1


@requires_db
def test_concurrent_cashouts_never_draw_on_uncleared_money(client):
    """§19, D2: ₱1,000 in the wallet of which ₱300 has not cleared. Two ₱400
    requests at once must not both pass: together they would spend ₱100 the
    marketplace has not paid yet. The wallet's CHECK (>= 0) cannot see that."""
    from app.core.errors import AppError
    from app.db.session import SessionLocal
    from app.models.commission import Commission
    from app.models.enums import CommissionTarget, Platform
    from app.models.payout import Payout
    from app.models.user import User
    from app.services import payout_service

    uid, token, _ = register_and_token(client)
    rid = client.post("/api/v1/reviews", headers=_auth(token), json={
        "product_id": _product(client, _auth(token)), "title": "Cashout race",
        "discussion": "The review the uncleared commission belongs to.",
        "verdict": "yes_absolutely", "star_rating": 4}).json()["id"]
    # ₱700 of cleared money through a real inflow, then a ₱300 commission
    # credited but not yet cleared: ₱1,000 in the wallet, ₱700 withdrawable, and
    # the wallet still equals its inflows (the invariant supabase_verify checks).
    from app.services import wallet
    from tests.test_payouts_api import _set_wallet
    _set_wallet(uid, "700.00")
    db = SessionLocal()
    try:
        db.add(Commission(
            commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=uuid.UUID(rid), reviewer_id=uuid.UUID(uid), reviewer_share_bps=3000,
            gross_amount=Decimal("1000.00"), platform_share=Decimal("400.00"),
            reviewer_share=Decimal("300.00"), honesty_fund_share=Decimal("300.00"),
            currency="PHP", csv_source=f"race:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=datetime(1998, 6, 1, tzinfo=UTC).date(), platform=Platform.shopee,
            cleared_at=None))
        wallet.adjust(db, uuid.UUID(uid), Decimal("300.00"))
        db.commit()
    finally:
        db.close()

    def cash():
        s = SessionLocal()
        try:
            return payout_service.request_cashout(
                s, s.get(User, uuid.UUID(uid)), Decimal("400.00")).amount
        finally:
            s.close()

    results = _race(cash, cash)
    paid = [r for r in results if isinstance(r, Decimal)]
    assert paid == [Decimal("400.00")], results
    assert any(isinstance(r, AppError) and r.code in ("exceeds_withdrawable",
                                                      "below_payout_minimum")
               for r in results), results

    db = SessionLocal()
    try:
        wallet = db.get(User, uuid.UUID(uid)).wallet_balance
        reserved = db.scalar(select(func.coalesce(func.sum(Payout.amount), 0)).where(
            Payout.user_id == uuid.UUID(uid)))
    finally:
        db.close()
    assert wallet == Decimal("600.00") and reserved == Decimal("400.00")
    assert wallet >= Decimal("300.00"), "the uncleared ₱300 must still be in the wallet"

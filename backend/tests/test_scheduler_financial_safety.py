"""Retry safety for the two scheduled jobs that move money.

The scheduler retries. GitHub Actions can deliver a workflow late, twice, or
overlap two of them, and the continuation loop calls the same endpoint many
times in a row. For the six recompute-style jobs a duplicate run is a wasted
recomputation. For these two it would be a duplicate payment.

So the question here is not "does the claim work" — that is proved against real
concurrent sessions in test_scheduler_state_machine.py. It is the weaker but
more important property underneath it: **even if the claim were bypassed
entirely, would a second run double-pay?** Belt and braces, because the cost of
being wrong is money leaving the system.

Nothing here contacts PayPal. `schedule_payouts` only reserves internal wallet
balances into a batch; submission remains a moderator action on
POST /admin/payouts/run, deliberately not automated.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.models.payout import Payout
from tests.conftest import make_user, requires_db


@requires_db
def test_running_the_batch_twice_never_creates_or_debits_anything(db):
    """Business Rules §15: the batch run only processes reviewers' own
    requests; it never sweeps a balance into a payout by itself, so running it
    twice — or after a failure — cannot double-pay."""
    from app.services.payout_service import request_cashout, schedule_payouts

    user = make_user(db, wallet_balance=Decimal("5000.00"),
                     payout_account=f"payee_{uuid.uuid4().hex[:8]}@example.com")
    bystander = make_user(db, wallet_balance=Decimal("4000.00"),
                          payout_account=f"idle_{uuid.uuid4().hex[:8]}@example.com")
    db.commit()

    when = date(2026, 8, 5)
    request_cashout(db, user, when=when)
    first = schedule_payouts(db, when=when)
    db.commit()
    second = schedule_payouts(db, when=when)
    db.commit()

    rows = db.scalar(select(func.count(Payout.id)).where(Payout.user_id == user.id))
    assert rows == 1, f"a repeated run must not create a second payout; found {rows}"
    assert first.get("scheduled", 0) >= 1
    assert second.get("scheduled", 0) >= 1, "the same request is still the one waiting"
    total = db.scalar(select(func.coalesce(func.sum(Payout.amount), 0))
                      .where(Payout.user_id == user.id))
    assert Decimal(total) == Decimal("5000.00"), "the reserved amount must not double"
    assert db.scalar(select(func.count(Payout.id))
                     .where(Payout.user_id == bystander.id)) == 0, (
        "nobody is paid out without asking")

@requires_db
def test_a_distributed_honesty_fund_cycle_is_not_distributed_again(db):
    """`distribute` aborts on a cycle that already has rows.

    This is what makes the monthly job safe to call every day: the workflow
    fires daily because "the 1st at 02:00 Manila" cannot be expressed in UTC
    cron, so most invocations must find the cycle already done and do nothing.
    """
    from app.models.honesty_fund import HonestyFundDistribution
    from app.services.honesty_fund_service import distribute

    cycle = date(2026, 7, 1)
    before = db.scalar(select(func.count(HonestyFundDistribution.id))
                       .where(HonestyFundDistribution.cycle_month == cycle))

    first = distribute(db, cycle_month=cycle)
    db.commit()
    second = distribute(db, cycle_month=cycle)
    db.commit()

    after = db.scalar(select(func.count(HonestyFundDistribution.id))
                      .where(HonestyFundDistribution.cycle_month == cycle))

    if first.get("recipients", 0):
        assert second["status"] == "already_distributed", (
            "a completed cycle must refuse to distribute again")
        assert after == before + first["recipients"], (
            "the second call must not add distribution rows")
    else:
        # No eligible population in this database — then the invariant to hold
        # is simply that neither call invented one.
        assert after == before
        assert second.get("recipients", 0) == 0


@requires_db
def test_a_retry_covers_new_requests_without_repaying_earlier_ones(db):
    """A request made after one run is picked up by the next, and the earlier
    requester is not paid twice."""
    from app.services.payout_service import request_cashout, schedule_payouts

    paid = make_user(db, wallet_balance=Decimal("3000.00"),
                     payout_account=f"a_{uuid.uuid4().hex[:8]}@example.com")
    db.commit()

    when = date(2026, 8, 6)
    request_cashout(db, paid, when=when)
    schedule_payouts(db, when=when)
    db.commit()

    later = make_user(db, wallet_balance=Decimal("2500.00"),
                      payout_account=f"b_{uuid.uuid4().hex[:8]}@example.com")
    db.commit()
    request_cashout(db, later, when=when)
    schedule_payouts(db, when=when)
    db.commit()

    assert db.scalar(select(func.count(Payout.id))
                     .where(Payout.user_id == paid.id)) == 1, (
        "the earlier requester must not receive a second payout")
    assert db.scalar(select(func.count(Payout.id))
                     .where(Payout.user_id == later.id)) == 1, (
        "the new request is covered")

def test_the_scheduler_does_not_submit_to_a_payment_provider():
    """Preparation is automated; submission is not.

    The old Celery task followed scheduling with `submit_batch`. Turning a step
    a moderator used to take into one that happens unattended is not something
    a scheduler change should do quietly, so the scheduled task stops at
    reserving balances.

    Asked of the AST rather than of the text, because the module's own
    docstring explains why it does not call `submit_batch` — a substring search
    matches the explanation and proves nothing.
    """
    import ast
    import inspect

    from app.api.v1.routes import internal_cron

    tree = ast.parse(inspect.getsource(internal_cron))
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            called.add(fn.attr if isinstance(fn, ast.Attribute)
                       else getattr(fn, "id", None))
    assert "submit_batch" not in called, (
        "the scheduler must not submit payout batches to a provider")

    imported = {alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names}
    assert "submit_batch" not in imported, (
        "the scheduler must not even import the submission path")

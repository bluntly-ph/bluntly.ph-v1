"""The admin Payouts screen's cards (Figma Screen/Admin/Payouts 8024:12721)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.models.enums import PayoutMethod, PayoutStatus
from app.services import payout_service
from tests.conftest import make_user, register_and_token, requires_db


@requires_db
def test_summary_is_staff_only(client):
    _, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    url = "/api/v1/admin/payouts/summary"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": f"Bearer {member}"}).status_code == 403
    body = client.get(url, headers={"Authorization": f"Bearer {admin}"}).json()
    assert {"to_send_total", "to_send_count", "sent_month_total", "waiting_in_wallets",
            "failed_count", "sent_count"} <= set(body)


@requires_db
def test_requests_count_as_to_send_until_paid(db):
    from app.models.payout import Payout

    before = payout_service.admin_summary(db)
    member = make_user(db)
    payout = Payout(user_id=member.id, amount=Decimal("450.00"), status=PayoutStatus.scheduled,
                    method=PayoutMethod.paypal_sandbox, scheduled_for=date.today())
    db.add(payout)
    db.flush()
    during = payout_service.admin_summary(db)
    assert during["to_send_count"] == before["to_send_count"] + 1
    assert during["to_send_total"] == before["to_send_total"] + Decimal("450.00")

    payout.status = PayoutStatus.paid
    payout.paid_at = datetime.now(UTC)
    db.flush()
    after = payout_service.admin_summary(db)
    assert after["to_send_count"] == before["to_send_count"]
    assert after["sent_month_count"] == before["sent_month_count"] + 1


@requires_db
def test_below_minimum_counts_members_who_cannot_cash_out_yet(db, monkeypatch):
    """Overview "Below ₱300 threshold": 0 < withdrawable < the minimum cashout,
    by the same balance rule (withdrawable_from) and the same minimum
    request_cashout refuses below - so exactly the minimum is NOT below it."""
    from app.core.config import settings

    minimum = Decimal(settings.payout_min_php)
    before = payout_service.admin_summary(db)
    assert before["payout_minimum"] == minimum
    below = make_user(db, wallet_balance=minimum - Decimal("0.01"))
    make_user(db, wallet_balance=minimum)                       # can cash out: not below
    make_user(db, wallet_balance=minimum + Decimal("150.00"))   # above
    make_user(db, wallet_balance=Decimal("0.00"))               # nothing to withdraw
    make_user(db, wallet_balance=Decimal("120.00"), is_claimed_seller=True)  # cannot earn
    # Wallet above the minimum, but most of it not cleared yet: 450 - 300 = 150 cleared.
    pending = make_user(db, wallet_balance=Decimal("450.00"))
    # And a wallet that is all uncleared: nothing withdrawable, so not "below".
    locked = make_user(db, wallet_balance=Decimal("200.00"))
    db.flush()
    real = payout_service.uncleared_shares

    def uncleared(session, ids):
        out = real(session, ids)
        out[pending.id] = Decimal("300.00")
        out[locked.id] = Decimal("200.00")
        return out

    monkeypatch.setattr(payout_service, "uncleared_shares", uncleared)
    after = payout_service.admin_summary(db)
    assert after["below_minimum_count"] == before["below_minimum_count"] + 2   # below, pending
    assert below and pending


@requires_db
def test_the_route_carries_the_count_and_the_minimum(client):
    _, admin, _ = register_and_token(client, role="administrator")
    body = client.get("/api/v1/admin/payouts/summary",
                      headers={"Authorization": f"Bearer {admin}"}).json()
    assert isinstance(body["below_minimum_count"], int) and body["below_minimum_count"] >= 0
    assert Decimal(body["payout_minimum"]) == Decimal("300.00")

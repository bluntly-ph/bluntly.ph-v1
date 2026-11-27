"""The contributor Payout screen's figures (Figma Screen/Payout, meeting
2026-10-02 4:12): withdrawable split into commission and Honesty Fund, the
gap to the minimum, money in flight, and the masked payout account."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models.enums import PayoutMethod, PayoutStatus
from app.models.honesty_fund import HonestyFundDistribution
from app.models.payout import Payout
from app.services import payout_service
from tests.conftest import make_user, register_and_token, requires_db

D = Decimal


@requires_db
def test_split_gap_and_in_flight(db):
    member = make_user(db, wallet_balance=D("250.00"))
    db.add(HonestyFundDistribution(
        distribution_id=f"hfd_{uuid.uuid4().hex[:12]}", cycle_month=date(1979, 1, 1),
        reviewer_id=member.id, honesty_score=D("1"), pool_amount=D("100"),
        payout_amount=D("60.00"), created_at=datetime.now(UTC)))
    db.add(Payout(user_id=member.id, amount=D("40.00"), status=PayoutStatus.scheduled,
                  method=PayoutMethod.manual, scheduled_for=date.today()))
    db.flush()
    b = payout_service.member_breakdown(db, member)
    assert (b["withdrawable_commission"], b["withdrawable_honesty_fund"]) == (
        D("190.00"), D("60.00"))
    assert b["short_of_minimum"] == D("50.00")   # 300.00 minimum - 250.00
    assert b["in_flight"] == D("40.00")


@requires_db
def test_balance_endpoint_masks_the_account(client):
    _, token, _ = register_and_token(client)
    auth = {"Authorization": f"Bearer {token}"}
    body = client.get("/api/v1/payouts/balance", headers=auth).json()
    assert body["payout_account_masked"] is None and body["short_of_minimum"] == "300.00"
    assert client.patch("/api/v1/auth/me/payout-account", headers=auth,
                        json={"payout_account": "juan.delacruz@gmail.com"}).status_code == 200
    body = client.get("/api/v1/payouts/balance", headers=auth).json()
    assert body["payout_account_masked"] == "j***@gmail.com"
    assert "juan.delacruz" not in str(body)


@requires_db
def test_account_name_is_kept_and_shown(client):
    """Screen/Payout/Details: the name on the PayPal account, saved with or
    without the address, returned to its owner and to staff paying it."""
    _, token, _ = register_and_token(client)
    h = {"Authorization": f"Bearer {token}"}
    url = "/api/v1/auth/me/payout-account"
    assert client.patch(url, headers=h, json={}).status_code == 422
    assert client.patch(url, headers=h, json={"account_name": "   "}).status_code == 422
    assert client.patch(url, headers=h,
                        json={"account_name": "see https://evil.example"}).status_code == 422
    r = client.patch(url, headers=h, json={"payout_account": "juan@example.com",
                                           "account_name": " Juan  Dela Cruz "})
    assert r.status_code == 200 and r.json()["account_name"] == "Juan Dela Cruz"
    # The name alone: the address stays.
    r = client.patch(url, headers=h, json={"account_name": "Juan D. Cruz"})
    assert r.json() == {"payout_account": "juan@example.com", "account_name": "Juan D. Cruz"}
    body = client.get("/api/v1/payouts/balance", headers=h).json()
    assert body["payout_account_name"] == "Juan D. Cruz"
    assert body["payout_account_masked"] == "j***@example.com"

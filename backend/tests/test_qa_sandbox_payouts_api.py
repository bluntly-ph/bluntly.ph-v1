"""QA sandbox test earnings and the payout steps a QA tester walks through.

Owner decision, 2026-09-27: real QA testers must be able to test getting paid
before the defense. Only accounts the owner names can receive a test earning;
it is cleared at once, withdrawable through the real cashout and payout flow,
audited, announced to the tester, never counted as revenue, and refused on
live PayPal. No test makes a real PayPal call.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.adapters import paypal
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import MemberRole, ModerationAction, PayoutStatus
from app.models.moderation import ModerationLog
from app.models.payout import Payout
from app.models.triage import PlatformSetting
from app.models.user import User
from app.services import admin_overview_service, payout_service, qa_sandbox_service
from tests.conftest import make_user, owned_photo_url, register_and_token, requires_db

pytestmark = requires_db

API = "/api/v1"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner(db):
    """A Super Admin, who manages the tester list (owner decision D).

    The list is shared state in `platform_settings`, so its previous value is
    put back afterwards rather than deleted from under another suite.
    """
    user = make_user(db, role=MemberRole.super_admin)
    db.commit()
    row = db.get(PlatformSetting, qa_sandbox_service.SETTINGS_KEY)
    previous = dict(row.value) if row is not None else None
    try:
        yield {"Authorization": f"Bearer {create_access_token(user.id, 'super_admin')}"}
    finally:
        db.expire_all()
        row = db.get(PlatformSetting, qa_sandbox_service.SETTINGS_KEY)
        if previous is None and row is not None:
            db.delete(row)
        elif row is not None:
            row.value = previous
        db.commit()


def _review(client, headers: dict, tag: str) -> str:
    pid = client.post(f"{API}/products", headers=headers,
                      json={"name": f"QA sandbox {tag}", "category": "electronics"}).json()["id"]
    res = client.post(f"{API}/reviews", headers=headers, json={
        "product_id": pid, "title": f"Sandbox {tag}",
        "discussion": f"QA sandbox fixture {tag}. Used it for weeks.",
        "verdict": "yes_absolutely", "star_rating": 4, "photo_url": owned_photo_url(headers)})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _tester(client, owner: dict) -> tuple[str, dict, str]:
    """A fresh account named as a QA tester, with one published review."""
    uid, token, _email = register_and_token(client)
    headers = _auth(token)
    username = client.get(f"{API}/auth/me", headers=headers).json()["username"]
    res = client.post(f"{API}/admin/qa-sandbox/testers", headers=owner,
                      json={"identifier": f"@{username}"})
    assert res.status_code == 201, res.text
    assert uid in {t["user_id"] for t in res.json()["testers"]}
    return uid, headers, _review(client, headers, uid[:8])


def _mod(client) -> tuple[str, dict]:
    mid, token, _ = register_and_token(client, role="administrator")
    return mid, _auth(token)


def _kinds(client, headers: dict) -> dict[str, dict]:
    rows = client.get(f"{API}/notifications", headers=headers, params={"limit": 50}).json()
    out: dict[str, dict] = {}
    for row in rows:
        out.setdefault(row["kind"], row)
    return out


def _audit(action: ModerationAction, target: str) -> list[ModerationLog]:
    db = SessionLocal()
    try:
        return list(db.scalars(select(ModerationLog).where(
            ModerationLog.action == action,
            ModerationLog.target_ref == uuid.UUID(target))))
    finally:
        db.close()


def test_only_the_owner_names_testers_and_only_staff_see_them(client, owner):
    _, mh = _mod(client)
    _, user_tok, email = register_and_token(client)

    # A moderator can read the list but cannot put anyone on it.
    read = client.get(f"{API}/admin/qa-sandbox/testers", headers=mh)
    assert read.status_code == 200 and read.json()["can_manage_testers"] is False
    assert client.post(f"{API}/admin/qa-sandbox/testers", headers=mh,
                       json={"identifier": email}).status_code == 403
    # A member can do neither.
    assert client.get(f"{API}/admin/qa-sandbox/testers",
                      headers=_auth(user_tok)).status_code == 403

    # The owner names them by email as readily as by username; unknown is a 404.
    added = client.post(f"{API}/admin/qa-sandbox/testers", headers=owner,
                        json={"identifier": email.upper()})
    assert added.status_code == 201, added.text
    assert added.json()["can_manage_testers"] is True
    assert client.post(f"{API}/admin/qa-sandbox/testers", headers=owner,
                       json={"identifier": "nobody_by_this_name_xyz"}).status_code == 404

    listed = {t["user_id"] for t in client.get(
        f"{API}/admin/qa-sandbox/testers", headers=mh).json()["testers"]}
    me = client.get(f"{API}/auth/me", headers=_auth(user_tok)).json()["id"]
    assert me in listed
    assert _audit(ModerationAction.qa_tester_add, me)

    removed = client.delete(f"{API}/admin/qa-sandbox/testers/{me}", headers=owner)
    assert removed.status_code == 200
    assert me not in {t["user_id"] for t in removed.json()["testers"]}
    assert _audit(ModerationAction.qa_tester_remove, me)


def test_a_test_earning_walks_the_whole_payout_path(client, owner):
    """Credit → cleared balance → cashout → admin list → run → paid → notified."""
    mid, mh = _mod(client)
    uid, th, rid = _tester(client, owner)

    before = client.get(f"{API}/payouts/balance", headers=th).json()
    assert before["qa_tester"] is True

    credit = client.post(f"{API}/admin/qa-sandbox/credits", headers=mh,
                         json={"review_id": rid})
    assert credit.status_code == 201, credit.text
    body = credit.json()
    assert body["is_test"] is True and Decimal(body["amount"]) == Decimal("350.00")
    assert body["cleared_at"] is not None

    # Cleared at once: withdrawable, not "still clearing".
    bal = client.get(f"{API}/payouts/balance", headers=th).json()
    assert Decimal(bal["withdrawable"]) - Decimal(before["withdrawable"]) == Decimal("350.00")
    assert Decimal(bal["pending_clearance"]) == Decimal(before["pending_clearance"])

    # The tester's history labels it, and they were told it is not real money.
    rows = client.get(f"{API}/users/me/earnings", headers=th).json()["rows"]
    row = next(r for r in rows if r["review_id"] == rid)
    assert row["is_test"] is True and row["status"] == "paid"
    notice = _kinds(client, th)["qa_test_earning"]
    assert "not real money" in notice["body"] and notice["link"] == "/dashboard/transfer"
    assert _audit(ModerationAction.qa_test_credit, rid)[0].moderator_id == uuid.UUID(mid)

    # The real cashout path.
    assert client.patch(f"{API}/auth/me/payout-account", headers=th,
                        json={"payout_account": "qa-tester@example.com"}).status_code == 200
    cash = client.post(f"{API}/payouts/cashout", headers=th, json={"amount": "350.00"})
    assert cash.status_code == 201, cash.text
    pid = cash.json()["id"]

    listed = client.get(f"{API}/admin/payouts", headers=mh,
                        params={"status": "scheduled", "limit": 100}).json()
    mine = next(p for p in listed if p["id"] == pid)
    assert mine["qa_tester"] is True
    assert mine["payout_account"] == "qa-tester@example.com"
    assert mine["username"]

    assert client.post(f"{API}/admin/payouts/run", headers=mh,
                       json={"submit": False}).status_code == 200
    paid = client.post(f"{API}/admin/payouts/{pid}/mark-paid", headers=mh,
                       json={"provider_ref": "SANDBOX-QA-1"})
    assert paid.status_code == 200 and paid.json()["status"] == "paid"

    own = client.get(f"{API}/payouts", headers=th).json()
    assert own[0]["status"] == "paid" and own[0]["provider_ref"] == "SANDBOX-QA-1"
    notice = _kinds(client, th)["payout_paid"]
    assert "₱350.00" in notice["title"] and "SANDBOX-QA-1" in notice["body"]
    events = [log.context.get("event") for log in _audit(ModerationAction.payout, uid)
              if log.moderator_id == uuid.UUID(mid)]
    assert "paid" in events


def test_test_earnings_are_refused_outside_the_rules(client, owner, monkeypatch):
    _, mh = _mod(client)
    _, _, rid = _tester(client, owner)

    # Not a named tester.
    _, other_tok, _ = register_and_token(client)
    stranger = _review(client, _auth(other_tok), "stranger")
    res = client.post(f"{API}/admin/qa-sandbox/credits", headers=mh,
                      json={"review_id": stranger})
    assert res.status_code == 409 and res.json()["code"] == "not_a_qa_tester"

    # Over the cap.
    res = client.post(f"{API}/admin/qa-sandbox/credits", headers=mh,
                      json={"review_id": rid, "amount": "1000.01"})
    assert res.status_code == 422

    # Never on live PayPal.
    monkeypatch.setattr(settings, "payout_provider", "paypal_live")
    res = client.post(f"{API}/admin/qa-sandbox/credits", headers=mh, json={"review_id": rid})
    assert res.status_code == 409 and res.json()["code"] == "qa_sandbox_live_provider"
    monkeypatch.setattr(settings, "payout_provider", "paypal_sandbox")

    # One per review.
    assert client.post(f"{API}/admin/qa-sandbox/credits", headers=mh,
                       json={"review_id": rid, "amount": "400"}).status_code == 201
    again = client.post(f"{API}/admin/qa-sandbox/credits", headers=mh, json={"review_id": rid})
    assert again.status_code == 409 and again.json()["code"] == "qa_test_credit_exists"

    # A member cannot credit anyone.
    _, member_tok, _ = register_and_token(client)
    assert client.post(f"{API}/admin/qa-sandbox/credits", headers=_auth(member_tok),
                       json={"review_id": rid}).status_code == 403


def test_test_earnings_never_count_as_revenue_or_pool(client, owner):
    _, mh = _mod(client)
    _, _, rid = _tester(client, owner)
    db = SessionLocal()
    try:
        health = admin_overview_service.affiliate_health(db)
        pool = admin_overview_service.overview(db).honesty_fund_pool
    finally:
        db.close()

    assert client.post(f"{API}/admin/qa-sandbox/credits", headers=mh,
                       json={"review_id": rid, "amount": "900"}).status_code == 201

    db = SessionLocal()
    try:
        after = admin_overview_service.affiliate_health(db)
        assert after.recognised_amount == health.recognised_amount
        assert admin_overview_service.overview(db).honesty_fund_pool == pool
        row = db.scalar(select(Commission).where(Commission.review_id == uuid.UUID(rid),
                                                 Commission.is_test.is_(True)))
        assert row.platform_share == 0 and row.honesty_fund_share == 0
        assert row.gross_amount == row.reviewer_share == Decimal("900.00")
    finally:
        db.close()


def test_cancel_and_fail_refund_tell_the_reviewer_and_are_audited(client, owner):
    mid, mh = _mod(client)
    uid, th, rid = _tester(client, owner)
    assert client.post(f"{API}/admin/qa-sandbox/credits", headers=mh,
                       json={"review_id": rid}).status_code == 201
    client.patch(f"{API}/auth/me/payout-account", headers=th,
                 json={"payout_account": "qa-tester@example.com"})

    first = client.post(f"{API}/payouts/cashout", headers=th, json={"amount": "350"}).json()
    res = client.post(f"{API}/admin/payouts/{first['id']}/cancel", headers=mh)
    assert res.status_code == 200 and res.json()["status"] == "cancelled"
    assert "back in your balance" in _kinds(client, th)["payout_cancelled"]["body"]
    bal = client.get(f"{API}/payouts/balance", headers=th).json()
    assert Decimal(bal["withdrawable"]) >= Decimal("350")

    second = client.post(f"{API}/payouts/cashout", headers=th, json={"amount": "350"}).json()
    res = client.post(f"{API}/admin/payouts/{second['id']}/fail", headers=mh,
                      json={"reason": "PayPal sandbox account not found"})
    assert res.status_code == 200 and res.json()["status"] == "failed"
    notice = _kinds(client, th)["payout_failed"]
    assert "PayPal sandbox account not found" in notice["body"]

    events = [(log.context.get("event"), log.moderator_id)
              for log in _audit(ModerationAction.payout, uid)]
    assert ("cancelled", uuid.UUID(mid)) in events
    assert ("failed", uuid.UUID(mid)) in events

    retried = client.post(f"{API}/admin/payouts/{second['id']}/retry", headers=mh)
    assert retried.status_code == 200 and retried.json()["status"] == "scheduled"
    assert ("retried", uuid.UUID(mid)) in [
        (log.context.get("event"), log.moderator_id)
        for log in _audit(ModerationAction.payout, uid)]


def test_provider_status_says_how_payouts_leave_and_never_a_secret(client, monkeypatch):
    _, mh = _mod(client)
    monkeypatch.setattr(settings, "paypal_client_id", "client-id-value-xyz")
    monkeypatch.setattr(settings, "paypal_secret", "secret-value-xyz")
    res = client.get(f"{API}/admin/payouts/provider", headers=mh)
    assert res.status_code == 200
    body = res.json()
    assert body["method"] == settings.payout_provider
    assert body["paypal_configured"] is True
    assert body["api_base_is_sandbox"] is True
    assert "secret-value-xyz" not in res.text and "client-id-value-xyz" not in res.text

    _, member_tok, _ = register_and_token(client)
    assert client.get(f"{API}/admin/payouts/provider",
                      headers=_auth(member_tok)).status_code == 403


def _scheduled_for(uid: str) -> Payout:
    db = SessionLocal()
    try:
        return db.scalar(select(Payout).where(Payout.user_id == uuid.UUID(uid),
                                              Payout.status == PayoutStatus.scheduled))
    finally:
        db.close()


def test_sandbox_mode_never_submits_to_a_live_host(client, owner, monkeypatch):
    _, mh = _mod(client)
    uid, th, rid = _tester(client, owner)
    client.post(f"{API}/admin/qa-sandbox/credits", headers=mh, json={"review_id": rid})
    client.patch(f"{API}/auth/me/payout-account", headers=th,
                 json={"payout_account": "qa-tester@example.com"})
    assert client.post(f"{API}/payouts/cashout", headers=th,
                       json={"amount": "350"}).status_code == 201
    payout = _scheduled_for(uid)

    calls = []
    monkeypatch.setattr(paypal, "submit_batch", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(settings, "paypal_client_id", "id")
    monkeypatch.setattr(settings, "paypal_secret", "secret")
    monkeypatch.setattr(settings, "paypal_base_url", "https://api-m.paypal.com")
    db = SessionLocal()
    try:
        out = payout_service.submit_batch(db, payout.batch_id)
    finally:
        db.close()
    assert out["status"] == "sandbox_url_mismatch" and calls == []
    assert _scheduled_for(uid) is not None


def test_a_live_batch_leaves_out_anyone_holding_test_money(client, owner, monkeypatch):
    _, mh = _mod(client)
    uid, th, rid = _tester(client, owner)
    client.post(f"{API}/admin/qa-sandbox/credits", headers=mh, json={"review_id": rid})
    client.patch(f"{API}/auth/me/payout-account", headers=th,
                 json={"payout_account": "qa-tester@example.com"})
    assert client.post(f"{API}/payouts/cashout", headers=th,
                       json={"amount": "350"}).status_code == 201
    payout = _scheduled_for(uid)

    sent: list[list] = []

    def fake_submit(batch, items):
        sent.append([i.sender_item_id for i in items])
        return paypal.BatchResult(payout_batch_id="LIVE-1", batch_status="PENDING")

    monkeypatch.setattr(paypal, "submit_batch", fake_submit)
    monkeypatch.setattr(settings, "payout_provider", "paypal_live")
    monkeypatch.setattr(settings, "paypal_client_id", "id")
    monkeypatch.setattr(settings, "paypal_secret", "secret")
    monkeypatch.setattr(settings, "paypal_base_url", "https://api-m.paypal.com")
    db = SessionLocal()
    try:
        out = payout_service.submit_batch(db, payout.batch_id)
    finally:
        db.close()
    assert all(payout.payout_id not in ids for ids in sent)
    assert out["status"] in {"held_test_funds", "processing"}
    still = _scheduled_for(uid)
    assert still is not None and still.id == payout.id


def test_the_owner_cannot_name_a_claimed_seller(client, owner):
    db = SessionLocal()
    try:
        seller = make_user(db, is_claimed_seller=True, username=f"sel_{uuid.uuid4().hex[:8]}")
        db.commit()
        name = seller.username
        sid = seller.id
    finally:
        db.close()
    try:
        res = client.post(f"{API}/admin/qa-sandbox/testers", headers=owner,
                          json={"identifier": name})
        assert res.status_code == 409 and res.json()["code"] == "seller_cannot_earn"
    finally:
        db = SessionLocal()
        try:
            db.query(User).filter(User.id == sid).delete()
            db.commit()
        finally:
            db.close()

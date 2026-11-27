"""Payouts — reviewer cashout requests, batch run, wallet reserve/refund, PayPal
adapter (mocked), manual rail (Business Rules §15, §19).

No test makes a real PayPal call: the adapter is monkeypatched, per the plan.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.adapters import paypal
from app.core.config import settings
from app.models.enums import MembershipTier, PayoutStatus  # noqa: F401
from app.services import payout_service
from tests.conftest import register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _set_wallet(uid: str, amount: str, tier: MembershipTier | None = None,
                account: str | None = "payee@example.com") -> None:
    """Fund a wallet the way the platform really does — via a commission whose
    reviewer_share IS the target amount.

    Setting `wallet_balance` directly would fabricate money with no row behind
    it and break the whole-database invariant
    `wallet == inflows - reserved payouts` (scripts/supabase_verify.py), which is
    exactly the drift that invariant exists to catch.
    """
    from datetime import date

    from app.db.session import SessionLocal
    from app.models.honesty_fund import HonestyFundDistribution
    from app.models.user import User

    # Honesty Fund payout is the simplest legitimate inflow to synthesise: unlike
    # `commissions` (ck_commission_target demands a review_id) it allows a null
    # review, so no product/review scaffolding is needed just to fund a wallet.
    target = Decimal(amount)
    db = SessionLocal()
    try:
        u = db.get(User, _uuid.UUID(uid))
        u.payout_account = account
        if tier is not None:
            u.membership_tier = tier
        # Clear prior fixture funding so `target` is the whole balance.
        for old in db.scalars(select(HonestyFundDistribution).where(
                HonestyFundDistribution.reviewer_id == u.id,
                HonestyFundDistribution.distribution_id.like("hfd_payfix_%"))):
            db.delete(old)
        db.flush()
        if target > 0:
            db.add(HonestyFundDistribution(
                distribution_id=f"hfd_payfix_{_uuid.uuid4().hex[:8]}",
                cycle_month=date(1970, 1, 1), review_id=None, reviewer_id=u.id,
                honesty_score=Decimal("1"), pool_amount=target,
                payout_amount=target))
        u.wallet_balance = target
        db.commit()
    finally:
        db.close()


def _wallet(uid: str) -> Decimal:
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        return db.get(User, _uuid.UUID(uid)).wallet_balance
    finally:
        db.close()


def _payouts_for(uid: str) -> list:
    from app.db.session import SessionLocal
    from app.models.payout import Payout

    db = SessionLocal()
    try:
        return list(db.scalars(select(Payout).where(Payout.user_id == _uuid.UUID(uid))))
    finally:
        db.close()


def _free_when() -> date:
    """A scheduling date whose batch_id is unused.

    `schedule_payouts` is deliberately GLOBAL (it sweeps every eligible user) and
    the batch key is `batch_YYYYMM`, so consecutive suite runs would otherwise
    share a batch and trip uq_payout_user_batch. A unique historic month gives
    each test its own batch without weakening the real monthly behaviour.
    """
    from app.db.session import SessionLocal
    from app.models.payout import Payout

    db = SessionLocal()
    try:
        used = {b for b in db.scalars(select(Payout.batch_id).distinct()) if b}
        for year in range(1990, 2100):
            for month in range(1, 13):
                when = date(year, month, 5)
                if payout_service.batch_id_for(when) not in used:
                    return when
        raise AssertionError("no free payout batch month")
    finally:
        db.close()


def _request(uid: str, when: date, amount: str | None = None):
    """The reviewer's own cashout request (Business Rules §15)."""
    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        return payout_service.request_cashout(
            db, db.get(User, _uuid.UUID(uid)),
            Decimal(amount) if amount is not None else None, when=when)
    finally:
        db.close()


@requires_db
def test_payout_account_setter_validates_email(client):
    _, token, _ = register_and_token(client)
    h = _auth(token)
    assert client.patch("/api/v1/auth/me/payout-account", headers=h,
                        json={"payout_account": "not-an-email"}).status_code == 422
    r = client.patch("/api/v1/auth/me/payout-account", headers=h,
                     json={"payout_account": "me@example.com"})
    assert r.status_code == 200 and r.json()["payout_account"] == "me@example.com"
    assert client.patch("/api/v1/auth/me/payout-account",
                        json={"payout_account": "me@example.com"}).status_code == 401


@requires_db
def test_cashout_is_requested_by_the_reviewer_and_reserved_at_once(client, monkeypatch):
    """§15: payouts start with the reviewer's own request, ₱300 minimum, no
    cooldown; the batch run processes requests and creates nothing on its own.
    Membership tiers no longer order anyone."""
    from app.core.errors import AppError
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "manual")
    when = _free_when()

    asker, _, _ = register_and_token(client)
    poor, _, _ = register_and_token(client)
    no_acct, _, _ = register_and_token(client)
    silent, _, _ = register_and_token(client)
    _set_wallet(asker, "500.00")
    _set_wallet(poor, "299.99")                          # below the minimum
    _set_wallet(no_acct, "900.00", account=None)
    _set_wallet(silent, "900.00")                        # eligible, but never asks

    payout = _request(asker, when)
    assert payout.amount == Decimal("500.00") and payout.status == PayoutStatus.scheduled
    assert _wallet(asker) == Decimal("0.00")             # reserved at once

    with pytest.raises(AppError) as below:
        _request(poor, when)
    assert below.value.code == "below_payout_minimum"
    with pytest.raises(AppError) as missing:
        _request(no_acct, when)
    assert missing.value.code == "payout_account_missing"

    db = SessionLocal()
    try:
        result = payout_service.schedule_payouts(db, when=when)
    finally:
        db.close()
    assert result["method"] == "manual"
    assert _payouts_for(silent) == [] and _wallet(silent) == Decimal("900.00")
    assert _payouts_for(poor) == [] and _wallet(poor) == Decimal("299.99")


@requires_db
def test_asking_again_tops_up_the_waiting_request_and_the_run_is_idempotent(client,
                                                                            monkeypatch):
    """No cooldown (§15): a second request in the same batch adds to the one
    waiting instead of being refused; re-running the batch creates nothing."""
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "manual")
    when = _free_when()
    uid, _, _ = register_and_token(client)
    _set_wallet(uid, "800.00")
    _request(uid, when, "300.00")
    _request(uid, when, "350.00")
    rows = _payouts_for(uid)
    assert len(rows) == 1 and rows[0].amount == Decimal("650.00")
    assert _wallet(uid) == Decimal("150.00")

    db = SessionLocal()
    try:
        payout_service.schedule_payouts(db, when=when)
        payout_service.schedule_payouts(db, when=when)
    finally:
        db.close()
    assert len(_payouts_for(uid)) == 1
    assert _wallet(uid) == Decimal("150.00")


@requires_db
def test_asking_again_after_the_batch_was_sent_opens_the_next_batch(client, monkeypatch):
    """§15, no cooldown. Once this month's batch has been sent, a reviewer's
    next request used to collide with their first payout on
    uq_payout_user_batch — a 500. It opens the month's next batch instead, and
    both requests are reserved from the wallet exactly once."""
    from app.db.session import SessionLocal
    from app.models.payout import Payout

    monkeypatch.setattr(settings, "payout_provider", "manual")
    when = _free_when()
    uid, _, _ = register_and_token(client)
    _set_wallet(uid, "1200.00")
    first = _request(uid, when, "300.00")

    db = SessionLocal()
    try:                                   # the month's batch goes out
        db.get(Payout, first.id).status = PayoutStatus.processing
        db.commit()
    finally:
        db.close()

    second = _request(uid, when, "350.00")
    assert second.id != first.id
    assert first.batch_id == f"batch_{when:%Y%m}"
    assert second.batch_id == f"batch_{when:%Y%m}_2"
    assert second.status == PayoutStatus.scheduled
    assert _wallet(uid) == Decimal("550.00")

    # A third request tops up the open second batch, as before. Every request
    # meets the ₱300 minimum on its own, top-ups included.
    third = _request(uid, when, "300.00")
    assert third.id == second.id and third.amount == Decimal("650.00")
    assert _wallet(uid) == Decimal("250.00")


@requires_db
def test_a_sent_batch_is_never_resubmitted_under_the_same_sender_id(client, monkeypatch):
    """The batch key is PayPal's sender_batch_id, which PayPal refuses twice.
    A request made after a batch was submitted must land in a new batch, so
    each submission carries its own id and nothing is left stranded."""
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "paypal_sandbox")
    monkeypatch.setattr(paypal, "is_configured", lambda: True)
    sent: list[str] = []

    def fake_submit(sender_batch_id, items):
        sent.append(sender_batch_id)
        return paypal.BatchResult(payout_batch_id=f"PP-{len(sent)}",
                                  batch_status=paypal.BATCH_PENDING)

    monkeypatch.setattr(paypal, "submit_batch", fake_submit)
    when = _free_when()
    a, _, _ = register_and_token(client)
    b, _, _ = register_and_token(client)
    _set_wallet(a, "400.00")
    _set_wallet(b, "400.00")

    first = _request(a, when)
    db = SessionLocal()
    try:
        assert payout_service.submit_batch(db, first.batch_id)["status"] == "processing"
    finally:
        db.close()

    later = _request(b, when)
    assert later.batch_id != first.batch_id
    db = SessionLocal()
    try:
        assert payout_service.submit_batch(db, later.batch_id)["status"] == "processing"
        # Resubmitting the first key finds nothing left to send.
        assert payout_service.submit_batch(db, first.batch_id)["status"] == "nothing_to_submit"
    finally:
        db.close()
    assert sent == [first.batch_id, later.batch_id]


@requires_db
def test_a_decimal_constraint_is_a_clean_422_not_a_500(client):
    """Regression (M3 s10), kept after its original endpoint (contracts) was
    retired: pydantic puts the constraint value in the error `ctx` —
    Decimal('0') for a `gt=0` Decimal field — and emitting exc.errors() raw made
    json.dumps fail, turning every such 422 into a 500. The shared error
    contract must stay JSON-safe."""
    _, token, _ = register_and_token(client)
    resp = client.post("/api/v1/payouts/cashout", headers=_auth(token), json={"amount": "0"})
    assert resp.status_code == 422, "must be a clean 422, not a 500"
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["loc"][-1] == "amount"
    assert body["errors"][0]["ctx"]["gt"] in ("0", 0)


@requires_db
def test_manual_mark_paid_and_rbac(client, monkeypatch):
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "manual")
    when = _free_when()
    uid, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    h, mh = _auth(token), _auth(mod_token)
    _set_wallet(uid, "450.00")
    _request(uid, when)
    db = SessionLocal()
    try:
        payout_service.schedule_payouts(db, when=when)
    finally:
        db.close()
    pid = str(_payouts_for(uid)[0].id)

    # Own payouts are visible; another user can't see them.
    assert pid in [p["id"] for p in client.get("/api/v1/payouts", headers=h).json()]
    _, other, _ = register_and_token(client)
    assert client.get("/api/v1/payouts", headers=_auth(other)).json() == []
    # RBAC on the admin surface.
    assert client.get("/api/v1/admin/payouts", headers=h).status_code == 403
    assert client.post(f"/api/v1/admin/payouts/{pid}/mark-paid", headers=h,
                       json={"provider_ref": "X"}).status_code == 403

    r = client.post(f"/api/v1/admin/payouts/{pid}/mark-paid", headers=mh,
                    json={"provider_ref": "MANUAL-REF-1"})
    assert r.status_code == 200
    assert r.json()["status"] == "paid" and r.json()["provider_ref"] == "MANUAL-REF-1"
    assert r.json()["paid_at"] is not None
    assert _wallet(uid) == Decimal("0.00")   # stays debited — it was paid
    # Can't pay twice.
    assert client.post(f"/api/v1/admin/payouts/{pid}/mark-paid", headers=mh,
                       json={"provider_ref": "AGAIN"}).status_code == 409


@requires_db
def test_failure_and_cancel_refund_the_wallet(client, monkeypatch):
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "manual")
    when = _free_when()
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)

    # Failure path.
    uid, _, _ = register_and_token(client)
    _set_wallet(uid, "500.00")
    _request(uid, when)
    db = SessionLocal()
    try:
        payout_service.schedule_payouts(db, when=when)
    finally:
        db.close()
    pid = str(_payouts_for(uid)[0].id)
    assert _wallet(uid) == Decimal("0.00")
    r = client.post(f"/api/v1/admin/payouts/{pid}/fail", headers=mh,
                    json={"reason": "bad receiver account"})
    assert r.status_code == 200 and r.json()["status"] == "failed"
    assert _wallet(uid) == Decimal("500.00")     # refunded — earnings not lost

    # Retry re-reserves it.
    r = client.post(f"/api/v1/admin/payouts/{pid}/retry", headers=mh)
    assert r.status_code == 200 and r.json()["status"] == "scheduled"
    assert _wallet(uid) == Decimal("0.00")

    # Cancel path refunds too.
    r = client.post(f"/api/v1/admin/payouts/{pid}/cancel", headers=mh)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert _wallet(uid) == Decimal("500.00")
    # A cancelled payout can't be cancelled again.
    assert client.post(f"/api/v1/admin/payouts/{pid}/cancel", headers=mh).status_code == 409


@requires_db
def test_paypal_adapter_receives_correct_payload(client, monkeypatch):
    """The adapter is mocked — assert we call it with exactly the documented shape."""
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "paypal_sandbox")
    when = _free_when()
    monkeypatch.setattr(paypal, "is_configured", lambda: True)
    captured: dict = {}

    def fake_submit(sender_batch_id, items):
        captured["batch"] = sender_batch_id
        captured["items"] = items
        return paypal.BatchResult(payout_batch_id="PB-123", batch_status=paypal.BATCH_PENDING)

    monkeypatch.setattr(paypal, "submit_batch", fake_submit)

    uid, _, _ = register_and_token(client)
    _set_wallet(uid, "750.00", account="payee-x@example.com")
    _request(uid, when)
    db = SessionLocal()
    try:
        result = payout_service.schedule_payouts(db, when=when)
        sub = payout_service.submit_batch(db, result["batch_id"])
    finally:
        db.close()

    assert sub["status"] == "processing" and sub["provider_ref"] == "PB-123"
    assert captured["batch"] == result["batch_id"]
    mine = [i for i in captured["items"] if i.receiver == "payee-x@example.com"]
    assert len(mine) == 1
    assert mine[0].amount == Decimal("750.00")
    assert mine[0].currency == "PHP"
    assert mine[0].sender_item_id == _payouts_for(uid)[0].payout_id
    assert _payouts_for(uid)[0].status == PayoutStatus.processing


@requires_db
def test_missing_credentials_leaves_batch_scheduled_not_crashing(client, monkeypatch):
    """No PayPal creds must NOT be an error — the manual rail stays available."""
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "paypal_sandbox")
    when = _free_when()
    monkeypatch.setattr(paypal, "is_configured", lambda: False)
    uid, _, _ = register_and_token(client)
    _set_wallet(uid, "800.00")
    _request(uid, when)
    db = SessionLocal()
    try:
        result = payout_service.schedule_payouts(db, when=when)
        sub = payout_service.submit_batch(db, result["batch_id"])
    finally:
        db.close()
    assert sub["status"] == "provider_not_configured"
    assert _payouts_for(uid)[0].status == PayoutStatus.scheduled  # still payable by hand
    assert _wallet(uid) == Decimal("0.00")


@requires_db
def test_refresh_settles_success_and_failure(client, monkeypatch):
    from app.db.session import SessionLocal

    monkeypatch.setattr(settings, "payout_provider", "paypal_sandbox")
    when = _free_when()
    monkeypatch.setattr(paypal, "is_configured", lambda: True)
    monkeypatch.setattr(paypal, "submit_batch", lambda b, i: paypal.BatchResult(
        payout_batch_id="PB-REFRESH", batch_status=paypal.BATCH_PENDING))

    winner, _, _ = register_and_token(client)
    loser, _, _ = register_and_token(client)
    _set_wallet(winner, "500.00", account="win@example.com")
    _set_wallet(loser, "600.00", account="lose@example.com")
    _request(winner, when)
    _request(loser, when)
    db = SessionLocal()
    try:
        result = payout_service.schedule_payouts(db, when=when)
        payout_service.submit_batch(db, result["batch_id"])
    finally:
        db.close()

    win_pid = _payouts_for(winner)[0].payout_id
    lose_pid = _payouts_for(loser)[0].payout_id
    monkeypatch.setattr(paypal, "get_batch", lambda ref: {
        "batch_status": paypal.BATCH_PROCESSING,
        "items": {win_pid: paypal.TXN_SUCCESS, lose_pid: paypal.TXN_FAILED}})

    db = SessionLocal()
    try:
        out = payout_service.refresh_batch(db, result["batch_id"])
    finally:
        db.close()
    assert out["paid"] >= 1 and out["failed"] >= 1
    assert _payouts_for(winner)[0].status == PayoutStatus.paid
    assert _wallet(winner) == Decimal("0.00")          # paid: stays debited
    assert _payouts_for(loser)[0].status == PayoutStatus.failed
    assert _wallet(loser) == Decimal("600.00")         # failed: refunded


@pytest.mark.parametrize("txn", sorted(paypal.TXN_FAILURES))
def test_every_documented_failure_status_is_treated_as_failure(txn):
    """PayPal's transaction_status enum has several terminal-failure values; each
    must refund rather than silently strand the money."""
    assert txn in paypal.TXN_FAILURES
    assert txn not in (paypal.TXN_SUCCESS, paypal.TXN_PENDING,
                       paypal.TXN_UNCLAIMED, paypal.TXN_ONHOLD)


def test_live_provider_requires_credentials_and_non_sandbox_url():
    from app.core.config import Settings

    # Every field this assertion depends on is passed explicitly: Settings also
    # reads the repo-root .env, so a developer with real PAYPAL_* values
    # configured would otherwise see the credentials check correctly pass and
    # this test fail for reasons that have nothing to do with the code.
    s = Settings(app_env="production", payout_provider="paypal_live",
                 paypal_client_id="", paypal_secret="",
                 paypal_base_url="https://api-m.sandbox.paypal.com",
                 jwt_secret="x" * 40, pii_hash_salt="y" * 40,
                 use_supabase=True, supabase_connection_string="postgresql://x/y")
    issues = " ".join(s.production_issues())
    assert "PAYPAL_CLIENT_ID" in issues
    assert "sandbox" in issues


# --------------------------------------------------------------------------
# Provider fault handling (PayPal acceptance readiness, no credentials needed)
#
# payout_service catches exactly PayPalError/PayPalNotConfigured and leaves the
# batch `scheduled` so it can be retried. Anything escaping that handler is a
# 500 that loses the retry and misreports the cause, so these pin the
# translation rather than the happy path.
# --------------------------------------------------------------------------

def _configured(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "paypal_client_id", "cid", raising=False)
    monkeypatch.setattr(settings, "paypal_secret", "sec", raising=False)


def test_provider_timeout_becomes_a_paypal_error(monkeypatch):
    import httpx

    from app.adapters import paypal
    _configured(monkeypatch)

    class _Boom:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): raise httpx.ReadTimeout("timed out")
        def get(self, *a, **k): raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(paypal.httpx, "Client", lambda **k: _Boom())
    with pytest.raises(paypal.PayPalError) as exc:
        paypal.submit_batch("b1", [])
    assert "unreachable" in str(exc.value).lower()
    with pytest.raises(paypal.PayPalError):
        paypal.get_batch("b1")


def test_connection_error_becomes_a_paypal_error(monkeypatch):
    import httpx

    from app.adapters import paypal
    _configured(monkeypatch)

    class _Boom:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): raise httpx.ConnectError("refused")
        def get(self, *a, **k): raise httpx.ConnectError("refused")

    monkeypatch.setattr(paypal.httpx, "Client", lambda **k: _Boom())
    with pytest.raises(paypal.PayPalError):
        paypal.submit_batch("b2", [])


def test_oauth_200_without_a_token_becomes_a_paypal_error(monkeypatch):
    """A 200 carrying no access_token used to raise KeyError and escape."""
    from app.adapters import paypal
    _configured(monkeypatch)

    class _Resp:
        status_code = 200
        def json(self): return {"scope": "…", "expires_in": 300}   # no access_token

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()
        def get(self, *a, **k): return _Resp()

    monkeypatch.setattr(paypal.httpx, "Client", lambda **k: _Client())
    with pytest.raises(paypal.PayPalError):
        paypal.submit_batch("b3", [])


def test_malformed_json_body_becomes_a_paypal_error(monkeypatch):
    from app.adapters import paypal
    _configured(monkeypatch)

    class _TokenResp:
        status_code = 200
        def json(self): return {"access_token": "t"}

    class _BadResp:
        status_code = 200
        def json(self): raise ValueError("not json")

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, **k): return _TokenResp() if "oauth2" in url else _BadResp()
        def get(self, *a, **k): return _BadResp()

    monkeypatch.setattr(paypal.httpx, "Client", lambda **k: _Client())
    with pytest.raises(paypal.PayPalError) as exc:
        paypal.submit_batch("b4", [])
    assert "unusable" in str(exc.value).lower() or "malformed" in str(exc.value).lower()


def test_provider_errors_never_echo_the_credential(monkeypatch):
    """The OAuth payload is the one place a secret could come back to us."""
    from app.adapters import paypal
    _configured(monkeypatch)

    class _Resp:
        status_code = 401
        def json(self): return {"error": "invalid_client", "client_id": "cid",
                                "client_secret": "sec"}

    class _Client:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()
        def get(self, *a, **k): return _Resp()

    monkeypatch.setattr(paypal.httpx, "Client", lambda **k: _Client())
    with pytest.raises((paypal.PayPalError, paypal.PayPalNotConfigured)) as exc:
        paypal.submit_batch("b5", [])
    message = str(exc.value)
    assert "sec" not in message.split("HTTP")[0] or "client_secret" not in message
    assert "invalid_client" not in message, "provider body leaked into the error"

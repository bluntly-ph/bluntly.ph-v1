"""Earnings payouts (Business Rules §15, §19).

A payout starts with the reviewer's own cashout request (no cooldown, minimum
₱300) against CLEARED funds only — reviewer shares whose marketplace payout has
reached Bluntly and been reconciled. Requests are processed in batches; bank
transfer is the interim method and PayPal stays sandbox-only. Membership tiers
no longer order anyone.

Money safety rule: the wallet is debited **when the payout is scheduled**, not
when it is paid. The balance is therefore reserved while a batch is in flight and
cannot be spent twice; `failed` and `cancelled` refund it. Every state change
goes through one of the helpers here so that invariant holds:

    wallet == inflows - SUM(payouts in scheduled/processing/paid)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters import paypal
from app.core.config import settings
from app.core.constants import MANILA
from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger
from app.models.commission import Commission
from app.models.enums import (
    ModerationAction,
    PayoutMethod,
    PayoutStatus,
)
from app.models.moderation import ModerationLog
from app.models.payout import Payout
from app.models.user import User
from app.services import notification_service, wallet

log = get_logger("payouts")

# Money has left the wallet in these states; failed/cancelled put it back.
RESERVED_STATES = (PayoutStatus.scheduled, PayoutStatus.processing, PayoutStatus.paid)


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(detail: str, code: str) -> AppError:
    return AppError(detail, code=code, status_code=409, title="Conflicting state")


def current_method() -> PayoutMethod:
    try:
        return PayoutMethod(settings.payout_provider)
    except ValueError:
        return PayoutMethod.manual


def provider_status() -> dict:
    """How payouts leave Bluntly right now, for the admin screen. No secrets:
    whether credentials exist is a yes/no, never a value.

    PayPal stays SANDBOX (owner rule). `api_base_is_sandbox` is what makes that
    checkable from the console rather than assumed from a variable's name.
    """
    method = current_method()
    return {
        "provider": settings.payout_provider,
        "method": method.value,
        "paypal_configured": paypal.is_configured(),
        "api_base_is_sandbox": "sandbox" in settings.paypal_base_url,
        # A batch can go through the PayPal API only in sandbox mode, with
        # credentials, against the sandbox host; anything else is paid by hand.
        "api_submission_available": (method == PayoutMethod.paypal_sandbox
                                     and paypal.is_configured()
                                     and "sandbox" in settings.paypal_base_url),
        "minimum_cashout": str(settings.payout_min_php),
        "qa_test_earnings_allowed": method != PayoutMethod.paypal_live,
    }


def _peso(amount) -> str:
    return f"₱{Decimal(amount):,.2f}"


def _audit(db: Session, moderator_id: uuid.UUID | None, event: str, payout: Payout,
           **extra) -> None:
    """One audit row per money-state change a person (or their refresh) made.

    `moderation_logs` doubles as the audit log; `payout` is its action for
    everything that moves a payout, and `event` says which move it was.
    """
    context = {"event": event, "payout_id": payout.payout_id, "amount": str(payout.amount),
               "batch_id": payout.batch_id, "user_id": str(payout.user_id)}
    context.update({k: v for k, v in extra.items() if v is not None})
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=moderator_id,
        action=ModerationAction.payout, target_ref=payout.user_id,
        notes=f"payout {event}", context=context))


def _tell(db: Session, payout: Payout, kind: str, title: str, body: str) -> None:
    """The reviewer hears about every outcome of their own request."""
    notification_service.notify(db, payout.user_id, kind, title, body=body,
                                link="/dashboard/transfer")


def batch_id_for(when: date) -> str:
    return f"batch_{when:%Y%m}"


def open_batch_for(db: Session, when: date) -> str:
    """The batch a new cashout request joins: this month's first batch that
    nobody has sent yet.

    A batch key is also PayPal's `sender_batch_id`, which PayPal refuses to see
    twice within 30 days — the deliberate guard against paying a batch twice
    when a submit's outcome is unknown and it is retried. So once any payout in
    a batch has left `scheduled` (sent, paid, failed or cancelled), that key is
    closed: a request made afterwards opens `batch_YYYYMM_2`, `_3`, … instead of
    joining a batch that was already sent. Joining it used to fail twice over:
    a reviewer's second request that month collided with their first payout on
    `uq_payout_user_batch` (a 500, where §15 promises no cooldown), and any new
    payout in a sent batch could never be sent, because resubmitting the key is
    exactly what PayPal refuses.
    """
    base = batch_id_for(when)
    for n in range(1, 1000):
        key = base if n == 1 else f"{base}_{n}"
        closed = db.scalar(select(Payout.id).where(
            Payout.batch_id == key, Payout.status != PayoutStatus.scheduled).limit(1))
        if closed is None:
            return key
    raise AppError("Too many payout batches this month.", code="payout_batches_exhausted",
                   status_code=409, title="Conflicting state")



def _locked(db: Session, payout: Payout) -> Payout:
    """Re-read a payout FOR UPDATE so its state check cannot race.

    Every transition here guards on the current status - "only a scheduled
    payout can be cancelled". Read outside a lock, two concurrent callers both
    see `scheduled`, both pass the guard, and both refund. The guard reads like
    a state machine while behaving like a suggestion.

    `populate_existing` matters: without it the identity map hands back the
    same stale instance that was checked a moment ago, and the lock buys
    nothing.
    """
    return db.execute(
        select(Payout)
        .where(Payout.id == payout.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()


def uncleared_share(db: Session, user_id: uuid.UUID) -> Decimal:
    """Credited reviewer shares whose marketplace payout has not reached Bluntly.

    Business Rules §15: "Bluntly only pays out money it has actually,
    confirmedly received and reconciled from the marketplace's own payout".
    These are in the wallet (they were earned) but cannot be withdrawn yet.
    """
    total = db.scalar(select(func.coalesce(func.sum(Commission.reviewer_share), 0)).where(
        Commission.reviewer_id == user_id, Commission.cleared_at.is_(None),
        Commission.reviewer_share > 0))
    return Decimal(total or 0).quantize(Decimal("0.01"))


def uncleared_shares(db: Session, user_ids) -> dict[uuid.UUID, Decimal]:
    """`uncleared_share` for many reviewers in one grouped query (reports).

    Same predicate as the single-reviewer form; a reviewer with nothing
    uncleared is present with 0.00 rather than missing.
    """
    ids = list({u for u in user_ids if u is not None})
    out = {u: Decimal("0.00") for u in ids}
    if not ids:
        return out
    rows = db.execute(
        select(Commission.reviewer_id, func.coalesce(func.sum(Commission.reviewer_share), 0))
        .where(Commission.reviewer_id.in_(ids), Commission.cleared_at.is_(None),
               Commission.reviewer_share > 0)
        .group_by(Commission.reviewer_id)).all()
    for reviewer_id, total in rows:
        out[reviewer_id] = Decimal(total or 0).quantize(Decimal("0.01"))
    return out


def withdrawable_from(wallet_balance, uncleared: Decimal) -> Decimal:
    """The §19 rule itself: the wallet less what has not cleared, never below 0.

    The one place it is written. `withdrawable` (a cashout's check) and the
    reports' batched readings both call it, so they cannot disagree.
    """
    balance = Decimal(wallet_balance or 0) - Decimal(uncleared)
    return max(Decimal("0.00"), balance.quantize(Decimal("0.01")))


def withdrawable(db: Session, user: User) -> Decimal:
    """Cleared, reconciled funds: the only balance a cashout may draw on (§19)."""
    return withdrawable_from(user.wallet_balance, uncleared_share(db, user.id))


def request_cashout(db: Session, user: User, amount: Decimal | None = None, *,
                    when: date | None = None) -> Payout:
    """The reviewer asks to withdraw (§15): no cooldown, processed in a batch.

    The money is reserved at once (the wallet is debited here, the invariant
    below holds). A second request inside the same batch tops up the one
    already waiting rather than failing, so asking again is never refused
    just for being soon.
    """
    # Lock the reviewer's row and re-read it before anything is decided. The
    # withdrawable amount is computed from the balance; unlocked, two requests
    # racing both read the same "available" figure and together could draw on
    # money that has not cleared yet (§19). The wallet's non-negative CHECK
    # cannot catch that: the wallet stays positive, the uncleared part is what
    # gets spent. Serialised, the second request sees the first one's debit.
    db.refresh(user, with_for_update=True)
    if user.is_claimed_seller:
        raise _conflict("A claimed seller account has no earnings to withdraw.",
                        "seller_cannot_earn")
    if not user.payout_account:
        raise _conflict("Add where to send your money before cashing out.",
                        "payout_account_missing")
    available = withdrawable(db, user)
    amount = (Decimal(amount) if amount is not None else available).quantize(Decimal("0.01"))
    if amount < settings.payout_min_php:
        raise AppError(f"The minimum cashout is ₱{settings.payout_min_php:,.0f}.",
                       code="below_payout_minimum", status_code=422, title="Invalid cashout",
                       extra={"minimum": str(settings.payout_min_php),
                              "withdrawable": str(available)})
    if amount > available:
        raise AppError("That is more than your cleared balance.",
                       code="exceeds_withdrawable", status_code=422, title="Invalid cashout",
                       extra={"withdrawable": str(available)})
    when = when or _now().astimezone(MANILA).date()
    batch = open_batch_for(db, when)
    existing = db.scalar(select(Payout).where(
        Payout.user_id == user.id, Payout.batch_id == batch,
        Payout.status == PayoutStatus.scheduled).with_for_update())
    if existing is not None:
        existing.amount = (Decimal(existing.amount) + amount).quantize(Decimal("0.01"))
        payout = existing
    else:
        payout = Payout(payout_id=f"pay_{uuid.uuid4().hex[:12]}", user_id=user.id,
                        amount=amount, currency="PHP", status=PayoutStatus.scheduled,
                        method=current_method(), batch_id=batch, scheduled_for=when)
        db.add(payout)
    wallet.adjust(db, user.id, -amount)
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=None,
        action=ModerationAction.cashout_request, target_ref=user.id,
        context={"amount": str(amount), "batch_id": batch}))
    db.commit()
    db.refresh(payout)
    return payout


def record_remittance(db: Session, moderator: User, platform, cycle_month: date,
                      amount_received: Decimal, received_on: date,
                      reference: str | None) -> dict:
    """The marketplace paid Bluntly for one cycle: its commissions clear (§15, §19).

    Reconciliation is reported, not enforced: the gross the imported report
    attributed to this cycle is returned beside what arrived, so a moderator
    sees any gap before anyone cashes out against it.
    """
    from app.models.commission import MarketplaceRemittance
    cycle_month = date(cycle_month.year, cycle_month.month, 1)
    if db.scalar(select(MarketplaceRemittance.id).where(
            MarketplaceRemittance.platform == platform,
            MarketplaceRemittance.cycle_month == cycle_month)) is not None:
        raise _conflict("This cycle's payout is already recorded.", "remittance_exists")
    row = MarketplaceRemittance(platform=platform, cycle_month=cycle_month,
                                amount_received=amount_received, received_on=received_on,
                                reference=reference, recorded_by_id=moderator.id)
    db.add(row)
    rows = db.scalars(select(Commission).where(
        Commission.platform == platform, Commission.cycle_month == cycle_month,
        Commission.cleared_at.is_(None))).all()
    now = _now()
    gross = Decimal("0")
    for commission in rows:
        commission.cleared_at = now
        gross += Decimal(commission.gross_amount)
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=moderator.id,
        action=ModerationAction.remittance_record,
        context={"platform": platform.value, "cycle_month": cycle_month.isoformat(),
                 "amount_received": str(amount_received), "cleared": len(rows),
                 "attributed_gross": str(gross)}))
    db.commit()
    return {"platform": platform.value, "cycle_month": cycle_month.isoformat(),
            "cleared_commissions": len(rows), "attributed_gross": str(gross),
            "amount_received": str(amount_received),
            "difference": str(Decimal(amount_received) - gross)}


def schedule_payouts(db: Session, when: date | None = None,
                     triggered_by: uuid.UUID | None = None) -> dict:
    """Run the internal payout batch over every requested payout that is due.

    Business Rules §15: payouts start with the reviewer's own request; the
    platform processes them on its schedule. Nothing here creates a payout for
    someone who did not ask, and no membership tier orders anyone ahead. With
    the manual method (bank transfer, the interim) the batch stays `scheduled`
    until a moderator marks each one paid.
    """
    when = when or _now().astimezone(MANILA).date()
    batch = batch_id_for(when)
    method = current_method()
    waiting = db.scalars(select(Payout).where(
        Payout.status == PayoutStatus.scheduled, Payout.scheduled_for <= when)).all()
    batches = sorted({p.batch_id for p in waiting if p.batch_id})
    total = sum((Decimal(p.amount) for p in waiting), Decimal("0"))
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        moderator_id=triggered_by, action=ModerationAction.payout,
        notes="payout batch run",
        context={"batch_id": batch, "requested": len(waiting), "total": str(total),
                 "batches": batches, "method": method.value},
    ))
    db.commit()
    # Preparation only: handing money to a provider is a separate, explicit
    # moderator step (`submit_batch`), never a side effect of a scheduled run.
    result = {"batch_id": batch, "scheduled": len(waiting), "method": method.value,
              "batches": batches,
              # Kept for API compatibility: requests, not a sweep, now start payouts.
              "skipped_no_payout_account": 0, "skipped_already_in_batch": 0}
    log.info("payout batch run", extra={"extra_fields": {
        "batch_id": batch, "requested": len(waiting), "method": method.value}})
    return result


def _holds_test_money(db: Session, user_id: uuid.UUID) -> bool:
    return db.scalar(select(Commission.id).where(
        Commission.reviewer_id == user_id, Commission.is_test.is_(True)).limit(1)) is not None


def submit_batch(db: Session, batch: str, moderator_id: uuid.UUID | None = None) -> dict:
    """Hand a scheduled batch to the provider. Missing credentials is NOT an
    error: the batch stays `scheduled` and can be paid manually."""
    payouts = db.scalars(select(Payout).where(
        Payout.batch_id == batch, Payout.status == PayoutStatus.scheduled)).all()
    if not payouts:
        return {"batch_id": batch, "submitted": 0, "status": "nothing_to_submit"}
    method = current_method()
    if method == PayoutMethod.manual:
        return {"batch_id": batch, "submitted": 0, "status": "manual_mode"}
    if method == PayoutMethod.paypal_sandbox and "sandbox" not in settings.paypal_base_url:
        # Sandbox mode pointed at a non-sandbox host would send real money
        # under a label that says it cannot. PayPal stays SANDBOX: refuse.
        log.warning("paypal sandbox mode with a non-sandbox base URL; not submitting",
                    extra={"extra_fields": {"batch_id": batch}})
        return {"batch_id": batch, "submitted": 0, "status": "sandbox_url_mismatch"}
    if method == PayoutMethod.paypal_live:
        # A QA sandbox test earning is never real money: whoever holds one is
        # left out of a live batch, to be settled by hand.
        held = [p for p in payouts if _holds_test_money(db, p.user_id)]
        payouts = [p for p in payouts if p not in held]
        if not payouts:
            return {"batch_id": batch, "submitted": 0, "status": "held_test_funds",
                    "held": len(held)}
    if not paypal.is_configured():
        log.info("paypal not configured; batch left scheduled for manual payment",
                 extra={"extra_fields": {"batch_id": batch, "payouts": len(payouts)}})
        return {"batch_id": batch, "submitted": 0, "status": "provider_not_configured"}

    items = [paypal.PayoutItem(receiver=db.get(User, p.user_id).payout_account,
                               amount=p.amount, sender_item_id=p.payout_id)
             for p in payouts]
    try:
        result = paypal.submit_batch(batch, items)
    except (paypal.PayPalError, paypal.PayPalNotConfigured) as exc:
        log.info("paypal submit failed; batch stays scheduled",
                 extra={"extra_fields": {"batch_id": batch, "error": str(exc)}})
        return {"batch_id": batch, "submitted": 0, "status": "submit_failed",
                "error": str(exc)}
    for p in payouts:
        p.status = PayoutStatus.processing
        p.provider_ref = result.payout_batch_id
        _audit(db, moderator_id, "submitted", p, provider_ref=result.payout_batch_id,
               method=method.value)
    db.commit()
    return {"batch_id": batch, "submitted": len(payouts), "status": "processing",
            "provider_ref": result.payout_batch_id}


def refresh_batch(db: Session, batch: str, moderator_id: uuid.UUID | None = None) -> dict:
    """Poll the provider and settle each payout: SUCCESS -> paid; a terminal
    failure -> failed + wallet refunded."""
    payouts = db.scalars(select(Payout).where(
        Payout.batch_id == batch, Payout.status == PayoutStatus.processing)).all()
    if not payouts:
        return {"batch_id": batch, "updated": 0, "status": "nothing_processing"}
    ref = next((p.provider_ref for p in payouts if p.provider_ref), None)
    if not ref:
        return {"batch_id": batch, "updated": 0, "status": "no_provider_ref"}
    try:
        remote = paypal.get_batch(ref)
    except (paypal.PayPalError, paypal.PayPalNotConfigured) as exc:
        return {"batch_id": batch, "updated": 0, "status": "poll_failed",
                "error": str(exc)}

    paid = failed = 0
    batch_status = remote.get("batch_status")
    for p in payouts:
        txn = (remote.get("items") or {}).get(p.payout_id)
        if txn == paypal.TXN_SUCCESS:
            mark_paid(db, p, provider_ref=ref, commit=False, moderator_id=moderator_id,
                      via_provider=True)
            paid += 1
        elif txn in paypal.TXN_FAILURES or batch_status in paypal.TERMINAL_FAILURE_BATCH:
            mark_failed(db, p, reason=f"provider status {txn or batch_status}",
                        commit=False, moderator_id=moderator_id)
            failed += 1
        # PENDING / UNCLAIMED / ONHOLD stay `processing` — not settled yet.
    db.commit()
    return {"batch_id": batch, "updated": paid + failed, "paid": paid,
            "failed": failed, "batch_status": batch_status}


def mark_paid(db: Session, payout: Payout, provider_ref: str | None = None,
              commit: bool = True, *, moderator_id: uuid.UUID | None = None,
              via_provider: bool = False) -> Payout:
    payout = _locked(db, payout)
    if payout.status not in (PayoutStatus.scheduled, PayoutStatus.processing):
        raise _conflict("Only a scheduled or processing payout can be marked paid.",
                        "payout_not_payable")
    payout.status = PayoutStatus.paid
    payout.paid_at = _now()
    if provider_ref:
        payout.provider_ref = provider_ref
    _audit(db, moderator_id, "paid", payout, provider_ref=payout.provider_ref,
           via="provider" if via_provider else "manual")
    sandbox = via_provider and payout.method == PayoutMethod.paypal_sandbox
    _tell(db, payout, "payout_paid", f"Your {_peso(payout.amount)} withdrawal was paid",
          ("Paid through PayPal sandbox (test mode) — no real money moved. "
           if sandbox else "")
          + (f"Reference: {payout.provider_ref}" if payout.provider_ref else ""))
    if commit:
        db.commit()
        db.refresh(payout)
    return payout


def mark_failed(db: Session, payout: Payout, reason: str,
                commit: bool = True, *, moderator_id: uuid.UUID | None = None) -> Payout:
    """Failure refunds the reserved wallet money — the user keeps their earnings."""
    payout = _locked(db, payout)
    if payout.status not in (PayoutStatus.scheduled, PayoutStatus.processing):
        raise _conflict("Only a scheduled or processing payout can fail.",
                        "payout_not_failable")
    payout.status = PayoutStatus.failed
    payout.failure_reason = reason
    wallet.adjust(db, payout.user_id, payout.amount)
    _audit(db, moderator_id, "failed", payout, reason=reason)
    _tell(db, payout, "payout_failed",
          f"Your {_peso(payout.amount)} withdrawal couldn't be paid",
          f"The money is back in your balance. Reason: {reason}")
    if commit:
        db.commit()
        db.refresh(payout)
    return payout


def cancel(db: Session, payout: Payout, moderator_id: uuid.UUID | None = None) -> Payout:
    """Admin cancel — only while still scheduled (nothing has been submitted)."""
    payout = _locked(db, payout)
    if payout.status != PayoutStatus.scheduled:
        raise _conflict("Only a scheduled payout can be cancelled.",
                        "payout_not_cancellable")
    payout.status = PayoutStatus.cancelled
    wallet.adjust(db, payout.user_id, payout.amount)
    _audit(db, moderator_id, "cancelled", payout)
    _tell(db, payout, "payout_cancelled",
          f"Your {_peso(payout.amount)} withdrawal was cancelled",
          "The money is back in your balance; you can request it again.")
    db.commit()
    db.refresh(payout)
    return payout


def retry(db: Session, payout: Payout, moderator_id: uuid.UUID | None = None) -> Payout:
    """Re-schedule a failed payout: re-reserve the money into a fresh batch."""
    payout = _locked(db, payout)
    if payout.status != PayoutStatus.failed:
        raise _conflict("Only a failed payout can be retried.", "payout_not_retryable")
    user = db.get(User, payout.user_id)
    if user is None or user.wallet_balance < payout.amount:
        raise _conflict("The wallet no longer covers this payout.",
                        "insufficient_wallet_balance")
    today = _now().astimezone(MANILA).date()  # see schedule_payouts
    payout.status = PayoutStatus.scheduled
    payout.failure_reason = None
    payout.provider_ref = None
    payout.batch_id = f"{batch_id_for(today)}_retry_{uuid.uuid4().hex[:6]}"
    payout.scheduled_for = today
    wallet.adjust(db, payout.user_id, -payout.amount)
    _audit(db, moderator_id, "retried", payout)
    db.commit()
    db.refresh(payout)
    return payout


def get_or_404(db: Session, payout_id: uuid.UUID) -> Payout:
    payout = db.get(Payout, payout_id)
    if payout is None:
        raise NotFoundError("Payout not found.", code="payout_not_found")
    return payout


def list_own(db: Session, user_id: uuid.UUID, limit: int = 50) -> list[Payout]:
    return list(db.scalars(select(Payout).where(Payout.user_id == user_id)
                           .order_by(Payout.created_at.desc()).limit(min(limit, 100))))


def list_admin(db: Session, status: PayoutStatus | None = None,
               batch_id: str | None = None, limit: int = 50) -> list[Payout]:
    stmt = select(Payout)
    if status is not None:
        stmt = stmt.where(Payout.status == status)
    if batch_id:
        stmt = stmt.where(Payout.batch_id == batch_id)
    return list(db.scalars(stmt.order_by(Payout.created_at.desc())
                           .limit(min(limit, 100))))


def admin_rows(db: Session, status: PayoutStatus | None = None,
               batch_id: str | None = None, limit: int = 50) -> list[dict]:
    """The payout list with who it is for and where it goes: a moderator
    paying by hand needs the recipient's PayPal address, and nothing else
    about them."""
    from app.services import qa_sandbox_service
    payouts = list_admin(db, status, batch_id, limit)
    users = {u.id: u for u in db.scalars(select(User).where(
        User.id.in_({p.user_id for p in payouts})))} if payouts else {}
    testers = qa_sandbox_service.tester_ids(db)
    return [{"payout": p, "username": getattr(users.get(p.user_id), "username", None),
             "payout_account": getattr(users.get(p.user_id), "payout_account", None),
             "payout_account_name": getattr(users.get(p.user_id), "payout_account_name", None),
             "display_name": getattr(users.get(p.user_id), "display_name", None),
             "trust_stage": getattr(users.get(p.user_id), "trust_stage", None),
             "trust_level_name": getattr(users.get(p.user_id), "trust_level_name", None),
             "qa_tester": p.user_id in testers} for p in payouts]


def admin_summary(db: Session, *, now: datetime | None = None) -> dict:
    """The admin Payouts screen's three cards (Figma Screen/Admin/Payouts).

    to send            requests not yet paid (scheduled or processing)
    sent this month    paid since the first of this Manila month
    waiting in wallets cleared money members have not asked for yet: each
                       wallet less its uncleared share (the §19 rule), summed
    below minimum      members whose cleared money is more than nothing but less
                       than the minimum cashout, so they cannot ask for it yet:
                       0 < withdrawable < payout_min_php - the same balance rule
                       and the same minimum `request_cashout` refuses below (the
                       minimum itself can be cashed out). A claimed seller cannot
                       cash out at all, so is not "below the minimum".
    """
    now = now or datetime.now(MANILA)
    month_start = datetime.combine(now.astimezone(MANILA).date().replace(day=1),
                                   datetime.min.time(), tzinfo=MANILA)
    open_states = (PayoutStatus.scheduled, PayoutStatus.processing)
    to_send_total, to_send_count, oldest = db.execute(
        select(func.coalesce(func.sum(Payout.amount), 0), func.count(Payout.id),
               func.min(Payout.created_at))
        .where(Payout.status.in_(open_states))).one()
    sent_total, sent_count = db.execute(
        select(func.coalesce(func.sum(Payout.amount), 0), func.count(Payout.id))
        .where(Payout.status == PayoutStatus.paid, Payout.paid_at >= month_start)).one()
    paid_all = int(db.scalar(select(func.count(Payout.id))
                             .where(Payout.status == PayoutStatus.paid)) or 0)
    failed = int(db.scalar(select(func.count(Payout.id))
                           .where(Payout.status == PayoutStatus.failed)) or 0)
    wallets = db.execute(select(User.id, User.wallet_balance, User.is_claimed_seller)
                         .where(User.wallet_balance > 0)).all()
    uncleared = uncleared_shares(db, [uid for uid, _, _ in wallets])
    minimum = Decimal(settings.payout_min_php)
    waiting = Decimal("0.00")
    below_minimum = 0
    for uid, bal, seller in wallets:
        cleared = withdrawable_from(bal, uncleared.get(uid, Decimal("0")))
        waiting += cleared
        if not seller and Decimal("0") < cleared < minimum:
            below_minimum += 1
    return {
        "to_send_total": Decimal(to_send_total), "to_send_count": int(to_send_count),
        "oldest_requested_at": oldest,
        "sent_month_total": Decimal(sent_total), "sent_month_count": int(sent_count),
        "month_start": month_start.date(),
        "sent_count": paid_all, "failed_count": failed,
        "waiting_in_wallets": waiting,
        "below_minimum_count": below_minimum, "payout_minimum": minimum,
    }


def member_breakdown(db: Session, user: User) -> dict:
    """The contributor Payout screen's extra figures (Figma Screen/Payout, meeting
    2026-10-02, 4:12): what the withdrawable money is made of (the pie chart),
    how far it is from the minimum (the locked state) and what is in flight.

    The wallet is one pot of money: Honesty Fund credits are counted in it up to
    the balance, and are always cleared (a fund credit has no marketplace
    remittance to wait for), so the withdrawable fund part is the smaller of the
    two; the rest of the withdrawable money is commission.
    """
    from app.models.honesty_fund import HonestyFundDistribution

    cent = Decimal("0.01")
    balance = Decimal(user.wallet_balance or 0).quantize(cent)
    available = withdrawable(db, user)
    fund_earned = Decimal(db.scalar(
        select(func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0))
        .where(HonestyFundDistribution.reviewer_id == user.id)) or 0).quantize(cent)
    fund = min(available, min(balance, fund_earned))
    in_flight = Decimal(db.scalar(
        select(func.coalesce(func.sum(Payout.amount), 0))
        .where(Payout.user_id == user.id,
               Payout.status.in_((PayoutStatus.scheduled, PayoutStatus.processing)))) or 0)
    minimum = Decimal(settings.payout_min_php).quantize(cent)
    return {
        "withdrawable_commission": available - fund,
        "withdrawable_honesty_fund": fund,
        "short_of_minimum": max(Decimal("0.00"), minimum - available),
        "in_flight": in_flight.quantize(cent),
    }

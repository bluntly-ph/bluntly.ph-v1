"""Payout endpoints (M3 slice 11).

Manual mode is always available: a moderator can mark a payout paid with the
provider reference from their own PayPal dashboard, so payouts work end-to-end
without any API credentials.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import MANILA
from app.core.errors import AppError
from app.core.link_policy import reject_links
from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.enums import PayoutMethod, PayoutStatus, Platform
from app.models.user import User
from app.schemas.referral import ReasonRequest
from app.services import honesty_fund_cycles, payout_service, payout_simulation, qa_sandbox_service
from app.services.payout_simulation import SimulationOut
from app.services.reporting.common import mask_destination

router = APIRouter(tags=["payouts"])


class PayoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payout_id: str | None = None
    user_id: uuid.UUID
    amount: Decimal
    currency: str
    status: PayoutStatus
    method: PayoutMethod
    provider_ref: str | None = None
    batch_id: str | None = None
    scheduled_for: date
    paid_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime


class AdminPayoutOut(PayoutOut):
    """A payout as the moderator paying it sees it."""

    username: str | None = None
    #: The recipient's PayPal address — what a manual payment is sent to.
    payout_account: str | None = None
    #: The name the recipient gave for that account; checked before sending.
    payout_account_name: str | None = None
    #: The recipient is a named QA tester (their balance may hold test money).
    qa_tester: bool = False
    #: Who it is for, as the Payouts table shows them (Figma 8024:12721).
    display_name: str | None = None
    trust_stage: int | None = None
    trust_level_name: str | None = None


class ProviderStatusOut(BaseModel):
    """How payouts leave Bluntly now. Never a credential, only whether one exists."""

    provider: str
    method: PayoutMethod
    paypal_configured: bool
    api_base_is_sandbox: bool
    api_submission_available: bool
    minimum_cashout: Decimal
    qa_test_earnings_allowed: bool


class PayoutAccountUpdate(BaseModel):
    payout_account: EmailStr | None = Field(
        default=None, description="The PayPal email. Omitted: keep the current one.")
    #: The name on the PayPal account (Screen/Payout/Details). Omitted: unchanged.
    account_name: str | None = Field(default=None, max_length=120)

    @field_validator("account_name")
    @classmethod
    def _plain_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())
        if not v:
            raise ValueError("Enter the name on your account.")
        return reject_links(v, field="account names")


class MarkPaidRequest(BaseModel):
    provider_ref: str = Field(min_length=1, max_length=128)


class CashoutRequest(BaseModel):
    """Omit `amount` to withdraw the whole cleared balance."""

    amount: Decimal | None = Field(default=None, gt=0, le=Decimal("10000000"))


class BalanceOut(BaseModel):
    """Business Rules §19: what can be cashed out, and what is still clearing."""

    wallet_balance: Decimal
    #: Cleared and reconciled: the only amount a cashout may draw on.
    withdrawable: Decimal
    #: Earned, but the marketplace has not paid Bluntly for that cycle yet.
    pending_clearance: Decimal
    minimum_cashout: Decimal
    can_cash_out: bool
    payout_account_set: bool
    #: A named QA tester: their balance may hold sandbox test earnings.
    qa_tester: bool = False
    #: The Payout screen (Figma Screen/Payout): the withdrawable money split
    #: into commission and Honesty Fund (its pie chart)...
    withdrawable_commission: Decimal = Decimal("0.00")
    withdrawable_honesty_fund: Decimal = Decimal("0.00")
    #: ...how far it is from the minimum (its locked state), 0 once reached...
    short_of_minimum: Decimal = Decimal("0.00")
    #: ...what is already requested and waiting to be sent...
    in_flight: Decimal = Decimal("0.00")
    #: ...and where it goes, masked (j***@gmail.com); never the full address.
    payout_account_masked: str | None = None
    #: The name on it, as the member gave it (their own data).
    payout_account_name: str | None = None


class RemittanceIn(BaseModel):
    platform: Platform
    cycle_month: date = Field(description="Any day in the cycle's month.")
    amount_received: Decimal = Field(ge=0, le=Decimal("100000000"))
    received_on: date
    reference: str | None = Field(default=None, max_length=200)


class RunRequest(BaseModel):
    submit: bool = Field(default=False,
                         description="Also hand the batch to the provider now.")


@router.patch("/auth/me/payout-account", summary="Set where your payouts are sent")
def set_payout_account(payload: PayoutAccountUpdate, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> dict:
    if payload.payout_account is None and payload.account_name is None:
        raise AppError("Nothing to change.", code="payout_account_empty", status_code=422,
                       title="Invalid payout account")
    if payload.payout_account is not None:
        user.payout_account = str(payload.payout_account)
    if payload.account_name is not None:
        user.payout_account_name = payload.account_name
    db.commit()
    return {"payout_account": user.payout_account,
            "account_name": user.payout_account_name}


@router.get("/payouts/balance", response_model=BalanceOut,
            summary="Your cleared (withdrawable) and pending balances")
def my_balance(db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> BalanceOut:
    available = payout_service.withdrawable(db, user)
    pending = payout_service.uncleared_share(db, user.id)
    return BalanceOut(
        wallet_balance=user.wallet_balance, withdrawable=available,
        pending_clearance=pending, minimum_cashout=settings.payout_min_php,
        can_cash_out=available >= settings.payout_min_php and bool(user.payout_account),
        payout_account_set=bool(user.payout_account),
        qa_tester=qa_sandbox_service.is_tester(db, user.id),
        payout_account_masked=mask_destination(user.payout_account),
        payout_account_name=user.payout_account_name,
        **payout_service.member_breakdown(db, user),
    )


@router.post("/payouts/cashout", response_model=PayoutOut, status_code=201,
             summary="Request a cashout of cleared funds (no cooldown; batched)")
def cashout(payload: CashoutRequest, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> PayoutOut:
    return PayoutOut.model_validate(payout_service.request_cashout(db, user, payload.amount))


@router.post("/admin/remittances", summary="Record a marketplace payout; clears that cycle")
def record_remittance(payload: RemittanceIn, db: Session = Depends(get_db),
                      mod: User = Depends(require_staff)) -> dict:
    return payout_service.record_remittance(
        db, mod, payload.platform, payload.cycle_month, payload.amount_received,
        payload.received_on, payload.reference)


@router.get("/payouts", response_model=list[PayoutOut], summary="Your payouts")
def list_own(db: Session = Depends(get_db), user: User = Depends(get_current_user),
             limit: int = Query(50, ge=1, le=100)) -> list[PayoutOut]:
    return [PayoutOut.model_validate(p) for p in payout_service.list_own(db, user.id, limit)]


@router.get("/payouts/simulate", response_model=SimulationOut,
            summary="Preview a GCash or Maya payout of your balance (simulation; moves no money)")
def simulate_payout(rail: Literal["gcash", "maya"] = Query(...),
                    user: User = Depends(get_current_user)) -> SimulationOut:
    """Completion contract X.4: GCash and Maya are simulated, never paid.

    A GET with no database session at all: the balance is read off the
    authenticated user, and `payout_simulation.simulate` only describes.
    """
    return payout_simulation.simulate(user.wallet_balance, rail,
                                      minimum=settings.payout_min_php,
                                      today=datetime.now(MANILA).date())


@router.get("/admin/payouts", response_model=list[AdminPayoutOut],
            summary="All payouts, with each recipient's PayPal address (administrator)")
def admin_list(db: Session = Depends(get_db),
               mod: User = Depends(require_staff),
               status: PayoutStatus | None = None, batch_id: str | None = None,
               limit: int = Query(50, ge=1, le=100)) -> list[AdminPayoutOut]:
    return [AdminPayoutOut(**PayoutOut.model_validate(row["payout"]).model_dump(),
                           username=row["username"], payout_account=row["payout_account"],
                           payout_account_name=row["payout_account_name"],
                           qa_tester=row["qa_tester"], display_name=row["display_name"],
                           trust_stage=row["trust_stage"],
                           trust_level_name=row["trust_level_name"])
            for row in payout_service.admin_rows(db, status, batch_id, limit)]


class AdminPayoutSummaryOut(BaseModel):
    to_send_total: Decimal
    to_send_count: int
    oldest_requested_at: datetime | None
    sent_month_total: Decimal
    sent_month_count: int
    month_start: date
    sent_count: int
    failed_count: int
    #: Cleared money members have not asked for yet (wallet less uncleared).
    waiting_in_wallets: Decimal
    #: Members with cleared money above 0 but under the minimum cashout, who
    #: cannot withdraw it yet (Overview "Below ₱300 threshold").
    below_minimum_count: int
    #: The minimum cashout those members are below (settings.payout_min_php).
    payout_minimum: Decimal


class FundCycleOut(BaseModel):
    month: date
    pool: Decimal
    contributors: int
    largest_share: Decimal | None = None
    distributed: Decimal
    distributed_at: datetime | None = None
    #: "collecting" (this month), "distributed", or "not_distributed".
    status: str


class FundCyclesOut(BaseModel):
    current: FundCycleOut
    closes_on: date
    distributes_on: date
    last: FundCycleOut | None = None
    cycles: list[FundCycleOut]


@router.get("/admin/payouts/honesty-fund", response_model=FundCyclesOut,
            summary="The Honesty Fund tab: this cycle, the last distribution, recent cycles")
def admin_honesty_fund(db: Session = Depends(get_db),
                       mod: User = Depends(require_staff)) -> FundCyclesOut:
    f = honesty_fund_cycles.build(db)
    return FundCyclesOut(
        current=FundCycleOut(**f.current.__dict__), closes_on=f.closes_on,
        distributes_on=f.distributes_on,
        last=FundCycleOut(**f.last.__dict__) if f.last else None,
        cycles=[FundCycleOut(**c.__dict__) for c in f.cycles])


@router.get("/admin/payouts/summary", response_model=AdminPayoutSummaryOut,
            summary="The Payouts screen's cards: to send, sent this month, waiting in wallets")
def admin_summary(db: Session = Depends(get_db),
                  mod: User = Depends(require_staff)) -> AdminPayoutSummaryOut:
    return AdminPayoutSummaryOut(**payout_service.admin_summary(db))


@router.get("/admin/payouts/provider", response_model=ProviderStatusOut,
            summary="How payouts are sent right now (administrator; no secrets)")
def provider_status(mod: User = Depends(require_staff)) -> ProviderStatusOut:
    return ProviderStatusOut(**payout_service.provider_status())


@router.post("/admin/payouts/run", summary="Process requested payouts now (administrator)")
def run_scheduler(payload: RunRequest, db: Session = Depends(get_db),
                  mod: User = Depends(require_staff)) -> dict:
    # Business Rules §15: processes reviewers' own requests only; no sweep.
    result = payout_service.schedule_payouts(db, triggered_by=mod.id)
    if payload.submit and result["scheduled"]:
        result["submission"] = [payout_service.submit_batch(db, b, moderator_id=mod.id)
                                for b in result["batches"]]
    return result


@router.post("/admin/payouts/{payout_id}/mark-paid", response_model=PayoutOut,
             summary="Mark a payout paid by hand (administrator; manual rail)")
def mark_paid(payout_id: uuid.UUID, payload: MarkPaidRequest,
              db: Session = Depends(get_db),
              mod: User = Depends(require_staff)) -> PayoutOut:
    payout = payout_service.get_or_404(db, payout_id)
    return PayoutOut.model_validate(
        payout_service.mark_paid(db, payout, provider_ref=payload.provider_ref,
                                 moderator_id=mod.id))


@router.post("/admin/payouts/{payout_id}/fail", response_model=PayoutOut,
             summary="Mark a payout failed (administrator; refunds the wallet)")
def mark_failed(payout_id: uuid.UUID, payload: ReasonRequest,
                db: Session = Depends(get_db),
                mod: User = Depends(require_staff)) -> PayoutOut:
    payout = payout_service.get_or_404(db, payout_id)
    return PayoutOut.model_validate(
        payout_service.mark_failed(db, payout, reason=payload.reason, moderator_id=mod.id))


@router.post("/admin/payouts/{payout_id}/retry", response_model=PayoutOut,
             summary="Retry a failed payout (administrator)")
def retry(payout_id: uuid.UUID, db: Session = Depends(get_db),
          mod: User = Depends(require_staff)) -> PayoutOut:
    payout = payout_service.get_or_404(db, payout_id)
    return PayoutOut.model_validate(payout_service.retry(db, payout, moderator_id=mod.id))


@router.post("/admin/payouts/{payout_id}/cancel", response_model=PayoutOut,
             summary="Cancel a scheduled payout (administrator; refunds the wallet)")
def cancel(payout_id: uuid.UUID, db: Session = Depends(get_db),
           mod: User = Depends(require_staff)) -> PayoutOut:
    payout = payout_service.get_or_404(db, payout_id)
    return PayoutOut.model_validate(payout_service.cancel(db, payout, moderator_id=mod.id))


@router.post("/admin/payouts/batches/{batch_id}/refresh",
             summary="Poll the provider and settle a batch (administrator)")
def refresh_batch(batch_id: str, db: Session = Depends(get_db),
                  mod: User = Depends(require_staff)) -> dict:
    return payout_service.refresh_batch(db, batch_id, moderator_id=mod.id)

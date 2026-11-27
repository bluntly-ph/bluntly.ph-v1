"""QA sandbox test earnings (owner decision, 2026-09-27).

Real QA testers need to see the whole payout path — money in their balance, a
withdrawal request, the batch, a PayPal sandbox payment, "paid" — before the
defense, and none of them will have made a marketplace sale through a Bluntly
link by then. So a moderator can credit one of a tester's published reviews
with a labelled test earning.

The rules that keep this from ever becoming money anybody is owed:

* **Only accounts the owner names.** The list lives in `platform_settings`
  (`qa_testers`); only a Super Admin changes it. An administrator can credit a
  tester, never make someone one.
* **Never on live PayPal.** Refused outright when `PAYOUT_PROVIDER=paypal_live`,
  and a live batch leaves out anyone holding test money
  (`payout_service.submit_batch`). PayPal stays SANDBOX.
* **One per review, capped.** ₱350 by default (enough to clear the ₱300
  cashout minimum), at most ₱1,000; the partial unique index
  `uq_commission_one_qa_test` backs the one-per-review rule.
* **The real ledger, labelled.** An ordinary commission row with
  `is_test = true`, cleared at once, so the tester's wallet, cashout and history
  behave exactly as they do for real earnings. No platform share and no
  Honesty Fund share (`ck_commission_test_no_revenue`), and every revenue or
  pool figure filters it out.
* **Audited and announced.** Each change to the list and each credit writes a
  moderation log entry; the tester is told what arrived and that it is not
  real money.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import AppError, NotFoundError
from app.models.commission import Commission
from app.models.enums import CommissionTarget, ModerationAction, PayoutMethod
from app.models.moderation import ModerationLog
from app.models.review import Review
from app.models.triage import PlatformSetting
from app.models.user import User
from app.services import notification_service, wallet

SETTINGS_KEY = "qa_testers"
DEFAULT_AMOUNT = Decimal("350.00")
MAX_AMOUNT = Decimal("1000.00")
#: `commissions.csv_source` for every test earning: never a file, never a provider.
SOURCE = "qa_sandbox"


def _conflict(detail: str, code: str) -> AppError:
    return AppError(detail, code=code, status_code=409, title="Conflicting state")


def _log(db: Session, actor_id: uuid.UUID, action: ModerationAction,
         target: uuid.UUID, context: dict) -> None:
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=actor_id,
                         action=action, target_ref=target, context=context))


def tester_ids(db: Session) -> set[uuid.UUID]:
    row = db.get(PlatformSetting, SETTINGS_KEY)
    raw = (row.value or {}).get("user_ids", []) if row is not None else []
    out: set[uuid.UUID] = set()
    for value in raw if isinstance(raw, list) else []:
        try:
            out.add(uuid.UUID(str(value)))
        except ValueError:
            continue
    return out


def is_tester(db: Session, user_id: uuid.UUID) -> bool:
    return user_id in tester_ids(db)


def _save(db: Session, ids: set[uuid.UUID], owner_id: uuid.UUID) -> None:
    row = db.get(PlatformSetting, SETTINGS_KEY)
    value = {"user_ids": sorted(str(i) for i in ids)}
    if row is None:
        db.add(PlatformSetting(key=SETTINGS_KEY, value=value, updated_by=owner_id))
    else:
        row.value = value
        row.updated_at = datetime.now(UTC)
        row.updated_by = owner_id


def _resolve(db: Session, identifier: str) -> User:
    """A username (with or without @) or an email, case-insensitively."""
    ident = identifier.strip()
    if not ident:
        raise AppError("Give a username or an email.", code="qa_tester_identifier_missing",
                       status_code=422, title="Invalid QA tester")
    if "@" in ident[1:]:
        user = db.scalar(select(User).where(func.lower(User.email) == ident.lower()))
    else:
        user = db.scalar(select(User).where(
            func.lower(User.username) == ident.lstrip("@").lower()))
    if user is None:
        raise NotFoundError("No account has that username or email.",
                            code="qa_tester_not_found")
    return user


def add_tester(db: Session, owner: User, identifier: str) -> User:
    user = _resolve(db, identifier)
    if user.is_claimed_seller:
        raise _conflict("A claimed seller account has no earnings to withdraw, so it "
                        "cannot test payouts.", "seller_cannot_earn")
    ids = tester_ids(db)
    if user.id not in ids:
        ids.add(user.id)
        _save(db, ids, owner.id)
        _log(db, owner.id, ModerationAction.qa_tester_add, user.id,
             {"username": user.username})
        db.commit()
    return user


def remove_tester(db: Session, owner: User, user_id: uuid.UUID) -> None:
    """Un-name a tester. Test earnings already credited stay in the ledger —
    removing the history would hide what happened — but no new one can be."""
    ids = tester_ids(db)
    if user_id not in ids:
        raise NotFoundError("That account is not a QA tester.", code="qa_tester_not_found")
    ids.discard(user_id)
    _save(db, ids, owner.id)
    _log(db, owner.id, ModerationAction.qa_tester_remove, user_id, {})
    db.commit()


def testers(db: Session) -> list[dict]:
    """The named testers with their balance and each published review's credit."""
    ids = tester_ids(db)
    if not ids:
        return []
    users = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.username)).all()
    reviews = db.scalars(select(Review).where(
        Review.author_id.in_(ids), Review.published_at.is_not(None),
        Review.is_removed.is_(False), Review.removed_by_author_at.is_(None),
        (Review.thread_id.is_(None)) | (Review.thread_id == Review.id),
    ).order_by(Review.published_at.desc())).all()
    credits = {c.review_id: c for c in db.scalars(select(Commission).where(
        Commission.is_test.is_(True), Commission.reviewer_id.in_(ids)))}
    out = []
    for user in users:
        own = [r for r in reviews if r.author_id == user.id]
        out.append({
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "payout_account_set": bool(user.payout_account),
            "wallet_balance": Decimal(user.wallet_balance or 0),
            "test_earned": sum((Decimal(c.reviewer_share) for c in credits.values()
                                if c.reviewer_id == user.id), Decimal("0")),
            "reviews": [{
                "review_id": r.id,
                "title": r.title,
                "published_at": r.published_at,
                "credited_amount": (Decimal(credits[r.id].reviewer_share)
                                    if r.id in credits else None),
                "credited_at": credits[r.id].created_at if r.id in credits else None,
            } for r in own[:20]],
        })
    return out


def credit(db: Session, moderator: User, review_id: uuid.UUID,
           amount: Decimal | None = None) -> Commission:
    """Credit a QA tester's published review with one sandbox test earning."""
    from app.services.payout_service import current_method

    if current_method() == PayoutMethod.paypal_live:
        raise _conflict("Test earnings are refused while payouts run on live PayPal.",
                        "qa_sandbox_live_provider")
    amount = (Decimal(amount) if amount is not None else DEFAULT_AMOUNT).quantize(
        Decimal("0.01"))
    if not Decimal("1.00") <= amount <= MAX_AMOUNT:
        raise AppError(f"A test earning is between ₱1 and ₱{MAX_AMOUNT:,.0f}.",
                       code="qa_test_amount_out_of_range", status_code=422,
                       title="Invalid test earning")
    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review not found.", code="review_not_found")
    if review.author_id is None or not is_tester(db, review.author_id):
        raise _conflict("Only a named QA tester's review can take a test earning.",
                        "not_a_qa_tester")
    if (review.published_at is None or review.is_removed
            or review.removed_by_author_at is not None or not review.is_thread_root):
        raise _conflict("Only a published original review can take a test earning.",
                        "review_not_published")
    if db.scalar(select(Commission.id).where(
            Commission.review_id == review.id, Commission.is_test.is_(True))) is not None:
        raise _conflict("This review already has its test earning.",
                        "qa_test_credit_exists")

    now = datetime.now(UTC)
    today = now.astimezone(MANILA).date()
    commission = Commission(
        commission_id=f"qa_{uuid.uuid4().hex[:12]}",
        target_type=CommissionTarget.review,
        review_id=review.id,
        reviewer_id=review.author_id,
        reviewer_share_bps=10000,
        gross_amount=amount,
        platform_share=Decimal("0.00"),
        reviewer_share=amount,
        honesty_fund_share=Decimal("0.00"),
        currency="PHP",
        csv_source=SOURCE,
        row_reference=f"review:{review.id}",
        order_status="qa_sandbox",
        cycle_month=today.replace(day=1),
        # Cleared at once: there is no marketplace payout to wait for, and the
        # point is to let the tester withdraw it.
        cleared_at=now,
        is_test=True,
    )
    db.add(commission)
    wallet.adjust(db, review.author_id, amount)
    _log(db, moderator.id, ModerationAction.qa_test_credit, review.id,
         {"amount": str(amount), "commission_id": commission.commission_id,
          "reviewer_id": str(review.author_id)})
    notification_service.notify(
        db, review.author_id, "qa_test_earning",
        f"Sandbox test earning: ₱{amount:,.2f} for QA",
        body=("QA only — not real money. It is ready to withdraw now: request a "
              "withdrawal on Transfer to test a PayPal sandbox payout."),
        link="/dashboard/transfer")
    try:
        db.commit()
    except IntegrityError as exc:
        # Two moderators crediting the same review at once: the partial unique
        # index lets exactly one through.
        db.rollback()
        raise _conflict("This review already has its test earning.",
                        "qa_test_credit_exists") from exc
    db.refresh(commission)
    return commission

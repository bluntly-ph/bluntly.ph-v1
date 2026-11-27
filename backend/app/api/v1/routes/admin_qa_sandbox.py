"""QA sandbox test earnings (owner decision, 2026-09-27; `qa_sandbox_service`).

Moderators see the named QA testers and credit one of their published reviews
with a labelled test earning. Only a Super Admin (`require_super_admin`) names
or un-names a tester: the list decides who may receive test money at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import is_super_admin, require_staff, require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.services import qa_sandbox_service

router = APIRouter(prefix="/admin/qa-sandbox", tags=["admin: QA sandbox"])


class TesterReviewOut(BaseModel):
    review_id: uuid.UUID
    title: str | None = None
    published_at: datetime | None = None
    #: The test earning already credited to this review, if any.
    credited_amount: Decimal | None = None
    credited_at: datetime | None = None


class TesterOut(BaseModel):
    user_id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    payout_account_set: bool
    wallet_balance: Decimal
    test_earned: Decimal
    reviews: list[TesterReviewOut]


class TestersOut(BaseModel):
    testers: list[TesterOut]
    default_amount: Decimal
    max_amount: Decimal
    #: The caller is a Super Admin, the only role that can change the list.
    can_manage_testers: bool = False


class TesterIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=320,
                            description="A username (with or without @) or an email.")


class CreditIn(BaseModel):
    review_id: uuid.UUID
    amount: Decimal | None = Field(default=None, gt=0, le=qa_sandbox_service.MAX_AMOUNT)


class CreditOut(BaseModel):
    commission_id: str | None
    review_id: uuid.UUID
    reviewer_id: uuid.UUID
    amount: Decimal
    cleared_at: datetime | None
    is_test: bool


def _testers(db: Session, viewer: User) -> TestersOut:
    return TestersOut(testers=[TesterOut(**t) for t in qa_sandbox_service.testers(db)],
                      default_amount=qa_sandbox_service.DEFAULT_AMOUNT,
                      max_amount=qa_sandbox_service.MAX_AMOUNT,
                      can_manage_testers=is_super_admin(viewer))


@router.get("/testers", response_model=TestersOut,
            summary="The named QA testers and their published reviews (administrator)")
def list_testers(db: Session = Depends(get_db),
                 mod: User = Depends(require_staff)) -> TestersOut:
    return _testers(db, mod)


@router.post("/testers", response_model=TestersOut, status_code=201,
             summary="Name an account as a QA tester (Super Admin)")
def add_tester(payload: TesterIn, db: Session = Depends(get_db),
               owner: User = Depends(require_super_admin)) -> TestersOut:
    qa_sandbox_service.add_tester(db, owner, payload.identifier)
    return _testers(db, owner)


@router.delete("/testers/{user_id}", response_model=TestersOut,
               summary="Stop an account being a QA tester (Super Admin)")
def remove_tester(user_id: uuid.UUID, db: Session = Depends(get_db),
                  owner: User = Depends(require_super_admin)) -> TestersOut:
    qa_sandbox_service.remove_tester(db, owner, user_id)
    return _testers(db, owner)


@router.post("/credits", response_model=CreditOut, status_code=201,
             summary="Credit a QA tester's review with a sandbox test earning (administrator)")
def credit(payload: CreditIn, db: Session = Depends(get_db),
           mod: User = Depends(require_staff)) -> CreditOut:
    row = qa_sandbox_service.credit(db, mod, payload.review_id, payload.amount)
    return CreditOut(commission_id=row.commission_id, review_id=row.review_id,
                     reviewer_id=row.reviewer_id, amount=row.reviewer_share,
                     cleared_at=row.cleared_at, is_test=row.is_test)

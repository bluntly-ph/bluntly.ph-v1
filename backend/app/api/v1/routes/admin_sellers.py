"""Seller moderation (FR-4, FR-9) — moderator only.

The whole router is guarded by `require_staff`, so neither a
`seller` nor an ordinary `user` can reach it: a store owner approving their
own claim, or removing the ratings of their own store, is the failure this
workflow exists to prevent. The service adds the narrower rule that a moderator
cannot decide a claim they submitted, nor remove a rating they wrote or one of
a store they run.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.user import User
from app.schemas.seller import (
    AppealDecisionIn,
    ClaimDecision,
    SellerAppealOut,
    SellerClaimOut,
    SellerReviewOut,
    SellerReviewRemoval,
    SubstantiationRequestIn,
)
from app.services import seller_service

router = APIRouter(prefix="/admin", tags=["admin"],
                   dependencies=[Depends(require_staff)])


@router.get("/seller-claims", response_model=list[SellerClaimOut],
            summary="Seller claims waiting for a decision, oldest first")
def pending_claims(db: Session = Depends(get_db),
                   limit: int = Query(50, ge=1, le=200),
                   offset: int = Query(0, ge=0)) -> list[SellerClaimOut]:
    return seller_service.list_pending_claims(db, limit, offset)


@router.post("/seller-claims/{claim_id}/decision", response_model=SellerClaimOut,
             summary="Approve or reject a seller claim")
def decide_claim(claim_id: uuid.UUID, decision: ClaimDecision,
                 db: Session = Depends(get_db),
                 moderator: User = Depends(get_current_user)) -> SellerClaimOut:
    return seller_service.decide_claim(db, claim_id, moderator, decision)


@router.post("/seller-reviews/{review_id}/removal", response_model=SellerReviewOut,
             summary="Remove a seller review from the store's page and numbers")
def remove_seller_review(review_id: uuid.UUID, payload: SellerReviewRemoval,
                         db: Session = Depends(get_db),
                         moderator: User = Depends(get_current_user)) -> SellerReviewOut:
    return seller_service.remove_seller_review(db, review_id, moderator, payload.note)


@router.get("/seller-review-appeals", response_model=list[SellerAppealOut],
            summary="Open seller appeals against reviews (oldest first); "
                    "?decided=true for upheld and dismissed ones")
def list_appeals(db: Session = Depends(get_db),
                 moderator: User = Depends(get_current_user),
                 limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0),
                 decided: bool = False) -> list[SellerAppealOut]:
    return seller_service.list_open_appeals(db, limit, decided=decided, offset=offset)


@router.post("/seller-review-appeals/{appeal_id}/substantiation-request",
             response_model=SellerAppealOut,
             summary="Ask the reviewer to substantiate an appealed review")
def request_substantiation(appeal_id: uuid.UUID, payload: SubstantiationRequestIn,
                           db: Session = Depends(get_db),
                           moderator: User = Depends(get_current_user)) -> SellerAppealOut:
    return seller_service.request_substantiation(db, appeal_id, moderator, payload.note)


@router.post("/seller-review-appeals/{appeal_id}/decision", response_model=SellerAppealOut,
             summary="Uphold (remove the review) or dismiss a seller's appeal")
def decide_appeal(appeal_id: uuid.UUID, payload: AppealDecisionIn,
                  db: Session = Depends(get_db),
                  moderator: User = Depends(get_current_user)) -> SellerAppealOut:
    return seller_service.decide_appeal(db, appeal_id, moderator, payload.decision, payload.note)

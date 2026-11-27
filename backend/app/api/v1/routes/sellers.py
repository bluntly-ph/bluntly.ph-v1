"""Seller routes (FR-4) — stores, their public ratings, and claim requests.

Reading is public: FR-2 lets anyone browse without an account. Adding a store,
rating one and claiming one each need an account. Deciding a claim is a
moderator action and lives in `admin_sellers`.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ForbiddenError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user, get_optional_user
from app.db.session import get_db
from app.models.enums import Platform
from app.models.user import User
from app.schemas.qa import QAAuthor
from app.schemas.report import ReportCreate, ReportOut
from app.schemas.seller import (
    SellerAppealIn,
    SellerAppealOut,
    SellerClaimCreate,
    SellerClaimOut,
    SellerCreate,
    SellerDashboardOut,
    SellerDetailOut,
    SellerOut,
    SellerReplyIn,
    SellerReplyOut,
    SellerResponseIn,
    SellerReviewCreate,
    SellerReviewOut,
    SellerVoteIn,
    SellerVoteOut,
    StoreQuestionOut,
    SubstantiationIn,
)
from app.services import seller_review_engagement, seller_service
from app.services.storage import review_photo_belongs_to

router = APIRouter(prefix="/sellers", tags=["sellers"])


@router.post("", response_model=SellerOut, status_code=201,
             summary="Find a store, or add it if it is new")
def add_seller(payload: SellerCreate, response: Response,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> SellerOut:
    """201 when the store is new, 200 when an existing one matched.

    Matching is by platform and normalised name, so casing and stray spaces
    return the existing store rather than a duplicate.
    """
    seller, created = seller_service.find_or_create_seller(db, payload)
    if not created:
        response.status_code = 200
    return SellerOut.model_validate(seller)


class SellerCount(BaseModel):
    total: int


class SellerFilters(BaseModel):
    q: str | None
    platform: Platform | None
    claimed: bool | None
    min_rating: int | None
    answers_within: Literal["day", "week"] | None


def _seller_filters(
    q: str | None = Query(None, max_length=160),
    platform: Platform | None = None,
    claimed: bool | None = Query(
        None, description="Profile: true = claimed by the owner, false = unclaimed. "
                          "Omitted = both."),
    min_rating: int | None = Query(
        None, ge=1, le=5,
        description='Rating: "4★ & up" or "3★ & up" (the overall rating shown).'),
    answers_within: Literal["day", "week"] | None = Query(
        None, description="Answers buyers: the store's median time to answer its "
                          "questions is within a day or a week."),
) -> SellerFilters:
    return SellerFilters(q=q, platform=platform, claimed=claimed, min_rating=min_rating,
                         answers_within=answers_within)


@router.get("", response_model=list[SellerOut], summary="Search stores")
def list_sellers(db: Session = Depends(get_db),
                 filters: SellerFilters = Depends(_seller_filters),
                 sort: Literal["ranked", "reviews", "name"] = Query(
                     "ranked", description="Ranked (best-evidenced first: rating confidence, "
                                           "number of reviews, recent activity), the "
                                           "most-reviewed first, or by name."),
                 limit: int = Query(30, ge=1, le=100)) -> list[SellerOut]:
    return seller_service.list_sellers(db, limit=limit, sort=sort, **filters.model_dump())


@router.get("/count", response_model=SellerCount,
            summary="How many stores the Sellers tab's filters match")
def count_sellers(db: Session = Depends(get_db),
                  filters: SellerFilters = Depends(_seller_filters)) -> SellerCount:
    """Sheet/Filter sellers' "Show 24 sellers", asked with the choices not yet
    applied. Declared before `/{seller_id}` so "count" is never parsed as an id."""
    return SellerCount(total=seller_service.count_sellers(db, **filters.model_dump()))


@router.get("/mine", response_model=list[SellerOut],
            summary="Stores this account runs (approved claims only)")
def my_stores(db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> list[SellerOut]:
    """Declared before `/{seller_id}` so "mine" is never parsed as a store id."""
    return seller_service.list_my_stores(db, user)


@router.get("/claims/mine", response_model=list[SellerClaimOut],
            summary="Your own store claims, newest first (any status)")
def my_claims(db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> list[SellerClaimOut]:
    """Declared before `/{seller_id}`, like /mine."""
    return seller_service.list_my_claims(db, user)


@router.post("/claims/{claim_id}/withdraw", response_model=SellerClaimOut,
             summary="Withdraw your own pending store claim")
def withdraw_claim(claim_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> SellerClaimOut:
    return seller_service.withdraw_claim(db, claim_id, user)


@router.get("/{seller_id}", response_model=SellerDetailOut,
            summary="A store with its public rating summary")
def get_seller(seller_id: uuid.UUID, db: Session = Depends(get_db)) -> SellerDetailOut:
    return seller_service.get_seller_detail(db, seller_id)


@router.get("/{seller_id}/dashboard", response_model=SellerDashboardOut,
            summary="The approved owner's view of their store (review monitoring)")
def seller_dashboard(seller_id: uuid.UUID, db: Session = Depends(get_db),
                     period: Literal["30d", "3m", "6m", "12m", "all"] = Query(
                         "6m", description="The Overview's period (tiles, breakdown)."),
                     user: User = Depends(get_current_user)) -> SellerDashboardOut:
    return seller_service.get_dashboard(db, seller_id, user, period)


@router.get("/{seller_id}/appeals", response_model=list[SellerAppealOut],
            summary="The flags this store's owner raised, newest first (claimed owner)")
def store_appeals(seller_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[SellerAppealOut]:
    return seller_service.list_store_appeals(db, seller_id, user)


@router.get("/{seller_id}/questions", response_model=list[StoreQuestionOut],
            summary="The store's questions with its own answers (claimed owner)")
def store_questions(seller_id: uuid.UUID, db: Session = Depends(get_db),
                    status: Literal["needs", "answered", "all"] = Query(
                        "all", description="needs = no answer from the store yet."),
                    limit: int = Query(100, ge=1, le=200),
                    user: User = Depends(get_current_user)) -> list[StoreQuestionOut]:
    return seller_service.list_store_questions(db, seller_id, user, status=status, limit=limit)


@router.post("/{seller_id}/reviews", response_model=SellerReviewOut, status_code=201,
             summary="Rate a store on FR-4's four dimensions")
def rate_seller(seller_id: uuid.UUID, payload: SellerReviewCreate,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> SellerReviewOut:
    # The same ownership rule as a product review's photo (routes/reviews.py):
    # without it any public image URL could be passed off as this buyer's own.
    for url in payload.photo_urls:
        if not review_photo_belongs_to(url, user.id):
            raise ForbiddenError(
                "A photo must be one you uploaded through /reviews/photo.",
                code="photo_not_owned")
    seller = seller_service.get_seller_or_404(db, seller_id)
    return seller_service.create_seller_review(db, seller, user, payload)


@router.get("/{seller_id}/reviews", response_model=list[SellerReviewOut],
            summary="A store's ratings, newest first")
def list_seller_reviews(seller_id: uuid.UUID, db: Session = Depends(get_db),
                        limit: int = Query(30, ge=1, le=100),
                        offset: int = Query(0, ge=0, le=10_000),
                        viewer: User | None = Depends(get_optional_user)) -> list[SellerReviewOut]:
    return seller_service.list_seller_reviews(db, seller_id, limit,
                                              viewer.id if viewer is not None else None,
                                              offset=offset)


# ---- QA-043: votes, replies and reports on a seller review -----------------

@router.put("/reviews/{review_id}/vote", response_model=SellerVoteOut,
            summary="Vote a seller review helpful or not (helpfulness only)")
def vote_seller_review(review_id: uuid.UUID, payload: SellerVoteIn,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> SellerVoteOut:
    review = seller_review_engagement.visible_review_or_404(db, review_id)
    up, down, mine = seller_review_engagement.vote(db, review, user, payload.direction)
    return SellerVoteOut(helpful_votes=up, unhelpful_votes=down, my_vote=mine)


@router.delete("/reviews/{review_id}/vote", response_model=SellerVoteOut,
               summary="Take back your vote on a seller review")
def unvote_seller_review(review_id: uuid.UUID, db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> SellerVoteOut:
    review = seller_review_engagement.visible_review_or_404(db, review_id)
    up, down, mine = seller_review_engagement.vote(db, review, user, None)
    return SellerVoteOut(helpful_votes=up, unhelpful_votes=down, my_vote=mine)


@router.post("/reviews/{review_id}/replies", response_model=SellerReplyOut, status_code=201,
             summary="Reply under a seller review")
def reply_to_seller_review(review_id: uuid.UUID, payload: SellerReplyIn,
                           db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)) -> SellerReplyOut:
    review = seller_review_engagement.visible_review_or_404(db, review_id)
    reply = seller_review_engagement.add_reply(db, review, user, payload.body)
    return SellerReplyOut(id=reply.id, body=reply.body, created_at=reply.created_at,
                          author=QAAuthor.model_validate(user))


@router.delete("/replies/{reply_id}", status_code=204, response_model=None,
               summary="Delete your own reply under a seller review")
def delete_seller_review_reply(reply_id: uuid.UUID, db: Session = Depends(get_db),
                               user: User = Depends(get_current_user)) -> None:
    seller_review_engagement.delete_reply(db, reply_id, user)


@router.post("/reviews/{review_id}/report", response_model=ReportOut, status_code=201,
             summary="Report a seller review to the administrators")
def report_seller_review(review_id: uuid.UUID, payload: ReportCreate, request: Request,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> ReportOut:
    enforce_rate_limit(request, "report", max_requests=settings.report_rate_limit_max)
    review = seller_review_engagement.visible_review_or_404(db, review_id)
    log, _created = seller_review_engagement.report(
        db, review, user, reason=payload.reason, notes=payload.notes,
        evidence_url=payload.evidence_url)
    return ReportOut.model_validate(log)


@router.post("/{seller_id}/claims", response_model=SellerClaimOut, status_code=201,
             summary="Ask to be recognised as this store's owner")
def claim_seller(seller_id: uuid.UUID, payload: SellerClaimCreate,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> SellerClaimOut:
    seller = seller_service.get_seller_or_404(db, seller_id)
    return seller_service.submit_claim(db, seller, user, payload)


@router.post("/reviews/{review_id}/response", response_model=SellerReviewOut,
             summary="Respond publicly to a review of your store (claimed owner)")
def respond_to_review(review_id: uuid.UUID, payload: SellerResponseIn,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> SellerReviewOut:
    return seller_service.respond_to_review(db, review_id, user, payload.body)


@router.post("/reviews/{review_id}/appeal", response_model=SellerAppealOut, status_code=201,
             summary="Flag a review of your store as suspected fake (claimed owner)")
def appeal_review(review_id: uuid.UUID, payload: SellerAppealIn,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> SellerAppealOut:
    return seller_service.appeal_review(db, review_id, user, payload.reason, payload.kind)


@router.get("/appeals/{appeal_id}", response_model=SellerAppealOut,
            summary="Read an appeal against your store review (reviewer)")
def get_appeal(appeal_id: uuid.UUID, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> SellerAppealOut:
    return seller_service.appeal_for_reviewer(db, appeal_id, user)


@router.post("/appeals/{appeal_id}/substantiation", response_model=SellerAppealOut,
             summary="Back up your store review when an admin asks (reviewer)")
def substantiate(appeal_id: uuid.UUID, payload: SubstantiationIn,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> SellerAppealOut:
    return seller_service.substantiate(db, appeal_id, user, payload.response)

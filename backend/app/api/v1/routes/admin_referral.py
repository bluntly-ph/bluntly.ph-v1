"""Moderator referral/publication endpoints (M2 slice 1). All RBAC=moderator,
all mutations audit-logged in `moderation_logs`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_staff
from app.db.session import get_db
from app.models.enums import EarnEligibleStatus
from app.models.user import User
from app.schemas.all_reviews import AllReviewsPage, AllReviewsSort, ReviewState
from app.schemas.referral import (
    AttachLinkRequest,
    AwaitingAffiliatePage,
    GateStateOut,
    ReasonRequest,
    ReferralLinkOut,
    ReviewQueueResponse,
)
from app.schemas.review import ReviewOut
from app.services import (
    all_reviews,
    earn_gate,
    monetization_attention,
    referral_service,
    review_service,
)
from app.services.moderation_priority import PriorityBand, PriorityLane, SlaState
from app.services.priority_tiers import Tier

router = APIRouter(prefix="/admin", tags=["admin: referral"],
                   dependencies=[Depends(require_staff)])


@router.get("/review-queue", response_model=ReviewQueueResponse,
            summary="Administrator queue: one policy-prioritized, filtered page")
def review_queue(
    db: Session = Depends(get_db),
    band: PriorityBand | None = Query(None, description="Filter to one priority band."),
    lane: PriorityLane | None = Query(None, description="Filter to one routing lane."),
    sla: SlaState | None = Query(None, description="Filter to one SLA state."),
    factor: str | None = Query(None, max_length=64,
                               description="Filter to cards carrying this factor code."),
    q: str | None = Query(None, max_length=200,
                          description="Free-text match on review title/body or product."),
    tier: Tier | None = Query(None, description="Filter to one admin priority tier."),
    sort: Literal["policy", "tier", "oldest"] = Query(
        "policy", description="Policy order (lane/SLA), priority tier, or oldest first."),
    view: Literal["waiting", "taken_down"] = Query(
        "waiting", description="Waiting for a decision (the work), or taken down by a "
                               "moderator (decided; Restore lives here)."),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ReviewQueueResponse:
    limit = min(limit, 100)
    query = referral_service.QueueQuery(
        band=band, lane=lane, sla=sla, factor=factor, q=q,
        tier=tier.value if tier is not None else None, sort=sort, view=view,
        limit=limit, offset=offset,
    )
    page = referral_service.get_prioritized_queue(db, query)

    return ReviewQueueResponse(
        items=page.items,
        total=page.total,
        next_cursor=page.next_cursor,
        counts=page.counts,
        earn_gate_phase=earn_gate.current_phase(db),
    )


@router.get("/reviews", response_model=AllReviewsPage,
            summary="All Reviews: every review that still exists, with both Wilson figures")
def list_all_reviews(
    db: Session = Depends(get_db),
    q: str | None = Query(None, max_length=200,
                          description="Title, text, product, author username or reference."),
    state: ReviewState | None = Query(None, description="Published, taken down, removed, "
                                                        "or deleted by its author."),
    earn: EarnEligibleStatus | None = Query(None, description="Earning state."),
    product_id: uuid.UUID | None = Query(None),
    created_from: date | None = Query(None, description="Written on or after (UTC day)."),
    created_to: date | None = Query(None, description="Written on or before (UTC day)."),
    sort: AllReviewsSort = Query("newest"),
    limit: int = Query(50, ge=1, le=all_reviews.MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> AllReviewsPage:
    return all_reviews.list_reviews(db, all_reviews.AllReviewsQuery(
        q=q, state=state, earn=earn, product_id=product_id, created_from=created_from,
        created_to=created_to, sort=sort, limit=limit, offset=offset))


@router.post("/reviews/{review_id}/referral-link", response_model=ReviewOut,
             summary="Approve earnings on the affiliate path by attaching the referral link")
def attach_link(review_id: uuid.UUID, payload: AttachLinkRequest,
                db: Session = Depends(get_db),
                mod: User = Depends(require_staff)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = referral_service.attach_link_and_publish(db, review, mod.id,
                                                      payload.url, payload.platform,
                                                      sub_id=payload.sub_id)
    return ReviewOut.model_validate(review)


@router.delete("/reviews/{review_id}/referral-link", response_model=ReviewOut,
               summary="Revoke the active referral link (stays published)")
def revoke_link(review_id: uuid.UUID, payload: ReasonRequest,
                db: Session = Depends(get_db),
                mod: User = Depends(require_staff)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = referral_service.revoke_link(db, review, mod.id, payload.reason)
    return ReviewOut.model_validate(review)


@router.post("/reviews/{review_id}/approve-earnings", response_model=ReviewOut,
             summary="Approve earnings without a link (<=2* -> Honesty Fund, else approved)")
def approve_earnings(review_id: uuid.UUID, db: Session = Depends(get_db),
                     mod: User = Depends(require_staff)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = referral_service.approve_earnings(db, review, mod.id)
    return ReviewOut.model_validate(review)


@router.post("/reviews/{review_id}/publish", response_model=ReviewOut, deprecated=True,
             summary="Deprecated alias of approve-earnings (reviews publish on submission)")
def publish(review_id: uuid.UUID, db: Session = Depends(get_db),
            mod: User = Depends(require_staff)) -> ReviewOut:
    return approve_earnings(review_id, db, mod)


@router.post("/reviews/{review_id}/restore", response_model=ReviewOut,
             summary="Put a taken-down review back on the public site")
def restore(review_id: uuid.UUID, db: Session = Depends(get_db),
            mod: User = Depends(require_staff)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = referral_service.restore(db, review, mod.id)
    return ReviewOut.model_validate(review)


@router.get("/awaiting-affiliate", response_model=AwaitingAffiliatePage,
            summary="Earnings-approved public reviews with no active affiliate link")
def awaiting_affiliate(db: Session = Depends(get_db),
                       limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0)) -> AwaitingAffiliatePage:
    return monetization_attention.awaiting_affiliate(db, limit=limit, offset=offset)


@router.get("/reviews/{review_id}/gate", response_model=GateStateOut,
            summary="Post-Seeding earn_eligible gate progress for one review")
def gate(review_id: uuid.UUID, db: Session = Depends(get_db)) -> GateStateOut:
    review_service.get_review_or_404(db, review_id)
    state = earn_gate.gate_state(db, review_id)
    return GateStateOut(phase=earn_gate.current_phase(db), **state.__dict__)


@router.post("/reviews/{review_id}/reject", response_model=ReviewOut,
             summary="Reject earnings (the review stays public)")
def reject(review_id: uuid.UUID, payload: ReasonRequest, db: Session = Depends(get_db),
           mod: User = Depends(require_staff)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = referral_service.reject(db, review, mod.id, payload.reason)
    return ReviewOut.model_validate(review)


@router.post("/reviews/{review_id}/unpublish", response_model=ReviewOut,
             summary="Take a published review off the public site")
def unpublish(review_id: uuid.UUID, payload: ReasonRequest,
              db: Session = Depends(get_db),
              mod: User = Depends(require_staff)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = referral_service.unpublish(db, review, mod.id, payload.reason)
    return ReviewOut.model_validate(review)


@router.get("/reviews/{review_id}/referral-links", response_model=list[ReferralLinkOut],
            summary="Referral link history for a review")
def link_history(review_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ReferralLinkOut]:
    review_service.get_review_or_404(db, review_id)
    return [ReferralLinkOut.model_validate(link)
            for link in referral_service.list_links(db, review_id)]

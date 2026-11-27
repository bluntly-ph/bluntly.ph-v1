"""Price observation moderation (FR-2, FR-9) — moderator only.

Every community price starts pending, and the public price panel is built from
approved ones alone (`price_service.panel_from`). This router is where they are
decided. The service refuses a moderator deciding a price they submitted.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.enums import Platform, PriceObservationSource
from app.models.user import User
from app.schemas.product import (
    PriceObservationCount,
    PriceObservationDecision,
    PriceObservationQueueItem,
)
from app.services import price_service

router = APIRouter(prefix="/admin/price-observations", tags=["admin"],
                   dependencies=[Depends(require_staff)])


def _query(product_id: uuid.UUID | None = None,
           platform: Platform | None = Query(None, description="One marketplace."),
           source: PriceObservationSource | None = Query(
               None, description="`review` (from a review) or `manual` (a price report)."),
           held: Literal["outlier", "no_baseline"] | None = Query(
               None, description="Why it waits: far outside the usual range, or no range yet."),
           q: str | None = Query(None, max_length=120, description="Words in the product's name."),
           mine: Literal["hide"] | None = Query(
               None, description="`hide` leaves out the prices you reported."),
           sort: Literal["oldest", "newest", "product"] = Query(
               "oldest", description="oldest (default), newest, or product (one product's "
                                     "prices together)."),
           viewer: User = Depends(get_current_user)) -> price_service.PendingQuery:
    return price_service.PendingQuery(product_id=product_id, platform=platform, source=source,
                                      held=held, q=q, mine=mine, viewer_id=viewer.id, sort=sort)


@router.get("", response_model=list[PriceObservationQueueItem],
            summary="Price observations waiting for a decision (oldest first by default)")
def pending_observations(db: Session = Depends(get_db),
                         query: price_service.PendingQuery = Depends(_query),
                         limit: int = Query(50, ge=1, le=200),
                         offset: int = Query(0, ge=0)) -> list[PriceObservationQueueItem]:
    """One page. Its total is GET /count with the same filters (MQA-043: the
    screen stopped at 100 rows and called that the backlog)."""
    return price_service.list_pending(db, query=query, limit=limit, offset=offset)


@router.get("/count", response_model=PriceObservationCount,
            summary="How many price observations match - the list's own total")
def pending_count(db: Session = Depends(get_db),
                  query: price_service.PendingQuery = Depends(_query)) -> PriceObservationCount:
    return PriceObservationCount(total=price_service.count_pending(db, query))


@router.post("/{observation_id}/decision", response_model=PriceObservationQueueItem,
             summary="Approve or reject a price observation")
def decide_observation(observation_id: uuid.UUID, decision: PriceObservationDecision,
                       db: Session = Depends(get_db),
                       moderator: User = Depends(get_current_user)) -> PriceObservationQueueItem:
    return price_service.decide_observation(db, observation_id, moderator, decision)

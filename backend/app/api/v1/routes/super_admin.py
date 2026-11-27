"""Super Admin: the 2.5-star special routing queue (owner decision A).

    GET  /admin/super/special-routing                 threads waiting, oldest first
    POST /admin/super/special-routing/{review_id}     {destination, confirm: "route"}
    GET  /admin/super/special-routing/history         the audited decisions

Every route requires a Super Admin; an Administrator gets 403 from all three,
whatever the console shows. User management lives at /admin/users.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.special_routing import (
    SpecialRoutingDecision,
    SpecialRoutingIn,
    SpecialRoutingItem,
    SpecialRoutingResult,
)
from app.services import special_routing
from app.services.referral_service import has_ownership_evidence

router = APIRouter(prefix="/admin/super", tags=["admin: super admin"])


@router.get("/special-routing", response_model=list[SpecialRoutingItem],
            summary="2.5-star It depends threads waiting on a Super Admin")
def routing_queue(db: Session = Depends(get_db),
                  _: User = Depends(require_super_admin)) -> list[SpecialRoutingItem]:
    return [
        SpecialRoutingItem(
            review_id=i.review.id, review_ref=i.review.review_id, title=i.latest.title,
            product_name=i.product_name, author=i.author, latest_entry_id=i.latest.id,
            verdict=i.latest.verdict, stars=i.latest.star_rating,
            photo_provided=has_ownership_evidence(i.review),
            status=i.review.earn_eligible_status, created_at=i.review.created_at,
            escalated_at=i.escalated_at, author_name=i.author_name, excerpt=i.excerpt,
            product_image_url=i.product_image_url, approval_note=i.approval_note)
        for i in special_routing.queue(db)
    ]


@router.post("/special-routing/{review_id}", response_model=SpecialRoutingResult,
             summary="Route a 2.5-star It depends thread to the Honesty Fund or the platform")
def route_review(review_id: uuid.UUID, payload: SpecialRoutingIn,
                 db: Session = Depends(get_db),
                 actor: User = Depends(require_super_admin)) -> SpecialRoutingResult:
    review, changed = special_routing.route(db, actor, review_id, payload.destination,
                                            payload.note)
    return SpecialRoutingResult(review_id=review.id, destination=review.special_route,
                                status=review.earn_eligible_status,
                                routed_at=review.special_routed_at, changed=changed)


@router.get("/special-routing/history", response_model=list[SpecialRoutingDecision],
            summary="The Super Admins' routing decisions, newest first")
def routing_history(limit: int = Query(default=50, ge=1, le=200),
                    db: Session = Depends(get_db),
                    _: User = Depends(require_super_admin)) -> list[SpecialRoutingDecision]:
    logs = special_routing.history(db, limit)
    ids = {log.moderator_id for log in logs if log.moderator_id}
    names = {u.id: u.display_name or (f"@{u.username}" if u.username else None)
             for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
    return [
        SpecialRoutingDecision(
            at=log.created_at, review_id=log.target_ref, actor_name=names.get(log.moderator_id),
            review_ref=(log.context or {}).get("review_ref"),
            destination=(log.context or {}).get("destination"),
            previous_status=(log.context or {}).get("previous_status"),
            actor_staff_ref=(log.context or {}).get("actor_staff_ref"))
        for log in logs
    ]

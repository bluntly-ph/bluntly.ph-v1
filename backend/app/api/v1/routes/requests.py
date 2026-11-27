"""Request board endpoints (M3 slice 9).

Since the dev/QA sync of 2026-09-29 every request names a product, every later
review of that product answers it, and the ASKER picks the Best Answer
(`POST /{id}/best-answer`), which takes it off the board without deleting or
archiving it: `GET /{id}` and `GET /{id}/answers` keep serving it, and
`GET /requests?q=` still finds it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user, get_optional_user, require_staff
from app.db.session import get_db
from app.models.enums import RequestStatus
from app.models.product import Product
from app.models.request_board import RequestUpvote
from app.models.user import User
from app.schemas.referral import ReasonRequest
from app.schemas.request_board import (
    FulfillRequest,
    RequestAnswerOut,
    RequestCreate,
    RequestOut,
)
from app.services import notification_service, request_service

router = APIRouter(tags=["request board"])


def _out(req, my_upvote: bool = False, answer_count: int = 0,
         product_name: str | None = None) -> RequestOut:
    out = RequestOut.model_validate(req)
    out.my_upvote = my_upvote
    out.answer_count = answer_count
    out.product_name = product_name
    return out


def _outs(db: Session, rows: list, user: User | None) -> list[RequestOut]:
    """Request rows with the viewer's up-votes, answer counts and product names,
    one query each for the whole page."""
    mine = _my_upvotes(db, user, [r.id for r in rows])
    counts = request_service.answer_counts(db, rows)
    ids = {r.product_id for r in rows if r.product_id}
    names = dict(db.execute(select(Product.id, Product.canonical_name).where(
        Product.id.in_(ids))).all()) if ids else {}
    return [_out(r, r.id in mine, counts.get(r.id, 0), names.get(r.product_id))
            for r in rows]


def _my_upvotes(db: Session, user: User | None,
                request_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Which of these requests the viewer has up-voted, in one query (BUG-026).

    Batched for the same reason as review votes: the board lists up to 100 rows
    and a per-row check would multiply the round trips by 100.
    """
    if user is None or not request_ids:
        return set()
    return set(db.scalars(
        select(RequestUpvote.request_id).where(
            RequestUpvote.user_id == user.id,
            RequestUpvote.request_id.in_(request_ids),
        )
    ).all())


@router.post("/requests", response_model=RequestOut, status_code=201,
             summary="Post a review request (names a product; AI-screened; free to post)")
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> RequestOut:
    return _outs(db, [request_service.create_request(db, user, payload)], user)[0]


@router.get("/requests", response_model=list[RequestOut], summary="List review requests")
def list_requests(db: Session = Depends(get_db),
                  status: RequestStatus | None = None,
                  sort: Literal["newest", "demand"] = "newest",
                  limit: int = Query(50, ge=1, le=100),
                  q: str | None = Query(None, max_length=100,
                                        description="Search the question and its product."),
                  user: User | None = Depends(get_optional_user)) -> list[RequestOut]:
    rows = request_service.list_requests(db, status, sort, limit, q=q)
    return _outs(db, rows, user)


@router.get("/requests/{request_id}", response_model=RequestOut, summary="Get a request")
def get_request(request_id: uuid.UUID, db: Session = Depends(get_db),
                user: User | None = Depends(get_optional_user)) -> RequestOut:
    req = request_service.get_or_404(db, request_id)
    return _outs(db, [req], user)[0]


@router.get("/requests/{request_id}/answers", response_model=list[RequestAnswerOut],
            summary="Every review that answers a request, the Best Answer first")
def list_answers(request_id: uuid.UUID,
                 db: Session = Depends(get_db)) -> list[RequestAnswerOut]:
    req = request_service.get_or_404(db, request_id)
    rows = request_service.answers(db, req)
    ids = {r.author_id for r in rows if r.author_id}
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} \
        if ids else {}
    return [RequestAnswerOut(
        review_id=r.id, title=r.title,
        excerpt=notification_service.excerpt(r.discussion or "", 240),
        star_rating=float(r.star_rating), verdict=r.verdict.value,
        author_username=getattr(people.get(r.author_id), "username", None),
        author_display_name=getattr(people.get(r.author_id), "display_name", None),
        created_at=r.created_at, is_best=r.id == req.fulfilled_by_review_id,
    ) for r in rows]


@router.post("/requests/{request_id}/best-answer", response_model=RequestOut,
             summary="The asker picks the Best Answer; the request leaves the board")
def pick_best_answer(request_id: uuid.UUID, payload: FulfillRequest,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> RequestOut:
    req = request_service.get_or_404(db, request_id)
    return _outs(db, [request_service.pick_best_answer(db, req, user, payload.review_id)],
                 user)[0]


@router.post("/requests/{request_id}/upvote", response_model=RequestOut,
             summary="Up-vote a request (says you want this reviewed too)")
def upvote(request_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)) -> RequestOut:
    enforce_rate_limit(request, "vote", max_requests=settings.vote_rate_limit_max)
    req = request_service.get_or_404(db, request_id)
    # my_upvote is read back from the vote just written (BUG-026).
    return _outs(db, [request_service.upvote(db, req, user)], user)[0]


@router.delete("/requests/{request_id}/upvote", response_model=RequestOut,
               summary="Remove your up-vote")
def remove_upvote(request_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> RequestOut:
    req = request_service.get_or_404(db, request_id)
    return _outs(db, [request_service.remove_upvote(db, req, user.id)], user)[0]


@router.post("/requests/{request_id}/fulfill", response_model=RequestOut,
             summary="Deprecated alias of best-answer: the asker picks the Best Answer")
def fulfill(request_id: uuid.UUID, payload: FulfillRequest,
            db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> RequestOut:
    req = request_service.get_or_404(db, request_id)
    return _outs(db, [request_service.fulfill(db, req, user, payload.review_id)], user)[0]


@router.delete("/requests/{request_id}", response_model=RequestOut,
               summary="Cancel your open request (refunds the escrow)")
def cancel(request_id: uuid.UUID, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)) -> RequestOut:
    req = request_service.get_or_404(db, request_id)
    return _outs(db, [request_service.cancel_request(db, req, user)], user)[0]


@router.post("/admin/requests/{request_id}/remove", response_model=RequestOut,
             summary="Remove a request (administrator; refunds the requester)")
def admin_remove(request_id: uuid.UUID, payload: ReasonRequest,
                 db: Session = Depends(get_db),
                 mod: User = Depends(require_staff)) -> RequestOut:
    req = request_service.get_or_404(db, request_id)
    return _outs(db, [request_service.remove_request(db, req, mod.id, payload.reason)],
                 None)[0]

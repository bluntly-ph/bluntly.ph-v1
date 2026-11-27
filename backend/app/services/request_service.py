"""Request board (M3 slice 9).

There is no money flow here any more. Posting a request used to escrow a token
bounty which was refunded on cancel/expire/remove and paid out with a
platform-minted top-up on fulfilment; tokens were retired in favour of the PHP
revenue share, and this board was the last thing still spending them
(migration 0022).

So a request is now a free demand signal: you ask, others up-vote to say they
want it too, and whoever writes the review earns through the ordinary revenue
share like any other review. Up-votes rank the board instead of raising a purse.

The historical ledger is untouched and still readable — see the migration.

Dev/QA sync 2026-09-29 (the final Bounty Board model, agreed at ≈41:30):
every request names a product and belongs to it for good; the board only
surfaces the open, most-wanted ones for the people who can answer. Every
review of that product written after the request is an ANSWER (many people
may answer); the request stays open until the ASKER picks the Best Answer,
and then leaves the board, neither deleted nor archived: its own page keeps
the question, every answer and the pick, and search still finds it. This
replaces QA-074's "the first review closes it", under which only one person
could ever answer and the asker chose nothing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    RequestStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.request_board import RequestUpvote, ReviewRequest
from app.models.review import Review
from app.models.user import User
from app.schemas.request_board import RequestCreate
from app.services import product_matching
from app.services.ai_critique import get_provider


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(detail: str, code: str) -> AppError:
    return AppError(detail, code=code, status_code=409, title="Conflicting state")


def get_or_404(db: Session, request_id: uuid.UUID) -> ReviewRequest:
    req = db.get(ReviewRequest, request_id)
    if req is None or req.status == RequestStatus.removed:
        raise NotFoundError("Request not found.", code="request_not_found")
    return req


def create_request(db: Session, requester: User, payload: RequestCreate) -> ReviewRequest:
    if payload.product_id is not None and db.get(Product, payload.product_id) is None:
        raise NotFoundError("Product not found.", code="product_not_found")

    # AI screening is blocking at creation; the verdict is stored either way.
    verdict = get_provider().validate_request(payload.title, payload.details,
                                              payload.source_url)
    if not verdict.valid:
        raise AppError("This request needs more detail before it can be posted.",
                       code="request_invalid", status_code=422,
                       title="Request rejected by validation",
                       extra={"reasons": verdict.reasons})

    product_id = payload.product_id
    if product_id is None and payload.source_url:
        # QA-074: a pasted listing we already know pins the request to its
        # canonical product, so a review of that product answers it. Exact
        # listing identity only — never a similar name.
        known = product_matching.product_for_listing(db, payload.source_url)
        product_id = known.id if known is not None else None
    if product_id is None:
        # The request belongs to its product's thread (2026-09-29): without
        # one it has nowhere to live and nothing can answer it.
        raise AppError("Choose the product you want reviewed.",
                       code="request_product_required", status_code=422,
                       title="Request needs a product")

    req = ReviewRequest(
        request_id=f"req_{uuid.uuid4().hex[:10]}",
        requester_id=requester.id, product_id=product_id,
        title=payload.title, details=payload.details, source_url=payload.source_url,
        status=RequestStatus.open,
        expires_at=_now() + timedelta(days=settings.request_ttl_days),
        upvote_count=0, ai_validation=verdict.model_dump(),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def cancel_request(db: Session, req: ReviewRequest, user: User) -> ReviewRequest:
    if req.requester_id != user.id:
        raise AppError("Only the requester may cancel this request.",
                       code="not_request_owner", status_code=403,
                       title="Insufficient permissions")
    if req.status != RequestStatus.open:
        raise _conflict("Only an open request can be cancelled.", "request_not_open")
    req.status = RequestStatus.cancelled
    db.commit()
    db.refresh(req)
    return req


def remove_request(db: Session, req: ReviewRequest, moderator_id: uuid.UUID,
                   reason: str) -> ReviewRequest:
    if req.status in (RequestStatus.removed, RequestStatus.fulfilled):
        raise _conflict("This request can no longer be removed.", "request_not_removable")
    req.status = RequestStatus.removed
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=ModerationTargetType.review, target_ref=req.id,
        moderator_id=moderator_id, action=ModerationAction.remove, notes=reason,
        context={"kind": "review_request", "upvotes": req.upvote_count},
    ))
    db.commit()
    db.refresh(req)
    return req


def upvote(db: Session, req: ReviewRequest, user: User) -> ReviewRequest:
    if req.status != RequestStatus.open:
        raise _conflict("Only an open request can be up-voted.", "request_not_open")
    if req.requester_id == user.id:
        raise _conflict("You cannot up-vote your own request.",
                        "cannot_upvote_own_request")
    db.add(RequestUpvote(request_id=req.id, user_id=user.id))
    try:
        db.flush()
    except IntegrityError as exc:  # uq_request_upvote_once
        db.rollback()
        raise _conflict("You have already up-voted this request.",
                        "already_upvoted") from exc
    _recount_upvotes(db, req)
    from app.services import notification_service
    notification_service.request_upvoted(db, req, user.id)
    db.commit()
    db.refresh(req)
    return req


def remove_upvote(db: Session, req: ReviewRequest, user_id: uuid.UUID) -> ReviewRequest:
    existing = db.scalar(select(RequestUpvote).where(
        RequestUpvote.request_id == req.id, RequestUpvote.user_id == user_id))
    if existing is None:
        raise NotFoundError("You have not up-voted this request.",
                            code="upvote_not_found")
    db.delete(existing)
    db.flush()
    _recount_upvotes(db, req)
    db.commit()
    db.refresh(req)
    return req


def _recount_upvotes(db: Session, req: ReviewRequest) -> None:
    req.upvote_count = db.scalar(
        select(func.count(RequestUpvote.id)).where(
            RequestUpvote.request_id == req.id)) or 0


def _is_root(review: Review):
    return (Review.thread_id.is_(None)) | (Review.thread_id == Review.id)


def _request_product_id(db: Session, req: ReviewRequest) -> uuid.UUID | None:
    """The product a request is about: its own, or (for a request posted
    before a product was required) the product whose listing it pasted."""
    if req.product_id is not None:
        return req.product_id
    if req.source_url:
        known = product_matching.product_for_listing(db, req.source_url)
        return known.id if known is not None else None
    return None


def answers(db: Session, req: ReviewRequest) -> list[Review]:
    """Every review that answers `req`: public reviews of its product written
    after it by anyone but the asker, oldest first; the Best Answer first once
    it is picked. Derived from product identity, so nothing is claimed by hand
    and nothing is stored twice."""
    product_id = _request_product_id(db, req)
    if product_id is None:
        return []
    rows = list(db.scalars(select(Review).where(
        Review.product_id == product_id, Review.published_at.isnot(None),
        Review.is_removed.is_(False), _is_root(Review),
        Review.author_id != req.requester_id,
        Review.created_at >= req.created_at,
    ).order_by(Review.created_at.asc(), Review.id)))
    best = req.fulfilled_by_review_id
    return sorted(rows, key=lambda r: r.id != best) if best else rows


def answer_counts(db: Session, reqs: list[ReviewRequest]) -> dict[uuid.UUID, int]:
    """How many answers each request has, one query for the page (the board)."""
    by_product: dict[uuid.UUID, list[ReviewRequest]] = {}
    for req in reqs:
        product_id = _request_product_id(db, req)
        if product_id is not None:
            by_product.setdefault(product_id, []).append(req)
    if not by_product:
        return {}
    rows = db.execute(select(Review.product_id, Review.author_id, Review.created_at).where(
        Review.product_id.in_(list(by_product)), Review.published_at.isnot(None),
        Review.is_removed.is_(False), _is_root(Review))).all()
    counts: dict[uuid.UUID, int] = {}
    for product_id, author_id, created_at in rows:
        for req in by_product[product_id]:
            if author_id != req.requester_id and created_at >= req.created_at:
                counts[req.id] = counts.get(req.id, 0) + 1
    return counts


def pick_best_answer(db: Session, req: ReviewRequest, user: User,
                     review_id: uuid.UUID) -> ReviewRequest:
    """The asker awards the Best Answer: the request is fulfilled and leaves
    the board. Nothing is paid here; the answer's author earns from that review
    through the ordinary revenue share, as they would without a request."""
    if req.requester_id != user.id:
        raise AppError("Only the person who asked picks the Best Answer.",
                       code="not_request_owner", status_code=403,
                       title="Insufficient permissions")
    if req.status not in (RequestStatus.open, RequestStatus.expired):
        raise _conflict("This request already has its answer.", "request_not_open")
    review = db.get(Review, review_id)
    if review is None or review.is_removed:
        raise NotFoundError("Review not found.", code="review_not_found")
    if review.published_at is None:
        raise _conflict("The review must be published before it can be the Best Answer.",
                        "review_not_published")
    if review.id not in {r.id for r in answers(db, req)}:
        raise _conflict("That review does not answer this request: it must be about the "
                        "same product and written after the request, by someone else.",
                        "not_an_answer")

    closed = db.execute(
        update(ReviewRequest)
        .where(ReviewRequest.id == req.id,
               ReviewRequest.status.in_([RequestStatus.open, RequestStatus.expired]))
        .values(status=RequestStatus.fulfilled, fulfilled_by_review_id=review.id,
                fulfilled_at=_now())
        .returning(ReviewRequest.id)
        .execution_options(synchronize_session="fetch")
    ).first()
    if closed is None:  # a concurrent pick won
        raise _conflict("This request already has its answer.", "request_not_open")
    # Audited as Q&A audits its Best Answer (`best_answer_pick`, the asker as
    # the actor). Never `approve`: the Overview counts those as staff approvals.
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=ModerationTargetType.review, target_ref=review.id,
        moderator_id=user.id, action=ModerationAction.best_answer_pick,
        notes="Best Answer to a review request, picked by the person who asked.",
        context={"kind": "request_best_answer", "request_id": str(req.id),
                 "picked_by": str(user.id)},
    ))
    from app.services import notification_service
    notification_service.request_best_answer(db, req, review)
    for (voter_id,) in db.execute(select(RequestUpvote.user_id).where(
            RequestUpvote.request_id == req.id)):
        notification_service.request_fulfilled(db, req, review, voter_id, requester=False)
    db.commit()
    db.refresh(req)
    return req


def fulfill(db: Session, req: ReviewRequest, user: User,
            review_id: uuid.UUID) -> ReviewRequest:
    """The retired reviewer self-claim, kept as a route: it now follows the
    one rule there is, the asker picks (2026-09-29)."""
    return pick_best_answer(db, req, user, review_id)


def announce_answer(db: Session, review: Review) -> int:
    """A newly public review answers the open requests for its product: tell
    each asker ("Someone answered your request"), and each up-voter once, at
    the first answer. The request stays open for more answers until its asker
    picks the Best Answer. Does not commit.

    A request matches by canonical product identity only: the same product
    id, or, for a request posted before a product was required, the exact
    same listing as one of this product's (`listing_key`). Never by a similar
    name, so "Jisulife Life 9" does not answer "Jisulife Life 9 Pro". Only a
    review written after the request answers it; the asker's own review does
    not answer their own request.
    """
    if (review.published_at is None or review.is_removed
            or (review.thread_id is not None and review.thread_id != review.id)):
        return 0
    keys = product_matching.product_listing_keys(db, review.product_id)
    same_product = ReviewRequest.product_id == review.product_id
    match = same_product if not keys else or_(same_product, and_(
        ReviewRequest.product_id.is_(None), ReviewRequest.source_url.isnot(None),
        product_matching.sql_listing_key(ReviewRequest.source_url).in_(keys)))
    open_requests = list(db.scalars(select(ReviewRequest).where(
        ReviewRequest.status == RequestStatus.open, match,
        ReviewRequest.requester_id != review.author_id,
        ReviewRequest.created_at <= review.created_at)))
    if not open_requests:
        return 0
    from app.services import notification_service
    for req in open_requests:
        notification_service.request_answered(db, req, review)
        earlier = [r for r in answers(db, req) if r.id != review.id]
        if not earlier:
            for (voter_id,) in db.execute(select(RequestUpvote.user_id).where(
                    RequestUpvote.request_id == req.id)):
                notification_service.request_fulfilled(db, req, review, voter_id,
                                                       requester=False)
    return len(open_requests)


def move_to_product(db: Session, from_product_id: uuid.UUID,
                    to_product_id: uuid.UUID) -> None:
    """A submission attached to a canonical product takes its requests along."""
    db.execute(update(ReviewRequest)
               .where(ReviewRequest.product_id == from_product_id)
               .values(product_id=to_product_id)
               .execution_options(synchronize_session=False))


def list_requests(db: Session, status: RequestStatus | None = None,
                  sort: str = "newest", limit: int = 50,
                  q: str | None = None) -> list[ReviewRequest]:
    stmt = select(ReviewRequest).where(ReviewRequest.status != RequestStatus.removed)
    if status is not None:
        stmt = stmt.where(ReviewRequest.status == status)
    if q and q.strip():
        # Search (2026-09-29): an answered request is not archived, so a reader
        # can still find it by what it asked, or by its product's name.
        needle = f"%{q.strip()[:100].replace('%', '').replace('_', '')}%"
        stmt = stmt.outerjoin(Product, Product.id == ReviewRequest.product_id).where(or_(
            ReviewRequest.title.ilike(needle), ReviewRequest.details.ilike(needle),
            Product.canonical_name.ilike(needle)))
    if sort == "demand":
        # Most-wanted first. This replaced a sort by bounty + top-up when the
        # board stopped charging for requests; up-votes were always the better
        # signal anyway, since they say how many people want the answer rather
        # than how many tokens one person happened to have.
        stmt = stmt.order_by(ReviewRequest.upvote_count.desc(),
                             ReviewRequest.created_at.desc())
    else:
        stmt = stmt.order_by(ReviewRequest.created_at.desc())
    return list(db.scalars(stmt.limit(min(limit, 100))))


def expire_open_requests(db: Session) -> int:
    """Nightly sweep: open requests past expires_at -> expired."""
    due = db.scalars(select(ReviewRequest).where(
        ReviewRequest.status == RequestStatus.open,
        ReviewRequest.expires_at <= _now())).all()
    for req in due:
        req.status = RequestStatus.expired
    db.commit()
    return len(due)

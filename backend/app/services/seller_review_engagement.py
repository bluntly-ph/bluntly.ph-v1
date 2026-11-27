"""Votes, replies and reports on seller reviews (QA-043, owner 2026-09-28).

The retest expected a seller review to carry the same controls as any other
review: up, down, reply, share and "⋯". Share and the store's response already
existed; this adds the rest with the narrowest rules that make them honest:

* **Votes are helpfulness only.** Equal weight, one per member, toggled like a
  comment vote. They move no store rating, no trust stage and no money. The
  review's author and the store's claimed owner cannot vote on it.
* **Replies are one flat thread.** Any signed-in member except the store's
  claimed owner, whose voice is the single "Response from the store". No links
  (as the store's response), 1,000 characters. The review's author is told.
* **Reports go through the ordinary queue** (target `seller_review`), where a
  moderator can remove or restore the review.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.models.enums import ModerationTargetType, VoteDirection
from app.models.seller import Seller, SellerReview, SellerReviewReply, SellerReviewVote
from app.models.user import User
from app.schemas.qa import QAAuthor
from app.services import notification_service, report_service

REPLIES_SHOWN = 20


def visible_review_or_404(db: Session, review_id: uuid.UUID) -> SellerReview:
    review = db.get(SellerReview, review_id)
    if review is None or review.is_removed:
        raise NotFoundError("Seller review not found.", code="seller_review_not_found")
    return review


def _owner_id(db: Session, review: SellerReview) -> uuid.UUID | None:
    seller = db.get(Seller, review.seller_id)
    return seller.claimed_by_id if seller is not None else None


def vote(db: Session, review: SellerReview, user: User,
         direction: VoteDirection | None) -> tuple[int, int, VoteDirection | None]:
    """Cast, change or (None) take back a vote. Returns (up, down, mine)."""
    if review.reviewer_id == user.id:
        raise AppError("You can't vote on your own review.", code="self_vote",
                       status_code=422, title="Invalid vote")
    if _owner_id(db, review) == user.id:
        raise ForbiddenError("A store can't vote on reviews of itself.",
                             code="store_owner_vote")
    existing = db.scalar(select(SellerReviewVote).where(
        SellerReviewVote.seller_review_id == review.id,
        SellerReviewVote.user_id == user.id).with_for_update())
    if direction is None:
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(SellerReviewVote(seller_review_id=review.id, user_id=user.id,
                                direction=direction))
    else:
        existing.direction = direction
    db.commit()
    up, down = counts(db, [review.id]).get(review.id, (0, 0))
    return up, down, direction


def counts(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not review_ids:
        return {}
    rows = db.execute(
        select(SellerReviewVote.seller_review_id, SellerReviewVote.direction,
               func.count(SellerReviewVote.id))
        .where(SellerReviewVote.seller_review_id.in_(review_ids))
        .group_by(SellerReviewVote.seller_review_id, SellerReviewVote.direction)
    ).all()
    out: dict[uuid.UUID, list[int]] = {}
    for rid, direction, n in rows:
        slot = out.setdefault(rid, [0, 0])
        slot[0 if direction == VoteDirection.up else 1] = int(n)
    return {rid: (v[0], v[1]) for rid, v in out.items()}


def my_votes(db: Session, user_id: uuid.UUID | None,
             review_ids: list[uuid.UUID]) -> dict[uuid.UUID, VoteDirection]:
    if user_id is None or not review_ids:
        return {}
    return dict(db.execute(
        select(SellerReviewVote.seller_review_id, SellerReviewVote.direction)
        .where(SellerReviewVote.user_id == user_id,
               SellerReviewVote.seller_review_id.in_(review_ids))
    ).all())


def replies_for(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    """Visible replies per review, oldest first, with their authors."""
    if not review_ids:
        return {}
    rows = db.execute(
        select(SellerReviewReply, User)
        .outerjoin(User, User.id == SellerReviewReply.author_id)
        .where(SellerReviewReply.seller_review_id.in_(review_ids),
               SellerReviewReply.is_removed.is_(False))
        .order_by(SellerReviewReply.created_at.asc())
    ).all()
    out: dict[uuid.UUID, list[dict]] = {}
    for reply, author in rows:
        bucket = out.setdefault(reply.seller_review_id, [])
        if len(bucket) < REPLIES_SHOWN:
            bucket.append({
                "id": reply.id, "body": reply.body, "created_at": reply.created_at,
                "author": QAAuthor.model_validate(author) if author is not None else None,
            })
    return out


def reply_counts(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not review_ids:
        return {}
    return dict(db.execute(
        select(SellerReviewReply.seller_review_id, func.count(SellerReviewReply.id))
        .where(SellerReviewReply.seller_review_id.in_(review_ids),
               SellerReviewReply.is_removed.is_(False))
        .group_by(SellerReviewReply.seller_review_id)
    ).all())


def add_reply(db: Session, review: SellerReview, user: User, body: str) -> SellerReviewReply:
    if _owner_id(db, review) == user.id:
        raise AppError("Your store answers with its one public response.",
                       code="store_owner_reply", status_code=409, title="Conflicting state")
    reply = SellerReviewReply(seller_review_id=review.id, author_id=user.id, body=body)
    db.add(reply)
    if review.reviewer_id is not None and review.reviewer_id != user.id:
        notification_service.notify(
            db, review.reviewer_id, "seller_review_reply",
            f"@{user.username or 'Someone'} replied to your store review", body=body,
            link=f"/sellers/{review.seller_id}#seller-review-{review.id}")
    db.commit()
    db.refresh(reply)
    return reply


def delete_reply(db: Session, reply_id: uuid.UUID, user: User) -> None:
    reply = db.get(SellerReviewReply, reply_id)
    if reply is None or reply.is_removed:
        raise NotFoundError("Reply not found.", code="seller_review_reply_not_found")
    if reply.author_id != user.id:
        raise ForbiddenError("Only its author can delete a reply.", code="not_reply_author")
    reply.is_removed = True
    db.commit()


def report(db: Session, review: SellerReview, user: User, *, reason, notes, evidence_url):
    """The ordinary report pipeline: rate limit (in the route), self-report
    refusal, one open report per reporter, the moderators' queue."""
    return report_service.file_report(
        db, reporter_id=user.id, author_id=review.reviewer_id,
        target_type=ModerationTargetType.seller_review, target_ref=review.id,
        reason=reason, notes=notes, evidence_url=evidence_url)

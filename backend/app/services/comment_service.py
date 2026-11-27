"""Comment threads on published reviews (BUG-014).

Visibility follows the review: a comment is readable exactly when the review it
hangs off is readable, so this module never re-implements the publication gate —
callers hand it a review they have already resolved through
`review_service.get_review_or_404` + the route's `_visible_or_404`.

Removal is soft. A removed comment keeps its row and its position in the thread
but surrenders its body, so replies underneath it still make sense.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.security import is_staff
from app.models.comment import CommentFollow, CommentSave, ReviewComment, ReviewCommentVote
from app.models.enums import VoteDirection
from app.models.product import Product
from app.models.review import Review
from app.models.user import User

# What a removed comment says instead of its body. The row stays so the thread
# shape survives; the text does not.
REMOVED_PLACEHOLDER = "[removed]"

#: Business Rules §8: commenting needs Stage 1 (posted at least one review).
MIN_COMMENT_STAGE = 1
#: ...and Stage 2 on a thread whose review has an open report, against pile-ons.
MIN_STAGE_WHILE_REPORTED = 2
#: A newly qualified account: shown a "new account" badge and a generous cap.
NEW_ACCOUNT_DAYS = 30
#: Generous and rarely triggered on purpose (§8): friction for abuse, not for people.
NEW_ACCOUNT_COMMENTS_PER_HOUR = 30
#: A comment this far below zero (helpful - unhelpful) is collapsed for everyone.
COLLAPSE_AT_NET_VOTES = -5
#: QA-067: at most this many people are notified from one comment's @mentions,
#: so a comment cannot be used to page the whole membership.
MAX_MENTIONS = 5
#: `@username` as plain text: the username alphabet (services/username.py),
#: not preceded by a word character, so "me@example.com" mentions nobody.
_MENTION = re.compile(r"(?<![A-Za-z0-9_@])@([A-Za-z0-9_]{3,32})(?![A-Za-z0-9_])")


def mentioned_usernames(body: str) -> list[str]:
    """The distinct usernames a comment @mentions, in order, capped.

    A regex over the stored plain text — nothing is rendered or executed, and
    the body itself is never rewritten into markup.
    """
    seen: list[str] = []
    for match in _MENTION.finditer(body or ""):
        name = match.group(1).lower()
        if name not in seen:
            seen.append(name)
        if len(seen) == MAX_MENTIONS:
            break
    return seen


def is_new_account(user: User, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    created = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=UTC)
    return (now - created) < timedelta(days=NEW_ACCOUNT_DAYS)


def is_collapsed(helpful: int, unhelpful: int) -> bool:
    """§8: heavily downvoted comments auto-collapse, regardless of who posted them."""
    return (helpful or 0) - (unhelpful or 0) <= COLLAPSE_AT_NET_VOTES


def review_has_open_report(db: Session, review_id: uuid.UUID) -> bool:
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    return db.scalar(select(ModerationLog.id).where(
        ModerationLog.action == ModerationAction.report,
        ModerationLog.target_ref == review_id,
        ModerationLog.resolution.is_(None)).limit(1)) is not None


def _may_comment(db: Session, review: Review, author: User) -> None:
    """The §8 participation rules, enforced here so no client can skip them."""
    # A claimed seller can never post a review, so never reaches Stage 1 — yet
    # §8 lets sellers reply to reviews and join threads. They are exempt from
    # the Stage-1 bar (not from the reported-thread bar below).
    if not author.is_claimed_seller and author.trust_stage < MIN_COMMENT_STAGE:
        raise ForbiddenError("Commenting unlocks once you've posted a review.",
                             code="comment_stage_locked")
    if author.trust_stage < MIN_STAGE_WHILE_REPORTED and review_has_open_report(db, review.id):
        raise ForbiddenError(
            "This thread is under review by our administrators; replies are limited to "
            "established members until it's resolved.",
            code="comment_thread_reported")
    if is_new_account(author):
        since = datetime.now(UTC) - timedelta(hours=1)
        recent = db.scalar(select(func.count(ReviewComment.id)).where(
            ReviewComment.author_id == author.id, ReviewComment.created_at >= since)) or 0
        if recent >= NEW_ACCOUNT_COMMENTS_PER_HOUR:
            raise AppError("New accounts can post up to 30 comments an hour. Try again soon.",
                           code="comment_rate_capped", status_code=429,
                           title="Too many requests")


def _commentable_or_404(review: Review) -> None:
    """Only a live, published review accepts comments."""
    if review.published_at is None or review.is_removed:
        raise NotFoundError("Review not found.", code="review_not_found")


def get_comment_or_404(db: Session, comment_id: uuid.UUID) -> ReviewComment:
    comment = db.get(ReviewComment, comment_id)
    if comment is None:
        raise NotFoundError("Comment not found.", code="comment_not_found")
    return comment


def create_comment(db: Session, review: Review, author: User, body: str,
                   parent_id: uuid.UUID | None = None) -> ReviewComment:
    _commentable_or_404(review)
    _may_comment(db, review, author)

    if parent_id is not None:
        parent = get_comment_or_404(db, parent_id)
        if parent.review_id != review.id:
            # Guessing a parent id from another review would otherwise graft a
            # thread onto the wrong page.
            raise NotFoundError("Comment not found.", code="comment_not_found")
        if parent.parent_id is not None:
            raise AppError(
                "Replies are one level deep — reply to the top comment instead.",
                code="comment_nesting_too_deep", status_code=409,
                title="Conflicting state")
        if parent.is_removed:
            raise AppError("That comment was removed.",
                           code="comment_removed", status_code=409,
                           title="Conflicting state")

    comment = ReviewComment(
        review_id=review.id, author_id=author.id, parent_id=parent_id, body=body,
    )
    db.add(comment)
    db.flush()
    _notify_new_comment(db, review, comment, author,
                        parent if parent_id is not None else None)
    db.commit()
    # Repeated long comments are moderation evidence; best effort, after posting.
    from app.services.duplicate_text import check_new_comment
    check_new_comment(db, comment.id)
    db.refresh(comment)
    return comment


def _notify_new_comment(db: Session, review: Review, comment: ReviewComment,
                        author: User, parent: ReviewComment | None) -> None:
    """QA-067/069: in the comment's own transaction, so a comment that fails
    to save announces nothing."""
    from app.services import notification_service
    names = mentioned_usernames(comment.body)
    mentioned = list(db.scalars(select(User).where(
        func.lower(User.username).in_(names)))) if names else []
    followers: list[uuid.UUID] = []
    if parent is not None:
        followers = list(db.scalars(select(CommentFollow.user_id).where(
            CommentFollow.comment_id == parent.id)))
    notification_service.new_comment(db, review, comment, author, parent=parent,
                                     followers=followers, mentioned=mentioned)


def _markable_or_error(db: Session, comment: ReviewComment, user: User) -> None:
    if comment.is_removed:
        raise AppError("That comment was removed.", code="comment_removed",
                       status_code=409, title="Conflicting state")
    if comment.author_id == user.id:
        raise AppError("That's your own comment — replies to it already reach you.",
                       code="own_comment", status_code=409, title="Conflicting state")


def set_mark(db: Session, comment: ReviewComment, user: User, *, kind: str,
             on: bool) -> bool:
    """Follow / save (QA-069) on, or off. Idempotent both ways.

    Only ever the caller's own row: nothing here reads or reports anyone
    else's follows or saves.
    """
    model = {"follow": CommentFollow, "save": CommentSave}[kind]
    existing = db.scalar(select(model).where(model.comment_id == comment.id,
                                             model.user_id == user.id))
    if on:
        _markable_or_error(db, comment, user)
        if existing is None:
            db.add(model(comment_id=comment.id, user_id=user.id))
            try:
                db.flush()
            except IntegrityError:  # a double tap: the other request saved it
                db.rollback()
                return True
    elif existing is not None:
        db.delete(existing)
    db.commit()
    return on


def marks_for(db: Session, viewer_id: uuid.UUID | None,
              comment_ids: list[uuid.UUID]) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Which of these comments the viewer follows, and which they saved."""
    if viewer_id is None or not comment_ids:
        return set(), set()
    followed = set(db.scalars(select(CommentFollow.comment_id).where(
        CommentFollow.user_id == viewer_id, CommentFollow.comment_id.in_(comment_ids))))
    saved = set(db.scalars(select(CommentSave.comment_id).where(
        CommentSave.user_id == viewer_id, CommentSave.comment_id.in_(comment_ids))))
    return followed, saved


def list_saved(db: Session, user_id: uuid.UUID, *, limit: int = 24, offset: int = 0
               ) -> list[tuple[ReviewComment, Review, str | None, User | None]]:
    """The caller's saved comments, most recently saved first.

    Same visibility as the public thread: a comment since removed, or on a
    review since taken down, drops out rather than showing text nobody else
    can read any more.
    """
    rows = db.execute(
        select(ReviewComment, Review, Product.canonical_name, User)
        .join(CommentSave, CommentSave.comment_id == ReviewComment.id)
        .join(Review, Review.id == ReviewComment.review_id)
        .outerjoin(Product, Product.id == Review.product_id)
        .outerjoin(User, User.id == ReviewComment.author_id)
        .where(CommentSave.user_id == user_id,
               ReviewComment.is_removed.is_(False),
               Review.is_removed.is_(False),
               Review.published_at.isnot(None))
        .order_by(CommentSave.created_at.desc())
        .limit(limit).offset(offset)
    ).all()
    return [(c, r, name, u) for c, r, name, u in rows]


def remove_comment(db: Session, comment: ReviewComment, user: User) -> ReviewComment:
    """Soft-delete. The author may retract; a moderator may remove anyone's."""
    if comment.author_id != user.id and not is_staff(user):
        raise ForbiddenError(
            "Only the author or an administrator may remove this comment.",
            code="not_comment_owner")
    comment.is_removed = True
    db.commit()
    db.refresh(comment)
    return comment


def list_comments(db: Session, review: Review,
                  viewer_id: uuid.UUID | None = None
                  ) -> tuple[list[ReviewComment], dict[uuid.UUID, User],
                             dict[uuid.UUID, VoteDirection]]:
    """Every comment on a review, oldest first, with authors and the viewer's votes.

    Authors and votes are fetched in one query each rather than per comment —
    a 50-comment thread would otherwise be 100 round trips.
    """
    comments = list(db.scalars(
        select(ReviewComment)
        .where(ReviewComment.review_id == review.id)
        .order_by(ReviewComment.created_at.asc())
    ))
    if not comments:
        return [], {}, {}

    author_ids = {c.author_id for c in comments if c.author_id is not None}
    authors: dict[uuid.UUID, User] = {}
    if author_ids:
        authors = {
            u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids)))
        }

    my_votes: dict[uuid.UUID, VoteDirection] = {}
    if viewer_id is not None:
        comment_ids = [c.id for c in comments]
        my_votes = {
            comment_id: vote
            for comment_id, vote in db.execute(
                select(ReviewCommentVote.comment_id, ReviewCommentVote.vote).where(
                    ReviewCommentVote.comment_id.in_(comment_ids),
                    ReviewCommentVote.voter_id == viewer_id,
                )
            )
        }
    return comments, authors, my_votes


def recompute_comment_vote_aggregates(db: Session, comment: ReviewComment) -> None:
    """Refresh the counters from the vote rows, in the vote's own transaction."""
    votes = list(db.scalars(
        select(ReviewCommentVote.vote).where(
            ReviewCommentVote.comment_id == comment.id)
    ))
    comment.helpful_votes = sum(1 for v in votes if v == VoteDirection.up)
    comment.unhelpful_votes = len(votes) - comment.helpful_votes


def cast_comment_vote(db: Session, comment: ReviewComment, voter: User,
                      direction: VoteDirection) -> ReviewComment:
    if comment.is_removed:
        raise AppError("That comment was removed.", code="comment_removed",
                       status_code=409, title="Conflicting state")
    if voter.is_claimed_seller:
        # §8, §9: sellers comment and reply, but never vote.
        raise ForbiddenError("A claimed seller account can't vote.", code="seller_cannot_vote")
    if comment.author_id == voter.id:
        raise AppError("You cannot vote on your own comment.",
                       code="cannot_vote_own_comment", status_code=409,
                       title="Conflicting state")

    existing = db.scalar(select(ReviewCommentVote).where(
        ReviewCommentVote.comment_id == comment.id,
        ReviewCommentVote.voter_id == voter.id))
    previous = existing.vote if existing is not None else None
    if existing is None:
        db.add(ReviewCommentVote(
            comment_id=comment.id, voter_id=voter.id, vote=direction))
    else:
        existing.vote = direction
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent first-votes hit the unique index
        db.rollback()
        raise AppError("Your vote was submitted twice at once; retry.",
                       code="vote_conflict", status_code=409,
                       title="Conflicting state") from exc

    recompute_comment_vote_aggregates(db, comment)
    if direction == VoteDirection.up and previous != VoteDirection.up:
        # QA-067: a new upvote (or a change to one) — never a repeat of the
        # same vote, and never a vote taken back.
        from app.services import notification_service
        notification_service.comment_upvoted(db, comment, voter.id)
    db.commit()
    db.refresh(comment)
    return comment


def remove_comment_vote(db: Session, comment: ReviewComment,
                        voter_id: uuid.UUID) -> ReviewComment:
    existing = db.scalar(select(ReviewCommentVote).where(
        ReviewCommentVote.comment_id == comment.id,
        ReviewCommentVote.voter_id == voter_id))
    if existing is None:
        raise NotFoundError("You have no vote on this comment.",
                            code="vote_not_found")
    db.delete(existing)
    db.flush()
    recompute_comment_vote_aggregates(db, comment)
    db.commit()
    db.refresh(comment)
    return comment


def list_authored(db: Session, author_id: uuid.UUID, *, limit: int = 24,
                  offset: int = 0) -> list[tuple[ReviewComment, Review, str | None, int]]:
    """A member's own comments, newest first, each with its parent review.

    The profile's Comments tab reads this. Three filters make it a *public*
    list rather than a personal one: the comment is not removed, the review is
    not removed, and the review is published. A member's profile is readable by
    anyone, so a comment on their own unpublished draft must not leak through it.

    The reply count is counted in the same statement rather than per row — the
    N+1 the review feed already learned to avoid (BUG-006).
    """
    comment_count = (
        select(func.count(ReviewComment.id))
        .where(
            ReviewComment.review_id == Review.id,
            ReviewComment.is_removed.is_(False),
        )
        .correlate(Review)
        .scalar_subquery()
    )
    rows = db.execute(
        select(ReviewComment, Review, Product.canonical_name, comment_count)
        .join(Review, Review.id == ReviewComment.review_id)
        .outerjoin(Product, Product.id == Review.product_id)
        .where(
            ReviewComment.author_id == author_id,
            ReviewComment.is_removed.is_(False),
            Review.is_removed.is_(False),
            Review.published_at.is_not(None),
        )
        .order_by(ReviewComment.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows]

"""Comment routes — reading and posting discussion under a published review.

Visibility is inherited, not re-derived: every path resolves the parent review
through the same publication gate the review routes use, so a comment on an
unpublished draft is unreachable by exactly the people who cannot see the draft.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user, get_optional_user, is_staff
from app.db.session import get_db
from app.models.comment import ReviewComment
from app.models.enums import ModerationTargetType, VoteDirection
from app.models.review import Review
from app.models.user import User
from app.schemas.comment import (
    AuthoredCommentOut,
    CommentAuthor,
    CommentCreate,
    CommentMarkOut,
    CommentOut,
    CommentReview,
    CommentVoteIn,
    SavedCommentOut,
)
from app.schemas.report import ReportCreate, ReportOut
from app.services import comment_service, report_service, review_service

router = APIRouter(tags=["comments"])


def _visible_review_or_404(db: Session, review_id: uuid.UUID,
                           user: User | None) -> Review:
    """The parent review, or 404 — mirrors reviews.py `_visible_or_404`."""
    review = review_service.get_review_or_404(db, review_id)
    is_moderator = is_staff(user)
    can_view_unpublished = user is not None and (
        user.id == review.author_id or is_moderator)
    if review.published_at is None and not can_view_unpublished:
        raise NotFoundError("Review not found.", code="review_not_found")
    return review


def _to_out(comment: ReviewComment, authors: dict[uuid.UUID, User],
            my_votes: dict[uuid.UUID, VoteDirection],
            marks: tuple[set, set] = (set(), set())) -> CommentOut:
    author = authors.get(comment.author_id) if comment.author_id else None
    return CommentOut(
        id=comment.id,
        review_id=comment.review_id,
        parent_id=comment.parent_id,
        # A removed comment keeps its slot in the thread but not its text.
        body=comment_service.REMOVED_PLACEHOLDER if comment.is_removed else comment.body,
        helpful_votes=comment.helpful_votes,
        unhelpful_votes=comment.unhelpful_votes,
        is_removed=comment.is_removed,
        created_at=comment.created_at,
        author=None if comment.is_removed or author is None
        else CommentAuthor.model_validate(author),
        my_vote=my_votes.get(comment.id),
        followed_by_me=comment.id in marks[0],
        saved_by_me=comment.id in marks[1],
        replies=[],
    )


def _single_out(db: Session, comment: ReviewComment,
                my_vote: VoteDirection | None = None) -> CommentOut:
    """One comment, with its author resolved — the shape every write returns."""
    author = db.get(User, comment.author_id) if comment.author_id else None
    authors = {author.id: author} if author is not None else {}
    return _to_out(comment, authors, {comment.id: my_vote} if my_vote else {})


@router.get("/reviews/{review_id}/comments", response_model=list[CommentOut],
            summary="List the comment thread on a review")
def list_comments(review_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User | None = Depends(get_optional_user)) -> list[CommentOut]:
    review = _visible_review_or_404(db, review_id, user)
    comments, authors, my_votes = comment_service.list_comments(
        db, review, viewer_id=user.id if user else None)
    marks = comment_service.marks_for(db, user.id if user else None,
                                      [c.id for c in comments])

    # Flat rows in, two-level tree out. One pass builds the nodes, a second nests
    # them, so a reply that happens to sort before its parent still lands right.
    nodes = {c.id: _to_out(c, authors, my_votes, marks) for c in comments}
    roots: list[CommentOut] = []
    for comment in comments:
        node = nodes[comment.id]
        parent = nodes.get(comment.parent_id) if comment.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent.replies.append(node)
    # QA-039: a deleted comment leaves the thread. A deleted top comment stays
    # only while it has live replies, as a tombstone that keeps their context;
    # a deleted reply never shows. The client applies the same rule on delete,
    # so a refresh cannot bring a deleted comment back.
    visible: list[CommentOut] = []
    for root in roots:
        root.replies = [r for r in root.replies if not r.is_removed]
        if root.is_removed and not root.replies:
            continue
        visible.append(root)
    return visible


@router.post("/reviews/{review_id}/comments", response_model=CommentOut,
             status_code=201, summary="Post a comment or a reply")
def create_comment(review_id: uuid.UUID, payload: CommentCreate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> CommentOut:
    enforce_rate_limit(request, "comment",
                       max_requests=settings.comment_rate_limit_max)
    review = _visible_review_or_404(db, review_id, user)
    comment = comment_service.create_comment(
        db, review, user, payload.body, payload.parent_id)
    return _single_out(db, comment)


@router.delete("/comments/{comment_id}", response_model=CommentOut,
               summary="Remove your comment (or any comment, as an administrator)")
def remove_comment(comment_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> CommentOut:
    comment = comment_service.get_comment_or_404(db, comment_id)
    _visible_review_or_404(db, comment.review_id, user)
    comment = comment_service.remove_comment(db, comment, user)
    return _single_out(db, comment)


@router.post("/comments/{comment_id}/vote", response_model=CommentOut,
             summary="Cast or change a vote on a comment")
def vote_comment(comment_id: uuid.UUID, payload: CommentVoteIn, request: Request,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> CommentOut:
    enforce_rate_limit(request, "vote", max_requests=settings.vote_rate_limit_max)
    comment = comment_service.get_comment_or_404(db, comment_id)
    _visible_review_or_404(db, comment.review_id, user)
    comment = comment_service.cast_comment_vote(db, comment, user, payload.vote)
    return _single_out(db, comment, payload.vote)


@router.delete("/comments/{comment_id}/vote", response_model=CommentOut,
               summary="Remove your vote from a comment")
def unvote_comment(comment_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> CommentOut:
    comment = comment_service.get_comment_or_404(db, comment_id)
    _visible_review_or_404(db, comment.review_id, user)
    comment = comment_service.remove_comment_vote(db, comment, user.id)
    return _single_out(db, comment)


@router.post("/comments/{comment_id}/report", response_model=ReportOut, status_code=201,
             summary="Report another member's comment to the administrators")
def report_comment(comment_id: uuid.UUID, payload: ReportCreate, request: Request,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> ReportOut:
    """QA-069: the same pipeline a review report goes through — same rate
    limit, same self-report refusal, same repeat handling, same moderator
    queue (where the comment can be removed or restored)."""
    enforce_rate_limit(request, "report", max_requests=settings.report_rate_limit_max)
    comment = comment_service.get_comment_or_404(db, comment_id)
    _visible_review_or_404(db, comment.review_id, user)
    if comment.is_removed:
        raise NotFoundError("Comment not found.", code="comment_not_found")
    log, _created = report_service.file_report(
        db, reporter_id=user.id, author_id=comment.author_id,
        target_type=ModerationTargetType.comment, target_ref=comment.id,
        reason=payload.reason, notes=payload.notes, evidence_url=payload.evidence_url)
    return ReportOut.model_validate(log)


def _mark(db: Session, comment_id: uuid.UUID, user: User, kind: str,
          on: bool) -> CommentMarkOut:
    comment = comment_service.get_comment_or_404(db, comment_id)
    _visible_review_or_404(db, comment.review_id, user)
    state = comment_service.set_mark(db, comment, user, kind=kind, on=on)
    return CommentMarkOut(comment_id=comment.id,
                          **{"followed" if kind == "follow" else "saved": state})


@router.put("/comments/{comment_id}/follow", response_model=CommentMarkOut,
            summary="Follow a comment: hear about replies to it")
def follow_comment(comment_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> CommentMarkOut:
    return _mark(db, comment_id, user, "follow", True)


@router.delete("/comments/{comment_id}/follow", response_model=CommentMarkOut,
               summary="Stop following a comment")
def unfollow_comment(comment_id: uuid.UUID, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> CommentMarkOut:
    return _mark(db, comment_id, user, "follow", False)


@router.put("/comments/{comment_id}/save", response_model=CommentMarkOut,
            summary="Save a comment privately")
def save_comment(comment_id: uuid.UUID, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> CommentMarkOut:
    return _mark(db, comment_id, user, "save", True)


@router.delete("/comments/{comment_id}/save", response_model=CommentMarkOut,
               summary="Remove a comment from your saved comments")
def unsave_comment(comment_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> CommentMarkOut:
    return _mark(db, comment_id, user, "save", False)


@router.get("/users/me/saved-comments", response_model=list[SavedCommentOut],
            summary="The comments you saved (visible to you only)")
def saved_comments(limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0),
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> list[SavedCommentOut]:
    """QA-069: the caller's own list. There is no route that reads anyone
    else's saves; the member is taken from the session, not the path."""
    return [
        SavedCommentOut(
            id=comment.id, body=comment.body, created_at=comment.created_at,
            author=CommentAuthor.model_validate(author) if author is not None else None,
            review=CommentReview(id=review.id, title=review.title, product_name=name,
                                 helpful_votes=review.helpful_votes),
        )
        for comment, review, name, author in comment_service.list_saved(
            db, user.id, limit=limit, offset=offset)
    ]


@router.get("/users/{user_id}/comments", response_model=list[AuthoredCommentOut],
            summary="List the comments a member has written")
def list_authored_comments(
    user_id: uuid.UUID,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[AuthoredCommentOut]:
    """The Comments tab of a profile (Figma 5446:6398).

    Public, and deliberately so: a profile is a public page, and this list is
    the same conversation anyone can already read under each review. The service
    applies the visibility filter — removed comments and comments on unpublished
    or removed reviews never appear, whoever is asking.
    """
    rows = comment_service.list_authored(db, user_id, limit=limit, offset=offset)
    return [
        AuthoredCommentOut(
            id=comment.id,
            body=comment.body,
            helpful_votes=comment.helpful_votes,
            created_at=comment.created_at,
            review=CommentReview(
                id=review.id,
                title=review.title,
                product_name=product_name,
                helpful_votes=review.helpful_votes,
                comment_count=comment_count,
            ),
        )
        for comment, review, product_name, comment_count in rows
    ]

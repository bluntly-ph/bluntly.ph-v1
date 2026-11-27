"""Review-comment schemas (BUG-014)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.core.link_policy import reject_links
from app.models.enums import VoteDirection


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    # Present only on a reply. The service rejects a parent that is itself a
    # reply — threading is one level deep by design (see models/comment.py).
    parent_id: uuid.UUID | None = None

    @field_validator("body")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` counts characters, so "   " passes it and posts blank.

        Strip first, then re-check, so the stored body is also trimmed.
        """
        value = value.strip()
        if not value:
            raise ValueError("A comment cannot be empty.")
        # Business Rules §1: no links in comments or replies, sellers' included.
        return reject_links(value, field="comments")


class CommentAuthor(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    trust_stage: int | None = None
    trust_level_name: str | None = None
    #: The public 0-100 score the Honesty Score badge draws beside the name
    #: (Figma comment block, 4305:2114); public on every profile (§17).
    reputation_score: Decimal | None = None
    #: §8/§9: a claimed seller joining the conversation is labelled as one.
    is_claimed_seller: bool = False
    created_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_new_account(self) -> bool:
        """§8: the visible "new account" badge (under 30 days old)."""
        if self.created_at is None:
            return False
        from app.services.comment_service import NEW_ACCOUNT_DAYS
        created = (self.created_at if self.created_at.tzinfo
                   else self.created_at.replace(tzinfo=UTC))
        return datetime.now(UTC) - created < timedelta(days=NEW_ACCOUNT_DAYS)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    review_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    body: str
    helpful_votes: int
    unhelpful_votes: int
    is_removed: bool
    created_at: datetime
    author: CommentAuthor | None = None
    # The viewer's own vote, so the UI can show the pressed state without a
    # second round trip. None for signed-out readers and for un-voted comments.
    my_vote: VoteDirection | None = None
    #: QA-069: the viewer's OWN follow / save of this comment. Never anyone
    #: else's: there is no field, route or count that reveals who else did.
    followed_by_me: bool = False
    saved_by_me: bool = False
    replies: list[CommentOut] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_collapsed(self) -> bool:
        """§8: heavily downvoted comments auto-collapse for everyone."""
        from app.services.comment_service import is_collapsed
        return is_collapsed(self.helpful_votes, self.unhelpful_votes)


# `replies` refers to the class being defined, and `from __future__ import
# annotations` keeps every annotation a string, so the forward reference is only
# resolvable once the class exists.
CommentOut.model_rebuild()


class CommentVoteIn(BaseModel):
    vote: VoteDirection


class CommentReview(BaseModel):
    """The parent review, reduced to what a profile row draws.

    Enough to render the headline ("<product> - <title>") and its engagement
    counts, and to link to the review. Not a `ReviewOut`: the Comments tab shows
    none of the body, the verdict or the rating, and shipping the whole review
    per comment would multiply the payload for nothing.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    product_name: str | None = None
    helpful_votes: int = 0
    comment_count: int = 0


class AuthoredCommentOut(BaseModel):
    """One comment a member wrote, for their profile's Comments tab.

    `CommentOut` answers "what is under this review"; this answers "what has
    this member said", which is the opposite direction and needs the review to
    travel with the row. Removed comments and comments on unpublished or removed
    reviews are never in this list — a profile is a public surface.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    helpful_votes: int = 0
    created_at: datetime
    review: CommentReview


class CommentMarkOut(BaseModel):
    """The caller's follow or save state on one comment, after a change."""

    comment_id: uuid.UUID
    followed: bool | None = None
    saved: bool | None = None


class SavedCommentOut(BaseModel):
    """One comment the caller saved (QA-069), with where it lives."""

    id: uuid.UUID
    body: str
    created_at: datetime
    author: CommentAuthor | None = None
    review: CommentReview

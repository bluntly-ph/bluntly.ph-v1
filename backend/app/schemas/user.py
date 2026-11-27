"""User-facing trust/profile schemas (M2 slices 3-4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import MemberRole


class BadgeOut(BaseModel):
    badge_id: str
    name: str
    awarded_at: datetime


class InteractionOut(BaseModel):
    user_id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    upvotes: int = 0
    downvotes: int = 0
    comments: int = 0


class PublicProfileOut(BaseModel):
    """A reviewer's public identity, resolvable by handle (BUG-030).

    The public profile lives at `/u/{handle}`, and QA reported it 404ing for
    every real reviewer. Two reasons, both here:

      * the page resolved a reviewer through the review feed's `author_id`,
        which takes a UUID — so a handle like `/u/ciel` could never match;
      * a reviewer with no PUBLISHED review has no feed row at all, so an
        account that plainly exists answered "not found".

    This resolves either spelling and does not depend on the reviewer having
    published anything. What it deliberately does NOT carry is as much the
    point as what it does: no email, no role, no staff flags, no earnings, no
    interests. `/u/{handle}` is a page a stranger can open.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    trust_stage: int
    trust_level_name: str
    reputation_score: Decimal
    verified_review_count: int
    #: Published, not removed. Zero is a real answer — see the docstring.
    review_count: int = 0
    created_at: datetime
    # Business Rules §17 — public on every profile. Never: who reported this
    # person, or what they earned.
    people_helped: int = 0
    comment_count: int = 0
    #: Whose reviews this person votes on / comments on most.
    interacts_with_most: list[InteractionOut] = Field(default_factory=list)
    #: Who votes on / comments on this person's reviews most.
    most_interacted_by: list[InteractionOut] = Field(default_factory=list)
    #: A claimed seller account (§9) — shown so readers know who they are hearing.
    is_claimed_seller: bool = False


class TrustProgressOut(BaseModel):
    """How far this member is from the next trust stage.

    The profile's Stats card (Figma 5446:6532) draws a progress bar and a
    "x of y" caption. The ladder lives in `app.services.trust`; serving the
    numbers rather than the thresholds keeps the frontend from carrying a second
    copy of it that can drift.

    `null` on the whole object means the member is at the top stage — there is
    nothing further to progress towards, which is not the same as zero progress.
    """

    next_stage: int
    next_level_name: str
    reviews_have: int
    reviews_needed: int


class UserTrustOut(BaseModel):
    """Public trust profile (M2 slice 3). Stages move only via recompute."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trust_stage: int
    trust_level_name: str
    reputation_score: Decimal
    verified_review_count: int
    helpfulness_ratio: Decimal
    badges: list[BadgeOut] = Field(default_factory=list)
    progress: TrustProgressOut | None = None


class RoleUpdate(BaseModel):
    """user <-> seller (M2 slice 4), by a Super Admin. Staff roles are refused."""

    role: MemberRole




class NotificationPrefs(BaseModel):
    """Which store notices reach this account (Figma Screen/Seller/Settings 8218:24151):
    the kinds, and the channels — each notice also by email, and the Monday summary
    (0085, sent through the email outbox)."""

    model_config = ConfigDict(extra="forbid")

    store_reviews: bool = True
    #: Only reviews of 3 stars or fewer (needs store_reviews on).
    store_reviews_low_only: bool = False
    store_questions: bool = True
    appeal_updates: bool = True
    product_links: bool = True
    #: Each notice above also by email (0085).
    email: bool = True
    #: Monday 08:00 Manila: rating, new reviews and what's waiting.
    weekly_summary: bool = True


class EmailChangeStartIn(BaseModel):
    """Overlay/Store/Account 8232:25342 "Change email" (0084)."""

    model_config = ConfigDict(extra="forbid")

    new_email: EmailStr


class EmailChangeConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The code sent to the CURRENT address, and the one sent to the NEW address.
    current_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class EmailChangePendingOut(BaseModel):
    new_email: str
    expires_at: datetime


class EmailChangeDoneOut(BaseModel):
    email: str
    #: A fresh token for THIS browser: every session issued before the change ended.
    access_token: str
    token_type: str = "bearer"
    #: Seconds, as TokenResponse: the web sets the session cookie's max-age from it.
    expires_in: int

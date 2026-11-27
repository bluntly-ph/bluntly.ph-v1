"""The Super Admin's 2.5-star routing queue (owner decision A)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import EarnEligibleStatus, SpecialRoute, Verdict


class SpecialRoutingItem(BaseModel):
    """What a Super Admin needs to decide — and nothing about anyone's money."""

    review_id: uuid.UUID
    review_ref: str | None = None
    title: str
    product_name: str | None = None
    author: str | None = None
    #: The entry that decides the thread: the latest visible one.
    latest_entry_id: uuid.UUID
    verdict: Verdict
    stars: Decimal
    photo_provided: bool
    status: EarnEligibleStatus
    created_at: datetime
    escalated_at: datetime | None = None
    #: Figma Screen/Admin/SpecialRouting 8178:20045 + Overlay/Routing/Track 8178:20344:
    #: the author's name, the latest entry's opening words, the product picture
    #: and the note the Administrator left when approving it to earn.
    author_name: str | None = None
    excerpt: str | None = None
    product_image_url: str | None = None
    approval_note: str | None = None


class SpecialRoutingIn(BaseModel):
    destination: SpecialRoute
    #: The explicit confirmation the console sends after its dialog.
    confirm: Literal["route"]
    #: Overlay/Routing/Track "Note for the log": kept in the Activity log only.
    note: str | None = Field(default=None, max_length=500)


class SpecialRoutingResult(BaseModel):
    review_id: uuid.UUID
    destination: SpecialRoute
    status: EarnEligibleStatus
    routed_at: datetime | None = None
    #: False when this exact decision had already been recorded.
    changed: bool


class SpecialRoutingDecision(BaseModel):
    """One audited decision, as the history lists it."""

    at: datetime
    review_id: uuid.UUID | None = None
    review_ref: str | None = None
    destination: str | None = None
    previous_status: str | None = None
    actor_staff_ref: str | None = None
    #: The Super Admin's name ("Routed this month · By Zient P.").
    actor_name: str | None = None

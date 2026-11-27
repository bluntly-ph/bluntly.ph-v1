"""Seller support request payloads (0063).

Two views of one row, on purpose:

    SupportRequestOut        what the store's owner sees — their words, the
                             status and the administrator's reply
    AdminSupportRequestOut   adds who is handling it and the staff-only
                             internal note

A seller never receives `internal_note`, another store's request, a reporter's
identity or any moderation evidence: the seller schema simply has no field
that could carry them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.link_policy import reject_links
from app.models.enums import SupportRequestCategory, SupportRequestStatus


class SupportRequestCreate(BaseModel):
    category: SupportRequestCategory
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=4000)
    #: A review OF THIS STORE the request is about.
    related_seller_review_id: uuid.UUID | None = None
    #: A product review the request is about (e.g. one naming the store).
    related_review_id: uuid.UUID | None = None
    related_product_id: uuid.UUID | None = None

    @field_validator("subject", "message")
    @classmethod
    def _no_links(cls, value: str) -> str:
        # Business Rules §1: no links in user-written text, support included.
        return reject_links(value.strip(), field="support requests")


class SupportRequestOut(BaseModel):
    id: uuid.UUID
    reference: str
    #: The Messages thread this request was moved from (MQA-021): its one
    #: history, where the seller replies. None for a request filed directly.
    conversation_id: uuid.UUID | None = None
    seller_id: uuid.UUID
    seller_name: str | None = None
    category: SupportRequestCategory
    subject: str
    message: str
    related_seller_review_id: uuid.UUID | None = None
    related_review_id: uuid.UUID | None = None
    related_product_id: uuid.UUID | None = None
    status: SupportRequestStatus
    admin_response: str | None = None
    admin_responded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class AdminSupportRequestOut(SupportRequestOut):
    created_by: str | None = None
    assigned_admin: str | None = None
    assigned_admin_id: uuid.UUID | None = None
    #: Staff-only; never sent to the seller.
    internal_note: str | None = None


class SupportRespondIn(BaseModel):
    """An administrator's reply to the seller, optionally moving the status."""

    response: str = Field(min_length=1, max_length=4000)
    status: SupportRequestStatus | None = None
    #: MQA-022, one choice made when replying: "ask" (for more information:
    #: waiting for the seller), "review" (keep in review) or "resolve".
    #: Wins over `status` when both are sent.
    action: Literal["ask", "review", "resolve"] | None = None


class SupportStatusIn(BaseModel):
    status: SupportRequestStatus
    internal_note: str | None = Field(default=None, max_length=4000)

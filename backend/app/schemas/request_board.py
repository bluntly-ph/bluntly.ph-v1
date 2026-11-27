"""Request board schemas (M3 slice 9)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.link_policy import reject_links
from app.models.enums import RequestStatus
from app.schemas.urls import web_url_or_none


class RequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    details: str = Field(min_length=1)
    product_id: uuid.UUID | None = None
    # A marketplace link for humans. Stored, shown, NEVER fetched (no scraping).
    source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def _only_web_source(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Listing links")

    # The marketplace link belongs in `source_url` (moderator-only); the public
    # title and details follow the platform-wide link ban (Business Rules §1).
    @field_validator("title", "details")
    @classmethod
    def _no_links(cls, value: str) -> str:
        return reject_links(value, field="requests")


class FulfillRequest(BaseModel):
    review_id: uuid.UUID


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    request_id: str | None = None
    requester_id: uuid.UUID
    product_id: uuid.UUID | None = None
    title: str
    details: str
    source_url: str | None = None
    status: RequestStatus
    fulfilled_by_review_id: uuid.UUID | None = None
    expires_at: datetime
    upvote_count: int = 0
    # Whether the requesting viewer has up-voted this (BUG-026). Not a column —
    # the route fills it in, because it is a fact about the viewer. Without it
    # the count survived a refresh but the highlight did not, and clicking again
    # sent a second POST that the unique constraint rejected, which read as the
    # button hanging.
    my_upvote: bool = False
    ai_validation: dict | None = None
    created_at: datetime
    #: When the asker picked the Best Answer (2026-09-29; 0057 stored it).
    fulfilled_at: datetime | None = None
    #: Not columns: the route fills them in. How many reviews answer it, and
    #: the name of the product it belongs to.
    answer_count: int = 0
    product_name: str | None = None


class RequestAnswerOut(BaseModel):
    """One answer to a request: a public review of its product, written after
    it by someone other than the asker (dev/QA sync 2026-09-29)."""

    review_id: uuid.UUID
    title: str | None = None
    excerpt: str
    star_rating: float
    verdict: str
    author_username: str | None = None
    author_display_name: str | None = None
    created_at: datetime
    is_best: bool = False

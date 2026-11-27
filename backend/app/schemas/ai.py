"""AI critique schemas (M1)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CritiqueRequest(BaseModel):
    """Ad-hoc critique of arbitrary draft text (also reused for stored reviews)."""

    # Caps that bound what one call can cost on a paid provider. A review's
    # longest field is 5,000 characters, so 10,000 is room for a whole draft.
    title: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=10_000)


class CritiqueResponse(BaseModel):
    provider: str
    model: str
    quality_score: int = Field(ge=0, le=100)
    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class RequestValidation(BaseModel):
    """AI screening verdict for a review request (M3 slice 9)."""

    valid: bool
    reasons: list[str] = Field(default_factory=list)
    provider: str
    model: str

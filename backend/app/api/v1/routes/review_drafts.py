"""Review drafts, kept with the account so they follow the reviewer across devices
(QA-003). Every route is the caller's own; nothing here is ever public.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import review_draft_service

router = APIRouter(prefix="/review-drafts", tags=["reviews"])


class DraftIn(BaseModel):
    draft: dict
    saved_at: int = Field(ge=0, description="The client's save time, ms since epoch")


class DraftOut(BaseModel):
    slot: str
    draft: dict
    saved_at: int


def _out(row) -> DraftOut:
    return DraftOut(slot=row.slot, draft=row.payload, saved_at=row.saved_at_ms)


@router.get("", response_model=list[DraftOut], summary="Your unfinished reviews, newest first")
def list_drafts(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> list[DraftOut]:
    return [_out(r) for r in review_draft_service.list_for(db, user)]


@router.put("/{slot}", response_model=DraftOut,
            summary="Save an unfinished review (an older save never replaces a newer one)")
def save_draft(slot: str, body: DraftIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> DraftOut:
    return _out(review_draft_service.save(db, user, slot, body.draft, body.saved_at))


@router.delete("/{slot}", status_code=204, summary="Discard an unfinished review")
def delete_draft(slot: str, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> Response:
    review_draft_service.delete(db, user, slot)
    return Response(status_code=204)

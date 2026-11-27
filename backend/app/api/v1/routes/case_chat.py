"""Chat on a seller claim or a review appeal: the filer and staff only.

    GET  /cases/{kind}/{case_id}/messages     kind = claim | appeal | appeal-reviewer
    POST /cases/{kind}/{case_id}/messages

Who may read and write is decided in services/case_chat_service.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.conversation import ConversationAttachmentOut
from app.services import case_chat_service

router = APIRouter(prefix="/cases", tags=["sellers"])

Kind = Path(pattern="^(claim|appeal|appeal-reviewer)$")


class CaseMessageOut(BaseModel):
    id: str
    author_id: uuid.UUID | None = None
    author_name: str | None = None
    #: Written by an Administrator or Super Admin (shown as "Bluntly").
    from_staff: bool
    body: str
    sent_at: datetime
    #: A file sent in the case's thread; `href` answers with a 5-minute signed link.
    attachment: ConversationAttachmentOut | None = None


class CaseMessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=case_chat_service.MAX_LENGTH)


@router.get("/{kind}/{case_id}/messages", response_model=list[CaseMessageOut],
            summary="The conversation on a seller claim or review appeal (its filer or staff)")
def case_messages(case_id: uuid.UUID, kind: str = Kind, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[CaseMessageOut]:
    return [CaseMessageOut(**m.__dict__)
            for m in case_chat_service.messages(db, kind, case_id, user)]


@router.post("/{kind}/{case_id}/messages", response_model=CaseMessageOut, status_code=201,
             summary="Write on a seller claim or review appeal (its filer or staff)")
def send_case_message(payload: CaseMessageIn, case_id: uuid.UUID, kind: str = Kind,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> CaseMessageOut:
    return CaseMessageOut(**case_chat_service.send(db, kind, case_id, user, payload.body).__dict__)

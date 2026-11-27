"""Store change requests (MQA-017/018/019/020/025).

    POST /sellers/{seller_id}/change-requests     the store's owner asks (one or more changes)
    GET  /sellers/{seller_id}/change-requests     the owner's requests and their status
    GET  /admin/inbox/{conversation_id}/changes   the changes a thread carries (staff)
    POST /admin/store-changes/{request_id}/decision   approve (applies it) or reject (staff)
    POST /admin/sellers/{seller_id}/details      a moderator corrects a store (staff)

Who may do what is decided in services/store_change_service.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.seller import Seller
from app.models.store_change import StoreChangeRequest
from app.models.user import User
from app.services import store_change_service as svc

router = APIRouter(tags=["sellers"])


class StoreChangeOut(BaseModel):
    id: uuid.UUID
    seller_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    field: Literal["display_name", "store_url", "registration"]
    #: "Store name", "Store link", "Registration".
    label: str
    #: The store's value when the owner asked.
    current_value: str | None = None
    requested_value: str
    #: The store's value now (staff view): it may have moved since.
    live_value: str | None = None
    #: Store links only: why this link cannot be the store's (MQA-020), if so.
    link_problem: str | None = None
    status: Literal["pending", "approved", "rejected"]
    decision_note: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class StoreChangeSent(BaseModel):
    conversation_id: uuid.UUID
    requests: list[StoreChangeOut]


class StoreChangeDecision(BaseModel):
    decision: Literal["approve", "reject"]
    #: Shown to the owner; required to reject.
    note: str | None = Field(default=None, max_length=1000)


def _out(db: Session, row: StoreChangeRequest, *, staff: bool = False) -> StoreChangeOut:
    seller = db.get(Seller, row.seller_id) if staff else None
    return StoreChangeOut(
        id=row.id, seller_id=row.seller_id, conversation_id=row.conversation_id,
        field=row.field, label=svc.FIELD_LABEL[row.field],
        current_value=svc.display(row.field, row.current_value),
        requested_value=svc.display(row.field, row.requested_value),
        live_value=svc.display(row.field, svc._current(db, seller, row.field))  # noqa: SLF001
        if seller is not None else None,
        link_problem=svc.link_mismatch(seller.platform, row.requested_value)
        if seller is not None and row.field == "store_url" and row.status == "pending" else None,
        status=row.status, decision_note=row.decision_note, decided_at=row.decided_at,
        created_at=row.created_at)


def _changes(raw: str) -> list[svc.ChangeIn]:
    try:
        items = json.loads(raw)
        return [svc.ChangeIn(field=str(i["field"]), value=str(i.get("value") or ""),
                             kind=(str(i["kind"]) if i.get("kind") else None))
                for i in items]
    except (ValueError, TypeError, KeyError) as exc:
        raise AppError("Send the changes as a list of {field, value}.", code="change_invalid",
                       status_code=422, title="Invalid change") from exc


@router.post("/sellers/{seller_id}/change-requests", response_model=StoreChangeSent,
             status_code=201, summary="Ask for changes to your store (its approved owner)")
async def request_changes(seller_id: uuid.UUID, changes: str = Form(...),
                          note: str = Form(default=""),
                          file: UploadFile | None = File(default=None),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> StoreChangeSent:
    from app.api.v1.routes.conversations import _file
    conversation_id, rows = svc.submit(db, user, seller_id, _changes(changes), note,
                                       await _file(file))
    return StoreChangeSent(conversation_id=conversation_id,
                           requests=[_out(db, r) for r in rows])


@router.get("/sellers/{seller_id}/change-requests", response_model=list[StoreChangeOut],
            summary="Your store's change requests and their status (its approved owner)")
def my_changes(seller_id: uuid.UUID, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> list[StoreChangeOut]:
    from app.services import conversation_service as conv_svc
    conv_svc._owns_store(db, user, seller_id)  # noqa: SLF001 - the one owner rule
    return [_out(db, r) for r in svc.for_store(db, seller_id)]


@router.get("/admin/inbox/{conversation_id}/changes", response_model=list[StoreChangeOut],
            tags=["admin: inbox"], dependencies=[Depends(require_staff)],
            summary="The store changes a conversation asks for")
def thread_changes(conversation_id: uuid.UUID,
                   db: Session = Depends(get_db)) -> list[StoreChangeOut]:
    return [_out(db, r, staff=True) for r in svc.for_conversation(db, conversation_id)]


@router.post("/admin/store-changes/{request_id}/decision", response_model=StoreChangeOut,
             tags=["admin: inbox"], summary="Approve (apply to the store) or reject a change")
def decide_change(request_id: uuid.UUID, payload: StoreChangeDecision,
                  db: Session = Depends(get_db),
                  staff: User = Depends(require_staff)) -> StoreChangeOut:
    return _out(db, svc.decide(db, staff, request_id, payload.decision, payload.note),
                staff=True)


class StoreEditIn(BaseModel):
    field: Literal["display_name", "store_url", "registration"]
    value: str = Field(max_length=2000)
    kind: Literal["dti", "sec"] | None = None
    note: str | None = Field(default=None, max_length=1000)


@router.post("/admin/sellers/{seller_id}/details", response_model=StoreChangeOut,
             tags=["admin: sellers"], summary="Correct a store's name, link or registration")
def edit_store(seller_id: uuid.UUID, payload: StoreEditIn, db: Session = Depends(get_db),
               staff: User = Depends(require_staff)) -> StoreChangeOut:
    row = svc.staff_edit(db, staff, seller_id,
                         svc.ChangeIn(field=payload.field, value=payload.value,
                                      kind=payload.kind), payload.note)
    return _out(db, row, staff=True)

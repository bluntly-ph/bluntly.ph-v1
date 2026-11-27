"""Seller support requests (owner decision 2026-09-28; docs/SELLER_DASHBOARD.md).

    Store owner (approved claim on THIS store):
      POST /sellers/{seller_id}/support-requests
      GET  /sellers/{seller_id}/support-requests
      GET  /sellers/{seller_id}/support-requests/{request_id}

    Staff:
      GET  /admin/support-requests[?status=]
      GET  /admin/support-requests/{request_id}
      POST /admin/support-requests/{request_id}/assign
      POST /admin/support-requests/{request_id}/respond
      POST /admin/support-requests/{request_id}/status

Ownership is re-derived from the database on every call: seller A asking for
seller B's store gets 403 `not_store_owner`; asking for B's request through A's
own store path gets 404. The staff guard is one named dependency so the coming
Administrator / Super Admin split changes a line, not the endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.enums import SupportRequestStatus
from app.models.user import User
from app.schemas.support import (
    AdminSupportRequestOut,
    SupportRequestCreate,
    SupportRequestOut,
    SupportRespondIn,
    SupportStatusIn,
)
from app.services import seller_service, support_service

router = APIRouter(tags=["support requests"])

#: Who handles support requests. One line to change when roles are split.
require_support_staff = require_staff


@router.post("/sellers/{seller_id}/support-requests", response_model=SupportRequestOut,
             status_code=201, summary="Contact the administrators about your store")
def create_request(seller_id: uuid.UUID, payload: SupportRequestCreate,
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> SupportRequestOut:
    seller = seller_service.get_seller_or_404(db, seller_id)
    return support_service.create(db, seller, user, payload)


@router.get("/sellers/{seller_id}/support-requests", response_model=list[SupportRequestOut],
            summary="Your store's support requests, newest first")
def list_requests(seller_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[SupportRequestOut]:
    seller = seller_service.get_seller_or_404(db, seller_id)
    return support_service.list_for_store(db, seller, user)


@router.get("/sellers/{seller_id}/support-requests/{request_id}",
            response_model=SupportRequestOut, summary="One of your store's support requests")
def get_request(seller_id: uuid.UUID, request_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> SupportRequestOut:
    seller = seller_service.get_seller_or_404(db, seller_id)
    return support_service.get_for_store(db, seller, user, request_id)


@router.get("/admin/support-requests", response_model=list[AdminSupportRequestOut],
            summary="Support requests, oldest first (staff)")
def admin_list(status: SupportRequestStatus | None = Query(default=None),
               limit: int = Query(default=100, ge=1, le=200),
               db: Session = Depends(get_db),
               _: User = Depends(require_support_staff)) -> list[AdminSupportRequestOut]:
    return support_service.admin_list(db, status, limit)


@router.get("/admin/support-requests/{request_id}", response_model=AdminSupportRequestOut,
            summary="One support request (staff)")
def admin_get(request_id: uuid.UUID, db: Session = Depends(get_db),
              _: User = Depends(require_support_staff)) -> AdminSupportRequestOut:
    return support_service.admin_get(db, request_id)


@router.post("/admin/support-requests/{request_id}/assign", response_model=AdminSupportRequestOut,
             summary="Take a support request (staff)")
def admin_assign(request_id: uuid.UUID, db: Session = Depends(get_db),
                 staff: User = Depends(require_support_staff)) -> AdminSupportRequestOut:
    return support_service.assign(db, request_id, staff)


@router.post("/admin/support-requests/{request_id}/respond",
             response_model=AdminSupportRequestOut,
             summary="Answer the seller, optionally moving the status (staff)")
def admin_respond(request_id: uuid.UUID, payload: SupportRespondIn,
                  db: Session = Depends(get_db),
                  staff: User = Depends(require_support_staff)) -> AdminSupportRequestOut:
    return support_service.respond(db, request_id, staff, payload.response, payload.status,
                                   payload.action)


@router.post("/admin/support-requests/{request_id}/status",
             response_model=AdminSupportRequestOut,
             summary="Set a support request's status, with an internal note (staff)")
def admin_status(request_id: uuid.UUID, payload: SupportStatusIn,
                 db: Session = Depends(get_db),
                 staff: User = Depends(require_support_staff)) -> AdminSupportRequestOut:
    return support_service.set_status(db, request_id, staff, payload.status,
                                      payload.internal_note)

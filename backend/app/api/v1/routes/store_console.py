"""The rest of a store owner's console (Figma Screen/Seller/Insights 8208:22905,
Overlay/Store/Export 8213:23286, Screen/Seller/StoreProfile 8209:23011,
Confirm/Store/GiveUp 8220:24024).

Owner only (the store's approved owner; anyone else 403, staff included —
staff read stores in the Admin console):

    GET  /sellers/{seller_id}/insights?period=          store review figures by month
    GET  /sellers/{seller_id}/export/sizes?period=      rows per file, for the overlay
    GET  /sellers/{seller_id}/export?include=&period=   a zip of CSVs
    GET  /sellers/{seller_id}/profile                   the store and how its claim was verified
    POST /sellers/{seller_id}/give-up                   the store goes back to unclaimed
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import seller_insights, store_profile_service

router = APIRouter(tags=["sellers"])

EXPORT_FILES = ("reviews", "questions", "appeals", "products")


class _Attrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InsightsMonthOut(_Attrs):
    month: str
    reviews: int
    rating: float | None = None
    recommend: float | None = None
    responded: float | None = None
    matched: float | None = None
    complete: float | None = None
    service: float | None = None
    packaging: float | None = None


class InsightsPeersOut(_Attrs):
    stores: int
    rating: float | None = None
    recommend: float | None = None
    packaging: float | None = None
    responded: float | None = None


class StoreInsightsOut(_Attrs):
    period: str
    reviews: int
    reviews_before: int
    rating: float | None = None
    recommend: float | None = None
    responded: float | None = None
    matched: float | None = None
    complete: float | None = None
    service: float | None = None
    packaging: float | None = None
    reply_hours: float | None = None
    reply_hours_first: float | None = None
    months: list[InsightsMonthOut]
    peers: InsightsPeersOut | None = None
    platform: str


class ExportSizesOut(BaseModel):
    reviews: int
    questions: int
    appeals: int
    products: int


class OwnershipOut(_Attrs):
    registration_kind: str | None = None
    registration_last4: str | None = None
    registered_business_name: str | None = None
    marketplace_shop_name: str | None = None
    shop_name_matches: bool | None = None
    approved_at: datetime | None = None
    owner_name: str


class StoreProfileOut(_Attrs):
    id: uuid.UUID
    display_name: str
    platform: str
    store_url: str | None = None
    on_bluntly_since: datetime
    rating: float | None = None
    reviews: int
    ownership: OwnershipOut


@router.get("/sellers/{seller_id}/insights", response_model=StoreInsightsOut,
            summary="Store review figures by month (owner only)")
def insights(seller_id: uuid.UUID, period: str = Query(default="6m", max_length=8),
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> StoreInsightsOut:
    return StoreInsightsOut.model_validate(seller_insights.insights(db, seller_id, user, period))


@router.get("/sellers/{seller_id}/export/sizes", response_model=ExportSizesOut,
            summary="Rows in each export file (owner only)")
def export_sizes(seller_id: uuid.UUID, period: str = Query(default="6m", max_length=8),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> ExportSizesOut:
    return ExportSizesOut(**seller_insights.export_sizes(db, seller_id, user, period))


@router.get("/sellers/{seller_id}/export", response_class=Response,
            responses={200: {"content": {"application/zip": {}}}},
            summary="Download the store's data as CSV files in a zip (owner only)")
def export(seller_id: uuid.UUID,
           include: str = Query(default="reviews", max_length=64,
                                description="Comma-separated: " + ", ".join(EXPORT_FILES)),
           period: str = Query(default="6m", max_length=8), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)) -> Response:
    chosen = {part.strip() for part in include.split(",") if part.strip()}
    if not chosen or not chosen <= set(EXPORT_FILES):
        raise AppError("Choose what to include.", code="export_include_invalid",
                       status_code=422, title="Invalid export")
    filename, data = seller_insights.export(db, seller_id, user, chosen, period)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/sellers/{seller_id}/profile", response_model=StoreProfileOut,
            summary="The store and how its claim was verified (owner only)")
def profile(seller_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> StoreProfileOut:
    return StoreProfileOut.model_validate(store_profile_service.profile(db, seller_id, user))


@router.post("/sellers/{seller_id}/give-up", status_code=204, response_class=Response,
             summary="Give the store up: it goes back to unclaimed (owner only)")
def give_up(seller_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> Response:
    store_profile_service.give_up(db, seller_id, user)
    return Response(status_code=204)

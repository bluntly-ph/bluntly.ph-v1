"""Store ↔ product links (0077; Figma Screen/Seller/Products and its overlays).

Owner (the store's approved owner only; anyone else 403):

    GET  /sellers/{seller_id}/products                      linked, waiting, not approved
    GET  /sellers/{seller_id}/products/options?q=           catalogue products to link
    POST /sellers/{seller_id}/products                      {product_id} — send for approval
    POST /sellers/{seller_id}/products/{link_id}/cancel     withdraw a waiting request
    GET  /sellers/{seller_id}/products/{product_id}/analytics   approved links only

Staff:

    GET  /admin/store-products?status=pending|approved|rejected|cancelled
    POST /admin/store-products/{link_id}/decision           {decision: approve|reject, note?}
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.user import User
from app.services import store_product_service as svc

router = APIRouter(tags=["sellers"])


class _Attrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StoreProductFiguresOut(_Attrs):
    reviews: int
    median: float | None = None
    change_30d: float | None = None
    worth_it: float | None = None
    complicated: float | None = None
    not_worth: float | None = None
    questions: int
    open_questions: int


class StoreProductRowOut(_Attrs):
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    category: str | None = None
    image_url: str | None = None
    status: Literal["pending", "approved", "rejected", "cancelled"]
    requested_at: datetime
    decided_at: datetime | None = None
    decision_note: str | None = None
    figures: StoreProductFiguresOut


class StoreProductsOut(_Attrs):
    rows: list[StoreProductRowOut]
    linked: int
    waiting: int
    reviews: int
    open_questions: int
    products_with_open_questions: int


class StoreProductOptionOut(_Attrs):
    product_id: uuid.UUID
    name: str
    category: str | None = None
    review_count: int
    state: Literal["link", "pending", "linked"]


class StoreProductLinkOut(_Attrs):
    id: uuid.UUID
    product_id: uuid.UUID
    status: Literal["pending", "approved", "rejected", "cancelled"]
    created_at: datetime
    decided_at: datetime | None = None


class StoreProductLinkIn(BaseModel):
    product_id: uuid.UUID


class MonthPointOut(_Attrs):
    month: str
    median: float | None = None
    category_median: float | None = None


class ThemeOut(_Attrs):
    text: str
    reviews: int
    share: float


class RecentQuestionOut(BaseModel):
    id: uuid.UUID
    body: str
    created_at: datetime
    answers: int


class StoreProductAnalyticsOut(_Attrs):
    product_id: uuid.UUID
    name: str
    category: str | None = None
    figures: StoreProductFiguresOut
    months: list[MonthPointOut]
    worth_it_last_month: float | None = None
    complaints: list[ThemeOut]
    praise: list[ThemeOut]
    category_products: int
    category_median: float | None = None
    category_worth_it: float | None = None
    store_answered: float | None = None
    category_store_answered: float | None = None
    recent_questions: list[RecentQuestionOut]


class AdminStoreProductOut(_Attrs):
    id: uuid.UUID
    status: str
    seller_id: uuid.UUID
    seller_name: str
    product_id: uuid.UUID
    product_name: str
    product_category: str | None = None
    review_count: int
    requested_by: str | None = None
    requested_at: datetime
    decided_at: datetime | None = None
    decision_note: str | None = None


class StoreProductDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


def _link(link) -> StoreProductLinkOut:
    return StoreProductLinkOut(id=link.id, product_id=link.product_id, status=link.status.value,
                               created_at=link.created_at, decided_at=link.decided_at)


@router.get("/sellers/{seller_id}/products", response_model=StoreProductsOut,
            summary="Your store's linked products and link requests (owner only)")
def store_products(seller_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> StoreProductsOut:
    return StoreProductsOut.model_validate(svc.list_for_store(db, seller_id, user))


@router.get("/sellers/{seller_id}/products/options", response_model=list[StoreProductOptionOut],
            summary="Catalogue products your store could link (owner only)")
def store_product_options(seller_id: uuid.UUID, q: str = Query(min_length=1, max_length=120),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)) -> list[StoreProductOptionOut]:
    return [StoreProductOptionOut.model_validate(o) for o in svc.options(db, seller_id, user, q)]


@router.post("/sellers/{seller_id}/products", response_model=StoreProductLinkOut, status_code=201,
             summary="Ask to link a product your store sells (owner only; a moderator approves)")
def link_store_product(seller_id: uuid.UUID, payload: StoreProductLinkIn,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> StoreProductLinkOut:
    return _link(svc.request_link(db, seller_id, user, payload.product_id))


@router.post("/sellers/{seller_id}/products/{link_id}/cancel", response_model=StoreProductLinkOut,
             summary="Cancel a link request still waiting for approval (owner only)")
def cancel_store_product(seller_id: uuid.UUID, link_id: uuid.UUID,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> StoreProductLinkOut:
    return _link(svc.cancel_link(db, seller_id, user, link_id))


@router.get("/sellers/{seller_id}/products/{product_id}/analytics",
            response_model=StoreProductAnalyticsOut,
            summary="A linked product's figures for its store (owner only, approved links)")
def store_product_analytics(seller_id: uuid.UUID, product_id: uuid.UUID,
                            db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)) -> StoreProductAnalyticsOut:
    return StoreProductAnalyticsOut.model_validate(
        svc.analytics(db, seller_id, user, product_id))


@router.get("/admin/store-products", response_model=list[AdminStoreProductOut],
            tags=["admin"], summary="Stores' product link requests (staff)")
def admin_store_products(status: Literal["pending", "approved", "rejected",
                                         "cancelled"] = "pending",
                         db: Session = Depends(get_db),
                         staff: User = Depends(require_staff)) -> list[AdminStoreProductOut]:
    return [AdminStoreProductOut.model_validate(r) for r in svc.admin_list(db, status)]


@router.post("/admin/store-products/{link_id}/decision", response_model=StoreProductLinkOut,
             tags=["admin"], summary="Approve or reject a store's product link (staff)")
def decide_store_product(link_id: uuid.UUID, payload: StoreProductDecisionIn,
                         db: Session = Depends(get_db),
                         staff: User = Depends(require_staff)) -> StoreProductLinkOut:
    return _link(svc.decide(db, staff, link_id, payload.decision == "approve", payload.note))

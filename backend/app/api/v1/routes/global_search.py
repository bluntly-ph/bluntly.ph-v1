"""The top bar's search (Figma Search/Admin/Global, Search/Seller/Global).

    GET /admin/search?q=               staff: reviews, products, sellers, people
    GET /sellers/{seller_id}/search?q= the store's owner: its reviews, questions,
                                       and the products its buyers reviewed
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.user import User
from app.services import global_search

router = APIRouter(tags=["search"])


class SearchHitOut(BaseModel):
    type: str
    id: uuid.UUID
    title: str
    sub: str | None = None
    href: str
    tag: str


class SearchGroupOut(BaseModel):
    key: str
    label: str
    items: list[SearchHitOut]


def _out(groups: list[global_search.Group]) -> list[SearchGroupOut]:
    return [SearchGroupOut(key=g.key, label=g.label,
                           items=[SearchHitOut(**h.__dict__) for h in g.items]) for g in groups]


@router.get("/admin/search", response_model=list[SearchGroupOut], tags=["admin: console"],
            summary="Search reviews, products, sellers and people (staff)")
def admin_search(q: str = Query(min_length=1, max_length=120), db: Session = Depends(get_db),
                 staff: User = Depends(require_staff)) -> list[SearchGroupOut]:
    return _out(global_search.admin_search(db, q))


@router.get("/sellers/{seller_id}/search", response_model=list[SearchGroupOut],
            summary="Search your store's reviews, questions and products (owner only)")
def store_search(seller_id: uuid.UUID, q: str = Query(min_length=1, max_length=120),
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[SearchGroupOut]:
    return _out(global_search.store_search(db, seller_id, user, q))

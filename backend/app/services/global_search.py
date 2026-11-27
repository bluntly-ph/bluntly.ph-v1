"""The top bar's search (Figma Search/Admin/Global 8289:29993, Search/Seller/Global
8289:30079, and their "No results" states 8314:32952 / 8314:33015).

Grouped results, a few per group, each with where it opens:

* staff: reviews, products, sellers and people across the platform;
* a store's owner: that store's reviews, the questions about it and the
  products its buyers reviewed — "Searches your store only".

Read-only, and only what each viewer may already see on the screens these
results open.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import SellerClaimStatus
from app.models.product import Product
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.seller import Seller, SellerReview
from app.models.user import User
from app.services import product_search
from app.services.seller_service import require_store_owner

PER_GROUP = 3
MIN_LENGTH = 2


@dataclass(frozen=True)
class Hit:
    type: str
    id: uuid.UUID
    title: str
    sub: str | None
    href: str
    tag: str


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    items: list[Hit]


def _name(user: User | None) -> str:
    if user is None:
        return "Someone"
    return user.display_name or (f"@{user.username}" if user.username else "Someone")


def _stars(value: Decimal | float | None) -> str:
    return f"{float(value or 0):g}★"


def _ago(moment: datetime) -> str:
    days = (datetime.now(UTC) - moment).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return f"{months} month{'s' if months > 1 else ''} ago"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' if n != 1 else ''}"


def _like(q: str) -> str:
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _users(db: Session, ids) -> dict[uuid.UUID, User]:
    ids = [i for i in ids if i is not None]
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def admin_search(db: Session, q: str) -> list[Group]:
    term = (q or "").strip()
    if len(term) < MIN_LENGTH:
        return []
    like = _like(term)
    groups: list[Group] = []

    product_ids = product_search.matching_product_ids(term)
    match = or_(Review.title.ilike(like, escape="\\"), Review.product_id.in_(product_ids))
    try:  # "or a review ID" (8314:32952): a pasted id finds that review.
        match = or_(match, Review.id == uuid.UUID(term))
    except ValueError:
        pass
    reviews = db.scalars(
        select(Review).where(Review.published_at.is_not(None), match)
        .order_by(Review.published_at.desc()).limit(PER_GROUP)).all()
    authors = _users(db, {r.author_id for r in reviews})
    products = {p.id: p for p in db.scalars(select(Product).where(
        Product.id.in_([r.product_id for r in reviews])))} if reviews else {}
    hits = []
    for r in reviews:
        product = products.get(r.product_id)
        live = not r.is_removed
        hits.append(Hit(
            type="review", id=r.id, title=r.title,
            sub=" · ".join(x for x in (_stars(r.star_rating), _name(authors.get(r.author_id)),
                                       product.canonical_name if product else None) if x),
            href=f"/reviews/{r.id}" if live
            else f"/admin/review-queue?tab=all&aq={quote(r.title)}",
            tag="Review"))
    if hits:
        groups.append(Group("reviews", "Reviews", hits))

    found = db.scalars(product_search.search(select(Product), term, browse=False)
                       .limit(PER_GROUP)).all()
    if found:
        groups.append(Group("products", "Products", [
            Hit(type="product", id=p.id, title=p.canonical_name or "Unnamed product",
                sub=" · ".join(x for x in (p.category, _count(p.review_count, "review")) if x),
                href=f"/admin/products?q={quote(p.canonical_name or '')}", tag="Product")
            for p in found]))

    sellers = db.scalars(select(Seller).where(Seller.display_name.ilike(like, escape="\\"))
                         .order_by(func.length(Seller.display_name)).limit(PER_GROUP)).all()
    owners = _users(db, {s.claimed_by_id for s in sellers
                         if s.claim_status == SellerClaimStatus.claimed})
    people = db.scalars(select(User).where(or_(User.display_name.ilike(like, escape="\\"),
                                               User.username.ilike(like, escape="\\")))
                        .order_by(User.trust_stage.desc()).limit(PER_GROUP)).all()
    mixed = [Hit(type="seller", id=s.id, title=s.display_name,
                 sub=("Store · claimed by " + _name(owners.get(s.claimed_by_id)))
                 if s.claim_status == SellerClaimStatus.claimed and s.claimed_by_id in owners
                 else "Store · not claimed",
                 href=f"/sellers/{s.id}", tag="Seller") for s in sellers]
    mixed += [Hit(type="person", id=u.id, title=_name(u),
                  sub=f"{u.role.value.replace('_', ' ').capitalize()} · {u.trust_level_name}"
                  if u.role.value != "user" else f"Reviewer · {u.trust_level_name}",
                  href=f"/admin/people/{u.id}", tag="Person") for u in people]
    if mixed:
        groups.append(Group("people", "Sellers & people", mixed))
    return groups


def store_search(db: Session, seller_id: uuid.UUID, user: User, q: str) -> list[Group]:
    seller = db.get(Seller, seller_id)
    if seller is None:
        from app.core.errors import NotFoundError
        raise NotFoundError("Seller not found.", code="seller_not_found")
    require_store_owner(seller, user)
    term = (q or "").strip()
    if len(term) < MIN_LENGTH:
        return []
    like = _like(term)
    groups: list[Group] = []

    reviewer_ids = select(User.id).where(or_(User.display_name.ilike(like, escape="\\"),
                                             User.username.ilike(like, escape="\\")))
    reviews = db.scalars(
        select(SellerReview)
        .where(SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False),
               or_(SellerReview.title.ilike(like, escape="\\"),
                   SellerReview.comment.ilike(like, escape="\\"),
                   SellerReview.reviewer_id.in_(reviewer_ids)))
        .order_by(SellerReview.created_at.desc()).limit(PER_GROUP)).all()
    reviewers = _users(db, {r.reviewer_id for r in reviews})
    if reviews:
        groups.append(Group("reviews", "Reviews", [
            Hit(type="review", id=r.id, title=r.title or (r.comment or "A review")[:80],
                sub=" · ".join((_stars(r.overall_rating), _name(reviewers.get(r.reviewer_id)),
                                _ago(r.created_at))),
                href=f"/seller/{seller.id}/reviews", tag="Review")
            for r in reviews]))

    questions = db.scalars(
        select(Question).where(Question.seller_id == seller.id,
                               Question.body.ilike(like, escape="\\"))
        .order_by(Question.created_at.desc()).limit(PER_GROUP)).all()
    if questions:
        askers = _users(db, {x.asker_id for x in questions})
        answered = dict(db.execute(
            select(Answer.question_id, func.count()).where(
                Answer.question_id.in_([x.id for x in questions])).group_by(Answer.question_id)
        ).all())
        groups.append(Group("questions", "Questions", [
            Hit(type="question", id=x.id, title=x.body[:120],
                sub=f"{_name(askers.get(x.asker_id))} · "
                    + (f"{answered[x.id]} answer{'s' if answered[x.id] != 1 else ''}"
                       if answered.get(x.id) else "no answer yet"),
                href=f"/questions/{x.id}", tag="Question")
            for x in questions]))

    reviewed = select(SellerReview.product_id).where(SellerReview.seller_id == seller.id,
                                                     SellerReview.product_id.is_not(None))
    products = db.scalars(product_search.search(
        select(Product).where(Product.id.in_(reviewed)), term).limit(PER_GROUP)).all()
    if products:
        groups.append(Group("products", "Products", [
            Hit(type="product", id=p.id, title=p.canonical_name or "Unnamed product",
                sub=f"{_stars(p.median_rating)} · {p.review_count} "
                    f"review{'s' if p.review_count != 1 else ''}",
                href=f"/search?q={quote(p.canonical_name or '')}", tag="Product")
            for p in products]))
    return groups

"""Store ↔ product links (0077; Figma Screen/Seller/Products, Products/Analytics,
Overlay/Store/LinkProduct, Confirm/Store/LinkProduct, Confirm/Store/CancelLink).

A store's approved owner asks to link product pages the store sells; an
Administrator approves or rejects each request. Approved links bring the
product's figures into the Seller console. Nothing here lets an owner create,
rename or edit a product page (Business Rules §9).

Every figure follows the site's rules: one value per review thread (its latest
visible entry) and medians, never means (§4). A product with fewer than five
such entries has "Not enough reviews yet" rather than a number.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import AppError, NotFoundError
from app.models.enums import (
    ModerationAction,
    ProductStatus,
    SellerClaimStatus,
    StoreProductStatus,
    Verdict,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.seller import Seller, StoreProduct
from app.models.user import User
from app.services import notification_service, product_search
from app.services.seller_service import require_store_owner

MIN_REVIEWS = 5
THEME_MIN = 5
LIVE = (StoreProductStatus.pending, StoreProductStatus.approved)


def _now() -> datetime:
    return datetime.now(UTC)


def _owned(db: Session, seller_id: uuid.UUID, user: User) -> Seller:
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise NotFoundError("Seller not found.", code="seller_not_found")
    require_store_owner(seller, user)
    return seller


# ------------------------------------------------------------------ figures

def _latest(product_ids, until: datetime | None = None):
    """Each thread's latest visible entry for these products (as of `until`)."""
    thread = func.coalesce(Review.thread_id, Review.id)
    stmt = (select(Review.product_id.label("product_id"), Review.star_rating.label("stars"),
                   Review.verdict.label("verdict"), Review.pros.label("pros"),
                   Review.cons.label("cons"))
            .where(Review.product_id.in_(product_ids), Review.is_removed.is_(False),
                   Review.published_at.is_not(None)))
    if until is not None:
        stmt = stmt.where(Review.created_at <= until)
    return stmt.distinct(Review.product_id, thread).order_by(
        Review.product_id, thread, Review.created_at.desc(), Review.id.desc()).subquery()


def _medians(db: Session, product_ids: list[uuid.UUID],
             until: datetime | None = None) -> dict[uuid.UUID, tuple[int, float | None]]:
    if not product_ids:
        return {}
    latest = _latest(product_ids, until)
    rows = db.execute(select(latest.c.product_id, func.count(),
                             func.percentile_cont(0.5).within_group(latest.c.stars.asc()))
                      .group_by(latest.c.product_id)).all()
    return {r[0]: (int(r[1]), float(r[2]) if r[2] is not None else None) for r in rows}


def _verdicts(db: Session, product_ids: list[uuid.UUID],
              until: datetime | None = None) -> dict[uuid.UUID, dict[str, int]]:
    if not product_ids:
        return {}
    latest = _latest(product_ids, until)
    out: dict[uuid.UUID, dict[str, int]] = {}
    for pid, verdict, n in db.execute(select(latest.c.product_id, latest.c.verdict, func.count())
                                      .group_by(latest.c.product_id, latest.c.verdict)):
        out.setdefault(pid, {})[verdict.value if hasattr(verdict, "value") else str(verdict)] = n
    return out


def _questions(db: Session, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """(questions asked, of which unanswered) per product."""
    if not product_ids:
        return {}
    answered = select(Answer.question_id)
    rows = db.execute(
        select(Question.product_id, func.count(),
               func.count().filter(Question.id.not_in(answered)))
        .where(Question.product_id.in_(product_ids), Question.is_removed.is_(False))
        .group_by(Question.product_id)).all()
    return {r[0]: (int(r[1]), int(r[2])) for r in rows}


@dataclass
class Figures:
    reviews: int = 0
    median: float | None = None
    change_30d: float | None = None
    worth_it: float | None = None
    complicated: float | None = None
    not_worth: float | None = None
    questions: int = 0
    open_questions: int = 0


def _figures(db: Session, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, Figures]:
    now = _medians(db, product_ids)
    then = _medians(db, product_ids, _now() - timedelta(days=30))
    verdicts = _verdicts(db, product_ids)
    questions = _questions(db, product_ids)
    out: dict[uuid.UUID, Figures] = {}
    for pid in product_ids:
        count, median = now.get(pid, (0, None))
        f = Figures(reviews=count)
        asked, open_ = questions.get(pid, (0, 0))
        f.questions, f.open_questions = asked, open_
        if count >= MIN_REVIEWS:
            f.median = round(median, 2) if median is not None else None
            t_count, t_median = then.get(pid, (0, None))
            if t_count >= MIN_REVIEWS and t_median is not None and median is not None:
                f.change_30d = round(median - t_median, 2)
            v = verdicts.get(pid, {})
            f.worth_it = v.get(Verdict.yes_absolutely.value, 0) / count
            f.complicated = v.get(Verdict.it_depends.value, 0) / count
            f.not_worth = v.get(Verdict.hard_pass.value, 0) / count
        out[pid] = f
    return out


# ------------------------------------------------------------------ owner

@dataclass
class LinkRow:
    id: uuid.UUID
    product_id: uuid.UUID
    name: str
    category: str | None
    image_url: str | None
    status: str
    requested_at: datetime
    decided_at: datetime | None
    decision_note: str | None
    figures: Figures = field(default_factory=Figures)


@dataclass
class StoreProducts:
    rows: list[LinkRow]
    linked: int
    waiting: int
    reviews: int
    open_questions: int
    products_with_open_questions: int


def list_for_store(db: Session, seller_id: uuid.UUID, user: User) -> StoreProducts:
    seller = _owned(db, seller_id, user)
    links = db.execute(
        select(StoreProduct, Product).join(Product, Product.id == StoreProduct.product_id)
        .where(StoreProduct.seller_id == seller.id,
               StoreProduct.status.in_((StoreProductStatus.pending, StoreProductStatus.approved,
                                        StoreProductStatus.rejected)))
        .order_by(StoreProduct.created_at.desc())).all()
    approved = [p.id for link, p in links if link.status == StoreProductStatus.approved]
    figures = _figures(db, [p.id for _, p in links])
    rows = [LinkRow(id=link.id, product_id=p.id, name=p.canonical_name or "Product",
                    category=p.category, image_url=p.image_url, status=link.status.value,
                    requested_at=link.created_at, decided_at=link.decided_at,
                    decision_note=link.decision_note, figures=figures.get(p.id, Figures()))
            for link, p in links]
    linked = [r for r in rows if r.status == "approved"]
    return StoreProducts(
        rows=rows, linked=len(approved),
        waiting=sum(1 for r in rows if r.status == "pending"),
        reviews=sum(r.figures.reviews for r in linked),
        open_questions=sum(r.figures.open_questions for r in linked),
        products_with_open_questions=sum(1 for r in linked if r.figures.open_questions))


@dataclass
class LinkOption:
    product_id: uuid.UUID
    name: str
    category: str | None
    review_count: int
    state: str  # link | pending | linked


def options(db: Session, seller_id: uuid.UUID, user: User, q: str) -> list[LinkOption]:
    """Overlay/Store/LinkProduct: catalogue products matching `q`, with this store's state."""
    seller = _owned(db, seller_id, user)
    term = (q or "").strip()
    if len(term) < 2:
        return []
    found = db.scalars(product_search.search(
        select(Product).where(Product.status == ProductStatus.canonicalized), term)
        .limit(12)).all()
    states = {link.product_id: link.status for link in db.scalars(
        select(StoreProduct).where(StoreProduct.seller_id == seller.id,
                                   StoreProduct.status.in_(LIVE),
                                   StoreProduct.product_id.in_([p.id for p in found])))} \
        if found else {}
    return [LinkOption(product_id=p.id, name=p.canonical_name or "Product", category=p.category,
                       review_count=p.review_count,
                       state={StoreProductStatus.pending: "pending",
                              StoreProductStatus.approved: "linked"}.get(states.get(p.id), "link"))
            for p in found]


def request_link(db: Session, seller_id: uuid.UUID, user: User,
                 product_id: uuid.UUID) -> StoreProduct:
    """Confirm/Store/LinkProduct: "Send for approval"."""
    seller = _owned(db, seller_id, user)
    product = db.get(Product, product_id)
    if product is None or product.status != ProductStatus.canonicalized:
        raise NotFoundError("That product page isn't in the catalogue.", code="product_not_found")
    live = db.scalar(select(StoreProduct).where(
        StoreProduct.seller_id == seller.id, StoreProduct.product_id == product.id,
        StoreProduct.status.in_(LIVE)))
    if live is not None:
        raise AppError("This product is already linked or waiting for approval.",
                       code="link_exists", status_code=409, title="Already requested")
    link = StoreProduct(seller_id=seller.id, product_id=product.id, requested_by_id=user.id,
                        status=StoreProductStatus.pending)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def cancel_link(db: Session, seller_id: uuid.UUID, user: User, link_id: uuid.UUID) -> StoreProduct:
    """Confirm/Store/CancelLink: a pending request is withdrawn (ask again any time)."""
    seller = _owned(db, seller_id, user)
    link = db.get(StoreProduct, link_id, with_for_update=True)
    if link is None or link.seller_id != seller.id:
        raise NotFoundError("Link request not found.", code="link_not_found")
    if link.status != StoreProductStatus.pending:
        raise AppError("Only a request waiting for approval can be cancelled.",
                       code="link_not_pending", status_code=409, title="Conflicting state")
    link.status = StoreProductStatus.cancelled
    link.decided_at = _now()
    db.commit()
    db.refresh(link)
    return link


# ------------------------------------------------------------------ analytics

@dataclass
class MonthPoint:
    month: str
    median: float | None
    category_median: float | None


@dataclass
class Theme:
    text: str
    reviews: int
    share: float


@dataclass
class Analytics:
    product_id: uuid.UUID
    name: str
    category: str | None
    figures: Figures
    months: list[MonthPoint]
    worth_it_last_month: float | None
    complaints: list[Theme]
    praise: list[Theme]
    category_products: int
    category_median: float | None
    category_worth_it: float | None
    store_answered: float | None
    category_store_answered: float | None
    recent_questions: list[dict]


def _month_starts(n: int) -> list[datetime]:
    local = _now().astimezone(MANILA)
    first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out = []
    for i in range(n - 1, -1, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            m += 12
            y -= 1
        out.append(first.replace(year=y, month=m))
    return out


def _monthly_medians(db: Session, product_ids: list[uuid.UUID],
                     starts: list[datetime]) -> list[float | None]:
    """Median stars of the reviews written in each month (reviews, not threads:
    a month's mood is what was written that month)."""
    if not product_ids:
        return [None] * len(starts)
    ends = starts[1:] + [_now()]
    out = []
    for s, e in zip(starts, ends, strict=True):
        median = db.scalar(select(func.percentile_cont(0.5).within_group(Review.star_rating.asc()))
                           .where(Review.product_id.in_(product_ids),
                                  Review.is_removed.is_(False), Review.published_at.is_not(None),
                                  Review.created_at >= s, Review.created_at < e))
        out.append(round(float(median), 2) if median is not None else None)
    return out


def _themes(db: Session, product_id: uuid.UUID) -> tuple[list[Theme], list[Theme], int]:
    latest = _latest([product_id])
    rows = db.execute(select(latest.c.pros, latest.c.cons)).all()
    total = len(rows)
    pros, cons = Counter(), Counter()
    label: dict[str, str] = {}
    for p, c in rows:
        for bag, items in ((pros, p), (cons, c)):
            seen = set()
            for item in items or []:
                text = " ".join(str(item).split())
                key = text.casefold().rstrip(".")
                if text and key not in seen:
                    seen.add(key)
                    bag[key] += 1
                    label.setdefault(key, text)

    def top(bag: Counter) -> list[Theme]:
        return [Theme(text=label[k], reviews=n, share=n / total) for k, n in bag.most_common(5)
                if n >= THEME_MIN]
    return top(cons), top(pros), total


def analytics(db: Session, seller_id: uuid.UUID, user: User, product_id: uuid.UUID) -> Analytics:
    seller = _owned(db, seller_id, user)
    link = db.scalar(select(StoreProduct).where(
        StoreProduct.seller_id == seller.id, StoreProduct.product_id == product_id,
        StoreProduct.status == StoreProductStatus.approved))
    if link is None:
        raise NotFoundError("Link this product first; its analytics show once approved.",
                            code="link_not_approved")
    product = db.get(Product, product_id)
    figures = _figures(db, [product.id])[product.id]
    peers = list(db.scalars(select(Product.id).where(
        Product.category == product.category, Product.status == ProductStatus.canonicalized,
        Product.review_count > 0))) if product.category else []
    starts = _month_starts(6)
    mine = _monthly_medians(db, [product.id], starts)
    theirs = _monthly_medians(db, peers, starts)
    months = [MonthPoint(month=s.strftime("%Y-%m"), median=a, category_median=b)
              for s, a, b in zip(starts, mine, theirs, strict=True)]
    last_month_end = starts[-1]
    then = _verdicts(db, [product.id], last_month_end).get(product.id, {})
    then_total = sum(then.values())
    worth_then = (then.get(Verdict.yes_absolutely.value, 0) / then_total
                  if then_total >= MIN_REVIEWS else None)
    complaints, praise, _ = _themes(db, product.id)
    cat_median = db.scalar(select(func.percentile_cont(0.5).within_group(
        Product.median_rating.asc())).where(Product.id.in_(peers))) if peers else None
    cat_verdicts = _verdicts(db, peers) if peers else {}
    cat_total = sum(sum(v.values()) for v in cat_verdicts.values())
    cat_worth = (sum(v.get(Verdict.yes_absolutely.value, 0) for v in cat_verdicts.values())
                 / cat_total if cat_total else None)

    def store_answered(ids: list[uuid.UUID]) -> float | None:
        if not ids:
            return None
        asked = db.scalar(select(func.count()).select_from(Question).where(
            Question.product_id.in_(ids), Question.is_removed.is_(False))) or 0
        if not asked:
            return None
        by_store = db.scalar(select(func.count(func.distinct(Answer.question_id))).join(
            Question, Question.id == Answer.question_id).where(
            Question.product_id.in_(ids), Answer.is_seller_answer.is_(True))) or 0
        return by_store / asked

    recent = db.execute(
        select(Question.id, Question.body, Question.created_at,
               select(func.count()).where(Answer.question_id == Question.id)
               .correlate(Question).scalar_subquery())
        .where(Question.product_id == product.id, Question.is_removed.is_(False))
        .order_by(Question.created_at.desc()).limit(5)).all()
    return Analytics(
        product_id=product.id, name=product.canonical_name or "Product", category=product.category,
        figures=figures, months=months, worth_it_last_month=worth_then,
        complaints=complaints, praise=praise, category_products=len(peers),
        category_median=round(float(cat_median), 2) if cat_median is not None else None,
        category_worth_it=cat_worth, store_answered=store_answered([product.id]),
        category_store_answered=store_answered(peers),
        recent_questions=[{"id": str(r[0]), "body": r[1], "created_at": r[2],
                           "answers": int(r[3] or 0)} for r in recent])


# ------------------------------------------------------------------ staff

@dataclass
class AdminLinkRow:
    id: uuid.UUID
    status: str
    seller_id: uuid.UUID
    seller_name: str
    product_id: uuid.UUID
    product_name: str
    product_category: str | None
    review_count: int
    requested_by: str | None
    requested_at: datetime
    decided_at: datetime | None
    decision_note: str | None


def admin_list(db: Session, status: str = "pending") -> list[AdminLinkRow]:
    wanted = (StoreProductStatus(status),) if status in StoreProductStatus.__members__ else LIVE
    rows = db.execute(
        select(StoreProduct, Seller, Product, User)
        .join(Seller, Seller.id == StoreProduct.seller_id)
        .join(Product, Product.id == StoreProduct.product_id)
        .outerjoin(User, User.id == StoreProduct.requested_by_id)
        .where(StoreProduct.status.in_(wanted))
        .order_by(StoreProduct.created_at).limit(200)).all()
    return [AdminLinkRow(
        id=link.id, status=link.status.value, seller_id=seller.id, seller_name=seller.display_name,
        product_id=product.id, product_name=product.canonical_name or "Product",
        product_category=product.category, review_count=product.review_count,
        requested_by=(u.display_name or (f"@{u.username}" if u.username else None)) if u else None,
        requested_at=link.created_at, decided_at=link.decided_at,
        decision_note=link.decision_note) for link, seller, product, u in rows]


def decide(db: Session, admin: User, link_id: uuid.UUID, approve: bool,
           note: str | None = None) -> StoreProduct:
    link = db.get(StoreProduct, link_id, with_for_update=True)
    if link is None:
        raise NotFoundError("Link request not found.", code="link_not_found")
    if link.status != StoreProductStatus.pending:
        raise AppError("This request was already decided or cancelled.",
                       code="link_not_pending", status_code=409, title="Conflicting state")
    seller = db.get(Seller, link.seller_id)
    if approve and (seller is None or seller.claim_status != SellerClaimStatus.claimed):
        raise AppError("The store is no longer claimed.", code="store_not_claimed",
                       status_code=409, title="Conflicting state")
    link.status = StoreProductStatus.approved if approve else StoreProductStatus.rejected
    link.decided_by_id = admin.id
    link.decided_at = _now()
    link.decision_note = (note or "").strip() or None
    product = db.get(Product, link.product_id)
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=admin.id,
                         action=ModerationAction.store_product, target_ref=link.id,
                         notes=f"store product {link.status.value}",
                         context={"seller_id": str(link.seller_id),
                                  "product_id": str(link.product_id),
                                  "decision": link.status.value}))
    if link.requested_by_id is not None:
        name = product.canonical_name if product else "the product"
        notification_service.notify(
            db, link.requested_by_id, "store_product_decided",
            f"{name} is linked to your store" if approve else f"{name} wasn't linked",
            body=link.decision_note, link=f"/seller/{link.seller_id}/products")
    db.commit()
    db.refresh(link)
    return link


def linked_products(db: Session, seller_id: uuid.UUID) -> list[Product]:
    """The store's approved products, for its public page ("Sold by")."""
    return list(db.scalars(select(Product).join(
        StoreProduct, and_(StoreProduct.product_id == Product.id,
                           StoreProduct.status == StoreProductStatus.approved))
        .where(StoreProduct.seller_id == seller_id).order_by(Product.review_count.desc())))


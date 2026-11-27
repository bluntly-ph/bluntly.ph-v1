"""The Payout screen's "Get there faster" tips, each behind its own page
(Figma 7844:9469 Answer open questions, 7843:9501 Add receipts and photos).

Read-only and for the caller only. Every figure is counted from records:

* answers: how many the member wrote this month, what answers have earned
  them (net of returns, never QA test money), and up to three open questions
  nobody has answered yet in the first category they said they care about;
* proof: what a published review earns its writer on average with a photo or
  receipt and without one, across all reviewers, and which of the member's
  own published reviews have neither. A receipt cannot be attached after
  publishing and a photo only once, within 72 hours (review_service), so each
  row says whether a photo can still be added.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.categories import CATEGORIES, UnknownCategory, normalize_category, spellings_for
from app.core.constants import MANILA
from app.models.commission import Commission
from app.models.enums import CommissionTarget
from app.models.product import Product
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.user import User
from app.services.review_service import PHOTO_SWAP_WINDOW

OPEN_QUESTIONS = 3
MISSING_PROOF = 5
ZERO = Decimal("0.00")


@dataclass
class OpenQuestion:
    id: uuid.UUID
    body: str
    product_name: str | None
    created_at: datetime


@dataclass
class MissingProof:
    review_id: uuid.UUID
    product_name: str
    product_image_url: str | None
    published_at: datetime
    #: A photo can still be added (within 72 hours of publishing, swap unused).
    can_add_photo: bool


@dataclass
class PayoutTips:
    answers_this_month: int
    earned_from_answers: Decimal
    category_label: str | None
    open_questions: list[OpenQuestion]
    average_with_proof: Decimal | None
    average_without_proof: Decimal | None
    missing_proof: list[MissingProof]


def _money(v: Decimal | None) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"))


def _month_start(now: datetime) -> datetime:
    local = now.astimezone(MANILA)
    return datetime.combine(local.date().replace(day=1), time.min, tzinfo=MANILA)


def _first_category(user: User) -> str | None:
    for raw in user.interests or []:
        try:
            slug = normalize_category(raw)
        except UnknownCategory:
            continue
        if slug:
            return slug
    return None


def _open_questions(db: Session, user: User, slug: str | None) -> list[OpenQuestion]:
    answered = select(Answer.id).where(Answer.question_id == Question.id).exists()
    stmt = (select(Question, Product.canonical_name)
            .outerjoin(Product, Product.id == Question.product_id)
            .where(Question.is_removed.is_(False), ~answered,
                   or_(Question.asker_id.is_(None), Question.asker_id != user.id)))
    if slug:
        stmt = stmt.where(Product.category.in_(spellings_for(slug)))
    rows = db.execute(stmt.order_by(Question.created_at.desc()).limit(OPEN_QUESTIONS)).all()
    return [OpenQuestion(id=q.id, body=q.body, product_name=name, created_at=q.created_at)
            for q, name in rows]


def _averages(db: Session) -> tuple[Decimal | None, Decimal | None]:
    """Average net writer earning per published review, with and without proof."""
    has_proof = or_(Review.photo_url.is_not(None), Review.receipt_key.is_not(None))
    earned = (select(Commission.review_id, func.sum(Commission.reviewer_share).label("net"))
              .where(Commission.review_id.is_not(None), Commission.is_test.is_(False))
              .group_by(Commission.review_id).subquery())
    out: list[Decimal | None] = []
    for proof in (has_proof, ~has_proof):
        count, total = db.execute(
            select(func.count(Review.id), func.coalesce(func.sum(earned.c.net), 0))
            .outerjoin(earned, earned.c.review_id == Review.id)
            .where(Review.published_at.is_not(None), Review.is_removed.is_(False), proof)).one()
        out.append(_money(Decimal(total) / count) if count else None)
    return out[0], out[1]


def _missing_proof(db: Session, user: User, now: datetime) -> list[MissingProof]:
    rows = db.execute(
        select(Review, Product.canonical_name, Product.image_url)
        .join(Product, Product.id == Review.product_id)
        .where(Review.author_id == user.id, Review.published_at.is_not(None),
               Review.is_removed.is_(False),
               and_(Review.photo_url.is_(None), Review.receipt_key.is_(None)))
        .order_by(Review.published_at.desc()).limit(MISSING_PROOF)).all()
    out = []
    for review, name, image in rows:
        published = review.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        out.append(MissingProof(
            review_id=review.id, product_name=name or "A product", product_image_url=image,
            published_at=published,
            can_add_photo=(review.photo_replaced_at is None
                           and now - published <= PHOTO_SWAP_WINDOW)))
    return out


def build(db: Session, user: User, *, now: datetime | None = None) -> PayoutTips:
    now = now or datetime.now(UTC)
    answers = int(db.scalar(
        select(func.count(Answer.id))
        .where(Answer.responder_id == user.id, Answer.created_at >= _month_start(now))) or 0)
    earned = db.scalar(
        select(func.sum(Commission.reviewer_share))
        .where(Commission.reviewer_id == user.id, Commission.is_test.is_(False),
               Commission.target_type == CommissionTarget.answer))
    slug = _first_category(user)
    questions = _open_questions(db, user, slug)
    with_proof, without_proof = _averages(db)
    return PayoutTips(
        answers_this_month=answers, earned_from_answers=_money(earned),
        category_label=CATEGORIES.get(slug) if slug else None, open_questions=questions,
        average_with_proof=with_proof, average_without_proof=without_proof,
        missing_proof=_missing_proof(db, user, now))

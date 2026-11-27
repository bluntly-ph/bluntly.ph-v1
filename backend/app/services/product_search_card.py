"""The search page's product bar (Figma Mobile Search v10B 7693:7490, Questions
v6 7718:12930 / 7724:7520, Switch sheet 7708:8117).

One public read per product, built from data the product page already shows:
the review figures (median rating, how many recommend it), the latest approved
community price, and where its questions stand. "Active now" is the number of
distinct members who asked, answered, replied or voted on this product's
questions in the last hour: counted from those rows' own timestamps, nothing
inferred.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, union
from sqlalchemy.orm import Session

from app.models.enums import PriceObservationStatus, Verdict
from app.models.product import PriceHistory, Product
from app.models.qa import Answer, AnswerReply, QAVote, Question
from app.models.review import Review

ACTIVE_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class SearchCard:
    product_id: uuid.UUID
    review_count: int
    median_rating: Decimal
    #: Share of published reviews whose verdict is "Yes, absolutely" (0-100), None without reviews.
    recommend_pct: int | None
    latest_price: Decimal | None
    latest_price_on: date | None
    questions: int
    #: Questions with a Best Answer picked.
    best_answers: int
    #: Questions nobody has answered yet ("waiting").
    unanswered: int
    active_now: int


def card(db: Session, product: Product, now: datetime | None = None) -> SearchCard:
    now = now or datetime.now(UTC)
    published = (Review.product_id == product.id, Review.published_at.is_not(None),
                 Review.is_removed.is_(False))
    total, recommend = db.execute(
        select(func.count(Review.id),
               func.count(Review.id).filter(Review.verdict == Verdict.yes_absolutely))
        .where(*published)).one()
    price = db.execute(
        select(PriceHistory.price, PriceHistory.observed_at)
        .where(PriceHistory.product_id == product.id,
               PriceHistory.status == PriceObservationStatus.approved)
        .order_by(PriceHistory.observed_at.desc(), PriceHistory.created_at.desc())
        .limit(1)).first()

    live = (Question.product_id == product.id, Question.is_removed.is_(False))
    answered = select(Answer.question_id).scalar_subquery()
    questions, best, unanswered = db.execute(
        select(func.count(Question.id),
               func.count(Question.id).filter(Question.best_answer_id.is_not(None)),
               func.count(Question.id).filter(Question.id.not_in(answered)))
        .where(*live)).one()

    since = now - ACTIVE_WINDOW
    qids = select(Question.id).where(*live)
    aids = select(Answer.id).where(Answer.question_id.in_(qids))
    people = union(
        select(Question.asker_id.label("who")).where(*live, Question.created_at >= since),
        select(Answer.responder_id).where(Answer.question_id.in_(qids), Answer.created_at >= since),
        select(AnswerReply.author_id).where(AnswerReply.answer_id.in_(aids),
                                            AnswerReply.is_removed.is_(False),
                                            AnswerReply.created_at >= since),
        select(QAVote.user_id).where(QAVote.created_at >= since,
                                     (QAVote.question_id.in_(qids)) | (QAVote.answer_id.in_(aids))),
    ).subquery()
    active = db.scalar(select(func.count()).select_from(people).where(people.c.who.is_not(None)))

    return SearchCard(
        product_id=product.id, review_count=int(total or 0),
        median_rating=Decimal(product.median_rating or 0),
        recommend_pct=round(100 * recommend / total) if total else None,
        latest_price=price[0] if price else None, latest_price_on=price[1] if price else None,
        questions=int(questions or 0), best_answers=int(best or 0),
        unanswered=int(unanswered or 0), active_now=int(active or 0))

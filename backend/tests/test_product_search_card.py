"""The search page's product bar (Figma 7693:7490 / 7718:12930 / 7708:8117):
GET /products/{id}/search-card."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.db.session import SessionLocal
from app.models.enums import (
    Platform,
    PriceObservationStatus,
    QuestionDirectedTo,
    Verdict,
    VoteDirection,
)
from app.models.product import PriceHistory, Product
from app.models.qa import Answer, QAVote, Question
from app.models.review import Review
from app.services import product_search_card
from tests.conftest import make_user, requires_db

pytestmark = requires_db


def test_search_card_counts_reviews_price_and_questions(db):
    a, b, c = make_user(db), make_user(db), make_user(db)
    product = Product(canonical_name=f"Card {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    now = datetime.now(UTC)
    for author, verdict in ((a, Verdict.yes_absolutely), (b, Verdict.yes_absolutely),
                            (c, Verdict.hard_pass)):
        db.add(Review(product_id=product.id, author_id=author.id, title="t",
                      discussion="Body text for the card review.", verdict=verdict,
                      star_rating=Decimal("4"), published_at=now))
    db.add(Review(product_id=product.id, author_id=a.id, title="draft", discussion="Not out yet.",
                  verdict=Verdict.hard_pass, star_rating=Decimal("1")))
    ok, waiting_price = PriceObservationStatus.approved, PriceObservationStatus.pending
    for price, day, status in ((Decimal("999.00"), date(2026, 9, 1), ok),
                               (Decimal("1299.00"), date(2026, 9, 20), ok),
                               (Decimal("10.00"), date(2026, 9, 30), waiting_price)):
        db.add(PriceHistory(product_id=product.id, platform=Platform.shopee, price=price,
                            observed_at=day, status=status))
    buyers = QuestionDirectedTo.buyers
    asked = Question(product_id=product.id, asker_id=a.id, body="Is it loud?", directed_to=buyers)
    waiting = Question(product_id=product.id, asker_id=b.id, body="Does it fold?",
                       directed_to=buyers)
    removed = Question(product_id=product.id, asker_id=b.id, body="Spam", directed_to=buyers,
                       is_removed=True)
    db.add_all([asked, waiting, removed])
    db.flush()
    answer = Answer(question_id=asked.id, responder_id=c.id, body="Quiet on low.")
    db.add(answer)
    db.flush()
    asked.best_answer_id = answer.id
    db.add(QAVote(user_id=b.id, answer_id=answer.id, direction=VoteDirection.up))
    db.flush()

    got = product_search_card.card(db, product, now=now + timedelta(minutes=5))
    assert (got.review_count, got.recommend_pct) == (3, 67)
    assert (got.latest_price, got.latest_price_on) == (Decimal("1299.00"), date(2026, 9, 20))
    assert (got.questions, got.best_answers, got.unanswered) == (2, 1, 1)
    assert got.active_now == 3
    later = product_search_card.card(db, product, now=now + timedelta(hours=2))
    assert later.active_now == 0


def test_search_card_route_is_public_and_404s(client):
    db = SessionLocal()
    try:
        product = Product(canonical_name=f"Card {uuid.uuid4().hex[:6]}")
        db.add(product)
        db.commit()
        pid = product.id
    finally:
        db.close()
    body = client.get(f"/api/v1/products/{pid}/search-card").json()
    assert body["review_count"] == 0 and body["recommend_pct"] is None
    assert body["questions"] == 0 and body["active_now"] == 0
    assert client.get(f"/api/v1/products/{uuid.uuid4()}/search-card").status_code == 404

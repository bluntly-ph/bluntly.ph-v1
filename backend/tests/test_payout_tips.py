"""The Payout tips pages (Figma 7844:9469, 7843:9501): GET /users/me/payout-tips.

Each test builds its own records in the rolled-back `db` session; the
site-wide averages are only checked for shape, since other rows exist.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.models.commission import Commission
from app.models.enums import (
    CommissionTarget,
    EarnEligibleStatus,
    Platform,
    QuestionDirectedTo,
    Verdict,
    VerificationStatus,
)
from app.models.product import Product
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.user import User
from app.services import payout_tips_service as tips
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db

NOW = datetime(2026, 10, 3, 4, 0, tzinfo=UTC)


def _user(db, **kw) -> User:
    u = User(email=f"pt_{uuid.uuid4().hex}@example.com", password_hash="x",
             display_name="Tips Fixture", username=f"pt_{uuid.uuid4().hex[:10]}", **kw)
    db.add(u)
    db.flush()
    return u


def _product(db, category: str | None = None) -> Product:
    p = Product(canonical_name=f"Tips Product {uuid.uuid4().hex[:6]}", category=category)
    db.add(p)
    db.flush()
    return p


def _review(db, author, *, published: datetime, photo: str | None = None) -> Review:
    r = Review(product_id=_product(db).id, author_id=author.id, title="Fixture",
               discussion="Body text for the fixture review.", verdict=Verdict.yes_absolutely,
               star_rating=D("4"), earn_eligible_status=EarnEligibleStatus.monetized,
               verification_status=VerificationStatus.unverified, published_at=published,
               photo_url=photo)
    db.add(r)
    db.flush()
    return r


def _question(db, product, asker, *, at: datetime) -> Question:
    q = Question(product_id=product.id, asker_id=asker.id,
                 body=f"Is it any good? {uuid.uuid4().hex[:6]}",
                 directed_to=QuestionDirectedTo.buyers, created_at=at)
    db.add(q)
    db.flush()
    return q


def test_answers_this_month_and_what_answers_earned(db):
    me, asker = _user(db), _user(db)
    product = _product(db, "audio")
    q = _question(db, product, asker, at=NOW - timedelta(days=40))
    this_month = Answer(question_id=q.id, responder_id=me.id, body="Yes.",
                        created_at=NOW - timedelta(days=1))
    last_month = Answer(question_id=q.id, responder_id=me.id, body="Still yes.",
                        created_at=NOW - timedelta(days=10))
    db.add_all([this_month, last_month])
    db.flush()
    for share, test in (("18.00", False), ("-3.00", False), ("50.00", True)):
        db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                          target_type=CommissionTarget.answer, answer_id=this_month.id,
                          reviewer_id=me.id, platform=Platform.shopee, currency="PHP",
                          csv_source="tips-test", row_reference=uuid.uuid4().hex,
                          cycle_month=NOW.date().replace(day=1), gross_amount=D("60"),
                          platform_share=D("0" if test else "18"), reviewer_share=D(share),
                          honesty_fund_share=D("0" if test else "18"), is_test=test,
                          created_at=NOW))
    db.flush()
    t = tips.build(db, me, now=NOW)
    # 3 October Manila: the answer on 23 September is last month's.
    assert t.answers_this_month == 1
    # Net of the return, never QA test money.
    assert t.earned_from_answers == D("15.00")


def test_open_questions_are_unanswered_in_the_members_category_and_not_their_own(db):
    me = _user(db, interests=["not-a-category", "audio"])
    asker = _user(db)
    audio, beauty = _product(db, "audio"), _product(db, "beauty")
    waiting = _question(db, audio, asker, at=NOW - timedelta(hours=2))
    answered = _question(db, audio, asker, at=NOW - timedelta(hours=1))
    db.add(Answer(question_id=answered.id, responder_id=asker.id, body="Fine."))
    mine = _question(db, audio, me, at=NOW)
    elsewhere = _question(db, beauty, asker, at=NOW)
    db.flush()
    t = tips.build(db, me, now=NOW)
    assert t.category_label == "Audio"
    ids = {q.id for q in t.open_questions}
    assert answered.id not in ids and mine.id not in ids and elsewhere.id not in ids
    assert waiting.id in ids or len(t.open_questions) == tips.OPEN_QUESTIONS
    assert len(t.open_questions) <= tips.OPEN_QUESTIONS


def test_reviews_missing_proof_say_whether_a_photo_can_still_be_added(db):
    me = _user(db)
    fresh = _review(db, me, published=NOW - timedelta(hours=5))
    old = _review(db, me, published=NOW - timedelta(days=5))
    with_photo = _review(db, me, published=NOW, photo="https://example.com/p.jpg")
    t = tips.build(db, me, now=NOW)
    rows = {m.review_id: m for m in t.missing_proof}
    assert with_photo.id not in rows
    assert rows[fresh.id].can_add_photo is True
    assert rows[old.id].can_add_photo is False
    assert [m.review_id for m in t.missing_proof][:2] == [fresh.id, old.id]
    for avg in (t.average_with_proof, t.average_without_proof):
        assert avg is None or isinstance(avg, D)


def test_endpoint_is_the_callers_own(client):
    assert client.get("/api/v1/users/me/payout-tips").status_code == 401
    _, token, _ = register_and_token(client)
    r = client.get("/api/v1/users/me/payout-tips", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["answers_this_month"] == 0 and body["missing_proof"] == []
    assert set(body) >= {"open_questions", "average_with_proof", "average_without_proof"}

"""Investigation tabs (Figma Overlay/Review/Investigate/Author 8112:17871 and
Originality 8112:17611, "Where votes came from" 8237:26485, and the answer
investigation Overlay/Answer/Investigate 8129:*, 8237:26795)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    QuestionDirectedTo,
    VoteDirection,
)
from app.models.moderation import ModerationLog
from app.models.qa import Answer, QAVote, Question
from app.models.review import Review
from app.models.traffic import ReviewFirstVoteGeoBucket
from tests.conftest import register_and_token, requires_db
from tests.test_payout_tips import _product, _review, _user
from tests.test_review_investigation import _vote

pytestmark = requires_db

NOW = datetime(2030, 5, 1, 4, 0, tzinfo=UTC)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_the_author_block_reads_votes_circle_reports_and_months(db):
    from app.services import investigation_author

    author, circle, casual = _user(db), _user(db, trust_stage=2), _user(db)
    reviews = [_review(db, author, published=NOW - timedelta(days=40 - i)) for i in range(5)]
    for r in reviews:
        _vote(db, r, circle, (r.published_at or NOW) + timedelta(minutes=2))
    _vote(db, reviews[0], casual, NOW)
    theirs = _review(db, circle, published=NOW - timedelta(days=3))
    _vote(db, theirs, author, NOW)                      # the author votes back once
    db.add(ModerationLog(action=ModerationAction.report, target_type=ModerationTargetType.review,
                         target_ref=reviews[1].id, reporter_id=casual.id))
    db.flush()

    a = investigation_author.build(db, author, kind="reviews", current_id=reviews[-1].id, now=NOW)
    assert (a.reviews, a.answers, a.items, a.helpful_votes) == (5, 0, 5, 6)
    assert a.sources[0].person.id == circle.id and a.sources[0].votes == 5
    assert round(a.sources[0].share, 2) == 0.83 and a.others_people == 0
    assert [(c.person.id, c.covered, c.back) for c in a.circle] == [(circle.id, 5, 1)]
    assert len(a.per_month) == 12 and sum(n for _, n in a.per_month) == 5
    assert len(a.scores) == 5 and a.scores[-1].current and a.gate == 0.65
    assert [(r.status) for r in a.reports] == ["open"]


def test_where_votes_came_from_is_the_first_vote_place_buckets(db):
    author = _user(db)
    review = _review(db, author, published=NOW)
    places = [("Taguig", "NCR", 2), ("Taguig", "NCR", 1), ("Cebu City", "VII", 1)] + [
        (f"Town {i}", "IV-A", 1) for i in range(5)]
    for i, (city, region, n) in enumerate(places):
        db.add(ReviewFirstVoteGeoBucket(review_id=review.id, country="PH", region=region,
                                        city=city, first_vote_count=n,
                                        bucket_start=NOW + timedelta(hours=i)))
    db.flush()
    from app.services.review_investigation import places as vote_places
    top, other_places, other_votes = vote_places(db, review.id)
    assert top[0] == ("Taguig, NCR", 3) and len(top) == 5
    assert (other_places, other_votes) == (2, 2)


def test_originality_names_the_closest_earlier_text_only(db):
    from app.services import investigation_originality

    author = _user(db)
    text = ("I use it every day on a two hour commute and it charges my phone about four "
            "times from full, with some left over for my earbuds at the end of the week.")
    first = _review(db, author, published=NOW - timedelta(days=2))
    first.discussion = text
    later = Review(product_id=first.product_id, author_id=author.id, title="Again",
                   discussion=text, verdict=first.verdict, star_rating=first.star_rating,
                   earn_eligible_status=first.earn_eligible_status,
                   verification_status=first.verification_status, published_at=NOW,
                   created_at=NOW)
    db.add(later)
    db.flush()
    o = investigation_originality.for_review(db, later)
    assert o.meaningful and o.compared >= 1
    assert o.best is not None and o.best.id == first.id and o.best.flagged
    assert o.best.href == f"/reviews/{first.id}" and o.best.score > 0.9
    # The original has nothing earlier to have copied.
    assert investigation_originality.for_review(db, first).best is None


def test_answer_investigation_flags_the_circle_and_recomputes_the_score(db):
    from app.services import answer_investigation

    asker, responder = _user(db), _user(db)
    circle, honest = _user(db, trust_stage=2), _user(db, trust_stage=2)
    product = _product(db)
    answers = []
    for i in range(5):
        q = Question(product_id=product.id, asker_id=asker.id, body=f"Q{i} {uuid.uuid4().hex}",
                     directed_to=QuestionDirectedTo.buyers,
                     created_at=NOW - timedelta(days=10 - i))
        db.add(q)
        db.flush()
        a = Answer(question_id=q.id, responder_id=responder.id, body=f"Answer {i}",
                   created_at=NOW - timedelta(days=10 - i))
        db.add(a)
        db.flush()
        answers.append(a)
    target = answers[-1]
    for a in answers:
        db.add(QAVote(user_id=circle.id, answer_id=a.id, direction=VoteDirection.up,
                      created_at=a.created_at + timedelta(minutes=1)))
    db.add(QAVote(user_id=honest.id, answer_id=target.id, direction=VoteDirection.down,
                  created_at=target.created_at + timedelta(hours=3)))
    db.flush()

    i = answer_investigation.build(db, target)
    assert (i.votes_total, i.up, i.down, i.flagged, i.first_10_min) == (2, 1, 1, 1, 1)
    row = {v.voter_id: v for v in i.voters}
    assert row[circle.id].flagged and "voting_circle" in [s.kind for s in row[circle.id].signals]
    assert not row[honest.id].flagged and row[honest.id].vote == "down"
    assert i.history_size == 5 and row[circle.id].agreement == 5
    assert i.score_without_flagged < i.score_all or i.score_all == 0
    assert i.about == product.canonical_name and not i.is_best


def test_answer_endpoints_are_staff_only_and_unmark_best_is_audited(client, db):
    _, asker, _ = register_and_token(client)
    _, helper, _ = register_and_token(client)
    _, member, _ = register_and_token(client)
    admin_id, admin, _ = register_and_token(client, role="administrator")
    pid = client.post("/api/v1/products", headers=_h(asker), json={
        "name": f"Investigate fixture {uuid.uuid4().hex[:8]}",
        "category": "electronics"}).json()["id"]
    q = client.post("/api/v1/questions", headers=_h(asker),
                    json={"product_id": pid, "body": "Does it rattle at full speed?"}).json()
    a = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_h(helper),
                    json={"body": "Not mine, even after a month.", "rating": 4}).json()
    assert client.post(f"/api/v1/questions/{q['id']}/answers/{a['id']}/best",
                       headers=_h(asker)).status_code == 200

    base = f"/api/v1/admin/answers/{a['id']}"
    for path in ("/investigation", "/investigation/author", "/investigation/originality"):
        assert client.get(base + path, headers=_h(member)).status_code == 403
        assert client.get(base + path, headers=_h(admin)).status_code == 200, path
    body = client.get(base + "/investigation", headers=_h(admin)).json()
    assert body["is_best"] and body["picked_by_asker"] and body["question"].startswith("Does it")

    assert client.post(base + "/unmark-best", headers=_h(member),
                       json={"note": "Voting circle."}).status_code == 403
    assert client.post(base + "/unmark-best", headers=_h(admin),
                       json={"note": "Voting circle."}).status_code == 204
    after = client.get(f"/api/v1/questions/{q['id']}").json()
    assert after["best_answer_id"] is None
    assert client.post(base + "/unmark-best", headers=_h(admin),
                       json={"note": "Again."}).status_code == 409
    db.expire_all()
    from sqlalchemy import select
    log = db.scalars(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.override,
        ModerationLog.target_ref == uuid.UUID(a["id"]))).one()
    assert str(log.moderator_id) == admin_id and "Voting circle." in log.notes

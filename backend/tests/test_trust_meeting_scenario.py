"""The Honesty Score a member sees (dev/QA sync 2026-09-29, ENG-0929-H).

At the meeting a tester's score read 21 with 3 up-votes and 1 down-vote on
their one review, 12 after the vote became "2-2", and 15 once the down-vote
was removed; a comment changed nothing. The team called the score
percentile-based. The code (ADR-003, ADR-014) computes it as a fixed formula:

    0.60 x (100 x Wilson lower bound of helpful / all votes)
  + min(25, 10 x log10(1 + verified reviews))
  + min(15, 3 x Best Answers) - 15 x strikes, clamped to 0..100

These tests pin THAT formula at the three vote states seen, and pin that
comments are not an input. They define nothing new: the formula is
`app/services/trust.py`, and Zient's own calculation document is still owed.
"""

from __future__ import annotations

import uuid

import pytest

from app.services.trust import helpfulness_score, reputation_score
from tests.conftest import register_and_token, register_commenter, requires_db


@pytest.mark.parametrize(("helpful", "unhelpful", "shown"), [
    (3, 1, 21),   # "naka 21 siya ... 3 up votes at 1 down vote"
    (2, 2, 12),   # "down vote yan, 2-2 ... 12"
    (2, 1, 15),   # "pag inalis ko yung downvote ko, magiging 15"
])
def test_the_implemented_formula_gives_the_scores_seen_at_the_meeting(helpful, unhelpful, shown):
    score = reputation_score(helpfulness_score(helpful, unhelpful), verified_review_count=1,
                             best_answer_count=0, strikes=0)
    assert round(score) == shown


def test_the_formula_is_fixed_not_a_percentile_of_other_members():
    # The same record scores the same whoever else is on the platform: there
    # is no population in the inputs at all.
    one = reputation_score(helpfulness_score(3, 1), 1, 0, 0)
    assert one == reputation_score(helpfulness_score(3, 1), 1, 0, 0)
    # And every component is bounded as ADR-003 says.
    assert reputation_score(100.0, 10_000, 1_000, 0) == 100.0
    assert reputation_score(helpfulness_score(3, 1), 1, 0, 2) == 0.0


@requires_db
def test_a_comment_does_not_move_the_authors_score(client, db):
    from app.models.user import User
    from app.services.trust_service import recompute_user_trust
    from tests.test_votes_api import make_published_review

    author_id, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    auth = {"Authorization": f"Bearer {author}"}
    rid, _ = make_published_review(client, auth, {"Authorization": f"Bearer {admin}"},
                                   name=f"TrustComment {uuid.uuid4().hex[:6]}")

    def score() -> float:
        db.expire_all()
        recompute_user_trust(db, uuid.UUID(author_id))
        db.commit()
        return float(db.get(User, uuid.UUID(author_id)).reputation_score or 0)

    before = score()
    _, commenter, _ = register_commenter(client)
    res = client.post(f"/api/v1/reviews/{rid}/comments",
                      headers={"Authorization": f"Bearer {commenter}"},
                      json={"body": "How long did the battery last for you?"})
    assert res.status_code == 201, res.text
    assert score() == before

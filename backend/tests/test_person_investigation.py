"""People investigation (Figma Screen/Admin/People/Person, meeting 2026-10-02).

Asserted on fixtures this test creates, so the shared database does not matter.
"""

from __future__ import annotations

import uuid

from app.models.enums import (
    ModerationAction,
    ModerationReason,
    ModerationTargetType,
    ProductStatus,
    Verdict,
    VerificationStatus,
    VoteDirection,
)
from app.services import person_investigation_service as svc
from tests.conftest import make_user, register_and_token, requires_db


def _review(db, author, product):
    from app.models.review import Review

    r = Review(product_id=product.id, author_id=author.id, title="Fixture", discussion="Body",
               verdict=Verdict.yes_absolutely, star_rating=4,
               verification_status=VerificationStatus.unverified)
    db.add(r)
    db.flush()
    return r


def _vote(db, voter, review, direction=VoteDirection.up):
    from app.models.vote import ReviewVote

    db.add(ReviewVote(review_id=review.id, voter_id=voter.id, vote=direction))
    db.flush()


@requires_db
def test_a_mutual_pair_shows_reciprocity_and_links_to_the_exact_review(db):
    from app.models.product import Product

    product = Product(canonical_name=f"Fixture {uuid.uuid4().hex[:6]}",
                      status=ProductStatus.canonicalized)
    db.add(product)
    db.flush()
    jun, paolo, carla = make_user(db), make_user(db), make_user(db)
    jun_review, paolo_review, carla_review = (_review(db, u, product) for u in (jun, paolo, carla))
    _vote(db, jun, paolo_review)          # Jun up-votes Paolo...
    _vote(db, paolo, jun_review)          # ...and Paolo returns it.
    _vote(db, jun, carla_review, VoteDirection.down)

    inv = svc.investigate(db, jun.id)
    by_id = {i.person.id: i for i in inv.interactions}
    assert by_id[paolo.id].up == 1 and by_id[paolo.id].up_back == 1
    assert by_id[paolo.id].reciprocity_pct == 100.0, "every up-vote returned"
    assert by_id[paolo.id].same_day == 1
    assert by_id[carla.id].down == 1 and by_id[carla.id].reciprocity_pct == 0.0
    assert inv.votes_total == 2 and inv.votes_up == 1 and inv.votes_down == 1
    hrefs = {a.href for a in inv.activity if a.kind.startswith("vote_")}
    assert f"/reviews/{paolo_review.id}" in hrefs


@requires_db
def test_reports_against_and_staff_actions_are_listed(db):
    from app.models.moderation import ModerationLog
    from app.models.product import Product

    product = Product(canonical_name=f"Fixture {uuid.uuid4().hex[:6]}",
                      status=ProductStatus.canonicalized)
    db.add(product)
    db.flush()
    person, reporter = make_user(db), make_user(db)
    review = _review(db, person, product)
    db.add(ModerationLog(action=ModerationAction.report, target_type=ModerationTargetType.review,
                         target_ref=review.id, reporter_id=reporter.id,
                         reason=ModerationReason.spam))
    db.add(ModerationLog(action=ModerationAction.unpublish,
                         target_type=ModerationTargetType.review, target_ref=review.id))
    db.add(ModerationLog(action=ModerationAction.receipt_view,
                         target_type=ModerationTargetType.review, target_ref=review.id))
    db.flush()

    inv = svc.investigate(db, person.id)
    assert inv.reports_against == 1 and inv.reports_filed == 0
    assert [r.direction for r in inv.reports] == ["received"]
    assert [m.action for m in inv.moderation] == ["unpublish"], \
        "a receipt view is an audit record, not a moderation action"
    assert inv.takedowns == 1


@requires_db
def test_linked_accounts_are_only_recorded_links(db):
    shared = f"pp_{uuid.uuid4().hex}@example.com"
    person = make_user(db, payout_account=shared)
    twin = make_user(db, payout_account=shared)
    make_user(db)  # unrelated
    inv = svc.investigate(db, person.id)
    assert [(link.person.id, link.basis) for link in inv.linked] == [
        (twin.id, "shared_payout_account")]
    assert all(link.basis in ("shared_network", "shared_payout_account") for link in inv.linked)


@requires_db
def test_the_endpoint_is_staff_only_and_404s_an_unknown_member(client):
    _, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    target_id, _, _ = register_and_token(client)
    url = f"/api/v1/admin/people/{target_id}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": f"Bearer {member}"}).status_code == 403
    ok = client.get(url, headers={"Authorization": f"Bearer {admin}"}, params={"range": "6M"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["person"]["status"] == "active" and len(body["daily"]) == 183
    assert "payout_account" not in str(body), "the destination itself is never returned"
    missing = client.get(f"/api/v1/admin/people/{uuid.uuid4()}",
                         headers={"Authorization": f"Bearer {admin}"})
    assert missing.status_code == 404

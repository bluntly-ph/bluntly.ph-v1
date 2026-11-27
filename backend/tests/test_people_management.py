"""People management beyond the investigation (Figma Menu/Person/Actions
8010:12514, Menu/People/Sort 7999:11850 and Filter 7999:11860): suspending a
member account, and the People list's sort and stage filter."""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models.enums import ModerationAction
from app.models.moderation import ModerationLog
from app.models.user import User
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _suspend(client, token: str, uid: str, suspended: bool = True,
             reason: str = "Vote ring, upheld."):
    return client.put(f"/api/v1/admin/people/{uid}/suspension", headers=_auth(token),
                      json={"suspended": suspended, "reason": reason})


def test_only_a_super_admin_suspends_and_it_signs_the_member_out(client):
    member_id, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    root_id, root, _ = register_and_token(client, role="super_admin")

    assert _suspend(client, member, member_id).status_code == 403
    assert _suspend(client, admin, member_id).status_code == 403
    assert _suspend(client, root, member_id, reason="").status_code == 422

    done = _suspend(client, root, member_id)
    assert done.status_code == 200, done.text
    assert done.json()["suspended"] is True
    # A suspended account's token no longer works.
    assert client.get("/api/v1/auth/me", headers=_auth(member)).status_code in (401, 403)
    person = client.get(f"/api/v1/admin/people/{member_id}", headers=_auth(admin)).json()
    assert person["person"]["status"] == "suspended"

    back = _suspend(client, root, member_id, suspended=False, reason="Cleared on appeal.")
    assert back.status_code == 200 and back.json()["suspended"] is False
    assert client.get("/api/v1/auth/me", headers=_auth(member)).status_code == 200

    db = SessionLocal()
    try:
        logs = (db.query(ModerationLog)
                .filter(ModerationLog.target_ref == uuid.UUID(member_id))
                .order_by(ModerationLog.created_at).all())
        root_uuid = uuid.UUID(root_id)
        trail = [(lg.action, lg.moderator_id, lg.target_type.value, lg.notes,
                  lg.created_at is not None) for lg in logs][-2:]
    finally:
        db.close()
    # Audited like every staff action: who, on whom, why, when.
    assert trail == [
        (ModerationAction.suspend, root_uuid, "user", "Vote ring, upheld.", True),
        (ModerationAction.restore, root_uuid, "user", "Cleared on appeal.", True),
    ]

    # Never yourself, never a staff account (demote it in Users first).
    assert _suspend(client, root, root_id).status_code == 422
    admin_id = client.get("/api/v1/auth/me", headers=_auth(admin)).json()["id"]
    refused = _suspend(client, root, admin_id)
    assert refused.status_code == 422 and refused.json()["code"] == "staff_account"
    assert _suspend(client, root, str(uuid.uuid4())).status_code == 404


def test_a_seller_cannot_suspend_and_a_suspended_voter_stops_counting(client):
    """A claimed seller has no staff power; a suspended member's past upvotes
    leave the earnings gate while suspended and return on reinstatement."""
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.models.enums import Verdict
    from app.models.product import Product
    from app.models.review import Review
    from app.services import earn_gate
    from tests.test_business_rules_api import _claimed_seller

    _, seller_token, _, _ = _claimed_seller(client)
    author_id, _, _ = register_and_token(client)
    voter_id, voter, _ = register_and_token(client)
    _, root, _ = register_and_token(client, role="super_admin")
    assert _suspend(client, seller_token, voter_id).status_code == 403

    db = SessionLocal()
    try:
        v = db.get(User, uuid.UUID(voter_id))
        v.trust_stage, v.reputation_score = 3, Decimal("80")
        v.created_at = datetime.now(UTC) - timedelta(days=400)
        product = Product(canonical_name=f"Gate {uuid.uuid4().hex[:6]}")
        db.add(product)
        db.flush()
        review = Review(product_id=product.id, author_id=uuid.UUID(author_id), title="Gate",
                        discussion="Body text for the gate review.",
                        verdict=Verdict.yes_absolutely, star_rating=Decimal("5"),
                        published_at=datetime.now(UTC))
        db.add(review)
        db.commit()
        rid = review.id
    finally:
        db.close()
    voted = client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(voter), json={"vote": "up"})
    assert voted.status_code in (200, 201), voted.text

    def positive() -> float:
        db = SessionLocal()
        try:
            return earn_gate.gate_state(db, rid).effective_positive
        finally:
            db.close()

    counted = positive()
    assert counted > 0
    assert _suspend(client, root, voter_id).status_code == 200
    assert positive() == 0
    assert _suspend(client, root, voter_id, suspended=False, reason="Cleared.").status_code == 200
    assert positive() == counted


def test_people_list_sorts_and_filters_by_stage(client):
    _, admin, _ = register_and_token(client, role="administrator")
    tag = uuid.uuid4().hex[:8]
    ids = []
    db = SessionLocal()
    try:
        for i, stage in enumerate((2, 2, 4)):
            uid, _, _ = register_and_token(client)
            user = db.get(User, uuid.UUID(uid))
            user.display_name = f"Sorter {tag} {i}"
            user.trust_stage = stage
            ids.append(uid)
        db.commit()
    finally:
        db.close()

    base = f"/api/v1/admin/reviewers?scope=members&q=Sorter%20{tag}"
    page = client.get(base, headers=_auth(admin)).json()
    assert page["total"] == 3 and page["stages"] == {"2": 2, "4": 1}
    two = client.get(f"{base}&stage=2", headers=_auth(admin)).json()
    assert two["total"] == 2 and two["stages"] == {"2": 2, "4": 1}

    def order(sort: str) -> list[str]:
        rows = client.get(f"{base}&sort={sort}", headers=_auth(admin)).json()["rows"]
        return [r["id"] for r in rows]

    newest, oldest = order("newest"), order("oldest")
    assert newest == ids[::-1] and oldest == ids
    assert client.get(f"{base}&sort=bogus", headers=_auth(admin)).status_code == 422

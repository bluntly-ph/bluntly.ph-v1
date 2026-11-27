"""Legacy rejection notices are re-pointed at their review (QA-054, round 2).

The tester's retest opened a rejection notice written on 2026-09-22 by the
pre-release code, which linked to /dashboard/history. Migration 0053 repairs
such rows — but only when the moderator's `reject` log shares the notice's
exact instant AND targets the recipient's own review, so no one can be pointed
at somebody else's review.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from tests.conftest import register_and_token, requires_db

_MIGRATION = (Path(__file__).resolve().parents[1] / "alembic" / "versions"
              / "0053_repair_rejection_links.py")


def _repair_sql() -> str:
    spec = importlib.util.spec_from_file_location("m0053", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.REPAIR_SQL


def _review(client, token: str) -> str:
    h = {"Authorization": f"Bearer {token}"}
    pid = client.post("/api/v1/products", headers=h, json={
        "name": f"Repair fixture {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
    r = client.post("/api/v1/reviews", headers=h, json={
        "product_id": pid, "title": "Fine", "discussion": "Used it for a month.",
        "verdict": "yes_absolutely", "star_rating": 4})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@requires_db
def test_a_legacy_rejection_notice_is_repointed_only_at_its_own_review(client):
    from app.db.session import SessionLocal
    from app.models.enums import ModerationAction, ModerationTargetType
    from app.models.moderation import ModerationLog
    from app.models.notification import Notification

    author_id, author_token, _ = register_and_token(client)
    other_id, _, _ = register_and_token(client)
    rid = _review(client, author_token)
    when = datetime.now(UTC).replace(microsecond=123456)

    db = SessionLocal()
    try:
        mine = Notification(user_id=uuid.UUID(author_id), kind="review_rejected",
                            title="Your review was rejected", link="/dashboard/history",
                            created_at=when)
        # Same instant, but the rejected review is not this user's: must not move.
        decoy = Notification(user_id=uuid.UUID(other_id), kind="review_rejected",
                             title="Your review was rejected", link="/dashboard/history",
                             created_at=when)
        db.add_all([mine, decoy, ModerationLog(
            target_type=ModerationTargetType.review, target_ref=uuid.UUID(rid),
            action=ModerationAction.reject, created_at=when)])
        db.commit()
        mine_id, decoy_id = mine.id, decoy.id

        db.execute(text(_repair_sql()))
        db.commit()
        db.expire_all()

        assert db.get(Notification, mine_id).link == f"/reviews/{rid}"
        assert db.get(Notification, decoy_id).link == "/dashboard/history"

        # Idempotent.
        db.execute(text(_repair_sql()))
        db.commit()
        db.expire_all()
        assert db.get(Notification, mine_id).link == f"/reviews/{rid}"
    finally:
        db.close()


@requires_db
def test_a_new_rejection_notice_already_links_to_the_review(client):
    """The live path: rejecting writes /reviews/<id>, and the review stays public."""
    _, author_token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    rid = _review(client, author_token)
    ah = {"Authorization": f"Bearer {author_token}"}

    rejected = client.post(f"/api/v1/admin/reviews/{rid}/reject",
                           headers={"Authorization": f"Bearer {mod_token}"},
                           json={"reason": "Photo is a stock image."})
    assert rejected.status_code == 200, rejected.text

    notes = client.get("/api/v1/notifications", headers=ah).json()
    notice = next(n for n in notes if n["kind"] == "earnings_rejected")
    assert notice["link"] == f"/reviews/{rid}"
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200

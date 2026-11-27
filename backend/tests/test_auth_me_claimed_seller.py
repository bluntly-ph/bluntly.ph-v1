"""/auth/me carries the account's own §9 bar (QA-027/043, round 2).

The UI leaves out vote controls a claimed seller may not use; it learns that
from the caller's own profile. Enforcement stays in the API (vote_service).
"""

from __future__ import annotations

import uuid

from tests.conftest import register_and_token, requires_db


@requires_db
def test_me_reports_whether_the_caller_is_a_claimed_seller(client):
    from app.db.session import SessionLocal
    from app.models.user import User

    uid, token, _ = register_and_token(client)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=h).json()["is_claimed_seller"] is False

    db = SessionLocal()
    try:
        db.get(User, uuid.UUID(uid)).is_claimed_seller = True
        db.commit()
    finally:
        db.close()

    assert client.get("/api/v1/auth/me", headers=h).json()["is_claimed_seller"] is True

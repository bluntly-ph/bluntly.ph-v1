"""An administrator's Honesty Score override (0095, owner 2026-10-05).

effective = override if set else computed; users.reputation_score is the
effective score every reader uses. Set / change / clear need a reason and are
audited. The trust stage is not derived from the score and does not move.
The Admin People API carries computed, override, effective and the photo.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.user import User
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _put(client, token: str, uid: str, score, reason: str = "Verified out-of-band evidence."):
    return client.put(f"/api/v1/admin/people/{uid}/trust-score", headers=_auth(token),
                      json={"score": score, "reason": reason})


def _set_computed(uid: str, value: str, stage: int = 2) -> None:
    with SessionLocal() as db:
        u = db.get(User, uuid.UUID(uid))
        u.computed_reputation_score = Decimal(value)
        u.reputation_score = Decimal(value)
        u.trust_stage = stage
        db.commit()


def _audits(uid: str) -> list[ModerationLog]:
    with SessionLocal() as db:
        return list(db.scalars(select(ModerationLog).where(
            ModerationLog.target_type == ModerationTargetType.user,
            ModerationLog.target_ref == uuid.UUID(uid),
            ModerationLog.action == ModerationAction.override,
        ).order_by(ModerationLog.created_at)))


def test_set_change_and_clear_with_reasons_and_an_audit_row_each(client):
    uid, _, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _set_computed(uid, "42.50")

    first = _put(client, admin, uid, 80)
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["computed_score"], body["score_override"], body["effective_score"]) == (
        "42.50", "80.00", "80.00")
    assert body["is_score_overridden"] is True
    assert body["score_override_reason"] == "Verified out-of-band evidence."
    assert body["score_overridden_at"] and body["score_overridden_by"]

    changed = _put(client, admin, uid, 65.255, reason="Second look at the votes.")
    assert changed.json()["effective_score"] == "65.26"                 # two decimals

    cleared = _put(client, admin, uid, None, reason="Evidence withdrawn.")
    body = cleared.json()
    assert body["is_score_overridden"] is False and body["score_override"] is None
    assert body["effective_score"] == "42.50"                           # back to computed
    assert body["score_override_reason"] is None

    rows = _audits(uid)
    assert [r.context["change"] for r in rows] == ["set", "change", "clear"]
    assert rows[0].context["effective_before"] == "42.50"
    assert rows[0].context["override_after"] == "80.00"
    assert rows[2].context["effective_after"] == "42.50"
    assert rows[2].notes.endswith("Evidence withdrawn.")
    # A repeat of the same value is a no-op: no new audit row.
    _put(client, admin, uid, None, reason="Still nothing to override.")
    assert len(_audits(uid)) == 3


def test_validation_and_permissions(client):
    uid, member, _ = register_and_token(client)
    admin_id, admin, _ = register_and_token(client, role="administrator")
    _, root, _ = register_and_token(client, role="super_admin")

    assert _put(client, member, uid, 50).status_code == 403            # members cannot
    for bad in (-1, 100.01, 150):
        res = _put(client, admin, uid, bad)
        assert res.status_code == 422 and res.json()["code"] == "score_out_of_range", bad
    assert _put(client, admin, uid, 50, reason="").status_code == 422   # reason required
    assert _put(client, admin, uid, 50, reason="  a ").json()["code"] == "reason_required"
    assert _put(client, admin, admin_id, 99).json()["code"] == "self_decision"
    assert _put(client, admin, str(uuid.uuid4()), 50).status_code == 404
    assert _put(client, admin, uid, 0).json()["effective_score"] == "0.00"      # bounds
    assert _put(client, root, uid, 100).json()["effective_score"] == "100.00"  # super admin too
    assert _audits(uid) and len(_audits(uid)) == 2                      # refusals left none


def test_the_algorithm_keeps_computing_under_an_override(client):
    """A recompute updates the computed score and keeps the override in force;
    clearing returns to the freshly computed value. The stage is untouched."""
    from app.services.trust_service import recompute_user_trust

    uid, _, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _set_computed(uid, "33.00", stage=1)
    _put(client, admin, uid, 90)
    with SessionLocal() as db:
        u = db.get(User, uuid.UUID(uid))
        u.computed_reputation_score = Decimal("12.00")                  # stale on purpose
        db.commit()
        recompute_user_trust(db, u.id)
        db.commit()
        db.refresh(u)
        computed = u.computed_reputation_score
        assert u.reputation_score == Decimal("90.00")                   # override stands
        assert computed != Decimal("12.00")                              # recomputed
    cleared = _put(client, admin, uid, None, reason="Back to the algorithm.")
    assert cleared.json()["effective_score"] == str(computed)


def test_the_stage_does_not_follow_the_score(client):
    uid, _, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _set_computed(uid, "20.00", stage=2)
    _put(client, admin, uid, 100)
    person = client.get(f"/api/v1/admin/people/{uid}", headers=_auth(admin)).json()["person"]
    assert person["trust_stage"] == 2 and person["trust_level_name"] == "Verified Buyer"
    assert person["reputation_score"] == "100.00"


def test_admin_people_api_fields_and_profile_photo(client):
    with_photo, _, _ = register_and_token(client)
    without, _, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    photo = "https://cdn.example.test/avatars/me.jpg"
    with SessionLocal() as db:
        db.get(User, uuid.UUID(with_photo)).avatar_url = photo
        db.commit()
    _set_computed(without, "55.00")
    _put(client, admin, without, 70)

    a = client.get(f"/api/v1/admin/people/{with_photo}", headers=_auth(admin)).json()["person"]
    assert a["avatar_url"] == photo
    assert a["is_score_overridden"] is False and a["score_override"] is None
    b = client.get(f"/api/v1/admin/people/{without}", headers=_auth(admin)).json()["person"]
    assert b["avatar_url"] is None
    assert (b["computed_score"], b["score_override"], b["reputation_score"]) == (
        "55.00", "70.00", "70.00")
    assert b["is_score_overridden"] is True and b["score_override_reason"]

    rows = {r["id"]: r for r in client.get(
        "/api/v1/admin/reviewers", headers=_auth(admin),
        params={"scope": "everyone", "sort": "newest", "limit": 50}).json()["rows"]}
    assert rows[with_photo]["avatar_url"] == photo
    assert rows[without]["avatar_url"] is None
    assert (rows[without]["computed_score"], rows[without]["score_override"],
            rows[without]["reputation_score"], rows[without]["is_score_overridden"]) == (
        "55.00", "70.00", "70.00", True)

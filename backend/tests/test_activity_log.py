"""The admin Activity log (Figma Screen/Admin/ActivityLog 8074:16245): the audit
log filtered by person / type / target / range / search, rows named in words,
the side-card summary, the CSV export and Run now (Confirm/Jobs/RunNow)."""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models.enums import ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed(admin_id: str, member_id: str, tag: str) -> None:
    db = SessionLocal()
    try:
        db.add_all([
            ModerationLog(moderator_id=uuid.UUID(admin_id),
                          action=ModerationAction.investigation_set,
                          target_type=ModerationTargetType.user, target_ref=uuid.UUID(member_id),
                          notes=f"voting ring {tag}"),
            ModerationLog(moderator_id=uuid.UUID(admin_id), action=ModerationAction.receipt_view,
                          target_type=ModerationTargetType.user, target_ref=uuid.UUID(member_id),
                          notes=f"proof {tag}"),
            ModerationLog(moderator_id=None, action=ModerationAction.escalate,
                          target_type=ModerationTargetType.user, target_ref=uuid.UUID(member_id),
                          notes=f"system {tag}"),
        ])
        db.commit()
    finally:
        db.close()


def test_activity_filters_label_and_summarise(client):
    member_id, _, _ = register_and_token(client)
    admin_id, admin, _ = register_and_token(client, role="administrator")
    tag = uuid.uuid4().hex[:8]
    _seed(admin_id, member_id, tag)

    page = client.get(f"/api/v1/admin/activity?q={tag}&range=today", headers=_auth(admin)).json()
    assert page["total"] == 3
    groups = {r["action"]: r["group"] for r in page["rows"]}
    assert groups == {"investigation_set": "moderation", "receipt_view": "privacy",
                      "escalate": "moderation"}
    mine = [r for r in page["rows"] if r["actor_id"] == admin_id]
    assert len(mine) == 2 and all(r["target_label"] == "Tester" for r in mine)
    assert mine[0]["href"] == f"/admin/people/{member_id}"

    by = lambda qs: client.get(f"/api/v1/admin/activity?q={tag}&{qs}",  # noqa: E731
                               headers=_auth(admin)).json()["total"]
    assert by(f"actor={admin_id}") == 2
    assert by("actor=system") == 1
    assert by("action=privacy") == 1
    assert by("action=investigation_set") == 1
    assert by("target=review") == 0
    for bad in ("action=nope_nope", "actor=bogus"):
        assert client.get(f"/api/v1/admin/activity?{bad}", headers=_auth(admin)).status_code == 422

    summary = client.get("/api/v1/admin/activity/summary", headers=_auth(admin)).json()
    assert summary["by_type"]["privacy"] >= 1 and summary["by_type"]["system"] >= 1
    assert summary["today_total"] == sum(summary["by_type"].values())
    counts = [t["count"] for t in summary["team_today"]]
    assert counts and counts == sorted(counts, reverse=True)
    assert any(v["target"] == "Tester" for v in summary["receipt_views"])

    csv = client.get(f"/api/v1/admin/activity.csv?q={tag}&range=today", headers=_auth(admin))
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.strip().splitlines()
    assert lines[0].startswith("when,type,action,by") and len(lines) == 4
    assert any(",System," in line for line in lines[1:])


def test_activity_is_staff_only_and_run_now_respects_roles(client):
    _, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    for path in ("/api/v1/admin/activity", "/api/v1/admin/activity/summary",
                 "/api/v1/admin/activity.csv"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=_auth(member)).status_code == 403
    assert client.post("/api/v1/admin/jobs/priority_tiers/run",
                       headers=_auth(member)).status_code == 403
    # Money and data-deletion jobs are the Super Admin's to run by hand.
    for job in ("honesty_fund_distribution", "schedule_payouts", "pii_retention"):
        refused = client.post(f"/api/v1/admin/jobs/{job}/run", headers=_auth(admin))
        assert refused.status_code == 403 and refused.json()["code"] == "super_admin_only"
    assert client.post("/api/v1/admin/jobs/nope/run", headers=_auth(admin)).status_code == 404
    ran = client.post("/api/v1/admin/jobs/priority_tiers/run", headers=_auth(admin))
    assert ran.status_code == 200, ran.text
    assert ran.json()["status"] in {"ok", "continuing", "skipped_not_due",
                                    "skipped_already_completed", "skipped_already_running"}


def test_answers_store_reviews_and_inbox_events_are_named(client):
    """An answer, a store review and an Inbox conversation read as what they are
    (with a link), not as "picked a Best Answer on" + nothing, or a bare "—"."""
    from tests.conftest import claim_body

    _, asker, _ = register_and_token(client)
    _, writer, _ = register_and_token(client)
    admin_id, admin, _ = register_and_token(client, role="administrator")
    tag = uuid.uuid4().hex[:8]
    store = client.post("/api/v1/sellers", headers=_auth(asker), json={
        "display_name": f"Lamp Store {tag}", "platform": "shopee"}).json()
    q = client.post("/api/v1/questions", headers=_auth(asker), json={
        "seller_id": store["id"], "body": f"Which charger fits the {tag} lamp?"}).json()
    a = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_auth(writer),
                    json={"body": "The 20 W USB-C one."}).json()
    sr = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(writer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 4,
        "packaging_quality": 4, "overall_rating": 4, "would_recommend": True}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(asker),
                        json=claim_body(shop_name=store["display_name"])).json()
    assert client.post(f"/api/v1/cases/claim/{claim['id']}/messages", headers=_auth(admin),
                       json={"body": "Send the permit?"}).status_code == 201
    conv = next(c for c in client.get("/api/v1/conversations", headers=_auth(asker)).json()[
        "items"] if c["topic"] == "claim")
    db = SessionLocal()
    try:
        db.add_all([
            ModerationLog(moderator_id=uuid.UUID(admin_id),
                          action=ModerationAction.best_answer_pick,
                          target_type=ModerationTargetType.answer,
                          target_ref=uuid.UUID(a["id"]), notes=f"pick {tag}"),
            ModerationLog(moderator_id=uuid.UUID(admin_id), action=ModerationAction.remove,
                          target_type=ModerationTargetType.seller_review,
                          target_ref=uuid.UUID(sr["id"]), notes=f"remove {tag}"),
            ModerationLog(moderator_id=uuid.UUID(admin_id), action=ModerationAction.conversation,
                          target_ref=uuid.UUID(conv["id"]),
                          notes="conversation moved_to_support", context={"tag": tag}),
        ])
        db.commit()
    finally:
        db.close()
    rows = client.get(f"/api/v1/admin/activity?actor={admin_id}&range=today&limit=50",
                      headers=_auth(admin)).json()["rows"]
    by = {r["action"]: r for r in rows}
    assert by["best_answer_pick"]["target_label"].startswith("an answer to “Which charger fits")
    assert by["best_answer_pick"]["href"] == f"/questions/{q['id']}"
    assert by["remove"]["target_label"] == f"a review of Lamp Store {tag}"
    assert by["remove"]["href"] == f"/sellers/{store['id']}#review-{sr['id']}"
    assert by["conversation"]["target_label"].startswith(conv["reference"] + " · ")
    assert by["conversation"]["href"] == f"/admin/inbox?c={conv['id']}"

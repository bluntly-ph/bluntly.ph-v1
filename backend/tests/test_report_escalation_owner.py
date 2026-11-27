"""An escalation has an owner and stays findable (MQA-005), its activity entry
says what happened and opens the report (MQA-006, MQA-016), and price decisions
are in the activity log (MQA-008)."""

from __future__ import annotations

from app.db.session import SessionLocal
from app.models.notification import Notification
from tests.conftest import all_report_queue_items, register_and_token, requires_db
from tests.test_escalation_behaviour import _auth, _reported

pytestmark = requires_db


def _decide(client, headers, report_id, resolution, notes=None):
    return client.post(f"/api/v1/admin/reports/{report_id}/decision", headers=headers,
                       json={"resolution": resolution, "notes": notes})


def test_an_escalated_report_goes_to_the_super_admins_who_decide_it(client):
    rid, report_id, admin = _reported(client, "EscalateOwner")
    super_id, super_token, _ = register_and_token(client, role="super_admin")
    superadmin = _auth(super_token)

    assert _decide(client, admin, report_id, "escalated", "Possible ring.").status_code == 200
    # Every Super Admin is told, with a link that opens the report under Escalated.
    with SessionLocal() as s:
        note = s.query(Notification).filter(Notification.user_id == super_id,
                                            Notification.kind == "report_escalated").one()
        assert note.link == f"/admin/review-queue?tab=report&rstatus=escalated&report={report_id}"
        assert "Possible ring." in (note.body or "")

    # An administrator cannot decide it any more, and nothing happens to the content.
    refused = _decide(client, admin, report_id, "content_removed")
    assert refused.status_code == 403 and refused.json()["code"] == "report_escalated"
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200
    # It cannot be escalated twice.
    assert _decide(client, superadmin, report_id, "escalated").status_code == 409

    # The Super Admin gives the final answer; it is resolved, no longer escalated.
    done = _decide(client, superadmin, report_id, "dismissed", "Not a ring.")
    assert done.status_code == 200 and done.json()["report"]["resolution"] == "dismissed"
    assert report_id not in {i["report"]["id"] for i in all_report_queue_items(
        client, admin, status="escalated")}
    assert report_id in {i["report"]["id"] for i in all_report_queue_items(
        client, admin, status="resolved")}


def test_activity_entries_name_the_outcome_and_open_the_report(client):
    _, report_id, admin = _reported(client, "ActivityOutcome")
    assert _decide(client, admin, report_id, "dismissed").status_code == 200
    rows = client.get("/api/v1/admin/activity?limit=50", headers=admin).json()["rows"]
    dismissal = next(r for r in rows if r["outcome"] == "dismissed"
                     and r["href"] and report_id in r["href"])
    # Audited as `approve` (the content stood), but labelled by its outcome.
    assert dismissal["action"] == "approve"
    assert dismissal["href"] == f"/admin/review-queue?tab=report&rstatus=all&report={report_id}"
    filed = next(r for r in rows if r["id"] == report_id)
    assert filed["action"] == "report" and filed["href"].endswith(f"report={report_id}")


def test_a_price_decision_is_in_the_activity_log(client):
    from tests.test_price_and_compare import _observe, _product
    _, member, _ = register_and_token(client)
    _, admin_token, _ = register_and_token(client, role="administrator")
    admin = _auth(admin_token)
    product = _product(client, _auth(member))
    assert _observe(client, _auth(member), product, 599).status_code == 201
    obs = client.get("/api/v1/admin/price-observations", headers=admin,
                     params={"product_id": product}).json()[0]["id"]
    r = client.post(f"/api/v1/admin/price-observations/{obs}/decision", headers=admin,
                    json={"decision": "approve"})
    assert r.status_code == 200, r.text
    rows = client.get("/api/v1/admin/activity?limit=50", headers=admin).json()["rows"]
    entry = next(r for r in rows if r["target_ref"] == obs)
    assert entry["outcome"] == "price_approved" and entry["href"] == "/admin/prices"

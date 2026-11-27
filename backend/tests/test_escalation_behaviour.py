"""Escalation as it works today (dev/QA sync 2026-09-29, ENG-0929-C).

The team confirmed this behaviour as correct at the meeting; these tests pin
it so a later change has to mean it:

* escalating a report takes it out of the open Reports queue, into its own
  Escalated status for a Super Admin (MQA-005, 2026-10-05);
* the escalation is an audited `escalate` action, which the Overview's recent
  activity shows ("doon lang siya sa overview lumalabas");
* the reported content stays published: nothing is done to it;
* while a review has an OPEN report, members below Stage 2 cannot comment on
  it ("under review by our administrators"); established members can.

Two gaps between the meeting's description and this model are recorded in
docs/MEETING_2026_09_29_DECISIONS.md §C and pinned here as they stand, not
"fixed" on the eve of the defense: the Overview entry is recent activity, not
a standing list; and escalation closes the report, so the comment limit lifts
unless another report on the review is still open.
"""

from __future__ import annotations

from tests.conftest import all_report_queue_items, register_and_token, requires_db, set_trust_stage
from tests.test_votes_api import make_published_review

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _reported(client, name: str):
    """A published review with one member's report on it."""
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    rid, _ = make_published_review(client, _auth(author), _auth(admin), name=name)
    _, reporter, _ = register_and_token(client)
    report = client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter),
                         json={"reason": "fake_proof", "notes": "Listing photo."})
    assert report.status_code == 201, report.text
    return rid, report.json()["id"], _auth(admin)


def _open_report_ids(client, admin) -> set[str]:
    return {i["report"]["id"] for i in all_report_queue_items(client, admin)}


def _comment(client, headers, rid: str):
    return client.post(f"/api/v1/reviews/{rid}/comments", headers=headers,
                       json={"body": "Is the photo really yours?"})


def test_escalating_takes_the_report_out_of_the_queue_and_leaves_the_content_live(client):
    rid, report_id, admin = _reported(client, "EscalateLive")
    assert report_id in _open_report_ids(client, admin)

    res = client.post(f"/api/v1/admin/reports/{report_id}/decision", headers=admin,
                      json={"resolution": "escalated", "notes": "Needs a second look."})
    assert res.status_code == 200, res.text
    assert res.json()["report"]["resolution"] == "escalated"

    assert report_id not in _open_report_ids(client, admin)
    # MQA-005: an escalated report has its own status, where it stays findable;
    # it is not "resolved" until a Super Admin decides it.
    escalated = {i["report"]["id"]: i for i in all_report_queue_items(
        client, admin, status="escalated")}
    assert escalated[report_id]["report"]["resolution"] == "escalated"
    resolved = {i["report"]["id"] for i in all_report_queue_items(client, admin, status="resolved")}
    assert report_id not in resolved
    # Nothing was done to the content.
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200

    # The Overview's recent activity shows it as an escalation.
    overview = client.get("/api/v1/admin/analytics/overview", headers=admin).json()
    assert any(a["action"] == "escalate" and a["target_ref"] == rid
               for a in overview["activity"])


def test_an_open_report_limits_comments_to_established_members(client):
    rid, report_id, admin = _reported(client, "EscalateHold")
    newcomer_id, newcomer, _ = register_and_token(client)
    set_trust_stage(newcomer_id, 1)
    held = _comment(client, _auth(newcomer), rid)
    assert held.status_code == 403 and held.json()["code"] == "comment_thread_reported"
    assert "administrators" in held.json()["detail"]

    established_id, established, _ = register_and_token(client)
    set_trust_stage(established_id, 2)
    assert _comment(client, _auth(established), rid).status_code == 201


def test_escalation_closes_the_report_so_the_limit_follows_any_other_open_report(client):
    rid, report_id, admin = _reported(client, "EscalateLift")
    _, second_reporter, _ = register_and_token(client)
    second = client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(second_reporter),
                         json={"reason": "spam"}).json()["id"]
    newcomer_id, newcomer, _ = register_and_token(client)
    set_trust_stage(newcomer_id, 1)

    assert client.post(f"/api/v1/admin/reports/{report_id}/decision", headers=admin,
                       json={"resolution": "escalated"}).status_code == 200
    # Another report is still open: the thread stays limited.
    assert _comment(client, _auth(newcomer), rid).status_code == 403

    assert client.post(f"/api/v1/admin/reports/{second}/decision", headers=admin,
                       json={"resolution": "escalated"}).status_code == 200
    # Gap (b), as it stands: with every report escalated (closed), it lifts.
    assert _comment(client, _auth(newcomer), rid).status_code == 201


def test_dismissing_also_closes_it_and_the_content_stands(client):
    rid, report_id, admin = _reported(client, "EscalateDismiss")
    assert client.post(f"/api/v1/admin/reports/{report_id}/decision", headers=admin,
                       json={"resolution": "dismissed"}).status_code == 200
    assert report_id not in _open_report_ids(client, admin)
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200

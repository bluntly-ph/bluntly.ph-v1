"""Admin Settings (Figma Screen/Admin/Settings 8076:16388): read-only, staff
only, the live rules, and staff emails for the Super Admin alone."""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_settings_state_the_live_rules_and_hide_emails_from_administrators(client):
    _, member, _ = register_and_token(client)
    admin_id, admin, admin_email = register_and_token(client, role="administrator")
    _, root, _ = register_and_token(client, role="super_admin")
    assert client.get("/api/v1/admin/settings").status_code == 401
    assert client.get("/api/v1/admin/settings", headers=_auth(member)).status_code == 403

    body = client.get("/api/v1/admin/settings", headers=_auth(admin)).json()
    assert (body["wilson_gate"], body["min_stage2_voters"]) == (0.65, 3)
    split = (body["split_reviewer"], body["split_honesty_fund"], body["split_platform"])
    assert tuple(float(x) for x in split) == (0.3, 0.3, 0.4)
    assert float(body["payout_minimum"]) == 300.0
    assert (body["payout_day"], body["honesty_fund_day"]) == (5, 1)
    assert {i["key"] for i in body["integrations"]} == {"affiliate", "paypal", "paymongo", "email"}
    assert all(m["email"] is None for m in body["team"])
    assert body["team_total"] >= 2 and any(r["label"] == "Activity log" for r in body["retention"])
    assert {"label": "Request geography", "value": "90 days, no IP addresses"} in [
        {"label": r["label"], "value": r["value"]} for r in body["retention"]]

    seen = client.get("/api/v1/admin/settings", headers=_auth(root)).json()
    assert any(m["email"] for m in seen["team"])
    # Read-only: there is nothing to write to.
    assert client.put("/api/v1/admin/settings", headers=_auth(root), json={}).status_code == 405

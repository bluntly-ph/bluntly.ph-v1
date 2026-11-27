"""Membership tiers: list, RBAC-gated assignment (integration)."""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@requires_db
def test_list_tiers_after_seed(client):
    from scripts.seed import seed
    seed()  # idempotent
    resp = client.get("/api/v1/membership-tiers")
    assert resp.status_code == 200
    codes = {t["code"] for t in resp.json()}
    assert {"special", "founding", "standard"} <= codes


@requires_db
def test_only_a_super_admin_assigns_a_tier(client):
    """Owner decision C: moving a member up a tier is user management."""
    target_id, _, _ = register_and_token(client)
    _, user_token, _ = register_and_token(client)
    _, admin_token, _ = register_and_token(client, role="administrator")
    _, super_token, _ = register_and_token(client, role="super_admin")

    for token in (user_token, admin_token):
        forbidden = client.patch(f"/api/v1/users/{target_id}/membership-tier",
                                 headers=_auth(token), json={"membership_tier": "founding"})
        assert forbidden.status_code == 403
    assert client.patch("/api/v1/membership-tiers/standard", headers=_auth(admin_token),
                        json={"revenue_share_bps": 3100}).status_code == 403

    ok = client.patch(f"/api/v1/users/{target_id}/membership-tier",
                      headers=_auth(super_token), json={"membership_tier": "founding"})
    assert ok.status_code == 200
    assert ok.json()["membership_tier"] == "founding"

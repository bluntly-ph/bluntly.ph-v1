"""HIGH 8 RBAC sweep (defense build, session 4): every registered admin route,
called by the wrong role, against the real app.

Discovered, not listed: the routes are read from the app, so an admin route
added later is swept too. For each route under /api/v1/admin (and the reports
routes) the guard is read from its dependency tree:

* every one must carry a staff or Super Admin guard — none may rely on the
  service alone;
* nobody signed out gets past it (401), a member or a store owner never does
  (403), and an Administrator is refused every Super Admin-only route (403).

Calls carry dummy ids and an empty body: the guard runs before validation, so
a 401/403 is the only acceptable answer. Nothing is written by a refused call.
"""

from __future__ import annotations

import re
import uuid

from fastapi.routing import APIRoute

from app.core.security import require_staff, require_super_admin
from app.main import app
from tests.conftest import register_and_token, requires_db
from tests.test_business_rules_api import _auth, _claimed_seller

pytestmark = requires_db

ADMIN_PREFIXES = ("/api/v1/admin/", "/api/v1/admin")


def _calls(dependant) -> set:
    out = {dependant.call}
    for sub in dependant.dependencies:
        out |= _calls(sub)
    return out


def _admin_routes(everywhere: bool = False) -> list[tuple[APIRoute, str, str]]:
    """(route, method, guard) for every admin route — or, `everywhere`, for every
    route in the app that carries a role guard; guard = staff | super | none."""
    rows = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not everywhere and not route.path.startswith(ADMIN_PREFIXES):
            continue
        calls = _calls(route.dependant)
        guard = ("super" if require_super_admin in calls
                 else "staff" if require_staff in calls else "none")
        if everywhere and guard == "none":
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            rows.append((route, method, guard))
    return rows


def _url(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), path)


def _call(client, method: str, path: str, headers: dict | None = None):
    kwargs = {"headers": headers or {}}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    return client.request(method, _url(path), **kwargs)


def test_every_admin_route_has_a_role_guard():
    rows = _admin_routes()
    assert len(rows) > 60, "the sweep found too few admin routes to be meaningful"
    unguarded = [f"{m} {r.path}" for r, m, g in rows if g == "none"]
    assert unguarded == [], f"admin routes without a staff/super guard: {unguarded}"


def test_signed_out_member_and_store_owner_are_refused_everywhere(client):
    _, member, _ = register_and_token(client)
    _, owner, _store, _mod = _claimed_seller(client)   # a claimed store's owner
    leaks = []
    for route, method, _guard in _admin_routes(everywhere=True):
        anon = _call(client, method, route.path)
        if anon.status_code != 401:
            leaks.append(f"anon {method} {route.path} -> {anon.status_code}")
        for name, token in (("member", member), ("owner", owner)):
            r = _call(client, method, route.path, _auth(token))
            if r.status_code != 403:
                leaks.append(f"{name} {method} {route.path} -> {r.status_code}")
    assert leaks == [], "\n".join(leaks)


def test_an_administrator_is_refused_every_super_admin_route(client):
    _, admin, _ = register_and_token(client, role="administrator")
    supers = [(r, m) for r, m, g in _admin_routes(everywhere=True) if g == "super"]
    assert supers, "no Super Admin-only routes found"
    leaks = [f"{m} {r.path} -> {res.status_code}"
             for r, m in supers
             if (res := _call(client, m, r.path, _auth(admin))).status_code != 403]
    assert leaks == [], "\n".join(leaks)


def test_store_owners_are_isolated_from_each_other(client):
    """A store's private surfaces: its owner and staff, never another store's owner."""
    _, owner_a, store_a, mod = _claimed_seller(client)
    _, owner_b, _store_b, _ = _claimed_seller(client)
    _, member, _ = register_and_token(client)
    sid = store_a["id"]
    private = (f"/api/v1/sellers/{sid}/dashboard",
               f"/api/v1/sellers/{sid}/reports/rating-summary",
               f"/api/v1/sellers/{sid}/support-requests")
    for path in private:
        assert client.get(path, headers=_auth(owner_a)).status_code == 200, path
        assert client.get(path, headers=_auth(mod)).status_code in (200, 403), path
        for who in (owner_b, member):
            assert client.get(path, headers=_auth(who)).status_code in (403, 404), path
        assert client.get(path).status_code == 401, path


def test_money_is_only_ever_the_callers_own(client):
    """Payout balance, payouts, earnings, the statement and the contributor
    dashboards take no user id: each returns the caller's own figures."""
    uid_a, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    for path in ("/api/v1/payouts/balance", "/api/v1/payouts", "/api/v1/users/me/contributor",
                 "/api/v1/users/me/performance", "/api/v1/users/me/earnings",
                 "/api/v1/reports/earnings-statement"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=_auth(b)).status_code == 200, path
    # Another reviewer's statement is a staff route.
    other = f"/api/v1/admin/reports/earnings-statement/{uid_a}"
    assert client.get(other, headers=_auth(b)).status_code == 403
    # A case thread is its filer's and staff's only (services/case_chat_service).
    assert client.get(f"/api/v1/cases/claim/{uuid.uuid4()}/messages",
                      headers=_auth(b)).status_code in (403, 404)

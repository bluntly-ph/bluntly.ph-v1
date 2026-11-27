"""Security limits: who a rate limit counts, who may record a view, and what an
AI critique may cost (security review, 2026-10-22).

S1. The limiter keyed on the first X-Forwarded-For hop. For every call the
    Next.js server makes on a visitor's behalf that hop is the frontend
    function, so all visitors shared a few dozen counters and about ten failed
    logins a minute from anyone locked everyone out. It now counts the address
    `trusted_client_ip` believes: the visitor's, signed by our own server.
S2. POST /internal/traffic accepted anyone, and its view counts feed the
    admin's monetization attention list. It now needs the proxy's secret.
S3. AI critique had no size cap and no per-account limit.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
import redis

from app.core import client_ip, rate_limit
from app.core.config import settings
from app.core.errors import RateLimitError
from tests.conftest import register_and_token, requires_db

SECRET = "test-signing-secret"
FRONTEND = "10.20.30.40"      # the frontend function's own egress address


class _Req:
    """A request as the API sees it: headers plus the socket peer."""

    def __init__(self, headers: dict[str, str], peer: str = FRONTEND) -> None:
        self.headers = headers
        self.client = SimpleNamespace(host=peer)


def _signed(ip: str, at: int | None = None, secret: str = SECRET) -> dict[str, str]:
    at = int(time.time()) if at is None else at
    return {"x-bluntly-bff": "1", "x-bluntly-client-ip": ip,
            "x-bluntly-client-ip-at": str(at),
            "x-bluntly-client-ip-signature": client_ip.sign(ip, at, secret)}


@pytest.fixture
def keys(monkeypatch):
    """Record every counter key instead of counting (no Redis, no Postgres)."""
    seen: list[str] = []

    def no_redis():
        raise redis.ConnectionError("not in this test")

    monkeypatch.setattr(rate_limit, "get_redis", no_redis)
    monkeypatch.setattr(rate_limit, "_count_in_postgres",
                        lambda k, w: (seen.append(k), (1, 60))[1])
    monkeypatch.setattr(settings, "client_ip_signing_secret", SECRET)
    return seen


# --- S1: which address a limit counts ------------------------------------------------------

@pytest.mark.parametrize("mode", ["none", "vercel"])
def test_two_signed_visitors_behind_one_server_get_separate_counters(monkeypatch, keys, mode):
    """The bug itself: both calls come from the frontend's address. Signed,
    they are two visitors and two counters."""
    monkeypatch.setattr(settings, "trusted_proxy", mode)
    edge = {"x-vercel-forwarded-for": FRONTEND}
    rate_limit.enforce_rate_limit(_Req({**edge, **_signed("203.0.113.1")}), "login")
    rate_limit.enforce_rate_limit(_Req({**edge, **_signed("203.0.113.2")}), "login")
    rate_limit.enforce_rate_limit(_Req({**edge, **_signed("203.0.113.1")}), "login")
    assert keys[0] != keys[1], "two visitors shared the frontend's counter"
    assert keys[0] == keys[2], "one visitor must keep one counter"
    assert all("untrusted" not in k for k in keys)


def test_a_signed_visitor_is_counted_apart_from_the_servers_own_address(monkeypatch, keys):
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    rate_limit.enforce_rate_limit(_Req(_signed("203.0.113.1")), "login")
    rate_limit.enforce_rate_limit(_Req({}), "login")       # unsigned: the peer itself
    assert keys[0] != keys[1]


@pytest.mark.parametrize("headers", [
    {"x-bluntly-client-ip": "203.0.113.1"},                                 # unsigned
    _signed("203.0.113.1", secret="not-the-secret"),                         # wrong key
    {**_signed("203.0.113.1"), "x-bluntly-client-ip": "203.0.113.99"},       # tampered
], ids=["unsigned", "wrong-secret", "tampered"])
def test_an_unsigned_or_wrongly_signed_address_is_ignored(monkeypatch, keys, headers):
    """Locally the limiter then counts the socket peer, exactly as if the
    header were not there: a client cannot pick its own counter."""
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    rate_limit.enforce_rate_limit(_Req(headers), "login")
    rate_limit.enforce_rate_limit(_Req({}), "login")
    assert keys[0] == keys[1], "a forged address chose its own counter"


def test_an_expired_signature_is_ignored(monkeypatch, keys):
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    stale = _signed("203.0.113.1", at=int(time.time()) - 10 * 60)
    rate_limit.enforce_rate_limit(_Req(stale), "login")
    rate_limit.enforce_rate_limit(_Req({}), "login")
    rate_limit.enforce_rate_limit(_Req(_signed("203.0.113.1")), "login")
    assert keys[0] == keys[1], "an expired signature was believed"
    assert keys[0] != keys[2]


def test_a_forwarding_header_never_chooses_the_counter_locally(monkeypatch, keys):
    """The old behaviour, pinned closed: X-Forwarded-For is whatever the
    client wrote unless the edge wrote it."""
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    rate_limit.enforce_rate_limit(_Req({"x-forwarded-for": "198.51.100.1"}), "login")
    rate_limit.enforce_rate_limit(_Req({"x-forwarded-for": "198.51.100.2"}), "login")
    assert keys[0] == keys[1]


def test_on_vercel_an_untrusted_call_gets_its_own_stricter_bucket(monkeypatch, keys):
    """A frontend call that could not be signed (no secret configured): not a
    visitor's counter, not one global counter, and a tighter ceiling."""
    monkeypatch.setattr(settings, "trusted_proxy", "vercel")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "")
    warned: list[str] = []
    monkeypatch.setattr(rate_limit.log, "warning", lambda msg, **kw: warned.append(msg))
    monkeypatch.setattr(rate_limit, "_count_in_postgres",
                        lambda k, w: (keys.append(k), (6, 60))[1])

    unsigned = {"x-bluntly-bff": "1", "x-vercel-forwarded-for": FRONTEND}
    with pytest.raises(RateLimitError):
        # 6 calls is inside the normal limit of 10 but over the untrusted 5.
        rate_limit.enforce_rate_limit(_Req(unsigned), "login", max_requests=10)
    assert keys[-1].startswith("rl:login:untrusted:")
    assert warned, "an untrusted rate-limit key must be logged"

    other = {"x-bluntly-bff": "1", "x-vercel-forwarded-for": "10.20.30.41"}
    with pytest.raises(RateLimitError):
        rate_limit.enforce_rate_limit(_Req(other), "login", max_requests=10)
    assert keys[-1] != keys[-2], "untrusted calls collapsed into one global counter"


def test_the_untrusted_key_never_holds_the_address(monkeypatch, keys):
    monkeypatch.setattr(settings, "trusted_proxy", "vercel")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "")
    rate_limit.enforce_rate_limit(
        _Req({"x-bluntly-bff": "1", "x-vercel-forwarded-for": FRONTEND}), "vote")
    assert FRONTEND not in keys[0] and "10.20" not in keys[0]


def test_the_user_keyed_limiter_follows_the_account_not_the_address(monkeypatch, keys):
    rate_limit.enforce_user_rate_limit("user-a", "ai_critique", 20, 3600)
    rate_limit.enforce_user_rate_limit("user-b", "ai_critique", 20, 3600)
    rate_limit.enforce_user_rate_limit("user-a", "ai_critique", 20, 3600)
    assert keys[0] == keys[2] != keys[1]
    assert keys[0].startswith("rl:user:ai_critique:") and "user-a" not in keys[0]


def test_the_user_keyed_limiter_refuses_over_the_limit(monkeypatch, keys):
    monkeypatch.setattr(rate_limit, "_count_in_postgres", lambda k, w: (21, 1800))
    with pytest.raises(RateLimitError) as exc:
        rate_limit.enforce_user_rate_limit("user-a", "ai_critique", 20, 3600)
    assert exc.value.extra["retry_after_seconds"] == 1800


# --- S2: the traffic beacon needs the proxy's secret ----------------------------------------

BEACON = {"country": "PH", "city": "Manila", "pop": "sin1"}


@requires_db
def test_with_a_secret_configured_the_beacon_must_present_it(client, monkeypatch):
    monkeypatch.setattr(settings, "traffic_beacon_secret", "beacon-secret")
    url = "/api/v1/internal/traffic"
    assert client.post(url, json=BEACON).status_code == 401
    assert client.post(url, json=BEACON,
                       headers={"X-Traffic-Key": "wrong"}).status_code == 401
    assert client.post(url, json=BEACON,
                       headers={"X-Traffic-Key": "beacon-secret"}).status_code == 204


@requires_db
def test_in_production_an_unset_secret_fails_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "traffic_beacon_secret", "")
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.post("/api/v1/internal/traffic", json=BEACON,
                       headers={"X-Traffic-Key": "anything"}).status_code == 401


@requires_db
def test_outside_production_an_unset_secret_keeps_local_stacks_working(client, monkeypatch):
    monkeypatch.setattr(settings, "traffic_beacon_secret", "")
    assert client.post("/api/v1/internal/traffic", json=BEACON).status_code == 204


@requires_db
def test_the_beacon_is_limited_per_signed_visitor_at_its_own_ceiling(client, monkeypatch):
    """120 a minute per visitor, not the login limiter's 10 per proxy."""
    seen: list[tuple[str, int]] = []

    def record(request, bucket, max_requests=None, window_seconds=None):
        seen.append((bucket, max_requests))

    from app.api.v1.routes import traffic_ingest
    monkeypatch.setattr(settings, "traffic_beacon_secret", "")
    monkeypatch.setattr(traffic_ingest, "enforce_rate_limit", record)
    assert client.post("/api/v1/internal/traffic", json=BEACON).status_code == 204
    assert seen == [("traffic_ingest", 120)]


# --- S3: AI critique caps ------------------------------------------------------------------

@requires_db
def test_critique_text_and_title_are_capped(client):
    _, token, _ = register_and_token(client)
    auth = {"Authorization": f"Bearer {token}"}
    url = "/api/v1/ai/critique"
    assert client.post(url, json={"text": "x" * 10_001}, headers=auth).status_code == 422
    assert client.post(url, json={"text": "ok", "title": "t" * 201},
                       headers=auth).status_code == 422
    assert client.post(url, json={"text": "x" * 10_000, "title": "t" * 200},
                       headers=auth).status_code == 200


@requires_db
def test_critique_is_limited_per_account(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_critique_rate_limit_max", 2)
    _, token, _ = register_and_token(client)
    auth = {"Authorization": f"Bearer {token}"}
    url = "/api/v1/ai/critique"
    codes = [client.post(url, json={"text": "A draft."}, headers=auth).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429], codes

    # A second account has its own allowance: it is keyed by account.
    _, other, _ = register_and_token(client)
    assert client.post(url, json={"text": "A draft."},
                       headers={"Authorization": f"Bearer {other}"}).status_code == 200

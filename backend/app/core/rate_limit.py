"""Fixed-window rate limiting: Redis first, Postgres second, open last.

Added per Architecture §8/Q11 and PRD §8 — the source spec has no rate limiting,
leaving registration/auth open to flooding. A fixed-window counter keyed by
the visitor's trusted address (or account) + route bucket.

Sync client: our API endpoints are sync `def`, run in a threadpool — a sync Redis
client avoids event-loop lifecycle issues.

**Why there are two stores.** Failing open on a Redis outage is deliberate: a
counter must never be the reason nobody can log in. But for a long time it was
the *only* story, and on 2026-08-20 that was measured against production —
fourteen consecutive failed logins from one address, all 401, not one 429,
against a configured limit of ten per minute. `REDIS_URL` is set nowhere, so
every call was reaching for `localhost`, raising, and being allowed. The
protection was absent, and it was absent quietly, which is the part that
matters: the design's escape hatch had become its normal operating mode.

So Postgres backs it up. It is already the system of record and already on the
request path, which makes it the cheap answer rather than a second piece of
paid infrastructure for a counter. Redis stays first because it is the right
tool; Postgres catches the case where Redis simply is not there; and only if
*both* are unreachable does the limiter fall open, which is now a genuine
outage rather than a Tuesday.
"""

from __future__ import annotations

import hashlib
import hmac
import random
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import text

from app.core.client_ip import _edge_ip, proxy_mode, trusted_client_ip
from app.core.config import settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger

log = get_logger("rate_limit")

if TYPE_CHECKING:
    # Imported where it is used: an instance that serves no rate-limited
    # request never needs the client.
    import redis

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    import redis

    global _redis
    if _redis is None:
        # Timeouts are load-bearing, not tuning. Failing open is the design, but
        # the *default* client waits ~4s before deciding it cannot connect, and
        # that wait lands on every rate-limited request: voting, reporting,
        # commenting, and every auth call including OTP. Measured 2026-08-10 with
        # no Redis listening: 4.045s per call. A dead limiter must cost
        # milliseconds, otherwise a Redis outage silently becomes a site-wide
        # four-second tax on exactly the endpoints users feel most.
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
    return _redis


#: A request whose address cannot be trusted gets this share of the normal
#: limit, in a bucket of its own (see `_client_identity`).
UNTRUSTED_LIMIT_DIVISOR = 2


def _client_identity(request: Request) -> tuple[str, bool]:
    """(address to count, whether it is the visitor's own), never the raw XFF.

    The counter used to key on the first `X-Forwarded-For` hop. For a call the
    Next.js server makes on a visitor's behalf (login, sign-up, sign-in codes,
    votes, comments, reports) that hop is the frontend function, so every
    visitor shared one of a few dozen counters and about ten failed logins a
    minute from anyone locked everyone out. The server now forwards the
    visitor's address signed (lib/api/client.ts), and `trusted_client_ip`
    believes only that or the address the Vercel edge itself wrote.

    * A trusted address: the visitor.
    * Locally (proxy mode "none"), the socket peer. Nothing there is shared.
    * On Vercel with nothing trusted (a frontend call that could not be
      signed): the connecting address, counted apart from visitors' counters
      and held to a stricter limit, so unsigned traffic can neither share a
      visitor's counter nor fall into one global counter.
    """
    ip = trusted_client_ip(request)
    if ip is not None:
        return ip, True
    peer = request.client.host if request.client else "unknown"
    if proxy_mode() != "vercel":
        return peer, True
    return _edge_ip(request) or peer, False


def _keyed(value: str) -> str:
    """A stable, keyed stand-in for an identifier, never the identifier.

    The counter only needs to tell one client from another. Until 2026-09-30 it
    stored the raw address as its key (`rl:vote:<address>` in
    `rate_limit_counters`), which kept IP addresses in the database the
    vote-farming work promised never to hold. HMAC-SHA256 under a key derived
    from the server secret `PII_HASH_SALT`, truncated to 32 hex characters: the
    same client still maps to the same counter, and the row cannot be turned
    back into an address without the secret."""
    key = hmac.new(settings.pii_hash_salt.encode(), b"rate-limit-v1", hashlib.sha256).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:32]


def enforce_rate_limit(request: Request, bucket: str,
                       max_requests: int | None = None,
                       window_seconds: int | None = None) -> None:
    """Increment the caller's window counter; raise RateLimitError when exceeded."""
    max_requests = max_requests or settings.auth_rate_limit_max
    window_seconds = window_seconds or settings.auth_rate_limit_window_seconds
    address, trusted = _client_identity(request)
    if trusted:
        key = f"rl:{bucket}:{_keyed(address)}"
    else:
        key = f"rl:{bucket}:untrusted:{_keyed(address)}"
        max_requests = max(1, max_requests // UNTRUSTED_LIMIT_DIVISOR)
        log.warning("rate limit on an untrusted address", extra={
            "extra_fields": {"bucket": bucket}})
    _hit(key, bucket, max_requests, window_seconds)


def enforce_user_rate_limit(user_id: object, bucket: str, max_requests: int,
                            window_seconds: int) -> None:
    """The same counter keyed by account, for limits that follow a person
    across addresses (an AI critique costs money whoever's network it is on)."""
    _hit(f"rl:user:{bucket}:{_keyed(str(user_id))}", bucket, max_requests, window_seconds)


def _hit(key: str, bucket: str, max_requests: int, window_seconds: int) -> None:
    import redis

    try:
        r = get_redis()
        current = r.incr(key)
        if current == 1:
            r.expire(key, window_seconds)
        ttl = r.ttl(key) if current > max_requests else 0
    except redis.RedisError as exc:
        hit = _count_in_postgres(key, window_seconds)
        if hit is None:
            # Both stores are unreachable. Allow, but say so at a level someone
            # will actually see — this is the state where there is no limit.
            log.warning("rate limiter unavailable in both stores; allowing", extra={
                "extra_fields": {"bucket": bucket, "error": str(exc)}})
            return
        current, ttl = hit
    if current > max_requests:
        raise RateLimitError(
            f"Rate limit exceeded for {bucket}. Retry in {max(ttl, 0)}s.",
            extra={"retry_after_seconds": max(ttl, 0)},
        )


# One statement, so the read-modify-write cannot interleave with another
# request for the same key. `count` resets to 1 when the stored window has
# already closed, which is what makes this a fixed window rather than a
# counter that only ever grows.
_UPSERT = text("""
    INSERT INTO rate_limit_counters (key, count, window_start)
    VALUES (:key, 1, now())
    ON CONFLICT (key) DO UPDATE SET
        count = CASE
            WHEN rate_limit_counters.window_start
                 < now() - make_interval(secs => :window) THEN 1
            ELSE rate_limit_counters.count + 1 END,
        window_start = CASE
            WHEN rate_limit_counters.window_start
                 < now() - make_interval(secs => :window) THEN now()
            ELSE rate_limit_counters.window_start END
    RETURNING count,
              GREATEST(0, CEIL(EXTRACT(EPOCH FROM (
                  window_start + make_interval(secs => :window) - now()))))::int
""")

# Rows are keyed by client, so the table's size follows the number of distinct
# callers rather than the number of requests. It still needs sweeping, and a
# small chance per call is enough to keep up without a scheduler.
_PRUNE_PROBABILITY = 0.01
_PRUNE = text("DELETE FROM rate_limit_counters "
              "WHERE window_start < now() - interval '1 hour'")


def _count_in_postgres(key: str, window_seconds: int) -> tuple[int, int] | None:
    """(count, seconds until the window closes), or None if Postgres is no help.

    Uses its own short-lived session on purpose: this runs inside a request
    that has its own transaction, and a limiter must not be able to roll that
    back or be rolled back with it. Counting a request that later fails is the
    correct behaviour anyway — the attempt was still made.
    """
    from app.db.session import SessionLocal

    try:
        with SessionLocal() as db:
            row = db.execute(_UPSERT, {"key": key, "window": window_seconds}).one()
            if random.random() < _PRUNE_PROBABILITY:
                db.execute(_PRUNE)
            db.commit()
            return int(row[0]), int(row[1])
    except Exception as exc:  # noqa: BLE001 - including "table not yet migrated"
        log.warning("postgres rate limiter unavailable", extra={
            "extra_fields": {"error": f"{type(exc).__name__}: {exc}"}})
        return None


def auth_rate_limiter(bucket: str):
    """Dependency factory for auth-adjacent endpoints."""

    def _dep(request: Request) -> None:
        enforce_rate_limit(request, bucket)

    return _dep

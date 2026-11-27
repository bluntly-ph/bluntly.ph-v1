"""The client's IP address, from a source that cannot be forged (QA 2026-09-29).

Only the vote-farming network signal reads this, and it stores nothing but a
keyed hash of the result (`services/vote_network.py`). Every other header a
client sends is untrusted.

Where the address comes from, in order:

1. **The BFF's signature.** A vote from the site goes browser -> Vercel edge ->
   Next.js BFF (`app/api/bff`) -> API. The BFF received the voter's address
   from the edge; it forwards it in `x-bluntly-client-ip` with an HMAC over
   `ip|unix time` under `CLIENT_IP_SIGNING_SECRET`. A valid signature under 120
   seconds old is trusted.
2. **The edge itself**, only when `trusted_proxy` is "vercel": Vercel
   overwrites `X-Forwarded-For` and sets `x-vercel-forwarded-for` with the
   address that connected to it. That is the voter on a direct call to the API.
   On a call the BFF made it is the BFF's own egress address, shared by every
   voter, so a request marked `x-bluntly-bff` never uses it: with a signing
   secret configured it must be signed, and without one it records nothing.
3. **Nothing.** Locally, in tests, or behind any proxy this code does not know,
   every forwarding header is ignored: a client can write them.

`None` means "unknown", and the signal then simply has no network to compare.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import time

from starlette.requests import Request

from app.core.config import settings

SIGNED_IP = "x-bluntly-client-ip"
SIGNATURE = "x-bluntly-client-ip-signature"
SIGNED_AT = "x-bluntly-client-ip-at"
VIA_BFF = "x-bluntly-bff"
MAX_SIGNATURE_AGE_SECONDS = 120


def proxy_mode() -> str:
    mode = (settings.trusted_proxy or "").strip().lower()
    if mode in ("vercel", "none"):
        return mode
    return "vercel" if os.getenv("VERCEL") == "1" else "none"


def _valid_ip(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


def sign(ip: str, at: int, secret: str) -> str:
    """The BFF's signature (mirrored in app/api/bff/[...path]/route.ts)."""
    return hmac.new(secret.encode(), f"{ip}|{at}".encode(), hashlib.sha256).hexdigest()


def _signed_ip(request: Request) -> str | None:
    secret = settings.client_ip_signing_secret
    if not secret:
        return None
    ip = _valid_ip(request.headers.get(SIGNED_IP))
    signature = request.headers.get(SIGNATURE) or ""
    try:
        at = int(request.headers.get(SIGNED_AT) or "")
    except ValueError:
        return None
    if ip is None or abs(time.time() - at) > MAX_SIGNATURE_AGE_SECONDS:
        return None
    if not hmac.compare_digest(sign(ip, at, secret), signature):
        return None
    return ip


def _edge_ip(request: Request) -> str | None:
    raw = request.headers.get("x-vercel-forwarded-for") or \
        (request.headers.get("x-forwarded-for") or "").split(",")[0]
    return _valid_ip(raw)


def trusted_client_ip(request: Request) -> str | None:
    signed = _signed_ip(request)
    if signed is not None:
        return signed
    if proxy_mode() != "vercel":
        return None
    if request.headers.get(VIA_BFF) and not settings.client_ip_signing_secret:
        # A BFF call without signing: the edge saw the BFF, not the voter.
        return None
    return _edge_ip(request)

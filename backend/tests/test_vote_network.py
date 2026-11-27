"""Vote farming from one network (QA, 2026-09-29): "IP detection to identify
possible anomalous voting or vote farming".

A signal, never a verdict: several accounts on one network up-voting one member
files a SYSTEM_DETECTED report and nothing else. No IP address is stored (a
keyed hash of the network, 30 days), none is shown, and a forwarding header a
client can write is never believed.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, inspect, select
from starlette.requests import Request

from app.core import client_ip
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.integrity import VoteNetworkFingerprint
from app.models.user import User
from app.services import vote_network
from tests.conftest import all_report_queue_items, register_and_token, requires_db, unique_text


def _request(headers: dict[str, str]) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/",
                    "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]})


# --- which address is believed -------------------------------------------------------------

def test_a_forwarding_header_is_ignored_unless_the_deployment_proxy_writes_it(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "")
    spoofed = _request({"x-forwarded-for": "198.51.100.9",
                        "x-vercel-forwarded-for": "198.51.100.9"})
    assert client_ip.trusted_client_ip(spoofed) is None
    monkeypatch.setattr(settings, "trusted_proxy", "vercel")
    assert client_ip.trusted_client_ip(spoofed) == "198.51.100.9"
    assert client_ip.trusted_client_ip(_request({"x-forwarded-for": "not-an-ip"})) is None


def test_a_bff_call_never_records_the_bffs_own_shared_address(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy", "vercel")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "")
    via_bff = _request({"x-bluntly-bff": "1", "x-forwarded-for": "10.1.2.3"})
    assert client_ip.trusted_client_ip(via_bff) is None


def test_a_signed_address_from_the_bff_is_believed_and_a_forged_one_is_not(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "shared-secret")
    now = int(time.time())
    good = {"x-bluntly-bff": "1", "x-bluntly-client-ip": "203.0.113.7",
            "x-bluntly-client-ip-at": str(now),
            "x-bluntly-client-ip-signature": client_ip.sign("203.0.113.7", now, "shared-secret")}
    assert client_ip.trusted_client_ip(_request(good)) == "203.0.113.7"
    forged = {**good, "x-bluntly-client-ip-signature": client_ip.sign("203.0.113.7", now, "guess")}
    assert client_ip.trusted_client_ip(_request(forged)) is None
    stale_at = now - 600
    stale = {**good, "x-bluntly-client-ip-at": str(stale_at),
             "x-bluntly-client-ip-signature": client_ip.sign("203.0.113.7", stale_at,
                                                              "shared-secret")}
    assert client_ip.trusted_client_ip(_request(stale)) is None


def test_with_signing_on_an_unsigned_bff_marker_cannot_hide_the_callers_address(monkeypatch):
    """A farmer calling the API directly with a fake `x-bluntly-bff` header gets
    the address the edge saw: their own."""
    monkeypatch.setattr(settings, "trusted_proxy", "vercel")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "shared-secret")
    faked = _request({"x-bluntly-bff": "1", "x-vercel-forwarded-for": "198.51.100.9"})
    assert client_ip.trusted_client_ip(faked) == "198.51.100.9"


def test_the_stored_network_is_a_keyed_hash_never_the_address(monkeypatch):
    h = vote_network.network_hash("203.0.113.7")
    assert len(h) == 32 and "203" not in h
    # One home rotates through its IPv6 /64: the same network.
    assert vote_network.network_hash("2001:db8:1:2::10") == \
        vote_network.network_hash("2001:db8:1:2:ffff::1")
    assert vote_network.network_hash("2001:db8:1:2::10") != \
        vote_network.network_hash("2001:db8:1:3::10")
    monkeypatch.setattr(settings, "pii_hash_salt", "a-different-server-secret")
    assert vote_network.network_hash("203.0.113.7") != h        # useless without the key


# --- on a real database ---------------------------------------------------------------------

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def behind_vercel(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy", "vercel")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "")


def _voters(client, n: int, *, mature: bool) -> list[tuple[str, dict]]:
    out = []
    db = SessionLocal()
    try:
        for _ in range(n):
            uid, tok, _ = register_and_token(client)
            if mature:
                db.get(User, uuid.UUID(uid)).created_at = datetime.now(UTC) - timedelta(days=400)
            out.append((uid, _auth(tok)))
        db.commit()
    finally:
        db.close()
    return out


def _author_with_reviews(client, n: int) -> tuple[str, list[str]]:
    uid, tok, _ = register_and_token(client)
    ids = []
    for i in range(n):
        pid = client.post("/api/v1/products", headers=_auth(tok), json={
            "name": f"Network {i} {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
        res = client.post("/api/v1/reviews", headers=_auth(tok), json={
            "product_id": pid, "title": f"Network {i}", "discussion": unique_text("Network"),
            "verdict": "yes_absolutely", "star_rating": 4})
        assert res.status_code == 201, res.text
        ids.append(res.json()["id"])
    return uid, ids


def _upvote(client, headers: dict, rid: str, ip: str) -> None:
    res = client.post(f"/api/v1/reviews/{rid}/vote", json={"vote": "up"},
                      headers={**headers, "x-vercel-forwarded-for": ip})
    assert res.status_code == 200, res.text


def _network_reports(client, admin: dict, author_id: str) -> list[dict]:
    return [i for i in all_report_queue_items(client, admin)
            if i["report"]["target_ref"] == author_id and i["origin"] == "system_detected"
            and (i.get("explanation") or {}).get("signal") == "shared_network_votes"]


def _ip() -> str:
    """A documentation-range address unique to this test run."""
    return f"198.51.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"


@requires_db
def test_a_household_of_ordinary_accounts_is_not_flagged(client, behind_vercel):
    _, admin, _ = register_and_token(client, role="administrator")
    author_id, [rid] = _author_with_reviews(client, 1)
    ip = _ip()
    for _, headers in _voters(client, 3, mature=True):
        _upvote(client, headers, rid, ip)
    assert _network_reports(client, _auth(admin), author_id) == []
    assert client.get(f"/api/v1/reviews/{rid}").json()["helpful_votes"] == 3   # all counted


@requires_db
def test_fresh_accounts_clustered_on_one_network_are_flagged_and_nobody_is_penalised(
        client, behind_vercel):
    _, admin, _ = register_and_token(client, role="administrator")
    author_id, [rid] = _author_with_reviews(client, 1)
    ip = _ip()
    voters = _voters(client, 3, mature=False)
    for _, headers in voters:
        _upvote(client, headers, rid, ip)

    [item] = _network_reports(client, _auth(admin), author_id)
    why = item["explanation"]
    assert why["summary"].startswith("Possible vote farming: 3 accounts on one network")
    assert "No IP address is stored or shown." in why["summary"]
    # Evidence only: every vote stands, nobody is struck, suspended or held.
    assert client.get(f"/api/v1/reviews/{rid}").json()["helpful_votes"] == 3
    db = SessionLocal()
    try:
        for uid in [author_id] + [v for v, _ in voters]:
            user = db.get(User, uuid.UUID(uid))
            assert not user.is_suspended and user.strikes == 0 and not user.is_on_probation
    finally:
        db.close()
    # The address appears nowhere an administrator can read, nor does its hash.
    text = str(all_report_queue_items(client, _auth(admin)))
    assert ip not in text and vote_network.network_hash(ip) not in text


@requires_db
def test_a_large_cluster_of_older_accounts_is_flagged_by_its_volume(client, behind_vercel):
    _, admin, _ = register_and_token(client, role="administrator")
    author_id, reviews = _author_with_reviews(client, 2)
    ip = _ip()
    for _, headers in _voters(client, 5, mature=True):
        for rid in reviews:
            _upvote(client, headers, rid, ip)
    [item] = _network_reports(client, _auth(admin), author_id)
    assert "10 times" in item["explanation"]["summary"]


@requires_db
def test_a_spoofed_header_off_vercel_records_nothing(client, monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy", "none")
    monkeypatch.setattr(settings, "client_ip_signing_secret", "")
    _, admin, _ = register_and_token(client, role="administrator")
    author_id, [rid] = _author_with_reviews(client, 1)
    for _, headers in _voters(client, 3, mature=False):
        _upvote(client, headers, rid, "198.51.100.77")
    db = SessionLocal()
    try:
        assert db.scalar(select(func.count(VoteNetworkFingerprint.id)).where(
            VoteNetworkFingerprint.review_id == uuid.UUID(rid))) == 0
    finally:
        db.close()
    assert _network_reports(client, _auth(admin), author_id) == []


@requires_db
def test_no_address_column_exists_and_old_rows_are_purged(client, behind_vercel):
    from app.services.retention_service import run_retention_sweep

    db = SessionLocal()
    try:
        columns = {c["name"] for c in inspect(db.get_bind()).get_columns(
            "vote_network_fingerprints")}
        assert columns == {"id", "review_id", "voter_id", "author_id", "network",
                           "new_account", "created_at"}
    finally:
        db.close()
    author_id, [rid] = _author_with_reviews(client, 1)
    [(voter_id, headers)] = _voters(client, 1, mature=True)
    _upvote(client, headers, rid, _ip())
    db = SessionLocal()
    try:
        row = db.scalar(select(VoteNetworkFingerprint).where(
            VoteNetworkFingerprint.review_id == uuid.UUID(rid)))
        row.created_at = datetime.now(UTC) - timedelta(
            days=settings.vote_network_retention_days + 1)
        db.commit()
        assert run_retention_sweep(db)["vote_network_fingerprints"] >= 1
        assert db.scalar(select(func.count(VoteNetworkFingerprint.id)).where(
            VoteNetworkFingerprint.review_id == uuid.UUID(rid))) == 0
    finally:
        db.close()

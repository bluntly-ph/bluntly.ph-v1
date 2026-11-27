"""Vote farming from one network: a moderation signal (QA, 2026-09-29).

"IP detection to identify possible anomalous voting or vote farming." Several
accounts on one network up-voting the same member is worth a look. It is NOT
proof: a household, an office, a school or a mobile carrier's shared address
(carrier-grade NAT) puts honest people on one network every day. So this is a
SIGNAL only. It files a SYSTEM_DETECTED report on the member for an
Administrator; it never removes a vote, strikes, bans, holds money or touches
anyone's trust (Business Rules §12).

WHAT IS STORED. Never an IP address. The trusted client IP
(`core/client_ip.py`; forwarding headers a client can write are ignored) is
reduced to its network (the address for IPv4, the /64 for IPv6, since one
home rotates through its /64), then HMAC-SHA256'd under a key derived from the
server secret `PII_HASH_SALT` and truncated to 32 hex characters. Without the
secret it cannot be reversed or compared across systems. Rows are deleted after
`vote_network_retention_days` (30). No API returns the hash, and reports carry
counts and ids, never a network.

THE RULE (configurable, `settings.vote_network_*`), per member, over the last
`vote_network_window_hours` (72) of up-votes on their reviews, grouped by
network:

* at least `vote_network_min_accounts` (3) distinct accounts on one network,
  of which at least `vote_network_min_new_accounts` (2) were under 30 days old
  when they voted: fresh accounts clustered on one network; or
* at least `vote_network_large_cluster` (5) distinct accounts on one network
  casting at least `vote_network_large_cluster_upvotes` (10) up-votes on the
  member's reviews, whatever their age.

Three long-standing accounts in one home up-voting a relative never meet it.
No approved threshold exists in the Business Rules; these are conservative
engineering thresholds for FLAGGING ONLY, documented in
docs/ANTI_FARMING_AND_PLAGIARISM.md.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.client_ip import trusted_client_ip
from app.core.config import settings
from app.core.constants import ACCOUNT_MATURATION_DAYS
from app.models.enums import ModerationReason, ModerationTargetType
from app.models.integrity import VoteNetworkFingerprint
from app.models.user import User

log = logging.getLogger(__name__)

SIGNAL = "shared_network_votes"
SEVERITY = 0.8
ALGORITHM_VERSION = "net-hmac-v1"


def network_of(ip: str) -> str:
    """The network an address stands for: IPv4 as is, IPv6 by its /64."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def network_hash(ip: str) -> str:
    """Keyed, truncated, irreversible without the server secret."""
    key = hmac.new(settings.pii_hash_salt.encode(), b"vote-network-v1",
                   hashlib.sha256).digest()
    return hmac.new(key, network_of(ip).encode(), hashlib.sha256).hexdigest()[:32]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def record_upvote(db: Session, request: Request, *, review_id: uuid.UUID,
                  author_id: uuid.UUID | None, voter: User,
                  now: datetime | None = None) -> bool:
    """Record one up-vote's network and re-check its author. Returns True when a
    report was filed or updated. The caller isolates failures and commits."""
    ip = trusted_client_ip(request)
    if ip is None or author_id is None or author_id == voter.id:
        return False
    now = now or datetime.now(UTC)
    network = network_hash(ip)
    new_account = (now - _aware(voter.created_at)) < timedelta(days=ACCOUNT_MATURATION_DAYS)
    db.execute(insert(VoteNetworkFingerprint).values(
        review_id=review_id, voter_id=voter.id, author_id=author_id, network=network,
        new_account=new_account, created_at=now,
    ).on_conflict_do_update(
        constraint="uq_vote_network_review_voter",
        set_={"network": network, "new_account": new_account, "created_at": now}))
    return check_author(db, author_id, network, now=now)


def check_author(db: Session, author_id: uuid.UUID, network: str, *,
                 now: datetime) -> bool:
    since = now - timedelta(hours=settings.vote_network_window_hours)
    rows = db.execute(
        select(VoteNetworkFingerprint.voter_id, VoteNetworkFingerprint.review_id,
               VoteNetworkFingerprint.new_account)
        .where(VoteNetworkFingerprint.author_id == author_id,
               VoteNetworkFingerprint.network == network,
               VoteNetworkFingerprint.created_at >= since)).all()
    accounts = {voter for voter, _, _ in rows}
    new_accounts = {voter for voter, _, new in rows if new}
    upvotes = len(rows)
    fresh_cluster = (len(accounts) >= settings.vote_network_min_accounts
                     and len(new_accounts) >= settings.vote_network_min_new_accounts)
    large_cluster = (len(accounts) >= settings.vote_network_large_cluster
                     and upvotes >= settings.vote_network_large_cluster_upvotes)
    if not (fresh_cluster or large_cluster):
        return False
    evidence = {
        "accounts": len(accounts),
        "new_accounts": len(new_accounts),
        "upvotes": upvotes,
        "window_hours": settings.vote_network_window_hours,
        "rule": "new_accounts_clustered" if fresh_cluster else "large_cluster",
        "reviews": sorted({str(review) for _, review, _ in rows}),
        # Staff-only, to investigate; never the network, never an address.
        "voters": sorted(str(v) for v in accounts),
        "thresholds": {
            "min_accounts": settings.vote_network_min_accounts,
            "min_new_accounts": settings.vote_network_min_new_accounts,
            "large_cluster": settings.vote_network_large_cluster,
            "large_cluster_upvotes": settings.vote_network_large_cluster_upvotes,
        },
        "algorithm": ALGORITHM_VERSION,
        "detected_at": now.isoformat(),
    }
    from app.services.report_service import file_system_report
    report, _ = file_system_report(
        db, target_type=ModerationTargetType.user, target_ref=author_id, signal=SIGNAL,
        reason=ModerationReason.other, severity=SEVERITY)
    # An open report takes the latest counts: the cluster may still be growing.
    report.context = {**(report.context or {}), "evidence": evidence}
    return True


def purge_expired(db: Session, now: datetime | None = None) -> int:
    """Delete network rows past retention. The caller commits."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=settings.vote_network_retention_days)
    return db.execute(delete(VoteNetworkFingerprint).where(
        VoteNetworkFingerprint.created_at < cutoff)).rowcount or 0


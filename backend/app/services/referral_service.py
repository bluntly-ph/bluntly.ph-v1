"""Referral / affiliate link flow (M2 slice 1) — the manual, moderator-mediated
realization of the `MarketplaceIntegrationService` seam.

The moderator reviews a queued (hidden) review, generates the referral link in
their own affiliate dashboard using the user's product link, and pastes it here —
pasting a valid link both monetizes and publishes the review, atomically.
**No scraping, no marketplace API calls.** If a formal API partnership ever lands,
only this module's internals change.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Collection, Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import AppError
from app.models.comment import ReviewComment
from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationTargetType,
    Platform,
    ReferralLinkStatus,
    VerificationStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import Product, ProductPlatform
from app.models.review import ReferralLink, Review
from app.models.session import Session as ClickSession
from app.models.user import User
from app.schemas.referral import (
    QueueAuthor,
    QueueCounts,
    QueueItem,
    QueuePage,
    QueuePlatform,
    QueuePriorityAssessment,
    QueuePriorityFactor,
    QueueProduct,
    QueueSignals,
    QueueVotingEvidence,
    TierReasonOut,
    TriageOut,
)
from app.schemas.review import ReviewOut
from app.services import (
    activity_surge,
    fraud_service,
    notification_service,
    priority_triage,
    report_service,
)
from app.services.earning_track import (
    SUPERADMIN_ROUTING,
    EarningTrack,
    approved_status_for,
    effective_track,
    track_for,
    verdict_star_mismatch,
)
from app.services.moderation_priority import (
    PriorityAssessment,
    PriorityBand,
    PriorityFacts,
    PriorityLane,
    SlaState,
    evaluate_priority,
)
from app.services.pii import retention_deadlines
from app.services.priority_tiers import TIER_RANK, Tier
from app.services.ranking import (
    COLLUSION_MIN_VOTERS,
    COLLUSION_THRESHOLD,
    VELOCITY_THRESHOLD,
    VELOCITY_WINDOW_SECONDS,
)
from app.services.review_service import recompute_product_aggregates
from app.services.trust_service import recompute_user_trust

MAX_URL_LEN = 2048


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(detail: str, code: str) -> AppError:
    return AppError(detail, code=code, status_code=409, title="Conflicting state")


def sub_id_for_review(review_id: uuid.UUID) -> str:
    """The affiliate sub-ID a moderator must set when generating the link.

    Deterministic from the review id so the queue can show it BEFORE the link
    exists (the moderator needs it to create the link in their dashboard), and so
    it is reproducible for support. This is the only identifier that survives the
    round trip into the marketplace's monthly report — see
    docs/AFFILIATE_REPORT_FORMATS.md.
    """
    return f"blt_{review_id.hex[:12]}"


def _audit(db: Session, moderator_id: uuid.UUID, action: ModerationAction,
           review_id: uuid.UUID, notes: str | None = None,
           context: dict | None = None) -> None:
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=ModerationTargetType.review, target_ref=review_id,
        moderator_id=moderator_id, action=action, notes=notes, context=context,
    ))


# --- Link queries ---
def get_active_link(db: Session, review_id: uuid.UUID) -> ReferralLink | None:
    return db.scalar(select(ReferralLink).where(
        ReferralLink.review_id == review_id,
        ReferralLink.status == ReferralLinkStatus.active))


def list_links(db: Session, review_id: uuid.UUID) -> list[ReferralLink]:
    return list(db.scalars(select(ReferralLink)
                           .where(ReferralLink.review_id == review_id)
                           .order_by(ReferralLink.created_at.desc())))


# --- URL validation (§4) ---
def _platform_blocked(db: Session, product_id: uuid.UUID, platform: Platform) -> bool:
    """True only when an explicit non-monetizable platform row exists (Lazada A6)."""
    return db.scalar(select(ProductPlatform.id).where(
        ProductPlatform.product_id == product_id,
        ProductPlatform.platform == platform,
        ProductPlatform.is_monetizable.is_(False))) is not None


#: Marketplace short-link hosts. An affiliate dashboard mints these for ONE
#: product, so the opaque path is accepted; every other URL must visibly be a
#: product page (Business Rules §1: "never a category or search page").
_SHORT_LINK_HOSTS = {
    "shopee": ("s.shopee.ph", "shope.ee", "shp.ee"),
    "lazada": ("s.lazada.com.ph", "c.lazada.com.ph"),
    "amazon": ("amzn.to",),
}
_PRODUCT_PATHS = {
    # shopee.ph/<name>-i.<shop>.<item>  or  shopee.ph/product/<shop>/<item>
    "shopee": re.compile(r"(-i\.\d+\.\d+/?$)|(^/product/\d+/\d+/?$)", re.I),
    # lazada.com.ph/products/<name>-i<item>(-s<sku>).html  or /products/i<item>.html
    "lazada": re.compile(r"^/products/[^/]*i\d+(-s\d+)?\.html$", re.I),
    "amazon": re.compile(r"(/dp/[a-z0-9]{10})|(/gp/product/[a-z0-9]{10})", re.I),
}


def is_product_page(url: str, platform: Platform) -> bool:
    """True when `url` identifies one product, not a store, search or category."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in _SHORT_LINK_HOSTS.get(platform.value, ())):
        return True
    pattern = _PRODUCT_PATHS.get(platform.value)
    return bool(pattern and pattern.search(parts.path or ""))


def validate_affiliate_url(db: Session, url: str, platform: Platform,
                           product_id: uuid.UUID) -> None:
    def fail(rule: str) -> AppError:
        return AppError(f"Affiliate URL rejected: {rule}.", code="affiliate_url_invalid",
                        status_code=422, title="Invalid affiliate URL",
                        extra={"rule": rule, "platform": platform.value})

    if not url or len(url) > MAX_URL_LEN:
        raise fail("url_too_long_or_empty")
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise fail("not_https")
    if "@" in (parts.netloc or ""):
        raise fail("userinfo_not_allowed")
    host = (parts.hostname or "").lower()
    if not host:
        raise fail("no_host")
    allowed = settings.affiliate_domains.get(platform.value, [])
    if not any(host == d or host.endswith("." + d) for d in allowed):
        raise fail("domain_not_allowed")
    if not is_product_page(url, platform):
        raise fail("not_product_page")
    if _platform_blocked(db, product_id, platform):
        raise fail("platform_not_monetizable")


# --- Moderator actions ---
def _require_public(review: Review) -> None:
    """Earning decisions are about a live review. A review a moderator has
    taken down is restored first (`restore`), then decided."""
    if review.published_at is None:
        raise _conflict("This review is not public; restore it before deciding its earnings.",
                        "not_published")


def _require_thread_root(review: Review) -> None:
    """A thread earns through its original review, where the link lives (§4)."""
    if not review.is_thread_root:
        raise _conflict("Earnings are decided on the thread's original review.",
                        "not_thread_root")


def _refuse_seller_author(db: Session, review: Review) -> None:
    """§9: a claimed seller account never earns, on anything."""
    author = db.get(User, review.author_id) if review.author_id else None
    if author is not None and author.is_claimed_seller:
        raise _conflict("A claimed seller account can't earn from reviews.",
                        "seller_cannot_earn")


def has_ownership_evidence(review: Review) -> bool:
    """§3's "Photo provided": a verified photo of the item, or a receipt."""
    return review.verification_status == VerificationStatus.verified or bool(review.receipt_key)


def _require_ownership_evidence(review: Review) -> None:
    """§3: earning requires a photo of the item or a receipt ("Photo provided")."""
    if not has_ownership_evidence(review):
        raise _conflict("Only reviews with a photo of the item or a receipt can earn.",
                        "review_not_verified")


def thread_track(db: Session, review: Review) -> EarningTrack:
    """The track the thread's LATEST entry selects (§14), with a Super Admin's
    2.5 routing decision applied (owner decision A)."""
    from app.services.review_service import latest_entry
    latest = latest_entry(db, review.thread_key) or review
    root = db.get(Review, review.thread_key) if review.thread_key != review.id else review
    return effective_track(track_for(latest.verdict, latest.star_rating),
                           getattr(root, "special_route", None))


def _require_routed(track: EarningTrack) -> EarningTrack:
    """Refuse anything that needs a destination the Super Admin has not given."""
    if track == SUPERADMIN_ROUTING:
        raise _conflict("This review is \"It depends\" at 2.5 stars: a Super Admin decides "
                        "whether its earnings go to the Honesty Fund or the platform.",
                        "earning_track_pending_superadmin_routing")
    return track


def _after_moderator_approval(db: Session, review: Review) -> None:
    """What a moderator's publish used to trigger, now that approval is the
    human decision: the author's trust (which counts moderator-decided
    reviews — trust_service.TRUST_COUNTED_STATUSES) and the legacy publish
    tokens (first approval only; uq_token_once absorbs repeats)."""
    if review.author_id is None:
        return
    from app.services.token_service import award_review_published
    award_review_published(db, review.author_id, review.id)
    recompute_user_trust(db, review.author_id)


def _audit_cold_start(db: Session, review: Review, moderator_id: uuid.UUID) -> None:
    """§2: before enough trust-weighted voters exist, an admin's own approval can
    stand in for the community threshold. It is logged as its own action —
    never as a vote, never inside the Wilson math — because one person
    deciding who earns is an insider risk that needs its own audit trail."""
    from app.services import earn_gate
    state = earn_gate.gate_state(db, review.id)
    _audit(db, moderator_id, ModerationAction.cold_start_substitution, review.id,
           context={"gate_passed": state.passes,
                    "wilson_lower_bound": state.wilson_lower_bound,
                    "stage2_plus_voters": state.stage2_plus_voters,
                    "voters": state.voters})


def attach_link_and_publish(db: Session, review: Review, moderator_id: uuid.UUID,
                            url: str, platform: Platform,
                            sub_id: str | None = None) -> Review:
    """Approve earnings on the commission track by attaching the affiliate link.

    Name kept for its callers; it publishes nothing (a review is public from
    submission). Only the commission track carries a link (§14), and the link
    must point at the exact product page (§1). No contract: every monetized
    review earns indefinitely until deleted or its author is banned.
    """
    _require_public(review)
    _require_thread_root(review)
    _refuse_seller_author(db, review)
    track = _require_routed(thread_track(db, review))
    if track != EarningTrack.commission:
        raise _conflict("This review's verdict routes it to the Honesty Fund; approve "
                        "earnings without a link instead.", "fund_track_no_link")
    _require_ownership_evidence(review)
    if get_active_link(db, review.id) is not None:
        raise _conflict("This review already has an active referral link.",
                        "active_link_exists")
    validate_affiliate_url(db, url, platform, review.product_id)

    was_undecided = review.earn_eligible_status == EarnEligibleStatus.none
    # Attribution key (M3 slice 12). Defaults to the review's deterministic
    # sub-ID; a moderator may override it to match what they actually typed into
    # the affiliate dashboard. `sub_id_in_url` records whether the pasted link
    # visibly carries it — a false here means the monthly report will very likely
    # come back unattributable for this link.
    effective_sub_id = (sub_id or sub_id_for_review(review.id)).strip()
    db.add(ReferralLink(review_id=review.id, platform=platform, url=url,
                        status=ReferralLinkStatus.active,
                        sub_id=effective_sub_id,
                        sub_id_in_url=effective_sub_id in url,
                        review_version=review.current_version, created_by=moderator_id))
    review.affiliate_link = url
    review.earn_eligible_status = EarnEligibleStatus.monetized
    _audit(db, moderator_id, ModerationAction.affiliate_link_attach, review.id,
           context={"platform": platform.value, "url": url, "track": track.value})
    if was_undecided:
        _audit_cold_start(db, review, moderator_id)
    _after_moderator_approval(db, review)
    notification_service.review_decided(db, review, "earnings_approved")
    db.commit()
    db.refresh(review)
    return review


def approve_earnings(db: Session, review: Review, moderator_id: uuid.UUID) -> Review:
    """The moderator's earnings approval, without a link.

    The verdict decides the track (§14): the commission track lands on
    `approved` ("may earn, affiliate link not attached yet" — the admin's
    awaiting-affiliate list), the fund track on `honesty_fund`.

    Works from `none` too: before the community gate queues a review, this is
    the cold-start substitution §2 allows, audited as its own action.
    """
    _require_public(review)
    _require_thread_root(review)
    if review.earn_eligible_status in (EarnEligibleStatus.approved, EarnEligibleStatus.monetized,
                                       EarnEligibleStatus.honesty_fund,
                                       EarnEligibleStatus.pending_superadmin_routing):
        raise _conflict("Earnings are already approved for this review.",
                        "earnings_already_decided")
    _refuse_seller_author(db, review)
    track = thread_track(db, review)
    _require_ownership_evidence(review)
    was_undecided = review.earn_eligible_status == EarnEligibleStatus.none
    review.earn_eligible_status = approved_status_for(track)
    escalated = track == SUPERADMIN_ROUTING
    # Owner decision A: the administrator approves THAT it may earn; for 2.5
    # "It depends" only a Super Admin decides WHERE. Escalation is audited as
    # its own action so the Super Admin queue's history reads plainly.
    _audit(db, moderator_id,
           ModerationAction.escalate if escalated else ModerationAction.approve, review.id,
           context={"routed_to": review.earn_eligible_status.value, "track": track.value})
    if was_undecided:
        _audit_cold_start(db, review, moderator_id)
    _after_moderator_approval(db, review)
    if not escalated:
        # The author hears the outcome once there is one: for an escalated
        # review, from the Super Admin's routing decision.
        notification_service.review_decided(db, review, "earnings_approved")
    db.commit()
    db.refresh(review)
    return review


#: The old name, kept so the deprecated `/publish` route and any script still
#: resolve. It never publishes now; it approves earnings.
publish_without_link = approve_earnings


def reject(db: Session, review: Review, moderator_id: uuid.UUID, reason: str) -> Review:
    """Decline earnings. The review stays public — that is a separate question,
    answered by `unpublish` if the content itself has to come down."""
    if review.earn_eligible_status == EarnEligibleStatus.rejected:
        raise _conflict("Earnings are already rejected for this review.",
                        "earnings_already_decided")
    if get_active_link(db, review.id) is not None:
        raise _conflict("Revoke the active referral link before rejecting earnings.",
                        "active_link_exists")
    review.earn_eligible_status = EarnEligibleStatus.rejected
    _audit(db, moderator_id, ModerationAction.reject, review.id, notes=reason)
    if review.author_id is not None:
        recompute_user_trust(db, review.author_id)  # a rejected review stops counting
    # FR-3: a rejection reaches the author with its reason (1.6, 3.12).
    notification_service.review_decided(db, review, "earnings_rejected", reason)
    db.commit()
    db.refresh(review)
    return review


def revoke_link(db: Session, review: Review, moderator_id: uuid.UUID, reason: str) -> Review:
    link = get_active_link(db, review.id)
    if link is None:
        raise _conflict("No active referral link to revoke.", "no_active_link")
    link.status = ReferralLinkStatus.revoked
    link.revoked_by = moderator_id
    link.revoked_at = _now()
    link.revoke_reason = reason
    review.affiliate_link = None
    # Content stays published; monetization drops back to approved (link pending).
    review.earn_eligible_status = EarnEligibleStatus.approved
    _audit(db, moderator_id, ModerationAction.affiliate_link_revoke, review.id, notes=reason)
    db.commit()
    db.refresh(review)
    return review


def unpublish(db: Session, review: Review, moderator_id: uuid.UUID,
              reason: str | None) -> Review:
    """Take a review off the public site (content moderation).

    Publication and earning are separate since 2026-09-22, so this leaves the
    earning state alone: `restore` puts the review back exactly as it was. The
    redirect and the Honesty Fund both require a public review, so a taken-down
    review cannot pay while it is down. It stays reachable in the moderator's
    queue as a `taken_down` card (see `_all_queue_candidates`), so it is never
    stranded — the property the old re-queue-as-pending existed to protect.
    """
    reason = (reason or "").strip()
    if not reason:
        # Owner decision 2026-09-28: a take-down always says why. The author is
        # told the reason, and the audit row carries it.
        raise AppError("Give the reason this review is being taken down.",
                       code="takedown_reason_required", status_code=422,
                       title="Unprocessable content")
    if review.published_at is None:
        raise _conflict("Review is not published.", "not_published")
    previous_published_at = review.published_at
    review.published_at = None
    _audit(db, moderator_id, ModerationAction.unpublish, review.id, notes=reason,
           context={"previous_status": review.earn_eligible_status.value,
                    "previous_published_at": _as_utc(previous_published_at).isoformat()})
    notification_service.review_decided(db, review, "unpublished", reason)
    recompute_product_aggregates(db, review.product_id)
    if review.author_id is not None:
        recompute_user_trust(db, review.author_id)
    db.commit()
    db.refresh(review)
    return review


def restore(db: Session, review: Review, moderator_id: uuid.UUID) -> Review:
    """Put an unpublished review on the public site.

    A review a moderator took down returns at its original publication time,
    read back from the take-down's audit row. One that was never public — held
    under the pre-2026-09-22 hide-until-approved flow — is published at its
    submission time, which is what `published_at` means now.
    """
    if review.published_at is not None:
        raise _conflict("Review is already public.", "already_published")
    if review.is_removed:
        raise _conflict("A removed review cannot be restored.", "review_removed")
    last = db.scalar(
        select(ModerationLog).where(ModerationLog.target_ref == review.id,
                                    ModerationLog.action == ModerationAction.unpublish)
        .order_by(ModerationLog.created_at.desc()).limit(1))
    original = None
    if last is not None and isinstance(last.context, dict):
        raw = last.context.get("previous_published_at")
        if raw:
            try:
                original = datetime.fromisoformat(raw)
            except ValueError:
                original = None
    review.published_at = original or review.created_at or _now()
    _audit(db, moderator_id, ModerationAction.restore, review.id,
           context={"restored_published_at": _as_utc(review.published_at).isoformat()})
    notification_service.review_decided(db, review, "restored")
    recompute_product_aggregates(db, review.product_id)
    if review.author_id is not None:
        recompute_user_trust(db, review.author_id)
    db.commit()
    db.refresh(review)
    return review


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Click attribution (§3 GET /r/{id}) ---

# Marketplaces that echo custom sub-IDs back to us on conversion. Lazada does so
# through its postback macros and its /marketing/conversion/report API; Shopee's
# programme has no equivalent, so its links are passed through untouched and
# reconciled from the monthly CSV.
_SUB_ID_PLATFORMS = {Platform.lazada}


def decorate_affiliate_url(url: str, platform: Platform, sub_id: str | None,
                           click_ref: str) -> str:
    """Append our attribution keys to an outbound affiliate URL.

    `sub_id1` carries the review, `sub_id2` the individual click. Without
    `sub_id2` a conversion can only be traced to the review — which is what the
    monthly CSV already gives us — so this is what buys per-click attribution.

    Existing parameters win: if the moderator already typed a `sub_id1` into the
    dashboard when generating the link, theirs is what Lazada has on file and
    overwriting it here would break their reporting. Lazada's own guidance also
    reserves `sub_aff_id` for sub-affiliate channels, so it is never used as a
    click id (their troubleshooting note #4).
    """
    if platform not in _SUB_ID_PLATFORMS:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if sub_id and not query.get("sub_id1"):
        query["sub_id1"] = sub_id
    if not query.get("sub_id2"):
        query["sub_id2"] = click_ref
    return urlunsplit(parts._replace(query=urlencode(query)))


def record_click(db: Session, review: Review, link: ReferralLink,
                 user_id: uuid.UUID | None, user_agent: str | None,
                 ip_address: str | None) -> str:
    """Create a `sessions` click row with the PII retention schedule; return the
    destination affiliate URL to redirect to."""
    now = _now()
    deadlines = retention_deadlines(now)
    click_ref = f"ref_{uuid.uuid4().hex[:12]}"
    destination = decorate_affiliate_url(link.url, link.platform, link.sub_id, click_ref)
    db.add(ClickSession(
        session_id=f"clk_{uuid.uuid4().hex[:12]}",
        review_id=review.id, product_id=review.product_id, user_id=user_id,
        # Store where the user was actually sent, decoration included — otherwise
        # a support question about a conversion cannot be answered from the row.
        destination_url=destination, platform=link.platform,
        click_ref=click_ref,
        clicked_at=now, user_agent=user_agent, ip_address=ip_address,
        ua_purge_at=deadlines["ua_purge_at"], ip_hash_at=deadlines["ip_hash_at"],
        ip_delete_at=deadlines["ip_delete_at"],
    ))
    db.commit()
    return destination


# --- Moderator queue (§3 GET /admin/review-queue) ---
def get_queue(db: Session, limit: int = 50, offset: int = 0) -> tuple[list[Review], list[Review]]:
    """Return (pending reviews, monetized-but-edited-since reviews)."""
    pending = list(db.scalars(
        select(Review)
        .where(Review.earn_eligible_status == EarnEligibleStatus.pending,
               Review.published_at.isnot(None), Review.is_removed.is_(False))
        .order_by(Review.created_at.asc()).limit(limit).offset(offset)))

    edited = list(db.scalars(
        select(Review)
        .join(ReferralLink, ReferralLink.review_id == Review.id)
        .where(Review.earn_eligible_status == EarnEligibleStatus.monetized,
               ReferralLink.status == ReferralLinkStatus.active,
               Review.current_version > ReferralLink.review_version,
               Review.is_removed.is_(False))
        .order_by(Review.updated_at.desc())))
    return pending, edited


# --- Canonical, server-side prioritized queue (design §5) ------------------- #
#
# `get_queue` above is the pre-priority view: pending sorted by age, edited by
# recency, each paged in SQL. It stays for the deprecated `pending` /
# `edited_since_monetized` response arrays. The prioritized queue below loads the
# WHOLE backlog, runs the pure policy evaluator on every candidate, and only then
# orders and pages — so a high-priority review is on page one even when it was
# created after the first fifty.

_QueueKind = Literal["pending", "edited", "taken_down"]

_BASIS_FOR_KIND: dict[_QueueKind, Literal["review_created_at", "review_updated_at"]] = {
    "pending": "review_created_at",
    "edited": "review_updated_at",
    "taken_down": "review_updated_at",
}


@dataclass(frozen=True)
class QueueQuery:
    """Server-side filters + paging for the prioritized review queue.

    Ordering is by policy alone (assessment order key, then review id); ``offset``
    only picks which already-ordered slice to return. ``cursor`` is accepted for
    forward compatibility and unused in this slice.
    """

    band: PriorityBand | None = None
    lane: PriorityLane | None = None
    sla: SlaState | None = None
    factor: str | None = None
    q: str | None = None
    #: Admin priority tier filter ("highest" … "lowest"), dev note 2026-09-26.
    tier: str | None = None
    #: "policy" (lane/SLA order, the default), "tier" (priority tier, then the
    #: oldest clock) or "oldest" (arrival order).
    sort: str = "policy"
    #: MQA-015: "waiting" (the default) is the work - reviews waiting for a
    #: decision. "taken_down" lists the reviews a moderator took off the site:
    #: decided, so out of the working list and its counts, but one switch away
    #: with the same card and its Restore.
    view: str = "waiting"
    limit: int = 50
    offset: int = 0
    cursor: str | None = None


@dataclass(frozen=True)
class _AssessedCard:
    review_id: uuid.UUID
    kind: _QueueKind
    item: QueueItem
    order_key: tuple
    #: The row itself, so a caller aggregating the whole queue (the admin
    #: Overview) can read its columns without re-querying what this pass loaded.
    review: Review
    #: Distinct reports filed against this review. Carried separately from the
    #: assessment because "reported" is its own question: the Overview's
    #: Flagged bar counts reported targets, not High ones.
    report_count: int


_QUERY_CHUNK_SIZE = 500


def _chunks(values: Collection[uuid.UUID]) -> Iterator[tuple[uuid.UUID, ...]]:
    items = tuple(dict.fromkeys(values))
    for start in range(0, len(items), _QUERY_CHUNK_SIZE):
        yield items[start : start + _QUERY_CHUNK_SIZE]


def _ensure_utc(value: datetime) -> datetime:
    """DB timestamps are ``timestamptz`` (aware); coerce any stray naive value to
    UTC so the pure evaluator never rejects a real queue candidate."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def assessment_to_queue_schema(assessment: PriorityAssessment) -> QueuePriorityAssessment:
    """Map the pure-policy dataclass onto the wire schema (design §5). The
    internal ``order_key`` is deliberately not serialized — ordering is the
    server's job, not the client's."""
    return QueuePriorityAssessment(
        policy_version=assessment.policy_version,
        lane=assessment.lane,
        score=assessment.integrity_score,
        band=assessment.band,
        sla_state=assessment.sla_state,
        due_at=assessment.due_at,
        factors=[
            QueuePriorityFactor(
                code=factor.code,
                observed=factor.observed,
                contribution=factor.contribution,
                explanation=factor.explanation,
            )
            for factor in assessment.factors
        ],
        origins=list(assessment.origins),
    )


def _all_queue_candidates(db: Session) -> list[tuple[Review, _QueueKind]]:
    """Every review currently in the moderator queue, unpaginated.

    Same membership rules as ``get_queue``, without its limit/offset: the
    prioritized queue must see the whole backlog to place work correctly.
    """
    # Taken down = unpublished with an audited take-down. Only a moderator
    # can take a review off the site now, and that is always recorded.
    took_down = select(ModerationLog.id).where(
        ModerationLog.target_ref == Review.id,
        ModerationLog.action == ModerationAction.unpublish).exists()
    # Awaiting a first earnings decision: public reviews the gate (or Seeding)
    # queued, plus legacy rows held unpublished under the pre-2026-09-22 flow
    # that nobody has decided yet — those stay reachable exactly as before.
    pending = db.scalars(
        select(Review).where(
            Review.earn_eligible_status == EarnEligibleStatus.pending,
            Review.is_removed.is_(False),
            Review.published_at.isnot(None) | ~took_down,
        ).order_by(Review.created_at.asc())
    ).all()
    # Taken down by a moderator: off the site, and needing a restore or a
    # decision — never stranded where no moderator screen can reach it.
    taken_down = db.scalars(
        select(Review).where(
            Review.published_at.is_(None),
            Review.is_removed.is_(False),
            took_down,
        ).order_by(Review.updated_at.desc())
    ).all()
    # The old "edited since monetized" re-check is retired (Business Rules §4):
    # published content cannot be edited, so the case it existed for cannot
    # happen. The one allowed photo swap is audited on its own.
    taken_ids = {r.id for r in taken_down}
    return ([(r, "pending") for r in pending if r.id not in taken_ids]
            + [(r, "taken_down") for r in taken_down])


def _build_assessed_cards(
    db: Session,
    reviews: list[tuple[Review, _QueueKind]],
    *,
    now: datetime | None = None,
) -> list[_AssessedCard]:
    """Build one queue card + priority assessment per (review, kind).

    Product, author, report, and fraud facts are all loaded in bounded batches.
    No fact source performs a query per review.
    """
    evaluated_at = _ensure_utc(now) if now is not None else datetime.now(UTC)
    if not reviews:
        return []

    product_ids = {review.product_id for review, _ in reviews}
    products: dict[uuid.UUID, Product] = {}
    for chunk in _chunks(product_ids):
        products.update(
            (product.id, product)
            for product in db.scalars(
                select(Product)
                .options(selectinload(Product.platforms))
                .where(Product.id.in_(chunk))
            )
        )
    author_ids = {review.author_id for review, _ in reviews if review.author_id}
    authors: dict[uuid.UUID, User] = {}
    for chunk in _chunks(author_ids):
        authors.update(
            (user.id, user)
            for user in db.scalars(select(User).where(User.id.in_(chunk)))
        )

    report_facts = report_service.report_facts_by_target(
        db, ModerationTargetType.review, [review.id for review, _ in reviews]
    )
    # One grouped count for the whole page rather than one per card.
    comment_counts = dict(
        db.execute(
            select(ReviewComment.review_id, func.count(ReviewComment.id))
            .where(
                ReviewComment.review_id.in_([review.id for review, _ in reviews]),
                ReviewComment.is_removed.is_(False),
            )
            .group_by(ReviewComment.review_id)
        ).all()
    )
    evidence_by_review: dict[uuid.UUID, dict] = {}
    signals_by_review = fraud_service.compute_signals_by_review(
        db,
        [review for review, _ in reviews],
        authors,
        now=evaluated_at,
        evidence=evidence_by_review,
    )
    surging = activity_surge.surges_for(db, [review.id for review, _ in reviews],
                                        now=evaluated_at)

    cards: list[_AssessedCard] = []
    for review, kind in reviews:
        product = products.get(review.product_id)
        author = authors.get(review.author_id) if review.author_id else None
        signals = signals_by_review[review.id]
        edited = kind == "edited"

        # Temporary queue-entry-time approximation (no lifecycle column yet):
        # creation for an initial pending review, last edit for an edited one.
        queued_at = _ensure_utc(
            review.created_at if kind == "pending" else review.updated_at
        )
        facts = report_facts.get(review.id, report_service.NO_REPORTS)
        assessment = evaluate_priority(
            PriorityFacts(
                queued_at=queued_at,
                report_count=facts.count,
                report_reasons=facts.reasons,
                edited_since_monetized=edited,
                velocity=signals["velocity"],
                collusion=signals["collusion"],
                duplicate_content=signals["duplicate_content"],
                manually_escalated=False,
                weighted_reports=facts.weighted,
                report_surge=facts.surge,
                activity_surge=surging.get(review.id, False),
                verdict_star_mismatch=verdict_star_mismatch(review.verdict, review.star_rating),
                system_reports=facts.system,
            ),
            now=evaluated_at,
        )

        platforms = list(product.platforms) if product is not None else []
        item = QueueItem(
            review=ReviewOut.model_validate(review),
            product=QueueProduct(
                id=product.id if product is not None else review.product_id,
                canonical_name=product.canonical_name if product is not None else None,
                source_url=product.source_url if product is not None else None,
                platforms=[
                    QueuePlatform(platform=p.platform, is_monetizable=p.is_monetizable)
                    for p in platforms
                ],
            ),
            author=(
                QueueAuthor(
                    id=author.id,
                    display_name=author.display_name,
                    trust_stage=author.trust_stage,
                    reputation_score=author.reputation_score,
                    verified_review_count=author.verified_review_count,
                )
                if author is not None
                else None
            ),
            suggested_platform=suggested_platform_from(product, platforms),
            edited_since_monetized=edited,
            comment_count=comment_counts.get(review.id, 0),
            signals=QueueSignals(**signals),
            voting=QueueVotingEvidence(
                upvoters=evidence_by_review.get(review.id, {}).get("upvoters", 0),
                reciprocal_upvoters=evidence_by_review.get(review.id, {}).get(
                    "reciprocal_upvoters", 0),
                min_upvoters=COLLUSION_MIN_VOTERS, threshold=COLLUSION_THRESHOLD,
                max_upvotes_in_velocity_window=evidence_by_review.get(review.id, {}).get(
                    "max_upvotes_in_velocity_window", 0),
                velocity_window_seconds=VELOCITY_WINDOW_SECONDS,
                velocity_threshold=VELOCITY_THRESHOLD,
            ),
            priority=assessment_to_queue_schema(assessment),
            queue_time_basis=_BASIS_FOR_KIND[kind],
            suggested_sub_id=sub_id_for_review(review.id),
        )
        cards.append(
            _AssessedCard(
                review_id=review.id,
                kind=kind,
                item=item,
                order_key=assessment.order_key,
                review=review,
                report_count=facts.count,
            )
        )
    return cards


def _card_matches(card: _AssessedCard, query: QueueQuery) -> bool:
    if (card.kind == "taken_down") != (query.view == "taken_down"):
        return False
    priority = card.item.priority
    if query.tier is not None and (card.item.triage is None
                                   or card.item.triage.tier != query.tier):
        return False
    if query.band is not None and priority.band != query.band:
        return False
    if query.lane is not None and priority.lane != query.lane:
        return False
    if query.sla is not None and priority.sla_state != query.sla:
        return False
    if query.factor is not None and query.factor not in {f.code for f in priority.factors}:
        return False
    if query.q and query.q.strip():
        needle = query.q.strip().lower()
        haystack = " ".join(
            part
            for part in (
                card.item.review.title,
                card.item.review.discussion,
                card.item.product.canonical_name,
            )
            if part
        ).lower()
        if needle not in haystack:
            return False
    return True


def _queue_counts(cards: list[_AssessedCard]) -> QueueCounts:
    by_lane = {lane.value: 0 for lane in PriorityLane}
    by_band = {band.value: 0 for band in PriorityBand}
    by_sla = {state.value: 0 for state in SlaState}
    by_tier = {tier.value: 0 for tier in Tier}
    for card in cards:
        priority = card.item.priority
        by_lane[priority.lane.value] += 1
        by_band[priority.band.value] += 1
        by_sla[priority.sla_state.value] += 1
        if card.item.triage is not None:
            by_tier[card.item.triage.tier] += 1
    return QueueCounts(
        total=len(cards), by_lane=by_lane, by_band=by_band, by_sla=by_sla,
        by_tier=by_tier,
    )


def _paginate_cards(cards: list[_AssessedCard], query: QueueQuery) -> QueuePage:
    limit = max(1, min(query.limit, 100))
    offset = max(0, query.offset)

    filtered = [card for card in cards if _card_matches(card, query)]
    # A total order in every mode (review id breaks ties), so repeated calls
    # are stable and `offset` is a pure index into an already-correct sequence.
    if query.sort == "tier":
        filtered.sort(key=lambda card: (_tier_key(card), card.review_id))
    elif query.sort == "oldest":
        filtered.sort(key=lambda card: (_clock_of(card), card.review_id))
    else:
        filtered.sort(key=lambda card: (card.order_key, card.review_id))

    counts = _queue_counts(filtered)
    # The tier chips are the tier filter's own toggles, so each counts what
    # selecting it would show: every other filter applied, the tier left out.
    # Counted over `filtered`, choosing "Highest" read every other tier as 0
    # until it was cleared again (dev/QA sync 2026-09-29, ENG-0929-F).
    if query.tier is not None:
        untiered = replace(query, tier=None)
        counts.by_tier = _queue_counts(
            [card for card in cards if _card_matches(card, untiered)]).by_tier
    # The view switch's own counts: every other filter applied, each view's.
    counts.by_view = {view: sum(1 for card in cards
                                if _card_matches(card, replace(query, view=view)))
                      for view in QUEUE_VIEWS}
    window = filtered[offset : offset + limit]
    return QueuePage(
        items=[card.item for card in window],
        total=len(filtered),
        next_cursor=None,
        counts=counts,
    )


QUEUE_VIEWS = ("waiting", "taken_down")


def _clock_of(card: _AssessedCard) -> datetime:
    if card.item.triage is not None:
        return card.item.triage.clock_started_at
    return card.order_key[4]


def _tier_key(card: _AssessedCard) -> tuple:
    triage = card.item.triage
    rank = TIER_RANK[Tier(triage.tier)] if triage is not None else TIER_RANK[Tier.neutral]
    return (rank, _clock_of(card))


def attach_triage(db: Session, cards: list[_AssessedCard], *,
                  now: datetime | None = None) -> None:
    """Label every card with its admin priority tier (dev note 2026-09-26).

    Read-only: the tier sorts and filters what is already queued and never
    changes membership or any review's state.
    """
    targets = priority_triage.earnings_targets(db, [(c.review, c.kind) for c in cards])
    triaged = priority_triage.assess(db, targets, now=now)
    for card in cards:
        tri = triaged.get((priority_triage.EARNINGS, ModerationTargetType.review.value,
                           card.review_id))
        card.item.triage = triage_out(tri) if tri is not None else None


def review_queue_cards(db: Session, review_ids: Collection[uuid.UUID]
                       ) -> dict[uuid.UUID, QueueItem]:
    """The Review Queue card for each of these reviews, built by the queue's own
    `_build_assessed_cards` - so the Reports view's integrity signals (MQA-003)
    are the queue's signals, never a second computation that could disagree.
    Batched like the queue page: a few queries whatever the number of reviews.
    """
    ids = list(dict.fromkeys(review_ids))
    if not ids:
        return {}
    reviews = list(db.scalars(select(Review).where(Review.id.in_(ids))))
    return {card.review_id: card.item
            for card in _build_assessed_cards(db, [(r, "pending") for r in reviews])}


def triage_out(tri: priority_triage.Triage) -> TriageOut:
    a = tri.assessment
    return TriageOut(
        tier=a.tier.value, base_tier=a.base_tier.value, aged=a.aged,
        aged_at=tri.aged_at, clock_started_at=tri.clock_started_at,
        routine_spot_check=a.routine_spot_check,
        reasons=[TierReasonOut(code=r.code, label=r.label, detail=r.detail)
                 for r in a.reasons],
    )


def get_prioritized_queue(
    db: Session, query: QueueQuery, *, now: datetime | None = None
) -> QueuePage:
    """Evaluate the whole moderator backlog against the priority policy, apply
    server filters, order by policy, then return the requested page (design §5).

    Ordering correctness never depends on ``offset``; ``next_cursor`` is ``None``
    in this compatibility slice.
    """
    cards = _build_assessed_cards(db, _all_queue_candidates(db), now=now)
    attach_triage(db, cards, now=now)
    return _paginate_cards(cards, query)


@dataclass(frozen=True)
class QueueAssessmentSummary:
    """The whole open backlog, assessed once (design §5).

    Exists so the Overview's headline counts and the queue list cannot disagree
    about what is High or what is late: they are the same numbers, from the same
    evaluation, not two implementations of one policy.
    """

    #: Every candidate row, in candidate-loading order.
    reviews: tuple[Review, ...]
    #: Totals by lane, band and SLA state over that whole set.
    counts: QueueCounts
    #: Ids of the candidates carrying at least one report. Reported is not a
    #: band and not a lane the Overview can read off `counts` — a reported
    #: review can sit in any band — so it is carried explicitly.
    reported_review_ids: frozenset[uuid.UUID]

    @property
    def total(self) -> int:
        return self.counts.total

    @property
    def high_priority(self) -> int:
        return self.counts.by_band.get(PriorityBand.high.value, 0)

    @property
    def approaching(self) -> int:
        return self.counts.by_sla.get(SlaState.approaching.value, 0)

    @property
    def overdue(self) -> int:
        return self.counts.by_sla.get(SlaState.overdue.value, 0)


def assess_open_queue(
    db: Session, *, now: datetime | None = None
) -> QueueAssessmentSummary:
    """Assess every open queue candidate against policy v1 and aggregate it.

    The unfiltered, unpaginated counterpart of `get_prioritized_queue`: same
    candidates, same evaluator, no page. Callers that need totals rather than a
    page (the admin Overview) use this instead of paging through the queue.
    """
    # The backlog is the work still waiting: a review a moderator took down is
    # decided (MQA-015) and is not counted as queue depth or as past due.
    cards = [card for card in _build_assessed_cards(db, _all_queue_candidates(db), now=now)
             if card.kind != "taken_down"]
    return QueueAssessmentSummary(
        reviews=tuple(card.review for card in cards),
        counts=_queue_counts(cards),
        reported_review_ids=frozenset(
            card.review_id for card in cards if card.report_count > 0
        ),
    )


def open_queue_cards(
    db: Session, *, now: datetime | None = None
) -> list[tuple[QueueItem, Review, int]]:
    """Every open queue card as (card, row, distinct report count).

    The same candidates and evaluator as `assess_open_queue`, for a caller that
    lists cards rather than counting them (the Overview's Review queue card).
    One review queued under two kinds appears once, in its first kind.
    """
    seen: set[uuid.UUID] = set()
    out: list[tuple[QueueItem, Review, int]] = []
    for card in _build_assessed_cards(db, _all_queue_candidates(db), now=now):
        if card.review_id in seen or card.kind == "taken_down":
            continue
        seen.add(card.review_id)
        out.append((card.item, card.review, card.report_count))
    return out


def suggested_platform_from(product: Product | None,
                            platforms: list[ProductPlatform]) -> Platform | None:
    """Best-guess platform from already-loaded rows (no queries): a monetizable
    product_platform, else inferred from the product's source_url host."""
    for p in platforms:
        if p.is_monetizable:
            return p.platform
    src = product.source_url if product else None
    host = (urlsplit(src).hostname or "").lower() if src else ""
    for plat, domains in settings.affiliate_domains.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return Platform(plat)
    return None


def suggested_platform(db: Session, product_id: uuid.UUID) -> Platform | None:
    """Best-guess platform for the moderator: a monetizable product_platform, else
    inferred from the product's source_url host. Thin DB-loading wrapper around
    ``suggested_platform_from`` for callers that only have a product_id."""
    product = db.get(Product, product_id)
    platforms = list(db.scalars(select(ProductPlatform).where(
        ProductPlatform.product_id == product_id)))
    return suggested_platform_from(product, platforms)

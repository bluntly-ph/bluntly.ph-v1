"""The admin Overview's "Needs attention" panel (meeting 2026-10-02).

Four groups, in the order the meeting walked them: Moderation, Integrity,
Catalog and Money. Every count is a real query, and where a queue already has a
rule for what it lists, the count reuses that rule, so the number on the
Overview cannot disagree with the list it links to:

  reviews past due        the queue assessment's own `overdue` count (the same
                          one the Overview headline and the queue use)
  answers to moderate     answers with at least one OPEN report, from a member
                          or from the system (copied-answer detection files its
                          reports into the same table). There is no separate
                          answer-approval step, so an open report is what
                          "to moderate" can truthfully mean.
  open reports            open reports, counted exactly as the Reports view
                          lists them - one per report - with the number of
                          distinct items they are on as the row's detail
                          ("on 4 items"). It used to count the items only, so the
                          Overview said 4 while the Reports tab said 6 (MQA-045).
  support requests        seller support requests not yet resolved or rejected
  under investigation     members flagged for investigation
  "It depends" routing    reviews waiting for a Super Admin's routing decision
                          (Super Admin only; left out for an Administrator)
  price submissions       community prices awaiting a decision
  products without image  catalogue products with no usable picture, by the
                          same rule the site uses to decide a photo is usable
  seller claims & appeals pending claims plus open appeals
  reviews needing a link  the affiliate-link queue's own total
  failed payouts          payouts in `failed`

Nothing is summed across groups: the same review can be both reported and past
due, so a grand total would count it twice.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationTargetType,
    PayoutStatus,
    PriceObservationStatus,
    ProductStatus,
    SellerClaimStatus,
    SupportRequestStatus,
)
from app.models.moderation import ModerationLog
from app.models.payout import Payout
from app.models.product import PriceHistory, Product
from app.models.review import Review
from app.models.seller import SellerClaim, SellerReviewAppeal
from app.models.support import SellerSupportRequest
from app.models.user import User

log = logging.getLogger(__name__)

#: The appeal states a moderator still has to act on (seller_service).
OPEN_APPEAL_STATES = ("open", "substantiation_requested")
#: Support requests that are finished (support_service.CLOSED).
#: Not waiting on a moderator: decided, or waiting for the seller (MQA-022).
CLOSED_SUPPORT_STATES = (SupportRequestStatus.resolved, SupportRequestStatus.rejected,
                         SupportRequestStatus.waiting_for_seller)


@dataclass(frozen=True)
class AttentionItem:
    key: str
    label: str
    #: None when this one count could not be computed. Never 0 in its place:
    #: a zero on this panel reads as "nothing waiting", which is a claim.
    count: int | None
    #: A second figure, named: "on 4 items". None when there is none.
    detail: str | None = None


@dataclass(frozen=True)
class AttentionGroup:
    key: str
    label: str
    items: list[AttentionItem] = field(default_factory=list)


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _open_reports(target_type: ModerationTargetType | None = None):
    stmt = select(ModerationLog.target_type, ModerationLog.target_ref).where(
        ModerationLog.action == ModerationAction.report,
        ModerationLog.resolution.is_(None),
        ModerationLog.target_ref.is_not(None),
    )
    if target_type is not None:
        stmt = stmt.where(ModerationLog.target_type == target_type)
    return stmt


def open_reports(db: Session):
    """The Reports view's own totals (report_service.count_reports, status open)."""
    from app.services import report_service
    return report_service.count_reports(db, status="open")


def answers_to_moderate(db: Session) -> int:
    answers = _open_reports(ModerationTargetType.answer).distinct().subquery()
    return _count(db, select(func.count()).select_from(answers))


def reviews_past_due(db: Session, *, now: datetime | None = None) -> int:
    from app.services import referral_service
    return int(referral_service.assess_open_queue(db, now=now).overdue)


def support_requests_open(db: Session) -> int:
    return _count(db, select(func.count(SellerSupportRequest.id)).where(
        SellerSupportRequest.status.not_in(CLOSED_SUPPORT_STATES)))


def under_investigation(db: Session) -> int:
    return _count(db, select(func.count(User.id)).where(
        User.is_under_investigation.is_(True)))


def awaiting_super_admin_routing(db: Session) -> int:
    return _count(db, select(func.count(Review.id)).where(
        Review.earn_eligible_status == EarnEligibleStatus.pending_superadmin_routing,
        Review.is_removed.is_(False)))


def products_to_review(db: Session) -> int:
    """Submitted products not in the catalogue yet: the Products Queue tab's
    count (product_queue_service.queue), which Figma's nav badge repeats."""
    return _count(db, select(func.count(Product.id)).where(
        Product.status == ProductStatus.pending))


def price_submissions(db: Session) -> int:
    return _count(db, select(func.count(PriceHistory.id)).where(
        PriceHistory.status == PriceObservationStatus.pending))


def products_without_image(db: Session) -> int:
    """Mirrors `usablePhoto` (lib/image.ts): a picture counts only if it is an
    http(s) URL and not an example.com placeholder."""
    unusable = or_(
        Product.image_url.is_(None),
        Product.image_url.not_like("http%"),
        Product.image_url.like("%example.com%"),
    )
    return _count(db, select(func.count(Product.id)).where(
        Product.status == ProductStatus.canonicalized, unusable))


def seller_claims_and_appeals(db: Session) -> int:
    claims = _count(db, select(func.count(SellerClaim.id)).where(
        SellerClaim.status == SellerClaimStatus.pending))
    appeals = _count(db, select(func.count(SellerReviewAppeal.id)).where(
        SellerReviewAppeal.status.in_(OPEN_APPEAL_STATES)))
    return claims + appeals


def reviews_needing_link(db: Session) -> int:
    from app.services import monetization_attention
    return int(monetization_attention.awaiting_affiliate_total(db))


def failed_payouts(db: Session) -> int:
    return _count(db, select(func.count(Payout.id)).where(
        Payout.status == PayoutStatus.failed))


def _safe(db: Session, key: str, fn: Callable[[], int]) -> int | None:
    """One count failing leaves the rest of the panel standing. The session is
    rolled back so the failed statement cannot poison the next query."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 - one tile degrades, the panel does not
        db.rollback()
        log.exception("needs attention: %s failed", key)
        return None


def _open_reports_item(db: Session) -> AttentionItem:
    try:
        counts = open_reports(db)
    except Exception:  # noqa: BLE001 - as _safe: this row degrades, the panel does not
        db.rollback()
        log.exception("needs attention: open_reports failed")
        return AttentionItem("open_reports", "Open reports", None)
    detail = (f"on {counts.items} item{'' if counts.items == 1 else 's'}"
              if counts.reports else None)
    return AttentionItem("open_reports", "Open reports", counts.reports, detail)


def needs_attention(db: Session, *, super_admin: bool,
                    now: datetime | None = None) -> list[AttentionGroup]:
    """The panel for one viewer. An Administrator does not see the count of a
    queue only a Super Admin can work."""
    def item(key: str, label: str, fn: Callable[[], int]) -> AttentionItem:
        return AttentionItem(key, label, _safe(db, key, fn))

    integrity = [item("under_investigation", "Under investigation",
                      lambda: under_investigation(db))]
    if super_admin:
        integrity.append(item("it_depends_routing", "\"It depends\" routing",
                              lambda: awaiting_super_admin_routing(db)))
    return [
        AttentionGroup("moderation", "Moderation", [
            item("reviews_past_due", "Reviews past due",
                 lambda: reviews_past_due(db, now=now)),
            item("answers_to_moderate", "Answers to moderate",
                 lambda: answers_to_moderate(db)),
            _open_reports_item(db),
            item("support_requests", "Support requests", lambda: support_requests_open(db)),
        ]),
        AttentionGroup("integrity", "Integrity", integrity),
        AttentionGroup("catalog", "Catalog", [
            item("products_to_review", "Products to review", lambda: products_to_review(db)),
            item("price_submissions", "Price submissions", lambda: price_submissions(db)),
            item("products_without_image", "Products without image",
                 lambda: products_without_image(db)),
            item("seller_claims_appeals", "Seller claims & appeals",
                 lambda: seller_claims_and_appeals(db)),
        ]),
        AttentionGroup("money", "Money", [
            item("reviews_needing_link", "Reviews needing a link",
                 lambda: reviews_needing_link(db)),
            item("failed_payouts", "Failed payouts", lambda: failed_payouts(db)),
        ]),
    ]

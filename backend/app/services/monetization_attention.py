"""Monetization attention: raw engagement facts and the awaiting-affiliate list.

Two things an admin needs that the moderation queue does not give them:

* **Momentum facts** — how much real attention a review is getting, as raw
  counts over the last 24 hours and 7 days. No HIGH/MEDIUM/LOW, no score: which
  numbers should move a review up the monetization list is a pending business
  rule, and a threshold invented here would become policy by accident.
* **Awaiting affiliate** — reviews whose earnings a moderator has approved on
  the affiliate path (`approved`) that still have no active referral link,
  while their product is listed on a monetizable marketplace. Where the
  marketplace cannot generate links automatically (Shopee today), this is the
  admin's to-do list.

This is deliberately separate from `moderation_priority`, which orders the
queue by integrity risk (reports, velocity, collusion, duplicates). A burst of
downvotes is a moderation signal and never counts toward monetization
attention; it is shown here only as a raw fact. None of it is on the moderator
queue cards, and none of it reads reading telemetry, which the approved design
keeps collection-only (§8, §15).

Every fact is loaded in grouped queries over the whole page — never one query
per review.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.comment import ReviewComment
from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationTargetType,
    ReferralLinkStatus,
    VoteDirection,
)
from app.models.moderation import ModerationLog
from app.models.product import Product, ProductPlatform
from app.models.review import ReferralLink, Review
from app.models.traffic import ReviewViewBucket
from app.models.user import User
from app.models.vote import ReviewVote
from app.schemas.referral import (
    AwaitingAffiliateItem,
    AwaitingAffiliatePage,
    AwaitingPlatform,
    MomentumFacts,
    MomentumWindow,
    QueuePlatform,
    QueueProduct,
)
from app.schemas.review import ReviewOut

WINDOWS = {"last_24h": timedelta(hours=24), "last_7d": timedelta(days=7)}


def momentum_by_review(db: Session, reviews: Collection[Review], *,
                       now: datetime | None = None) -> dict[uuid.UUID, MomentumFacts]:
    """Raw engagement facts for each review, in a bounded number of queries."""
    if not reviews:
        return {}
    now = now or datetime.now(UTC)
    ids = [r.id for r in reviews]
    authors = {r.id: r.author_id for r in reviews}
    since = {k: now - d for k, d in WINDOWS.items()}
    widest = since["last_7d"]
    out: dict[uuid.UUID, dict[str, MomentumWindow]] = {
        rid: {k: MomentumWindow() for k in WINDOWS} for rid in ids}

    for rid, start, n in db.execute(
            select(ReviewViewBucket.review_id, ReviewViewBucket.bucket_start,
                   ReviewViewBucket.view_count)
            .where(ReviewViewBucket.review_id.in_(ids), ReviewViewBucket.bucket_start >= widest)):
        for k, lo in since.items():
            if start >= lo:
                out[rid][k].opens += int(n)

    participants: dict[tuple[uuid.UUID, str], set] = defaultdict(set)
    for rid, voter, direction, created in db.execute(
            select(ReviewVote.review_id, ReviewVote.voter_id, ReviewVote.vote,
                   ReviewVote.created_at)
            .where(ReviewVote.review_id.in_(ids), ReviewVote.created_at >= widest)):
        for k, lo in since.items():
            if created >= lo:
                if direction == VoteDirection.up:
                    out[rid][k].upvotes += 1
                else:
                    out[rid][k].downvotes += 1
                participants[(rid, k)].add(voter)
    for rid, author, created in db.execute(
            select(ReviewComment.review_id, ReviewComment.author_id, ReviewComment.created_at)
            .where(ReviewComment.review_id.in_(ids), ReviewComment.created_at >= widest,
                   ReviewComment.is_removed.is_(False))):
        for k, lo in since.items():
            if created >= lo:
                out[rid][k].comments += 1
                if author is not None and author != authors.get(rid):
                    participants[(rid, k)].add(author)

    from app.services import report_service
    reports = report_service.report_facts_by_target(db, ModerationTargetType.review, ids)
    facts: dict[uuid.UUID, MomentumFacts] = {}
    for rid in ids:
        for k in WINDOWS:
            out[rid][k].participants = len(participants[(rid, k)])
        facts[rid] = MomentumFacts(
            last_24h=out[rid]["last_24h"], last_7d=out[rid]["last_7d"],
            open_reports=reports.get(rid, report_service.NO_REPORTS).count,
        )
    return facts


def _awaiting_filter():
    has_active_link = select(ReferralLink.id).where(
        ReferralLink.review_id == Review.id,
        ReferralLink.status == ReferralLinkStatus.active).exists()
    monetizable = select(ProductPlatform.id).where(
        ProductPlatform.product_id == Review.product_id,
        ProductPlatform.is_monetizable.is_(True)).exists()
    return and_(
        Review.published_at.isnot(None),
        Review.is_removed.is_(False),
        Review.earn_eligible_status == EarnEligibleStatus.approved,
        ~has_active_link,
        monetizable,
    )


def awaiting_affiliate_total(db: Session) -> int:
    """How many reviews the affiliate-link queue lists.

    The overview's "Pending Affiliate" and the affiliate-links page's headline
    are this number, so neither can disagree with the list beneath it. They
    used to count every approved review without a link - including reviews of
    products with no listing to link to, which the queue rightly leaves out -
    so the page said "27 still need a link" above a list of five.
    """
    return int(db.scalar(select(func.count(Review.id)).where(_awaiting_filter())) or 0)


def awaiting_affiliate(db: Session, *, limit: int = 50, offset: int = 0,
                       now: datetime | None = None) -> AwaitingAffiliatePage:
    """Public, earnings-approved reviews with no active affiliate link.

    Ordered by publication, newest first, with the approval time (from the
    audit log) and the raw momentum facts on each item. No engagement
    ordering: which of these is most urgent is the admin's call — and a
    pending business rule — made from the facts.
    """
    from app.services.referral_service import sub_id_for_review, suggested_platform_from

    flt = _awaiting_filter()
    total = awaiting_affiliate_total(db)
    reviews = list(db.scalars(
        select(Review).where(flt)
        .order_by(Review.published_at.desc(), Review.id).limit(min(limit, 100))
        .offset(max(0, offset))))
    if not reviews:
        return AwaitingAffiliatePage(items=[], total=total)
    ids = [r.id for r in reviews]
    products = {p.id: p for p in db.scalars(
        select(Product).options(selectinload(Product.platforms))
        .where(Product.id.in_({r.product_id for r in reviews})))}
    names = dict(db.execute(select(User.id, User.display_name).where(
        User.id.in_({r.author_id for r in reviews if r.author_id}))).all())
    approved_at = dict(db.execute(
        select(ModerationLog.target_ref, func.max(ModerationLog.created_at))
        .where(ModerationLog.target_ref.in_(ids),
               ModerationLog.action.in_([ModerationAction.approve, ModerationAction.publish]))
        .group_by(ModerationLog.target_ref)).all())
    momentum = momentum_by_review(db, reviews, now=now)
    items = []
    for r in reviews:
        product = products.get(r.product_id)
        platforms = list(product.platforms) if product is not None else []
        items.append(AwaitingAffiliateItem(
            review=ReviewOut.model_validate(r),
            product=QueueProduct(
                id=r.product_id,
                canonical_name=product.canonical_name if product is not None else None,
                source_url=product.source_url if product is not None else None,
                platforms=[QueuePlatform(platform=p.platform, is_monetizable=p.is_monetizable)
                           for p in platforms]),
            author_display_name=names.get(r.author_id),
            platforms=[AwaitingPlatform(platform=p.platform, platform_url=p.platform_url,
                                        is_monetizable=p.is_monetizable,
                                        # By construction nothing on this list has one yet.
                                        has_active_link=False)
                       for p in platforms],
            suggested_platform=suggested_platform_from(product, platforms),
            suggested_sub_id=sub_id_for_review(r.id),
            earnings_approved_at=approved_at.get(r.id),
            momentum=momentum[r.id],
        ))
    return AwaitingAffiliatePage(items=items, total=total)


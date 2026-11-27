"""The Super Admin's 2.5-star routing decision (owner decision A, 2026-09-28).

"It depends" at exactly 2.5 stars goes to neither earning track by itself. An
administrator approves that it may earn (referral_service.approve_earnings),
which escalates it to `pending_superadmin_routing`; a thread update into 2.5
does the same (review_service.apply_thread_track). Then a Super Admin — and
nobody else — chooses exactly one of:

    HONESTY FUND   the thread joins the Honesty Fund track, as a Hard pass would:
                   status `honesty_fund`, no affiliate link
    PLATFORM       the commission route with the reviewer's share kept by the
                   platform: status `approved` (an administrator may attach the
                   official link), and every sale splits reviewer -> platform
                   (earnings.reviewer_routes_to_platform); the fund's own share
                   is untouched

THE DECISION IS
  * authorized — the route requires a Super Admin (require_super_admin);
  * audited — one `special_routing` row: who, when, where to, the previous
    status, the review and the entry it decided on;
  * idempotent — the same destination again is a no-op that writes nothing;
    a different destination after a decision is refused (409), never a silent
    overwrite;
  * safe under concurrent duplicate submissions — the thread root is locked
    (`FOR UPDATE`) before it is read, so two Super Admins submitting at once
    serialise and the second sees the first's decision.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationTargetType,
    SpecialRoute,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from app.services import notification_service
from app.services.earning_track import SUPERADMIN_ROUTING, track_for

#: Where each destination leaves the thread's earn status.
ROUTED_STATUS = {SpecialRoute.honesty_fund: EarnEligibleStatus.honesty_fund,
                 SpecialRoute.platform: EarnEligibleStatus.approved}

QUEUE_LIMIT = 100


def _conflict(message: str, code: str, **extra) -> AppError:
    return AppError(message, code=code, status_code=409, title="Conflicting state",
                    extra=extra or None)


@dataclass
class QueueItem:
    review: Review
    latest: Review
    product_name: str | None
    author: str | None
    escalated_at: datetime | None
    author_name: str | None = None
    product_image_url: str | None = None
    approval_note: str | None = None

    @property
    def excerpt(self) -> str | None:
        text = " ".join((self.latest.discussion or "").split())
        return (text[:197] + "…") if len(text) > 200 else (text or None)


def queue(db: Session, limit: int = QUEUE_LIMIT) -> list[QueueItem]:
    """Threads waiting on a Super Admin, oldest escalation first.

    Four queries whatever the length: the roots, their latest entries, the
    products and the authors (the escalation times come with the audit read).
    """
    from app.services.review_service import latest_entries
    roots = db.scalars(select(Review).where(
        Review.earn_eligible_status == EarnEligibleStatus.pending_superadmin_routing,
        Review.is_removed.is_(False))
        .order_by(Review.created_at).limit(limit)).all()
    if not roots:
        return []
    latest = latest_entries(db, [r.id for r in roots])
    products = {pid: (name, image) for pid, name, image in db.execute(
        select(Product.id, Product.canonical_name, Product.image_url)
        .where(Product.id.in_({r.product_id for r in roots}))).all()}
    people = {uid: (username, display) for uid, username, display in db.execute(
        select(User.id, User.username, User.display_name)
        .where(User.id.in_({r.author_id for r in roots if r.author_id}))).all()}
    authors = {uid: username for uid, (username, _) in people.items()}
    # The Administrator's note when approving it to earn (the latest one wins).
    approvals: dict[uuid.UUID, str] = {}
    for ref, note in db.execute(
            select(ModerationLog.target_ref, ModerationLog.notes)
            .where(ModerationLog.target_ref.in_([r.id for r in roots]),
                   ModerationLog.action == ModerationAction.approve,
                   ModerationLog.moderator_id.is_not(None))
            .order_by(ModerationLog.created_at)).all():
        if note and note.strip():
            approvals[ref] = note.strip()
    escalations: dict[uuid.UUID, datetime] = {}
    for ref, at in db.execute(
            select(ModerationLog.target_ref, ModerationLog.created_at)
            .where(ModerationLog.target_ref.in_([r.id for r in roots]),
                   ModerationLog.action.in_((ModerationAction.escalate,
                                             ModerationAction.track_flip)))
            .order_by(ModerationLog.created_at)).all():
        escalations[ref] = at
    return [QueueItem(review=r, latest=latest.get(r.id, r),
                      product_name=(products.get(r.product_id) or (None, None))[0],
                      author=f"@{authors[r.author_id]}" if authors.get(r.author_id) else None,
                      escalated_at=escalations.get(r.id),
                      author_name=(people.get(r.author_id) or (None, None))[1],
                      product_image_url=(products.get(r.product_id) or (None, None))[1],
                      approval_note=approvals.get(r.id))
            for r in roots]


def route(db: Session, actor: User, review_id: uuid.UUID,
          destination: SpecialRoute, note: str | None = None) -> tuple[Review, bool]:
    """Route one escalated thread. Returns (thread root, changed). Commits."""
    from app.services.review_service import latest_entry
    review = db.scalar(select(Review).where(Review.id == review_id).with_for_update()
                       .execution_options(populate_existing=True))
    if review is None or review.is_removed:
        raise NotFoundError("Review not found.", code="review_not_found")
    if review.thread_key != review.id:
        raise _conflict("Route the thread's original review, not an update.",
                        "not_thread_root", thread_root=str(review.thread_key))

    if review.special_route is not None:
        if review.special_route == destination:
            return review, False  # the same decision again: nothing to write
        raise _conflict("A Super Admin already routed this review "
                        f"to {review.special_route.value}.", "already_routed",
                        destination=review.special_route.value)
    if review.earn_eligible_status != EarnEligibleStatus.pending_superadmin_routing:
        raise _conflict("This review is not waiting on a Super Admin.",
                        "not_pending_routing", status=review.earn_eligible_status.value)
    latest = latest_entry(db, review.id) or review
    if track_for(latest.verdict, latest.star_rating) != SUPERADMIN_ROUTING:
        # Defensive: apply_thread_track moves a thread off this status the
        # moment it leaves 2.5, so this means the data was changed by hand.
        raise _conflict("This thread is no longer \"It depends\" at 2.5 stars.",
                        "not_special_routing_case")

    previous = review.earn_eligible_status
    now = datetime.now(UTC)
    review.special_route = destination
    review.special_routed_at = now
    review.special_routed_by_id = actor.id
    review.earn_eligible_status = ROUTED_STATUS[destination]
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", target_type=ModerationTargetType.review,
        target_ref=review.id, moderator_id=actor.id, action=ModerationAction.special_routing,
        notes=f"2.5-star It depends routed to {destination.value}"
              + (f" · {note.strip()}" if note and note.strip() else ""),
        context={"destination": destination.value, "previous_status": previous.value,
                 "new_status": review.earn_eligible_status.value,
                 "review_ref": review.review_id, "latest_entry": str(latest.id),
                 "stars": str(latest.star_rating), "verdict": latest.verdict.value,
                 "actor_staff_ref": actor.staff_ref}))
    if review.author_id is not None:
        notification_service.review_decided(
            db, review,
            "earnings_approved" if destination == SpecialRoute.honesty_fund
            else "routed_platform")
    db.commit()
    db.refresh(review)
    return review, True


def history(db: Session, limit: int = 50) -> list[ModerationLog]:
    return list(db.scalars(select(ModerationLog)
                           .where(ModerationLog.action == ModerationAction.special_routing)
                           .order_by(ModerationLog.created_at.desc()).limit(limit)))

"""Review submission, threads, the one photo swap, deletion, and product aggregates.

Business Rules §4 (Full Record, 2026-09-23): once published, text, rating and
verdict are frozen. The one exception is a single photo swap within 72 hours of
publishing. New information later is a NEW entry stacked on the same thread,
at most once every three months, and only the latest entry of a thread counts
toward the product's rating and the thread's earning track.
"""

from __future__ import annotations

import calendar
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.orm import Session, aliased

from app.core.categories import spellings_for
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.models.enums import (
    EarnEligibleStatus,
    ModerationAction,
    ModerationTargetType,
    PriceObservationSource,
    ReferralLinkStatus,
    VerificationStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import ReferralLink, Review, ReviewVersion
from app.models.user import User
from app.schemas.product import _ph_today
from app.schemas.review import ReviewCreate, ReviewEntryIn, ReviewUpdate
from app.services import earn_gate, review_draft_service, review_filters, review_lenses
from app.services.earning_track import SUPERADMIN_ROUTING, EarningTrack, track_for
from app.services.listing_filters import period_start
from app.services.price_service import new_observation
from app.services.storage import review_photo_belongs_to

#: §4: "photos can be swapped in a single edit pass, but only within 72 hours".
PHOTO_SWAP_WINDOW = timedelta(hours=72)
#: §4: a new entry on the same thread "allowed once every 3 months".
THREAD_UPDATE_COOLDOWN_MONTHS = 3
#: The confirmation a root deletion must carry (§4: "explicit, unambiguous").
DELETE_THREAD_CONFIRMATION = "delete-thread"


def _now() -> datetime:
    return datetime.now(UTC)


# Fields captured in each version snapshot.
#
# receipt_key is deliberately absent. Snapshots are served by
# GET /reviews/{id}/versions[/{n}], which accept anonymous callers for any
# published review - so anything in here is public. The edit history records
# `receipt_present` instead, which preserves the audit fact (evidence was
# attached, or removed) without publishing where the object lives.
VERSIONED_FIELDS = (
    "title", "discussion", "verdict", "verdict_explanation", "target_audience",
    "anti_target_audience", "star_rating", "pros", "cons", "photo_url", "photo_urls",
    "price_paid", "material_relationship",
)


def _verification_for(photos: list[str] | str | None,
                      author_id: uuid.UUID) -> VerificationStatus:
    """Verified only when the proof photo is an object this author uploaded.

    FR-3 makes a proof photo the thing that verifies a review, so "is this
    field non-empty" was never the real question - "did this author upload
    this object" is. Before, any string in `photo_url` earned the badge, so a
    reviewer could paste someone else's photo, or a URL to nothing at all, and
    be verified for it.

    The route checks ownership too and returns 403, which is the better answer
    for a caller who got it wrong. This exists because the decision belongs
    next to its precondition: a seed script, an admin path or a new endpoint
    that reaches the service directly must not be able to mint a verified
    review, and one day one of them will.

    Unverified rather than an exception: the service's job is to say what it
    can vouch for. Refusing to vouch is a complete answer, and it cannot be
    turned into an exploit by a caller that ignores it.
    """
    urls = [photos] if isinstance(photos, str) else list(photos or [])
    if any(url and review_photo_belongs_to(url, author_id) for url in urls):
        return VerificationStatus.verified
    return VerificationStatus.unverified


def _snapshot(review: Review) -> dict:
    """The versioned fields, in a shape `json.dumps` can actually write.

    The snapshot goes into a JSONB column, and psycopg serialises it with the
    standard `json` encoder — which has no idea what a `Decimal` is. Every
    numeric column here therefore has to be converted on the way in, and
    forgetting one does not fail until a review is actually submitted.

    It has happened: migration 0048 turned `star_rating` into `numeric(2,1)` for
    half steps, and the next submission raised `TypeError: Object of type
    Decimal is not JSON serializable` — a 500 on the composer's last step. Only
    the database-backed suite caught it. `test_review_snapshot_is_json.py` now
    checks the whole shape without a database, so the next one fails in seconds.

    The two Decimals are converted differently on purpose:

      star_rating   float — it is a rating on a 0..5 half-step scale, every one
                    of which is exact in binary, and the API serves it as a
                    number. A version and the live review must compare equal.
      price_paid    str — money. Two decimal places that must not acquire a
                    binary-rounding tail on the way through JSON.
    """
    snap: dict = {}
    for field in VERSIONED_FIELDS:
        value = getattr(review, field)
        if field in ("verdict", "material_relationship") and value is not None:
            value = value.value
        elif field == "price_paid" and value is not None:
            value = str(value)
        elif field == "star_rating" and value is not None:
            value = float(value)
        elif field == "photo_urls":
            value = list(value or [])
        snap[field] = value
    snap["receipt_present"] = bool(review.receipt_key)
    return snap


def _refuse_a_duplicate_submission(db: Session, author_id: uuid.UUID,
                                   payload: ReviewCreate) -> None:
    """The same review, submitted twice, is one review (BUG-031).

    QA could not test double-submit and filed that as the bug. The suspicion was
    right: the composer disables its own button while a request is in flight,
    and a disabled button is not a guarantee. A double tap that beats a
    re-render, a retry on a slow connection, a second tab, or anything posting
    to the API directly produced two identical reviews sitting in the moderation
    queue — and the person who made them had no way to remove either.

    WHAT COUNTS AS THE SAME REVIEW is the author, the product, the title and the
    body. Not just the author and the product: the first version of this guard
    refused any second pending review of a product, and that was an invented
    product rule rather than a fix for this bug. It also broke something real —
    the duplicate-content fraud fixtures post several different reviews of one
    product on purpose, because a reviewer flooding one listing is exactly what
    that detector exists to catch. A rule that makes the abuse unreachable is
    not a safety improvement.

    Only reviews still AWAITING a moderator's decision count — earning state
    `none` or `pending` — whether public or not. That is the old rule
    translated: it used to test "hidden and pending", because a review was
    hidden until a moderator decided it. Reviews are public from submission
    now (2026-09-22), so visibility no longer says whether anyone decided;
    the earning state does. Once a moderator has approved or rejected one, an
    identical resubmission is a deliberate act again — the duplicate-content
    fraud fixtures rely on exactly that. The error code is unchanged.
    """
    duplicate = db.scalar(
        select(Review.id).where(
            Review.author_id == author_id,
            Review.product_id == payload.product_id,
            Review.title == payload.title,
            Review.discussion == payload.discussion,
            Review.is_removed.is_(False),
            Review.earn_eligible_status.in_([EarnEligibleStatus.none,
                                             EarnEligibleStatus.pending]),
        ).limit(1)
    )
    if duplicate is not None:
        raise AppError(
            "You have already posted this review.",
            code="review_already_pending",
            status_code=409,
            title="Conflicting state",
        )


def recompute_product_aggregates(db: Session, product_id: uuid.UUID) -> None:
    """Service-layer aggregate update (ADR: no DB triggers).

    Counts only **published**, non-removed reviews (publication gate, M2 slice 1).
    Also refreshes the product's Wilson trust rating (M2 slice 4) since both move
    on the same events: publish / unpublish / star edit.

    Sessions run with autoflush=False, so flush first — callers invoke this right
    after mutating review state in-memory, and the aggregate SELECTs below must
    see those pending writes.
    """
    db.flush()
    thread = func.coalesce(Review.thread_id, Review.id)
    latest = (
        select(Review.star_rating.label("stars"))
        .where(Review.product_id == product_id, Review.is_removed.is_(False),
               Review.published_at.isnot(None))
        .distinct(thread)
        .order_by(thread, Review.created_at.desc(), Review.id.desc())
        .subquery()
    )
    # §4: one value per thread (its latest visible entry), combined by MEDIAN.
    stats = db.execute(
        select(func.count(),
               func.percentile_cont(0.5).within_group(latest.c.stars.asc()))
        .select_from(latest)
    ).one()
    product = db.get(Product, product_id)
    if product is not None:
        product.review_count = int(stats[0])
        median = stats[1] if stats[1] is not None else 0
        product.median_rating = Decimal(str(round(float(median), 2)))
    from app.services.trust_rating_service import recompute_product_trust
    recompute_product_trust(db, product_id)


def _add_months(moment: datetime, months: int) -> datetime:
    """`moment` plus whole calendar months, clamping the day (Jan 31 + 1 -> Feb 28)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _refuse_a_claimed_seller(db: Session, author_id: uuid.UUID) -> User | None:
    """§9: a claimed seller account never submits a review, on anything."""
    author = db.get(User, author_id)
    if author is not None and author.is_claimed_seller:
        raise ForbiddenError("A claimed seller account can't submit reviews.",
                             code="seller_cannot_review")
    return author


def thread_entries(db: Session, thread_key: uuid.UUID, *,
                   include_hidden: bool = False) -> list[Review]:
    """Every entry of a thread, oldest first. Author-deleted entries excluded
    unless `include_hidden`, which also includes taken-down entries."""
    stmt = select(Review).where(func.coalesce(Review.thread_id, Review.id) == thread_key)
    if not include_hidden:
        stmt = stmt.where(Review.removed_by_author_at.is_(None),
                          Review.is_removed.is_(False), Review.published_at.isnot(None))
    return list(db.scalars(stmt.order_by(Review.created_at, Review.id)))


def latest_entry(db: Session, thread_key: uuid.UUID) -> Review | None:
    """The thread's latest visible entry: the one that counts (§4)."""
    entries = thread_entries(db, thread_key)
    return entries[-1] if entries else None


def latest_entries(db: Session, thread_keys: list[uuid.UUID]) -> dict[uuid.UUID, Review]:
    """`latest_entry` for many threads in one query (DISTINCT ON the thread)."""
    if not thread_keys:
        return {}
    key = func.coalesce(Review.thread_id, Review.id)
    rows = db.scalars(
        select(Review).where(key.in_(thread_keys), Review.removed_by_author_at.is_(None),
                             Review.is_removed.is_(False), Review.published_at.isnot(None))
        .distinct(key).order_by(key, Review.created_at.desc(), Review.id.desc())).all()
    return {r.thread_key: r for r in rows}


def active_thread_for(db: Session, author_id: uuid.UUID,
                      product_id: uuid.UUID) -> Review | None:
    """The author's live thread on this product, as its newest entry, if any.

    A moderator take-down does not end a thread (the author cannot start a
    fresh one around it); an author deletion or a report removal does.
    """
    return db.scalar(
        select(Review).where(
            Review.author_id == author_id, Review.product_id == product_id,
            Review.is_removed.is_(False), Review.removed_by_author_at.is_(None),
        ).order_by(Review.created_at.desc(), Review.id.desc()).limit(1)
    )


def next_update_at(newest: Review) -> datetime:
    """When the thread may take its next entry (§4: once every 3 months)."""
    return _add_months(_utc(newest.created_at), THREAD_UPDATE_COOLDOWN_MONTHS)


def _new_entry(db: Session, author_id: uuid.UUID, product_id: uuid.UUID,
               payload: ReviewEntryIn, *, thread_id: uuid.UUID | None) -> Review:
    review = Review(
        product_id=product_id,
        author_id=author_id,
        title=payload.title,
        discussion=payload.discussion,
        verdict=payload.verdict,
        verdict_explanation=payload.verdict_explanation,
        target_audience=payload.target_audience,
        anti_target_audience=payload.anti_target_audience,
        star_rating=payload.star_rating,
        pros=payload.pros,
        cons=payload.cons,
        # The reviewer's own photos only, in their order; [] when none (0094).
        photo_urls=list(payload.photo_urls or []),
        receipt_key=payload.receipt_key,
        price_paid=payload.price_paid,
        material_relationship=payload.material_relationship,
        # A photo of the item this author uploaded is the ownership evidence
        # earning needs (§3), shown as "Photo provided" — never as proof of
        # purchase. A receipt is the other accepted evidence (has_receipt).
        verification_status=_verification_for(payload.photo_urls, author_id),
        review_id=f"rev_{uuid.uuid4().hex[:10]}",
        current_version=1,
        # §2: public on submission. `published_at` is when it went public.
        published_at=_now(),
        # An update entry never enters the earnings queue on its own: the
        # thread's earning state lives on its root (§4, §14).
        earn_eligible_status=(earn_gate.initial_status(db) if thread_id is None
                              else EarnEligibleStatus.none),
        thread_id=thread_id,
    )
    db.add(review)
    db.flush()
    if review.thread_id is None:
        review.thread_id = review.id
    # "Let's talk money" feeds price history (§16), attached to this review.
    if payload.price_paid is not None and payload.price_paid > 0 and payload.price_platform:
        db.add(new_observation(
            db, review.product_id, author_id, payload.price_platform, payload.price_paid,
            _ph_today(), None, source=PriceObservationSource.review, review_id=review.id))
    db.add(ReviewVersion(review_id=review.id, version_number=1,
                         snapshot=_snapshot(review), edited_by=author_id,
                         change_note=("initial submission" if thread_id is None
                                      else "thread update")))
    return review


def _lock_thread_slot(db: Session, author_id: uuid.UUID, product_id: uuid.UUID) -> None:
    """Serialise every thread write for one (author, product) — §4's "one thread".

    The thread rule is enforced by reading first (is there already a thread?
    has the cooldown passed?) and inserting after. Two requests racing — a
    double tap that beats the button's own guard, two tabs, a client retry —
    both read "nothing yet" and both insert: two competing threads for one
    product, or two updates inside one 3-month window.

    Not a unique index: production already holds reviews from before §4 with
    several per author and product (2 such pairs on 2026-09-24), which an index
    would refuse at migration time. A transaction-scoped advisory lock closes
    the race for every new write whatever the legacy rows are, and is released
    by the commit or rollback that ends the request.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": f"review-thread:{author_id}:{product_id}"})


def create_review(db: Session, author_id: uuid.UUID, payload: ReviewCreate) -> Review:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise NotFoundError("Product not found.", code="product_not_found")
    _lock_thread_slot(db, author_id, payload.product_id)

    _refuse_a_claimed_seller(db, author_id)
    _refuse_a_duplicate_submission(db, author_id, payload)
    existing = active_thread_for(db, author_id, payload.product_id)
    if existing is not None:
        # §4: more to say later is an update on the same thread, not a second
        # review. No bypass through this endpoint.
        raise AppError(
            "You've already reviewed this product. Add an update to your review instead.",
            code="review_thread_exists", status_code=409, title="Conflicting state",
            extra={"thread_id": str(existing.thread_key),
                   "next_update_at": next_update_at(existing).isoformat()},
        )

    review = _new_entry(db, author_id, payload.product_id, payload, thread_id=None)
    # The draft it was written in is published now, in the same transaction.
    review_draft_service.consume(db, author_id, payload.product_id)
    # QA-073 / 2026-09-29: a public review answers the open requests for this
    # product (their askers are told; the asker picks the Best Answer later),
    # in this transaction, so a failed submission announces nothing.
    from app.services.request_service import announce_answer
    announce_answer(db, review)
    # Publication moves the product's aggregates — the review is public now —
    # and can lift the author to Stage 1 ("posted at least one review", §8),
    # which is what unlocks commenting. Stage 2+ and the publish tokens still
    # follow a moderator's earnings approval (referral_service).
    recompute_product_aggregates(db, review.product_id)
    from app.services.trust_service import recompute_user_trust
    recompute_user_trust(db, author_id)
    db.commit()
    # Copied text is moderation evidence, checked once the review is public:
    # best effort, and a failure never touches the published review.
    from app.services.duplicate_text import check_new_review
    check_new_review(db, review.id)
    from app.services.duplicate_images import check_review_photo
    check_review_photo(db, review.id)
    db.refresh(review)
    return review


def add_thread_update(db: Session, entry: Review, author_id: uuid.UUID,
                      payload: ReviewEntryIn) -> Review:
    """A new entry on the author's thread (§4), at most once every 3 months."""
    if entry.author_id != author_id:
        raise ForbiddenError("Only the author can add an update to this review.",
                             code="not_review_author")
    _refuse_a_claimed_seller(db, author_id)
    root = db.get(Review, entry.thread_key)
    if root is None or root.is_removed or root.removed_by_author_at is not None:
        raise NotFoundError("Review not found.", code="review_not_found")
    _lock_thread_slot(db, author_id, root.product_id)
    newest = db.scalar(
        select(Review).where(func.coalesce(Review.thread_id, Review.id) == root.id,
                             Review.removed_by_author_at.is_(None))
        .order_by(Review.created_at.desc(), Review.id.desc()).limit(1))
    opens = next_update_at(newest or root)
    if _now() < opens:
        raise AppError(
            "Updates open 3 months after your last entry on this review.",
            code="thread_update_cooldown", status_code=409, title="Conflicting state",
            extra={"next_update_at": opens.isoformat()},
        )
    created = _new_entry(db, author_id, root.product_id, payload, thread_id=root.id)
    review_draft_service.consume(db, author_id, root.product_id)
    apply_thread_track(db, root, actor_id=author_id)
    recompute_product_aggregates(db, root.product_id)
    db.commit()
    from app.services.duplicate_text import check_new_review
    check_new_review(db, created.id)
    from app.services.duplicate_images import check_review_photo
    check_review_photo(db, created.id)
    db.refresh(created)
    return created


def _revoke_active_link(db: Session, root: Review, actor_id: uuid.UUID | None,
                        reason: str) -> bool:
    link = db.scalar(select(ReferralLink).where(
        ReferralLink.review_id == root.id, ReferralLink.status == ReferralLinkStatus.active))
    if link is None:
        return False
    link.status = ReferralLinkStatus.revoked
    link.revoked_by = actor_id
    link.revoked_at = _now()
    link.revoke_reason = reason
    root.affiliate_link = None
    return True


def _log(db: Session, actor_id: uuid.UUID | None, action: ModerationAction,
         review_id: uuid.UUID, *, notes: str | None = None,
         context: dict | None = None) -> None:
    db.add(ModerationLog(target_type=ModerationTargetType.review, target_ref=review_id,
                         moderator_id=actor_id, action=action, notes=notes, context=context))


def apply_thread_track(db: Session, root: Review, *, actor_id: uuid.UUID | None) -> None:
    """Re-decide the thread's earning track from its latest entry (§14).

    Only prospective: money already paid before the crossing is never clawed
    back. Commission side -> fund side revokes the active link; fund side ->
    commission side returns the thread to `approved`, where the normal
    affiliate-attach flow picks it up. Threads with no earnings decision yet
    are left alone: the track is read at approval time.

    Owner decision A: an update that moves a decided thread INTO "It depends"
    at 2.5 stars escalates it — the link is switched off and the thread waits
    for a Super Admin (`pending_superadmin_routing`). A thread a Super Admin
    already routed keeps that route while its latest entry stays at 2.5; the
    route is cleared the moment the thread moves off 2.5, and the ordinary
    rule takes over from there.
    """
    latest = latest_entry(db, root.id) or root
    track = track_for(latest.verdict, latest.star_rating)
    status = root.earn_eligible_status
    commission_side = status in (EarnEligibleStatus.approved, EarnEligibleStatus.monetized)
    fund_side = status == EarnEligibleStatus.honesty_fund
    pending = status == EarnEligibleStatus.pending_superadmin_routing

    if track == SUPERADMIN_ROUTING:
        if root.special_route is not None or pending or not (commission_side or fund_side):
            return
        revoked = _revoke_active_link(db, root, actor_id,
                                      "thread update moved to 2.5 stars, It depends: "
                                      "awaiting a Super Admin")
        root.earn_eligible_status = EarnEligibleStatus.pending_superadmin_routing
        _log(db, actor_id, ModerationAction.track_flip, root.id,
             context={"from": status.value, "to": "pending_superadmin_routing",
                      "latest_entry": str(latest.id), "link_revoked": revoked})
        return

    cleared = None
    if root.special_route is not None:
        cleared = root.special_route.value
        root.special_route = None
        root.special_routed_at = None
        root.special_routed_by_id = None
    if (commission_side or pending) and track == EarningTrack.honesty_fund:
        revoked = _revoke_active_link(db, root, actor_id,
                                      "thread update moved to the Honesty Fund")
        root.earn_eligible_status = EarnEligibleStatus.honesty_fund
        _log(db, actor_id, ModerationAction.track_flip, root.id,
             context={"from": status.value, "to": "honesty_fund",
                      "latest_entry": str(latest.id), "link_revoked": revoked,
                      "special_route_cleared": cleared})
    elif (fund_side or pending) and track == EarningTrack.commission:
        root.earn_eligible_status = EarnEligibleStatus.approved
        _log(db, actor_id, ModerationAction.track_flip, root.id,
             context={"from": status.value, "to": "approved",
                      "latest_entry": str(latest.id), "special_route_cleared": cleared})
    elif cleared is not None:
        _log(db, actor_id, ModerationAction.track_flip, root.id,
             context={"from": status.value, "to": status.value,
                      "latest_entry": str(latest.id), "special_route_cleared": cleared})


def update_review(db: Session, review: Review, editor_id: uuid.UUID,
                  payload: ReviewUpdate) -> Review:
    """The one change a published review allows: a single photo swap within 72h.

    §4: text, rating and verdict are frozen forever once published — "votes and
    earnings are based on them". Anything but the photos is refused. The swap
    replaces the whole ordered set (`photo_urls`, or `photo_url` for one).
    """
    data = payload.model_dump(exclude_unset=True)
    data.pop("change_note", None)
    frozen = sorted(k for k in data if k not in ("photo_url", "photo_urls"))
    if frozen:
        raise AppError(
            "A published review can't be edited. Add an update to your review instead.",
            code="review_content_frozen", status_code=409, title="Conflicting state",
            extra={"fields": frozen},
        )
    photos = payload.photos()
    if photos is None or photos == list(review.photo_urls or []):
        return review
    if not photos:
        raise AppError("A replacement photo is required.", code="photo_required",
                       status_code=422, title="Invalid request")
    if review.photo_replaced_at is not None:
        raise AppError("You've already replaced this review's photo once.",
                       code="photo_swap_used", status_code=409, title="Conflicting state")
    published = _utc(review.published_at or review.created_at)
    if _now() - published > PHOTO_SWAP_WINDOW:
        raise AppError("Photos can only be replaced within 72 hours of publishing.",
                       code="photo_swap_window_closed", status_code=409,
                       title="Conflicting state")
    review.photo_urls = photos
    review.photo_url = photos[0]
    review.photo_replaced_at = _now()
    review.verification_status = _verification_for(photos, review.author_id)
    review.current_version += 1
    db.add(ReviewVersion(review_id=review.id, version_number=review.current_version,
                         snapshot=_snapshot(review), edited_by=editor_id,
                         change_note="photo replaced"))
    _log(db, editor_id, ModerationAction.photo_replace, review.id)
    db.commit()
    # The replacement photo gets the same reused-photo check (QA 2026-09-29).
    from app.services.duplicate_images import check_review_photo
    check_review_photo(db, review.id)
    db.refresh(review)
    return review


def delete_entry(db: Session, review: Review, author_id: uuid.UUID, *,
                 confirm: str | None) -> list[uuid.UUID]:
    """The author deletes one entry, or the whole thread from its root (§4).

    Never a hard delete: commissions and payouts reference these rows, and "a
    thread that ever triggered a payout doesn't vanish without a trace" — it
    counts in the product's aggregate "removed by author" note instead of being
    singled out. Returns the ids taken down.
    """
    if review.author_id != author_id:
        raise ForbiddenError("Only the author can delete this review.",
                             code="not_review_author")
    # Serialise concurrent deletes of the same entry (a double tap, two tabs):
    # re-read it under a row lock, and if the first request already removed it,
    # the second is a no-op rather than a second audit row and a second pass
    # over the thread.
    review = db.execute(select(Review).where(Review.id == review.id).with_for_update()
                        .execution_options(populate_existing=True)).scalar_one()
    if review.removed_by_author_at is not None:
        db.rollback()
        return []
    now = _now()
    if not review.is_thread_root:
        review.is_removed = True
        review.removed_by_author_at = now
        _log(db, author_id, ModerationAction.author_delete, review.id,
             context={"scope": "entry"})
        root = db.get(Review, review.thread_key)
        if root is not None:
            apply_thread_track(db, root, actor_id=author_id)
        recompute_product_aggregates(db, review.product_id)
        db.commit()
        return [review.id]

    if confirm != DELETE_THREAD_CONFIRMATION:
        raise AppError(
            "Deleting your original review deletes the whole thread, every update "
            "included, and ends all future earning from it. This can't be undone.",
            code="thread_delete_confirmation_required", status_code=409,
            title="Confirmation required",
            extra={"confirm": DELETE_THREAD_CONFIRMATION},
        )
    from app.models.commission import Commission
    paid = bool(db.scalar(select(exists().where(
        Commission.review_id == review.id, Commission.reviewer_share > 0,
        Commission.is_test.is_(False)))))
    entries = thread_entries(db, review.id, include_hidden=True)
    for entry in entries:
        entry.is_removed = True
        entry.removed_by_author_at = now
    review.removed_after_payout = paid
    revoked = _revoke_active_link(db, review, author_id, "thread deleted by its author")
    _log(db, author_id, ModerationAction.author_delete, review.id,
         context={"scope": "thread", "entries": len(entries), "link_revoked": revoked,
                  "after_payout": paid})
    recompute_product_aggregates(db, review.product_id)
    if review.author_id is not None:
        from app.services.trust_service import recompute_user_trust
        recompute_user_trust(db, review.author_id)
    db.commit()
    return [entry.id for entry in entries]


def removed_after_payout_count(db: Session, product_id: uuid.UUID) -> int:
    """How many paid threads on this product their authors deleted (§4 aggregate)."""
    return int(db.scalar(select(func.count(Review.id)).where(
        Review.product_id == product_id, Review.removed_after_payout.is_(True))) or 0)


def get_review_or_404(db: Session, review_id: uuid.UUID) -> Review:
    review = db.get(Review, review_id)
    if review is None or review.is_removed:
        raise NotFoundError("Review not found.", code="review_not_found")
    return review


def list_versions(db: Session, review_id: uuid.UUID) -> list[ReviewVersion]:
    return list(db.scalars(
        select(ReviewVersion).where(ReviewVersion.review_id == review_id)
        .order_by(ReviewVersion.version_number)
    ))


#: A feed dominated by one voice or one product is not a feed. These caps are
#: deliberately small: the point is that scrolling shows you the platform, not
#: one prolific reviewer's back catalogue.
MAX_PER_AUTHOR = 2
MAX_PER_PRODUCT = 2


def diversify(
    rows: list[tuple[Review, User | None, Product | None]],
    *, limit: int,
    max_per_author: int = MAX_PER_AUTHOR,
    max_per_product: int = MAX_PER_PRODUCT,
) -> list[tuple[Review, User | None, Product | None]]:
    """Thin a ranked list so no author or product dominates it.

    Order is preserved: this only removes, never re-sorts, so whatever ranking
    produced `rows` still decides what a reader sees first. Anything dropped for
    exceeding a cap is appended afterwards rather than discarded, so a small
    corpus still fills the page — on a platform with fifteen reviews, strict
    caps would otherwise return four.

    Pure, so the rule is testable without a database.
    """
    kept: list[tuple[Review, User | None, Product | None]] = []
    overflow: list[tuple[Review, User | None, Product | None]] = []
    by_author: dict[uuid.UUID, int] = {}
    by_product: dict[uuid.UUID, int] = {}

    for row in rows:
        review, author, _ = row
        author_key = author.id if author is not None else None
        author_n = by_author.get(author_key, 0) if author_key else 0
        product_n = by_product.get(review.product_id, 0)
        if author_n >= max_per_author or product_n >= max_per_product:
            overflow.append(row)
            continue
        if author_key:
            by_author[author_key] = author_n + 1
        by_product[review.product_id] = product_n + 1
        kept.append(row)
        if len(kept) >= limit:
            return kept

    return (kept + overflow)[:limit]


def prioritise_interests(
    rows: list[tuple[Review, User | None, Product | None]],
    interests: list[str] | None,
) -> list[tuple[Review, User | None, Product | None]]:
    """Move reviews in the reader's chosen categories to the front.

    A stable partition rather than a score: reviews the reader asked for come
    first, everything else keeps its existing order behind them. Nothing is
    removed, so a reader whose interests match two reviews still gets a full
    feed instead of a two-item one — the fallback is the same list, which is
    what "graceful" has to mean when personalisation data is thin.

    Pure, so the rule is testable without a database.
    """
    if not interests:
        return rows
    wanted = {c for i in interests for c in spellings_for(i)}
    if not wanted:
        return rows
    preferred = [r for r in rows if r[2] is not None and r[2].category in wanted]
    rest = [r for r in rows if not (r[2] is not None and r[2].category in wanted)]
    return preferred + rest


# --- The author's own reviews -------------------------------------------------
#
# A review is public from submission (2026-09-22); it is unpublished only when
# a moderator takes it down. The public feed is publication-gated, so the
# author's own profile must not read it: that is how a review once
# "disappeared" from its author's profile (2026-09-18). These read the author's
# reviews in every state, and say which state each is in.

PUBLISHED, PENDING, REJECTED = "published", "pending", "rejected"


def publication_status(review: Review) -> str:
    """The state an author sees: published, awaiting moderation, or rejected.

    Derived from the columns that already decide it, not a new state.
    `pending` now means "taken down for another look" (referral_service.unpublish);
    `rejected` survives for reviews rejected under the old hide-until-approved
    flow. An earnings rejection no longer hides a review, so it reads as
    published here — earning state is not a publication state.
    """
    if review.published_at is not None:
        return PUBLISHED
    if review.earn_eligible_status == EarnEligibleStatus.rejected:
        return REJECTED
    return PENDING


def list_own_reviews(db: Session, author_id: uuid.UUID, *, limit: int, offset: int = 0):
    """The author's non-removed reviews, newest first, with their products."""
    stmt = (
        select(Review, Product)
        .join(Product, Product.id == Review.product_id, isouter=True)
        .where(Review.author_id == author_id, Review.is_removed.is_(False))
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).all())


def _latest_notes(db: Session, review_ids: list[uuid.UUID],
                  action) -> dict[uuid.UUID, str | None]:
    """The most recent moderator note of one action per review, in one query."""
    if not review_ids:
        return {}
    from app.models.enums import ModerationTargetType
    from app.models.moderation import ModerationLog

    rows = db.execute(
        select(ModerationLog.target_ref, ModerationLog.notes)
        .where(
            ModerationLog.target_type == ModerationTargetType.review,
            ModerationLog.action == action,
            ModerationLog.target_ref.in_(review_ids),
        )
        .order_by(ModerationLog.target_ref, ModerationLog.created_at.desc())
        .distinct(ModerationLog.target_ref)
    ).all()
    return {ref: notes for ref, notes in rows}


def rejection_reasons(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """The most recent reject note per review, in one query.

    The note is the reason the moderator gave (referral_service.reject), which
    the author already receives in their notification.
    """
    from app.models.enums import ModerationAction
    return _latest_notes(db, review_ids, ModerationAction.reject)


def takedown_reasons(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """QA-054: the reason the moderator gave when taking each review down
    (referral_service.unpublish) — already in the author's notification, and
    now on the review page they land on from it."""
    from app.models.enums import ModerationAction
    return _latest_notes(db, review_ids, ModerationAction.unpublish)


def _has_newer_visible_entry():
    """True for an entry a later visible entry of its thread supersedes (§4).

    Card lists show a thread once, as its latest entry; older entries stay
    reachable by their own URL and in the thread history.
    """
    newer = aliased(Review)
    return exists().where(
        func.coalesce(newer.thread_id, newer.id) == func.coalesce(Review.thread_id, Review.id),
        newer.created_at > Review.created_at,
        newer.is_removed.is_(False),
        newer.published_at.isnot(None),
    )


def _feed_stmt(
    *, product_id: uuid.UUID | None = None, author_id: uuid.UUID | None = None,
    category: str | Sequence[str] | None = None, q: str | None = None,
    sort: str = "wilson", period: str | None = None, lens: str | None = None,
    trust: str | None = None, max_price: Decimal | None = None,
    show: review_filters.FeedShow | None = None,
):
    """The feed's query: filters and order, no slice. Shared by `list_feed`
    and `count_feed` so a page and its total can never disagree (MQA-036).
    `show` is the filter sheet's Rating, Show only and Variant (review_filters)."""
    categories = [category] if isinstance(category, str) else list(category or [])
    categories = [c for c in categories if c]
    stmt = select(Review).where(
        Review.is_removed.is_(False), Review.published_at.isnot(None),
        ~_has_newer_visible_entry(),
    )
    if product_id is not None:
        stmt = stmt.where(Review.product_id == product_id)
    if author_id is not None:
        stmt = stmt.where(Review.author_id == author_id)
    since = period_start(period)  # type: ignore[arg-type]
    if since is not None:
        stmt = stmt.where(Review.published_at >= since)
    if categories or q:
        stmt = stmt.join(Product, Review.product_id == Product.id)
        if categories:
            # Alias-tolerant: rows written before the vocabulary had an owner
            # still hold the old spelling. See app/core/categories.py.
            spellings: set[str] = set()
            for category in categories:
                spellings.update(spellings_for(category))
            stmt = stmt.where(Product.category.in_(sorted(spellings)))
        if q:
            # Business Rules §6: the product side uses the ranked, typo-tolerant
            # product matcher; a title matches as a substring only from 4
            # characters, so "ma" no longer finds every "10000mAh".
            from app.services import product_search
            term = product_search.normalize(q)
            clauses = [Review.product_id.in_(product_search.matching_product_ids(q))]
            if len(term) >= product_search.MIN_SUBSTRING_LENGTH:
                clauses.append(Review.title.ilike(f"%{q.strip()}%"))
            stmt = stmt.where(or_(*clauses))
    for clause in (review_lenses.trust_clause(trust),  # type: ignore[arg-type]
                   review_lenses.budget_clause(max_price)):
        if clause is not None:
            stmt = stmt.where(clause)
    stmt = review_filters.apply(stmt, show)
    if lens is not None:
        # Orders by the lens itself unless the reader chose a date order.
        stmt = review_lenses.apply_lens(stmt, lens, keep_order=sort != "wilson")  # type: ignore[arg-type]
    # Every order ends on the id: reviews written in one transaction share a
    # timestamp, and without a total order an offset page can repeat one review
    # and skip another (the numbered pages, MQA-036/037).
    if sort == "oldest":
        stmt = stmt.order_by(Review.created_at.asc(), Review.id)
    elif sort == "lowest":
        # "Lowest rated" (Figma 7762:9948): fewest stars first, newest among equals.
        stmt = stmt.order_by(Review.star_rating.asc(), Review.created_at.desc(), Review.id.desc())
    elif sort != "wilson":
        stmt = stmt.order_by(Review.created_at.desc(), Review.id.desc())
    elif lens is None:
        stmt = stmt.order_by(Review.wilson_score.desc(), Review.created_at.desc(),
                             Review.id.desc())

    return stmt


def count_feed(
    db: Session, *, product_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None, category: str | Sequence[str] | None = None,
    q: str | None = None, period: str | None = None, lens: str | None = None,
    trust: str | None = None, max_price: Decimal | None = None,
    show: review_filters.FeedShow | None = None,
) -> int:
    """How many reviews `list_feed` would page through with these filters."""
    stmt = _feed_stmt(product_id=product_id, author_id=author_id, category=category, q=q,
                      sort="newest", period=period, lens=lens, trust=trust,
                      max_price=max_price, show=show).order_by(None)
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


#: What a review card reads, and nothing else (E1). The long free-text fields
#: (discussion, verdict_explanation, target_audience, anti_target_audience) are
#: up to 5,000 + 3 x 2,000 characters a row, and a card shows 180 of them: they
#: stay in Postgres, and the card gets `excerpt` instead. The last three are
#: the trust badge's inputs (services/trust_badge.py), not shown themselves.
CARD_REVIEW_COLUMNS = (
    Review.id, Review.product_id, Review.author_id, Review.title, Review.verdict,
    Review.star_rating, Review.photo_urls, Review.photo_url, Review.helpful_votes,
    Review.unhelpful_votes, Review.created_at,
    Review.verification_status, Review.published_at, Review.earn_eligible_status,
)

#: The excerpt a card list carries. Cards cut to 180 characters on a word
#: (excerptOf in lib/reviews.ts); 200 leaves it room to find the word break and
#: to know the text ran longer, so the card reads exactly as before.
CARD_EXCERPT_LENGTH = 200


def card_excerpt():
    """The discussion's first 200 characters with whitespace collapsed, cut in
    SQL so the full text never leaves the database. Collapsing first matches
    the card's own `replace(/\\s+/g, " ").trim()`, so a run of blank lines cannot
    eat into the 200."""
    collapsed = func.btrim(func.regexp_replace(Review.discussion, r"\s+", " ", "g"))
    return func.left(collapsed, CARD_EXCERPT_LENGTH).label("excerpt")


def list_feed_cards(
    db: Session, *, limit: int = 8, offset: int = 0, with_total: bool = False,
    product_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None,
    category: str | Sequence[str] | None = None,
    q: str | None = None, sort: str = "wilson",
    period: str | None = None,
    lens: str | None = None, trust: str | None = None,
    max_price: Decimal | None = None,
    show: review_filters.FeedShow | None = None,
) -> tuple[list[tuple[Any, Any, Any]], int | None]:
    """`list_feed` in the card shape: the same query, the same order, only the
    columns a card reads (E1), and authors and products as display columns
    only (E2). Rows are (review, author, product) like `list_feed`'s, so
    `prioritise_interests` and `diversify` take either.

    `with_total` adds the filters' total in the same query (count(*) OVER (),
    computed before the slice), for the search and feed pages that number
    their results. A page past the end has no row to carry it, so that one
    case asks `count_feed`; every other page costs no second query.
    """
    filters = dict(product_id=product_id, author_id=author_id, category=category, q=q,
                   period=period, lens=lens, trust=trust, max_price=max_price, show=show)
    stmt = _feed_stmt(sort=sort, **filters)
    columns = [*CARD_REVIEW_COLUMNS, card_excerpt()]
    if with_total:
        columns.append(func.count().over().label("total"))
    rows = list(db.execute(stmt.with_only_columns(*columns)
                           .limit(limit).offset(max(0, offset))).all())

    total: int | None = None
    if with_total:
        if rows:
            total = int(rows[0].total)
        elif offset > 0:
            total = count_feed(db, **filters)
        else:
            total = 0

    author_ids = {r.author_id for r in rows if r.author_id is not None}
    product_ids = {r.product_id for r in rows}
    authors = {
        a.id: a for a in db.execute(
            select(User.id, User.username, User.display_name, User.avatar_url,
                   User.trust_stage, User.trust_level_name, User.reputation_score)
            .where(User.id.in_(author_ids))).all()
    } if author_ids else {}
    products = {
        p.id: p for p in db.execute(
            select(Product.id, Product.canonical_name, Product.category)
            .where(Product.id.in_(product_ids))).all()
    } if product_ids else {}
    return [(r, authors.get(r.author_id), products.get(r.product_id)) for r in rows], total


def list_feed(
    db: Session, *, limit: int = 8, offset: int = 0,
    product_id: uuid.UUID | None = None,
    author_id: uuid.UUID | None = None,
    category: str | Sequence[str] | None = None,
    q: str | None = None, sort: str = "wilson",
    period: str | None = None,
    lens: str | None = None, trust: str | None = None,
    max_price: Decimal | None = None,
    show: review_filters.FeedShow | None = None,
) -> list[tuple[Review, User | None, Product | None]]:
    """Published reviews with their author + product, for public card surfaces.

    Batch-loads authors and products by id (two extra queries total) rather than
    an ORM join, so the shape stays trivial and the N+1 is avoided.

    `category` may name several categories (QA-025): a review in ANY of them
    is shown. `period` is the All filters sheet's Time ("year", "month").
    `lens`, `trust` and `max_price` are the sheet's Review score, Trust rating
    and Budget (QA-053), defined in `review_lenses`. A lens orders the results
    its own way unless the reader picked Latest or Oldest.
    """
    stmt = _feed_stmt(product_id=product_id, author_id=author_id, category=category, q=q,
                      sort=sort, period=period, lens=lens, trust=trust, max_price=max_price,
                      show=show)
    reviews = list(db.scalars(stmt.limit(limit).offset(max(0, offset))))
    author_ids = {r.author_id for r in reviews if r.author_id is not None}
    product_ids = {r.product_id for r in reviews}
    authors = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(author_ids)))}
        if author_ids else {}
    )
    products = (
        {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
        if product_ids else {}
    )
    return [(r, authors.get(r.author_id), products.get(r.product_id)) for r in reviews]

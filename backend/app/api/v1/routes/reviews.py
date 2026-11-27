"""Review routes — submission, versioning, AI critique, with the publication gate.

A review is hidden (`published_at IS NULL`) until a moderator publishes it. Anonymous
and other users only see published reviews; authors see their own drafts; moderators
see everything (`?include_unpublished=true`).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.core.rate_limit import enforce_rate_limit, enforce_user_rate_limit
from app.core.security import get_current_user, get_optional_user, is_staff
from app.db.session import get_db
from app.models.comment import ReviewComment
from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    VoteDirection,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review, ReviewVersion
from app.models.user import User
from app.models.vote import ReviewVote
from app.schemas.ai import CritiqueResponse
from app.schemas.report import ReportCreate, ReportOut
from app.schemas.review import (
    FeedAuthor,
    FeedCardOut,
    FeedCardProduct,
    FeedCardReview,
    FeedItemOut,
    FeedPageOut,
    FeedProduct,
    OwnReviewOut,
    ReviewCreate,
    ReviewEntryIn,
    ReviewOut,
    ReviewUpdate,
    ReviewVersionOut,
    ThreadDeleted,
    ThreadEntryOut,
    ThreadOut,
    VoteIn,
)
from app.services import (
    reading_telemetry_service,
    report_service,
    request_traffic_service,
    review_filters,
    review_service,
    vote_service,
)
from app.services.ai_critique import get_provider
from app.services.listing_filters import Period
from app.services.request_geo import from_headers
from app.services.review_lenses import Lens, TrustBand
from app.services.storage import (
    receipt_key_belongs_to,
    review_photo_belongs_to,
    signed_receipt_url,
    upload_receipt,
    upload_review_photo,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = get_logger(__name__)


def _is_moderator(user: User | None) -> bool:
    return is_staff(user)


def _can_view_unpublished(review: Review, user: User | None) -> bool:
    return user is not None and (user.id == review.author_id or _is_moderator(user))


def _visible_or_404(review: Review, user: User | None) -> Review:
    if review.published_at is None and not _can_view_unpublished(review, user):
        raise NotFoundError("Review not found.", code="review_not_found")
    return review


def _own_photos_or_403(urls: list[str] | None, user: User) -> None:
    """Every photo of a review is one this caller uploaded (see below)."""
    for url in urls or []:
        _own_photo_or_403(url, user)


def _own_photo_or_403(url: str | None, user: User) -> str | None:
    """Reject a proof photo this caller did not upload through us.

    Without this the field is self-asserted: any string makes a review
    `verified` (review_service derives it from photo_url being non-null), and
    verified is what unlocks earning eligibility. That would make FR-8's first
    fraud layer free to bypass.
    """
    if url is None or review_photo_belongs_to(url, user.id):
        return url
    raise ForbiddenError(
        "A proof photo must be one you uploaded through /reviews/photo.",
        code="photo_not_owned")


def _own_receipt_key_or_400(key: str | None, user: User) -> str | None:
    """Reject a receipt key this caller did not upload.

    Keys are `{uploader_id}/{uuid}.{ext}`, so without this check a user could
    attach somebody else's receipt to their own review and then read it back
    through the authorized endpoint - which would turn the private bucket into
    a slower version of the hole it replaced.
    """
    if key is None or receipt_key_belongs_to(key, user.id):
        return key
    raise ForbiddenError("That proof of purchase belongs to someone else.",
                         code="receipt_not_owned")


def _my_votes(db: Session, user: User | None,
              review_ids: list[uuid.UUID]) -> dict[uuid.UUID, VoteDirection]:
    """The viewer's own votes across a set of reviews, in one query (BUG-013).

    Batched deliberately: the feed returns up to 100 rows, and asking per row
    would turn one page render into 100 extra round trips against a database in
    another region. Signed-out readers cost nothing — no viewer, no query.
    """
    if user is None or not review_ids:
        return {}
    rows = db.execute(
        select(ReviewVote.review_id, ReviewVote.vote).where(
            ReviewVote.voter_id == user.id,
            ReviewVote.review_id.in_(review_ids),
        )
    ).all()
    return {review_id: vote for review_id, vote in rows}


def _out(review: Review, my_vote: VoteDirection | None = None) -> ReviewOut:
    out = ReviewOut.model_validate(review)
    out.my_vote = my_vote
    return out


def _comment_counts(db: Session, review_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Live comment totals for a set of reviews, in one grouped query (BUG-006).

    Removed comments are excluded: the card's count should match what a reader
    finds when they open the thread, and a soft-deleted comment renders as
    "[removed]" rather than as a contribution.
    """
    if not review_ids:
        return {}
    rows = db.execute(
        select(ReviewComment.review_id, func.count(ReviewComment.id))
        .where(
            ReviewComment.review_id.in_(review_ids),
            ReviewComment.is_removed.is_(False),
        )
        .group_by(ReviewComment.review_id)
    ).all()
    return {review_id: total for review_id, total in rows}


@router.post("", response_model=ReviewOut, status_code=201, summary="Submit a review")
def create_review(payload: ReviewCreate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> ReviewOut:
    _own_photos_or_403(payload.photo_urls, user)
    _own_receipt_key_or_400(payload.receipt_key, user)
    review = review_service.create_review(db, user.id, payload)
    return ReviewOut.model_validate(review)


class PhotoUploaded(BaseModel):
    url: str


class ReceiptUploaded(BaseModel):
    """The key is what gets submitted with the review; the URL is for preview.

    Two different things on purpose. `key` is the durable, opaque locator the
    API stores. `preview_url` is a short-lived signed URL so the uploader can
    see what they just attached - it is a bearer credential, expires quickly,
    and is never persisted anywhere.
    """

    key: str
    preview_url: str
    expires_in: int


class ReceiptAccess(BaseModel):
    url: str
    expires_in: int


@router.post("/photo", response_model=PhotoUploaded,
             summary="Upload a PUBLIC review photo; returns its URL")
def upload_photo(file: UploadFile,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> PhotoUploaded:
    """Store a PUBLIC review photo and hand back its URL for `photo_url`.

    Separate from review creation because the photo is picked while the review
    is still being written — there is no review id to attach it to yet, and
    making the author upload only to have submission fail validation would lose
    the file. Declared above `/{review_id}` so the literal path wins the match.

    Proof of purchase does NOT come through here; see POST /reviews/receipt.
    This endpoint writes to a public bucket, which is correct for an image
    that appears on the published review and wrong for anything else.
    """
    from app.services import duplicate_images, image_fingerprint
    from app.services.storage import validate_review_photo

    data = file.file.read()
    validate_review_photo(data)                 # size and magic bytes, as before
    try:
        # A full, bounded decode: a file whose header claims an image but whose
        # body is corrupt, or a decompression bomb, is refused before storage.
        fp = image_fingerprint.fingerprint(data)
    except image_fingerprint.UnreadableImage as exc:
        raise AppError(str(exc), code="unreadable_image", status_code=415,
                       title="Unsupported media type") from exc
    url = upload_review_photo(user.id, data)
    # The fingerprint the duplicate-photo check compares (QA 2026-09-29). The
    # photo is stored already; a failure here only means it is not compared.
    try:
        duplicate_images.record_upload(db, url=url, uploader_id=user.id, fp=fp)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return PhotoUploaded(url=url)


@router.post("/receipt", response_model=ReceiptUploaded,
             summary="Upload proof of purchase to private storage")
def upload_receipt_route(file: UploadFile,
                         user: User = Depends(get_current_user)) -> ReceiptUploaded:
    """Store proof of purchase and return its private key.

    Separate from /reviews/photo because the two have different audiences, and
    one endpoint returning "a URL suitable for either" is what let a receipt
    end up in a public bucket. The caller does not choose the destination: the
    endpoint it calls decides, server-side.
    """
    key = upload_receipt(user.id, file.file.read())
    ttl = settings.receipt_url_ttl_seconds
    preview = signed_receipt_url(key, ttl)
    if preview is None:
        raise NotFoundError("Upload succeeded but could not be previewed.",
                            code="receipt_not_found")
    return ReceiptUploaded(key=key, preview_url=preview, expires_in=ttl)


@router.get("/{review_id}/receipt", response_model=ReceiptAccess,
            summary="Signed, short-lived access to a review's proof of purchase")
def get_receipt(review_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> ReceiptAccess:
    """Author or moderator only. Authorization happens before signing.

    404 rather than 403 for everyone else, including when no receipt exists:
    a distinct "forbidden" would confirm to an unrelated user that this review
    has proof of purchase attached, which is itself something they should not
    learn. The PRD scopes receipts to earn_eligible evaluation (FR-3, FR-9),
    so the moderator half of this is a requirement, not a convenience.
    """
    review = review_service.get_review_or_404(db, review_id)
    if not (user.id == review.author_id or _is_moderator(user)):
        raise NotFoundError("Review not found.", code="review_not_found")
    if not review.receipt_key:
        raise NotFoundError("No proof of purchase on this review.",
                            code="receipt_not_found")
    ttl = settings.receipt_url_ttl_seconds
    url = signed_receipt_url(review.receipt_key, ttl)
    if url is None:
        # The row points at an object that is no longer in the bucket.
        raise NotFoundError("No proof of purchase on this review.",
                            code="receipt_not_found")

    # Audit AFTER authorization and AFTER the object is known to exist, so a
    # refused or empty request never writes a successful-access record. Only a
    # moderator is logged: an author opening their own evidence is not a
    # moderation action, and recording it would turn the audit trail into a
    # log of ordinary use.
    if _is_moderator(user) and user.id != review.author_id:
        db.add(ModerationLog(
            log_id=f"mlog_{uuid.uuid4().hex[:10]}",
            moderator_id=user.id,
            action=ModerationAction.receipt_view,
            target_type=ModerationTargetType.review,
            target_ref=review.id,
            # Deliberately no context: the object key, the signed URL and
            # anything off the receipt are exactly what must not be recorded.
        ))
        db.commit()

    return ReceiptAccess(url=url, expires_in=ttl)


@router.get("", response_model=list[ReviewOut],
            summary="List reviews (published; author/mod see more)")
def list_reviews(db: Session = Depends(get_db),
                 user: User | None = Depends(get_optional_user),
                 product_id: uuid.UUID | None = None,
                 include_unpublished: bool = False, limit: int = Query(50, ge=1, le=100),
                 sort: Literal["newest", "wilson"] = "newest") -> list[ReviewOut]:
    stmt = select(Review).where(Review.is_removed.is_(False))
    if product_id is not None:
        stmt = stmt.where(Review.product_id == product_id)
    if _is_moderator(user) and include_unpublished:
        pass  # moderators may see everything
    elif user is not None:
        stmt = stmt.where(or_(Review.published_at.isnot(None), Review.author_id == user.id))
    else:
        stmt = stmt.where(Review.published_at.isnot(None))
    if sort == "wilson":
        stmt = stmt.order_by(Review.wilson_score.desc(), Review.created_at.desc())
    else:
        stmt = stmt.order_by(Review.created_at.desc())
    rows = db.scalars(stmt.limit(limit))
    return [ReviewOut.model_validate(r) for r in rows]


def _feed_show(
    stars: list[Annotated[int, Field(ge=1, le=5)]] | None = Query(
        None, max_length=5,
        description="Rating: whole-star groups 1-5; a review is in the 4 group at 4 or 4.5 "
                    "stars. Several may be given (Figma 7762:9999)."),
    photos: bool = Query(False, description="Show only reviews with the reviewer's photos."),
    verified: bool = Query(False, description="Show only verified buyers (checked proof)."),
    recommends: bool = Query(False, description='Show only "Yes, absolutely" verdicts.'),
    variant: str | None = Query(
        None, max_length=120,
        description="One variant, as reviewers of the product reported it "
                    "(GET /reviews/feed/variants)."),
) -> review_filters.FeedShow:
    """The filter sheet's Rating, Show only and Variant (review_filters)."""
    return review_filters.FeedShow.of(stars=stars, photos=photos, verified=verified,
                                      recommends=recommends, variant=variant)


# Declared before "/{review_id}" so "feed" is matched as this route rather than
# being parsed as a review UUID (which would 422).
@router.get("/feed", response_model=list[FeedItemOut] | list[FeedCardOut],
            summary="Public feed: published reviews joined with author + product")
def review_feed(db: Session = Depends(get_db), limit: int = Query(8, ge=1, le=100),
                offset: int = Query(0, ge=0, le=1000),
                product_id: uuid.UUID | None = None,
                author_id: uuid.UUID | None = None,
                category: list[str] | None = Query(
                    None, max_length=12,
                    description="One or more categories; a review in any is shown (QA-025)."),
                q: str | None = Query(None, max_length=200),
                sort: Literal["newest", "oldest", "wilson", "lowest"] = "wilson",
                period: Period = Query(
                    "all", description="Time: all time, the past year or the past month."),
                lens: Lens | None = Query(
                    None, description="Review score lens (QA-053): hidden_gems, "
                    "controversial or trending. See app/services/review_lenses.py."),
                trust: TrustBand | None = Query(
                    None, description="Author trust score: high (80-100) or low (under 80)."),
                max_price: Decimal | None = Query(
                    None, gt=0, le=10_000_000,
                    description="Budget: at most this price paid (PHP)."),
                mode: Literal["plain", "for-you"] = "plain",
                view: Literal["full", "card"] = Query(
                    "full", description="card: only what a card shows, with a 200-character "
                    "excerpt instead of the discussion (FeedCardOut)."),
                show: review_filters.FeedShow = Depends(_feed_show),
                user: User | None = Depends(get_optional_user),
                ) -> list[FeedItemOut] | list[FeedCardOut]:
    """The public card feed, and the browsing feed behind `/feed`.

    `mode` defaults to `plain`, which is the behaviour every existing caller
    (landing, search, category, profile) already depends on — sort, slice,
    return. `for-you` is the only thing that ranks:

      * a bounded candidate pool is read at the requested sort,
      * reviews in the reader's chosen categories move to the front,
      * no author or product may take more than two of the visible slots.

    Both extra steps are pure functions in `review_service`, so the ranking is
    testable without a database, and both are no-ops when there is nothing to
    act on: a signed-out reader, or one who skipped onboarding interests, gets
    the same quality-and-recency feed as `plain` rather than an empty one.

    `offset` is bounded at 1000 rather than unbounded: this is a browsing feed,
    not an export.

    `view=card` returns the card shape (FeedCardOut): every card list on the
    site asks for it, because a card shows 180 characters of a review that can
    hold 11,000. The default stays the full shape for other API clients.
    """
    filters = dict(product_id=product_id, author_id=author_id, category=category, q=q,
                   sort=sort, period=period, lens=lens, trust=trust, max_price=max_price,
                   show=show)
    if view == "card":
        cards, _ = _feed_cards(db, user, limit=limit, offset=offset, mode=mode,
                               with_total=False, filters=filters)
        return cards
    if mode == "for-you":
        # Over-read so there is something to thin. Bounded, because a feed page
        # must not turn into a table scan.
        pool = review_service.list_feed(
            db, limit=min(limit * 4, 100), offset=offset, product_id=product_id,
            author_id=author_id, category=category, q=q, sort=sort, period=period,
            lens=lens, trust=trust, max_price=max_price, show=show)
        ranked = review_service.prioritise_interests(
            pool, user.interests if user is not None else None)
        items = review_service.diversify(ranked, limit=min(limit, 100))
    else:
        items = review_service.list_feed(
            db, limit=min(limit, 100), offset=offset, product_id=product_id,
            author_id=author_id, category=category, q=q, sort=sort, period=period,
            lens=lens, trust=trust, max_price=max_price, show=show)
    review_ids = [r.id for r, _, _ in items]
    mine = _my_votes(db, user, review_ids)
    comments = _comment_counts(db, review_ids)
    return [
        FeedItemOut(
            review=_out(r, mine.get(r.id)),
            author=FeedAuthor.model_validate(a) if a is not None else None,
            product=FeedProduct.model_validate(p) if p is not None else None,
            comment_count=comments.get(r.id, 0),
        )
        for r, a, p in items
    ]


def _feed_cards(db: Session, user: User | None, *, limit: int, offset: int, mode: str,
                with_total: bool, filters: dict) -> tuple[list[FeedCardOut], int | None]:
    """The card shape of `/feed`, ranked the same way, and optionally its total."""
    if mode == "for-you":
        pool, total = review_service.list_feed_cards(
            db, limit=min(limit * 4, 100), offset=offset, with_total=with_total, **filters)
        ranked = review_service.prioritise_interests(
            pool, user.interests if user is not None else None)
        rows = review_service.diversify(ranked, limit=min(limit, 100))
    else:
        rows, total = review_service.list_feed_cards(
            db, limit=min(limit, 100), offset=offset, with_total=with_total, **filters)
    review_ids = [r.id for r, _, _ in rows]
    mine = _my_votes(db, user, review_ids)
    comments = _comment_counts(db, review_ids)
    cards = []
    for r, a, p in rows:
        review = FeedCardReview.model_validate(r)
        review.my_vote = mine.get(r.id)
        cards.append(FeedCardOut(
            review=review,
            author=FeedAuthor.model_validate(a) if a is not None else None,
            product=FeedCardProduct.model_validate(p) if p is not None else None,
            comment_count=comments.get(r.id, 0),
        ))
    return cards, total


# Declared before "/{review_id}" for the same reason as "/feed".
@router.get("/feed/page", response_model=FeedPageOut,
            summary="A page of review cards and the filters' total, in one call")
def review_feed_page(db: Session = Depends(get_db), limit: int = Query(24, ge=1, le=100),
                     offset: int = Query(0, ge=0, le=1000),
                     product_id: uuid.UUID | None = None,
                     author_id: uuid.UUID | None = None,
                     category: list[str] | None = Query(None, max_length=12),
                     q: str | None = Query(None, max_length=200),
                     sort: Literal["newest", "oldest", "wilson", "lowest"] = "wilson",
                     period: Period = "all",
                     lens: Lens | None = None,
                     trust: TrustBand | None = None,
                     max_price: Decimal | None = Query(None, gt=0, le=10_000_000),
                     mode: Literal["plain", "for-you"] = "plain",
                     show: review_filters.FeedShow = Depends(_feed_show),
                     user: User | None = Depends(get_optional_user)) -> FeedPageOut:
    """`/feed?view=card` and `/feed/count` in one response, for the search's
    Reviews tab and the Feed, which show a page and number it. The total comes
    from the page's own query (count(*) OVER ()), so the two cannot disagree
    and the count costs no second round trip. `/feed/count` stays for the
    filter sheet's live "Show 42 reviews"."""
    cards, total = _feed_cards(
        db, user, limit=limit, offset=offset, mode=mode, with_total=True,
        filters=dict(product_id=product_id, author_id=author_id, category=category, q=q,
                     sort=sort, period=period, lens=lens, trust=trust,
                     max_price=max_price, show=show))
    return FeedPageOut(items=cards, total=total or 0)


class FeedCount(BaseModel):
    total: int


# Declared before "/{review_id}" for the same reason as "/feed".
@router.get("/feed/count", response_model=FeedCount,
            summary="How many published reviews the feed's filters match (for page numbers)")
def review_feed_count(db: Session = Depends(get_db),
                      product_id: uuid.UUID | None = None,
                      author_id: uuid.UUID | None = None,
                      category: list[str] | None = Query(None, max_length=12),
                      q: str | None = Query(None, max_length=200),
                      period: Period = "all",
                      lens: Lens | None = None,
                      trust: TrustBand | None = None,
                      max_price: Decimal | None = Query(None, gt=0, le=10_000_000),
                      show: review_filters.FeedShow = Depends(_feed_show)) -> FeedCount:
    """The total behind `/feed` with the same filters (MQA-036/037): the search's
    Reviews tab and the Feed number their pages and say "214 reviews". Same
    query as the page (`review_service._feed_stmt`), so the two never disagree.
    The filter sheet's "Show 42 reviews" asks it with the choices not yet applied."""
    return FeedCount(total=review_service.count_feed(
        db, product_id=product_id, author_id=author_id, category=category, q=q,
        period=period, lens=lens, trust=trust, max_price=max_price, show=show))


# Declared before "/{review_id}" for the same reason as "/feed".
@router.get("/feed/variants", response_model=list[str],
            summary="The variants one product's reviewers reported (the filter sheet's Variant)")
def review_feed_variants(product_id: uuid.UUID, db: Session = Depends(get_db)) -> list[str]:
    """Most-reviewed first, at most a dozen. Empty when no reviewer named one;
    the sheet then draws no Variant group."""
    return review_filters.variants_for_product(db, product_id)


class MyVotesOut(BaseModel):
    #: review id -> "up" or "down"; reviews the reader has not voted on are absent.
    votes: dict[str, VoteDirection]


# Declared before "/{review_id}" for the same reason as "/feed".
@router.get("/my-votes", response_model=MyVotesOut,
            summary="The signed-in reader's own votes on a set of reviews")
def my_votes(ids: list[uuid.UUID] = Query(..., min_length=1, max_length=100),
             db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> MyVotesOut:
    """Lets a signed-in reader's list come from the shared cache (cost plan,
    2026-10-22): the web app reads the anonymous, cached page of cards and asks
    only this for the reader's own votes, instead of fetching the whole list
    uncached because one field in it is personal. One query (`_my_votes`)."""
    return MyVotesOut(votes={str(k): v for k, v in _my_votes(db, user, ids).items()})


# Declared before "/{review_id}" for the same reason as "/feed".
@router.get("/mine", response_model=list[OwnReviewOut],
            summary="Your own reviews in every state, newest first")
def my_reviews(db: Session = Depends(get_db), user: User = Depends(get_current_user),
               limit: int = Query(24, ge=1, le=100),
               offset: int = Query(0, ge=0, le=1000)) -> list[OwnReviewOut]:
    """The caller's reviews — pending, published and rejected — for their profile.

    The author is the authenticated caller and nothing else: there is no
    author parameter, so this can never read someone else's unpublished work.
    Removed reviews are left out. Public surfaces keep using the
    publication-gated `/feed`; this route is never cached by the web app.
    """
    rows = review_service.list_own_reviews(db, user.id, limit=limit, offset=offset)
    review_ids = [r.id for r, _ in rows]
    mine = _my_votes(db, user, review_ids)
    comments = _comment_counts(db, review_ids)
    statuses = {r.id: review_service.publication_status(r) for r, _ in rows}
    reasons = review_service.rejection_reasons(
        db, [rid for rid, st in statuses.items() if st == review_service.REJECTED])
    author = FeedAuthor.model_validate(user)
    # §4: the newest entry of each live thread carries when the next may be added.
    newest_update: dict = {}
    seen_threads: set = set()
    for r, _ in rows:  # newest first, so the first of each thread is its newest
        if r.thread_key not in seen_threads:
            seen_threads.add(r.thread_key)
            newest_update[r.id] = review_service.next_update_at(r)
    return [
        OwnReviewOut(
            review=_out(r, mine.get(r.id)),
            author=author,
            product=FeedProduct.model_validate(p) if p is not None else None,
            comment_count=comments.get(r.id, 0),
            status=statuses[r.id],
            rejection_reason=reasons.get(r.id),
            next_update_at=newest_update.get(r.id),
        )
        for r, p in rows
    ]


@router.get("/{review_id}", response_model=ReviewOut, summary="Get a review")
def get_review(review_id: uuid.UUID, db: Session = Depends(get_db),
               user: User | None = Depends(get_optional_user)) -> ReviewOut:
    review = _visible_or_404(review_service.get_review_or_404(db, review_id), user)
    return _out(review, _my_votes(db, user, [review.id]).get(review.id))


@router.get("/{review_id}/full", response_model=FeedItemOut,
            summary="A review with its author + product (respects the publication gate)")
def get_review_full(review_id: uuid.UUID, db: Session = Depends(get_db),
                    user: User | None = Depends(get_optional_user)) -> FeedItemOut:
    review = _visible_or_404(review_service.get_review_or_404(db, review_id), user)
    author = db.get(User, review.author_id) if review.author_id is not None else None
    product = db.get(Product, review.product_id)
    reason = takedown = None
    if user is not None and review.author_id == user.id:
        reason = review_service.rejection_reasons(db, [review.id]).get(review.id)
        if review.published_at is None and not review.is_removed:
            takedown = review_service.takedown_reasons(db, [review.id]).get(review.id)
    return FeedItemOut(
        review=_out(review, _my_votes(db, user, [review.id]).get(review.id)),
        author=FeedAuthor.model_validate(author) if author is not None else None,
        product=FeedProduct.model_validate(product) if product is not None else None,
        comment_count=_comment_counts(db, [review.id]).get(review.id, 0),
        author_rejection_reason=reason,
        author_takedown_reason=takedown,
        **_listing_for(db, product),
    )


def _listing_for(db: Session, product: Product | None) -> dict:
    """QA-006: where the product is sold, for a review with no affiliate link.

    The product's recorded listings first (one per marketplace), then the link
    it was submitted with; only a link on a known marketplace host.
    """
    if product is None:
        return {}
    from app.models.product import ProductPlatform
    from app.services.canonical_service import marketplace_for_url
    candidates = [row.platform_url for row in db.scalars(
        select(ProductPlatform).where(ProductPlatform.product_id == product.id)
        .order_by(ProductPlatform.created_at))]
    candidates.append(product.source_url)
    for url in candidates:
        platform = marketplace_for_url(url)
        if url and platform is not None and url.lower().startswith("https://"):
            return {"listing_url": url, "listing_platform": platform.value}
    return {}


@router.patch("/{review_id}", response_model=ReviewOut,
              summary="Replace a review's photo (once, within 72 hours)")
def update_review(review_id: uuid.UUID, payload: ReviewUpdate,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> ReviewOut:
    """Business Rules §4: published text, rating and verdict are frozen. The
    only change allowed is one photo swap within 72 hours, by the author."""
    review = review_service.get_review_or_404(db, review_id)
    if review.author_id != user.id:
        raise ForbiddenError("Only the author may replace this review's photo.",
                             code="not_review_owner")
    _own_photos_or_403(payload.photos(), user)
    _own_receipt_key_or_400(payload.receipt_key, user)
    review = review_service.update_review(db, review, user.id, payload)
    return ReviewOut.model_validate(review)


@router.post("/{review_id}/updates", response_model=ReviewOut, status_code=201,
             summary="Add an update entry to your review's thread (every 3 months)")
def add_update(review_id: uuid.UUID, payload: ReviewEntryIn,
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> ReviewOut:
    entry = review_service.get_review_or_404(db, review_id)
    _own_photos_or_403(payload.photo_urls, user)
    _own_receipt_key_or_400(payload.receipt_key, user)
    created = review_service.add_thread_update(db, entry, user.id, payload)
    return ReviewOut.model_validate(created)


@router.get("/{review_id}/thread", response_model=ThreadOut,
            summary="A review's thread: every visible entry, the latest counts")
def get_thread(review_id: uuid.UUID, db: Session = Depends(get_db),
               user: User | None = Depends(get_optional_user)) -> ThreadOut:
    review = _visible_or_404(review_service.get_review_or_404(db, review_id), user)
    entries = review_service.thread_entries(db, review.thread_key)
    if not entries:
        entries = [review]
    latest_id = entries[-1].id
    next_at = None
    if user is not None and review.author_id == user.id:
        newest = review_service.active_thread_for(db, user.id, review.product_id)
        next_at = review_service.next_update_at(newest) if newest is not None else None
    return ThreadOut(
        thread_id=review.thread_key,
        entries=[ThreadEntryOut(
            id=e.id, title=e.title, verdict=e.verdict, star_rating=float(e.star_rating),
            published_at=e.published_at, created_at=e.created_at,
            is_root=e.is_thread_root, is_latest=e.id == latest_id) for e in entries],
        next_update_at=next_at,
    )


@router.delete("/{review_id}", response_model=ThreadDeleted,
               summary="Delete your review entry (the root deletes the whole thread)")
def delete_review(review_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user),
                  confirm: str | None = Query(None, max_length=32)) -> ThreadDeleted:
    """§4: an update entry can be deleted on its own. Deleting the original
    deletes the whole thread and needs `?confirm=delete-thread`."""
    review = db.get(Review, review_id)
    if review is not None and review.removed_by_author_at is not None \
            and review.author_id == user.id:
        # Idempotent for its author: deleting what they already deleted is not
        # an error (a double tap, a retry after a dropped response). Anyone
        # else still gets the same 404 as for a review that never existed.
        return ThreadDeleted(removed_ids=[])
    review = review_service.get_review_or_404(db, review_id)
    removed = review_service.delete_entry(db, review, user.id, confirm=confirm)
    return ThreadDeleted(removed_ids=removed)


@router.get("/{review_id}/versions", response_model=list[ReviewVersionOut],
            summary="List a review's version history")
def list_versions(review_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User | None = Depends(get_optional_user)) -> list[ReviewVersionOut]:
    review = review_service.get_review_or_404(db, review_id)
    _visible_or_404(review, user)
    return [ReviewVersionOut.model_validate(v) for v in review_service.list_versions(db, review_id)]


@router.get("/{review_id}/versions/{version_number}", response_model=ReviewVersionOut,
            summary="Get a specific review version")
def get_version(review_id: uuid.UUID, version_number: int, db: Session = Depends(get_db),
                user: User | None = Depends(get_optional_user)) -> ReviewVersionOut:
    _visible_or_404(review_service.get_review_or_404(db, review_id), user)
    version = db.scalar(select(ReviewVersion).where(
        ReviewVersion.review_id == review_id,
        ReviewVersion.version_number == version_number))
    if version is None:
        raise NotFoundError("Review version not found.", code="version_not_found")
    return ReviewVersionOut.model_validate(version)


@router.post("/{review_id}/vote", response_model=ReviewOut,
             summary="Cast or change a helpfulness vote on a published review")
def vote_review(review_id: uuid.UUID, payload: VoteIn, request: Request,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> ReviewOut:
    enforce_rate_limit(request, "vote", max_requests=settings.vote_rate_limit_max)
    review = review_service.get_review_or_404(db, review_id)
    result = vote_service.cast_vote(db, review, user, payload.vote)
    # Capture every scalar the telemetry tails (and their logs) need *before*
    # either one can run. A tail's caught rollback — or an uncaught raise from
    # the first tail reaching the second — expires every ORM object in the
    # session, so `result.review.id` read afterward would trigger a lazy
    # reload outside this guard and could turn an already-committed vote into
    # an HTTP failure.
    voted_review_id = result.review.id
    voted_author_id = result.review.author_id
    created = result.created
    # Echo the vote just cast rather than re-reading it: the client uses this
    # response to set its pressed state, so it must not come back empty. Built
    # (and fully serialized) before the telemetry tail below: a failed
    # telemetry rollback can expire the underlying ORM object, and the
    # already-committed vote response must survive it.
    out = _out(result.review, payload.vote)

    # Write-only, best-effort telemetry tail. Each helper below owns its own
    # transaction and already isolates its own failures; this call site
    # isolates a second time so an unexpected raise straight out of a helper
    # (not just a caught one) can never turn a successful vote into an error.
    try:
        reading_telemetry_service.note_vote(db, voted_review_id, user.id)
    except Exception:  # noqa: BLE001 - the vote response must survive this
        db.rollback()
        logger.warning("vote telemetry tail failed", extra={"extra_fields": {
            "review_id": str(voted_review_id), "action": "note_vote"}})

    if payload.vote == VoteDirection.up:
        # Vote-farming network signal (QA 2026-09-29): a keyed hash of the
        # voter's trusted network, never an address; flags, never blocks.
        try:
            from app.services import vote_network
            vote_network.record_upvote(db, request, review_id=voted_review_id,
                                       author_id=voted_author_id, voter=user)
            db.commit()
        except Exception:  # noqa: BLE001 - same reasoning
            db.rollback()
            logger.warning("vote network tail failed", extra={"extra_fields": {
                "review_id": str(voted_review_id)}})

    if created:
        try:
            request_traffic_service.record_first_vote_geo(
                db, voted_review_id, from_headers(request.headers))
        except Exception:  # noqa: BLE001 - same reasoning
            db.rollback()
            logger.warning("vote telemetry tail failed", extra={"extra_fields": {
                "review_id": str(voted_review_id), "action": "record_first_vote_geo"}})

    return out


@router.delete("/{review_id}/vote", response_model=ReviewOut,
               summary="Remove your helpfulness vote from a review")
def unvote_review(review_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> ReviewOut:
    review = review_service.get_review_or_404(db, review_id)
    review = vote_service.remove_vote(db, review, user.id)
    # The vote is gone, so my_vote is None — the schema default, stated here so
    # the symmetry with the POST above is visible rather than inferred.
    return _out(review, None)


@router.post("/{review_id}/report", response_model=ReportOut, status_code=201,
             summary="Report a published review to the administrators")
def report_review(review_id: uuid.UUID, payload: ReportCreate, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> ReportOut:
    # Same 60s bucket shape as voting: reporting is a community action and the
    # limiter is what stops one account from carpet-reporting a reviewer.
    enforce_rate_limit(request, "report", max_requests=settings.report_rate_limit_max)
    review = review_service.get_review_or_404(db, review_id)
    # Only reportable once visible — an unpublished draft is already in the
    # moderator queue, and 404ing keeps drafts unenumerable by non-authors.
    _visible_or_404(review, user)
    log, _created = report_service.file_report(
        db,
        reporter_id=user.id,
        author_id=review.author_id,
        target_type=ModerationTargetType.review,
        target_ref=review.id,
        reason=payload.reason,
        notes=payload.notes,
        evidence_url=payload.evidence_url,
    )
    # A repeat report returns 201 with the original row: the reporter's intent is
    # satisfied either way, and telling them "already reported" leaks nothing.
    return ReportOut.model_validate(log)


@router.post("/{review_id}/critique", response_model=CritiqueResponse,
             summary="AI critique of a stored review (author or administrator)")
def critique_review(review_id: uuid.UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> CritiqueResponse:
    review = review_service.get_review_or_404(db, review_id)
    if review.author_id != user.id and not is_staff(user):
        raise ForbiddenError("Only the author or an administrator may critique this review.",
                             code="not_review_owner")
    # The same per-account allowance as POST /ai/critique: one paid provider.
    enforce_user_rate_limit(user.id, "ai_critique",
                            max_requests=settings.ai_critique_rate_limit_max,
                            window_seconds=3600)
    return get_provider().critique(review.title, review.discussion)

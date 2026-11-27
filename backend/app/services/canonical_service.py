"""Canonical products and their marketplace listings (Business Rules §5, §6).

    "One canonical product per real-world item, holding multiple
    platform-specific listings underneath it ... If a user can't find a product,
    they submit a marketplace link, which goes to an admin queue and is either
    canonicalized as a new product or attached as a new platform listing on an
    existing one."

Synonym curation is folded into the same workflow (§6): naming a product can
add aliases, and attaching a submission records its submitted name as an alias
of the product it joined, so search learns the name people actually used.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.models.enums import (
    ImageSource,
    ModerationAction,
    Platform,
    ProductStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import PriceHistory, Product, ProductAlias, ProductPlatform
from app.models.qa import Question
from app.models.review import Review
from app.services.product_search import normalize
from app.services.storage import upload_product_image

MAX_ALIASES = 20


def platform_for_url(url: str | None) -> Platform:
    host = (url or "").lower()
    if "shopee" in host or "shope.ee" in host or "shp.ee" in host:
        return Platform.shopee
    if "lazada" in host:
        return Platform.lazada
    if "amazon" in host or "amzn." in host:
        return Platform.amazon
    return Platform.other


def marketplace_for_url(url: str | None) -> Platform | None:
    """The marketplace a link's host belongs to, or None for any other site."""
    host = (urlsplit(url).hostname or "").lower() if url else ""
    for platform, domains in settings.affiliate_domains.items():
        if host and any(host == d or host.endswith("." + d) for d in domains):
            return Platform(platform)
    return None


def record_source_listing(db: Session, product: Product) -> None:
    """The marketplace link a product was submitted with is its first listing (§5).

    attach_listing records a duplicate submission's link as a listing, but the
    product's own link was never recorded, so a product sold on one
    marketplace looked like one with no listing at all - and its
    earnings-approved reviews never reached the affiliate-link queue, which
    lists only products with a monetizable listing
    (monetization_attention._awaiting_filter). Idempotent.
    """
    platform = marketplace_for_url(product.source_url)
    if platform is None:
        return
    exists = db.scalar(select(ProductPlatform.id).where(
        ProductPlatform.product_id == product.id, ProductPlatform.platform == platform,
        ProductPlatform.platform_url == product.source_url))
    if exists is None:
        db.add(ProductPlatform(product_id=product.id, platform=platform,
                               platform_url=product.source_url))


def add_aliases(db: Session, product: Product, aliases: list[str],
                actor_id: uuid.UUID | None) -> list[str]:
    """Record synonyms for a product; duplicates and its own name are skipped."""
    existing = {a for (a,) in db.execute(
        select(ProductAlias.normalized).where(ProductAlias.product_id == product.id)).all()}
    own = normalize(product.canonical_name)
    added: list[str] = []
    for raw in aliases[:MAX_ALIASES]:
        alias = (raw or "").strip()[:160]
        key = normalize(alias)
        if not key or key == own or key in existing:
            continue
        db.add(ProductAlias(product_id=product.id, alias=alias, normalized=key,
                            created_by_id=actor_id))
        existing.add(key)
        added.append(alias)
    if added:
        db.add(ModerationLog(target_type=None, target_ref=product.id, moderator_id=actor_id,
                             action=ModerationAction.alias_add, context={"aliases": added}))
    return added


def remove_alias(db: Session, product: Product, alias: str,
                 actor_id: uuid.UUID | None) -> bool:
    """Take a synonym off a product (matched as search matches it); audited."""
    key = normalize(alias)
    row = db.scalar(select(ProductAlias).where(ProductAlias.product_id == product.id,
                                               ProductAlias.normalized == key))
    if row is None:
        return False
    db.delete(row)
    db.add(ModerationLog(target_type=None, target_ref=product.id, moderator_id=actor_id,
                         action=ModerationAction.alias_remove, context={"alias": row.alias}))
    return True


def set_product_image(db: Session, product: Product, data: bytes,
                      actor_id: uuid.UUID) -> Product:
    """A moderator supplies the product's picture (QA-001).

    38 of the 43 products on production had no image, and the only way to give
    one a picture was the owner running `scripts/seed_product_images.py` by
    hand, so their cards and search rows could only ever show the placeholder.
    `ImageSource.moderator` was reserved for exactly this and never set.

    The bytes are sniffed and size-capped by `upload_product_image` before
    anything is stored; the browser's Content-Type is never trusted. The
    audit row uses `photo_replace`, the existing action for a replaced photo,
    with the product as its target, as alias and attach rows are, so no enum
    value (and no migration) is needed.
    """
    had_image = bool(product.image_url)
    product.image_url = upload_product_image(product.id, data)
    product.image_source = ImageSource.moderator
    product.image_fetched_at = datetime.now(UTC)
    db.add(ModerationLog(target_type=None, target_ref=product.id, moderator_id=actor_id,
                         action=ModerationAction.photo_replace,
                         context={"subject": "product_image", "replaced": had_image}))
    return product


def attach_listing(db: Session, submission_id: uuid.UUID, target_id: uuid.UUID,
                   moderator_id: uuid.UUID) -> Product:
    """Attach a pending submission to an existing canonical product (§5).

    The submission's marketplace listing becomes another ProductPlatform row on
    the target, anything already written against the submission (reviews,
    questions, prices) moves with it, and the submitted name becomes an alias.
    The submission itself is closed — never deleted, so the audit trail holds.
    """
    if submission_id == target_id:
        raise AppError("A product cannot be attached to itself.", code="attach_self",
                       status_code=422, title="Invalid attach")
    submission = db.get(Product, submission_id, with_for_update=True)
    target = db.get(Product, target_id)
    if submission is None or target is None:
        raise NotFoundError("Product not found.", code="product_not_found")
    if submission.status != ProductStatus.pending:
        raise AppError("Only a pending submission can be attached.",
                       code="not_pending_submission", status_code=409,
                       title="Conflicting state")
    if target.status != ProductStatus.canonicalized:
        raise AppError("Attach to a canonical product.", code="target_not_canonical",
                       status_code=409, title="Conflicting state")
    return _move_into(db, submission, target, moderator_id, kind="attach")


def merge_products(db: Session, source_id: uuid.UUID, target_id: uuid.UUID,
                   moderator_id: uuid.UUID) -> Product:
    """Merge one catalogue product into another (Confirm/Product/Merge 8287:29648).

    The same move as attaching a submission, for two canonical pages of one
    real product: everything written against the source follows it to the
    target, its aliases come along, and its name becomes one more alias.
    """
    if source_id == target_id:
        raise AppError("A product cannot be merged into itself.", code="merge_self",
                       status_code=422, title="Invalid merge")
    source = db.get(Product, source_id, with_for_update=True)
    target = db.get(Product, target_id)
    if source is None or target is None:
        raise NotFoundError("Product not found.", code="product_not_found")
    if source.status == ProductStatus.rejected:
        raise AppError("That product was already merged or rejected.",
                       code="merge_source_closed", status_code=409, title="Conflicting state")
    if target.status != ProductStatus.canonicalized:
        raise AppError("Merge into a catalogue product.", code="target_not_canonical",
                       status_code=409, title="Conflicting state")
    from app.models.product import ProductAlias
    from app.models.seller import SellerReview
    taken = {a.normalized for a in db.scalars(
        select(ProductAlias).where(ProductAlias.product_id == target.id))}
    for alias in list(db.scalars(select(ProductAlias).where(ProductAlias.product_id == source.id))):
        if alias.normalized in taken:
            db.delete(alias)
        else:
            alias.product_id = target.id
            taken.add(alias.normalized)
    db.execute(update(SellerReview).where(SellerReview.product_id == source.id)
               .values(product_id=target.id))
    db.flush()
    return _move_into(db, source, target, moderator_id, kind="merge")


def _move_into(db: Session, submission: Product, target: Product, moderator_id: uuid.UUID,
               *, kind: str) -> Product:

    existing = {(p.platform, p.platform_url) for p in db.scalars(
        select(ProductPlatform).where(ProductPlatform.product_id == target.id))}
    for listing in list(db.scalars(select(ProductPlatform).where(
            ProductPlatform.product_id == submission.id))):
        if (listing.platform, listing.platform_url) in existing:
            db.delete(listing)
        else:
            listing.product_id = target.id
            existing.add((listing.platform, listing.platform_url))
    if submission.source_url:
        key = (platform_for_url(submission.source_url), submission.source_url)
        if key not in existing:
            db.add(ProductPlatform(product_id=target.id, platform=key[0],
                                   platform_url=submission.source_url))
    moved_ids = list(db.scalars(select(Review.id).where(Review.product_id == submission.id)))
    moved_reviews = db.execute(update(Review).where(Review.product_id == submission.id)
                               .values(product_id=target.id)
                               .execution_options(synchronize_session="fetch")).rowcount or 0
    db.execute(update(Question).where(Question.product_id == submission.id)
               .values(product_id=target.id))
    db.execute(update(PriceHistory).where(PriceHistory.product_id == submission.id)
               .values(product_id=target.id))
    add_aliases(db, target, [submission.canonical_name or ""], moderator_id)
    if submission.category and not target.category:
        # QA-071: the reviewer's category is kept when the canonical product
        # has none; one the target already has is never overwritten.
        target.category = submission.category
    # QA-071/074: the submission's requests follow its reviews to the canonical
    # product, and a moved review now answers the target's open requests.
    from app.services import request_service
    request_service.move_to_product(db, submission.id, target.id)
    db.flush()
    for review in db.scalars(select(Review).where(Review.id.in_(moved_ids))) if moved_ids else ():
        request_service.announce_answer(db, review)
    submission.status = ProductStatus.rejected
    db.add(ModerationLog(target_type=None, target_ref=submission.id, moderator_id=moderator_id,
                         action=ModerationAction.listing_attach,
                         context={"attached_to": str(target.id), "reviews_moved": moved_reviews,
                                  "kind": kind}))
    from app.services.review_service import recompute_product_aggregates
    recompute_product_aggregates(db, target.id)
    recompute_product_aggregates(db, submission.id)
    db.commit()
    db.refresh(target)
    return target


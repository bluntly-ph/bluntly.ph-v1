"""Page-shaped reads: everything one page needs, in one call.

WHY THIS EXISTS (cost plan, 2026-10-22). Every backend call the web app makes
is a separate billed function invocation on Vercel, a separate database
transaction, and a round trip through the CDN. The review page made seven of
them per visit, in two rounds (the second waited for the product id the first
returned). That fan-out, multiplied by crawler traffic, was most of the bill.

These routes do not add behaviour. Each part of the answer is produced by the
same handler or service that answers it on its own route, with the same
viewer, so the publication gate, the viewer's own votes and every field stay
exactly as they were. Only the number of trips changes.

A part that fails on its own route degraded to a fallback in the web app
(comments to [], the thread and the price panel to nothing, the payout count to
0, related reviews to none); it degrades the same way here, so one wobbling
part never costs the reader the whole page. The review itself does not: a
review the viewer may not see is a 404 here exactly as on `/reviews/{id}/full`.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.routes import comments as comment_routes
from app.api.v1.routes import products as product_routes
from app.api.v1.routes import reviews as review_routes
from app.api.v1.routes.products import SearchCardOut
from app.core.logging import get_logger
from app.core.security import get_optional_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.comment import CommentOut
from app.schemas.product import PricePanelOut, ProductOut
from app.schemas.review import FeedCardOut, FeedItemOut, ThreadOut
from app.services.review_service import removed_after_payout_count

log = get_logger(__name__)

router = APIRouter(prefix="/pages", tags=["pages"])

#: The desktop sidebar shows four related reviews; one extra so that leaving
#: out the review being read still leaves four (as app/reviews/[id] did).
RELATED_LIMIT = 5

def _part[T](db: Session, name: str, read: Callable[[], T], fallback: T) -> T:
    """One optional part of a page: its value, or its fallback on any failure.

    The failed read's transaction is rolled back so the parts after it start
    clean, and the failure is logged by name (never by content).
    """
    try:
        return read()
    except Exception as exc:  # noqa: BLE001 - a part must never sink the page
        db.rollback()
        log.warning("page part failed", extra={"extra_fields": {
            "part": name, "error": type(exc).__name__}})
        return fallback


class ReviewPageOut(BaseModel):
    """Everything app/reviews/[id] renders, in one response."""

    review: FeedItemOut
    comments: list[CommentOut]
    thread: ThreadOut | None = None
    price_panel: PricePanelOut | None = None
    #: Card-shaped, read signed out: the sidebar never showed the viewer's votes.
    related: list[FeedCardOut]
    removed_after_payout_count: int = 0


@router.get("/review/{review_id}", response_model=ReviewPageOut,
            summary="A review page's data in one call: review, comments, thread, "
                    "price panel, related reviews and the payout-removal count")
def review_page(review_id: uuid.UUID, db: Session = Depends(get_db),
                user: User | None = Depends(get_optional_user)) -> ReviewPageOut:
    # Not wrapped: the publication gate decides whether there is a page at all.
    review = review_routes.get_review_full(review_id, db, user)
    product = review.product

    comments = _part(db, "comments",
                     lambda: comment_routes.list_comments(review_id, db, user), [])
    thread = _part(db, "thread", lambda: review_routes.get_thread(review_id, db, user), None)
    price_panel = (
        _part(db, "price_panel", lambda: product_routes.get_price_panel(product.id, db), None)
        if product is not None else None
    )
    removed = (
        _part(db, "removed_after_payout",
              lambda: removed_after_payout_count(db, product.id), 0)
        if product is not None else 0
    )
    related: list[FeedCardOut] = []
    if product is not None and product.category:
        related = _part(db, "related", lambda: review_routes._feed_cards(
            db, None, limit=RELATED_LIMIT, offset=0, mode="plain", with_total=False,
            filters=dict(category=[product.category], sort="wilson"))[0], [])

    return ReviewPageOut(review=review, comments=comments, thread=thread,
                         price_panel=price_panel, related=related,
                         removed_after_payout_count=removed)


# --------------------------------------------------------------------------
# The search page's product match (was lib/search-product.ts, 2026-10-22).
# --------------------------------------------------------------------------

search_router = APIRouter(prefix="/search", tags=["search"])

#: Products a match lists (the Switch sheet), as before.
MAX_MATCHES = 6
#: Words dropped from the end, at most, while looking for the product.
MAX_TRIES = 4

#: Python's spelling of the web app's /[^\p{L}\p{N}]+/u: anything that is not a
#: letter or a digit. `\W` keeps the underscore, so it is excluded by hand.
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)


class ProductMatchOut(BaseModel):
    product: ProductOut
    card: SearchCardOut | None = None


class ProductResolutionOut(BaseModel):
    """Which product a search names, and what the rest of it asks."""

    #: The products the query names, most-reviewed first (the Switch sheet).
    matches: list[ProductMatchOut]
    #: The one the bar shows: the reader's pick, else the best match.
    chosen: ProductMatchOut
    #: The words that named the product, and what is left (the question).
    productTerms: str  # noqa: N815 - the web app's existing field names
    rest: str


def _browse(db: Session, q: str) -> list[ProductOut]:
    return product_routes.list_products(db=db, limit=MAX_MATCHES, q=q,
                                        include_low_trust=False, browse=True)


def _card(db: Session, product_id: uuid.UUID) -> SearchCardOut | None:
    return _part(db, "search_card", lambda: product_routes.get_search_card(product_id, db), None)


def _in_name(word: str, name_words: list[str]) -> bool:
    """A query word names the product when a word of its name starts with it,
    or (from four letters) it starts with a word of the name."""
    w = _NON_WORD.sub("", word.lower())
    return bool(w) and any(n.startswith(w) or (len(w) >= 4 and w.startswith(n))
                           for n in name_words)


def resolve_product(db: Session, q: str, pick: str | None) -> ProductResolutionOut | None:
    """Port of lib/search-product.ts `resolveSearchProduct`, unchanged in effect.

    Each leading run of words, dropping up to MAX_TRIES from the end, is looked
    up. Typo tolerance lets a longer run still find something weaker, so the
    run kept is the LONGEST whose best match is as reviewed as any run found;
    the words after it are the question. None when nothing matches.
    """
    words = q.split()
    if not words:
        return None
    lengths = list(range(len(words), max(1, len(words) - MAX_TRIES) - 1, -1))
    runs = [_part(db, "search_run", lambda n=n: _browse(db, " ".join(words[:n])), [])
            for n in lengths]
    top = [run[0].review_count if run else -1 for run in runs]
    best = max([-1, *top])
    if best < 0:
        return None
    at = top.index(best)
    found, used = runs[at], lengths[at]
    matches = [ProductMatchOut(product=p, card=_card(db, p.id)) for p in found]

    chosen = next((m for m in matches if str(m.product.id) == pick), None)
    if chosen is None and pick:
        try:
            picked_id = uuid.UUID(pick)
        except ValueError:
            picked_id = None
        if picked_id is not None:
            picked = _part(db, "picked_product",
                           lambda: product_routes.get_product(picked_id, db), None)
            if picked is not None:
                chosen = ProductMatchOut(product=picked, card=_card(db, picked.id))
    chosen = chosen or matches[0]

    name_words = [w for w in _NON_WORD.split((chosen.product.canonical_name or "").lower()) if w]
    product_words = [w for w in words[:used] if _in_name(w, name_words)]
    question_words = [w for i, w in enumerate(words) if i >= used or not _in_name(w, name_words)]
    return ProductResolutionOut(
        matches=matches,
        chosen=chosen,
        productTerms=" ".join(product_words or words[:used]),
        rest=" ".join(question_words),
    )


@search_router.get("/resolve", response_model=ProductResolutionOut | None,
                   summary="Which product a search names, and the question left over "
                           "(the search page's product bar), in one call")
def search_resolve(q: str = Query(..., max_length=200),
                   pick: str | None = Query(None, max_length=64),
                   db: Session = Depends(get_db)) -> ProductResolutionOut | None:
    return resolve_product(db, q, pick)

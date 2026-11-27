"""The rest of the All filters sheet (Figma 1587:4658, QA-053).

The frame draws three groups beyond Category and Time: a Review score lens
(Most Helpful / Hidden Gems / Controversial / Trending), a Trust rating
(All / 0–70 / 80–100) and a Budget slider (Thrifty ↔ Balanced). Nothing
defined them, so they were left out; the retest still failed the sheet, and
the owner asked for it fixed (2026-09-28). These are the definitions, written
down once here so the sheet, the rail and the API mean the same thing. Each is
built only from numbers the site already shows a reader, so a filter never
sorts on something the reader cannot see:

* **Most Helpful** — the feed's default order (Wilson lower bound on helpful
  votes). Not a filter; it is "no lens".
* **Hidden Gems** — a review readers found helpful (at least one helpful
  vote, and more helpful than unhelpful) of a product with at most
  ``HIDDEN_GEM_MAX_REVIEWS`` published reviews: a good review of something few
  people have covered yet. Most helpful first.
* **Controversial** — readers split on it: at least one vote each way, and
  the smaller side at least half the larger. Most votes first.
* **Trending** — helpful votes cast and comments posted in the past
  ``TRENDING_DAYS`` days; at least one. Most of that activity first.
* **Trust rating** — the author's trust score (0..100, ADR-003), the number
  printed beside their level on every review. Two bands: 80–100, and under
  80. (The frame's "0–70" left 71–79 in neither band; "under 80" closes it.)
* **Budget** — what the reviewer says they paid, at most the amount chosen.
  A review with no price paid is left out once a budget is set: it cannot be
  said to fit one.

Votes and the trust score move no money here; these are reading lenses only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.comment import ReviewComment
from app.models.enums import VoteDirection
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote

Lens = Literal["hidden_gems", "controversial", "trending"]
TrustBand = Literal["high", "low"]

HIDDEN_GEM_MAX_REVIEWS = 3
TRENDING_DAYS = 7
TRUST_HIGH_FROM = Decimal("80")


def _product_review_count() -> ColumnElement:
    """How many reviewers have a published review of the row's product (one
    per thread, so a reviewer's updates do not count twice)."""
    peer = aliased(Review)
    return (
        select(func.count(func.distinct(func.coalesce(peer.thread_id, peer.id))))
        .where(peer.product_id == Review.product_id, peer.is_removed.is_(False),
               peer.published_at.isnot(None))
        .correlate(Review)
        .scalar_subquery()
    )


def _recent_activity(now: datetime | None = None) -> ColumnElement:
    since = (now or datetime.now(UTC)) - timedelta(days=TRENDING_DAYS)
    votes = (
        select(func.count(ReviewVote.id))
        .where(ReviewVote.review_id == Review.id, ReviewVote.vote == VoteDirection.up,
               ReviewVote.updated_at >= since)
        .correlate(Review)
        .scalar_subquery()
    )
    comments = (
        select(func.count(ReviewComment.id))
        .where(ReviewComment.review_id == Review.id, ReviewComment.is_removed.is_(False),
               ReviewComment.created_at >= since)
        .correlate(Review)
        .scalar_subquery()
    )
    return votes + comments


def apply_lens(stmt: Select, lens: Lens | None, *, keep_order: bool,
               now: datetime | None = None) -> Select:
    """Narrow (and, unless the reader chose an order, order) by a lens."""
    if lens is None:
        return stmt
    up, down = Review.helpful_votes, Review.unhelpful_votes
    if lens == "hidden_gems":
        stmt = stmt.where(up >= 1, up > down,
                          _product_review_count() <= HIDDEN_GEM_MAX_REVIEWS)
        order = (Review.wilson_score.desc(), Review.created_at.desc(), Review.id.desc())
    elif lens == "controversial":
        stmt = stmt.where(up >= 1, down >= 1,
                          2 * func.least(up, down) >= func.greatest(up, down))
        order = ((up + down).desc(), Review.created_at.desc(), Review.id.desc())
    else:
        activity = _recent_activity(now)
        stmt = stmt.where(activity >= 1)
        order = (activity.desc(), Review.created_at.desc(), Review.id.desc())
    return stmt if keep_order else stmt.order_by(*order)


def trust_clause(band: TrustBand | None) -> ColumnElement | None:
    """A condition on the review's author, or None for every author."""
    if band is None:
        return None
    score = select(User.reputation_score).where(User.id == Review.author_id) \
        .correlate(Review).scalar_subquery()
    # A deleted author has no score, and so falls in neither band.
    return score >= TRUST_HIGH_FROM if band == "high" else score < TRUST_HIGH_FROM


def budget_clause(max_price: Decimal | None) -> ColumnElement | None:
    if max_price is None:
        return None
    return and_(Review.price_paid.isnot(None), Review.price_paid <= max_price)

"""What a moderator sees when they investigate one review (Figma
Overlay/Review/Investigate: Summary 8109:17496, Votes 8110:17539, Voters
8117:17753). Read-only: nothing here removes a vote, holds money or tells
anyone they were looked at (docs/ANTI_FARMING_AND_PLAGIARISM.md).

Every figure is read from records: the votes as cast (direction, time, the
weight snapshotted on each, the voter's stage), the vote-network fingerprints
the up-vote path stores as keyed hashes (never an address; 30-day retention),
and the voters' votes on the author's other reviews.

A vote is FLAGGED, for this view only, when its voter
* shares a network with another voter on this review (fingerprints still
  retained), or
* is in the author's voting circle: up-voted at least CIRCLE_SHARE of the
  author's published reviews, over at least CIRCLE_MIN_REVIEWS of them.
Both are signals, not findings. "Without flagged" recomputes the earnings
gate's own arithmetic (`earn_gate._gate_from_rows`) with those voters left
out, so the moderator can see whether the review passes on the rest.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.categories import spellings_for
from app.models.enums import VoteDirection
from app.models.integrity import VoteNetworkFingerprint
from app.models.product import Product
from app.models.review import Review
from app.models.user import TRUST_LEVEL_NAMES, User
from app.models.vote import ReviewVote
from app.services.earn_gate import GateState, _gate_from_rows

HISTORY = 20             # the author's reviews shown per voter (Voters tab)
CIRCLE_SHARE = 0.8       # up-voted at least this share of the author's reviews…
CIRCLE_MIN_REVIEWS = 5   # …over at least this many of them
EARLY = timedelta(minutes=10)
QUICK = timedelta(minutes=5)
NEW_ACCOUNT_DAYS = 30
TYPICAL_SAMPLE = 400     # recent reviews in the category, for "typical"
PLACES = 5               # places named in "Where votes came from"


@dataclass
class Signal:
    kind: str            # same_network | voting_circle | new_account | always_quick
    label: str


@dataclass
class VoterRow:
    voter_id: uuid.UUID
    name: str
    username: str | None
    stage: int
    level_name: str | None
    vote: str            # up | down
    seconds_after: int   # since the review was published
    flagged: bool
    signals: list[Signal] = field(default_factory=list)
    #: The author's last HISTORY published reviews, oldest first: up / down / None.
    history: list[str | None] = field(default_factory=list)
    agreement: int = 0   # up-votes among `history`
    #: The weight the vote carries in the score (0 for a suspended or claimed
    #: seller account; None for a vote cast before weights were recorded).
    weight: float | None = None


@dataclass
class Investigation:
    review_id: uuid.UUID
    published_at: datetime
    votes_total: int
    up: int
    down: int
    first_10_min: int
    typical_first_10_min: float | None
    flagged: int
    flagged_stage2_plus: int
    gate_all: GateState
    gate_without_flagged: GateState
    voters: list[VoterRow]
    history_size: int
    #: "Where votes came from": first-time votes per place, most first.
    places: list[tuple[str, int]] = field(default_factory=list)
    #: Places beyond the top PLACES, folded into one row.
    places_other: int = 0
    places_other_count: int = 0


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _name(u: User | None) -> str:
    if u is None:
        return "Former member"
    return u.display_name or (f"@{u.username}" if u.username else "Member")


def _typical_first_10(db: Session, review: Review) -> float | None:
    """Median count of votes in the first 10 minutes across recent published
    reviews in the same category (this one excluded)."""
    product = db.get(Product, review.product_id)
    if product is None or not product.category:
        return None
    recent = (select(Review.id, Review.published_at)
              .join(Product, Product.id == Review.product_id)
              .where(Product.category.in_(spellings_for(product.category)),
                     Review.published_at.is_not(None), Review.is_removed.is_(False),
                     Review.id != review.id)
              .order_by(Review.published_at.desc()).limit(TYPICAL_SAMPLE).subquery())
    counts = db.execute(
        select(recent.c.id, func.count(ReviewVote.id))
        .outerjoin(ReviewVote, (ReviewVote.review_id == recent.c.id)
                   & (ReviewVote.created_at <= recent.c.published_at + EARLY))
        .group_by(recent.c.id)).all()
    if not counts:
        return None
    return float(statistics.median(n for _, n in counts))


def _place(city: str | None, region: str | None, country: str | None) -> str:
    if city and region:
        return f"{city}, {region}"
    return city or region or (country or "Unknown place")


def places(db: Session, review_id: uuid.UUID) -> tuple[list[tuple[str, int]], int, int]:
    """First-time votes by place (Overlay/Review/Investigate/Votes "Where votes
    came from"), from `review_first_vote_geo_buckets`: hourly counts per place
    with no voter and no address (migration 0041). Returns the top PLACES, the
    number of other places and their votes. A place is what the edge reported;
    votes cast before 0041 or without geography have none and are not counted."""
    from app.models.traffic import ReviewFirstVoteGeoBucket as G
    rows = db.execute(
        select(G.city, G.region, G.country, func.sum(G.first_vote_count))
        .where(G.review_id == review_id)
        .group_by(G.city, G.region, G.country)
        .order_by(func.sum(G.first_vote_count).desc())).all()
    named = [(_place(city, region, country), int(n)) for city, region, country, n in rows if n]
    top, rest = named[:PLACES], named[PLACES:]
    return top, len(rest), sum(n for _, n in rest)


def build(db: Session, review: Review, *, now: datetime | None = None) -> Investigation:
    now = now or datetime.now(UTC)
    published = _aware(review.published_at or review.created_at)
    rows = db.execute(
        select(ReviewVote, User).outerjoin(User, User.id == ReviewVote.voter_id)
        .where(ReviewVote.review_id == review.id)
        .order_by(ReviewVote.created_at)).all()

    # Shared networks among this review's voters (keyed hashes; never shown).
    by_network: dict[str, list[uuid.UUID]] = {}
    for voter_id, network in db.execute(
            select(VoteNetworkFingerprint.voter_id, VoteNetworkFingerprint.network)
            .where(VoteNetworkFingerprint.review_id == review.id)).all():
        by_network.setdefault(network, []).append(voter_id)
    shares_with: dict[uuid.UUID, list[uuid.UUID]] = {}
    for voters in by_network.values():
        if len(voters) > 1:
            for v in voters:
                shares_with[v] = [o for o in voters if o != v]

    # The author's published reviews: the last HISTORY for the strip, all for the circle.
    author_reviews = db.execute(
        select(Review.id, Review.published_at)
        .where(Review.author_id == review.author_id, Review.published_at.is_not(None),
               Review.is_removed.is_(False))
        .order_by(Review.published_at.desc())).all() if review.author_id else []
    all_ids = [rid for rid, _ in author_reviews]
    published_of = {rid: _aware(p) for rid, p in author_reviews}
    recent_ids = list(reversed(all_ids[:HISTORY]))
    voter_ids = [v.voter_id for v, _ in rows]
    cast: dict[uuid.UUID, dict[uuid.UUID, tuple[VoteDirection, datetime]]] = {}
    if voter_ids and all_ids:
        for voter_id, rid, direction, at in db.execute(
                select(ReviewVote.voter_id, ReviewVote.review_id, ReviewVote.vote,
                       ReviewVote.created_at)
                .where(ReviewVote.voter_id.in_(voter_ids), ReviewVote.review_id.in_(all_ids))):
            cast.setdefault(voter_id, {})[rid] = (direction, _aware(at))

    users = {v.voter_id: u for v, u in rows}
    out: list[VoterRow] = []
    flagged_ids: set[uuid.UUID] = set()
    for vote, user in rows:
        mine = cast.get(vote.voter_id, {})
        ups = sum(1 for d, _ in mine.values() if d == VoteDirection.up)
        signals: list[Signal] = []
        for other in shares_with.get(vote.voter_id, [])[:2]:
            signals.append(Signal("same_network", f"Same network · {_name(users.get(other))}"))
        circle = len(all_ids) >= CIRCLE_MIN_REVIEWS and ups >= CIRCLE_SHARE * len(all_ids)
        if circle:
            signals.append(Signal("voting_circle", f"Up-voted {ups} of {len(all_ids)} reviews"))
        at = _aware(vote.created_at)
        if user is not None:
            age = (at - _aware(user.created_at)).days
            if age < NEW_ACCOUNT_DAYS:
                signals.append(Signal("new_account", f"{age}-day-old account"))
        delays = [t - published_of[rid] for rid, (_, t) in mine.items() if rid in published_of]
        if len(delays) >= 3 and all(d <= QUICK for d in delays):
            signals.append(Signal("always_quick", "Always within 5 min"))
        flagged = vote.voter_id in shares_with or circle
        if flagged:
            flagged_ids.add(vote.voter_id)
        history = [None if rid not in mine else
                   ("up" if mine[rid][0] == VoteDirection.up else "down") for rid in recent_ids]
        out.append(VoterRow(
            voter_id=vote.voter_id, name=_name(user),
            username=user.username if user else None,
            stage=int(user.trust_stage) if user else 0,
            level_name=TRUST_LEVEL_NAMES[int(user.trust_stage)] if user else None,
            vote="up" if vote.vote == VoteDirection.up else "down",
            seconds_after=max(0, int((at - published).total_seconds())),
            flagged=flagged, signals=signals, history=history,
            agreement=sum(1 for h in history if h == "up"),
            weight=float(vote.vote_weight) if vote.vote_weight is not None else None))

    def counted(include) -> list[tuple]:
        return [(v.vote, v.vote_weight, v.trust_stage_snapshot) for v, u in rows
                if v.vote_weight is not None and not (u is not None and u.is_suspended)
                and include(v)]

    up = sum(1 for v, _ in rows if v.vote == VoteDirection.up)
    return Investigation(
        review_id=review.id, published_at=published, votes_total=len(rows), up=up,
        down=len(rows) - up,
        first_10_min=sum(1 for v, _ in rows if _aware(v.created_at) - published <= EARLY),
        typical_first_10_min=_typical_first_10(db, review),
        flagged=len(flagged_ids),
        flagged_stage2_plus=sum(1 for r in out if r.flagged and r.stage >= 2),
        gate_all=_gate_from_rows(counted(lambda v: True)),
        gate_without_flagged=_gate_from_rows(counted(lambda v: v.voter_id not in flagged_ids)),
        # Flagged first, then by when they voted: what the Voters tab lists.
        voters=sorted(out, key=lambda r: (not r.flagged, r.seconds_after)),
        history_size=len(recent_ids),
        **dict(zip(("places", "places_other", "places_other_count"), places(db, review.id),
                   strict=True)))


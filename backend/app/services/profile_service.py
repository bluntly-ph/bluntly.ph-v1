"""What a public profile shows (Business Rules §17).

    "Public on every profile: trust stage, reputation score, reviews written,
    people helped, comments, and who a person interacts with most - both
    directions, who they vote on most and who votes on them most, including
    upvotes, downvotes, and comments, but never who has reported them
    (reporter identity always stays private, to prevent retaliation) ...
    Individual earnings are not shown publicly on profiles."

Votes carry real money on this platform, so voting relationships are a
disclosed condition of participating — and a crowd-legible way to spot
collusion. Reports are never read here, and nothing touches money.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.comment import ReviewComment
from app.models.enums import VoteDirection
from app.models.review import Review
from app.models.user import User
from app.models.vote import ReviewVote

TOP_N = 5


@dataclass(frozen=True)
class Interaction:
    user_id: uuid.UUID
    username: str | None
    display_name: str | None
    avatar_url: str | None
    upvotes: int
    downvotes: int
    comments: int

    @property
    def total(self) -> int:
        return self.upvotes + self.downvotes + self.comments


def _visible_reviews():
    return (Review.is_removed.is_(False), Review.published_at.isnot(None))


def people_helped(db: Session, user_id: uuid.UUID) -> int:
    """Helpful votes the person's visible reviews received."""
    return int(db.scalar(select(func.coalesce(func.sum(Review.helpful_votes), 0)).where(
        Review.author_id == user_id, *_visible_reviews())) or 0)


def comment_count(db: Session, user_id: uuid.UUID) -> int:
    return int(db.scalar(select(func.count(ReviewComment.id)).where(
        ReviewComment.author_id == user_id, ReviewComment.is_removed.is_(False))) or 0)


def _merge(db: Session, votes, comments) -> list[Interaction]:
    counts: dict[uuid.UUID, list[int]] = {}
    for other, direction, n in votes:
        slot = counts.setdefault(other, [0, 0, 0])
        slot[0 if direction == VoteDirection.up else 1] += int(n)
    for other, n in comments:
        counts.setdefault(other, [0, 0, 0])[2] += int(n)
    if not counts:
        return []
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(list(counts))))}
    rows = [Interaction(uid, users[uid].username, users[uid].display_name,
                        users[uid].avatar_url, *c)
            for uid, c in counts.items() if uid in users]
    rows.sort(key=lambda i: (-i.total, i.username or ""))
    return rows[:TOP_N]


def interacts_with_most(db: Session, user_id: uuid.UUID) -> list[Interaction]:
    """Whose reviews this person votes on and comments on most."""
    votes = db.execute(
        select(Review.author_id, ReviewVote.vote, func.count(ReviewVote.id))
        .join(Review, Review.id == ReviewVote.review_id)
        .where(ReviewVote.voter_id == user_id, Review.author_id.isnot(None),
               Review.author_id != user_id, *_visible_reviews())
        .group_by(Review.author_id, ReviewVote.vote)).all()
    comments = db.execute(
        select(Review.author_id, func.count(ReviewComment.id))
        .join(Review, Review.id == ReviewComment.review_id)
        .where(ReviewComment.author_id == user_id, ReviewComment.is_removed.is_(False),
               Review.author_id.isnot(None), Review.author_id != user_id,
               *_visible_reviews())
        .group_by(Review.author_id)).all()
    return _merge(db, votes, comments)


def most_interacted_by(db: Session, user_id: uuid.UUID) -> list[Interaction]:
    """Who votes on and comments on this person's reviews most."""
    own = aliased(Review)
    votes = db.execute(
        select(ReviewVote.voter_id, ReviewVote.vote, func.count(ReviewVote.id))
        .join(own, own.id == ReviewVote.review_id)
        .where(own.author_id == user_id, ReviewVote.voter_id != user_id,
               own.is_removed.is_(False), own.published_at.isnot(None))
        .group_by(ReviewVote.voter_id, ReviewVote.vote)).all()
    comments = db.execute(
        select(ReviewComment.author_id, func.count(ReviewComment.id))
        .join(own, own.id == ReviewComment.review_id)
        .where(own.author_id == user_id, ReviewComment.author_id.isnot(None),
               ReviewComment.author_id != user_id, ReviewComment.is_removed.is_(False),
               own.is_removed.is_(False), own.published_at.isnot(None))
        .group_by(ReviewComment.author_id)).all()
    return _merge(db, votes, comments)


@dataclass(frozen=True)
class PersonHit:
    id: uuid.UUID
    username: str
    display_name: str | None
    avatar_url: str | None
    trust_stage: int
    trust_level_name: str | None
    review_count: int
    is_claimed_seller: bool


def _like_escape(text: str) -> str:
    """A LIKE pattern takes `%` and `_` as wildcards; usernames carry `_`."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_people(db: Session, query: str, limit: int = 20) -> list[PersonHit]:
    """People search (owner, 2026-09-28): find a member to open their profile.

    Matches the @handle or the display name from the start of a word, and
    anywhere in the handle from three characters. Closest first: the exact
    handle, then handles that start with the query, then names that do, then
    the rest; ties go to whoever has published more reviews. Suspended
    accounts are not listed. Public fields only — never an email.
    """
    needle = query.strip().lstrip("@").strip().lower()
    if not needle:
        return []
    esc = _like_escape(needle)
    starts = f"{esc}%"
    word = f"% {esc}%"
    conditions = [func.lower(User.username).like(starts, escape="\\"),
                  func.lower(User.display_name).like(starts, escape="\\"),
                  func.lower(User.display_name).like(word, escape="\\")]
    if len(needle) >= 3:
        conditions.append(func.lower(User.username).like(f"%{esc}%", escape="\\"))
    published = (select(Review.author_id, func.count(Review.id).label("n"))
                 .where(Review.published_at.is_not(None), Review.is_removed.is_(False))
                 .group_by(Review.author_id).subquery())
    rows = db.execute(
        select(User, func.coalesce(published.c.n, 0))
        .outerjoin(published, published.c.author_id == User.id)
        .where(User.username.is_not(None), User.is_suspended.is_(False),
               or_(*conditions))
        .limit(200)
    ).all()

    def rank(user: User) -> int:
        handle = (user.username or "").lower()
        name = (user.display_name or "").lower()
        if handle == needle:
            return 0
        if handle.startswith(needle):
            return 1
        if name.startswith(needle):
            return 2
        if f" {needle}" in f" {name}":
            return 3
        return 4

    rows.sort(key=lambda r: (rank(r[0]), -int(r[1]), (r[0].username or "").lower()))
    return [PersonHit(id=u.id, username=u.username, display_name=u.display_name,
                      avatar_url=u.avatar_url, trust_stage=u.trust_stage or 0,
                      trust_level_name=u.trust_level_name, review_count=int(n),
                      is_claimed_seller=bool(u.is_claimed_seller))
            for u, n in rows[:limit]]

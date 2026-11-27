"""The Author tab of an investigation (Figma Overlay/Review/Investigate/Author
8112:17871, Overlay/Answer/Investigate/Author 8129:19219): who wrote it and how
their helpful votes have come in, over everything they have published of that
kind (reviews or answers).

Read from records only:

* where their helpful votes come from: up-votes on all their published
  reviews (or answers), the three biggest voters' shares and everyone else;
* how many they published per month (Manila), the last 12 months;
* the helpful score of their last 12, oldest first, against the gate (reviews:
  the earnings gate; answers have no gate and are only ranked by it);
* reports filed against them or their content, with how each was decided;
* the voting circle: people who up-voted at least CIRCLE_SHARE of them (over
  at least CIRCLE_MIN of them), with how many of that person's own reviews the
  author up-voted back.

Nothing here is a finding; it is what the moderator reads before deciding.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.models.enums import ModerationAction, ModerationTargetType, VoteDirection
from app.models.moderation import ModerationLog
from app.models.qa import Answer, QAVote
from app.models.review import Review
from app.models.user import TRUST_LEVEL_NAMES, User
from app.models.vote import ReviewVote
from app.services.ranking import GATE_WILSON_LB

CIRCLE_SHARE = 0.8
CIRCLE_MIN = 5
SCORES = 12
MONTHS = 12
TOP_SOURCES = 3


@dataclass
class Person:
    id: uuid.UUID
    name: str
    username: str | None
    stage: int
    level_name: str | None


@dataclass
class Source:
    person: Person
    votes: int
    share: float


@dataclass
class Score:
    id: uuid.UUID
    score: float | None
    current: bool


@dataclass
class AuthorReport:
    at: datetime
    reason: str | None
    status: str  # open | upheld | dismissed | restored | escalated


@dataclass
class CircleMember:
    person: Person
    covered: int     # of the author's items this person up-voted
    back: int        # this person's reviews the author up-voted


@dataclass
class AuthorInvestigation:
    kind: str                       # reviews | answers
    person: Person
    trust_score: float
    joined: datetime
    reviews: int
    answers: int
    earned: Decimal | None
    items: int
    helpful_votes: int
    sources: list[Source]
    others_people: int
    others_share: float
    top_share: float
    per_month: list[tuple[str, int]]
    scores: list[Score]
    gate: float | None
    passing: int
    reports: list[AuthorReport] = field(default_factory=list)
    circle: list[CircleMember] = field(default_factory=list)


def _person(u: User) -> Person:
    return Person(id=u.id, name=u.display_name or (f"@{u.username}" if u.username else "Member"),
                  username=u.username, stage=int(u.trust_stage or 0),
                  level_name=TRUST_LEVEL_NAMES[int(u.trust_stage or 0)])


def _months(now: datetime) -> list[str]:
    local = now.astimezone(MANILA)
    y, m = local.year, local.month
    keys = []
    for _ in range(MONTHS):
        keys.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return list(reversed(keys))


def _status(log: ModerationLog) -> str:
    from app.services.person_investigation_service import _report_status
    return _report_status(log)


def build(db: Session, author: User, *, kind: str, current_id: uuid.UUID,
          now: datetime | None = None) -> AuthorInvestigation:
    now = now or datetime.now(MANILA)
    reviews_q = (select(Review.id, Review.published_at, Review.wilson_score)
                 .where(Review.author_id == author.id, Review.published_at.is_not(None),
                        Review.is_removed.is_(False))
                 .order_by(Review.published_at))
    reviews = db.execute(reviews_q).all()
    answers = db.execute(select(Answer.id, Answer.created_at, Answer.wilson_score)
                         .where(Answer.responder_id == author.id)
                         .order_by(Answer.created_at)).all()
    items = reviews if kind == "reviews" else answers
    ids = [i for i, _, _ in items]

    # Up-votes on the author's items, by voter.
    votes: list = []
    if ids and kind == "reviews":
        votes = db.execute(select(ReviewVote.voter_id, ReviewVote.review_id).where(
            ReviewVote.review_id.in_(ids), ReviewVote.vote == VoteDirection.up)).all()
    elif ids:
        votes = db.execute(select(QAVote.user_id, QAVote.answer_id).where(
            QAVote.answer_id.in_(ids), QAVote.direction == VoteDirection.up)).all()
    by_voter: dict[uuid.UUID, set[uuid.UUID]] = {}
    for voter, item in votes:
        by_voter.setdefault(voter, set()).add(item)
    total = len(votes)
    ranked = sorted(by_voter.items(), key=lambda kv: -len(kv[1]))
    people = {u.id: u for u in db.scalars(select(User).where(
        User.id.in_([v for v, _ in ranked[:TOP_SOURCES]] + [
            v for v, s in by_voter.items()
            if len(ids) >= CIRCLE_MIN and len(s) >= CIRCLE_SHARE * len(ids)])))} if ranked else {}
    sources = [Source(person=_person(people[v]), votes=len(s), share=round(len(s) / total, 4))
               for v, s in ranked[:TOP_SOURCES] if v in people] if total else []
    top = sum(s.votes for s in sources)

    # Per month, last 12 (Manila).
    counts: dict[str, int] = {}
    for _, at, _ in items:
        if at is None:
            continue
        key = at.astimezone(MANILA).strftime("%Y-%m")
        counts[key] = counts.get(key, 0) + 1
    per_month = [(k, counts.get(k, 0)) for k in _months(now)]

    # Helpful score of the last 12, oldest first.
    last = items[-SCORES:]
    scores = [Score(id=i, score=float(w) if w is not None else None, current=i == current_id)
              for i, _, w in last]
    gate = GATE_WILSON_LB if kind == "reviews" else None
    passing = sum(1 for _, _, w in items if w is not None and gate is not None and float(w) >= gate)

    # Reports against the author or their content.
    targets = [r for r, _, _ in reviews] + [a for a, _, _ in answers]
    reports = db.scalars(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.report,
        or_((ModerationLog.target_type == ModerationTargetType.user)
            & (ModerationLog.target_ref == author.id),
            ModerationLog.target_ref.in_(targets) if targets else false()))
        .order_by(ModerationLog.created_at.desc()).limit(20)).all()

    # The voting circle, and how many of each member's reviews the author up-voted back.
    circle_ids = [v for v, s in by_voter.items()
                  if len(ids) >= CIRCLE_MIN and len(s) >= CIRCLE_SHARE * len(ids)]
    back: dict[uuid.UUID, int] = {}
    if circle_ids:
        for owner, n in db.execute(
                select(Review.author_id, func.count(ReviewVote.id))
                .join(ReviewVote, ReviewVote.review_id == Review.id)
                .where(Review.author_id.in_(circle_ids), ReviewVote.voter_id == author.id,
                       ReviewVote.vote == VoteDirection.up)
                .group_by(Review.author_id)).all():
            back[owner] = int(n)
    circle = sorted((CircleMember(person=_person(people[v]), covered=len(by_voter[v]),
                                  back=back.get(v, 0))
                     for v in circle_ids if v in people), key=lambda c: -c.covered)

    earned = None
    try:
        from app.services.reporting import earnings_statement, periods
        earned = earnings_statement.build(db, author, periods.resolve()).summary.lifetime_earned
    except Exception:  # noqa: BLE001 - the tab stands without its money figure
        db.rollback()

    return AuthorInvestigation(
        kind=kind, person=_person(author), trust_score=float(author.reputation_score or 0),
        joined=author.created_at, reviews=len(reviews), answers=len(answers), earned=earned,
        items=len(ids), helpful_votes=total, sources=sources,
        others_people=max(0, len(by_voter) - len(sources)),
        others_share=round((total - top) / total, 4) if total else 0.0,
        top_share=round(top / total, 4) if total else 0.0,
        per_month=per_month, scores=scores, gate=gate, passing=passing,
        reports=[AuthorReport(at=r.created_at, reason=r.reason.value if r.reason else None,
                              status=_status(r)) for r in reports],
        circle=circle[:10])

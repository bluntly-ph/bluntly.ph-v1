"""What a moderator sees when they investigate one answer (Figma
Overlay/Answer/Investigate: Summary 8129:18013, Votes 8129:18282 and
8237:26795, Voters 8129:18588, Originality 8129:19014, Author 8129:19219).
Read-only, like the review investigation it mirrors (review_investigation.py).

Answer votes (qa_votes) carry no weight, no stage snapshot, no network
fingerprint and no place, so:

* a vote is FLAGGED here only for the voting circle: its voter up-voted at
  least CIRCLE_SHARE of the responder's answers, over at least CIRCLE_MIN of
  them. No "same network" flag exists for answers;
* the helpful score is the answer's own (`qa_engagement`: the Wilson lower
  bound of up over up + down), recomputed without the flagged voters;
* there is no gate and no reward for answers: the score only orders them;
* "Where votes came from" is not recorded for answers.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import VoteDirection
from app.models.product import Product
from app.models.qa import Answer, QAVote, Question
from app.models.seller import Seller
from app.models.user import TRUST_LEVEL_NAMES, User
from app.services.ranking import wilson_lower_bound
from app.services.review_investigation import Signal, VoterRow

HISTORY = 20
CIRCLE_SHARE = 0.8
CIRCLE_MIN = 5
EARLY = timedelta(minutes=10)
QUICK = timedelta(minutes=5)
NEW_ACCOUNT_DAYS = 30
TYPICAL_SAMPLE = 400


@dataclass
class AnswerInvestigation:
    answer_id: uuid.UUID
    question_id: uuid.UUID
    question: str
    asker: str | None
    about: str | None
    body: str
    posted_at: datetime
    responder_id: uuid.UUID | None
    responder: str
    responder_stage: int
    responder_level: str | None
    is_best: bool
    picked_by_asker: bool
    is_seller_answer: bool
    votes_total: int
    up: int
    down: int
    first_10_min: int
    typical_first_10_min: float | None
    flagged: int
    score_all: float
    score_without_flagged: float
    voters: list[VoterRow] = field(default_factory=list)
    history_size: int = 0


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _name(u: User | None) -> str:
    if u is None:
        return "Former member"
    return u.display_name or (f"@{u.username}" if u.username else "Member")


def _typical_first_10(db: Session, answer: Answer) -> float | None:
    """Median votes in the first 10 minutes across recent answers (this one excluded)."""
    recent = (select(Answer.id, Answer.created_at).where(Answer.id != answer.id)
              .order_by(Answer.created_at.desc()).limit(TYPICAL_SAMPLE).subquery())
    counts = db.execute(
        select(recent.c.id, func.count(QAVote.id))
        .outerjoin(QAVote, (QAVote.answer_id == recent.c.id)
                   & (QAVote.created_at <= recent.c.created_at + EARLY))
        .group_by(recent.c.id)).all()
    return float(statistics.median(n for _, n in counts)) if counts else None


def _score(up: int, down: int) -> float:
    return round(wilson_lower_bound(up, up + down), 4) if up + down else 0.0


def build(db: Session, answer: Answer) -> AnswerInvestigation:
    question = db.get(Question, answer.question_id)
    asker = db.get(User, question.asker_id) if question and question.asker_id else None
    about = None
    if question and question.product_id:
        product = db.get(Product, question.product_id)
        about = product.canonical_name if product else None
    elif question and question.seller_id:
        seller = db.get(Seller, question.seller_id)
        about = seller.display_name if seller else None
    responder = db.get(User, answer.responder_id) if answer.responder_id else None
    posted = _aware(answer.created_at)

    rows = db.execute(
        select(QAVote, User).outerjoin(User, User.id == QAVote.user_id)
        .where(QAVote.answer_id == answer.id).order_by(QAVote.created_at)).all()

    theirs = db.execute(select(Answer.id, Answer.created_at)
                        .where(Answer.responder_id == answer.responder_id)
                        .order_by(Answer.created_at.desc())).all() if answer.responder_id else []
    all_ids = [a for a, _ in theirs]
    created_of = {a: _aware(at) for a, at in theirs}
    recent_ids = list(reversed(all_ids[:HISTORY]))
    voter_ids = [v.user_id for v, _ in rows]
    cast: dict[uuid.UUID, dict[uuid.UUID, tuple[VoteDirection, datetime]]] = {}
    if voter_ids and all_ids:
        for voter_id, aid, direction, at in db.execute(
                select(QAVote.user_id, QAVote.answer_id, QAVote.direction, QAVote.created_at)
                .where(QAVote.user_id.in_(voter_ids), QAVote.answer_id.in_(all_ids))):
            cast.setdefault(voter_id, {})[aid] = (direction, _aware(at))

    out: list[VoterRow] = []
    flagged_ids: set[uuid.UUID] = set()
    for vote, user in rows:
        mine = cast.get(vote.user_id, {})
        ups = sum(1 for d, _ in mine.values() if d == VoteDirection.up)
        signals: list[Signal] = []
        circle = len(all_ids) >= CIRCLE_MIN and ups >= CIRCLE_SHARE * len(all_ids)
        if circle:
            signals.append(Signal("voting_circle", f"Up-voted {ups} of {len(all_ids)} answers"))
        at = _aware(vote.created_at)
        if user is not None and (at - _aware(user.created_at)).days < NEW_ACCOUNT_DAYS:
            signals.append(Signal("new_account",
                                  f"{(at - _aware(user.created_at)).days}-day-old account"))
        delays = [t - created_of[aid] for aid, (_, t) in mine.items() if aid in created_of]
        if len(delays) >= 3 and all(d <= QUICK for d in delays):
            signals.append(Signal("always_quick", "Always within 5 min"))
        if circle:
            flagged_ids.add(vote.user_id)
        history = [None if aid not in mine else
                   ("up" if mine[aid][0] == VoteDirection.up else "down") for aid in recent_ids]
        out.append(VoterRow(
            voter_id=vote.user_id, name=_name(user), username=user.username if user else None,
            stage=int(user.trust_stage) if user else 0,
            level_name=TRUST_LEVEL_NAMES[int(user.trust_stage)] if user else None,
            vote="up" if vote.direction == VoteDirection.up else "down",
            seconds_after=max(0, int((at - posted).total_seconds())),
            flagged=circle, signals=signals, history=history,
            agreement=sum(1 for h in history if h == "up")))

    up = sum(1 for v, _ in rows if v.direction == VoteDirection.up)
    down = len(rows) - up
    kept = [v for v, _ in rows if v.user_id not in flagged_ids]
    kept_up = sum(1 for v in kept if v.direction == VoteDirection.up)
    return AnswerInvestigation(
        answer_id=answer.id, question_id=answer.question_id,
        question=question.body if question else "", asker=_name(asker) if asker else None,
        about=about, body=answer.body, posted_at=posted, responder_id=answer.responder_id,
        responder=_name(responder), responder_stage=int(responder.trust_stage) if responder else 0,
        responder_level=TRUST_LEVEL_NAMES[int(responder.trust_stage)] if responder else None,
        is_best=bool(answer.is_best_answer or (question and question.best_answer_id == answer.id)),
        picked_by_asker=bool(question and question.best_answer_id == answer.id
                             and question.best_answer_picked_by_id is not None
                             and question.best_answer_picked_by_id == question.asker_id),
        is_seller_answer=bool(answer.is_seller_answer),
        votes_total=len(rows), up=up, down=down,
        first_10_min=sum(1 for v, _ in rows if _aware(v.created_at) - posted <= EARLY),
        typical_first_10_min=_typical_first_10(db, answer),
        flagged=len(flagged_ids), score_all=_score(up, down),
        score_without_flagged=_score(kept_up, len(kept) - kept_up),
        voters=sorted(out, key=lambda r: (not r.flagged, r.seconds_after)),
        history_size=len(recent_ids))

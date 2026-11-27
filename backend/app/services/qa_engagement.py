"""Votes and replies on the question page (Figma Question Detail v6B 7731:15601;
meeting 2026-10-02: "the question page now works like a thread").

The rules are the seller-review engagement rules (services/seller_review_engagement),
the narrowest that make the controls honest:

* **Votes are helpfulness only.** One per member per target, equal weight,
  changeable and removable. A question takes up-votes; answers and replies take
  up or down. Nobody votes on their own question, answer or reply. They move no
  money and no trust stage; an answer's stored `helpful_votes`,
  `unhelpful_votes` and `wilson_score` (which already order the answers) are
  recomputed from the vote rows on every change, never incremented.
* **Replies are a thread under an answer**, three levels deep as drawn (a reply
  to a third-level reply joins that level). Signed-in members, no links,
  1,000 characters. The answer's author (or the parent reply's) is told.
  The author or staff can remove a reply; removal is soft.
* A suspended member can read but not vote or reply.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.link_policy import find_link
from app.core.security import is_staff
from app.models.enums import VoteDirection
from app.models.qa import Answer, AnswerReply, QAVote, Question
from app.models.user import User
from app.services import notification_service
from app.services.ranking import wilson_lower_bound

MAX_REPLY = 1000
MAX_DEPTH = 3


def _active(user: User) -> None:
    if user.is_suspended:
        raise ForbiddenError("A suspended account can't vote or reply.", code="account_suspended")


def _self_vote(author_id: uuid.UUID | None, user: User, what: str) -> None:
    if author_id is not None and author_id == user.id:
        raise AppError(f"You can't vote on your own {what}.", code="self_vote",
                       status_code=422, title="Invalid vote")


def _set_vote(db: Session, user: User, column, target_id: uuid.UUID,
              direction: VoteDirection | None) -> None:
    existing = db.scalar(select(QAVote).where(column == target_id, QAVote.user_id == user.id)
                         .with_for_update())
    if direction is None:
        if existing is not None:
            db.delete(existing)
    elif existing is None:
        db.add(QAVote(user_id=user.id, direction=direction, **{column.key: target_id}))
    else:
        existing.direction = direction
    db.flush()


def tallies(db: Session, column, ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    """(up, down) per target id, from the vote rows."""
    if not ids:
        return {}
    out: dict[uuid.UUID, list[int]] = {}
    for tid, direction, n in db.execute(
            select(column, QAVote.direction, func.count(QAVote.id))
            .where(column.in_(ids)).group_by(column, QAVote.direction)).all():
        slot = out.setdefault(tid, [0, 0])
        slot[0 if direction == VoteDirection.up else 1] = int(n)
    return {k: (v[0], v[1]) for k, v in out.items()}


def mine(db: Session, user_id: uuid.UUID | None, column,
         ids: list[uuid.UUID]) -> dict[uuid.UUID, VoteDirection]:
    if user_id is None or not ids:
        return {}
    return dict(db.execute(select(column, QAVote.direction)
                           .where(QAVote.user_id == user_id, column.in_(ids))).all())


# --- targets ----------------------------------------------------------------

def _question(db: Session, question_id: uuid.UUID) -> Question:
    q = db.get(Question, question_id)
    if q is None or q.is_removed:
        raise NotFoundError("Question not found.", code="question_not_found")
    return q


def _answer(db: Session, question_id: uuid.UUID, answer_id: uuid.UUID) -> Answer:
    _question(db, question_id)
    a = db.get(Answer, answer_id)
    if a is None or a.question_id != question_id:
        raise NotFoundError("Answer not found.", code="answer_not_found")
    return a


def answer_or_404(db: Session, question_id: uuid.UUID, answer_id: uuid.UUID) -> Answer:
    return _answer(db, question_id, answer_id)


def _reply(db: Session, question_id: uuid.UUID, reply_id: uuid.UUID) -> AnswerReply:
    r = db.get(AnswerReply, reply_id)
    if r is None or r.is_removed:
        raise NotFoundError("Reply not found.", code="reply_not_found")
    _answer(db, question_id, r.answer_id)
    return r


# --- votes ------------------------------------------------------------------

def vote_question(db: Session, question_id: uuid.UUID, user: User, up: bool) -> tuple[int, bool]:
    """Up-vote a question, or take it back. Returns (up-votes, mine)."""
    _active(user)
    q = _question(db, question_id)
    _self_vote(q.asker_id, user, "question")
    _set_vote(db, user, QAVote.question_id, q.id, VoteDirection.up if up else None)
    db.commit()
    return tallies(db, QAVote.question_id, [q.id]).get(q.id, (0, 0))[0], up


def vote_answer(db: Session, question_id: uuid.UUID, answer_id: uuid.UUID, user: User,
                direction: VoteDirection | None) -> tuple[int, int, VoteDirection | None]:
    _active(user)
    a = _answer(db, question_id, answer_id)
    _self_vote(a.responder_id, user, "answer")
    _set_vote(db, user, QAVote.answer_id, a.id, direction)
    up, down = tallies(db, QAVote.answer_id, [a.id]).get(a.id, (0, 0))
    # The stored figures the answer order already reads, from the rows.
    a.helpful_votes, a.unhelpful_votes = up, down
    a.wilson_score = Decimal(str(round(wilson_lower_bound(up, up + down), 5)))
    db.commit()
    return up, down, direction


def vote_reply(db: Session, question_id: uuid.UUID, reply_id: uuid.UUID, user: User,
               direction: VoteDirection | None) -> tuple[int, int, VoteDirection | None]:
    _active(user)
    r = _reply(db, question_id, reply_id)
    _self_vote(r.author_id, user, "reply")
    _set_vote(db, user, QAVote.reply_id, r.id, direction)
    db.commit()
    up, down = tallies(db, QAVote.reply_id, [r.id]).get(r.id, (0, 0))
    return up, down, direction


# --- replies ----------------------------------------------------------------

@dataclass
class ReplyRow:
    id: uuid.UUID
    answer_id: uuid.UUID
    parent_id: uuid.UUID | None
    depth: int
    body: str
    created_at: datetime
    author: User | None
    up: int = 0
    down: int = 0
    my_vote: VoteDirection | None = None
    children: list = field(default_factory=list)


def add_reply(db: Session, question_id: uuid.UUID, answer_id: uuid.UUID, user: User,
              body: str, parent_id: uuid.UUID | None = None) -> AnswerReply:
    _active(user)
    answer = _answer(db, question_id, answer_id)
    text = (body or "").strip()
    if not text or len(text) > MAX_REPLY:
        raise AppError(f"A reply is 1 to {MAX_REPLY} characters.", code="reply_invalid",
                       status_code=422, title="Invalid reply")
    if find_link(text) is not None:
        raise AppError("Replies can't contain links.", code="reply_link",
                       status_code=422, title="Invalid reply")
    parent = None
    if parent_id is not None:
        parent = db.get(AnswerReply, parent_id)
        if parent is None or parent.answer_id != answer.id or parent.is_removed:
            raise NotFoundError("Reply not found.", code="reply_not_found")
        # The frame draws three levels; deeper replies join the third.
        while parent.depth >= MAX_DEPTH and parent.parent_id is not None:
            parent = db.get(AnswerReply, parent.parent_id)
    reply = AnswerReply(answer_id=answer.id, parent_id=parent.id if parent else None,
                        author_id=user.id, depth=(parent.depth + 1) if parent else 1, body=text)
    db.add(reply)
    told = parent.author_id if parent else answer.responder_id
    if told is not None and told != user.id:
        notification_service.notify(
            db, told, "answer_reply", "New reply in a question thread",
            body=text, link=f"/questions/{question_id}#answer-{answer.id}")
    db.commit()
    db.refresh(reply)
    return reply


def remove_reply(db: Session, question_id: uuid.UUID, reply_id: uuid.UUID, user: User) -> None:
    r = _reply(db, question_id, reply_id)
    if r.author_id != user.id and not is_staff(user):
        raise ForbiddenError("Only the reply's author or staff can remove it.",
                             code="not_reply_author")
    r.is_removed = True
    db.commit()


def threads(db: Session, answer_ids: list[uuid.UUID],
            viewer_id: uuid.UUID | None) -> dict[uuid.UUID, list[ReplyRow]]:
    """Each answer's visible replies, oldest first, as flat rows with parents.
    A removed reply's visible children stay, attached to its own parent."""
    if not answer_ids:
        return {}
    rows = db.execute(
        select(AnswerReply, User).outerjoin(User, User.id == AnswerReply.author_id)
        .where(AnswerReply.answer_id.in_(answer_ids))
        .order_by(AnswerReply.created_at.asc())).all()
    removed_parent = {r.id: r.parent_id for r, _ in rows if r.is_removed}
    ids = [r.id for r, _ in rows if not r.is_removed]
    counts = tallies(db, QAVote.reply_id, ids)
    my = mine(db, viewer_id, QAVote.reply_id, ids)
    out: dict[uuid.UUID, list[ReplyRow]] = {}
    for r, author in rows:
        if r.is_removed:
            continue
        parent = r.parent_id
        while parent in removed_parent:
            parent = removed_parent[parent]
        up, down = counts.get(r.id, (0, 0))
        out.setdefault(r.answer_id, []).append(ReplyRow(
            id=r.id, answer_id=r.answer_id, parent_id=parent, depth=r.depth, body=r.body,
            created_at=r.created_at, author=author, up=up, down=down, my_vote=my.get(r.id)))
    return out

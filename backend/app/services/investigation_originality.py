"""The Originality tab of an investigation (Figma Overlay/Review/Investigate/
Originality 8112:17611, Overlay/Answer/Investigate/Originality 8129:19014).

TEXT. The same comparison the duplicate-text detector files reports with
(`text_similarity.compare` over the same bounded candidate set,
`duplicate_text`), but shown whether or not it crosses the flag line: the
closest earlier Bluntly text, how much of it matches and why. Only EARLIER
items can be a source, so an original author is never named the copier.
Marketplace Q&A and the web are not searched; the frame's columns for them
are not drawn.

PHOTOS. Bluntly does not compare photos (no image fingerprint is stored), so
nothing here says a photo was or was not used before.

PROOF OF PURCHASE (reviews). Whether a receipt was submitted. Viewing it goes
through GET /reviews/{id}/receipt, which audits the view; the receipt checks in
the frame (product matches, bought before posting, no editing traces) are not
run by anything and are not shown.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.qa import Answer, Question
from app.models.review import Review
from app.services import text_similarity
from app.services.duplicate_text import COMPARED, NEIGHBOURHOOD, _review_candidates_sql


@dataclass
class TextMatch:
    kind: str                # review | answer
    id: uuid.UUID
    label: str
    href: str | None
    score: float             # 0..1: the larger of near-identical and passage share
    near_identical: float
    passage_share: float
    shared_phrases: int
    flagged: bool
    reason: str


@dataclass
class Originality:
    kind: str                # review | answer
    meaningful: bool         # long enough to compare at all
    compared: int            # earlier texts compared in full
    best: TextMatch | None
    has_photo: bool
    has_receipt: bool


def _best(target: str, candidates: list[tuple[str, uuid.UUID, str, str, str | None]]
          ) -> tuple[TextMatch | None, int]:
    best: TextMatch | None = None
    for kind, cid, body, label, href in candidates:
        c = text_similarity.compare(target, body)
        if best is None or c.score > best.score:
            best = TextMatch(kind=kind, id=cid, label=label, href=href, score=round(c.score, 4),
                             near_identical=round(c.near_identical, 4),
                             passage_share=round(c.passage_share, 4),
                             shared_phrases=c.shared_phrases, flagged=c.flagged,
                             reason=c.reason)
    return best, len(candidates)


def for_review(db: Session, review: Review) -> Originality:
    meaningful = text_similarity.is_meaningful(text_similarity.normalize(review.discussion))
    best, compared = None, 0
    if meaningful:
        rows = db.execute(_review_candidates_sql(False),
                          {"ids": [review.id], "neighbourhood": NEIGHBOURHOOD,
                           "compared": COMPARED}).all()
        titles = dict(db.execute(select(Review.id, Review.title).where(
            Review.id.in_([cid for _, cid, _ in rows]))).all()) if rows else {}
        best, compared = _best(review.discussion, [
            ("review", cid, body, titles.get(cid) or "An earlier review", f"/reviews/{cid}")
            for _, cid, body in rows])
    return Originality(kind="review", meaningful=meaningful, compared=compared, best=best,
                       has_photo=bool(review.photo_url), has_receipt=bool(review.receipt_key))


def for_answer(db: Session, answer: Answer) -> Originality:
    meaningful = text_similarity.is_meaningful(text_similarity.normalize(answer.body))
    best, compared = None, 0
    if meaningful:
        near = [Answer.question_id == answer.question_id]
        if answer.responder_id is not None:
            near.append(Answer.responder_id == answer.responder_id)
        rows = db.execute(
            select(Answer.id, Answer.body, Answer.question_id, Question.body)
            .join(Question, Question.id == Answer.question_id)
            .where(Answer.id != answer.id, Answer.created_at < answer.created_at, or_(*near))
            .order_by(Answer.created_at.desc()).limit(NEIGHBOURHOOD)).all()
        best, compared = _best(answer.body, [
            ("answer", aid, body, f"An answer to “{q[:80]}”", f"/questions/{qid}")
            for aid, body, qid, q in rows])
    return Originality(kind="answer", meaningful=meaningful, compared=compared, best=best,
                       has_photo=False, has_receipt=False)

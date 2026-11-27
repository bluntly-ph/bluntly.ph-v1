"""Suspicious duplicate text: finding and filing it (QA, 2026-09-29).

The one duplicate-text detector. It serves three callers:

* **at submission**, for a review, a dated thread update, an answer and a
  comment (`check_new_*`), best effort AFTER the content is committed: a
  failed check is logged and never blocks, delays or changes publication;
* the daily **integrity sweep**, for reviews submitted or voted on in its
  window (`fraud_service.compute_signals_by_review`), which also catches any
  submission-time check that failed;
* the Review Queue's `duplicate_content` signal (same function).

Finding: a bounded candidate set from the database, then the pure comparison in
`text_similarity` on normalised text.

* Reviews: the 200 most recent reviews of the same product and the 200 most
  recent by the same author. For reviews written in the last two days, the
  daily sweep also searches every product and author: up to 200 reviews whose
  text `pg_trgm` finds similar anywhere (the `%` operator over the existing
  GIN index `ix_reviews_discussion_trgm`, floor 0.3). That search costs about
  120 ms a review at 50,000 reviews, so a submission and the Review Queue read
  do not run it (`integrity_sweep.PLATFORM_WIDE_*`). The best eight by
  trigram similarity are compared in full. Every branch is capped, so a wave
  of near-identical spam cannot make one check scan the table.
* Answers: the same question and the same responder. Comments: the same
  review and the same author. Neither table has a trigram index, so neither is
  searched platform-wide.

Only an EARLIER item can be the source: the later text is the one flagged, so
an honest original author is never named a copier. A dated update is never
compared with the earlier entries of its own thread (§4): restating yourself
is not copying.

A match files one SYSTEM_DETECTED `duplicate_content` report on the later item
(never twice while one is open), with the evidence below. It removes nothing,
bans nobody, touches no money and is shown to no one but staff.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import bindparam, or_, select, text
from sqlalchemy.orm import Session

from app.models.comment import ReviewComment
from app.models.enums import ModerationReason, ModerationTargetType
from app.models.qa import Answer
from app.models.review import Review
from app.services import text_similarity
from app.services.text_similarity import ALGORITHM_VERSION, TextComparison, compare

log = logging.getLogger(__name__)

#: `pg_trgm` similarity a review must reach to be fetched platform-wide.
#: Deliberately loose: it only chooses what the real comparison looks at.
CANDIDATE_FLOOR = 0.3
#: Most recent same-product / same-author reviews considered.
NEIGHBOURHOOD = 200
#: Candidates compared in full per item.
COMPARED = 8
SEVERITY = 0.8


@dataclass(frozen=True)
class DuplicateFinding:
    matched_id: uuid.UUID
    matched_kind: str                       # "review" | "answer" | "comment"
    comparison: TextComparison
    others: tuple[tuple[uuid.UUID, float], ...] = ()

    def evidence(self, detected_at: datetime) -> dict:
        """What is stored on the report: ids and scores, never a name or text."""
        c = self.comparison
        return {
            "duplicate_of": str(self.matched_id),
            "matched_kind": self.matched_kind,
            "similarity": round(c.score, 3),
            "near_identical": c.near_identical,
            "passage_share": c.passage_share,
            "shared_phrases": c.shared_phrases,
            "reason": c.reason,
            "other_matches": [{"id": str(i), "similarity": round(s, 3)} for i, s in self.others],
            "algorithm": ALGORITHM_VERSION,
            "thresholds": {
                "near_identical": text_similarity.near_identical_threshold(),
                "passage_share": text_similarity.PASSAGE_SHARE,
                "min_shared_phrases": text_similarity.MIN_SHARED_PHRASES,
                "min_tokens": text_similarity.MIN_TOKENS,
            },
            "detected_at": detected_at.isoformat(),
        }


def _best(target_text: str, candidates: list[tuple[uuid.UUID, str]], kind: str
          ) -> DuplicateFinding | None:
    if not text_similarity.is_meaningful(text_similarity.normalize(target_text)):
        return None
    flagged = []
    for cid, body in candidates:
        comparison = compare(target_text, body)
        if comparison.flagged:
            flagged.append((comparison.score, cid, comparison))
    if not flagged:
        return None
    # The closest source first: a text containing an older one in full scores a
    # passage share of 1.0 against it too, so ties break on how near-identical
    # the two are, then on how much they share; the id only settles exact ties.
    flagged.sort(key=lambda row: (-row[0], -row[2].near_identical,
                                  -row[2].shared_phrases, str(row[1])))
    _, cid, comparison = flagged[0]
    others = tuple((other, score) for score, other, _ in flagged[1:3])
    return DuplicateFinding(cid, kind, comparison, others)


_PLATFORM_WIDE = """
                UNION
                (SELECT n.id FROM reviews AS n WHERE n.discussion % target.discussion
                 LIMIT :neighbourhood)"""


def _review_candidates_sql(platform_wide: bool):
    wide = _PLATFORM_WIDE if platform_wide else ""
    return text(
        f"""
    SELECT target.id AS target_id, c.id AS candidate_id, c.discussion AS body
    FROM reviews AS target
    JOIN LATERAL (
        SELECT c.id, c.discussion
        FROM reviews AS c
        WHERE c.id IN (
                (SELECT n.id FROM reviews AS n WHERE n.product_id = target.product_id
                 ORDER BY n.created_at DESC LIMIT :neighbourhood)
                UNION
                (SELECT n.id FROM reviews AS n
                 WHERE target.author_id IS NOT NULL AND n.author_id = target.author_id
                 ORDER BY n.created_at DESC LIMIT :neighbourhood){wide}
            )
          AND c.id <> target.id
          -- An update restating its own thread's earlier entry is not a copy.
          AND coalesce(c.thread_id, c.id) <> coalesce(target.thread_id, target.id)
          AND c.is_removed = false
          AND c.created_at < target.created_at
        ORDER BY similarity(c.discussion, target.discussion) DESC, c.id
        LIMIT :compared
    ) AS c ON true
    WHERE target.id IN :ids
    """
    ).bindparams(bindparam("ids", expanding=True))


def review_duplicates(db: Session, reviews: Collection[Review], *,
                      platform_wide: bool = False) -> dict[uuid.UUID, DuplicateFinding]:
    """The best earlier match for each review whose text is a copy, in one query.

    `platform_wide` adds the trigram-index search across every product and
    author. It costs about 120 ms a review at 50,000 reviews, so only the
    daily sweep uses it, for new reviews; a submission and the Review Queue
    search the same product and the same author (about 10 ms a review).
    """
    # Text too short to ever be flagged is never searched for (a submission
    # check costs nothing for "Good product.").
    by_id = {r.id: r for r in reviews
             if text_similarity.is_meaningful(text_similarity.normalize(r.discussion))}
    if not by_id:
        return {}
    if platform_wide:
        # `%` uses pg_trgm.similarity_threshold; set for this transaction only.
        db.execute(text("SELECT set_config('pg_trgm.similarity_threshold', :floor, true)"),
                   {"floor": str(CANDIDATE_FLOOR)})
    candidates: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = {rid: [] for rid in by_id}
    for target_id, candidate_id, body in db.execute(
            _review_candidates_sql(platform_wide),
            {"ids": list(by_id), "neighbourhood": NEIGHBOURHOOD, "compared": COMPARED}):
        candidates[target_id].append((candidate_id, body))
    found = {}
    for rid, review in by_id.items():
        finding = _best(review.discussion, candidates[rid], "review")
        if finding is not None:
            found[rid] = finding
    return found


def answer_duplicate(db: Session, answer: Answer) -> DuplicateFinding | None:
    near = [Answer.question_id == answer.question_id]
    if answer.responder_id is not None:
        near.append(Answer.responder_id == answer.responder_id)
    rows = db.execute(
        select(Answer.id, Answer.body).where(
            Answer.id != answer.id, Answer.created_at < answer.created_at, or_(*near))
        .order_by(Answer.created_at.desc()).limit(NEIGHBOURHOOD)).all()
    return _best(answer.body, [(i, b) for i, b in rows], "answer")


def comment_duplicate(db: Session, comment: ReviewComment) -> DuplicateFinding | None:
    near = [ReviewComment.review_id == comment.review_id]
    if comment.author_id is not None:
        near.append(ReviewComment.author_id == comment.author_id)
    rows = db.execute(
        select(ReviewComment.id, ReviewComment.body).where(
            ReviewComment.id != comment.id, ReviewComment.is_removed.is_(False),
            ReviewComment.created_at < comment.created_at, or_(*near))
        .order_by(ReviewComment.created_at.desc()).limit(NEIGHBOURHOOD)).all()
    return _best(comment.body, [(i, b) for i, b in rows], "comment")


def file_finding(db: Session, target_type: ModerationTargetType, target_ref: uuid.UUID,
                 finding: DuplicateFinding, *, now: datetime | None = None) -> bool:
    """One open SYSTEM_DETECTED report per item; the caller commits."""
    from app.services.report_service import file_system_report

    report, created = file_system_report(
        db, target_type=target_type, target_ref=target_ref, signal="duplicate_content",
        reason=ModerationReason.plagiarized, severity=SEVERITY)
    if created:
        report.context = {**(report.context or {}),
                          "evidence": finding.evidence(now or datetime.now(UTC))}
    return created


def _best_effort(db: Session, what: str, ref: uuid.UUID, run) -> None:
    """Run a submission-time check after the content is committed. Any failure is
    logged and rolled back: publication has already happened and stays."""
    try:
        run()
        db.commit()
    except Exception:  # noqa: BLE001 - a check must never break a submission
        db.rollback()
        log.warning("duplicate text check failed", extra={"extra_fields": {
            "what": what, "ref": str(ref)}}, exc_info=True)


def check_new_review(db: Session, review_id: uuid.UUID) -> None:
    def run():
        review = db.get(Review, review_id)
        if review is None or review.is_removed:
            return
        finding = review_duplicates(db, [review]).get(review.id)
        if finding is not None:
            file_finding(db, ModerationTargetType.review, review.id, finding)
    _best_effort(db, "review", review_id, run)


def check_new_answer(db: Session, answer_id: uuid.UUID) -> None:
    def run():
        answer = db.get(Answer, answer_id)
        if answer is None:
            return
        finding = answer_duplicate(db, answer)
        if finding is not None:
            file_finding(db, ModerationTargetType.answer, answer.id, finding)
    _best_effort(db, "answer", answer_id, run)


def check_new_comment(db: Session, comment_id: uuid.UUID) -> None:
    def run():
        comment = db.get(ReviewComment, comment_id)
        if comment is None or comment.is_removed:
            return
        finding = comment_duplicate(db, comment)
        if finding is not None:
            file_finding(db, ModerationTargetType.comment, comment.id, finding)
    _best_effort(db, "comment", comment_id, run)

"""Investigate one review or answer (Figma Overlay/Review/Investigate 8109–8117,
Overlay/Answer/Investigate 8129:*, 8237:26485/26795).

Read-only and staff-only: the votes as cast, which voters a signal flags and
why, how each voter has voted on the author's other reviews, and the earnings
gate with and without the flagged votes. See services/review_investigation.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.security import require_staff
from app.db.session import get_db
from app.models.review import Review
from app.services import review_investigation

router = APIRouter(prefix="/admin", tags=["admin: investigation"],
                   dependencies=[Depends(require_staff)])


class SignalOut(BaseModel):
    kind: str
    label: str


class VoterOut(BaseModel):
    voter_id: uuid.UUID
    name: str
    username: str | None = None
    stage: int
    level_name: str | None = None
    vote: str
    seconds_after: int
    flagged: bool
    signals: list[SignalOut]
    history: list[str | None]
    agreement: int
    weight: float | None = None


class PlaceOut(BaseModel):
    place: str
    votes: int


class GateOut(BaseModel):
    wilson_lower_bound: float
    stage2_plus_voters: int
    voters: int
    passes: bool
    threshold: float
    min_stage2_voters: int


class InvestigationOut(BaseModel):
    review_id: uuid.UUID
    published_at: datetime
    votes_total: int
    up: int
    down: int
    first_10_min: int
    #: Median votes in the first 10 minutes across recent reviews in the category.
    typical_first_10_min: float | None = None
    flagged: int
    flagged_stage2_plus: int
    gate_all: GateOut
    gate_without_flagged: GateOut
    voters: list[VoterOut]
    #: How many of the author's reviews each voter's `history` covers.
    history_size: int
    #: "Where votes came from": first-time votes per place (no voter, no address).
    places: list[PlaceOut] = []
    places_other: int = 0
    places_other_count: int = 0


def _gate(g) -> GateOut:
    return GateOut(wilson_lower_bound=g.wilson_lower_bound, stage2_plus_voters=g.stage2_plus_voters,
                   voters=g.voters, passes=g.passes, threshold=g.threshold,
                   min_stage2_voters=g.min_stage2_voters)


@router.get("/reviews/{review_id}/investigation", response_model=InvestigationOut,
            summary="Investigate a review: votes, flagged voters, the gate without them (staff)")
def investigate_review(review_id: uuid.UUID, db: Session = Depends(get_db)) -> InvestigationOut:
    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review not found.", code="review_not_found")
    i = review_investigation.build(db, review)
    return InvestigationOut(
        review_id=i.review_id, published_at=i.published_at, votes_total=i.votes_total,
        up=i.up, down=i.down, first_10_min=i.first_10_min,
        typical_first_10_min=i.typical_first_10_min, flagged=i.flagged,
        flagged_stage2_plus=i.flagged_stage2_plus, gate_all=_gate(i.gate_all),
        gate_without_flagged=_gate(i.gate_without_flagged),
        voters=[VoterOut(**{**v.__dict__, "signals": [SignalOut(**s.__dict__) for s in v.signals]})
                for v in i.voters],
        history_size=i.history_size,
        places=[PlaceOut(place=p, votes=n) for p, n in i.places],
        places_other=i.places_other, places_other_count=i.places_other_count)


# ---------------------------------------------------------------- author / originality

class PersonOut(BaseModel):
    id: uuid.UUID
    name: str
    username: str | None = None
    stage: int
    level_name: str | None = None


class SourceOut(BaseModel):
    person: PersonOut
    votes: int
    share: float


class ScoreOut(BaseModel):
    id: uuid.UUID
    score: float | None = None
    current: bool


class AuthorReportOut(BaseModel):
    at: datetime
    reason: str | None = None
    status: str


class CircleMemberOut(BaseModel):
    person: PersonOut
    covered: int
    back: int


class AuthorInvestigationOut(BaseModel):
    """Overlay/Review|Answer/Investigate/Author (8112:17871, 8129:19219)."""

    kind: str
    person: PersonOut
    trust_score: float
    joined: datetime
    reviews: int
    answers: int
    earned: str | None = None
    items: int
    helpful_votes: int
    sources: list[SourceOut]
    others_people: int
    others_share: float
    top_share: float
    per_month: list[tuple[str, int]]
    scores: list[ScoreOut]
    #: The review earnings gate; None for answers (no gate exists for them).
    gate: float | None = None
    passing: int
    reports: list[AuthorReportOut]
    circle: list[CircleMemberOut]


class TextMatchOut(BaseModel):
    kind: str
    id: uuid.UUID
    label: str
    href: str | None = None
    score: float
    near_identical: float
    passage_share: float
    shared_phrases: int
    flagged: bool
    reason: str


class OriginalityOut(BaseModel):
    """Overlay/Review|Answer/Investigate/Originality (8112:17611, 8129:19014)."""

    kind: str
    meaningful: bool
    compared: int
    best: TextMatchOut | None = None
    has_photo: bool
    has_receipt: bool


def _author_out(a) -> AuthorInvestigationOut:
    def person(p) -> PersonOut:
        return PersonOut(**p.__dict__)
    return AuthorInvestigationOut(
        kind=a.kind, person=person(a.person), trust_score=a.trust_score, joined=a.joined,
        reviews=a.reviews, answers=a.answers,
        earned=str(a.earned) if a.earned is not None else None, items=a.items,
        helpful_votes=a.helpful_votes,
        sources=[SourceOut(person=person(s.person), votes=s.votes, share=s.share)
                 for s in a.sources],
        others_people=a.others_people, others_share=a.others_share, top_share=a.top_share,
        per_month=a.per_month, scores=[ScoreOut(**s.__dict__) for s in a.scores], gate=a.gate,
        passing=a.passing, reports=[AuthorReportOut(**r.__dict__) for r in a.reports],
        circle=[CircleMemberOut(person=person(c.person), covered=c.covered, back=c.back)
                for c in a.circle])


def _originality_out(o) -> OriginalityOut:
    return OriginalityOut(kind=o.kind, meaningful=o.meaningful, compared=o.compared,
                          best=TextMatchOut(**o.best.__dict__) if o.best else None,
                          has_photo=o.has_photo, has_receipt=o.has_receipt)


def _review(db: Session, review_id: uuid.UUID) -> Review:
    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review not found.", code="review_not_found")
    return review


def _answer(db: Session, answer_id: uuid.UUID):
    from app.models.qa import Answer
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise NotFoundError("Answer not found.", code="answer_not_found")
    return answer


def _author_of(db: Session, user_id: uuid.UUID | None):
    from app.models.user import User
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise NotFoundError("The author's account no longer exists.", code="author_not_found")
    return user


@router.get("/reviews/{review_id}/investigation/author", response_model=AuthorInvestigationOut,
            summary="Investigate a review: its author (staff)")
def review_author(review_id: uuid.UUID, db: Session = Depends(get_db)) -> AuthorInvestigationOut:
    from app.services import investigation_author
    review = _review(db, review_id)
    return _author_out(investigation_author.build(
        db, _author_of(db, review.author_id), kind="reviews", current_id=review.id))


@router.get("/reviews/{review_id}/investigation/originality", response_model=OriginalityOut,
            summary="Investigate a review: how original its text is (staff)")
def review_originality(review_id: uuid.UUID, db: Session = Depends(get_db)) -> OriginalityOut:
    from app.services import investigation_originality
    return _originality_out(investigation_originality.for_review(db, _review(db, review_id)))


# ---------------------------------------------------------------- answers

class AnswerInvestigationOut(BaseModel):
    """Overlay/Answer/Investigate (8129:*, 8237:26795): the answer, its votes and voters."""

    answer_id: uuid.UUID
    question_id: uuid.UUID
    question: str
    asker: str | None = None
    about: str | None = None
    body: str
    posted_at: datetime
    responder_id: uuid.UUID | None = None
    responder: str
    responder_stage: int
    responder_level: str | None = None
    is_best: bool
    picked_by_asker: bool
    is_seller_answer: bool
    votes_total: int
    up: int
    down: int
    first_10_min: int
    typical_first_10_min: float | None = None
    flagged: int
    #: The answer's helpful score (Wilson lower bound) with every vote, and without flagged.
    score_all: float
    score_without_flagged: float
    voters: list[VoterOut]
    history_size: int


@router.get("/answers/{answer_id}/investigation", response_model=AnswerInvestigationOut,
            summary="Investigate an answer: votes, flagged voters, the score without them (staff)")
def investigate_answer(answer_id: uuid.UUID,
                       db: Session = Depends(get_db)) -> AnswerInvestigationOut:
    from app.services import answer_investigation
    i = answer_investigation.build(db, _answer(db, answer_id))
    data = {k: v for k, v in i.__dict__.items() if k != "voters"}
    return AnswerInvestigationOut(
        **data,
        voters=[VoterOut(**{**v.__dict__, "signals": [SignalOut(**s.__dict__) for s in v.signals]})
                for v in i.voters])


@router.get("/answers/{answer_id}/investigation/author", response_model=AuthorInvestigationOut,
            summary="Investigate an answer: its author (staff)")
def answer_author(answer_id: uuid.UUID, db: Session = Depends(get_db)) -> AuthorInvestigationOut:
    from app.services import investigation_author
    answer = _answer(db, answer_id)
    return _author_out(investigation_author.build(
        db, _author_of(db, answer.responder_id), kind="answers", current_id=answer.id))


@router.get("/answers/{answer_id}/investigation/originality", response_model=OriginalityOut,
            summary="Investigate an answer: how original its text is (staff)")
def answer_originality(answer_id: uuid.UUID, db: Session = Depends(get_db)) -> OriginalityOut:
    from app.services import investigation_originality
    return _originality_out(investigation_originality.for_answer(db, _answer(db, answer_id)))


class UnmarkBestIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


@router.post("/answers/{answer_id}/unmark-best", status_code=204, response_class=Response,
             summary="Unmark a best answer (Menu/Answer/Moderate; staff, audited)")
def unmark_best(answer_id: uuid.UUID, payload: UnmarkBestIn, db: Session = Depends(get_db),
                staff=Depends(require_staff)) -> Response:
    """The question goes back to having no best answer; the asker can pick
    again. Audited as `override` with the moderator's note. The responder's
    best-answer badge count is left as it is (a badge records a past pick)."""
    from app.models.enums import ModerationAction, ModerationTargetType
    from app.models.moderation import ModerationLog
    from app.models.qa import Question
    answer = _answer(db, answer_id)
    question = db.get(Question, answer.question_id, with_for_update=True)
    if question is None or (question.best_answer_id != answer.id and not answer.is_best_answer):
        raise AppError("This answer isn't the best answer.", code="not_best_answer",
                       status_code=409, title="Conflicting state")
    answer.is_best_answer = False
    if question.best_answer_id == answer.id:
        question.best_answer_id = None
        question.best_answer_picked_by_id = None
        question.best_answer_picked_at = None
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=staff.id,
                         action=ModerationAction.override,
                         target_type=ModerationTargetType.answer, target_ref=answer.id,
                         notes=f"unmarked best answer: {payload.note.strip()}",
                         context={"question_id": str(question.id), "event": "unmark_best"}))
    db.commit()
    return Response(status_code=204)

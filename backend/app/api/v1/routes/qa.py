"""Community Q&A routes (FR-5, FR-4): product or store questions, answers, Best Answer."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import get_current_user, get_optional_user
from app.db.session import get_db
from app.models.enums import ModerationTargetType, VoteDirection
from app.models.user import User
from app.schemas.qa import (
    AnswerCreate,
    AnswerOut,
    MyQuestionOut,
    QAAuthor,
    QuestionCreate,
    QuestionDetailOut,
    QuestionOut,
    QuestionVoteIn,
    QuestionVoteOut,
    ReplyCreate,
    ReplyOut,
    StoreAnswerEdit,
    SubscriptionIn,
    VoteSet,
    VoteTally,
)
from app.schemas.report import ReportCreate, ReportOut
from app.services import qa_engagement, qa_service, report_service
from app.services.listing_filters import Period

router = APIRouter(prefix="/questions", tags=["qa"])


@router.post("", response_model=QuestionOut, status_code=201,
             summary="Ask a question about a product or a store")
def ask_question(payload: QuestionCreate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> QuestionOut:
    return qa_service.create_question(db, user.id, payload)


@router.get("", response_model=list[QuestionOut], summary="List questions")
def list_questions(db: Session = Depends(get_db),
                   product_id: uuid.UUID | None = None,
                   seller_id: uuid.UUID | None = None,
                   q: str | None = Query(None, max_length=200),
                   period: Period = Query(
                       "all", description="Time: all time, the past year or the past month."),
                   sort: Literal["newest", "oldest"] = "newest",
                   limit: int = Query(30, ge=1, le=100)) -> list[QuestionOut]:
    """List questions, optionally filtered by product, by store, or by free text.

    `q` matches the question wording, the product's name or the store's name,
    which is what the Questions tab on /search needs. `seller_id` is the store
    page's Questions section.
    """
    return qa_service.list_questions(
        db, product_id=product_id, seller_id=seller_id, q=q, limit=min(limit, 100),
        period=period, sort=sort,
    )


@router.get("/mine", response_model=list[MyQuestionOut],
            summary="Your questions and their answers, or the questions you answered")
def my_questions(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 role: Literal["asked", "answered"] = "asked",
                 limit: int = Query(30, ge=1, le=100)) -> list[MyQuestionOut]:
    """The dashboard's Answers tab. Declared before `/{question_id}` so "mine"
    is never read as an id."""
    return qa_service.my_questions(db, user.id, role=role, limit=limit)


@router.get("/{question_id}", response_model=QuestionDetailOut,
            summary="Get a question with its answers")
def get_question(question_id: uuid.UUID, db: Session = Depends(get_db),
                 user: User | None = Depends(get_optional_user)) -> QuestionDetailOut:
    detail = qa_service.get_question_detail(db, question_id, user.id if user else None)
    if user is not None:
        detail.is_subscribed = qa_service.is_subscribed(db, question_id, user.id)
    return detail


@router.put("/{question_id}/subscription", response_model=SubscriptionIn,
            summary="Turn \"Notify me\" on or off for a question (QA-045)")
def set_subscription(question_id: uuid.UUID, payload: SubscriptionIn,
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> SubscriptionIn:
    question = qa_service.get_question_or_404(db, question_id)
    return SubscriptionIn(subscribed=qa_service.set_subscription(
        db, question, user.id, payload.subscribed))


@router.post("/{question_id}/answers", response_model=AnswerOut, status_code=201,
             summary="Answer a question")
def answer_question(question_id: uuid.UUID, payload: AnswerCreate,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> AnswerOut:
    question = qa_service.get_question_or_404(db, question_id)
    return qa_service.create_answer(db, question, user.id, payload)


@router.patch("/{question_id}/answers/{answer_id}", response_model=AnswerOut,
              summary="Edit the store's answer (the store's owner only)")
def edit_store_answer(question_id: uuid.UUID, answer_id: uuid.UUID, payload: StoreAnswerEdit,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> AnswerOut:
    question = qa_service.get_question_or_404(db, question_id)
    return qa_service.edit_store_answer(db, question, answer_id, user, payload.body)


@router.post("/{question_id}/answers/{answer_id}/best", response_model=QuestionDetailOut,
             summary="Award Best Answer (asker only)")
def best_answer(question_id: uuid.UUID, answer_id: uuid.UUID,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> QuestionDetailOut:
    question = qa_service.get_question_or_404(db, question_id)
    return qa_service.mark_best_answer(db, question, answer_id, user.id)


# --- the thread (0073; Figma Question Detail v6B 7731:15601) -------------------
# Helpfulness votes and replies; services/qa_engagement.py has the rules.

@router.put("/{question_id}/vote", response_model=QuestionVoteOut,
            summary="Up-vote a question, or take the up-vote back")
def vote_question(question_id: uuid.UUID, payload: QuestionVoteIn, request: Request,
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> QuestionVoteOut:
    enforce_rate_limit(request, "vote", max_requests=settings.vote_rate_limit_max)
    up, mine = qa_engagement.vote_question(db, question_id, user, payload.up)
    return QuestionVoteOut(upvotes=up, my_upvote=mine)


@router.put("/{question_id}/answers/{answer_id}/vote", response_model=VoteTally,
            summary="Vote an answer helpful or not, or take the vote back (null)")
def vote_answer(question_id: uuid.UUID, answer_id: uuid.UUID, payload: VoteSet,
                request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> VoteTally:
    enforce_rate_limit(request, "vote", max_requests=settings.vote_rate_limit_max)
    up, down, mine = qa_engagement.vote_answer(
        db, question_id, answer_id, user, VoteDirection(payload.vote) if payload.vote else None)
    return VoteTally(up=up, down=down, my_vote=mine.value if mine else None)


@router.post("/{question_id}/answers/{answer_id}/replies", response_model=ReplyOut,
             status_code=201, summary="Reply in an answer's thread")
def reply_to_answer(question_id: uuid.UUID, answer_id: uuid.UUID, payload: ReplyCreate,
                    request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> ReplyOut:
    enforce_rate_limit(request, "comment", max_requests=settings.comment_rate_limit_max)
    r = qa_engagement.add_reply(db, question_id, answer_id, user, payload.body, payload.parent_id)
    return ReplyOut(id=r.id, parent_id=r.parent_id, depth=r.depth, body=r.body,
                    created_at=r.created_at, author=QAAuthor.model_validate(user))


@router.put("/{question_id}/replies/{reply_id}/vote", response_model=VoteTally,
            summary="Vote a reply helpful or not, or take the vote back (null)")
def vote_reply(question_id: uuid.UUID, reply_id: uuid.UUID, payload: VoteSet,
               request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> VoteTally:
    enforce_rate_limit(request, "vote", max_requests=settings.vote_rate_limit_max)
    up, down, mine = qa_engagement.vote_reply(
        db, question_id, reply_id, user, VoteDirection(payload.vote) if payload.vote else None)
    return VoteTally(up=up, down=down, my_vote=mine.value if mine else None)


@router.delete("/{question_id}/replies/{reply_id}", status_code=204,
               summary="Remove a reply (its author, or staff)")
def remove_reply(question_id: uuid.UUID, reply_id: uuid.UUID,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> Response:
    qa_engagement.remove_reply(db, question_id, reply_id, user)
    return Response(status_code=204)


@router.post("/{question_id}/answers/{answer_id}/report", response_model=ReportOut,
             status_code=201, summary="Report an answer to the administrators")
def report_answer(question_id: uuid.UUID, answer_id: uuid.UUID, payload: ReportCreate,
                  request: Request, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> ReportOut:
    enforce_rate_limit(request, "report", max_requests=settings.report_rate_limit_max)
    answer = qa_engagement.answer_or_404(db, question_id, answer_id)
    log, _created = report_service.file_report(
        db, reporter_id=user.id, author_id=answer.responder_id,
        target_type=ModerationTargetType.answer, target_ref=answer.id,
        reason=payload.reason, notes=payload.notes, evidence_url=payload.evidence_url)
    return ReportOut.model_validate(log)

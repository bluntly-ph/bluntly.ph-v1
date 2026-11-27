"""Community Q&A service (FR-5, and FR-4's seller Q&A).

Questions about a product or about a store, with answers, a First Responder
badge (first answer within 24h), and a Best Answer the asker awards.
Answer-level earning stays unwired (ADR-006 / A5). Trust-score recompute on
Best Answer is left to the trust system; here we set the flags and award the
badges.

A store question (0045) is asked from the seller page. When the store's
moderator-approved owner answers it, the answer is marked as the seller's and
shown under the store's name; anyone else, including a claimant still waiting
for a moderator, answers as a buyer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.models.enums import (
    ModerationAction,
    ModerationTargetType,
    QuestionDirectedTo,
    SellerClaimStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.qa import Answer, Question, QuestionSubscription
from app.models.seller import Seller
from app.models.user import Badge, User, UserBadge
from app.schemas.qa import (
    AnswerCreate,
    AnswerOut,
    MyQuestionOut,
    QAAuthor,
    QuestionCreate,
    QuestionDetailOut,
    QuestionOut,
    ReplyOut,
)
from app.services import answer_parts, notification_service
from app.services.listing_filters import period_start
from app.services.storage import review_photo_belongs_to

FIRST_RESPONDER_WINDOW = timedelta(hours=24)


def is_seller_answer(seller: Any | None, responder_id: uuid.UUID) -> bool:
    """Whether this responder answers *as the store*.

    Only the owner a moderator approved — `claim_status == claimed` and
    `claimed_by_id` is them. A pending claim is a request, not ownership
    (FR-4), so a claimant waiting on a moderator answers as a buyer.
    """
    return (
        seller is not None
        and seller.claim_status == SellerClaimStatus.claimed
        and seller.claimed_by_id is not None
        and seller.claimed_by_id == responder_id
    )


def first_responder_eligible(prior_answers: int, age: timedelta, *,
                             answering_own: bool, seller_answer: bool) -> bool:
    """The First Responder rule: the first answer, inside the window.

    Refused when answering your own question (the self-dealing hole it used to
    have), and when a store answers a question about itself: a store replying
    to its own customers is the point of the feature, and a badge for it would
    reward the store for being asked.
    """
    return (prior_answers == 0 and age <= FIRST_RESPONDER_WINDOW
            and not answering_own and not seller_answer)


def _author(user: User | None) -> QAAuthor | None:
    if user is None:
        return None
    # The reputation too: the card prints it beside the level name, so leaving
    # it out showed every asker and answerer as "0", Stage 3 included.
    return QAAuthor(
        id=user.id, username=user.username, display_name=user.display_name,
        trust_stage=user.trust_stage, trust_level_name=user.trust_level_name,
        reputation_score=user.reputation_score, avatar_url=user.avatar_url,
    )


def _asker_picked(q: Question) -> bool:
    """Whether the question's Best Answer is a recorded pick by its asker (QA-058).

    Business Rules §7: only the asker awards Best Answer. Picks made before the
    pick was recorded (seed data and the pre-release code) carry no picker, so
    nothing shows they were the asker's — the retest found exactly such a badge
    and could not tell who chose it. Those are not presented as Best Answer;
    the rows are left untouched, and the asker can pick again, properly.
    """
    return q.best_answer_picked_by_id is not None and q.best_answer_picked_by_id == q.asker_id


def _answer_out(answer: Answer, responder: User | None,
                seller: Seller | None = None, *, best_is_attributed: bool = True) -> AnswerOut:
    return AnswerOut(
        id=answer.id, answer_id=answer.answer_id, body=answer.body,
        is_best_answer=bool(answer.is_best_answer and best_is_attributed),
        is_first_responder=answer.is_first_responder,
        helpful_votes=answer.helpful_votes, created_at=answer.created_at,
        responder=_author(responder),
        is_seller_answer=bool(answer.is_seller_answer),
        seller_name=(seller.display_name
                     if answer.is_seller_answer and seller is not None else None),
        edited_at=answer.edited_at,
    )


def _award_badge(db: Session, user_id: uuid.UUID | None, badge_key: str) -> None:
    if user_id is None:
        return
    badge = db.scalar(select(Badge).where(Badge.badge_id == badge_key))
    if badge is None:
        return
    already = db.scalar(
        select(UserBadge).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
    )
    if already is None:
        db.add(UserBadge(user_id=user_id, badge_id=badge.id))


def get_question_or_404(db: Session, question_id: uuid.UUID) -> Question:
    q = db.get(Question, question_id)
    if q is None or q.is_removed:
        raise NotFoundError("Question not found.", code="question_not_found")
    return q


def create_question(db: Session, asker_id: uuid.UUID, payload: QuestionCreate) -> QuestionOut:
    product = seller = None
    if payload.product_id is not None:
        product = db.get(Product, payload.product_id)
        if product is None:
            raise NotFoundError("Product not found.", code="product_not_found")
    else:
        seller = db.get(Seller, payload.seller_id)
        if seller is None:
            raise NotFoundError("Seller not found.", code="seller_not_found")
    q = Question(
        product_id=payload.product_id, seller_id=payload.seller_id, asker_id=asker_id,
        body=payload.body,
        # Deprecated column (owner decision 2026-09-28: no audience choice).
        # Still NOT NULL, so it is derived from the subject, never asked for;
        # nothing reads it any more. A later migration can drop it.
        directed_to=(QuestionDirectedTo.seller if payload.seller_id is not None
                     else QuestionDirectedTo.buyers),
        question_id=f"qst_{uuid.uuid4().hex[:10]}",
    )
    db.add(q)
    # A question about a claimed store reaches its owner (Seller console
    # notifications, "New question"); never their own question.
    if (seller is not None and seller.claim_status == SellerClaimStatus.claimed
            and seller.claimed_by_id is not None and seller.claimed_by_id != asker_id):
        asker = db.get(User, asker_id)
        who = (asker.display_name or asker.username) if asker is not None else None
        notification_service.notify(
            db, seller.claimed_by_id, "store_question_new", "New question",
            body=f"{who or 'A buyer'} · {payload.body[:200]}",
            link=f"/seller/{seller.id}/questions")
    db.commit()
    db.refresh(q)
    return QuestionOut(
        id=q.id, question_id=q.question_id, product_id=q.product_id,
        product_name=product.canonical_name if product is not None else None,
        seller_id=q.seller_id,
        seller_name=seller.display_name if seller is not None else None,
        body=q.body,
        best_answer_id=None, answer_count=0, created_at=q.created_at,
        asker=_author(db.get(User, asker_id)),
    )


#: Words that say nothing about what a question asks ("how", "does", "it").
_QUESTION_STOPWORDS = frozenset("""
a an and are as at be but by can could do does for from had has have how i if in
is it its it's me my of on or so than that the their them then there these this
to was we what when where which who why will with would you your
""".split())


def question_words(needle: str) -> list[str]:
    """The words of a search that can find a question, in order, once each:
    3 letters or more and not a stopword."""
    seen: list[str] = []
    for raw in needle.lower().split():
        w = "".join(ch for ch in raw if ch.isalnum() or ch in "-'")
        w = w.strip("-'")
        if len(w) >= 3 and w not in _QUESTION_STOPWORDS and w not in seen:
            seen.append(w)
    return seen[:8]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_questions(
    db: Session, *, product_id: uuid.UUID | None = None,
    seller_id: uuid.UUID | None = None, q: str | None = None, limit: int = 30,
    period: str | None = None, sort: str = "newest",
) -> list[QuestionOut]:
    """`period` and `sort` are the Questions tab's Time filter and By-date order
    (QA-050): the two controls of the search sheets that mean the same thing
    for a question as for a review."""
    stmt = select(Question).where(Question.is_removed.is_(False))
    since = period_start(period)  # type: ignore[arg-type]
    if since is not None:
        stmt = stmt.where(Question.created_at >= since)
    if product_id is not None:
        stmt = stmt.where(Question.product_id == product_id)
    if seller_id is not None:
        stmt = stmt.where(Question.seller_id == seller_id)
    # Free-text search, for the Questions tab on /search.
    #
    # The wording, the product and the store are all matched: someone searching
    # "jisulife" means the product or the store at least as often as the
    # phrasing of a question, and the card's headline is that subject.
    needle = (q or "").strip()
    score = None
    if needle:
        # Business Rules §6: products match through the shared ranked matcher;
        # question text only as a substring from 4 characters.
        from app.services import product_search
        long_enough = (len(product_search.normalize(needle))
                       >= product_search.MIN_SUBSTRING_LENGTH)
        like = f"%{_escape_like(needle)}%" if long_enough else f"{_escape_like(needle)}%"
        # QA-050 (Questions v6, "Best match for your search"): several words
        # are matched one by one, not as one phrase — "noise library" finds
        # "How much noise does it make in a quiet library?" — and the question
        # holding the most of them ranks first.
        words = question_words(needle)
        word_likes = [Question.body.ilike(f"%{_escape_like(w)}%", escape="\\") for w in words]
        body_match = (or_(*word_likes) if len(words) > 1
                      else Question.body.ilike(like, escape="\\"))
        stmt = stmt.where(
            or_(
                body_match,
                Question.product_id.in_(product_search.matching_product_ids(needle)),
                Question.seller_id.in_(
                    select(Seller.id).where(Seller.display_name.ilike(like, escape="\\")),
                ),
            ),
        )
        if len(words) > 1 and sort != "oldest":
            score = sum((case((m, 1), else_=0) for m in word_likes), literal(0))
    order = (Question.created_at.asc() if sort == "oldest" else Question.created_at.desc())
    ordering = (score.desc(), order, Question.id) if score is not None else (order, Question.id)
    questions = list(db.scalars(stmt.order_by(*ordering).limit(limit)))
    return _question_cards(db, questions)


def _question_cards(db: Session, questions: list[Question]) -> list[QuestionOut]:
    """The list card for each question, with its subject and answer count, in
    one query per table rather than one per question."""
    if not questions:
        return []

    asker_ids = {q.asker_id for q in questions if q.asker_id is not None}
    product_ids = {q.product_id for q in questions if q.product_id is not None}
    seller_ids = {q.seller_id for q in questions if q.seller_id is not None}
    q_ids = [q.id for q in questions]
    askers = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(asker_ids)))}
        if asker_ids else {}
    )
    products = (
        {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
        if product_ids else {}
    )
    sellers = (
        {s.id: s for s in db.scalars(select(Seller).where(Seller.id.in_(seller_ids)))}
        if seller_ids else {}
    )
    counts = dict(
        db.execute(
            select(Answer.question_id, func.count(Answer.id))
            .where(Answer.question_id.in_(q_ids))
            .group_by(Answer.question_id)
        ).all()
    )
    # The Best Answer's author, for the admin Answers queue: who answered whom.
    best_ids = [q.best_answer_id for q in questions if q.best_answer_id and _asker_picked(q)]
    best_by: dict[uuid.UUID, User] = {}
    if best_ids:
        rows = db.execute(
            select(Answer.id, User).join(User, User.id == Answer.responder_id)
            .where(Answer.id.in_(best_ids))
        ).all()
        best_by = {answer_id: user for answer_id, user in rows}
    return [
        QuestionOut(
            id=q.id, question_id=q.question_id, product_id=q.product_id,
            product_name=(products[q.product_id].canonical_name
                          if q.product_id in products else None),
            product_image_url=(products[q.product_id].image_url
                               if q.product_id in products else None),
            seller_id=q.seller_id,
            seller_name=sellers[q.seller_id].display_name if q.seller_id in sellers else None,
            body=q.body,
            best_answer_id=q.best_answer_id if _asker_picked(q) else None,
            answer_count=counts.get(q.id, 0), created_at=q.created_at,
            asker=_author(askers.get(q.asker_id)),
            best_answer_by=(_author(best_by.get(q.best_answer_id))
                            if q.best_answer_id and _asker_picked(q) else None),
        )
        for q in questions
    ]


def my_questions(db: Session, user_id: uuid.UUID, *, role: str = "asked",
                 limit: int = 30) -> list[MyQuestionOut]:
    """The dashboard's Answers tab (owner, 2026-09-28): "answers for my queries".

    `asked` — the questions this member asked, newest activity first, each
    with its newest answers (the Best Answer first once the asker picked one).
    `answered` — the questions this member answered, with their own answer.
    Removed questions are left out either way.
    """
    if role == "answered":
        mine = list(db.scalars(
            select(Answer).where(Answer.responder_id == user_id)
            .order_by(Answer.created_at.desc()).limit(limit)))
        own = {a.question_id: a for a in reversed(mine)}
        questions = [q for q in (db.get(Question, qid) for qid in own)
                     if q is not None and not q.is_removed]
        questions.sort(key=lambda q: own[q.id].created_at, reverse=True)
    else:
        last_answer = (select(Answer.question_id, func.max(Answer.created_at).label("at"))
                       .group_by(Answer.question_id).subquery())
        activity = func.coalesce(last_answer.c.at, Question.created_at)
        questions = list(db.scalars(
            select(Question)
            .outerjoin(last_answer, last_answer.c.question_id == Question.id)
            .where(Question.asker_id == user_id, Question.is_removed.is_(False))
            .order_by(activity.desc(), Question.id).limit(limit)))
        own = {}
    cards = _question_cards(db, questions)
    if not cards:
        return []
    by_id = {q.id: q for q in questions}
    answers = list(db.scalars(
        select(Answer).where(Answer.question_id.in_(list(by_id)))
        .order_by(Answer.is_best_answer.desc(), Answer.created_at.desc())))
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(
        {a.responder_id for a in answers if a.responder_id is not None})))} if answers else {}
    sellers = {s.id: s for s in db.scalars(select(Seller).where(Seller.id.in_(
        {q.seller_id for q in questions if q.seller_id is not None})))}
    out = []
    for card in cards:
        q = by_id[card.id]
        picked = _asker_picked(q)
        seller = sellers.get(q.seller_id)
        latest = [a for a in answers if a.question_id == q.id]
        if not picked:
            latest.sort(key=lambda a: a.created_at, reverse=True)
        mine_here = own.get(q.id)
        out.append(MyQuestionOut(
            **card.model_dump(),
            latest_answers=[_answer_out(a, people.get(a.responder_id), seller,
                                        best_is_attributed=picked) for a in latest[:2]],
            my_answer=(_answer_out(mine_here, people.get(mine_here.responder_id), seller,
                                   best_is_attributed=picked)
                       if mine_here is not None else None),
        ))
    return out


def get_question_detail(db: Session, question_id: uuid.UUID,
                        viewer_id: uuid.UUID | None = None) -> QuestionDetailOut:
    q = get_question_or_404(db, question_id)
    answers = list(
        db.scalars(
            select(Answer)
            .where(Answer.question_id == q.id)
            .order_by(
                Answer.is_best_answer.desc(),
                Answer.wilson_score.desc(),
                Answer.created_at.asc(),
            )
        )
    )
    responder_ids = {a.responder_id for a in answers if a.responder_id is not None}
    responders = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(responder_ids)))}
        if responder_ids else {}
    )
    product = db.get(Product, q.product_id) if q.product_id else None
    seller = db.get(Seller, q.seller_id) if q.seller_id else None
    asker = db.get(User, q.asker_id) if q.asker_id else None
    picked = _asker_picked(q)
    outs = [_answer_out(a, responders.get(a.responder_id), seller, best_is_attributed=picked)
            for a in answers]
    # The thread (0073): votes and replies from their rows, with the viewer's own.
    from app.models.qa import QAVote
    from app.services import qa_engagement as eng
    ids = [a.id for a in answers]
    tally = eng.tallies(db, QAVote.answer_id, ids)
    my = eng.mine(db, viewer_id, QAVote.answer_id, ids)
    threads = eng.threads(db, ids, viewer_id)
    for out in outs:
        out.helpful_votes, out.unhelpful_votes = tally.get(out.id, (0, 0))
        out.my_vote = my[out.id].value if out.id in my else None
        rows = threads.get(out.id, [])
        out.replies = [ReplyOut(id=r.id, parent_id=r.parent_id, depth=r.depth, body=r.body,
                                created_at=r.created_at, author=_author(r.author), up=r.up,
                                down=r.down, my_vote=r.my_vote.value if r.my_vote else None)
                       for r in rows]
        out.reply_count = len(rows)
    q_up = eng.tallies(db, QAVote.question_id, [q.id]).get(q.id, (0, 0))[0]
    return QuestionDetailOut(
        id=q.id, question_id=q.question_id, product_id=q.product_id,
        product_name=product.canonical_name if product else None,
        product_image_url=product.image_url if product else None,
        upvotes=q_up, my_upvote=q.id in eng.mine(db, viewer_id, QAVote.question_id, [q.id]),
        reply_count=sum(o.reply_count for o in outs),
        seller_id=q.seller_id, seller_name=seller.display_name if seller else None,
        body=q.body,
        best_answer_id=q.best_answer_id if picked else None,
        answer_count=len(answers), created_at=q.created_at, asker=_author(asker),
        answers=outs,
        best_answer_picked_at=q.best_answer_picked_at if picked else None,
        best_answer_picked_by_asker=picked,
    )


def edit_store_answer(db: Session, question: Question, answer_id: uuid.UUID,
                      user: User, body: str) -> AnswerOut:
    """The store's owner rewrites the store's answer (Figma Overlay/Store/
    EditAnswer 8202:22530); buyers then see "Edited".

    Only a store answer, only by the person who wrote it, and only while they
    still own the store: an owner who gave the store up can no longer speak
    for it. Buyers' answers are not editable (their votes and any Best Answer
    rest on the words as written)."""
    answer = db.get(Answer, answer_id)
    if answer is None or answer.question_id != question.id:
        raise NotFoundError("Answer not found.")
    seller = db.get(Seller, question.seller_id) if question.seller_id else None
    if (not answer.is_seller_answer or answer.responder_id != user.id
            or not is_seller_answer(seller, user.id)):
        raise ForbiddenError("Only the store's owner can edit the store's answer.",
                             code="not_store_answer_owner")
    answer.body = body
    answer.edited_at = datetime.now(UTC)
    db.commit()
    db.refresh(answer)
    return _answer_out(answer, user, seller)


#: What each required part is called in an error (the answer flow's step names).
_PART_WORDS = {"experience": "your experience", "pros_cons": "pros and cons",
               "verdict": "your verdict", "fit": "whether it's right for them"}


def _require_structure(question: Question, parts: answer_parts.AnswerParts, *,
                       seller_answer: bool) -> None:
    """Structured Q&A (owner 2026-10-05): a member's answer to a question about
    a product carries a RATING, always, and every specific the asker requested
    on the question's "Looking for:" line. Unrequested parts stay optional.

    Not applied to a store's own answer (a store does not rate its own product,
    and the seller console answers in words) nor to a question about a store,
    which has no rating step. A legacy question requests nothing, so only the
    rating applies to it.
    """
    if seller_answer or question.product_id is None:
        return
    if parts.rating is None:
        raise AppError("Give it a star rating. Every answer needs one.",
                       code="answer_rating_required", status_code=422,
                       title="Invalid answer", extra={"parts": ["rating"]})
    missing = answer_parts.missing_parts(parts, answer_parts.requested_parts(question.body))
    if missing:
        listed = ", ".join(_PART_WORDS[p] for p in missing)
        raise AppError(f"The asker asked for {listed}. Add it before posting.",
                       code="answer_part_required", status_code=422,
                       title="Invalid answer", extra={"parts": missing})


def create_answer(
    db: Session, question: Question, responder_id: uuid.UUID, payload: AnswerCreate,
) -> AnswerOut:
    prior = db.scalar(
        select(func.count(Answer.id)).where(Answer.question_id == question.id)
    )
    age = datetime.now(UTC) - question.created_at
    seller = db.get(Seller, question.seller_id) if question.seller_id else None
    seller_answer = is_seller_answer(seller, responder_id)
    responder = db.get(User, responder_id)
    if responder is not None and responder.is_claimed_seller and not seller_answer:
        # Business Rules §7: a seller participates in the conversation but never
        # submits a competing answer. Its answer belongs on questions put to its
        # own store; anywhere else it would compete with buyers.
        raise ForbiddenError(
            "A claimed seller account answers only questions put to its own store.",
            code="seller_cannot_answer")
    # Answering your own question is allowed - somebody who finds the answer
    # and comes back to share it is doing exactly what the board is for. What
    # is not allowed is being paid for it: without this, asking a question and
    # answering it a second later awards yourself the first-responder badge,
    # repeatably, one new question at a time. See first_responder_eligible.
    is_first = first_responder_eligible(
        prior or 0, age, answering_own=responder_id == question.asker_id,
        seller_answer=seller_answer)

    # The structured parts (meeting 2026-10-02) are stored as labelled lines
    # after the answer's words (services/answer_parts). A photo must be one
    # this answerer uploaded through us, as on a review.
    for url in payload.photo_urls:
        if not review_photo_belongs_to(url, responder_id):
            raise AppError("A photo must be one you uploaded.", code="answer_photo_not_owned",
                           status_code=422, title="Invalid answer")
    parts = answer_parts.AnswerParts(
        text=payload.body, experience=payload.experience, good=payload.good, bad=payload.bad,
        recommend=payload.recommend, right_for_you=payload.right_for_you,
        rating=payload.rating, photo_urls=list(payload.photo_urls), verdict=payload.verdict,
        verdict_reason=payload.verdict_reason)
    _require_structure(question, parts, seller_answer=seller_answer)
    body = answer_parts.compose(parts)
    # What a notification says: the words, never the photo addresses.
    summary = answer_parts.compose(answer_parts.AnswerParts(
        **{**parts.__dict__, "photo_urls": []}))

    answer = Answer(
        question_id=question.id, responder_id=responder_id, body=body,
        answer_id=f"ans_{uuid.uuid4().hex[:10]}", is_first_responder=is_first,
        is_seller_answer=seller_answer,
    )
    db.add(answer)
    if is_first:
        _award_badge(db, responder_id, "first_responder")
    if question.asker_id is not None and question.asker_id != responder_id:
        notification_service.notify(
            db, question.asker_id, "question_answered",
            "The store answered your question" if seller_answer
            else "Your question has a new answer",
            body=summary, link=f"/questions/{question.id}")
    # "Notify me!" (QA-045): everyone subscribed, except the asker (told above)
    # and the person who just answered.
    for (subscriber,) in db.execute(select(QuestionSubscription.user_id).where(
            QuestionSubscription.question_id == question.id)).all():
        if subscriber in (responder_id, question.asker_id):
            continue
        notification_service.notify(
            db, subscriber, "question_answered",
            "A question you follow has a new answer",
            body=summary, link=f"/questions/{question.id}")
    db.commit()
    # Copied answers are moderation evidence; best effort, after publication.
    from app.services.duplicate_text import check_new_answer
    check_new_answer(db, answer.id)
    db.refresh(answer)
    return _answer_out(answer, db.get(User, responder_id), seller)


def mark_best_answer(
    db: Session, question: Question, answer_id: uuid.UUID, asker_id: uuid.UUID,
) -> QuestionDetailOut:
    if question.asker_id != asker_id:
        raise ForbiddenError(
            "Only the person who asked can pick the best answer.",
            code="not_question_owner",
        )
    answer = db.get(Answer, answer_id)
    if answer is None or answer.question_id != question.id:
        raise NotFoundError("Answer not found.", code="answer_not_found")
    # The asker picks the best answer, so without this the asker can pick their
    # own and award themselves the badge. The other half of the same hole as
    # the first-responder check in create_answer.
    if answer.responder_id == asker_id:
        raise ForbiddenError(
            "You cannot mark your own answer as the best one.",
            code="cannot_pick_own_answer",
        )
    responder = db.get(User, answer.responder_id) if answer.responder_id else None
    if answer.is_seller_answer or (responder is not None and responder.is_claimed_seller):
        # §13: sellers "never vote, earn, or win awards".
        raise AppError("A store's answer can't be picked as the best answer.",
                       code="seller_cannot_win", status_code=409, title="Conflicting state")

    newly_picked = question.best_answer_id != answer.id
    if question.best_answer_id and question.best_answer_id != answer.id:
        previous = db.get(Answer, question.best_answer_id)
        if previous is not None:
            previous.is_best_answer = False
    answer.is_best_answer = True
    question.best_answer_id = answer.id
    # QA-058: who picked it and when, on the question and in the audit log.
    question.best_answer_picked_by_id = asker_id
    question.best_answer_picked_at = datetime.now(UTC)
    db.add(ModerationLog(target_type=ModerationTargetType.answer, target_ref=answer.id,
                         moderator_id=asker_id, action=ModerationAction.best_answer_pick,
                         context={"question_id": str(question.id)}))
    _award_badge(db, answer.responder_id, "best_answer")
    if newly_picked:
        notification_service.notify(
            db, answer.responder_id, "best_answer",
            "The person who asked picked your answer as the best one",
            body=question.body, link=f"/questions/{question.id}")
    db.commit()
    return get_question_detail(db, question.id, asker_id)


def set_subscription(db: Session, question: Question, user_id: uuid.UUID,
                     subscribed: bool) -> bool:
    """ "Notify me!" on a question (QA-045). Idempotent either way."""
    existing = db.get(QuestionSubscription, (question.id, user_id))
    if subscribed and existing is None:
        db.add(QuestionSubscription(question_id=question.id, user_id=user_id))
    elif not subscribed and existing is not None:
        db.delete(existing)
    db.commit()
    return subscribed


def is_subscribed(db: Session, question_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
    if user_id is None:
        return False
    return db.get(QuestionSubscription, (question_id, user_id)) is not None

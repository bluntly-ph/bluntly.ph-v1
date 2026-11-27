"""The Monday summary for store owners (Figma Screen/Seller/Settings "Weekly summary":
rating, new reviews and what's waiting, every Monday).

`enqueue_all(db)` runs from the weekly `weekly_summaries` task (internal_cron, Monday
08:00 Manila). One email per claimed store whose owner has the switch on, queued in the
email outbox with a dedupe key per store and ISO week, so a job that runs twice queues
nothing twice. A store with nothing new and nothing waiting gets no email: an empty
summary every week teaches people to ignore it.

Every figure is counted from rows, the same way the console counts it:
  * store rating   the visible reviews' overall average, as the store page shows it
                   (seller_service.summarize_reviews)
  * new reviews    visible store reviews posted in the last 7 days
  * responses      store responses first posted in the last 7 days
  * new questions  store questions asked in the last 7 days
  * waiting        visible reviews with no response; store questions the store hasn't answered
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.email_templates import weekly_summary_email
from app.core.config import settings
from app.models.enums import SellerClaimStatus
from app.models.qa import Answer, Question
from app.models.seller import Seller, SellerReview
from app.models.user import User
from app.services import email_outbox_service as outbox
from app.services.notification_service import prefs_of

MANILA = ZoneInfo("Asia/Manila")


def _rating(value) -> str:
    if value is None:
        return "—"
    v = float(value)
    return f"{int(v) if v.is_integer() else round(v, 1)} / 5"


def store_week(db: Session, seller: Seller, *, since: datetime) -> dict:
    """The figures for one store over [since, now)."""
    from app.services.seller_service import summarize_reviews

    visible = db.scalars(select(SellerReview).where(
        SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False))).all()
    summary = summarize_reviews(visible)
    new_reviews = sum(1 for r in visible if r.created_at >= since)
    responses = sum(1 for r in visible if r.seller_response_at and r.seller_response_at >= since)
    awaiting = sum(1 for r in visible if not r.seller_response)
    # As the dashboard counts it (seller_dashboard.build): a question is answered
    # once the store has answered it.
    answered = select(Answer.question_id).where(Answer.is_seller_answer.is_(True))
    questions = db.execute(select(Question.id, Question.created_at).where(
        Question.seller_id == seller.id, Question.is_removed.is_(False))).all()
    unanswered = db.scalar(select(func.count()).select_from(Question).where(
        Question.seller_id == seller.id, Question.is_removed.is_(False),
        Question.id.not_in(answered))) or 0
    return {
        "rating": summary.overall_average,
        "reviews_total": len(visible),
        "new_reviews": new_reviews,
        "responses": responses,
        "new_questions": sum(1 for _, created in questions if created >= since),
        "reviews_waiting": awaiting,
        "questions_waiting": int(unanswered),
    }


def _waiting_line(f: dict) -> str:
    parts = []
    if f["reviews_waiting"]:
        n = f["reviews_waiting"]
        parts.append(f"{n} review{'s' if n != 1 else ''} without your response")
    if f["questions_waiting"]:
        n = f["questions_waiting"]
        parts.append(f"{n} question{'s' if n != 1 else ''} without your answer")
    return ("Waiting on you: " + " and ".join(parts) + ".") if parts else \
        "Nothing is waiting on you. Nice."


def enqueue_all(db: Session, *, now: datetime | None = None) -> int:
    """Queue this week's summaries. Returns how many were newly queued (a second run
    in the same week finds them all queued and returns 0)."""
    now = (now or datetime.now(MANILA)).astimezone(MANILA)
    since = now - timedelta(days=7)
    year, week, _ = now.isocalendar()
    site = settings.public_site_url
    queued = 0
    stores = db.execute(select(Seller, User)
                        .join(User, User.id == Seller.claimed_by_id)
                        .where(Seller.claim_status == SellerClaimStatus.claimed,
                               User.is_suspended.is_(False))
                        .order_by(Seller.id)).all()
    for seller, owner in stores:
        if not owner.email or not prefs_of(owner)["weekly_summary"]:
            continue
        f = store_week(db, seller, since=since)
        quiet = not (f["new_reviews"] or f["responses"] or f["new_questions"]
                     or f["reviews_waiting"] or f["questions_waiting"])
        if quiet:
            continue
        figures = [
            ("Store rating", f"{_rating(f['rating'])} · {f['reviews_total']} reviews"),
            ("New reviews this week", str(f["new_reviews"])),
            ("Your responses this week", str(f["responses"])),
            ("New questions this week", str(f["new_questions"])),
        ]
        subject, text, html = weekly_summary_email(
            store=seller.display_name, week=since.strftime("%-d %b %Y"), figures=figures,
            waiting_line=_waiting_line(f), open_url=f"{site}/seller/{seller.id}",
            unsubscribe_url=outbox.unsubscribe_page(owner.id, "weekly_summary"))
        queued += outbox.enqueue(
            db, to=owner.email, kind="weekly_summary", subject=subject, text=text, html=html,
            user_id=owner.id,
            headers=outbox.unsubscribe_headers(owner.id, "weekly_summary") or None,
            dedupe_key=f"weekly:{seller.id}:{year}-W{week:02d}")
    db.commit()
    return queued

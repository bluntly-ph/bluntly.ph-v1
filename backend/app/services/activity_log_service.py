"""The admin Activity log (Figma Screen/Admin/ActivityLog 8074:16245 with its
Person / Action / Target / Range menus 8080:*): the audit log
(`moderation_logs`) read with filters, each row named in words, and the side
cards — today by type, proof-of-purchase views this week, team today.

Nothing new is stored. A type is a fixed grouping of the audit actions; a
target is labelled from its own row (the review's product and author, the
member's name, the question's opening words).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.models.conversation import Conversation
from app.models.enums import ModerationAction as A
from app.models.enums import ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.qa import Answer, Question
from app.models.review import Review
from app.models.seller import Seller, SellerReview
from app.models.user import User

#: Figma "Today by type": every audit action in one of five groups.
GROUPS: dict[str, tuple[A, ...]] = {
    "moderation": (A.report, A.approve, A.reject, A.remove, A.penalize, A.override, A.escalate,
                   A.publish, A.unpublish, A.cold_start_substitution, A.best_answer_pick,
                   A.seller_appeal, A.substantiation_request, A.appeal_decision, A.track_flip,
                   A.investigation_set, A.investigation_clear, A.author_delete,
                   A.special_routing, A.photo_replace, A.alias_add, A.alias_remove,
                   A.support_request, A.listing_attach, A.restore, A.conversation,
                   A.store_product, A.product_import),
    "money": (A.csv_import, A.payout, A.honesty_fund_distribution, A.affiliate_link_attach,
              A.affiliate_link_revoke, A.remittance_record, A.cashout_request, A.qa_test_credit),
    "access": (A.role_grant, A.role_revoke, A.suspend, A.qa_tester_add, A.qa_tester_remove,
               A.store_release, A.integration_change),
    "privacy": (A.receipt_view, A.data_export),
}
#: The Activity log offers the first three; the admin export also reads 90d and 12m.
RANGES = {"today": None, "7d": 7, "30d": 30, "90d": 90, "12m": 365}


def group_of(action: A) -> str:
    for name, actions in GROUPS.items():
        if action in actions:
            return name
    return "moderation"


def _since(range_: str | None, now: datetime) -> datetime | None:
    if not range_ or range_ == "all":
        return None
    if range_ == "today":
        return now.astimezone(MANILA).replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=RANGES[range_])


@dataclass(frozen=True)
class Row:
    id: uuid.UUID
    action: str
    group: str
    actor_id: uuid.UUID | None
    #: None: the system (a scheduled job or an automated signal).
    actor: str | None
    target_type: str | None
    target_ref: str | None
    target_label: str | None
    href: str | None
    reason: str | None
    notes: str | None
    at: datetime
    #: A report decision's outcome (dismissed, content_removed, escalated, …):
    #: a dismissal is audited as `approve`, so the label reads this instead
    #: (MQA-006: "Approved review" after a dismissal).
    outcome: str | None = None


def _name(u: User | None) -> str | None:
    if u is None:
        return None
    return u.display_name or (f"@{u.username}" if u.username else None)


def _labels(db: Session, logs: list[ModerationLog]) -> dict[uuid.UUID, tuple[str, str | None]]:
    """target_ref -> (label, admin link), read in one query per target type."""
    out: dict[uuid.UUID, tuple[str, str | None]] = {}
    by_type: dict[ModerationTargetType, set[uuid.UUID]] = {}
    for log in logs:
        if log.target_type and log.target_ref:
            by_type.setdefault(log.target_type, set()).add(log.target_ref)
    if ids := by_type.get(ModerationTargetType.review):
        for rid, title, product, display, username in db.execute(
                select(Review.id, Review.title, Product.canonical_name,
                       User.display_name, User.username)
                .outerjoin(Product, Product.id == Review.product_id)
                .outerjoin(User, User.id == Review.author_id)
                .where(Review.id.in_(ids))):
            who = display or (f"@{username}" if username else None)
            label = product or title or "a review"
            out[rid] = (f"{label}{f' by {who}' if who else ''}", f"/reviews/{rid}")
    if ids := by_type.get(ModerationTargetType.user):
        for u in db.scalars(select(User).where(User.id.in_(ids))):
            out[u.id] = (_name(u) or "a member", f"/admin/people/{u.id}")
    if ids := by_type.get(ModerationTargetType.question):
        for qid, body in db.execute(select(Question.id, Question.body).where(Question.id.in_(ids))):
            out[qid] = (_quote(body), f"/questions/{qid}")
    if ids := by_type.get(ModerationTargetType.answer):
        for aid, qid, body in db.execute(
                select(Answer.id, Question.id, Question.body)
                .join(Question, Question.id == Answer.question_id).where(Answer.id.in_(ids))):
            out[aid] = (f"an answer to {_quote(body)}", f"/questions/{qid}")
    if ids := by_type.get(ModerationTargetType.seller_review):
        for rid, sid, store in db.execute(
                select(SellerReview.id, Seller.id, Seller.display_name)
                .join(Seller, Seller.id == SellerReview.seller_id)
                .where(SellerReview.id.in_(ids))):
            out[rid] = (f"a review of {store}", f"/sellers/{sid}#review-{rid}")
    # Inbox events (0076) carry no target type: their target is the conversation.
    conv_ids = {log.target_ref for log in logs
                if log.action == A.conversation and log.target_type is None and log.target_ref}
    if conv_ids:
        for cid, ref, subject in db.execute(
                select(Conversation.id, Conversation.reference, Conversation.subject)
                .where(Conversation.id.in_(conv_ids))):
            out[cid] = (f"{ref} · {subject[:60]}{'…' if len(subject) > 60 else ''}",
                        f"/admin/inbox?c={cid}")
    return out


def _quote(body: str) -> str:
    text = (body or "").split("\n")[0]
    return f"“{text[:60]}{'…' if len(text) > 60 else ''}”"


def _where(*, actor_id: uuid.UUID | None, system: bool, action: str | None,
           target_type: str | None, since: datetime | None, q: str | None):
    where = []
    if system:
        where.append(ModerationLog.moderator_id.is_(None))
    elif actor_id:
        where.append(ModerationLog.moderator_id == actor_id)
    if action:
        if action in GROUPS:
            where.append(ModerationLog.action.in_(GROUPS[action]))
        elif action == "system":
            where.append(ModerationLog.moderator_id.is_(None))
        else:
            where.append(ModerationLog.action == A(action))
    if target_type:
        where.append(ModerationLog.target_type == ModerationTargetType(target_type))
    if since is not None:
        where.append(ModerationLog.created_at >= since)
    if q and q.strip():
        like = f"%{q.strip()}%"
        where.append(or_(cast(ModerationLog.action, String).ilike(like),
                         cast(ModerationLog.target_ref, String).ilike(like),
                         ModerationLog.log_id.ilike(like), ModerationLog.notes.ilike(like),
                         User.display_name.ilike(like), User.username.ilike(like)))
    return where


def rows(db: Session, *, limit: int = 50, offset: int = 0, actor_id: uuid.UUID | None = None,
         system: bool = False, action: str | None = None, target_type: str | None = None,
         range_: str | None = None, q: str | None = None,
         now: datetime | None = None) -> tuple[list[Row], int]:
    now = now or datetime.now(MANILA)
    where = _where(actor_id=actor_id, system=system, action=action, target_type=target_type,
                   since=_since(range_, now), q=q)
    base = select(ModerationLog, User).outerjoin(User, User.id == ModerationLog.moderator_id)
    total = int(db.scalar(select(func.count()).select_from(
        base.where(*where).subquery())) or 0)
    found = db.execute(base.where(*where).order_by(ModerationLog.created_at.desc())
                       .limit(limit).offset(offset)).all()
    labels = _labels(db, [log for log, _ in found])
    out = []
    from app.services.report_service import report_link
    for log, actor in found:
        label, href = labels.get(log.target_ref, (None, None)) if log.target_ref else (None, None)
        context = log.context or {}
        outcome = context.get("resolution") if context.get("report_id") else None
        if context.get("price_observation_id"):
            outcome = context.get("outcome")
            href = "/admin/prices"
            label = label or "a price report"
        # MQA-005/016: a filed report, and every decision on one, opens that report.
        if log.action == A.report:
            href = report_link(log.id)
        elif context.get("report_id"):
            href = report_link(context["report_id"])
        out.append(Row(
            id=log.id, action=log.action.value, group=group_of(log.action),
            actor_id=actor.id if actor else None, actor=_name(actor),
            target_type=log.target_type.value if log.target_type else None,
            target_ref=str(log.target_ref) if log.target_ref else None,
            target_label=label, href=href,
            reason=log.reason.value if log.reason else None, notes=log.notes, at=log.created_at,
            outcome=outcome))
    return out, total


@dataclass(frozen=True)
class Summary:
    #: Today, in Manila: actions per type (Figma "Today by type"), and in all.
    today_total: int
    by_type: dict[str, int]
    #: Proof-of-purchase views this week: who opened whose evidence, newest first.
    receipt_views: list[dict]
    #: Today: actions per staff member, most first.
    team_today: list[dict]
    #: Everyone who appears in the log, for the Person menu.
    actors: list[dict]


def summary(db: Session, now: datetime | None = None) -> Summary:
    now = now or datetime.now(MANILA)
    today = _since("today", now)
    is_system = ModerationLog.moderator_id.is_(None)
    by_action = db.execute(select(ModerationLog.action, is_system, func.count())
                           .where(ModerationLog.created_at >= today)
                           .group_by(ModerationLog.action, is_system)).all()
    by_type = {"moderation": 0, "system": 0, "money": 0, "access": 0, "privacy": 0}
    for action, by_system, count in by_action:
        by_type["system" if by_system else group_of(action)] += int(count)
    views = db.execute(
        select(ModerationLog, User).outerjoin(User, User.id == ModerationLog.moderator_id)
        .where(ModerationLog.action == A.receipt_view,
               ModerationLog.created_at >= now - timedelta(days=7))
        .order_by(ModerationLog.created_at.desc()).limit(10)).all()
    labels = _labels(db, [log for log, _ in views])
    receipt_views = []
    for log, u in views:
        label, href = labels.get(log.target_ref, ("a review", None))
        receipt_views.append({"actor": _name(u), "target": label, "href": href,
                              "at": log.created_at})
    team = db.execute(select(User, func.count(ModerationLog.id))
                      .join(ModerationLog, ModerationLog.moderator_id == User.id)
                      .where(ModerationLog.created_at >= today)
                      .group_by(User.id).order_by(func.count(ModerationLog.id).desc()).limit(8)).all()
    recent = select(ModerationLog.moderator_id).where(
        ModerationLog.moderator_id.is_not(None),
        ModerationLog.created_at >= now - timedelta(days=90)).distinct()
    actors = db.execute(select(User).where(User.id.in_(recent))
                        .order_by(User.display_name).limit(40)).scalars().all()
    return Summary(
        today_total=sum(by_type.values()), by_type=by_type, receipt_views=receipt_views,
        team_today=[{"id": u.id, "name": _name(u), "count": int(n)} for u, n in team],
        actors=[{"id": u.id, "name": _name(u)} for u in actors])

"""Moderator view of community content reports (FR-9). RBAC=moderator.

Reports live in `moderation_logs` (action=report). This route reads that queue
and joins the minimum context a moderator needs to act — who reported, what was
reported, and how many separate people have flagged the same target.

Resolving is here too (owner §30, 2026-09-16). Before it, this was a screen a
moderator could read and not answer: every report ever filed stayed in the
queue, whatever anyone did about it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.comment import ReviewComment
from app.models.enums import MemberRole, ModerationAction, ModerationTargetType, ReportResolution
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review
from app.models.seller import SellerReview
from app.models.user import User
from app.schemas.referral import (
    QueueIntegrityChecks,
    QueueSignals,
    QueueVotingEvidence,
    TriageOut,
)
from app.schemas.report import ReportOut
from app.services import (
    notification_service,
    priority_triage,
    referral_service,
    report_explainer,
    report_service,
    seller_service,
)
from app.services.priority_tiers import TIER_RANK, Tier

router = APIRouter(prefix="/admin", tags=["admin: reports"],
                   dependencies=[Depends(require_staff)])


class ReportReporter(BaseModel):
    id: uuid.UUID
    display_name: str | None = None
    username: str | None = None
    trust_stage: int


class ReportTarget(BaseModel):
    """Enough of the reported item to triage without a second round-trip."""

    id: uuid.UUID
    title: str | None = None
    author_id: uuid.UUID | None = None
    is_published: bool = False
    #: Where the item is on the site: `/reviews/<id>` for a review,
    #: `/reviews/<review id>#comment-<id>` for a comment (QA-069). Null for a
    #: type with no page of its own, rather than a link that 404s.
    link: str | None = None
    # --- the reported content, beside the report (dev/QA sync 2026-09-29) ---
    #: The first ~280 characters of what was reported.
    excerpt: str | None = None
    author_username: str | None = None
    product_name: str | None = None
    star_rating: float | None = None
    verdict: str | None = None
    #: "published", "taken_down" (by staff) or "removed" (by its author, or a
    #: removed comment); "member" for a report on an account.
    state: str | None = None


class ReportEvidenceLine(BaseModel):
    label: str
    value: str
    link: str | None = None


class ReportExplanation(BaseModel):
    """Why this was reported, from stored fields only (report_explainer)."""

    summary: str
    signal: str | None = None
    signal_label: str | None = None
    evidence: list[ReportEvidenceLine] = Field(default_factory=list)
    evidence_stored: bool = True


#: The report types this queue can show the content of, and act on.
_CONTENT_TYPES = (ModerationTargetType.review, ModerationTargetType.comment,
                  ModerationTargetType.seller_review)


def _targets(db: Session, logs: list[ModerationLog]
             ) -> tuple[dict[tuple[ModerationTargetType, uuid.UUID], ReportTarget],
                        dict[uuid.UUID, int], dict]:
    """The reported reviews and comments, their report counts and escalation facts.

    One query per type, whatever the page size (no N+1).
    """
    refs: dict[ModerationTargetType, list[uuid.UUID]] = {t: [] for t in _CONTENT_TYPES}
    for log in logs:
        if log.target_type in refs and log.target_ref:
            refs[log.target_type].append(log.target_ref)
    targets: dict[tuple[ModerationTargetType, uuid.UUID], ReportTarget] = {}
    user_refs = [log.target_ref for log in logs
                 if log.target_type == ModerationTargetType.user and log.target_ref]
    if refs[ModerationTargetType.review]:
        reviews = list(db.scalars(select(Review).where(
            Review.id.in_(refs[ModerationTargetType.review]))))
        names = _usernames(db, {r.author_id for r in reviews if r.author_id})
        products = {p.id: p.canonical_name for p in db.scalars(select(Product).where(
            Product.id.in_({r.product_id for r in reviews if r.product_id})))}
        for review in reviews:
            targets[(ModerationTargetType.review, review.id)] = ReportTarget(
                id=review.id, title=review.title, author_id=review.author_id,
                is_published=review.published_at is not None,
                link=f"/reviews/{review.id}",
                excerpt=notification_service.excerpt(review.discussion or "", 280),
                author_username=names.get(review.author_id),
                product_name=products.get(review.product_id),
                star_rating=float(review.star_rating) if review.star_rating is not None
                else None,
                verdict=review.verdict.value if review.verdict else None,
                state=("removed" if review.is_removed
                       else "published" if review.published_at is not None
                       else "taken_down"))
    if user_refs:
        for member in db.scalars(select(User).where(User.id.in_(user_refs))):
            handle = member.username or str(member.id)
            targets[(ModerationTargetType.user, member.id)] = ReportTarget(
                id=member.id, title=f"Member @{handle}", author_id=member.id,
                is_published=True, link=f"/u/{handle}", author_username=member.username,
                state="member")
    if refs[ModerationTargetType.comment]:
        for comment in db.scalars(select(ReviewComment).where(
                ReviewComment.id.in_(refs[ModerationTargetType.comment]))):
            targets[(ModerationTargetType.comment, comment.id)] = ReportTarget(
                id=comment.id,
                title="Comment: " + notification_service.excerpt(comment.body, 90),
                author_id=comment.author_id, is_published=not comment.is_removed,
                link=f"/reviews/{comment.review_id}#comment-{comment.id}",
                excerpt=notification_service.excerpt(comment.body, 280),
                state="removed" if comment.is_removed else "published")
    if refs[ModerationTargetType.seller_review]:
        # QA-043: a seller review is reported from its store page.
        for sr in db.scalars(select(SellerReview).where(
                SellerReview.id.in_(refs[ModerationTargetType.seller_review]))):
            targets[(ModerationTargetType.seller_review, sr.id)] = ReportTarget(
                id=sr.id,
                title="Store review: " + notification_service.excerpt(
                    sr.title or sr.comment or "(no text)", 90),
                author_id=sr.reviewer_id, is_published=not sr.is_removed,
                link=f"/sellers/{sr.seller_id}#seller-review-{sr.id}")
    counts: dict[uuid.UUID, int] = {}
    facts: dict = {}
    for target_type, ids in refs.items():
        if not ids:
            continue
        counts.update(report_service.report_counts(db, target_type, ids))
        facts.update(report_service.report_facts_by_target(db, target_type, ids))
    return targets, counts, facts


def _usernames(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.username).where(User.id.in_(ids))).all())


def _explanations(db: Session, items: list[ReportItem],
                  logs: dict[uuid.UUID, ModerationLog]) -> None:
    """Attach report_explainer's account of each report, in place. One query
    for every review the stored evidence points at (the copied-text match)."""
    match_ids: dict[str, set[uuid.UUID]] = {"review": set(), "answer": set(), "comment": set()}
    for log in logs.values():
        evidence = (log.context or {}).get("evidence")
        if not isinstance(evidence, dict):
            continue
        if evidence.get("duplicate_of"):
            kind = str(evidence.get("matched_kind") or "review")
            try:
                match_ids.setdefault(kind, set()).add(uuid.UUID(str(evidence["duplicate_of"])))
            except ValueError:
                continue
        if evidence.get("matched_review"):            # a reused photo
            try:
                match_ids["review"].add(uuid.UUID(str(evidence["matched_review"])))
            except ValueError:
                continue
    # One query per kind the evidence points at; a title or an excerpt, and a link.
    matched: dict[str, tuple[str | None, str | None]] = {}
    if match_ids["review"]:
        matched.update({str(r.id): (r.title, f"/reviews/{r.id}") for r in db.scalars(
            select(Review).where(Review.id.in_(match_ids["review"])))})
    if match_ids["answer"]:
        from app.models.qa import Answer
        for a in db.scalars(select(Answer).where(Answer.id.in_(match_ids["answer"]))):
            matched[str(a.id)] = (notification_service.excerpt(a.body, 90),
                                  f"/questions/{a.question_id}")
    if match_ids["comment"]:
        from app.models.comment import ReviewComment
        for c in db.scalars(select(ReviewComment).where(
                ReviewComment.id.in_(match_ids["comment"]))):
            matched[str(c.id)] = (notification_service.excerpt(c.body, 90),
                                  f"/reviews/{c.review_id}#comment-{c.id}")
    for item in items:
        log = logs.get(item.report.id)
        if log is None:
            continue
        found = report_explainer.explain(
            origin=item.origin, reason=log.reason.value if log.reason else None,
            notes=log.notes, target_type=log.target_type.value if log.target_type else None,
            context=log.context, report_count=item.target_report_count,
            weighted=item.target_weighted_reports, escalated=item.escalated,
            urgent=item.urgent_reason, surge=item.report_surge, matched=matched)
        item.explanation = ReportExplanation(
            summary=found.summary, signal=found.signal, signal_label=found.signal_label,
            evidence=[ReportEvidenceLine(label=e.label, value=e.value, link=e.link)
                      for e in found.evidence],
            evidence_stored=found.evidence_stored)


class ReportReviewSignals(BaseModel):
    """MQA-003: a reported review's integrity checks, as its Review Queue card
    shows them (referral_service.review_queue_cards): the advisory signals, the
    voting facts behind them, the external checks (plagiarism, reverse image:
    "not_configured" until a provider is procured) and whether its photo was
    found reused on an earlier review."""

    signals: QueueSignals
    voting: QueueVotingEvidence | None = None
    integrity: QueueIntegrityChecks = Field(default_factory=QueueIntegrityChecks)
    edited_since_monetized: bool = False
    #: The review carries a photo, so the reused-photo check applies to it.
    has_photo: bool = False
    #: The System found its photo on an earlier review (a duplicate_image report).
    reused_photo: bool = False


class ReportItem(BaseModel):
    report: ReportOut
    reporter: ReportReporter | None = None
    target: ReportTarget | None = None
    # How many distinct reports this same target has attracted. One angry reader
    # is noise; five independent reports is a signal, and the moderator should
    # see the difference without running a query.
    target_report_count: int = 1
    #: §12: "user_reported" or "system_detected".
    origin: str = "user_reported"
    #: §12: the target's trust-weighted sum of open user reports...
    target_weighted_reports: float = 0.0
    #: ...and whether it has escalated: the one threshold, an urgent reason
    #: (safety, personal information), or a burst against its own baseline.
    escalated: bool = False
    urgent_reason: bool = False
    report_surge: bool = False
    #: The admin priority tier of the reported item (dev note 2026-09-26).
    #: Open reports only; a triage label, never a membership decision.
    triage: TriageOut | None = None
    #: Why it was reported, written from stored fields (dev/QA sync 2026-09-29).
    explanation: ReportExplanation | None = None
    #: A reported review's integrity signals (MQA-003); null for other types.
    review_signals: ReportReviewSignals | None = None


class ReportQueueResponse(BaseModel):
    items: list[ReportItem]
    #: Every report matching the filters, not just this page (MQA-045).
    total: int
    #: Distinct reported items among those reports: "6 reports on 4 items".
    items_total: int = 0
    #: Open queue only: how many listed reports sit in each tier.
    by_tier: dict[str, int] = Field(default_factory=dict)


@router.get("/reports", response_model=ReportQueueResponse,
            summary="Administrator queue: community content reports")
def report_queue(
    db: Session = Depends(get_db),
    target_type: ModerationTargetType | None = Query(
        default=None, description="Filter to one content type."
    ),
    status: Literal["open", "escalated", "resolved", "all"] = Query(
        default="open",
        description="Open reports (the default), resolved ones, or both.",
    ),
    tier: Tier | None = Query(None, description="Open queue: one admin priority tier."),
    sort: Literal["escalation", "tier", "newest", "oldest"] = Query(
        "escalation",
        description="Open queue order: escalation (default), tier, newest, oldest."),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ReportQueueResponse:
    limit = min(limit, 100)
    if status == "open":
        # §12: open reports are ordered by escalation, not arrival. The open
        # queue is small, so it is ranked whole and then paged.
        logs = report_service.list_reports(
            db, target_type=target_type, status=status, limit=1000, offset=0)
    else:
        logs = report_service.list_reports(
            db, target_type=target_type, status=status, limit=limit, offset=offset
        )

    # Batch-load reporters and reviewed targets — one query each, no N+1.
    reporter_ids = {log.reporter_id for log in logs if log.reporter_id}
    reporters: dict[uuid.UUID, User] = {}
    if reporter_ids:
        reporters = {
            u.id: u
            for u in db.scalars(select(User).where(User.id.in_(reporter_ids))).all()
        }

    targets, counts, facts = _targets(db, logs)

    items: list[ReportItem] = []
    for log in logs:
        reporter = reporters.get(log.reporter_id) if log.reporter_id else None
        target = targets.get((log.target_type, log.target_ref)) if log.target_ref else None
        items.append(
            ReportItem(
                report=ReportOut.model_validate(log),
                reporter=(
                    ReportReporter(
                        id=reporter.id,
                        display_name=reporter.display_name,
                        username=reporter.username,
                        trust_stage=reporter.trust_stage,
                    )
                    if reporter
                    else None
                ),
                target=target,
                target_report_count=(
                    counts.get(log.target_ref, 1) if log.target_ref else 1
                ),
                **_escalation(log, facts),
            )
        )

    _explanations(db, items, {log.id: log for log in logs})

    if status == "open":
        triaged = {(t_type, ref): tri for (_, t_type, ref), tri in priority_triage.assess(
            db, priority_triage.report_targets(db)).items()}
        for item in items:
            tri = triaged.get((item.report.target_type.value, item.report.target_ref)) \
                if item.report.target_type and item.report.target_ref else None
            item.triage = referral_service.triage_out(tri) if tri is not None else None
        by_tier = {t.value: 0 for t in Tier}
        for item in items:
            if item.triage is not None:
                by_tier[item.triage.tier] += 1
        if tier is not None:
            items = [i for i in items if i.triage is not None and i.triage.tier == tier.value]
        if sort == "tier":
            items.sort(key=lambda i: (
                TIER_RANK[Tier(i.triage.tier)] if i.triage else TIER_RANK[Tier.neutral],
                i.triage.clock_started_at if i.triage else i.report.created_at,
                i.report.created_at))
        elif sort == "oldest":
            items.sort(key=lambda i: i.report.created_at)
        elif sort == "newest":
            # MQA-001: a report just filed, at the top.
            items.sort(key=lambda i: (i.report.created_at, str(i.report.id)), reverse=True)
        else:
            items.sort(key=lambda item: (not item.escalated, not item.urgent_reason,
                                         not item.report_surge,
                                         -item.target_weighted_reports))
        # The open queue is ranked whole, so its totals are the ranked list's
        # own - after the tier filter, as the rows on screen are.
        on = {(i.report.target_type, i.report.target_ref) for i in items
              if i.report.target_ref}
        page = items[offset:offset + limit]
        _review_signals(db, page)
        return ReportQueueResponse(items=page, total=len(items),
                                   items_total=len(on), by_tier=by_tier)
    # Paged in SQL: the total is a count of every match, never this page's length.
    _review_signals(db, items)
    counts = report_service.count_reports(db, target_type=target_type, status=status)
    return ReportQueueResponse(items=items, total=counts.reports, items_total=counts.items)


def _review_signals(db: Session, items: list[ReportItem]) -> None:
    """Attach each reported review's queue signals (MQA-003), in place, for
    the page being returned only. Two batched reads beyond the queue's own."""
    from app.services.duplicate_images import SIGNAL as REUSED_PHOTO
    ids = {i.report.target_ref for i in items
           if i.report.target_type == ModerationTargetType.review and i.report.target_ref
           and i.target is not None}
    if not ids:
        return
    cards = referral_service.review_queue_cards(db, ids)
    reused = set(db.scalars(select(ModerationLog.target_ref).where(
        ModerationLog.action == ModerationAction.report,
        ModerationLog.target_type == ModerationTargetType.review,
        ModerationLog.target_ref.in_(ids),
        ModerationLog.reporter_id.is_(None),
        ModerationLog.context["signal"].astext == REUSED_PHOTO)))
    for item in items:
        card = cards.get(item.report.target_ref) \
            if item.report.target_type == ModerationTargetType.review else None
        if card is None:
            continue
        item.review_signals = ReportReviewSignals(
            signals=card.signals, voting=card.voting, integrity=card.integrity,
            edited_since_monetized=bool(card.edited_since_monetized),
            has_photo=bool(card.review.photo_url),
            reused_photo=item.report.target_ref in reused)


def _escalation(log: ModerationLog, facts: dict) -> dict:
    from app.services.moderation_priority import REPORT_ESCALATION_THRESHOLD, URGENT_REASONS
    fact = facts.get(log.target_ref) if log.target_ref else None
    weighted = fact.weighted if fact is not None else 0.0
    urgent = log.reason in URGENT_REASONS
    surge = bool(fact.surge) if fact is not None else False
    origin = ("system_detected" if log.reporter_id is None else "user_reported")
    return {
        "origin": origin,
        "target_weighted_reports": weighted,
        "urgent_reason": urgent,
        "report_surge": surge,
        "escalated": urgent or weighted >= REPORT_ESCALATION_THRESHOLD or surge,
    }


@router.post("/integrity/sweep", summary="File automated integrity signals as reports")
def run_integrity_sweep(db: Session = Depends(get_db)) -> dict:
    """§12: fraud/collusion signals enter the same queue, labelled SYSTEM_DETECTED."""
    from app.services.integrity_sweep import sweep
    return sweep(db)


class InvestigationIn(BaseModel):
    under_investigation: bool
    note: str | None = Field(default=None, max_length=1000)


@router.put("/users/{user_id}/investigation",
            summary="Mark or clear an account as under investigation (halves vote weight)")
def set_investigation(user_id: uuid.UUID, payload: InvestigationIn,
                      db: Session = Depends(get_db),
                      moderator: User = Depends(get_current_user)) -> dict:
    """Business Rules §11: an unconfirmed, unproven investigation halves vote
    weight (probation still zeroes it). The trigger that sets or clears it is
    deliberately open in the Full Record, so only a moderator's explicit,
    audited action does today."""
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.", code="user_not_found")
    if target.id == moderator.id:
        raise AppError("You cannot change your own investigation state.",
                       code="self_decision", status_code=422, title="Invalid decision")
    target.is_under_investigation = payload.under_investigation
    # §11 halves their votes as evidence; the members they voted for are
    # re-evaluated now, and again when the investigation is cleared.
    from app.services.trust_service import recompute_authors_voted_on_by
    recompute_authors_voted_on_by(db, target.id)
    from app.models.enums import ModerationAction
    db.add(ModerationLog(
        target_type=ModerationTargetType.user, target_ref=target.id, moderator_id=moderator.id,
        action=(ModerationAction.investigation_set if payload.under_investigation
                else ModerationAction.investigation_clear),
        notes=payload.note))
    db.commit()
    return {"user_id": str(target.id), "under_investigation": target.is_under_investigation}


class ReportDecision(BaseModel):
    """A moderator's answer to one report."""

    resolution: ReportResolution
    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Why. Recorded in the audit log; not shown to the reporter.",
    )


@router.post("/reports/{report_id}/decision", response_model=ReportItem,
             summary="Resolve a report: dismiss, remove, restore or escalate")
def decide_report(
    report_id: uuid.UUID,
    payload: ReportDecision,
    db: Session = Depends(get_db),
    moderator: User = Depends(get_current_user),
) -> ReportItem:
    """Close a report, and carry out the content decision it implies.

    The two content outcomes are not recorded here and performed elsewhere —
    they are performed, through the same services the review routes use, so an
    unpublish from this screen is indistinguishable from any other unpublish:
    same audit entry, same author notification, same return to the queue.

      dismissed          the content stands. Nothing is done to it.
      content_removed    the reported review is unpublished (taken down; its
                         earning state is left alone, as `unpublish` defines).
      content_restored   the reported review is published again.
      escalated          nothing is done to the content; the report is marked
                         for a senior decision and leaves the open queue.

    The content action runs first and commits; the report is closed after it.
    So a resolution that cannot be carried out — a review already down, a target
    with no publish state — leaves the report OPEN rather than closing it over
    something that did not happen. The reverse order would be worse: a closed
    report over live content nobody is looking at any more.
    """
    report = report_service.get_report_or_404(db, report_id)
    senior = moderator.role == MemberRole.super_admin
    # MQA-005: an escalated report belongs to a Super Admin. Refuse before any
    # content action runs, so nothing is taken down over a refused decision.
    if report.resolution == ReportResolution.escalated and not senior:
        raise AppError("This report was escalated to a Super Admin, who decides it.",
                       code="report_escalated", status_code=403, title="Escalated")

    if payload.resolution in _CONTENT_ACTIONS:
        _apply_content_decision(db, report, payload, moderator)

    resolved = report_service.resolve_report(
        db, report, moderator_id=moderator.id,
        resolution=payload.resolution, notes=payload.notes,
        senior=senior,
    )
    return _item_for(db, resolved)


def _report_reason(report: ModerationLog) -> str:
    """The take-down reason when staff act on a report without notes: the
    report's own category, which is what the content was taken down for."""
    if report.reason is None:
        return "Taken down on a member's report."
    return f"Taken down on a member's report: {report.reason.value.replace('_', ' ')}."


#: The two outcomes that touch the content itself.
_CONTENT_ACTIONS = frozenset(
    {ReportResolution.content_removed, ReportResolution.content_restored}
)


def _apply_content_decision(db: Session, report: ModerationLog,
                            payload: ReportDecision, moderator: User) -> None:
    """Unpublish or republish the reported review or comment, or refuse.

    Reviews and comments (QA-069) can be acted on this way — answers,
    questions, sellers and users are reportable but have no state this route
    can move. A report on one of those can still be dismissed or escalated,
    which is the honest set of answers rather than a button that quietly does
    nothing.
    """
    if report.target_ref is None or report.target_type not in _CONTENT_TYPES:
        raise AppError(
            "Only a reported review, comment or store review can be removed or restored here.",
            code="report_target_not_actionable",
            status_code=422,
            title="Unprocessable content",
        )
    if report.target_type == ModerationTargetType.comment:
        _decide_comment(db, report, payload, moderator)
        return
    if report.target_type == ModerationTargetType.seller_review:
        _decide_seller_review(db, report, payload, moderator)
        return
    review = db.get(Review, report.target_ref)
    if review is None:
        raise NotFoundError("The reported review no longer exists.",
                            code="review_not_found")

    if payload.resolution is ReportResolution.content_removed:
        referral_service.unpublish(db, review, moderator.id,
                                   (payload.notes or "").strip() or _report_reason(report))
    else:
        # Visibility only. Earnings are decided in the earn_eligible queue.
        referral_service.restore(db, review, moderator.id)


def _decide_comment(db: Session, report: ModerationLog, payload: ReportDecision,
                    moderator: User) -> None:
    """Remove or restore a reported comment — the same soft removal an author's
    own delete uses, so the thread keeps its shape — with an audit row."""
    comment = db.get(ReviewComment, report.target_ref)
    if comment is None:
        raise NotFoundError("The reported comment no longer exists.",
                            code="comment_not_found")
    remove = payload.resolution is ReportResolution.content_removed
    if comment.is_removed == remove:
        raise AppError(
            "That comment is already removed." if remove else "That comment is not removed.",
            code="comment_already_in_state", status_code=409, title="Conflicting state")
    comment.is_removed = remove
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=ModerationTargetType.comment, target_ref=comment.id,
        moderator_id=moderator.id,
        action=ModerationAction.remove if remove else ModerationAction.restore,
        notes=payload.notes, context={"report_id": str(report.id)}))
    db.commit()


def _decide_seller_review(db: Session, report: ModerationLog, payload: ReportDecision,
                          moderator: User) -> None:
    """QA-043: remove a reported store review the way the store page's own
    moderator control does (off the page and out of the store's numbers), or
    put it back."""
    review = db.get(SellerReview, report.target_ref)
    if review is None:
        raise NotFoundError("The reported store review no longer exists.",
                            code="seller_review_not_found")
    if payload.resolution is ReportResolution.content_removed:
        seller_service.remove_seller_review(db, review.id, moderator, payload.notes)
        return
    if not review.is_removed:
        raise AppError("That store review is not removed.",
                       code="seller_review_already_visible", status_code=409,
                       title="Conflicting state")
    review.is_removed = False
    review.removed_at = None
    review.removed_by_id = None
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=ModerationTargetType.seller_review, target_ref=review.id,
        moderator_id=moderator.id, action=ModerationAction.restore,
        notes=payload.notes, context={"report_id": str(report.id)}))
    db.commit()


def _item_for(db: Session, log: ModerationLog) -> ReportItem:
    """One report, with the same context the queue serves."""
    reporter = db.get(User, log.reporter_id) if log.reporter_id else None
    targets, counts, facts = _targets(db, [log])
    target = targets.get((log.target_type, log.target_ref)) if log.target_ref else None
    item = ReportItem(
        report=ReportOut.model_validate(log),
        reporter=(
            ReportReporter(
                id=reporter.id,
                display_name=reporter.display_name,
                username=reporter.username,
                trust_stage=reporter.trust_stage,
            )
            if reporter
            else None
        ),
        target=target,
        target_report_count=counts.get(log.target_ref, 1) if log.target_ref else 1,
        **_escalation(log, facts),
    )
    _explanations(db, [item], {log.id: log})
    return item

"""Community content reports (FR-9).

Reports are stored as `moderation_logs` rows with `action=report` and the
reporting user in `reporter_id`. That table is deliberately the single audit
surface (see models/moderation.py — the 15-table Data Dictionary constraint), so
a report is an audit entry a moderator later resolves rather than a row in a
separate reports table.

Two rules keep the queue meaningful:

- You cannot report your own content. Self-reports carry no signal and would let
  an author manufacture "contested" status on their own review.
- One open report per (reporter, target). Re-submitting is idempotent and returns
  the existing report rather than letting one user inflate the count on a review
  they dislike.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import (
    ModerationAction,
    ModerationReason,
    ModerationTargetType,
    ReportResolution,
    ReportSource,
)
from app.models.moderation import ModerationLog
from app.models.user import User


def _existing_report(
    db: Session,
    reporter_id: uuid.UUID,
    target_type: ModerationTargetType,
    target_ref: uuid.UUID,
) -> ModerationLog | None:
    return db.scalars(
        select(ModerationLog).where(
            ModerationLog.action == ModerationAction.report,
            ModerationLog.reporter_id == reporter_id,
            ModerationLog.target_type == target_type,
            ModerationLog.target_ref == target_ref,
            # OPEN, which is what the rule above always said and what the table
            # could not express until reports could be closed (migration 0049).
            # A reader whose report was dealt with may report the same target
            # again if it goes wrong again; a reader whose report is still
            # waiting may not file it twice.
            ModerationLog.resolution.is_(None),
        )
    ).first()


#: §12: "a report resolved as unfounded only reduces that reporter's future
#: weight after a PATTERN of unfounded reports, not a single miss".
UNFOUNDED_PATTERN_MIN = 3
UNFOUNDED_PATTERN_RATIO = 0.5
UNFOUNDED_SEVERE_MIN = 6
UNFOUNDED_SEVERE_RATIO = 0.75

#: §12 velocity: a burst is at least this many reports in the last day...
SURGE_MIN_REPORTS = 3
#: ...and this many times the review's own daily rate over the prior 30 days.
SURGE_FACTOR = 3.0
SURGE_WINDOW = timedelta(hours=24)
SURGE_BASELINE = timedelta(days=30)


def unfounded_penalty(dismissed: int, resolved: int) -> float:
    """Multiplier on a reporter's weight from their track record. Pure.

    One unfounded report never counts against anyone: good-faith reporting
    must not be discouraged. Only a pattern does.
    """
    if resolved <= 0:
        return 1.0
    ratio = dismissed / resolved
    if dismissed >= UNFOUNDED_SEVERE_MIN and ratio >= UNFOUNDED_SEVERE_RATIO:
        return 0.25
    if dismissed >= UNFOUNDED_PATTERN_MIN and ratio >= UNFOUNDED_PATTERN_RATIO:
        return 0.5
    return 1.0


def reporter_weight(db: Session, reporter: User) -> tuple[float, float]:
    """(weight, penalty) for a new report: the gate-vote weight (§12 reuses it)
    times the unfounded-pattern penalty."""
    from app.services.trust import weight_of
    rows = db.execute(
        select(ModerationLog.resolution, func.count(ModerationLog.id))
        .where(ModerationLog.action == ModerationAction.report,
               ModerationLog.reporter_id == reporter.id,
               ModerationLog.resolution.is_not(None))
        .group_by(ModerationLog.resolution)
    ).all()
    resolved = sum(int(n) for _, n in rows)
    dismissed = sum(int(n) for res, n in rows if res == ReportResolution.dismissed)
    penalty = unfounded_penalty(dismissed, resolved)
    return round(weight_of(reporter) * penalty, 4), penalty


def file_system_report(db: Session, *, target_type: ModerationTargetType,
                       target_ref: uuid.UUID, signal: str,
                       reason: ModerationReason = ModerationReason.other,
                       severity: float = 1.0) -> tuple[ModerationLog, bool]:
    """An automated fraud/collusion signal, filed into the SAME queue as human
    reports and labelled SYSTEM_DETECTED (§12). One open system report per
    target and signal; the caller commits."""
    existing = db.scalar(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.report,
        ModerationLog.target_type == target_type,
        ModerationLog.target_ref == target_ref,
        ModerationLog.reporter_id.is_(None),
        ModerationLog.resolution.is_(None),
        ModerationLog.context["signal"].astext == signal,
    ))
    if existing is not None:
        return existing, False
    log = ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", target_type=target_type,
        target_ref=target_ref, reporter_id=None, action=ModerationAction.report,
        reason=reason, report_source=ReportSource.system_detected,
        notes=f"Automated check: {signal.replace('_', ' ')}",
        context={"signal": signal, "reporter_weight": severity, "system": True},
    )
    db.add(log)
    return log, True


def file_report(
    db: Session,
    *,
    reporter_id: uuid.UUID,
    author_id: uuid.UUID | None,
    target_type: ModerationTargetType,
    target_ref: uuid.UUID,
    reason: ModerationReason,
    notes: str | None = None,
    evidence_url: str | None = None,
) -> tuple[ModerationLog, bool]:
    """File a report. Returns (log, created) — `created` is False on a repeat.

    The caller supplies `author_id` so the self-report check happens here rather
    than being re-implemented per content type.
    """
    if author_id is not None and author_id == reporter_id:
        raise AppError(
            "You cannot report your own content.",
            code="self_report",
            status_code=422,
            title="Invalid report",
        )

    existing = _existing_report(db, reporter_id, target_type, target_ref)
    if existing is not None:
        return existing, False

    reporter = db.get(User, reporter_id)
    weight, penalty = reporter_weight(db, reporter) if reporter is not None else (0.0, 1.0)
    log = ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=target_type,
        target_ref=target_ref,
        reporter_id=reporter_id,
        action=ModerationAction.report,
        reason=reason,
        notes=notes,
        evidence_url=evidence_url,
        # §12: labelled by origin, and weighted like a vote toward "escalate".
        # The weight is kept on the row so the escalation stays auditable when
        # the reporter's trust later moves.
        report_source=ReportSource.user_reported,
        context={"reporter_weight": weight, "unfounded_penalty": penalty},
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log, True


def list_reports(
    db: Session,
    *,
    target_type: ModerationTargetType | None = None,
    status: str = "open",
    limit: int = 50,
    offset: int = 0,
) -> list[ModerationLog]:
    """The moderator queue of filed reports, newest first.

    `status` is "open" (the default), "escalated", "resolved" or "all". Open is
    the default because the queue is a to-do list: before reports could be closed
    it showed every report ever filed, so work already done came back round for
    ever. An escalated report is neither open nor resolved (MQA-005): it waits
    for a Super Admin under its own status, where it stays findable.
    """
    stmt = _reports_where(select(ModerationLog), target_type=target_type, status=status)
    stmt = (stmt.order_by(ModerationLog.created_at.desc(), ModerationLog.id.desc())
            .limit(limit).offset(offset))
    return list(db.scalars(stmt).all())


def _reports_where(stmt, *, target_type: ModerationTargetType | None, status: str):
    """The one definition of "the reports with this status", shared by the list
    and by every count of it, so a count can never disagree with the list."""
    stmt = stmt.where(ModerationLog.action == ModerationAction.report)
    if target_type is not None:
        stmt = stmt.where(ModerationLog.target_type == target_type)
    if status == "open":
        stmt = stmt.where(ModerationLog.resolution.is_(None))
    elif status == "escalated":
        stmt = stmt.where(ModerationLog.resolution == ReportResolution.escalated)
    elif status == "resolved":
        stmt = stmt.where(ModerationLog.resolution.is_not(None),
                          ModerationLog.resolution != ReportResolution.escalated)
    return stmt


@dataclass(frozen=True)
class ReportCounts:
    #: Report rows - what the Reports view lists, one row per report.
    reports: int
    #: Distinct reported items among them (one review reported three times is 1).
    items: int


def count_reports(db: Session, *, target_type: ModerationTargetType | None = None,
                  status: str = "open") -> ReportCounts:
    """How many reports have this status, and on how many items (MQA-045).

    The Overview said "Open reports 4" while the Reports tab said 6: one counted
    reported items, the other report rows from a 50-row page. Both now read this,
    and both numbers are shown under their own names.
    """
    row = db.execute(_reports_where(
        select(func.count(ModerationLog.id),
               func.count(func.distinct(case(
                   (ModerationLog.target_ref.is_not(None),
                    func.concat(ModerationLog.target_type, ":", ModerationLog.target_ref)),
                   else_=None)))),
        target_type=target_type, status=status)).one()
    return ReportCounts(reports=int(row[0] or 0), items=int(row[1] or 0))


def get_report_or_404(db: Session, report_id: uuid.UUID) -> ModerationLog:
    """One filed report. A log row that is not a report is not found."""
    log = db.get(ModerationLog, report_id)
    if log is None or log.action != ModerationAction.report:
        raise NotFoundError("Report not found.", code="report_not_found")
    return log


def resolve_report(
    db: Session,
    report: ModerationLog,
    *,
    moderator_id: uuid.UUID,
    resolution: ReportResolution,
    notes: str | None = None,
    senior: bool = False,
) -> ModerationLog:
    """Close a report, and audit the closing as its own entry.

    An ESCALATED report (MQA-005) is waiting for a Super Admin: only a `senior`
    caller may give it its final outcome, and it cannot be escalated twice.

    Two rows on purpose. The report row records THAT it was resolved, so the
    queue stops offering it; the new row records WHO closed it and how, in the
    same table every other moderator action is written to — so "what did this
    moderator do last week" is still one query. Whatever was done to the
    content itself (unpublishing, restoring) is audited by the service that did
    it, and this never pretends to have done it.

    Resolving an already-resolved report is refused rather than silently
    overwritten: two moderators reaching the same report should collide loudly.
    """
    if report.resolution == ReportResolution.escalated:
        if resolution == ReportResolution.escalated:
            raise AppError("That report is already escalated.", code="report_already_escalated",
                           status_code=409, title="Conflicting state")
        if not senior:
            raise AppError("This report was escalated to a Super Admin, who decides it.",
                           code="report_escalated", status_code=403, title="Escalated")
    elif report.resolution is not None:
        raise AppError(
            "That report has already been resolved.",
            code="report_already_resolved",
            status_code=409,
            title="Conflicting state",
        )

    report.resolution = resolution
    report.resolved_at = datetime.now(UTC)
    report.resolved_by = moderator_id
    # A dismissed vote-concentration hold releases the promotion it held
    # (ADR-016). Recompute the member now: waiting for their next vote or the
    # nightly sweep, which skips anyone inactive for 90 days, could leave a
    # released member held indefinitely (QA, 2026-09-29).
    from app.services.trust_service import CONCENTRATION_SIGNAL, recompute_user_trust
    if (resolution == ReportResolution.dismissed
            and report.target_type == ModerationTargetType.user
            and report.reporter_id is None
            and (report.context or {}).get("signal") == CONCENTRATION_SIGNAL
            and report.target_ref is not None):
        recompute_user_trust(db, report.target_ref)

    db.add(ModerationLog(
        target_type=report.target_type,
        target_ref=report.target_ref,
        moderator_id=moderator_id,
        action=_RESOLUTION_AUDIT_ACTION[resolution],
        notes=notes,
        context={"report_id": str(report.id), "resolution": resolution.value},
    ))
    if resolution == ReportResolution.escalated:
        _tell_super_admins(db, report, moderator_id, notes)
    db.commit()
    db.refresh(report)
    return report


def report_link(report_id: uuid.UUID | str, status: str = "all") -> str:
    """The Reports view opened on one report (Review Queue › Reports)."""
    return f"/admin/review-queue?tab=report&rstatus={status}&report={report_id}"


def _tell_super_admins(db: Session, report: ModerationLog, moderator_id: uuid.UUID,
                       notes: str | None) -> None:
    """MQA-005: an escalation has an owner. Every Super Admin but the one who
    escalated gets a notice that opens the report under Escalated."""
    from app.models.enums import MemberRole
    from app.models.user import User
    from app.services.notification_service import notify

    who = db.get(User, moderator_id)
    by = None
    if who is not None:
        by = who.display_name or (f"@{who.username}" if who.username else None)
    body = (f"{by} escalated it" if by else "Escalated") + (f": {notes}" if notes else ".")
    for admin_id in db.scalars(select(User.id).where(User.role == MemberRole.super_admin,
                                                     User.id != moderator_id)):
        notify(db, admin_id, "report_escalated", "A report was escalated to you",
               body=body, link=report_link(report.id, "escalated"))


#: Which audit action each outcome writes. `approve` for a dismissal reads oddly
#: at first glance and is exactly right: the moderator looked at the content and
#: let it stand.
_RESOLUTION_AUDIT_ACTION = {
    ReportResolution.dismissed: ModerationAction.approve,
    ReportResolution.content_removed: ModerationAction.remove,
    ReportResolution.content_restored: ModerationAction.restore,
    ReportResolution.escalated: ModerationAction.escalate,
}


def report_counts(
    db: Session, target_type: ModerationTargetType, target_refs: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """How many distinct reports each target has, for badging the moderator queue.

    Every report ever filed, resolved or not. Deliberate: the badge answers "how
    contested has this been", which a dismissal does not undo, and the priority
    policy reads the same counts — narrowing them to open reports would silently
    re-score the whole queue. Whether a dismissed report should stop contributing
    to priority is a policy question for the owner, not a change to sneak in with
    a UI control.
    """
    if not target_refs:
        return {}
    rows = db.execute(
        select(ModerationLog.target_ref, func.count(ModerationLog.id))
        .where(
            ModerationLog.action == ModerationAction.report,
            ModerationLog.target_type == target_type,
            ModerationLog.target_ref.in_(target_refs),
        )
        .group_by(ModerationLog.target_ref)
    ).all()
    return {row[0]: row[1] for row in rows}


@dataclass(frozen=True)
class ReportFacts:
    """The only report information the priority policy is allowed to see: how
    many people flagged a target and which enum reasons they picked. Never the
    notes, the evidence URLs, or who reported."""

    count: int
    reasons: frozenset[ModerationReason]
    #: §12: sum of OPEN user reports' reporter weights (never who reported).
    weighted: float = 0.0
    #: A burst against this target's own baseline (§12 velocity).
    surge: bool = False
    #: Open SYSTEM_DETECTED reports.
    system: int = 0
    #: Open USER_REPORTED reports.
    user_open: int = 0


#: Returned for a target that has no reports, so callers can index unconditionally.
NO_REPORTS = ReportFacts(count=0, reasons=frozenset())


def is_surge(recent: int, prior: int) -> bool:
    """Pure: `recent` reports in the last day against `prior` over the 30 before."""
    baseline_daily = prior / (SURGE_BASELINE / SURGE_WINDOW)
    return recent >= SURGE_MIN_REPORTS and recent >= SURGE_FACTOR * baseline_daily + 1

_QUERY_CHUNK_SIZE = 500


def _chunks(values: Collection[uuid.UUID]) -> Iterator[tuple[uuid.UUID, ...]]:
    items = tuple(dict.fromkeys(values))
    for start in range(0, len(items), _QUERY_CHUNK_SIZE):
        yield items[start : start + _QUERY_CHUNK_SIZE]


def report_facts_by_target(
    db: Session,
    target_type: ModerationTargetType,
    target_refs: Collection[uuid.UUID],
) -> dict[uuid.UUID, ReportFacts]:
    """Batch the report count and reason set for a bounded set of targets.

    Two grouped queries over ``moderation_logs`` (action=report) — one counting
    the distinct report rows, one collecting the distinct enum reasons. Targets
    with no reports are simply absent from the result; use :data:`NO_REPORTS`
    as the default. Nothing here loads a note, an evidence URL, or a
    ``reporter_id``.
    """
    refs = list(dict.fromkeys(target_refs))
    if not refs:
        return {}

    counts: dict[uuid.UUID, int] = {}
    reasons: dict[uuid.UUID, set[ModerationReason]] = {}
    for chunk in _chunks(refs):
        count_rows = db.execute(
            select(ModerationLog.target_ref, func.count(ModerationLog.id))
            .where(
                ModerationLog.action == ModerationAction.report,
                ModerationLog.target_type == target_type,
                ModerationLog.target_ref.in_(chunk),
            )
            .group_by(ModerationLog.target_ref)
        ).all()
        counts.update((target_ref, int(count)) for target_ref, count in count_rows)

        reason_rows = db.execute(
            select(ModerationLog.target_ref, ModerationLog.reason)
            .where(
                ModerationLog.action == ModerationAction.report,
                ModerationLog.target_type == target_type,
                ModerationLog.target_ref.in_(chunk),
                ModerationLog.reason.is_not(None),
            )
            .distinct()
        ).all()
        for target_ref, reason in reason_rows:
            reasons.setdefault(target_ref, set()).add(reason)

    weighted: dict[uuid.UUID, float] = {}
    system: dict[uuid.UUID, int] = {}
    user_open: dict[uuid.UUID, int] = {}
    recent: dict[uuid.UUID, int] = {}
    prior: dict[uuid.UUID, int] = {}
    now = datetime.now(UTC)
    for chunk in _chunks(refs):
        timed_rows = db.execute(
            select(ModerationLog.target_ref, ModerationLog.created_at)
            .where(
                ModerationLog.action == ModerationAction.report,
                ModerationLog.target_type == target_type,
                ModerationLog.target_ref.in_(chunk),
                ModerationLog.created_at >= now - SURGE_WINDOW - SURGE_BASELINE,
            )
        ).all()
        for target_ref, created_at in timed_rows:
            created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
            if now - created <= SURGE_WINDOW:
                recent[target_ref] = recent.get(target_ref, 0) + 1
            elif now - created <= SURGE_WINDOW + SURGE_BASELINE:
                prior[target_ref] = prior.get(target_ref, 0) + 1
        open_rows = db.execute(
            select(ModerationLog.target_ref, ModerationLog.reporter_id, ModerationLog.context)
            .where(
                ModerationLog.action == ModerationAction.report,
                ModerationLog.target_type == target_type,
                ModerationLog.target_ref.in_(chunk),
                ModerationLog.resolution.is_(None),
            )
        ).all()
        # Reports filed before 0050 carry no stored weight. They are weighed by
        # their reporter's CURRENT trust (one batched read) rather than counted
        # as 1.0 — a brand-new account's old report must not escalate alone.
        unweighed = {reporter_id for _, reporter_id, context in open_rows
                     if reporter_id is not None
                     and not (isinstance(context, dict) and "reporter_weight" in context)}
        current: dict[uuid.UUID, float] = {}
        if unweighed:
            from app.services.trust import weight_of
            current = {u.id: weight_of(u)
                       for u in db.scalars(select(User).where(User.id.in_(unweighed)))}
        for target_ref, reporter_id, context in open_rows:
            if reporter_id is None:
                system[target_ref] = system.get(target_ref, 0) + 1
                continue
            user_open[target_ref] = user_open.get(target_ref, 0) + 1
            raw = (context or {}).get("reporter_weight") if isinstance(context, dict) else None
            weight = float(raw) if raw is not None else current.get(reporter_id, 0.0)
            weighted[target_ref] = weighted.get(target_ref, 0.0) + weight

    return {
        target_ref: ReportFacts(
            count=count,
            reasons=frozenset(reasons.get(target_ref, ())),
            weighted=round(weighted.get(target_ref, 0.0), 4),
            surge=is_surge(recent.get(target_ref, 0), prior.get(target_ref, 0)),
            system=system.get(target_ref, 0),
            user_open=user_open.get(target_ref, 0),
        )
        for target_ref, count in counts.items()
    }

"""Read-only lists the admin console's navigation needs.

Two sidebar items in the approved design — Activity Log and Reviewers — had no
API behind them, so they were rendered as dead controls. These are the smallest
endpoints that make them work: both are read-only, both are moderator-gated by
the router dependency, and neither adds a new concept to the domain.

Nothing here writes. Actions on reviews and payouts already have their own
routes and are not duplicated.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.security import is_super_admin, require_staff, require_super_admin
from app.db.session import get_db
from app.models.enums import MemberRole
from app.models.review import Review
from app.models.user import User
from app.schemas.product import ProductCanonicalize, ProductOut
from app.schemas.urls import web_url_or_none
from app.services import product_admin_service, product_catalogue_service, product_queue_service

router = APIRouter(prefix="/admin", tags=["admin: console"],
                   dependencies=[Depends(require_staff)])


class ActivityRow(BaseModel):
    id: uuid.UUID
    action: str
    actor: str | None
    target_type: str | None
    #: Always a string. `moderation_logs.target_ref` is a UUID column and this
    #: is a str field; the two disagreeing is what took the Overview down.
    target_ref: str | None
    at: datetime
    #: For the Activity log (Figma 8074:16245): the type the action belongs to
    #: (moderation | money | access | privacy), who did it (None: the system),
    #: the target in words with its admin link, and the recorded reason / note.
    group: str | None = None
    actor_id: uuid.UUID | None = None
    target_label: str | None = None
    href: str | None = None
    reason: str | None = None
    notes: str | None = None
    #: A report decision's outcome (MQA-006); the label reads this, not `action`.
    outcome: str | None = None


class ActivityPage(BaseModel):
    rows: list[ActivityRow]
    total: int


ACTIVITY_ACTION = "^(moderation|money|access|privacy|system|[a-z_]{3,40})$"
ACTIVITY_TARGET = "^(review|answer|seller_review|question|user|comment)$"


def _activity_rows(db: Session, **kw) -> tuple[list[ActivityRow], int]:
    from app.services import activity_log_service
    try:
        found, total = activity_log_service.rows(db, **kw)
    except ValueError as exc:  # an action name that is not one
        raise AppError("Unknown action.", code="unknown_action", status_code=422,
                       title="Invalid filter") from exc
    return [ActivityRow(**r.__dict__) for r in found], total


@router.get("/activity", response_model=ActivityPage,
            summary="The moderation audit log, newest first")
def activity_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: str | None = Query(default=None, description="A staff member's id, or 'system'."),
    action: str | None = Query(default=None, pattern=ACTIVITY_ACTION,
                               description="A type (moderation|money|access|privacy|system) "
                                           "or one action."),
    target: str | None = Query(default=None, pattern=ACTIVITY_TARGET),
    range: Literal["today", "7d", "30d", "all"] = Query(default="all"),  # noqa: A002
    q: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
) -> ActivityPage:
    """Every recorded moderator action, including the ones the Overview's
    five-item feed deliberately leaves out, filtered as the Activity log's
    Person / Action / Target / Range menus ask."""
    rows, total = _activity_rows(
        db, limit=limit, offset=offset, actor_id=_actor(actor), system=actor == "system",
        action=action, target_type=target, range_=range, q=q)
    return ActivityPage(rows=rows, total=total)


def _actor(actor: str | None) -> uuid.UUID | None:
    if not actor or actor == "system":
        return None
    try:
        return uuid.UUID(actor)
    except ValueError as exc:
        raise AppError("Unknown person.", code="unknown_actor", status_code=422,
                       title="Invalid filter") from exc


@router.get("/activity.csv", summary="The Activity log, filtered, as CSV (Export CSV)",
            response_class=Response)
def activity_csv(
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None, pattern=ACTIVITY_ACTION),
    target: str | None = Query(default=None, pattern=ACTIVITY_TARGET),
    range: Literal["today", "7d", "30d", "all"] = Query(default="7d"),  # noqa: A002
    q: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
) -> Response:
    """Up to 5,000 rows, newest first. Notes are included; no emails, no
    payment destinations (the audit log holds neither)."""
    import csv
    import io

    rows, _ = _activity_rows(
        db, limit=5000, offset=0, actor_id=_actor(actor), system=actor == "system",
        action=action, target_type=target, range_=range, q=q)
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(["when", "type", "action", "by", "target_type", "target", "target_id",
                  "reason", "note"])
    for r in rows:
        out.writerow([r.at.isoformat(), r.group, r.action, r.actor or "System",
                      r.target_type or "", r.target_label or "", r.target_ref or "",
                      r.reason or "", r.notes or ""])
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition":
                             'attachment; filename="bluntly-activity-log.csv"',
                             "Cache-Control": "no-store"})


class ActivityTypeCounts(BaseModel):
    moderation: int = 0
    system: int = 0
    money: int = 0
    access: int = 0
    privacy: int = 0


class ReceiptViewOut(BaseModel):
    actor: str | None
    target: str
    href: str | None
    at: datetime


class TeamCountOut(BaseModel):
    id: uuid.UUID
    name: str | None
    count: int


class ActorOut(BaseModel):
    id: uuid.UUID
    name: str | None


class ActivitySummaryOut(BaseModel):
    today_total: int
    by_type: ActivityTypeCounts
    receipt_views: list[ReceiptViewOut]
    team_today: list[TeamCountOut]
    actors: list[ActorOut]


@router.get("/activity/summary", response_model=ActivitySummaryOut,
            summary="The Activity log's side cards: today by type, proof views, team today")
def activity_summary(db: Session = Depends(get_db)) -> ActivitySummaryOut:
    from app.services import activity_log_service
    s = activity_log_service.summary(db)
    return ActivitySummaryOut(
        today_total=s.today_total, by_type=ActivityTypeCounts(**s.by_type),
        receipt_views=[ReceiptViewOut(**v) for v in s.receipt_views],
        team_today=[TeamCountOut(**t) for t in s.team_today],
        actors=[ActorOut(**a) for a in s.actors])


class ReviewerRow(BaseModel):
    id: uuid.UUID
    username: str | None
    display_name: str | None
    role: str
    trust_stage: int
    reputation_score: str
    published_reviews: int
    joined: datetime
    #: Business Rules §11 — standing, not identity. Administrators set and
    #: clear it from this screen (PUT /admin/users/{id}/investigation).
    is_under_investigation: bool = False
    #: The member's public reference (USR-…), level name and suspension, for
    #: the People list (Figma Screen/Admin/People, 2026-10-02).
    user_ref: str | None = None
    trust_level_name: str | None = None
    is_suspended: bool = False
    #: Honesty Score detail (0095): reputation_score above is the EFFECTIVE
    #: score; these are the algorithm's value and the override (null = none).
    computed_score: str = "0.00"
    score_override: str | None = None
    is_score_overridden: bool = False
    #: The member's own profile photo (users.avatar_url); null = none.
    avatar_url: str | None = None


class ReviewerCounts(BaseModel):
    all: int = 0
    active: int = 0
    investigating: int = 0
    suspended: int = 0


class ReviewerPage(BaseModel):
    rows: list[ReviewerRow]
    total: int
    #: Per status, over the same scope and search; filled when asked by scope.
    counts: ReviewerCounts | None = None
    #: Per trust stage ("0".."5"), over the same scope, search and status: the
    #: Filter menu's Stage chips (Figma Menu/People/Filter 7999:11860).
    stages: dict[str, int] | None = None


@router.get("/reviewers", response_model=ReviewerPage,
            summary="Contributors, with trust stage and published counts")
def reviewers(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    scope: Literal["everyone", "members"] = Query(
        default="everyone",
        description="members: leave out staff and claimed sellers (the People list, "
                    "meeting 2026-10-02)."),
    status: Literal["all", "active", "investigating", "suspended"] = Query(default="all"),
    q: str | None = Query(default=None, max_length=120,
                          description="Name, username or USR reference."),
    stage: int | None = Query(default=None, ge=0, le=5),
    sort: Literal["published", "newest", "oldest"] = Query(
        default="published", description="Menu/People/Sort (7999:11850)."),
    db: Session = Depends(get_db),
) -> ReviewerPage:
    """Deliberately carries no email, no address and no session data: a
    moderator managing contributors needs standing and output, not identity."""
    published = (
        select(Review.author_id, func.count().label("n"))
        .where(Review.published_at.is_not(None), Review.is_removed.is_(False))
        .group_by(Review.author_id)
        .subquery()
    )
    where = []
    if scope == "members":
        where += [User.role.not_in((MemberRole.administrator, MemberRole.super_admin)),
                  User.is_claimed_seller.is_(False)]
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        where.append(or_(User.display_name.ilike(like), User.username.ilike(like),
                         User.user_id.ilike(like)))
    states = {
        "active": [User.is_suspended.is_(False), User.is_under_investigation.is_(False)],
        "investigating": [User.is_suspended.is_(False), User.is_under_investigation.is_(True)],
        "suspended": [User.is_suspended.is_(True)],
    }
    counts = None
    if scope == "members":
        counts = ReviewerCounts(
            all=int(db.scalar(select(func.count(User.id)).where(*where)) or 0),
            **{k: int(db.scalar(select(func.count(User.id)).where(*where, *cond)) or 0)
               for k, cond in states.items()})
    if status != "all":
        where += states[status]
    stages = None
    if scope == "members":
        stages = {str(k): int(v) for k, v in db.execute(
            select(User.trust_stage, func.count(User.id)).where(*where)
            .group_by(User.trust_stage)).all()}
    if stage is not None:
        where.append(User.trust_stage == stage)
    total = int(db.scalar(select(func.count(User.id)).where(*where)) or 0)
    order = {
        "published": (func.coalesce(published.c.n, 0).desc(), User.created_at.desc()),
        "newest": (User.created_at.desc(), User.id),
        "oldest": (User.created_at.asc(), User.id),
    }[sort]
    rows = db.execute(
        select(User, func.coalesce(published.c.n, 0))
        .outerjoin(published, published.c.author_id == User.id)
        .where(*where)
        .order_by(*order)
        .limit(limit)
        .offset(offset)
    ).all()
    return ReviewerPage(
        total=total,
        counts=counts,
        stages=stages,
        rows=[
            ReviewerRow(
                id=u.id,
                username=u.username,
                display_name=u.display_name,
                role=u.role.value if hasattr(u.role, "value") else str(u.role),
                trust_stage=u.trust_stage,
                reputation_score=str(u.reputation_score),
                published_reviews=int(n or 0),
                joined=u.created_at,
                is_under_investigation=bool(u.is_under_investigation),
                user_ref=u.user_id,
                trust_level_name=u.trust_level_name,
                is_suspended=bool(u.is_suspended),
                computed_score=str(u.computed_reputation_score),
                score_override=(str(u.reputation_score_override)
                                if u.reputation_score_override is not None else None),
                is_score_overridden=u.reputation_score_override is not None,
                avatar_url=u.avatar_url or None,
            )
            for u, n in rows
        ],
    )


class CronRunRow(BaseModel):
    task: str
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    processed: int | None
    failure: str | None
    detail: str | None


class TaskHealth(BaseModel):
    """One scheduled task's current standing."""

    task: str
    cadence: str
    #: healthy | due | overdue | failed | never_run
    state: str
    period: str
    #: When the current period became due, in Manila.
    due_at: datetime
    #: When the next period becomes due (the Jobs overlay's "Next in 20h").
    next_at: datetime | None = None
    last_run: CronRunRow | None = None
    last_success_at: datetime | None = None


class SchedulerHealth(BaseModel):
    """What a moderator needs to answer "is the automation healthy?"."""

    #: One row per task: standing, not just the last line of a log.
    tasks: list[TaskHealth]
    #: One row per task: its most recent run, whatever the outcome.
    latest: list[CronRunRow]
    #: Recent history across all tasks, newest first.
    recent: list[CronRunRow]
    #: Tasks that are scheduled but have never run at all.
    never_run: list[str]


class TeamMemberOut(BaseModel):
    id: uuid.UUID
    name: str | None
    #: Shown to the Super Admin only.
    email: str | None = None
    role: str
    #: The member's latest recorded staff action (no sign-in time is stored).
    last_action_at: datetime | None = None


class IntegrationOut(BaseModel):
    key: str
    name: str
    #: connected | manual | not_connected
    status: str
    detail: str


class RetentionOut(BaseModel):
    label: str
    value: str


class SettingsOut(BaseModel):
    """Figma Screen/Admin/Settings (8076:16388), read-only: the rules the
    services actually run on. Editable earning rules wait on an owner decision."""

    wilson_gate: float
    min_stage2_voters: int
    split_reviewer: Decimal
    split_honesty_fund: Decimal
    split_platform: Decimal
    payout_minimum: Decimal
    payout_day: int
    honesty_fund_day: int
    team: list[TeamMemberOut]
    team_total: int
    integrations: list[IntegrationOut]
    retention: list[RetentionOut]


@router.get("/settings", response_model=SettingsOut,
            summary="Settings: team, earning and payout rules, integrations, retention (read-only)")
def admin_settings(db: Session = Depends(get_db),
                   user: User = Depends(require_staff)) -> SettingsOut:
    from app.services import settings_overview_service
    o = settings_overview_service.overview(db, show_email=is_super_admin(user))
    return SettingsOut(
        **{k: v for k, v in o.__dict__.items() if k not in ("team", "integrations", "retention")},
        team=[TeamMemberOut(**t.__dict__) for t in o.team],
        integrations=[IntegrationOut(**i.__dict__) for i in o.integrations],
        retention=[RetentionOut(label=label, value=value) for label, value in o.retention])


#: Jobs that move money or delete personal data: the Super Admin's to run by
#: hand. The rest recompute derived figures and are safe to re-run.
SUPER_ONLY_JOBS = frozenset({"honesty_fund_distribution", "schedule_payouts",
                             "refresh_payout_batches", "pii_retention"})


class JobRunOut(BaseModel):
    task: str
    #: ok | continuing | skipped_not_due | skipped_already_completed |
    #: skipped_already_running (the scheduler's own vocabulary)
    status: str
    period: str
    processed: int | None = None
    detail: str | None = None


@router.post("/jobs/{task}/run", response_model=JobRunOut,
             summary="Run one scheduled job now (Activity log, Confirm/Jobs/RunNow)")
def run_job(task: str, db: Session = Depends(get_db),
            user: User = Depends(require_staff)) -> JobRunOut:
    """Figma Confirm/Jobs/RunNow (8081:16369). The scheduler's own route with
    `source=admin`: the same period lease, so a run never doubles one already
    done or in flight, and a job that is not due says so. Money and data-
    deletion jobs are the Super Admin's alone."""
    from app.api.v1.routes import internal_cron

    if task not in internal_cron.TASKS:
        raise NotFoundError("Unknown job.", code="unknown_job")
    if task in SUPER_ONLY_JOBS and not is_super_admin(user):
        raise AppError("Only a Super Admin runs this job by hand.", code="super_admin_only",
                       status_code=403, title="Not allowed")
    result = internal_cron.run_task(task=task, db=db, source="admin")
    return JobRunOut(task=task, status=result.status, period=result.period,
                     processed=result.processed, detail=result.detail)


@router.get("/cron-runs", response_model=SchedulerHealth,
            summary="Scheduled maintenance: last run per task, and recent history")
def cron_runs(
    limit: int = Query(default=40, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SchedulerHealth:
    """Scheduled maintenance runs on an external scheduler, so the only way a
    moderator can tell it is alive is the record it leaves. This is that record:
    no payloads, no credentials, and a failure carries an exception class rather
    than a message."""
    from app.api.v1.routes.internal_cron import TASKS
    from app.models.maintenance import CronRun

    def row(r: CronRun) -> CronRunRow:
        return CronRunRow(
            task=r.task, source=r.source, status=r.status,
            started_at=r.started_at, finished_at=r.finished_at,
            processed=r.processed, failure=r.failure, detail=r.detail)

    try:
        recent = db.scalars(
            select(CronRun).order_by(CronRun.started_at.desc()).limit(limit)).all()
    except Exception:  # noqa: BLE001 - table absent until migration 0034 is applied
        # Every task unrun is the truthful answer before the migration lands,
        # and it is the same thing this says on a fresh deployment.
        db.rollback()
        recent = []

    latest: list[CronRunRow] = []
    seen: set[str] = set()
    for task in TASKS:
        newest = db.scalar(
            select(CronRun).where(CronRun.task == task)
            .order_by(CronRun.started_at.desc()).limit(1))
        if newest is not None:
            latest.append(row(newest))
            seen.add(task)

    # Standing per task, from the period model rather than a guess about
    # wall-clock gaps. "Overdue" is the one that matters: the period is due,
    # nothing has succeeded in it, and enough time has passed that a working
    # scheduler would have fired by now.
    from datetime import timedelta

    from app.api.v1.routes.internal_cron import FAILED, OK
    from app.core.constants import MANILA

    now = datetime.now(MANILA)
    #: A late scheduler is normal; hours late is not. Vercel Cron calls every
    #: five minutes, so this is deliberately generous.
    GRACE = timedelta(hours=6)

    health: list[TaskHealth] = []
    for name, spec in TASKS.items():
        period = spec.period(now)
        due_at = spec.threshold(now)
        try:
            succeeded = db.scalar(
                select(CronRun).where(
                    CronRun.task == name, CronRun.period == period,
                    CronRun.status == OK).limit(1))
            newest = db.scalar(
                select(CronRun).where(CronRun.task == name)
                .order_by(CronRun.started_at.desc()).limit(1))
            last_ok = db.scalar(
                select(CronRun.finished_at).where(
                    CronRun.task == name, CronRun.status == OK)
                .order_by(CronRun.started_at.desc()).limit(1))
        except Exception:  # noqa: BLE001 - table absent before migration 0034/0035
            db.rollback()
            succeeded = newest = last_ok = None

        if succeeded is not None:
            state = "healthy"
        elif newest is None:
            state = "never_run"
        elif newest.status == FAILED and newest.period == period:
            state = "failed"
        elif not spec.is_due(now):
            state = "healthy"          # this period has not come round yet
        elif now > due_at + GRACE:
            state = "overdue"
        else:
            state = "due"

        health.append(TaskHealth(
            task=name, cadence=spec.cadence, state=state, period=period,
            due_at=due_at, next_at=spec.next_threshold(now),
            last_run=row(newest) if newest is not None else None,
            last_success_at=last_ok))

    return SchedulerHealth(
        tasks=sorted(health, key=lambda t: t.task),
        latest=latest,
        recent=[row(r) for r in recent],
        never_run=sorted(set(TASKS) - seen),
    )


# ------------------------------------------------------------------ Products queue

class LinkPreviewOut(BaseModel):
    url: str
    host: str | None = None
    #: A marketplace Bluntly links to (shopee | lazada | amazon), else null.
    marketplace: str | None = None
    https: bool


class QueueProductOut(BaseModel):
    id: uuid.UUID
    name: str | None = None
    category: str | None = None
    image_url: str | None = None
    #: Read from the URL alone; the page is never fetched.
    link: LinkPreviewOut | None = None
    submitted_by_id: uuid.UUID | None = None
    submitted_by_name: str | None = None
    submitter_trust_stage: int | None = None
    submitter_level_name: str | None = None
    submitted_at: datetime
    waiting_days: int
    review_count: int


class ProductQueueOut(BaseModel):
    items: list[QueueProductOut]
    total: int


class CatalogueRowOut(BaseModel):
    id: uuid.UUID
    name: str
    image_url: str | None = None
    category: str | None = None
    review_count: int
    aliases: list[str]
    price_trend: list[Decimal]
    latest_price: Decimal | None = None


class CatalogueOut(BaseModel):
    items: list[CatalogueRowOut]
    total: int
    #: The tabs' badges: named products, and submissions waiting in the queue.
    catalogue_count: int
    queue_count: int


@router.get("/products/catalogue", response_model=CatalogueOut,
            summary="The named products, with aliases and price trend (staff)")
def product_catalogue(q: str | None = Query(default=None, max_length=120),
                      category: str | None = Query(default=None, max_length=60),
                      sort: Literal["reviews", "name", "newest"] = Query(default="reviews"),
                      limit: int = Query(default=10, ge=1, le=100),
                      offset: int = Query(default=0, ge=0),
                      db: Session = Depends(get_db),
                      _: User = Depends(require_staff)) -> CatalogueOut:
    rows, total = product_catalogue_service.catalogue(
        db, q=q, category=category, sort=sort, limit=limit, offset=offset)
    in_catalogue, in_queue = product_catalogue_service.counts(db)
    return CatalogueOut(items=[CatalogueRowOut(**r.__dict__) for r in rows], total=total,
                        catalogue_count=in_catalogue, queue_count=in_queue)


class ProductAdminCreate(ProductCanonicalize):
    """Add product (staff): the Edit modal's naming, plus the listing link."""

    source_url: str | None = Field(default=None, max_length=2048)

    @field_validator("source_url")
    @classmethod
    def _only_web_source(cls, value: str | None) -> str | None:
        return web_url_or_none(value, field="Listing links")


@router.post("/products", response_model=ProductOut, status_code=201,
             responses={409: {"description": "Already in the catalogue (product_exists)"}},
             summary="Add a named product to the catalogue (staff); never a silent duplicate")
def add_product(payload: ProductAdminCreate, db: Session = Depends(get_db),
                staff: User = Depends(require_staff)) -> ProductOut:
    naming = ProductCanonicalize(**payload.model_dump(exclude={"source_url"}))
    product = product_admin_service.create(
        db, staff, product_admin_service.NewProduct(naming=naming, source_url=payload.source_url))
    return ProductOut.model_validate(product)


class ProductImportRowOut(BaseModel):
    line: int
    #: Preview: new / exists / duplicate / conflict / error. After applying:
    #: created / attached / failed; the others keep their preview outcome.
    outcome: Literal["new", "exists", "duplicate", "conflict", "error", "created", "attached",
                     "failed"]
    name: str | None = None
    category: str | None = None
    errors: list[str] = []
    product_id: uuid.UUID | None = None
    existing_name: str | None = None
    duplicate_of_line: int | None = None
    #: exists: "listing", "name" or "listing and name".
    matched_by: str | None = None
    #: exists: what attaching would add; empty means it can only be skipped.
    attach_adds: list[str] = []


class ProductImportOut(BaseModel):
    applied: bool
    rows: list[ProductImportRowOut]
    #: Every outcome's count, plus total / imported / attached / skipped /
    #: invalid / failed for the summary.
    counts: dict[str, int]
    columns: list[str]
    required: list[str]
    #: Headers in the file that are not columns; their cells were not read.
    ignored_columns: list[str] = []
    #: Applying failed and nothing was written: why.
    failure: str | None = None


def _lines(value: str) -> set[int]:
    try:
        return {int(part) for part in value.replace(" ", "").split(",") if part}
    except ValueError as exc:
        raise AppError("`attach` is a comma-separated list of line numbers.",
                       code="import_attach_invalid", status_code=422,
                       title="Invalid request") from exc


@router.post("/products/import", response_model=ProductImportOut,
             summary="Import products from a CSV: preview (apply=false) or apply (staff)")
def import_products(file: UploadFile = File(...), apply: bool = Form(default=False),
                    attach: str = Form(default="", max_length=4000,
                                       description="Lines of `exists` rows to attach "
                                                   "(comma-separated); the rest are skipped"),
                    db: Session = Depends(get_db),
                    staff: User = Depends(require_staff)) -> ProductImportOut:
    data = file.file.read(product_admin_service.MAX_IMPORT_BYTES + 1)
    result = product_admin_service.import_products(db, staff, data, apply=apply,
                                                   attach=_lines(attach),
                                                   filename=file.filename)
    return ProductImportOut(
        applied=result.applied,
        rows=[ProductImportRowOut(**r.__dict__) for r in result.rows],
        counts=result.summary(),
        columns=list(product_admin_service.COLUMNS),
        required=list(product_admin_service.REQUIRED),
        ignored_columns=result.ignored_columns, failure=result.failure)


@router.get("/products/import/template", response_class=Response,
            responses={200: {"content": {"text/csv": {}}}},
            summary="The product CSV template: the columns and one example row (staff)")
def import_template(_: User = Depends(require_staff)) -> Response:
    return Response(content=product_admin_service.template_csv(), media_type="text/csv",
                    headers={"Content-Disposition":
                             'attachment; filename="bluntly-products-template.csv"',
                             "Cache-Control": "no-store"})


@router.get("/products/queue", response_model=ProductQueueOut,
            summary="Submitted products waiting for the catalogue, with link preview (staff)")
def product_queue(sort: Literal["oldest", "newest"] = Query(default="oldest"),
                  limit: int = Query(default=100, ge=1, le=200),
                  db: Session = Depends(get_db),
                  _: User = Depends(require_staff)) -> ProductQueueOut:
    items, total = product_queue_service.queue(db, sort=sort, limit=limit)
    return ProductQueueOut(
        items=[QueueProductOut(**{**i.__dict__,
                                  "link": LinkPreviewOut(**i.link.__dict__) if i.link else None})
               for i in items],
        total=total)


@router.get("/export", response_class=Response,
            responses={200: {"content": {"application/zip": {}}}},
            summary="Export CSV: activity, moderation, earnings and analytics as a zip (audited)")
def admin_export(include: str = Query(default="activity", max_length=64,
                                      description="Comma-separated: activity, moderation, "
                                                  "earnings, analytics"),
                 period: Literal["7d", "30d", "90d", "12m"] = Query(default="30d"),
                 db: Session = Depends(get_db),
                 user: User = Depends(require_staff)) -> Response:
    """Figma Overlay/Admin/Export (8237:25470). Names are shortened and email
    addresses removed from every cell; the export itself is recorded in the
    Activity log (`data_export`) with its sections and period."""
    from app.services import admin_export as svc
    chosen = {part.strip() for part in include.split(",") if part.strip()}
    filename, data = svc.export(db, user, chosen, period)
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


# ---------------------------------------------------------------- PayMongo configuration

class PayMongoTestOut(BaseModel):
    ok: bool
    at: datetime
    detail: str


class PayMongoConfigOut(BaseModel):
    """Overlay/Settings/ConnectPayMongo. The secret key is never returned."""

    storage_ready: bool
    connected: bool
    test_mode: bool
    methods: list[str]
    public_key: str | None = None
    secret_hint: str | None = None
    connected_at: datetime | None = None
    last_test: PayMongoTestOut | None = None
    #: Always false: saving keys never turns automatic payouts on.
    payouts_enabled: bool = False


class PayMongoConfigIn(BaseModel):
    public_key: str = Field(min_length=8, max_length=200)
    #: Omit (or leave empty) to keep the saved secret key.
    secret_key: str | None = Field(default=None, max_length=200)
    methods: list[Literal["gcash", "maya", "bank"]] = Field(min_length=1, max_length=3)
    test_mode: bool = True


def _paymongo_out(c) -> PayMongoConfigOut:
    return PayMongoConfigOut(
        storage_ready=c.storage_ready, connected=c.connected, test_mode=c.test_mode,
        methods=c.methods, public_key=c.public_key, secret_hint=c.secret_hint,
        connected_at=c.connected_at,
        last_test=PayMongoTestOut(**c.last_test.__dict__) if c.last_test else None,
        payouts_enabled=False)


@router.get("/integrations/paymongo", response_model=PayMongoConfigOut,
            summary="PayMongo configuration (staff read; the secret key is never returned)")
def paymongo_config(db: Session = Depends(get_db)) -> PayMongoConfigOut:
    from app.services import paymongo_config as svc
    return _paymongo_out(svc.read(db))


@router.put("/integrations/paymongo", response_model=PayMongoConfigOut,
            summary="Save the PayMongo keys, methods and mode (Super Admin; moves no money)")
def save_paymongo(payload: PayMongoConfigIn, db: Session = Depends(get_db),
                  user: User = Depends(require_super_admin)) -> PayMongoConfigOut:
    from app.services import paymongo_config as svc
    return _paymongo_out(svc.save(db, user, public_key=payload.public_key,
                                  secret_key=payload.secret_key or None,
                                  methods=list(payload.methods), test_mode=payload.test_mode))


@router.post("/integrations/paymongo/test", response_model=PayMongoConfigOut,
             summary="Test the saved PayMongo key with one read-only call (Super Admin)")
def test_paymongo(db: Session = Depends(get_db),
                  user: User = Depends(require_super_admin)) -> PayMongoConfigOut:
    from app.services import paymongo_config as svc
    return _paymongo_out(svc.test_connection(db, user))


@router.delete("/integrations/paymongo", response_model=PayMongoConfigOut,
               summary="Remove the PayMongo keys (Super Admin)")
def remove_paymongo(db: Session = Depends(get_db),
                    user: User = Depends(require_super_admin)) -> PayMongoConfigOut:
    from app.services import paymongo_config as svc
    return _paymongo_out(svc.remove(db, user))

"""Admin earnings endpoints (M2 slices 6 + 8): commission CSV import and the
manual Honesty Fund distribution trigger. RBAC=moderator; all audit-logged."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import AppError
from app.core.security import require_staff
from app.db.session import get_db
from app.models.enums import Platform
from app.models.user import User
from app.schemas.affiliate_admin import (
    AffiliateImportDetailOut,
    AffiliateImportOut,
    AffiliateMonthOut,
    AffiliateTransactionOut,
    AffiliateTransactionPageOut,
)
from app.schemas.qa import QAAuthor
from app.services import (
    affiliate_admin_service,
    affiliate_ingest,
    commission_service,
    honesty_fund_service,
    retention_service,
    seeded_affiliate_reports,
)

router = APIRouter(prefix="/admin", tags=["admin: earnings"],
                   dependencies=[Depends(require_staff)])


class ImportResult(BaseModel):
    imported: int
    skipped_duplicates: int
    unmatched: list[int]
    total_rows: int
    # Which report format was detected: shopee_commission_report |
    # lazada_conversion_report | generic_v1.
    format: str = "generic_v1"
    # Rows the platform says aren't payable yet (pending/cancelled/rejected/
    # returned/invalid/zero commission) — skipped, never paid.
    skipped_unpayable: list[dict] = Field(default_factory=list)
    #: Lines attributed to a 2.5-star "It depends" thread no Super Admin has
    #: routed yet (owner decision A): not recognised now, recognised when the
    #: same file is imported again after routing.
    held_pending_routing: list[int] = Field(default_factory=list)


@router.post("/commissions/import", response_model=ImportResult,
             summary="Import a monthly commission CSV (all-or-nothing, idempotent)")
def import_commissions(file: UploadFile, db: Session = Depends(get_db),
                       mod: User = Depends(require_staff)) -> ImportResult:
    file_bytes = file.file.read()
    result = commission_service.import_commissions(
        db, mod.id, file.filename or "upload.csv", file_bytes)
    return ImportResult(**result)


class HonestyFundRunRequest(BaseModel):
    # Previous calendar month (Asia/Manila) when omitted.
    cycle_month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")


class HonestyFundRunResult(BaseModel):
    cycle_month: date
    pool: str
    recipients: int
    status: str


@router.post("/honesty-fund/run", response_model=HonestyFundRunResult,
             summary="Run the Honesty Fund distribution for a cycle (idempotent)")
def run_honesty_fund(payload: HonestyFundRunRequest, db: Session = Depends(get_db),
                     mod: User = Depends(require_staff)) -> HonestyFundRunResult:
    cycle = None
    if payload.cycle_month:
        year, month = (int(part) for part in payload.cycle_month.split("-"))
        if not 1 <= month <= 12:
            raise AppError("cycle_month must be YYYY-MM with a real month.",
                           code="invalid_cycle_month",
                           status_code=422, title="Invalid cycle month")
        cycle = date(year, month, 1)
    result = honesty_fund_service.distribute(db, cycle_month=cycle,
                                             triggered_by=mod.id)
    return HonestyFundRunResult(**result)


class RetentionSweepResult(BaseModel):
    #: IPs replaced by a salted hash at the 30-day mark.
    hashed: int
    #: Hashes deleted and user agents purged at 90 days, counted together —
    #: `run_retention_sweep` sums them, and this mirrors what it returns rather
    #: than inventing a shape it does not produce.
    purged: int


@router.post("/pii-retention/run", response_model=RetentionSweepResult,
             summary="Run the sessions PII retention sweep (idempotent)")
def run_pii_retention(db: Session = Depends(get_db),
                      mod: User = Depends(require_staff)
                      ) -> RetentionSweepResult:
    """Apply the 30/90-day retention schedule to `sessions`, on demand.

    The sweep is scheduled in `celery_app.beat_schedule` for 03:00 daily, and
    nothing runs it: the deployment is two Vercel services, frontend and
    backend, with no worker and no beat, and the broker points at a Redis that
    is not configured. Measured on 2026-08-21, three sessions were already
    holding a raw IP past their 30-day hashing deadline, and the 90-day
    deletions begin falling due from late October.

    So this exists for the same reason the Honesty Fund has a manual trigger:
    the retention schedule is a promise the platform makes about people's data,
    and it should not depend on infrastructure that is not deployed. Idempotent
    - the sweep selects on deadlines, so running it twice is a no-op the second
    time.
    """
    counts = retention_service.run_retention_sweep(db)
    return RetentionSweepResult(**counts)


class LifecycleImportResult(BaseModel):
    """What an affiliate lifecycle import did, or would do."""

    format: str
    total_rows: int
    recognised: int
    reversed: int
    dropped: int
    #: Rows the LEDGER did nothing about — a different axis from the row
    #: provenance below, and a first import legitimately reports both.
    no_ledger_effect: int
    #: Row provenance: did this file open a canonical transaction, change one,
    #: or say nothing new about it?
    created: int
    updated: int
    unchanged: int
    #: Rows that could not be used at all.
    invalid: int
    #: Usable but needing a human eye (a real sale with no attributable review).
    warnings: int
    #: The canonical lifecycle this file describes, before any ledger effect.
    lifecycle: dict[str, int]
    #: Transitions the matrix refuses. Never applied, always surfaced.
    refused: int
    #: Real sales with no attributable review — recorded, paid to nobody.
    unattributed: int
    #: Rows with no stable provider identity. Recorded as a count rather than
    #: guessed at: an invented key double-credits on the next import.
    unidentified: int
    recognised_amount: str
    reversed_amount: str
    #: Money a reversal could not claw back because it was already paid out.
    #: Bluntly absorbs this; no wallet is driven negative.
    unrecovered_amount: str
    dry_run: bool


@router.post("/affiliate/preview", response_model=LifecycleImportResult,
             summary="What a provider export WOULD do. Writes nothing.")
def preview_affiliate_import(
    file: UploadFile, db: Session = Depends(get_db),
) -> LifecycleImportResult:
    """Dry-run a Shopee or Lazada export.

    Separate from the apply below because a moderator is about to move money on
    the strength of a file they did not write, produced by a system they do not
    control. Seeing the effect first — how many recognitions, how many
    reversals, how much cannot be clawed back — is what makes that a decision
    rather than a leap.
    """
    summary = affiliate_ingest.preview(db, file.file.read())
    return LifecycleImportResult(**summary.as_dict())


@router.post("/affiliate/import", response_model=LifecycleImportResult,
             summary="Import a provider export into the canonical lifecycle")
def import_affiliate_report(
    file: UploadFile, db: Session = Depends(get_db),
    mod: User = Depends(require_staff),
) -> LifecycleImportResult:
    """Apply a Shopee or Lazada export.

    Idempotent on the provider's own transaction identity rather than on the
    file, so re-importing the same order from a different export is a no-op
    instead of a second credit.
    """
    summary = affiliate_ingest.apply(
        db, mod.id, file.filename or "upload.csv", file.file.read())
    return LifecycleImportResult(**summary.as_dict())


# --- Seeded marketplace reports (owner plan, 2026-09-28) ---------------------
# Real export shape, pre-filled with our sub-IDs, so the import -> match ->
# split -> reconcile -> report chain can run before real buyers exist. Refused
# on production; seeded rows are refused by both importers there too. See
# app/services/seeded_affiliate_reports.py and docs/REPORTING_MODULE.md.

def _seeded_csv(content: bytes, platform: Platform, label: str) -> Response:
    filename = f"bluntly-seeded-{platform.value}-{label}.csv"
    return Response(content=content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


@router.get("/affiliate/seeded-report",
            summary="Generate a seeded Shopee/Lazada report from active links (TEST only)",
            response_class=Response)
def seeded_affiliate_report(
    platform: Literal["shopee", "lazada"],
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=1970, le=2100),
    rows_per_link: int = Query(default=1, ge=1, le=20),
    include_unpayable: bool = Query(default=True),
    seed: str = Query(default="bluntly", min_length=1, max_length=40),
    db: Session = Depends(get_db),
):
    if (month is None) != (year is None):
        raise AppError("Give both month and year, or neither.", code="period_incomplete",
                       status_code=422, title="Invalid report period")
    cycle = (date(year, month, 1) if month is not None
             else seeded_affiliate_reports.default_cycle(datetime.now(MANILA).date()))
    content = seeded_affiliate_reports.synthesize(
        db, Platform(platform), cycle, rows_per_link=rows_per_link,
        include_unpayable=include_unpayable, seed=seed)
    return _seeded_csv(content, Platform(platform), f"{cycle:%Y-%m}")


@router.post("/affiliate/seeded-report/fill",
             summary="Fill a real Shopee/Lazada export with our sub-IDs (TEST only)",
             response_class=Response)
def fill_seeded_affiliate_report(
    file: UploadFile, platform: Literal["shopee", "lazada"] = Query(),
    db: Session = Depends(get_db),
):
    content = seeded_affiliate_reports.fill_template(db, Platform(platform), file.file.read())
    return _seeded_csv(content, Platform(platform), "filled")


# ------------------------------------------------------------------ Affiliate screen

@router.get("/affiliate/transactions", response_model=AffiliateTransactionPageOut,
            summary="Affiliate transactions imported from the marketplace reports (staff)")
def affiliate_transactions(
    platform: str | None = Query(default=None, pattern="^(shopee|lazada|amazon|other)$"),
    status: str | None = Query(default=None, pattern="^(pending|completed|cancelled|returned)$"),
    q: str | None = Query(default=None, max_length=120),
    settlement: str | None = Query(default=None, pattern="^(not_earned|earned|paid|reversed)$"),
    attribution: str | None = Query(default=None, pattern="^(attributed|unattributed)$"),
    updated: str | None = Query(default=None, pattern="^(7d|30d|year)$"),
    sort: str = Query(default="newest",
                      pattern="^(newest|oldest|commission_desc|commission_asc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
) -> AffiliateTransactionPageOut:
    page = affiliate_admin_service.transactions(
        db, platform=platform, status=status, q=q, settlement=settlement,
        attribution=attribution, updated=updated, sort=sort, limit=limit, offset=offset)
    return AffiliateTransactionPageOut(
        rows=[AffiliateTransactionOut(**{
            **r.__dict__,
            "reviewer": QAAuthor.model_validate(r.reviewer) if r.reviewer is not None else None})
            for r in page.rows],
        total=page.total, counts=page.counts, facets=page.facets)


@router.get("/affiliate/months", response_model=list[AffiliateMonthOut],
            summary="Commission recognised, reversed and remitted per marketplace month (staff)")
def affiliate_months(
    platform: str | None = Query(default=None, pattern="^(shopee|lazada|amazon|other)$"),
    db: Session = Depends(get_db),
    _: User = Depends(require_staff),
) -> list[AffiliateMonthOut]:
    return [AffiliateMonthOut(**m.__dict__)
            for m in affiliate_admin_service.months(db, platform=platform, limit=600)]


@router.get("/affiliate/imports", response_model=list[AffiliateImportOut],
            summary="Report imports, newest first, with what each did (staff)")
def affiliate_imports(limit: int = Query(default=50, ge=1, le=200),
                      db: Session = Depends(get_db),
                      _: User = Depends(require_staff)) -> list[AffiliateImportOut]:
    rows = affiliate_admin_service.imports(db, limit=limit)
    return [AffiliateImportOut(**i.__dict__) for i in rows]


@router.get("/affiliate/imports/{import_log_id}", response_model=AffiliateImportDetailOut,
            summary="One import: its summary and the rows it wrote (staff)")
def affiliate_import_detail(import_log_id: str = Path(max_length=48),
                            db: Session = Depends(get_db),
                            _: User = Depends(require_staff)) -> AffiliateImportDetailOut:
    d = affiliate_admin_service.import_detail(db, import_log_id)
    return AffiliateImportDetailOut(
        summary=AffiliateImportOut(**d.summary.__dict__), lifecycle=d.lifecycle,
        transactions=[AffiliateTransactionOut(**t.__dict__) for t in d.transactions])

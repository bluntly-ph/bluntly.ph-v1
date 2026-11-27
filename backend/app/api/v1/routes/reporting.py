"""The four system reports (docs/REPORTING_MODULE.md).

    GET /reports/earnings-statement                     the caller's own statement
    GET /admin/reports/earnings-statement/{user_id}     staff: any reviewer's
    GET /sellers/{seller_id}/reports/rating-summary     the store's approved owner, or staff
    GET /admin/reports/commissions-payouts              staff
    GET /admin/reports/honesty-fund                     staff
    GET /admin/reports/financial                        staff: the Reports screen's figures
    POST /admin/reports/financial/generate              staff: a branded PDF, logged
    GET /admin/reports/financial/history                staff: the generated PDFs
    GET /admin/reports/financial/history/{id}/pdf       staff: download one again

Every endpoint takes the same period parameters (month + year, year, or
start_date + end_date; default the current Manila month) and `format=csv`
for a download, with `section` choosing which table.

WHO MAY READ WHAT is decided here and only here, by the three guards below. A
reviewer's statement is derived from the session — there is no user id in the
reviewer's own path to swap. The staff guard is the finance-console role of the
current architecture (`moderator`); the Administrator / Super Admin split will
change `require_report_staff`, not the reports.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import get_current_user, is_staff, require_staff
from app.db.session import get_db
from app.models.user import User
from app.schemas.reporting import (
    CommissionPayoutReportOut,
    EarningsStatementOut,
    FinancialGenerateIn,
    FinancialReportEntryOut,
    FinancialReportOut,
    HonestyFundReportOut,
    SellerRatingSummaryOut,
)
from app.services import seller_service
from app.services.reporting import (
    commission_payout,
    earnings_statement,
    financial,
    financial_pdf,
    honesty_fund,
    periods,
    seller_rating,
)
from app.services.reporting.common import Table, csv_filename, to_csv

router = APIRouter(tags=["reports"])

#: The finance console's reader. One line to change when roles are split.
require_report_staff = require_staff


def is_report_staff(user: User) -> bool:
    return is_staff(user)


def report_period(month: int | None = Query(default=None, ge=1, le=12),
                  year: int | None = Query(default=None),
                  start_date: date | None = Query(default=None),
                  end_date: date | None = Query(default=None)) -> periods.Period:
    """month + year | year | start_date + end_date. Validated in `periods.resolve`."""
    return periods.resolve(month=month, year=year, start_date=start_date, end_date=end_date)


def _csv(tables: dict[str, Table], section: str | None, report: str,
         period: periods.Period) -> Response:
    name = section or next(iter(tables))
    table = tables.get(name)
    if table is None:
        raise AppError(f"Unknown section; choose one of: {', '.join(tables)}.",
                       code="report_section_unknown", status_code=422,
                       title="Invalid report request", extra={"sections": list(tables)})
    filename = csv_filename(report, period.slug, name if section else None)
    return Response(content=to_csv(table), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store"})


Format = Literal["json", "csv"]


# ------------------------------------------------------------------ 4. reviewer

@router.get("/reports/earnings-statement", response_model=EarningsStatementOut,
            summary="Your earnings statement for a period")
def my_earnings_statement(period: periods.Period = Depends(report_period),
                          format: Format = Query(default="json"),
                          section: str | None = Query(default=None, max_length=32),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    report = earnings_statement.build(db, user, period)
    if format == "csv":
        return _csv(earnings_statement.csv_tables(report), section, "earnings-statement",
                    period)
    return report


@router.get("/admin/reports/earnings-statement/{user_id}", response_model=EarningsStatementOut,
            summary="A reviewer's earnings statement (staff)")
def reviewer_earnings_statement(user_id: uuid.UUID, period: periods.Period = Depends(report_period),
                                format: Format = Query(default="json"),
                                section: str | None = Query(default=None, max_length=32),
                                db: Session = Depends(get_db),
                                _: User = Depends(require_report_staff)):
    reviewer = earnings_statement.reviewer_or_404(db, user_id)
    report = earnings_statement.build(db, reviewer, period)
    if format == "csv":
        return _csv(earnings_statement.csv_tables(report), section, "earnings-statement",
                    period)
    return report


# ------------------------------------------------------------------ 3. seller

@router.get("/sellers/{seller_id}/reports/rating-summary", response_model=SellerRatingSummaryOut,
            summary="A store's rating summary (its approved owner, or staff)")
def seller_rating_summary(seller_id: uuid.UUID, period: periods.Period = Depends(report_period),
                          format: Format = Query(default="json"),
                          db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    seller = seller_service.get_seller_or_404(db, seller_id)
    if not is_report_staff(user):
        # The same test the store dashboard applies: an APPROVED claim by this
        # account. A pending claimant, another store's owner and a buyer all get
        # 403 `not_store_owner`.
        seller_service.require_store_owner(seller, user)
    report = seller_rating.build(db, seller, period)
    if format == "csv":
        return _csv(seller_rating.csv_tables(report), None, "seller-rating-summary",
                    period)
    return report


# ------------------------------------------------------------------ 2. commissions

@router.get("/admin/reports/commissions-payouts", response_model=CommissionPayoutReportOut,
            summary="Commissions, reconciliation and payout readiness (staff)")
def commissions_payouts(period: periods.Period = Depends(report_period),
                        limit: int = Query(default=commission_payout.DEFAULT_LIMIT, ge=1,
                                           le=commission_payout.MAX_LIMIT),
                        offset: int = Query(default=0, ge=0),
                        format: Format = Query(default="json"),
                        section: str | None = Query(default=None, max_length=32),
                        db: Session = Depends(get_db),
                        _: User = Depends(require_report_staff)):
    if format == "csv":
        # A download is the whole period's table, up to the hard cap.
        report = commission_payout.build(db, period,
                                         limit=commission_payout.MAX_LIMIT, offset=0)
        return _csv(commission_payout.csv_tables(report), section, "commission-payout",
                    period)
    return commission_payout.build(db, period, limit=limit, offset=offset)


# ------------------------------------------------------------------ 1. honesty fund

@router.get("/admin/reports/honesty-fund", response_model=HonestyFundReportOut,
            summary="Honesty Fund inputs and distribution status (staff)")
def honesty_fund_report(period: periods.Period = Depends(report_period),
                        format: Format = Query(default="json"),
                        section: str | None = Query(default=None, max_length=32),
                        db: Session = Depends(get_db),
                        _: User = Depends(require_report_staff)):
    report = honesty_fund.build(db, period)
    if format == "csv":
        return _csv(honesty_fund.csv_tables(report), section, "honesty-fund", period)
    return report


# ------------------------------------------------------------------ 5. financial

def financial_period(month: int | None = Query(default=None, ge=1, le=12),
                     quarter: int | None = Query(default=None, ge=1, le=4),
                     year: int | None = Query(default=None),
                     start_date: date | None = Query(default=None),
                     end_date: date | None = Query(default=None)) -> periods.Period:
    """`report_period` plus a quarter: month + year | quarter + year | year | range."""
    return periods.resolve(month=month, quarter=quarter, year=year, start_date=start_date,
                           end_date=end_date)


def _generate_period(payload: FinancialGenerateIn) -> periods.Period:
    """The modal's Month / Quarter / Year / Custom, each with what it needs."""
    needs = {"month": ("month", "year"), "quarter": ("quarter", "year"), "year": ("year",),
             "custom": ("start_date", "end_date")}[payload.kind]
    missing = [f for f in needs if getattr(payload, f) is None]
    if missing:
        raise AppError(f"A {payload.kind} report needs: {', '.join(missing)}.",
                       code="period_incomplete", status_code=422, title="Invalid report period")
    values = {f: getattr(payload, f) for f in needs}
    return periods.resolve(**values)


@router.get("/admin/reports/financial", response_model=FinancialReportOut,
            summary="The financial report's figures for a period (staff)")
def financial_report(period: periods.Period = Depends(financial_period),
                     db: Session = Depends(get_db),
                     _: User = Depends(require_report_staff)):
    return financial.build(db, period)


@router.post("/admin/reports/financial/generate", response_model=FinancialReportEntryOut,
             status_code=201, summary="Generate a financial report PDF and log it (staff)")
def generate_financial_report(payload: FinancialGenerateIn,
                              db: Session = Depends(get_db),
                              user: User = Depends(require_report_staff)):
    period = _generate_period(payload)
    sections = financial.clean_sections(payload.sections)
    report = financial.build(db, period)
    _, pages = financial_pdf.render(report, sections, generated_by=financial.author_name(user))
    return financial.record(db, report, sections, pages, user)


@router.get("/admin/reports/financial/history", response_model=list[FinancialReportEntryOut],
            summary="Financial report PDFs generated so far, newest first (staff)")
def financial_history(db: Session = Depends(get_db),
                      _: User = Depends(require_report_staff)):
    return financial.history(db)


@router.get("/admin/reports/financial/history/{entry_id}/pdf", response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}},
            summary="Download a generated financial report again (staff)")
def financial_history_pdf(entry_id: str = Path(max_length=32, pattern="^[a-f0-9]+$"),
                          db: Session = Depends(get_db),
                          _: User = Depends(require_report_staff)):
    # Re-rendered from the figures logged at generation: the same document,
    # not today's numbers under an old date.
    entry, report = financial.find(db, entry_id)
    pdf, _pages = financial_pdf.render(report, list(entry["sections"]),
                                       generated_by=entry.get("generated_by"))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{financial_pdf.filename(report)}"',
                             "Cache-Control": "no-store"})

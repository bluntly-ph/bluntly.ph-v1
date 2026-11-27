"""The admin console's Export CSV (Figma Overlay/Admin/Export 8237:25470).

One zip of CSV files for a period:

- activity:   every audit-log row (moderator and system actions);
- moderation: the moderation group of the log: decisions, reports, escalations;
- earnings:   the commissions / payout readiness / remittances report and the
              Honesty Fund report, one file per table, as the Reports pages build them;
- analytics:  the Analytics page's figures (KPIs, funnel, moderation, community,
              and reviews per day or week), long format: section, metric, value, previous.

People's names are shortened to a first name and initial, @handles stay as they
are, and anything shaped like an email address is removed from every cell. Each
export is itself recorded in the audit log (`data_export`), with what it held.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.core.errors import AppError
from app.models.enums import ModerationAction
from app.models.moderation import ModerationLog
from app.models.user import User

#: The Analytics page's own ranges, so "the numbers on the Analytics page" match.
PERIODS = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}
SECTIONS = ("activity", "moderation", "earnings", "analytics")
ROW_CAP = 20_000

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def scrub(value: object) -> object:
    """Remove email addresses from a cell; other values pass through."""
    if isinstance(value, str):
        return _EMAIL.sub("[email removed]", value)
    return value


def short_name(name: str | None) -> str:
    """'Joanna Reyes' -> 'Joanna R.'; an @handle or a single word stays."""
    if not name:
        return ""
    name = str(scrub(name)).strip()
    if name.startswith("@"):
        return name
    parts = name.split()
    return f"{parts[0]} {parts[1][0]}." if len(parts) > 1 else parts[0]


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    out = csv.writer(buf)
    out.writerow(header)
    out.writerows([[scrub(c) if c is not None else "" for c in r] for r in rows])
    return buf.getvalue().encode("utf-8-sig")


def _log_file(db: Session, period: str, group: str | None) -> bytes:
    from app.services import activity_log_service
    found, _ = activity_log_service.rows(db, limit=ROW_CAP, offset=0, action=group,
                                         range_=period)
    return _csv(
        ["when", "type", "action", "by", "target_type", "target", "target_id", "reason",
         "note"],
        [[r.at.astimezone(MANILA).isoformat(), r.group, r.action,
          short_name(r.actor) or "System", r.target_type, r.target_label, r.target_ref,
          r.reason, r.notes] for r in found])


def _earnings(db: Session, days: int) -> dict[str, bytes]:
    from app.services.reporting import commission_payout, honesty_fund, periods
    from app.services.reporting.common import Table, to_csv
    today = datetime.now(MANILA).date()
    period = periods.resolve(start_date=today - timedelta(days=min(days, 366) - 1),
                             end_date=today)
    files: dict[str, bytes] = {}
    tables = {
        **{f"earnings-{k}": t for k, t in commission_payout.csv_tables(
            commission_payout.build(db, period, limit=commission_payout.MAX_LIMIT,
                                    offset=0)).items()},
        **{f"earnings-honesty-fund-{k}": t for k, t in honesty_fund.csv_tables(
            honesty_fund.build(db, period)).items()},
    }
    for name, table in tables.items():
        # The Reports pages' own CSV formatting, after the same scrub as the rest.
        rows = [{k: short_name(v) if k == "reviewer" and v else scrub(v) for k, v in r.items()}
                for r in table.rows]
        files[f"{name}.csv"] = to_csv(Table(table.name, table.columns, rows))
    return files


def _cell(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(MANILA).isoformat()
    return value


def _analytics(db: Session, period: str) -> bytes:
    from app.services import analytics_summary_service
    s = analytics_summary_service.summary(db, period)
    rows: list[list] = [["kpi", k.key, k.current, k.previous] for k in s.kpis]
    for section, values in (("funnel", s.funnel), ("moderation", s.moderation),
                            ("community", s.community), ("needs_a_look", s.needs_a_look)):
        for key, value in (values or {}).items():
            if isinstance(value, dict):  # e.g. reviewers by trust stage
                rows.extend([section, f"{key}.{k}", _cell(v), ""] for k, v in value.items())
            elif not isinstance(value, list):
                rows.append([section, key, _cell(value), ""])
    for point in s.series:
        start = point.get("start")
        rows.append([f"reviews per {s.series_unit}",
                     start.astimezone(MANILA).date().isoformat() if start else "",
                     point.get("current"), point.get("previous")])
    return _csv(["section", "metric", "value", "previous"], rows)


def export(db: Session, staff: User, include: set[str], period: str) -> tuple[str, bytes]:
    if period not in PERIODS:
        raise AppError("Choose a period.", code="export_period_invalid", status_code=422,
                       title="Invalid export")
    if not include or not include <= set(SECTIONS):
        raise AppError("Choose what to include.", code="export_include_invalid",
                       status_code=422, title="Invalid export")
    files: dict[str, bytes] = {}
    if "activity" in include:
        files["activity-log.csv"] = _log_file(db, period, None)
    if "moderation" in include:
        files["moderation.csv"] = _log_file(db, period, "moderation")
    if "earnings" in include:
        files.update(_earnings(db, PERIODS[period]))
    if "analytics" in include:
        files["analytics-summary.csv"] = _analytics(db, period)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=staff.id,
                         action=ModerationAction.data_export,
                         notes=f"exported {', '.join(sorted(include))} ({period})",
                         context={"sections": sorted(include), "period": period,
                                  "files": sorted(files)}))
    db.commit()
    stamp = datetime.now(MANILA).strftime("%Y%m%d")
    return f"bluntly-admin-export-{stamp}.zip", out.getvalue()

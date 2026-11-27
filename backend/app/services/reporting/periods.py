"""Reporting periods: which days a report covers, in Asia/Manila.

A period is chosen one of four ways, and never two at once:

    month + year          one calendar month
    quarter + year        one calendar quarter (the financial report's "Quarter")
    year                  one calendar year
    start_date + end_date a custom range of whole days, both ends inclusive

With nothing chosen it is the current Manila month. The platform's cycle is a
Manila calendar month (`honesty_fund_service.previous_cycle_month`, the
commission importer's `cycle_month`), so the day boundaries are Manila
midnights, turned into UTC instants for the queries.

Commissions are dated by their CYCLE MONTH, not by a day: the marketplace
reports settle by month and the importer stores `cycle_month` as the first of
that month. A financial report over a custom range therefore covers every
cycle month the range touches, and says so (`cycle_months`), rather than
pretending to a day-level precision the ledger does not have.

A range is capped at 366 days. Reports are read on demand against a shared
database; an unbounded range is an unbounded scan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.core.constants import MANILA
from app.core.errors import AppError

#: The longest custom range a report accepts, in days (a leap year).
MAX_RANGE_DAYS = 366
#: Earliest year a report may ask about: a sanity bound, not a business rule
#: (the real limit is MAX_RANGE_DAYS). Test fixtures date their isolated
#: cycles in the past (1970, 1996, 1997) so they can never collide with real
#: months, and a report must be able to read them.
MIN_YEAR = 1970


def _invalid(detail: str, code: str) -> AppError:
    return AppError(detail, code=code, status_code=422, title="Invalid report period")


@dataclass(frozen=True)
class Period:
    #: First day covered (Manila).
    start: date
    #: Last day covered, inclusive (Manila).
    end: date
    #: "month" | "quarter" | "year" | "range"
    kind: str

    @property
    def quarter(self) -> int:
        return (self.start.month - 1) // 3 + 1

    @property
    def label(self) -> str:
        if self.kind == "month":
            return self.start.strftime("%B %Y")
        if self.kind == "quarter":
            return f"Q{self.quarter} {self.start.year}"
        if self.kind == "year":
            return str(self.start.year)
        return f"{self.start.isoformat()} to {self.end.isoformat()}"

    @property
    def slug(self) -> str:
        """For file names: 2026-09, 2026-Q3, 2026, or 2026-09-01_2026-09-15."""
        if self.kind == "month":
            return self.start.strftime("%Y-%m")
        if self.kind == "quarter":
            return f"{self.start.year}-Q{self.quarter}"
        if self.kind == "year":
            return str(self.start.year)
        return f"{self.start.isoformat()}_{self.end.isoformat()}"

    @property
    def starts_at(self) -> datetime:
        """The first instant covered, as UTC."""
        return datetime.combine(self.start, time.min, MANILA).astimezone(UTC)

    @property
    def ends_before(self) -> datetime:
        """The first instant NOT covered (the Manila midnight after `end`), as UTC."""
        return datetime.combine(self.end + timedelta(days=1), time.min, MANILA).astimezone(UTC)

    @property
    def first_cycle(self) -> date:
        return self.start.replace(day=1)

    @property
    def last_cycle(self) -> date:
        return self.end.replace(day=1)

    @property
    def cycle_months(self) -> list[date]:
        """Every cycle month (first of month) the period touches, oldest first."""
        out: list[date] = []
        cursor = self.first_cycle
        while cursor <= self.last_cycle:
            out.append(cursor)
            cursor = (cursor.replace(year=cursor.year + 1, month=1) if cursor.month == 12
                      else cursor.replace(month=cursor.month + 1))
        return out

    def as_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "start": self.start.isoformat(),
                "end": self.end.isoformat(), "timezone": "Asia/Manila",
                "cycle_months": [m.strftime("%Y-%m") for m in self.cycle_months]}


def _month_end(first: date) -> date:
    nxt = (first.replace(year=first.year + 1, month=1) if first.month == 12
           else first.replace(month=first.month + 1))
    return nxt - timedelta(days=1)


def today_manila(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(MANILA).date()


def resolve(*, month: int | None = None, year: int | None = None,
            start_date: date | None = None, end_date: date | None = None,
            quarter: int | None = None, now: datetime | None = None) -> Period:
    """Turn the query parameters into one validated Period (422 on any misuse)."""
    ranged = start_date is not None or end_date is not None
    if ranged and (month is not None or year is not None or quarter is not None):
        raise _invalid("Choose a month/year or a date range, not both.", "period_ambiguous")
    if quarter is not None and month is not None:
        raise _invalid("Choose a month or a quarter, not both.", "period_ambiguous")

    if ranged:
        if start_date is None or end_date is None:
            raise _invalid("A date range needs both start_date and end_date.",
                           "period_incomplete")
        if end_date < start_date:
            raise _invalid("end_date is before start_date.", "period_inverted")
        if (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
            raise _invalid(f"A report covers at most {MAX_RANGE_DAYS} days.",
                           "period_too_long")
        if start_date.year < MIN_YEAR:
            raise _invalid(f"Reports start in {MIN_YEAR}.", "period_too_early")
        return Period(start=start_date, end=end_date, kind="range")

    if month is not None and year is None:
        raise _invalid("A month needs a year.", "period_incomplete")
    if quarter is not None and year is None:
        raise _invalid("A quarter needs a year.", "period_incomplete")
    if month is not None and not 1 <= month <= 12:
        raise _invalid("month must be 1 to 12.", "period_invalid_month")
    if quarter is not None and not 1 <= quarter <= 4:
        raise _invalid("quarter must be 1 to 4.", "period_invalid_quarter")
    if year is not None and not MIN_YEAR <= year <= 2100:
        raise _invalid(f"year must be {MIN_YEAR} to 2100.", "period_invalid_year")

    if quarter is not None and year is not None:
        first = date(year, 3 * (quarter - 1) + 1, 1)
        return Period(start=first, end=_month_end(date(year, 3 * quarter, 1)), kind="quarter")
    if year is None:
        first = today_manila(now).replace(day=1)
        return Period(start=first, end=_month_end(first), kind="month")
    if month is None:
        return Period(start=date(year, 1, 1), end=date(year, 12, 31), kind="year")
    first = date(year, month, 1)
    return Period(start=first, end=_month_end(first), kind="month")

"""The admin Payouts screen's Honesty Fund tab (Figma 8024:13286): the cycle
being collected, when it closes and is shared out, the last distribution, and
one row per recent cycle.

Every figure is counted: a cycle's pool is the Honesty Fund share of its
real (non-test) commissions; contributors, the largest share and the date are
read from the distribution rows the monthly run wrote. A closed cycle with no
rows says so ("not distributed") rather than borrowing a status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import MANILA
from app.models.commission import Commission
from app.models.honesty_fund import HonestyFundDistribution
from app.services.settings_overview_service import _task_day

CYCLES = 12
ZERO = Decimal("0.00")


@dataclass
class Cycle:
    month: date
    pool: Decimal
    contributors: int
    largest_share: Decimal | None
    distributed: Decimal
    distributed_at: datetime | None
    #: "collecting" (this month), "distributed", or "not_distributed".
    status: str


@dataclass
class FundCycles:
    current: Cycle
    closes_on: date
    distributes_on: date
    last: Cycle | None
    cycles: list[Cycle]


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def build(db: Session, *, now: datetime | None = None) -> FundCycles:
    today = (now or datetime.now(UTC)).astimezone(MANILA).date()
    this = today.replace(day=1)
    oldest = _add_months(this, -(CYCLES - 1))
    pools = dict(db.execute(
        select(Commission.cycle_month, func.coalesce(func.sum(Commission.honesty_fund_share), 0))
        .where(Commission.is_test.is_(False), Commission.cycle_month >= oldest,
               Commission.cycle_month <= this)
        .group_by(Commission.cycle_month)).all())
    runs = {row[0]: row[1:] for row in db.execute(
        select(HonestyFundDistribution.cycle_month,
               func.count(func.distinct(HonestyFundDistribution.reviewer_id)),
               func.max(HonestyFundDistribution.payout_amount),
               func.coalesce(func.sum(HonestyFundDistribution.payout_amount), 0),
               func.min(HonestyFundDistribution.created_at))
        .where(HonestyFundDistribution.cycle_month >= oldest,
               HonestyFundDistribution.cycle_month <= this)
        .group_by(HonestyFundDistribution.cycle_month)).all()}

    cycles: list[Cycle] = []
    for i in range(CYCLES):
        month = _add_months(this, -i)
        pool = Decimal(pools.get(month, 0) or 0).quantize(Decimal("0.01"))
        run = runs.get(month)
        if month != this and run is None and pool == 0:
            continue  # nothing happened in it
        cycles.append(Cycle(
            month=month, pool=pool,
            contributors=int(run[0]) if run else 0,
            largest_share=Decimal(run[1]).quantize(Decimal("0.01")) if run else None,
            distributed=Decimal(run[2]).quantize(Decimal("0.01")) if run else ZERO,
            distributed_at=run[3] if run else None,
            status="collecting" if month == this else "distributed" if run else "not_distributed"))
    next_month = _add_months(this, 1)
    day = _task_day("honesty_fund_distribution")
    return FundCycles(
        current=cycles[0], closes_on=next_month - timedelta(days=1),
        distributes_on=next_month.replace(day=min(day, 28)),
        last=next((c for c in cycles if c.status == "distributed"), None), cycles=cycles)

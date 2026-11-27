"""The "Time" filter the search sheets offer (Figma "All filters" 1587:4658).

All time, Past year, Past month — the only filter group in that frame whose
meaning is unambiguous, so it is the one served. One definition, shared by the
review feed, the Questions tab and the seller-review list, so "past month"
means the same thirty days everywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

Period = Literal["all", "year", "month"]

_WINDOW = {"year": timedelta(days=365), "month": timedelta(days=30)}


def period_start(period: Period | None, now: datetime | None = None) -> datetime | None:
    """The earliest instant a period admits, or None for all time."""
    window = _WINDOW.get(period or "all")
    if window is None:
        return None
    return (now or datetime.now(UTC)) - window

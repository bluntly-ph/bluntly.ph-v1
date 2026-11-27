"""What every report shares: money formatting, masking, tables and CSV.

CSV rules, all of them load-bearing for a finance export:

* Stable columns. A table declares its columns once, in order, and the CSV is
  written from that declaration — never from whatever keys a row happens to
  carry, so an internal field added to a row can never leak into an export.
* Exact money. Amounts are written as plain decimal strings to the centavo
  ("1234.50"), no currency sign and no thousands separator, so a spreadsheet
  reads the number the ledger holds.
* UTF-8 with a byte-order mark, so Excel opens "₱" and "Pokémon" correctly;
  RFC 4180 quoting via the csv module.
* Formula injection. A text cell starting with = + - @ (or a tab/CR) is
  prefixed with an apostrophe, so a review title like "=HYPERLINK(...)" is
  shown, not executed. Numbers are exempt: -12.50 is a reversal, not a formula.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
CURRENCY = "PHP"

_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_SAFE_FILENAME = re.compile(r"[^a-z0-9_.-]+")


def money(value: Any) -> Decimal:
    """Any stored amount as a Decimal to the centavo. Never a float."""
    if value is None:
        return ZERO
    if isinstance(value, float):  # pragma: no cover - a programming error, loudly
        raise TypeError("money must not be a float")
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def mask_destination(value: str | None) -> str | None:
    """A payout address as a reviewer may see it on a statement: j***@gmail.com.

    Enough to recognise which account was used, not enough to be a usable
    address. Anything that is not an email is reduced to its last 4 characters.
    """
    if not value:
        return None
    value = value.strip()
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[:1]}***@{domain}"
    return f"***{value[-4:]}" if len(value) > 4 else "***"


@dataclass
class Column:
    key: str
    header: str
    #: "text" | "money" | "number" | "date" | "datetime" | "bool"
    kind: str = "text"


@dataclass
class Table:
    name: str
    columns: list[Column]
    rows: list[dict[str, Any]] = field(default_factory=list)


def _cell(value: Any, kind: str) -> str:
    if value is None:
        return ""
    if kind == "money":
        return f"{money(value):f}"
    if kind == "bool":
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:f}"
    text = str(value)
    if kind == "text" and text.startswith(_FORMULA_START) and not _NUMBER.match(text):
        return "'" + text
    return text


def to_csv(table: Table) -> bytes:
    """One table as UTF-8 (BOM) CSV, columns in their declared order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([c.header for c in table.columns])
    for row in table.rows:
        writer.writerow([_cell(row.get(c.key), c.kind) for c in table.columns])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def csv_filename(report: str, period_slug: str, section: str | None = None) -> str:
    """bluntly-commission-payout-2026-09.csv — lower-case, no path characters."""
    parts = ["bluntly", report, period_slug] + ([section] if section else [])
    name = "-".join(_SAFE_FILENAME.sub("-", p.lower()).strip("-") for p in parts if p)
    return f"{name}.csv"

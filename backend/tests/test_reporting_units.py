"""Reporting module — the parts that need no database: periods, CSV, masking.

Money in a CSV is a promise about the ledger, so these pin the exact bytes.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.services.reporting import common, periods

# ---------------------------------------------------------------- periods

def test_default_is_the_current_manila_month():
    # 2026-09-30 17:00 UTC is already 1 October in Manila.
    p = periods.resolve(now=datetime(2026, 9, 30, 17, 0, tzinfo=UTC))
    assert (p.start, p.end, p.kind) == (date(2026, 10, 1), date(2026, 10, 31), "month")


def test_month_boundaries_are_manila_midnights():
    p = periods.resolve(month=9, year=2026)
    assert p.starts_at == datetime(2026, 8, 31, 16, 0, tzinfo=UTC)
    assert p.ends_before == datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
    assert p.slug == "2026-09" and p.label == "September 2026"
    assert p.cycle_months == [date(2026, 9, 1)]


def test_december_and_february_end_correctly():
    assert periods.resolve(month=12, year=2026).end == date(2026, 12, 31)
    assert periods.resolve(month=2, year=2028).end == date(2028, 2, 29)


def test_a_year_covers_twelve_cycles():
    p = periods.resolve(year=2026)
    assert (p.start, p.end, p.slug) == (date(2026, 1, 1), date(2026, 12, 31), "2026")
    assert len(p.cycle_months) == 12


def test_a_custom_range_lists_every_cycle_it_touches():
    p = periods.resolve(start_date=date(2026, 8, 20), end_date=date(2026, 10, 2))
    assert p.kind == "range"
    assert p.cycle_months == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]
    assert p.slug == "2026-08-20_2026-10-02"


@pytest.mark.parametrize("kwargs,code", [
    ({"month": 9}, "period_incomplete"),
    ({"month": 13, "year": 2026}, "period_invalid_month"),
    ({"year": 1969}, "period_invalid_year"),
    ({"start_date": date(2026, 1, 1)}, "period_incomplete"),
    ({"start_date": date(1969, 1, 1), "end_date": date(1969, 1, 2)}, "period_too_early"),
    ({"start_date": date(2026, 2, 1), "end_date": date(2026, 1, 1)}, "period_inverted"),
    ({"start_date": date(2025, 1, 1), "end_date": date(2026, 1, 2)}, "period_too_long"),
    ({"month": 1, "year": 2026, "start_date": date(2026, 1, 1),
      "end_date": date(2026, 1, 2)}, "period_ambiguous"),
])
def test_bad_periods_are_refused_not_widened(kwargs, code):
    with pytest.raises(AppError) as exc:
        periods.resolve(**kwargs)
    assert exc.value.code == code and exc.value.status_code == 422


def test_a_leap_year_range_is_allowed():
    p = periods.resolve(start_date=date(2028, 1, 1), end_date=date(2028, 12, 31))
    assert (p.end - p.start).days + 1 == 366


# ---------------------------------------------------------------- CSV

def _table(rows):
    return common.Table("t", [common.Column("name", "Name"),
                              common.Column("amount", "Amount", "money"),
                              common.Column("ok", "OK", "bool")], rows)


def test_csv_is_utf8_with_bom_and_stable_columns():
    raw = common.to_csv(_table([{"amount": Decimal("1234.5"), "name": "Pokémon ₱", "ok": True,
                                 "secret": "never exported"}]))
    assert raw.startswith("﻿".encode())
    text = raw.decode("utf-8-sig")
    assert text == "Name,Amount,OK\r\nPokémon ₱,1234.50,Yes\r\n"
    assert "never exported" not in text


def test_money_keeps_its_exact_value_and_sign():
    text = common.to_csv(_table([{"amount": Decimal("-12.50"), "name": "x", "ok": False},
                                 {"amount": Decimal("0.005"), "name": "y", "ok": None}]))
    lines = text.decode("utf-8-sig").splitlines()
    assert lines[1] == "x,-12.50,No"
    assert lines[2] == "y,0.01,"


def test_formula_injection_is_neutralised_in_text_cells():
    text = common.to_csv(_table([{"name": "=HYPERLINK(\"http://x\")", "amount": "1",
                                  "ok": True},
                                 {"name": "-5", "amount": "1", "ok": True},
                                 {"name": "+cmd", "amount": "1", "ok": True}]))
    lines = text.decode("utf-8-sig").splitlines()
    assert lines[1].startswith("\"'=HYPERLINK(")
    assert lines[2].startswith("-5,")        # a number is not a formula
    assert lines[3].startswith("'+cmd,")


def test_commas_and_quotes_are_quoted():
    text = common.to_csv(_table([{"name": 'He said "a, b"', "amount": "2", "ok": True}]))
    assert text.decode("utf-8-sig").splitlines()[1] == '"He said ""a, b""",2.00,Yes'


def test_float_money_is_refused():
    with pytest.raises(TypeError):
        common.money(0.1)


def test_filenames_are_safe():
    assert common.csv_filename("commission-payout", "2026-09") == \
        "bluntly-commission-payout-2026-09.csv"
    assert common.csv_filename("x/../y", "2026", "Payout Summary") == \
        "bluntly-x-..-y-2026-payout-summary.csv"
    assert "/" not in common.csv_filename("a/b", "c/d")


@pytest.mark.parametrize("value,masked", [
    ("juan.delacruz@gmail.com", "j***@gmail.com"),
    ("x@y.ph", "x***@y.ph"),
    ("09171234567", "***4567"),
    ("abc", "***"),
    (None, None),
    ("", None),
])
def test_payout_destinations_are_masked(value, masked):
    assert common.mask_destination(value) == masked


# ---------------------------------------------------------------- one formula

def test_reports_do_not_reimplement_the_split():
    """The 40/30/30 split lives in `earnings`; reports read stored shares.

    A second copy of the formula is how two screens come to disagree about
    the same peso, so the reporting package may not contain one.
    """
    root = pathlib.Path(__file__).resolve().parent.parent / "app" / "services" / "reporting"
    for path in root.glob("*.py"):
        source = path.read_text()
        for needle in ("split_commission", "REVIEWER_SHARE", "HONESTY_FUND_SHARE",
                       "Decimal(\"0.3\")", "Decimal(\"0.4\")", "* 0.3", "* 0.4"):
            assert needle not in source, f"{path.name} re-implements the split ({needle})"

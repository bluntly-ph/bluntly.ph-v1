"""Price history, tested without a database (Business Rules §16).

The Full Record supersedes FR-2's "three independent reporters before any
price shows": price history is a line graph per marketplace, a report always
belongs to a review, and only an outlier (or a product with no baseline yet)
waits for an admin. `panel_from` builds what is shown from approved rows; the
hold rule itself is `hold_reason_for` (test_business_rules_unit.py).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.models.enums import Platform, PriceObservationStatus
from app.services.price_service import panel_from


class Observation:
    """Duck-typed stand-in for a PriceHistory row. Approved unless stated."""

    def __init__(self, price, submitted_by=..., observed_at=None,
                 platform=Platform.shopee, status=PriceObservationStatus.approved):
        self.price = Decimal(str(price))
        self.submitted_by = uuid.uuid4() if submitted_by is ... else submitted_by
        self.observed_at = observed_at or date(2026, 8, 1)
        self.platform = platform
        self.status = status


def from_distinct_people(*prices):
    return [Observation(p) for p in prices]


class TestApprovedPricesShowAtOnce:

    def test_no_observations_shows_nothing(self):
        panel = panel_from([])
        assert panel.sufficient is False
        assert panel.observation_count == 0
        assert panel.series == {}

    def test_one_approved_price_is_enough_to_draw(self):
        panel = panel_from(from_distinct_people(100))
        assert panel.sufficient is True
        assert panel.observation_count == 1

    def test_distinct_people_are_still_counted_for_the_reader(self):
        alone = uuid.uuid4()
        rows = [Observation(p, submitted_by=alone) for p in (100, 110)]
        panel = panel_from(rows + [Observation(120)])
        assert panel.observation_count == 3
        assert panel.independent_count == 2


class TestOneLinePerMarketplace:
    """§16: "never blended into one merged, averaged line"."""

    def test_marketplaces_get_their_own_series(self):
        rows = [Observation(900, platform=Platform.shopee),
                Observation(1000, platform=Platform.lazada)]
        panel = panel_from(rows)
        assert set(panel.series) == {"shopee", "lazada"}
        assert [p.price for p in panel.series["shopee"]] == [Decimal("900")]
        assert [p.price for p in panel.series["lazada"]] == [Decimal("1000")]

    def test_a_missing_marketplace_has_no_series_so_no_toggle(self):
        panel = panel_from([Observation(900, platform=Platform.shopee)])
        assert list(panel.series) == ["shopee"]

    def test_same_day_prices_on_one_marketplace_are_one_point_at_their_median(self):
        day = date(2026, 8, 1)
        rows = [Observation(p, observed_at=day, platform=Platform.lazada)
                for p in (900, 1000, 1100)]
        panel = panel_from(rows)
        assert [(p.observed_at, p.price) for p in panel.series["lazada"]] == \
            [(day, Decimal("1000"))]

    def test_points_are_in_date_order(self):
        rows = [Observation(900, observed_at=date(2026, 8, 3)),
                Observation(950, observed_at=date(2026, 8, 1))]
        panel = panel_from(rows)
        assert [p.observed_at for p in panel.series["shopee"]] == \
            [date(2026, 8, 1), date(2026, 8, 3)]


class TestTheArithmeticOnceItOpens:

    def test_low_high_and_median_of_an_odd_count(self):
        panel = panel_from(from_distinct_people(300, 100, 200))
        assert panel.low == Decimal("100")
        assert panel.high == Decimal("300")
        assert panel.median == Decimal("200")

    def test_median_of_an_even_count_is_the_midpoint(self):
        panel = panel_from(from_distinct_people(100, 200, 300, 400))
        assert panel.median == Decimal("250")

    def test_centavos_survive(self):
        panel = panel_from(from_distinct_people("99.99", "100.01", "100.00"))
        assert panel.low == Decimal("99.99")
        assert panel.high == Decimal("100.01")
        assert panel.median == Decimal("100.00")

    def test_identical_prices_give_a_zero_width_range(self):
        panel = panel_from(from_distinct_people(150, 150, 150))
        assert panel.low == panel.high == panel.median == Decimal("150")

    def test_latest_observed_at_is_the_most_recent(self):
        rows = [
            Observation(100, observed_at=date(2026, 1, 1)),
            Observation(110, observed_at=date(2026, 8, 20)),
            Observation(120, observed_at=date(2026, 3, 15)),
        ]
        assert panel_from(rows).latest_observed_at == date(2026, 8, 20)

    def test_platforms_are_deduplicated_and_ordered(self):
        rows = [
            Observation(100, platform=Platform.shopee),
            Observation(110, platform=Platform.lazada),
            Observation(120, platform=Platform.shopee),
        ]
        assert panel_from(rows).platforms == ("lazada", "shopee")


class TestOnlyApprovedObservationsCount:
    """The completion contract: observations are pending, approved or rejected,
    and the panel is built from approved ones only. A price nobody has checked
    is not yet an observation of the market."""

    PENDING = PriceObservationStatus.pending
    REJECTED = PriceObservationStatus.rejected

    def test_pending_observations_do_not_open_the_panel(self):
        rows = [Observation(p, status=self.PENDING) for p in (100, 110, 120)]
        panel = panel_from(rows)
        assert panel.sufficient is False
        assert panel.observation_count == 0
        assert panel.independent_count == 0
        assert panel.pending_count == 3

    def test_held_rows_are_counted_as_waiting_but_never_priced(self):
        rows = from_distinct_people(100, 110) + [Observation(120_000, status=self.PENDING)]
        panel = panel_from(rows)
        assert panel.pending_count == 1
        assert panel.high == Decimal("110")

    def test_a_rejected_price_is_not_in_the_range(self):
        rows = from_distinct_people(100, 110, 120) + [
            Observation(99_999, status=self.REJECTED)]
        panel = panel_from(rows)
        assert panel.sufficient is True
        assert panel.high == Decimal("120")
        assert panel.observation_count == 3

    def test_a_rejected_price_is_not_counted_as_waiting(self):
        panel = panel_from([Observation(100, status=self.REJECTED)])
        assert panel.pending_count == 0


def test_panels_for_routes_through_the_same_rule():
    """The comparison view kept its own copy of the threshold; one rule only."""
    import inspect

    from app.services import price_service
    assert "panel_from(" in inspect.getsource(price_service.panels_for)


def test_get_panel_still_routes_through_the_rule():
    """The extraction must not have left a second copy behind."""
    import inspect

    from app.services import price_service
    src = inspect.getsource(price_service.get_panel)
    assert "panel_from(rows)" in src, (
        "get_panel no longer delegates to panel_from; the tested rule and the "
        "served one have diverged")

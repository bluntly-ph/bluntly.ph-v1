"""The settled Business Rules (Full Record, 2026-09-23), as pure rules. No database."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.models.enums import EarnEligibleStatus, SpecialRoute, Verdict
from app.services.activity_surge import is_activity_surge
from app.services.earning_track import (
    SUPERADMIN_ROUTING,
    EarningTrack,
    approved_status_for,
    effective_track,
    track_for,
    verdict_star_mismatch,
)
from app.services.earnings import FLAT_REVIEWER_BPS, split_for_review
from app.services.price_service import HOLD_NO_BASELINE, HOLD_OUTLIER, hold_reason_for
from app.services.product_search import normalize
from app.services.report_service import is_surge, unfounded_penalty
from app.services.review_service import _add_months
from app.services.trust import gate_vote_weight

# --- §14 verdict decides the track -------------------------------------------


@pytest.mark.parametrize("stars", [0, 0.5, 1, 2, 2.5, 3, 4, 5])
def test_yes_is_always_commission_whatever_the_stars(stars):
    assert track_for(Verdict.yes_absolutely, stars) == EarningTrack.commission


@pytest.mark.parametrize("stars", [0, 1, 2, 2.5, 3, 4, 5])
def test_hard_pass_is_always_the_honesty_fund_whatever_the_stars(stars):
    assert track_for(Verdict.hard_pass, stars) == EarningTrack.honesty_fund


@pytest.mark.parametrize(("stars", "track"), [
    (0, EarningTrack.honesty_fund), (1, EarningTrack.honesty_fund),
    (1.5, EarningTrack.honesty_fund), (2, EarningTrack.honesty_fund),
    (3, EarningTrack.commission), (3.5, EarningTrack.commission),
    (4, EarningTrack.commission), (5, EarningTrack.commission),
])
def test_it_depends_breaks_the_tie_on_stars(stars, track):
    assert track_for(Verdict.it_depends, stars) == track


def test_two_and_a_half_on_it_depends_goes_to_a_super_admin_not_a_track():
    """Owner decision A: neither track by itself; the approval escalates."""
    assert track_for(Verdict.it_depends, 2.5) == SUPERADMIN_ROUTING
    assert approved_status_for(SUPERADMIN_ROUTING) == \
        EarnEligibleStatus.pending_superadmin_routing


def test_the_super_admins_route_decides_the_track():
    assert effective_track(SUPERADMIN_ROUTING, None) == SUPERADMIN_ROUTING
    assert effective_track(SUPERADMIN_ROUTING, SpecialRoute.honesty_fund) == \
        EarningTrack.honesty_fund
    # PLATFORM is the commission route (a link may go on); the money differs.
    assert effective_track(SUPERADMIN_ROUTING, SpecialRoute.platform) == \
        EarningTrack.commission
    # A route never overrides a thread the ordinary rule already decides.
    assert effective_track(EarningTrack.honesty_fund, SpecialRoute.platform) == \
        EarningTrack.honesty_fund


def test_a_platform_route_keeps_the_reviewers_share_for_the_platform():
    review = SimpleNamespace(earn_eligible_status=EarnEligibleStatus.approved,
                             special_route=SpecialRoute.platform, removed_by_author_at=None)
    split, bps = split_for_review(Decimal("100.00"), review, SimpleNamespace())
    assert bps == 0
    assert split == {"gross_amount": Decimal("100.00"), "platform_share": Decimal("70.00"),
                     "reviewer_share": Decimal("0.00"), "honesty_fund_share": Decimal("30.00")}
    fund = SimpleNamespace(earn_eligible_status=EarnEligibleStatus.honesty_fund,
                           special_route=SpecialRoute.honesty_fund, removed_by_author_at=None)
    split, _ = split_for_review(Decimal("100.00"), fund, SimpleNamespace())
    assert (split["platform_share"], split["reviewer_share"], split["honesty_fund_share"]) \
        == (Decimal("40.00"), Decimal("0.00"), Decimal("60.00"))


def test_tracks_map_to_their_approved_states():
    assert approved_status_for(EarningTrack.commission) == EarnEligibleStatus.approved
    assert approved_status_for(EarningTrack.honesty_fund) == EarnEligibleStatus.honesty_fund


@pytest.mark.parametrize(("verdict", "stars", "mismatch"), [
    (Verdict.yes_absolutely, 2, True), (Verdict.yes_absolutely, 1, True),
    (Verdict.yes_absolutely, 3, False), (Verdict.hard_pass, 3, True),
    (Verdict.hard_pass, 5, True), (Verdict.hard_pass, 2, False),
    (Verdict.it_depends, 0, False), (Verdict.it_depends, 5, False),
])
def test_a_contradicting_verdict_is_a_signal_not_an_override(verdict, stars, mismatch):
    assert verdict_star_mismatch(verdict, stars) is mismatch


# --- §14 flat 40/30/30 ----------------------------------------------------------


def _review(status=EarnEligibleStatus.monetized):
    return SimpleNamespace(earn_eligible_status=status)


def test_every_sale_splits_forty_thirty_thirty():
    split, bps = split_for_review(Decimal("100.00"), _review(), SimpleNamespace(
        is_claimed_seller=False))
    assert bps == FLAT_REVIEWER_BPS == 3000
    assert (split["platform_share"], split["reviewer_share"], split["honesty_fund_share"]) \
        == (Decimal("40.00"), Decimal("30.00"), Decimal("30.00"))


@pytest.mark.parametrize("gross", ["0.01", "0.07", "33.33", "99.99", "1234.57"])
def test_the_split_always_resums_to_the_gross(gross):
    split, _ = split_for_review(Decimal(gross), _review(), None)
    assert split["platform_share"] + split["reviewer_share"] + split["honesty_fund_share"] \
        == split["gross_amount"]


def test_a_fund_track_thread_sends_the_reviewer_share_to_the_fund():
    split, bps = split_for_review(Decimal("100.00"),
                                  _review(EarnEligibleStatus.honesty_fund), None)
    assert bps == 0
    assert split["reviewer_share"] == Decimal("0.00")
    assert split["honesty_fund_share"] == Decimal("60.00")
    assert split["platform_share"] == Decimal("40.00")


def test_a_claimed_seller_never_earns():
    split, bps = split_for_review(Decimal("100.00"), _review(),
                                  SimpleNamespace(is_claimed_seller=True))
    assert bps == 0 and split["reviewer_share"] == Decimal("0.00")


# --- §11 vote weight -------------------------------------------------------------


def test_new_accounts_and_investigations_halve_and_stack():
    full = gate_vote_weight(2, 100.0, 365, False)
    assert gate_vote_weight(2, 100.0, 10, False) == pytest.approx(full * 0.5)
    assert gate_vote_weight(2, 100.0, 365, False, is_under_investigation=True) \
        == pytest.approx(full * 0.5)
    assert gate_vote_weight(2, 100.0, 10, False, is_under_investigation=True) \
        == pytest.approx(full * 0.25)


def test_probation_overrides_investigation_and_zeroes():
    assert gate_vote_weight(4, 100.0, 365, True, is_under_investigation=True) == 0.0


def test_a_claimed_seller_has_no_vote_weight_at_any_stage():
    assert gate_vote_weight(6, 100.0, 999, False, is_claimed_seller=True) == 0.0


# --- §12 reports --------------------------------------------------------------------


def test_one_unfounded_report_never_penalises():
    assert unfounded_penalty(dismissed=1, resolved=1) == 1.0
    assert unfounded_penalty(dismissed=2, resolved=2) == 1.0


def test_a_pattern_of_unfounded_reports_reduces_future_weight():
    assert unfounded_penalty(dismissed=3, resolved=4) == 0.5
    assert unfounded_penalty(dismissed=6, resolved=7) == 0.25
    assert unfounded_penalty(dismissed=3, resolved=10) == 1.0  # mostly founded


def test_a_burst_is_judged_against_the_items_own_baseline():
    assert is_surge(recent=3, prior=0) is True
    assert is_surge(recent=2, prior=0) is False
    # A review that is reported a lot every day is not "bursting" at the same rate.
    assert is_surge(recent=4, prior=120) is False
    assert is_surge(recent=20, prior=120) is True


def test_activity_surge_is_relative_not_raw_volume():
    assert is_activity_surge(recent=12, prior=0) is True
    assert is_activity_surge(recent=9, prior=0) is False          # too few to mean anything
    assert is_activity_surge(recent=300, prior=7000) is False     # popular, not unusual
    assert is_activity_surge(recent=3001, prior=7000) is True


# --- §16 price holds -------------------------------------------------------------


def test_no_baseline_gets_an_admin_glance():
    assert hold_reason_for([], Decimal("899")) == HOLD_NO_BASELINE
    assert hold_reason_for([Decimal("899"), Decimal("900")], Decimal("899")) == HOLD_NO_BASELINE


def test_a_normal_price_publishes_and_an_outlier_is_held():
    base = [Decimal("900"), Decimal("950"), Decimal("1000")]
    assert hold_reason_for(base, Decimal("980")) is None
    assert hold_reason_for(base, Decimal("5000")) == HOLD_OUTLIER
    assert hold_reason_for(base, Decimal("100")) == HOLD_OUTLIER


# --- §4 thread cooldown is calendar months --------------------------------------


def test_three_months_is_calendar_months_with_the_day_clamped():
    assert _add_months(datetime(2026, 1, 31, tzinfo=UTC), 3) == datetime(2026, 4, 30, tzinfo=UTC)
    assert _add_months(datetime(2026, 11, 15, tzinfo=UTC), 3) == datetime(2027, 2, 15, tzinfo=UTC)


# --- §6 search normalisation ---------------------------------------------------


def test_search_normalises_punctuation_and_accents():
    assert normalize("Jisulife  Life9-Handheld (Fan)") == "jisulife life9 handheld fan"
    assert normalize("Café") == "cafe"


# --- §14 Honesty Fund formula is an open decision --------------------------------


def test_honesty_fund_distribution_is_off_by_default():
    assert Settings.model_fields["honesty_fund_distribution_enabled"].default is False

"""Admin queue priority tiers — the pure rule (dev note 2026-09-26).

The test matrix the owner's round-3 brief asks for, case by case, against
`priority_tiers.evaluate`, plus the voter-risk mapping and the settings
validation. No database: every input is an already-loaded fact.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services import priority_settings
from app.services.priority_settings import DEFAULTS, TierConfig
from app.services.priority_tiers import (
    Tier,
    TierFacts,
    Trend,
    VoterRisk,
    escalate_one,
    evaluate,
)
from app.services.priority_triage import classify_voter

#: A Stage 1 author's second review with nothing going on: plain Neutral.
PLAIN = TierFacts(
    wilson_lower_bound=0.40, trend=Trend.stable, flagged_upvoters=0,
    author_history_flagged_voters=0, author_stage=1, first_submission=False,
    report_count=0, fraud_reports=0)

IN_BAND = 0.66   # inside 0.60-0.70
BELOW = 0.40     # outside the band


def tier(**changes) -> Tier:
    return evaluate(replace(PLAIN, **changes), DEFAULTS).tier


def codes(**changes) -> list[str]:
    return [r.code for r in evaluate(replace(PLAIN, **changes), DEFAULTS).reasons]


# --- one signal: High ------------------------------------------------------

def test_wilson_only_is_high():
    assert tier(wilson_lower_bound=IN_BAND) is Tier.high
    assert "wilson_band" in codes(wilson_lower_bound=IN_BAND)


def test_band_edges_are_inclusive_and_outside_is_not_a_signal():
    assert tier(wilson_lower_bound=0.60) is Tier.high
    assert tier(wilson_lower_bound=0.70) is Tier.high
    assert tier(wilson_lower_bound=0.599) is Tier.neutral
    assert tier(wilson_lower_bound=0.701) is Tier.neutral


def test_risk_voter_only_is_high():
    assert tier(flagged_upvoters=1) is Tier.high


def test_one_fraud_report_only_is_high():
    assert tier(fraud_reports=1, report_count=1) is Tier.high
    assert "fraud_report" in codes(fraud_reports=1, report_count=1)


def test_two_fraud_reports_alone_are_one_signal_so_high():
    assert tier(fraud_reports=2, report_count=2) is Tier.high


# --- convergence: Highest --------------------------------------------------

def test_wilson_and_risk_is_highest():
    assert tier(wilson_lower_bound=IN_BAND, flagged_upvoters=1) is Tier.highest


def test_wilson_and_two_fraud_is_highest():
    assert tier(wilson_lower_bound=IN_BAND, fraud_reports=2, report_count=2) is Tier.highest


def test_risk_and_two_fraud_is_highest():
    assert tier(flagged_upvoters=1, fraud_reports=2, report_count=2) is Tier.highest


def test_all_three_is_highest():
    assert tier(wilson_lower_bound=IN_BAND, flagged_upvoters=3,
                fraud_reports=4, report_count=4) is Tier.highest


def test_a_single_fraud_report_does_not_converge():
    """Tier 1 needs 2+ fraud reports; one report is its own High signal and
    never makes a second converging one."""
    assert tier(wilson_lower_bound=IN_BAND, fraud_reports=1, report_count=1) is Tier.high
    assert tier(flagged_upvoters=1, fraud_reports=1, report_count=1) is Tier.high


def test_the_highest_explanation_names_both_signals():
    reasons = evaluate(replace(PLAIN, wilson_lower_bound=IN_BAND, fraud_reports=2,
                               report_count=2), DEFAULTS).reasons
    labels = [r.label for r in reasons]
    assert "Wilson near threshold" in labels and "2 fraud reports" in labels


# --- the Stage 0 first-submission rule --------------------------------------

def test_stage0_first_submission_without_signals_is_high():
    assert tier(author_stage=0, first_submission=True) is Tier.high
    assert "stage0_first_submission" in codes(author_stage=0, first_submission=True)


def test_stage0_second_submission_is_not_automatically_high():
    assert tier(author_stage=0, first_submission=False) is Tier.neutral


def test_the_first_submission_rule_alone_never_makes_highest():
    assert tier(author_stage=0, first_submission=True, wilson_lower_bound=IN_BAND) is Tier.high


def test_a_first_submission_with_two_converging_signals_is_highest():
    assert tier(author_stage=0, first_submission=True, wilson_lower_bound=IN_BAND,
                flagged_upvoters=1) is Tier.highest


def test_the_first_submission_rule_is_only_for_stage_0():
    assert tier(author_stage=1, first_submission=True) is Tier.neutral


# --- Low / Lowest ------------------------------------------------------------

def test_stage3_clean_is_low():
    assert tier(author_stage=3) is Tier.low


def test_stage4_and_stage5_clean_are_lowest_routine_spot_check():
    for stage in (4, 5):
        result = evaluate(replace(PLAIN, author_stage=stage), DEFAULTS)
        assert result.tier is Tier.lowest
        assert result.routine_spot_check
        assert result.reasons[-1].label == "Routine spot-check"


def test_stage3_with_any_report_is_not_low():
    """Zero reports of ANY kind — a spam report is enough to lose Low."""
    assert tier(author_stage=3, report_count=1) is Tier.neutral
    assert tier(author_stage=5, report_count=1) is Tier.neutral


def test_stage3_with_a_flagged_voter_in_the_authors_history_is_not_low():
    assert tier(author_stage=3, author_history_flagged_voters=1) is Tier.neutral


def test_stage3_with_a_falling_wilson_trend_is_not_low():
    assert tier(author_stage=3, trend=Trend.falling) is Tier.neutral


def test_a_rising_or_unmoved_trend_keeps_low():
    assert tier(author_stage=3, trend=Trend.rising) is Tier.low
    assert tier(author_stage=3, trend=Trend.unknown) is Tier.low


def test_a_risk_signal_outranks_a_trusted_author():
    assert tier(author_stage=5, wilson_lower_bound=IN_BAND) is Tier.high


def test_no_signal_and_a_low_stage_is_neutral():
    assert tier(author_stage=2) is Tier.neutral
    assert tier(author_stage=None) is Tier.neutral


# --- aging: exactly one tier -------------------------------------------------

def _aged(**changes) -> Tier:
    return evaluate(replace(PLAIN, **changes), DEFAULTS, aged=True).tier


def test_neutral_aged_is_high():
    assert _aged() is Tier.high


def test_low_aged_is_neutral():
    assert _aged(author_stage=3) is Tier.neutral


def test_lowest_aged_is_low():
    assert _aged(author_stage=4) is Tier.low


def test_high_aged_is_highest():
    assert _aged(wilson_lower_bound=IN_BAND) is Tier.highest


def test_highest_aged_stays_highest():
    assert _aged(wilson_lower_bound=IN_BAND, flagged_upvoters=1) is Tier.highest


def test_aging_never_skips_a_tier():
    for start in Tier:
        up = escalate_one(start)
        assert abs(list(Tier).index(up) - list(Tier).index(start)) <= 1


def test_aging_is_explained():
    result = evaluate(PLAIN, DEFAULTS, aged=True)
    assert result.aged and result.base_tier is Tier.neutral
    assert result.reasons[-1].code == "aged"


# --- configuration -----------------------------------------------------------

def test_the_wilson_band_is_configurable():
    narrow = replace(DEFAULTS, wilson_band_low=0.64, wilson_band_high=0.66)
    assert evaluate(replace(PLAIN, wilson_lower_bound=0.68), narrow).tier is Tier.neutral
    assert evaluate(replace(PLAIN, wilson_lower_bound=0.65), narrow).tier is Tier.high


def test_fraud_thresholds_are_configurable():
    strict = replace(DEFAULTS, fraud_high_min=1, fraud_convergence_min=3)
    two = replace(PLAIN, flagged_upvoters=1, fraud_reports=2, report_count=2)
    assert evaluate(two, strict).tier is Tier.high
    assert evaluate(two, DEFAULTS).tier is Tier.highest


def test_stage_boundaries_are_configurable():
    shifted = replace(DEFAULTS, low_min_stage=2, lowest_min_stage=5)
    assert evaluate(replace(PLAIN, author_stage=2), shifted).tier is Tier.low
    assert evaluate(replace(PLAIN, author_stage=4), shifted).tier is Tier.low
    assert evaluate(replace(PLAIN, author_stage=5), shifted).tier is Tier.lowest


@pytest.mark.parametrize("patch", [
    {"wilson_band_low": 0.8, "wilson_band_high": 0.7},
    {"wilson_band_high": 1.5},
    {"fraud_high_min": 0},
    {"fraud_high_min": 3, "fraud_convergence_min": 2},
    {"aging_hours": 0},
    {"low_min_stage": 4, "lowest_min_stage": 3},
    {"fraud_reasons": ["not_a_reason"]},
    {"fraud_reasons": []},
    {"unknown_key": 1},
    {"aging_hours": "soon"},
])
def test_invalid_settings_are_refused_whole(patch):
    with pytest.raises(AppError):
        priority_settings._validated({**DEFAULTS.as_dict(), **patch})


def test_defaults_are_the_dev_notes_starting_values():
    assert (DEFAULTS.wilson_band_low, DEFAULTS.wilson_band_high) == (0.60, 0.70)
    assert (DEFAULTS.fraud_high_min, DEFAULTS.fraud_convergence_min) == (1, 2)
    assert (DEFAULTS.low_min_stage, DEFAULTS.lowest_min_stage) == (3, 4)
    assert DEFAULTS.aging_hours == 72
    assert set(DEFAULTS.fraud_reasons) == {"fake_proof", "seller_posing_as_buyer", "counterfeit"}
    assert isinstance(priority_settings._validated({}), TierConfig)


# --- voter risk: existing enforcement state, no new scoring ------------------

NOW = datetime(2026, 9, 27, tzinfo=UTC)


def _voter(**kw):
    base = {"is_suspended": False, "is_under_investigation": False, "is_on_probation": False,
            "strikes": 0, "created_at": NOW - timedelta(days=200)}
    return SimpleNamespace(**{**base, **kw})


def test_voter_risk_levels():
    assert classify_voter(_voter(), now=NOW) is VoterRisk.baseline
    assert classify_voter(_voter(created_at=NOW - timedelta(days=5)), now=NOW) is VoterRisk.elevated
    assert classify_voter(_voter(strikes=1), now=NOW) is VoterRisk.elevated
    assert classify_voter(_voter(is_on_probation=True), now=NOW) is VoterRisk.high
    assert classify_voter(_voter(), now=NOW, concentration="open") is VoterRisk.high
    assert classify_voter(_voter(is_under_investigation=True), now=NOW) is VoterRisk.critical
    assert classify_voter(_voter(is_suspended=True), now=NOW) is VoterRisk.critical
    assert classify_voter(_voter(), now=NOW, concentration="upheld") is VoterRisk.critical

"""reputation_score, stage determination, and gate vote-weight tests (ADR-003)."""

from __future__ import annotations

import math

from app.services import trust as T


def test_reputation_bounds():
    assert T.reputation_score(0, 0, 0, 0) == 0.0
    # Max out every component: 100 helpfulness, many reviews/best answers.
    assert T.reputation_score(100, 10_000, 100, 0) == 100.0


def test_reputation_strikes_penalize():
    base = T.reputation_score(80, 10, 2, 0)
    penalized = T.reputation_score(80, 10, 2, 2)
    assert penalized == max(0.0, base - 30.0)


def test_reputation_monotonic_in_helpfulness():
    assert T.reputation_score(50, 5, 1, 0) < T.reputation_score(90, 5, 1, 0)


def test_stage_ladder():
    assert T.determine_stage(0, 0, 0, 0, 0, 0) == 0
    assert T.determine_stage(1, 0, 0, 0, 0, 0) == 1          # first review
    assert T.determine_stage(1, 1, 0, 0, 0, 0) == 2          # first verified
    assert T.determine_stage(6, 5, 75, 0, 0, 1) == 3         # >=5 verified, >=70%
    assert T.determine_stage(20, 15, 85, 3, 0, 2) == 4       # trusted
    assert T.determine_stage(60, 50, 95, 5, 0, 7) == 5       # expert


def test_stage_4_blocked_by_strike():
    assert T.determine_stage(20, 15, 85, 3, 1, 2) == 3  # a strike drops below Stage 4


def test_helpfulness_discounts_small_samples():
    """ADR-014: a lone up-vote must not score as a perfect record."""
    assert T.helpfulness_score(0, 0) == 0.0
    assert T.helpfulness_score(1, 0) == 20.65
    assert T.helpfulness_score(3, 0) == 43.85
    # Confidence grows with evidence at a constant success rate.
    assert (T.helpfulness_score(1, 0) < T.helpfulness_score(10, 0)
            < T.helpfulness_score(100, 0) < 100.0)
    # And a large good record beats a tiny perfect one — the ordering the raw
    # proportion got backwards.
    assert T.helpfulness_score(85, 15) > T.helpfulness_score(5, 0)


def test_evidence_gate_blocks_the_small_sample_exploit():
    """ADR-014: five arranged up-votes must not reach Stage 3.

    The score alone cannot stop this — 5/5 legitimately out-scores the lowered
    Stage-3 threshold — so the vote-volume gate is what has to hold.
    """
    gamer = T.determine_stage(5, 5, T.helpfulness_score(5, 0), 0, 0, 12)
    assert gamer == 3, "score ladder alone still admits the 5-vote record"
    assert T.evidence_capped_stage(gamer, voter_evidence=5) == 2

    # An honest reviewer with real, broad support is unaffected.
    honest = T.determine_stage(20, 20, T.helpfulness_score(85, 15), 0, 0, 12)
    assert T.evidence_capped_stage(honest, voter_evidence=100) == honest


def test_evidence_gate_steps_down_one_stage_at_a_time():
    # Stage 5 needs 200 people of evidence, Stage 4 needs 60, Stage 3 needs 20.
    assert T.evidence_capped_stage(5, voter_evidence=200) == 5
    assert T.evidence_capped_stage(5, voter_evidence=199.5) == 4
    assert T.evidence_capped_stage(5, voter_evidence=59) == 3
    assert T.evidence_capped_stage(5, voter_evidence=19.75) == 2
    # Stages 0-2 gate on posting, not reception — never capped.
    assert T.evidence_capped_stage(2, voter_evidence=0) == 2


def test_evidence_gate_no_longer_accepts_a_row_count():
    """ADR-016: the old keyword is gone, so a caller still handing over
    `helpful + unhelpful` fails loudly instead of re-opening the ring exploit."""
    import pytest

    with pytest.raises(TypeError):
        T.evidence_capped_stage(3, total_votes=20)  # type: ignore[call-arg]


def test_a_voter_is_at_most_one_person_of_evidence():
    """No stage multiplier: a Stage 5 voter is one person, as a Stage 1 is."""
    for stage in (1, 2, 3, 4, 5):
        assert T.voter_evidence_weight(stage, 400, False) == 1.0


def test_zero_weight_voters_carry_no_evidence():
    """§9/§11: every state that zeroes a vote's weight zeroes its evidence."""
    assert T.voter_evidence_weight(0, 400, False) == 0.0                         # Stage 0
    assert T.voter_evidence_weight(4, 400, True) == 0.0                          # probation
    assert T.voter_evidence_weight(4, 400, False, is_claimed_seller=True) == 0.0
    assert T.voter_evidence_weight(4, 400, False, is_suspended=True) == 0.0
    # Probation overrides investigation, as in gate_vote_weight.
    assert T.voter_evidence_weight(4, 400, True, is_under_investigation=True) == 0.0


def test_evidence_halvings_follow_vote_weight():
    assert T.voter_evidence_weight(2, 29, False) == 0.5                          # < 30 days
    assert T.voter_evidence_weight(2, 30, False) == 1.0
    assert T.voter_evidence_weight(2, 400, False, is_under_investigation=True) == 0.5
    assert T.voter_evidence_weight(2, 5, False, is_under_investigation=True) == 0.25


def test_evidence_is_zero_exactly_where_gate_weight_is_zero():
    """The two readings of §11 cannot drift apart: a vote that moves no money
    is never trust evidence, and a vote that does is."""
    import itertools

    for stage, age, probation, investigating, claimed in itertools.product(
            range(6), (0, 29, 30, 400), (False, True), (False, True), (False, True)):
        gate = T.gate_vote_weight(stage, 100.0, age, probation, investigating, claimed)
        evidence = T.voter_evidence_weight(stage, age, probation, investigating, claimed)
        assert (gate == 0) == (evidence == 0), (stage, age, probation, investigating, claimed)


def test_a_fixed_ring_is_its_own_size_in_evidence_at_every_stage():
    """The report's proof of concept, on the pure functions: 4 accounts voting
    once on each of 5 or 50 reviews are 20 or 200 rows but 4 people."""
    for reviews, stage in ((5, 3), (15, 4), (50, 5)):
        ring = [T.VoterRecord(reviews_voted=reviews, evidence=1.0) for _ in range(4)]
        rows = sum(v.reviews_voted for v in ring)
        assert rows >= T.stage_evidence_required(stage), "rows alone met the old gate"
        assert T.evidence_capped_stage(stage, sum(v.evidence for v in ring)) == 2


def test_concentration_flags_a_stable_cohort_without_reciprocity():
    ring = [T.VoterRecord(reviews_voted=5, evidence=1.0) for _ in range(20)]
    c = T.vote_concentration(ring, counted_reviews=5)
    assert (c.cohort_size, c.cohort_rows, c.eligible_rows) == (20, 100, 100)
    assert c.cohort_share == 1.0 and c.holds_promotion


def test_concentration_leaves_broad_support_alone():
    crowd = [T.VoterRecord(reviews_voted=1, evidence=1.0) for _ in range(40)]
    regulars = [T.VoterRecord(reviews_voted=5, evidence=1.0) for _ in range(3)]
    c = T.vote_concentration(crowd + regulars, counted_reviews=5)
    assert c.cohort_size == 3
    assert math.isclose(c.cohort_share, 15 / 55)
    assert not c.holds_promotion


def test_concentration_ignores_ineligible_voters_and_needs_three_reviews():
    # Zero-evidence accounts neither form the cohort nor dilute it.
    ring = [T.VoterRecord(reviews_voted=5, evidence=1.0) for _ in range(20)]
    padding = [T.VoterRecord(reviews_voted=1, evidence=0.0) for _ in range(500)]
    c = T.vote_concentration(ring + padding, counted_reviews=5)
    assert c.distinct_voters == 520 and c.eligible_voters == 20
    assert c.holds_promotion
    # With two reviews, nobody can be a repeat cohort (floor of three).
    pair = [T.VoterRecord(reviews_voted=2, evidence=1.0) for _ in range(30)]
    assert T.vote_concentration(pair, counted_reviews=2).cohort_size == 0


def test_gate_weight_probation_is_zero():
    assert T.gate_vote_weight(4, 90.0, 400, is_on_probation=True) == 0.0


def test_gate_weight_stage0_is_zero():
    assert T.gate_vote_weight(0, 100.0, 400, is_on_probation=False) == 0.0


def test_gate_weight_stage1_flat_quarter():
    assert T.gate_vote_weight(1, 50.0, 400, is_on_probation=False) == 0.25


def test_gate_weight_stage2_scales_with_trust():
    # Stage 2 multiplier 1.0 x trust% (0.8).
    assert math.isclose(T.gate_vote_weight(2, 80.0, 400, is_on_probation=False), 0.8)


def test_gate_weight_new_account_halved():
    full = T.gate_vote_weight(5, 100.0, 400, is_on_probation=False)   # 3.0 x 1.0
    young = T.gate_vote_weight(5, 100.0, 10, is_on_probation=False)   # < 30 days -> halved
    assert math.isclose(full, 3.0)
    assert math.isclose(young, 1.5)

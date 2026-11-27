"""Trust progression & incentive math (ADR-003).

Pure functions. `reputation_score` (the spec's undefined "trust score percentage",
A1) is defined here as a deterministic 0-100 blend so gate vote weights are
testable. Weights are pinned and documented in ADR-003.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.core.constants import ACCOUNT_MATURATION_DAYS, honesty_price_multiplier
from app.services.ranking import COLLUSION_THRESHOLD, wilson_lower_bound

# --- reputation_score weights (ADR-003); components cap at 100 total ---
W_HELPFULNESS = 0.60          # up to 60 pts from helpfulness ratio (0-100)
VOLUME_CAP = 25.0             # up to 25 pts from verified-review volume
VOLUME_COEFF = 10.0           # 10 * log10(1 + n)
BEST_ANSWER_CAP = 15.0        # up to 15 pts from Best Answers
BEST_ANSWER_COEFF = 3.0
STRIKE_PENALTY = 15.0         # per strike

# --- Gate vote-weight multipliers per trust stage (FR-7) ---
STAGE_MULTIPLIER = {0: 0.0, 1: 0.25, 2: 1.0, 3: 1.5, 4: 2.0, 5: 3.0}

# --- Stage helpfulness thresholds (ADR-014) ---
# Re-derived for the Wilson lower bound, which is far stricter than the raw
# proportion these replaced (70/80/90). Values hold the modelled honest cohort at
# its historical pass rate; re-tune from real vote data as it arrives.
STAGE3_HELPFULNESS = 49.5
STAGE4_HELPFULNESS = 72.9
STAGE5_HELPFULNESS = 90.6

# --- Minimum-evidence gate (ADR-014, amended by ADR-016) ---
# A score cannot enforce a sample-size floor: a perfect 5-vote record legitimately
# out-scores a mediocre 40-vote one, so a lowered threshold alone re-admits the
# small-sample exploit. Stages additionally require evidence: 4 x the stage's
# verified-review requirement (20 / 60 / 200), counted in distinct eligible
# PEOPLE, not vote rows. Counted in rows, one fixed ring voting once on each of
# a member's reviews met every threshold (ADR-016).
MIN_VOTES_PER_VERIFIED_REVIEW = 4
STAGE_MIN_VERIFIED_REVIEWS = {3: 5, 4: 15, 5: 50}

# --- Repeated-cohort concentration (ADR-016) ---
# A cohort voter voted on at least COHORT_COVERAGE of a member's counted reviews,
# and on at least COHORT_MIN_REVIEWS of them. When the cohort supplies more than
# CONCENTRATION_HOLD_SHARE of the eligible vote rows, a promotion into the
# evidence-gated stages waits for a moderator. No reciprocity is required: a
# one-way sockpuppet cohort has the same shape as a mutual one.
COHORT_COVERAGE = 0.5
COHORT_MIN_REVIEWS = 3
CONCENTRATION_HOLD_SHARE = COLLUSION_THRESHOLD

# --- What the next stage asks for, in reviews (profile Stats card) ---
# The ladder above is the authority; this is the same ladder read forwards, so a
# member can be told what to do next. Reviews are the only requirement a member
# acts on directly — helpfulness, votes and time follow from posting — so this is
# what the progress bar measures. Stage 1 counts any published review; every
# stage above it counts verified ones.
STAGE_REVIEW_TARGET = {1: 1, 2: 1, 3: 5, 4: 15, 5: 50}
TOP_STAGE = 5


def next_stage_progress(
    stage: int,
    review_count: int,
    verified_review_count: int,
) -> tuple[int, int, int] | None:
    """`(next_stage, have, needed)` — or None at the top of the ladder.

    `have` is clamped to `needed` so a member who already clears the review
    requirement but is held back by helpfulness, votes or time sees a full bar
    rather than one that overflows: the reviews really are done.
    """
    if stage >= TOP_STAGE:
        return None
    nxt = stage + 1
    needed = STAGE_REVIEW_TARGET[nxt]
    have = review_count if nxt == 1 else verified_review_count
    return nxt, min(have, needed), needed


def reputation_score(
    helpfulness_ratio: float,
    verified_review_count: int,
    best_answer_count: int,
    strikes: int,
) -> float:
    """Deterministic trust score in [0, 100]."""
    helpfulness = W_HELPFULNESS * max(0.0, min(100.0, helpfulness_ratio))
    volume = min(VOLUME_CAP, VOLUME_COEFF * math.log10(1 + max(0, verified_review_count)))
    best_answers = min(BEST_ANSWER_CAP, BEST_ANSWER_COEFF * max(0, best_answer_count))
    raw = helpfulness + volume + best_answers - STRIKE_PENALTY * max(0, strikes)
    return max(0.0, min(100.0, raw))


def helpfulness_score(helpful_votes: int, unhelpful_votes: int) -> float:
    """Confidence-corrected helpfulness in [0, 100] (ADR-014).

    Wilson lower bound rather than `helpful / total`, so a small perfect record
    is not scored as a large one: 1/1 -> 20.65, not 100.0. Runs on the
    denormalized vote counters, keeping `recompute_user_trust` a single cheap
    aggregate rather than a per-vote scan on a write path.
    """
    total = max(0, helpful_votes) + max(0, unhelpful_votes)
    if total <= 0:
        return 0.0
    return round(100.0 * wilson_lower_bound(max(0, helpful_votes), total), 2)


def determine_stage(
    review_count: int,
    verified_review_count: int,
    helpfulness_ratio: float,
    best_answer_count: int,
    strikes: int,
    months_active: float,
) -> int:
    """Highest trust stage the *score* unlocks (FR-7). Returns 0..5.

    Thresholds are ADR-014 values, sized for `helpfulness_score`. This is the
    score ladder only — callers must additionally apply `evidence_capped_stage`
    so that vote volume, not just score, is required to climb.
    """
    if (verified_review_count >= 50 and helpfulness_ratio >= STAGE5_HELPFULNESS
            and months_active >= 6):
        return 5
    if (verified_review_count >= 15 and strikes == 0
            and best_answer_count >= 3 and helpfulness_ratio >= STAGE4_HELPFULNESS):
        return 4
    if verified_review_count >= 5 and helpfulness_ratio >= STAGE3_HELPFULNESS:
        return 3
    if verified_review_count >= 1:
        return 2
    if review_count >= 1:
        return 1
    return 0


def stage_evidence_required(stage: int) -> int:
    """Distinct eligible voters a stage needs (Stages 3+ only)."""
    return MIN_VOTES_PER_VERIFIED_REVIEW * STAGE_MIN_VERIFIED_REVIEWS[stage]


def evidence_capped_stage(stage: int, voter_evidence: float) -> int:
    """Cap a score-derived stage at what the voter evidence supports (ADR-014/016).

    Stages 3+ require `stage_evidence_required` in *voter evidence*: the sum of
    `voter_evidence_weight` over the DISTINCT people who voted on the member's
    counted reviews — never the number of vote rows. A person who voted on all
    fifty of a member's reviews is one person of evidence, so a ring must grow
    with the stage it wants rather than reuse itself (4 accounts once reached
    Stage 5). Stages 0-2 are unaffected: they gate on posting, not reception.

    The parameter was `total_votes` before ADR-016. It was renamed, not kept,
    so a caller still passing a row count fails loudly instead of quietly.
    """
    capped = stage
    while capped >= 3:
        if voter_evidence >= stage_evidence_required(capped):
            break
        capped -= 1
    return capped


def voter_evidence_weight(
    trust_stage: int,
    account_age_days: int,
    is_on_probation: bool,
    is_under_investigation: bool = False,
    is_claimed_seller: bool = False,
    is_suspended: bool = False,
) -> float:
    """How much one distinct voter counts toward a member's stage evidence.

    At most 1.0 — one person — however many of the member's reviews they voted
    on and whatever their own stage: a stage multiplier here would let a few
    high-stage accounts stand in for a crowd. Otherwise it follows Business
    Rules §11 exactly as `gate_vote_weight` does: zero for a claimed seller,
    confirmed probation or a Stage 0 account (the votes that carry no weight
    anywhere), and for a suspended account; halved under 30 days old; halved
    under investigation. `account_age_days` is the age when the vote was cast,
    the moment §11's own weight is taken.
    """
    if is_claimed_seller or is_on_probation or is_suspended or trust_stage <= 0:
        return 0.0
    weight = 1.0
    if account_age_days < ACCOUNT_MATURATION_DAYS:
        weight *= 0.5
    if is_under_investigation:
        weight *= 0.5
    return weight


@dataclass(frozen=True)
class VoterRecord:
    """One distinct voter's part in a member's history."""

    reviews_voted: int   # how many of the member's counted reviews they voted on
    evidence: float      # voter_evidence_weight, 0..1


@dataclass(frozen=True)
class Concentration:
    """How much of a member's vote evidence one stable cohort supplies."""

    distinct_voters: int      # every distinct voter, eligible or not
    eligible_voters: int      # voters whose evidence is above zero
    voter_evidence: float     # the sum `evidence_capped_stage` is given
    eligible_rows: int        # vote rows cast by eligible voters
    cohort_size: int          # eligible voters on >= COHORT_COVERAGE of the reviews
    cohort_rows: int          # vote rows the cohort cast
    cohort_share: float       # cohort_rows / eligible_rows
    top_voter_reviews: int    # the most reviews any one eligible voter voted on

    @property
    def holds_promotion(self) -> bool:
        return self.cohort_size > 0 and self.cohort_share > CONCENTRATION_HOLD_SHARE


def vote_concentration(voters: Iterable[VoterRecord], counted_reviews: int) -> Concentration:
    """Repeated-cohort concentration across a member's whole history (ADR-016).

    Per review, a ring looks like a handful of ordinary votes; only across the
    history does the same cohort keep appearing. Reciprocity is not required.
    """
    voters = list(voters)
    eligible = [v for v in voters if v.evidence > 0]
    floor = max(COHORT_MIN_REVIEWS, math.ceil(COHORT_COVERAGE * max(0, counted_reviews)))
    cohort = [v for v in eligible if v.reviews_voted >= floor]
    eligible_rows = sum(v.reviews_voted for v in eligible)
    cohort_rows = sum(v.reviews_voted for v in cohort)
    return Concentration(
        distinct_voters=len(voters),
        eligible_voters=len(eligible),
        voter_evidence=sum(v.evidence for v in voters),
        eligible_rows=eligible_rows,
        cohort_size=len(cohort),
        cohort_rows=cohort_rows,
        cohort_share=(cohort_rows / eligible_rows) if eligible_rows else 0.0,
        top_voter_reviews=max((v.reviews_voted for v in eligible), default=0),
    )


def gate_vote_weight(
    trust_stage: int,
    reputation_score_value: float,
    account_age_days: int,
    is_on_probation: bool,
    is_under_investigation: bool = False,
    is_claimed_seller: bool = False,
) -> float:
    """The backend weight of one vote (Business Rules §11).

    Stage 0 = 0. Stage 1 = flat 0.25. Stage 2+ = multiplier x trust%. Accounts
    under 30 days: halved, regardless of stage. Under investigation (unconfirmed):
    halved. Confirmed probation: zero, overriding investigation. A claimed
    seller: zero, permanently, on everything.
    """
    if is_claimed_seller or is_on_probation or trust_stage <= 0:
        return 0.0
    if trust_stage == 1:
        weight = STAGE_MULTIPLIER[1]
    else:
        trust_pct = max(0.0, min(100.0, reputation_score_value)) / 100.0
        weight = STAGE_MULTIPLIER.get(trust_stage, 0.0) * trust_pct
    if account_age_days < ACCOUNT_MATURATION_DAYS:
        weight *= 0.5
    if is_under_investigation:
        weight *= 0.5
    return weight


def weight_of(user, now=None) -> float:
    """`gate_vote_weight` for a user row, at `now` (defaults to the present).
    A suspended account weighs nothing while suspended (owner decision)."""
    from datetime import UTC, datetime
    if getattr(user, "is_suspended", False):
        return 0.0
    now = now or datetime.now(UTC)
    created = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=UTC)
    return gate_vote_weight(
        user.trust_stage, float(user.reputation_score or 0), max(0, (now - created).days),
        bool(user.is_on_probation), bool(getattr(user, "is_under_investigation", False)),
        bool(getattr(user, "is_claimed_seller", False)))


def honesty_score(trust_weighted_helpful_votes: Decimal, price_php: Decimal) -> Decimal:
    """Honesty Score = trust-weighted helpfulness votes x price-bracket multiplier (FR-6)."""
    return Decimal(trust_weighted_helpful_votes) * honesty_price_multiplier(Decimal(price_php))

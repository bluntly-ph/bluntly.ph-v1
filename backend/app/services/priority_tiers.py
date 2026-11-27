"""Admin queue priority tiers — the pure evaluator (dev note, 2026-09-26).

WHAT THIS IS NOT. It is not how an item enters a queue. Content reaches the
moderation queue at 3+ independent reports or one report from a Stage 4+
reviewer, and a review reaches the earn_eligible queue through the gate
(earn_gate.maybe_queue); both rules are untouched. A tier is computed only for
an item that is ALREADY in a queue, and only sorts, filters and labels it. An
admin can still open and decide any item in any order.

It is also separate from `moderation_priority` (lanes, SLA, integrity score),
which deliberately keeps the author's trust stage and the Wilson score out of
its inputs. The tiers are a triage layer the owner asked for on top of it, and
they use exactly those signals.

THE RULES (dev note):

Three "risk signals" can converge:

* A — the Wilson lower bound sits in the band around the 0.65 gate
  (0.60–0.70 by default);
* B — at least one upvoter is High or Critical risk;
* C — 2 or more fraud/counterfeit reports.

Highest: two or more of A, B, C at once. One signal alone never reaches it.
High:    exactly one of A, B, C; or exactly one fraud report (the single-report
         signal, which does not converge); or — unconditionally — the first
         submission ever from a Stage 0 account. That last rule can make an
         item High but never Highest on its own.
Low:     author at the Low stage (3) or above, zero reports of any kind, no
         High/Critical voter anywhere in the author's received votes, and a
         Wilson trend that is stable or rising.
Lowest:  the same, with the author at the Lowest stage (4 or 5). The UI calls it
         a routine spot-check; it is a label, not a different check.
Neutral: everything else.

AGING: an item left untouched (no approve, reject, resolve or other decision)
past the aging window moves up exactly one tier, once — Lowest to Low, Low to
Neutral, Neutral to High, High to Highest. It never jumps. Opening or
previewing an item is not a decision and records nothing. The hourly job
decides WHEN an item has aged (`priority_triage`); this module only applies it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from app.services.priority_settings import TierConfig


class Tier(str, enum.Enum):
    highest = "highest"
    high = "high"
    neutral = "neutral"
    low = "low"
    lowest = "lowest"


#: Most urgent first — the sort order.
TIER_ORDER: tuple[Tier, ...] = (Tier.highest, Tier.high, Tier.neutral, Tier.low, Tier.lowest)
TIER_RANK: dict[Tier, int] = {tier: i for i, tier in enumerate(TIER_ORDER)}

TIER_LABELS: dict[Tier, str] = {
    Tier.highest: "Highest",
    Tier.high: "High",
    Tier.neutral: "Neutral",
    Tier.low: "Low",
    Tier.lowest: "Lowest",
}


class VoterRisk(str, enum.Enum):
    baseline = "baseline"
    elevated = "elevated"
    high = "high"
    critical = "critical"


FLAGGED_RISKS = frozenset({VoterRisk.high, VoterRisk.critical})


class Trend(str, enum.Enum):
    rising = "rising"
    stable = "stable"
    falling = "falling"
    #: No weighted votes, or none before the trend window: nothing moved.
    unknown = "unknown"


@dataclass(frozen=True)
class TierFacts:
    """Already-loaded inputs for one queued item. No PII, no telemetry."""

    #: The gate's weighted Wilson lower bound; None where no Wilson applies
    #: (a reported comment, question, answer, seller review or account).
    wilson_lower_bound: float | None
    trend: Trend
    #: Upvoters of THIS item classified High or Critical.
    flagged_upvoters: int
    #: High/Critical voters anywhere in the author's received votes.
    author_history_flagged_voters: int
    author_stage: int | None
    #: This is the author's first submission of its kind, ever.
    first_submission: bool
    #: Every report on the item, user-filed or system-detected, open or not.
    report_count: int
    #: User reports in a fraud/counterfeit reason (one per reporter).
    fraud_reports: int


@dataclass(frozen=True)
class TierReason:
    code: str
    label: str
    detail: str


@dataclass(frozen=True)
class TierAssessment:
    tier: Tier
    base_tier: Tier
    aged: bool
    reasons: tuple[TierReason, ...]

    @property
    def routine_spot_check(self) -> bool:
        return self.tier is Tier.lowest


def escalate_one(tier: Tier) -> Tier:
    """Exactly one step toward Highest; Highest stays Highest."""
    return TIER_ORDER[max(0, TIER_RANK[tier] - 1)]


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def evaluate(facts: TierFacts, config: TierConfig, *, aged: bool = False) -> TierAssessment:
    """The tier for one queued item, and every reason it got it."""
    lb = facts.wilson_lower_bound
    signal_a = lb is not None and config.wilson_band_low <= lb <= config.wilson_band_high
    signal_b = facts.flagged_upvoters > 0
    signal_c = facts.fraud_reports >= config.fraud_convergence_min
    single_fraud = config.fraud_high_min <= facts.fraud_reports < config.fraud_convergence_min
    stage0_first = facts.author_stage == 0 and facts.first_submission

    reasons: list[TierReason] = []
    if signal_a:
        reasons.append(TierReason(
            "wilson_band", "Wilson near threshold",
            f"The gate's Wilson lower bound is {_fmt(lb)}, inside "
            f"{_fmt(config.wilson_band_low)}–{_fmt(config.wilson_band_high)} "
            "around the 0.65 gate."))
    if signal_b:
        reasons.append(TierReason(
            "risky_upvoter", "High-risk upvoter",
            f"{facts.flagged_upvoters} upvoter(s) classified High or Critical risk."))
    if signal_c:
        reasons.append(TierReason(
            "fraud_reports", f"{facts.fraud_reports} fraud reports",
            f"{facts.fraud_reports} reports in a fraud or counterfeit reason "
            f"(Highest needs {config.fraud_convergence_min}+ together with another signal)."))
    if single_fraud:
        reasons.append(TierReason(
            "fraud_report", "1 fraud report",
            "One report in a fraud or counterfeit reason."))
    if stage0_first:
        reasons.append(TierReason(
            "stage0_first_submission", "New account's first submission",
            "A Stage 0 account's first-ever submission is at least High."))

    converging = sum((signal_a, signal_b, signal_c))
    if converging >= 2:
        base = Tier.highest
    elif converging == 1 or single_fraud or stage0_first:
        base = Tier.high
    else:
        stage = facts.author_stage if facts.author_stage is not None else -1
        clean = (facts.report_count == 0
                 and facts.author_history_flagged_voters == 0
                 and facts.trend in (Trend.stable, Trend.rising, Trend.unknown))
        if clean and stage >= config.lowest_min_stage:
            base = Tier.lowest
            reasons.append(TierReason(
                "routine_trusted", "Routine spot-check",
                f"Stage {stage} author, no reports, no flagged voters in their history, "
                f"Wilson trend {facts.trend.value}."))
        elif clean and stage >= config.low_min_stage:
            base = Tier.low
            reasons.append(TierReason(
                "trusted_author", "Trusted author, clean record",
                f"Stage {stage} author, no reports, no flagged voters in their history, "
                f"Wilson trend {facts.trend.value}."))
        else:
            base = Tier.neutral
            why = []
            if facts.report_count > 0:
                why.append(f"{facts.report_count} report(s)")
            if facts.author_history_flagged_voters > 0:
                why.append("a flagged voter in the author's history")
            if facts.trend is Trend.falling:
                why.append("a falling Wilson trend")
            if stage < config.low_min_stage:
                why.append(f"author at Stage {stage if stage >= 0 else '—'}")
            reasons.append(TierReason(
                "no_signal", "No elevated signal",
                "Plain queue order" + (f" ({', '.join(why)})." if why else ".")))

    tier = base
    if aged:
        tier = escalate_one(base)
        reasons.append(TierReason(
            "aged", "Aged one tier",
            f"Untouched past the {config.aging_hours}-hour aging window: "
            f"{TIER_LABELS[base]} → {TIER_LABELS[tier]}."))
    return TierAssessment(tier=tier, base_tier=base, aged=aged, reasons=tuple(reasons))

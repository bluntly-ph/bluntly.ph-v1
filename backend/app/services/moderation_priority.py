"""Canonical, explainable review-priority policy (design §5).

This module is pure: it takes already-loaded facts and returns an assessment.
It never queries a database, never mutates content/trust/votes/funds, and
never imports reading telemetry (design §1, §11; enforced by
``tests/test_telemetry_isolation.py``). Reading time, scroll depth,
interaction timing, geography, Wilson score, and star rating are not inputs.

Business Rules §12 and §18 (policy v2):

* A report is a trust-weighted vote toward "escalate": the REPORTERS' weights
  (computed upstream, with the repeated-unfounded penalty) sum to ONE threshold.
* Report reason carries its own urgency: safety and personal-information
  (doxxing-adjacent) reports escalate at once, whatever their weight or volume.
* A burst of reports, and a surge of raw activity (views, comments, upvotes),
  count relative to THAT review's own baseline — never as lifetime totals.
* Automated signals feed the same queue, and every assessment says where its
  evidence came from: ``user_reported`` and/or ``system_detected``.
* The AUTHOR's reputation, trust stage and verification status stay excluded,
  so a moderator judges the content, not who posted it.

Later slices (queue batching, persistence, UI) consume ``evaluate_priority``
without re-implementing any of this scoring.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.enums import ModerationReason

POLICY_VERSION = "review-priority-v2"


class PriorityLane(str, enum.Enum):
    """Mutually exclusive operational routing, in precedence order."""

    escalated = "escalated"
    reported = "reported"
    integrity = "integrity"
    routine = "routine"
    # Separate second-review sampling of completed decisions (design §8).
    # Never assigned by this review-submission evaluator.
    quality_audit = "quality_audit"


class PriorityBand(str, enum.Enum):
    high = "high"
    normal = "normal"
    low = "low"


class SlaState(str, enum.Enum):
    on_track = "on_track"
    approaching = "approaching"
    overdue = "overdue"


@dataclass(frozen=True)
class PriorityFacts:
    """Already-loaded inputs for one queue candidate. No PII, no telemetry."""

    queued_at: datetime
    report_count: int
    report_reasons: frozenset[ModerationReason]
    edited_since_monetized: bool
    velocity: bool
    collusion: bool
    duplicate_content: bool
    manually_escalated: bool = False
    #: Sum of the open reports' reporter weights (§12). Defaults keep v1 callers valid.
    weighted_reports: float = 0.0
    #: A report reason that escalates on its own (safety, personal information).
    urgent_report: bool = False
    #: Reports arrived in a burst against this review's own baseline (§12).
    report_surge: bool = False
    #: Views/comments/upvotes surging against this review's own baseline (§18).
    activity_surge: bool = False
    #: The verdict flatly contradicts the stars outside the tie-break (§14).
    verdict_star_mismatch: bool = False
    #: Open SYSTEM_DETECTED reports on this review.
    system_reports: int = 0


@dataclass(frozen=True)
class PriorityFactor:
    code: str
    observed: bool | int | str
    contribution: int
    explanation: str


@dataclass(frozen=True)
class PriorityAssessment:
    policy_version: str
    lane: PriorityLane
    integrity_score: int
    band: PriorityBand
    sla_state: SlaState
    due_at: datetime
    factors: tuple[PriorityFactor, ...]
    order_key: tuple[int, int, int, datetime, datetime]
    #: §12: where the evidence came from — "user_reported", "system_detected".
    origins: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Policy constants (design §5)
# --------------------------------------------------------------------------- #

_SCORE_CAP = 100
_HIGH_SCORE_THRESHOLD = 40
_NORMAL_SCORE_THRESHOLD = 15
_APPROACHING_FRACTION = 0.75

_SLA_TARGETS: dict[PriorityLane, timedelta] = {
    PriorityLane.escalated: timedelta(hours=1),
    PriorityLane.reported: timedelta(hours=4),
    PriorityLane.integrity: timedelta(hours=8),
    PriorityLane.routine: timedelta(hours=24),
    PriorityLane.quality_audit: timedelta(hours=72),
}

_LANE_RANK: dict[PriorityLane, int] = {
    PriorityLane.escalated: 0,
    PriorityLane.reported: 1,
    PriorityLane.integrity: 2,
    PriorityLane.routine: 3,
    PriorityLane.quality_audit: 4,
}

_SLA_RANK: dict[SlaState, int] = {
    SlaState.overdue: 0,
    SlaState.approaching: 1,
    SlaState.on_track: 2,
}

#: §12: the trust-weighted report sum that escalates on its own. A Stage 2 voter
#: at full reputation weighs 1.0 (trust.STAGE_MULTIPLIER), so one well-trusted
#: reporter — or several lighter ones together — reaches it.
REPORT_ESCALATION_THRESHOLD = 1.0

#: §12: "safety and doxxing-adjacent reports escalate near-immediately
#: regardless of anything else".
URGENT_REASONS = frozenset({ModerationReason.safety_threat,
                            ModerationReason.personal_information})

# Highest tier first: only the highest-tier report reason applies, regardless
# of how many reports carry it (design §5.1).
_REPORT_REASON_TIERS: tuple[tuple[int, tuple[ModerationReason, ...]], ...] = (
    (40, (ModerationReason.safety_threat, ModerationReason.personal_information)),
    (20, (ModerationReason.fake_proof, ModerationReason.counterfeit,
          ModerationReason.harassment)),
    (15, (ModerationReason.seller_posing_as_buyer, ModerationReason.plagiarized)),
    (10, (ModerationReason.conflict_of_interest,)),
    (5, (ModerationReason.spam,)),
    (0, (ModerationReason.other,)),
)

_REPORT_REASON_LABELS: dict[ModerationReason, str] = {
    ModerationReason.fake_proof: "fake proof of purchase",
    ModerationReason.counterfeit: "a counterfeit product",
    ModerationReason.harassment: "harassment",
    ModerationReason.safety_threat: "a threat to someone's safety",
    ModerationReason.personal_information: "someone's personal information",
    ModerationReason.seller_posing_as_buyer: "a seller posing as a buyer",
    ModerationReason.plagiarized: "plagiarized content",
    ModerationReason.conflict_of_interest: "an undisclosed conflict of interest",
    ModerationReason.spam: "spam",
    ModerationReason.other: "an unspecified concern",
}


def _to_utc(value: datetime, name: str) -> datetime:
    """Reject naive input; normalize any timezone-aware input to UTC.

    Every timestamp this module produces — ``due_at`` and the two datetimes in
    ``order_key`` — must be UTC regardless of what the caller passed in, so a
    later comparison or serialization never has to reconcile mixed offsets.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _weighted_report_factor(facts: PriorityFacts) -> PriorityFactor | None:
    """§12: reports are weighted votes toward escalation, summed to one threshold."""
    if facts.report_count <= 0:
        return None
    weight = round(facts.weighted_reports, 2)
    if weight >= REPORT_ESCALATION_THRESHOLD:
        return PriorityFactor(
            code="report_weight_threshold", observed=str(weight), contribution=35,
            explanation=(f"Trust-weighted reports reached the escalation threshold "
                         f"({weight} of {REPORT_ESCALATION_THRESHOLD})."))
    if weight > 0:
        return PriorityFactor(
            code="report_weight_partial", observed=str(weight),
            contribution=max(5, round(25 * weight / REPORT_ESCALATION_THRESHOLD)),
            explanation=(f"Trust-weighted reports are at {weight} of the "
                         f"{REPORT_ESCALATION_THRESHOLD} threshold."))
    return PriorityFactor(
        code="report_unweighted", observed=facts.report_count, contribution=5,
        explanation="Reported by accounts whose reports carry no weight yet.")


def _report_reason_factor(
    report_reasons: frozenset[ModerationReason],
) -> PriorityFactor | None:
    if not report_reasons:
        return None
    for contribution, reasons in _REPORT_REASON_TIERS:
        winner = next((reason for reason in reasons if reason in report_reasons), None)
        if winner is not None:
            return PriorityFactor(
                code=f"report_reason_{winner.value}",
                observed=winner.value,
                contribution=contribution,
                explanation=(
                    f"The most serious report reason is {_REPORT_REASON_LABELS[winner]}."
                ),
            )
    return None


def _system_detected(facts: PriorityFacts) -> bool:
    return bool(facts.edited_since_monetized or facts.velocity or facts.collusion
                or facts.duplicate_content or facts.verdict_star_mismatch
                or facts.activity_surge or facts.system_reports > 0)


def origins_for(facts: PriorityFacts) -> tuple[str, ...]:
    """§12: every queue item is labelled by origin, never left ambiguous."""
    origins: list[str] = []
    if facts.report_count > 0:
        origins.append("user_reported")
    if _system_detected(facts):
        origins.append("system_detected")
    return tuple(origins)


def _lane_for(facts: PriorityFacts) -> PriorityLane:
    if (facts.manually_escalated or facts.urgent_report
            or bool(facts.report_reasons & URGENT_REASONS)
            or (facts.report_count > 0
                and facts.weighted_reports >= REPORT_ESCALATION_THRESHOLD)):
        return PriorityLane.escalated
    if facts.report_count > 0:
        return PriorityLane.reported
    if _system_detected(facts):
        return PriorityLane.integrity
    return PriorityLane.routine


def _sla_state_for(*, elapsed: timedelta, target: timedelta) -> SlaState:
    if elapsed >= target:
        return SlaState.overdue
    if elapsed >= target * _APPROACHING_FRACTION:
        return SlaState.approaching
    return SlaState.on_track


def _band_for(*, lane: PriorityLane, sla_state: SlaState, integrity_score: int) -> PriorityBand:
    if lane is PriorityLane.escalated or sla_state is SlaState.overdue \
            or integrity_score >= _HIGH_SCORE_THRESHOLD:
        return PriorityBand.high
    if sla_state is SlaState.approaching or integrity_score >= _NORMAL_SCORE_THRESHOLD:
        return PriorityBand.normal
    return PriorityBand.low


def evaluate_priority(facts: PriorityFacts, *, now: datetime) -> PriorityAssessment:
    """Evaluate one already-loaded candidate against policy v1.

    Raises ``ValueError`` if ``facts.queued_at`` or ``now`` is a naive
    datetime — SLA math must never silently assume a timezone. Any other
    timezone-aware input is normalized to UTC before use, so ``due_at`` and
    ``order_key`` always carry UTC timestamps regardless of the caller's
    offset.
    """
    queued_at = _to_utc(facts.queued_at, "facts.queued_at")
    now = _to_utc(now, "now")

    factors: list[PriorityFactor] = []
    if facts.edited_since_monetized:
        factors.append(PriorityFactor(
            code="edited_after_monetization", observed=True, contribution=40,
            explanation="The review was edited after its product started earning commission.",
        ))
    if facts.collusion:
        factors.append(PriorityFactor(
            code="collusion", observed=True, contribution=35,
            explanation="A voting-collusion advisory fired for this review.",
        ))
    if facts.duplicate_content:
        factors.append(PriorityFactor(
            code="duplicate_content", observed=True, contribution=30,
            explanation="The review body closely matches another review.",
        ))
    if facts.velocity:
        factors.append(PriorityFactor(
            code="vote_velocity", observed=True, contribution=15,
            explanation="An unusual vote-velocity advisory fired for this review.",
        ))
    if facts.verdict_star_mismatch:
        factors.append(PriorityFactor(
            code="verdict_star_mismatch", observed=True, contribution=15,
            explanation="The verdict contradicts the star rating (outside the "
                        "\"it's complicated\" tie-break).",
        ))
    if facts.system_reports > 0:
        factors.append(PriorityFactor(
            code="system_detected", observed=facts.system_reports, contribution=20,
            explanation="An automated fraud or collusion check flagged this review.",
        ))
    if facts.activity_surge:
        factors.append(PriorityFactor(
            code="activity_surge", observed=True, contribution=10,
            explanation="Views, comments or upvotes are surging against this "
                        "review's own normal level.",
        ))
    if facts.report_surge:
        factors.append(PriorityFactor(
            code="report_surge", observed=True, contribution=20,
            explanation="Reports arrived in a burst, far above this review's own "
                        "normal rate.",
        ))
    weighted_factor = _weighted_report_factor(facts)
    if weighted_factor is not None:
        factors.append(weighted_factor)
    report_reason_factor = _report_reason_factor(facts.report_reasons)
    if report_reason_factor is not None:
        factors.append(report_reason_factor)

    integrity_score = min(_SCORE_CAP, sum(factor.contribution for factor in factors))

    lane = _lane_for(facts)
    target = _SLA_TARGETS[lane]
    due_at = queued_at + target
    sla_state = _sla_state_for(elapsed=now - queued_at, target=target)
    band = _band_for(lane=lane, sla_state=sla_state, integrity_score=integrity_score)

    order_key = (
        _LANE_RANK[lane],
        _SLA_RANK[sla_state],
        -integrity_score,
        due_at,
        queued_at,
    )

    return PriorityAssessment(
        policy_version=POLICY_VERSION,
        lane=lane,
        integrity_score=integrity_score,
        band=band,
        sla_state=sla_state,
        due_at=due_at,
        factors=tuple(factors),
        order_key=order_key,
        origins=origins_for(facts),
    )

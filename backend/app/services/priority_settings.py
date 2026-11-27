"""The admin priority tiers' tunable thresholds (dev note, 2026-09-26).

"None of these are final. Expect to retune all four once we're looking at real
queue volume post-launch, ideally without a redeploy each time." So the
numbers live in `platform_settings` under one key, and the code carries only
the defaults the note starts from. A missing or partial row falls back to the
defaults key by key; an invalid saved value is refused on save, never
half-applied.

Defaults:

* Wilson band 0.60–0.70 — centred on the 0.65 earn_eligible gate, ±0.05.
* Fraud reports: 1 is a High signal on its own, 2 or more is a convergence
  signal toward Highest. "Fraud" means the fraud and counterfeit reasons.
* Aging: 72 hours, the conservative end of the note's 48–72 hour window. No
  newer meeting decision fixes one number, so it is provisional.
* Low needs an author at Stage 3 or above; Lowest at Stage 4 or above.
* Wilson trend: the gate's weighted lower bound now against the same bound
  before the last 7 days; a drop of more than 0.02 is "falling".
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import ModerationReason
from app.models.triage import PlatformSetting

SETTINGS_KEY = "priority_tiers"

#: The report reasons that count as "fraud or counterfeit" (dev note, Tier 1).
DEFAULT_FRAUD_REASONS: tuple[str, ...] = (
    ModerationReason.fake_proof.value,
    ModerationReason.seller_posing_as_buyer.value,
    ModerationReason.counterfeit.value,
)


@dataclass(frozen=True)
class TierConfig:
    wilson_band_low: float = 0.60
    wilson_band_high: float = 0.70
    #: At least this many fraud reports is a (single) High signal.
    fraud_high_min: int = 1
    #: At least this many is the fraud signal that converges toward Highest.
    fraud_convergence_min: int = 2
    aging_hours: int = 72
    low_min_stage: int = 3
    lowest_min_stage: int = 4
    trend_window_days: int = 7
    trend_tolerance: float = 0.02
    fraud_reasons: tuple[str, ...] = field(default=DEFAULT_FRAUD_REASONS)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["fraud_reasons"] = list(self.fraud_reasons)
        return data


DEFAULTS = TierConfig()


def _invalid(detail: str) -> AppError:
    return AppError(detail, code="invalid_priority_settings", status_code=422,
                    title="Invalid priority settings")


def _validated(data: dict) -> TierConfig:
    """Build a TierConfig from saved/patched values, refusing nonsense.

    The checks are the ones that would otherwise make a tier meaningless: an
    empty or inverted Wilson band, a convergence threshold below the single
    signal, a Lowest boundary under Low, a non-positive aging window.
    """
    merged = {**DEFAULTS.as_dict(), **{k: v for k, v in data.items() if v is not None}}
    unknown = set(merged) - set(DEFAULTS.as_dict())
    if unknown:
        raise _invalid(f"Unknown setting(s): {', '.join(sorted(unknown))}.")
    try:
        cfg = TierConfig(
            wilson_band_low=float(merged["wilson_band_low"]),
            wilson_band_high=float(merged["wilson_band_high"]),
            fraud_high_min=int(merged["fraud_high_min"]),
            fraud_convergence_min=int(merged["fraud_convergence_min"]),
            aging_hours=int(merged["aging_hours"]),
            low_min_stage=int(merged["low_min_stage"]),
            lowest_min_stage=int(merged["lowest_min_stage"]),
            trend_window_days=int(merged["trend_window_days"]),
            trend_tolerance=float(merged["trend_tolerance"]),
            fraud_reasons=tuple(str(r) for r in merged["fraud_reasons"]),
        )
    except (TypeError, ValueError) as exc:
        raise _invalid("Every setting must be a number, except the fraud reasons.") from exc
    if not 0.0 <= cfg.wilson_band_low < cfg.wilson_band_high <= 1.0:
        raise _invalid("The Wilson band must satisfy 0 ≤ low < high ≤ 1.")
    if cfg.fraud_high_min < 1 or cfg.fraud_convergence_min < cfg.fraud_high_min:
        raise _invalid("Fraud thresholds need 1 ≤ single-signal ≤ convergence.")
    if not 1 <= cfg.aging_hours <= 24 * 30:
        raise _invalid("The aging window must be between 1 hour and 30 days.")
    if not 0 <= cfg.low_min_stage <= cfg.lowest_min_stage <= 5:
        raise _invalid("Stage boundaries need 0 ≤ Low ≤ Lowest ≤ 5.")
    if not 1 <= cfg.trend_window_days <= 90 or not 0 <= cfg.trend_tolerance <= 0.5:
        raise _invalid("The trend window is 1–90 days and its tolerance 0–0.5.")
    valid_reasons = {r.value for r in ModerationReason}
    bad = [r for r in cfg.fraud_reasons if r not in valid_reasons]
    if bad or not cfg.fraud_reasons:
        raise _invalid("Fraud reasons must be one or more report reasons.")
    return cfg


def load(db: Session) -> TierConfig:
    """The current thresholds: the saved row over the defaults."""
    row = db.get(PlatformSetting, SETTINGS_KEY)
    if row is None or not isinstance(row.value, dict):
        return DEFAULTS
    try:
        return _validated(row.value)
    except AppError:
        # A row that no longer validates (a reason renamed, say) must not take
        # the queues down: fall back to the defaults the code ships with.
        return DEFAULTS


def update(db: Session, patch: dict, *, admin_id: uuid.UUID) -> TierConfig:
    """Save a partial change. Validated as a whole before anything is written."""
    current = load(db).as_dict()
    cfg = _validated({**current, **patch})
    row = db.get(PlatformSetting, SETTINGS_KEY)
    if row is None:
        row = PlatformSetting(key=SETTINGS_KEY, value=cfg.as_dict())
        db.add(row)
    else:
        row.value = cfg.as_dict()
    row.updated_at = datetime.now(UTC)
    row.updated_by = admin_id
    db.commit()
    return cfg

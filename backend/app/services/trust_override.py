"""An administrator's override of a member's Honesty Score (0095, owner 2026-10-05).

The algorithm keeps computing the score (trust_service writes
`computed_reputation_score`). An override replaces it; clearing the override
returns to the computed value:

    effective = override if set else computed      (users.reputation_score)

`reputation_score` stays the effective value, so every reader - vote weight,
review lenses, the Honesty Fund, profiles, cards - follows the override with no
second code path. Scale 0..100 (ADR-003), two decimals.

Trust STAGE (Newcomer … Community Expert) is NOT derived from the score: it
comes from review counts, verified reviews, helpfulness, best answers, strikes,
tenure and voter evidence (trust.determine_stage). An override therefore moves
the Honesty Score and what it weighs, never the stage name.

Every set, change and clear needs a reason and writes one audit row
(moderation_logs, action=override, target the member) with the before and after
values in `context`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.models.enums import ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.user import User

MIN_SCORE = Decimal("0")
MAX_SCORE = Decimal("100")


@dataclass(frozen=True)
class TrustScoreState:
    user_id: uuid.UUID
    computed: Decimal
    override: Decimal | None
    effective: Decimal
    reason: str | None
    overridden_at: datetime | None
    overridden_by_id: uuid.UUID | None

    @property
    def is_overridden(self) -> bool:
        return self.override is not None


CENT = Decimal("0.01")


def _score(value) -> Decimal:
    """Two decimals always ("0.00", not "0": a zero Decimal is falsy)."""
    return Decimal(str(value if value is not None else 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def state_of(user: User) -> TrustScoreState:
    return TrustScoreState(
        user_id=user.id,
        computed=_score(user.computed_reputation_score),
        override=(_score(user.reputation_score_override)
                  if user.reputation_score_override is not None else None),
        effective=_score(user.reputation_score),
        reason=user.reputation_override_reason,
        overridden_at=user.reputation_override_at,
        overridden_by_id=user.reputation_override_by_id,
    )


def _invalid(message: str, code: str) -> AppError:
    return AppError(message, code=code, status_code=422, title="Invalid score")


def set_override(db: Session, actor: User, user_id: uuid.UUID,
                 score: Decimal | float | str | None, reason: str) -> TrustScoreState:
    """Set or change the override (`score`), or clear it (`score=None`).

    Commits. Refuses an unknown member (404), the actor's own score, a blank
    reason and a score outside 0..100 (422). A no-op (same value, or clearing
    when nothing is set) changes nothing and writes no audit row.
    """
    target = db.get(User, user_id, with_for_update=True)
    if target is None:
        raise NotFoundError("Person not found.", code="person_not_found")
    if target.id == actor.id:
        raise AppError("You cannot change your own Honesty Score.", code="self_decision",
                       status_code=422, title="Invalid decision")
    why = (reason or "").strip()
    if len(why) < 3:
        raise _invalid("Say why the score is being changed.", "reason_required")

    new: Decimal | None = None
    if score is not None:
        try:
            new = Decimal(str(score)).quantize(CENT, rounding=ROUND_HALF_UP)
        except Exception as exc:  # noqa: BLE001 - any unparsable value is a 422
            raise _invalid("The score must be a number from 0 to 100.",
                           "score_out_of_range") from exc
        if not new.is_finite() or new < MIN_SCORE or new > MAX_SCORE:
            raise _invalid("The score must be a number from 0 to 100.", "score_out_of_range")

    before = state_of(target)
    if before.override == new:
        return before

    target.reputation_score_override = new
    target.reputation_score = new if new is not None else before.computed
    target.reputation_override_reason = why if new is not None else None
    target.reputation_override_at = datetime.now(UTC) if new is not None else None
    target.reputation_override_by_id = actor.id if new is not None else None
    kind = "clear" if new is None else ("set" if before.override is None else "change")
    db.add(ModerationLog(
        target_type=ModerationTargetType.user, target_ref=target.id, moderator_id=actor.id,
        action=ModerationAction.override,
        notes=f"Honesty Score override {kind}: {why}",
        context={
            "kind": "trust_score_override", "change": kind,
            "computed": str(before.computed),
            "override_before": str(before.override) if before.override is not None else None,
            "override_after": str(new) if new is not None else None,
            "effective_before": str(before.effective),
            "effective_after": str(target.reputation_score),
        }))
    # The member's votes weigh by their score (§11): the people they voted for
    # are re-evaluated now, as a suspension does.
    from app.services.trust_service import recompute_authors_voted_on_by
    recompute_authors_voted_on_by(db, target.id)
    db.commit()
    db.refresh(target)
    return state_of(target)

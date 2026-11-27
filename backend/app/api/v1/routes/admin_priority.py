"""The admin priority tiers' thresholds (dev note 2026-09-26).

Moderators read them — the queue explains each tier with these numbers, so the
people triaging should see them. Only a Super Admin changes them
(`require_super_admin`, the same authority that appoints staff): a change
reorders every moderator's queue at once.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import require_staff, require_super_admin
from app.db.session import get_db
from app.models.user import User
from app.services import priority_settings

router = APIRouter(prefix="/admin", tags=["admin: priority tiers"])


class PrioritySettingsOut(BaseModel):
    wilson_band_low: float
    wilson_band_high: float
    fraud_high_min: int
    fraud_convergence_min: int
    aging_hours: int
    low_min_stage: int
    lowest_min_stage: int
    trend_window_days: int
    trend_tolerance: float
    fraud_reasons: list[str]
    #: The shipped defaults, so a screen can offer "reset".
    defaults: dict = Field(default_factory=dict)


class PrioritySettingsPatch(BaseModel):
    wilson_band_low: float | None = None
    wilson_band_high: float | None = None
    fraud_high_min: int | None = None
    fraud_convergence_min: int | None = None
    aging_hours: int | None = None
    low_min_stage: int | None = None
    lowest_min_stage: int | None = None
    trend_window_days: int | None = None
    trend_tolerance: float | None = None
    fraud_reasons: list[str] | None = None


def _out(cfg: priority_settings.TierConfig) -> PrioritySettingsOut:
    return PrioritySettingsOut(**cfg.as_dict(), defaults=priority_settings.DEFAULTS.as_dict())


@router.get("/priority-settings", response_model=PrioritySettingsOut,
            summary="The priority tiers' current thresholds",
            dependencies=[Depends(require_staff)])
def read_settings(db: Session = Depends(get_db)) -> PrioritySettingsOut:
    return _out(priority_settings.load(db))


@router.put("/priority-settings", response_model=PrioritySettingsOut,
            summary="Retune the priority tiers (Super Admin)")
def update_settings(payload: PrioritySettingsPatch, db: Session = Depends(get_db),
                    owner: User = Depends(require_super_admin)) -> PrioritySettingsOut:
    patch = payload.model_dump(exclude_none=True)
    return _out(priority_settings.update(db, patch, admin_id=owner.id))

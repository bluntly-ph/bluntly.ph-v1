"""The admin Settings screen (Figma Screen/Admin/Settings 8076:16388), read-only.

Every value is the one the system actually runs on — the constants and
configuration the services read — so the screen documents the live rules
rather than offering knobs nobody wired. Editing the earning rules or the
commission split moves money and waits on an owner decision; until then the
screen states them and says where they are defined.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    HONESTY_FUND_SHARE,
    PAYOUT_MINIMUM_PHP,
    PLATFORM_SHARE,
    REVIEWER_SHARE,
)
from app.models.enums import MemberRole, ModerationAction
from app.models.moderation import ModerationLog
from app.models.user import User
from app.services.ranking import GATE_MIN_STAGE2_VOTERS, GATE_WILSON_LB
from app.services.retention_service import RETENTION_DAYS

TEAM_LIMIT = 10


@dataclass(frozen=True)
class TeamMember:
    id: uuid.UUID
    name: str | None
    email: str | None
    role: str
    last_action_at: datetime | None


@dataclass(frozen=True)
class Integration:
    key: str
    name: str
    #: connected | manual | not_connected
    status: str
    detail: str


@dataclass(frozen=True)
class SettingsOverview:
    wilson_gate: float
    min_stage2_voters: int
    split_reviewer: Decimal
    split_honesty_fund: Decimal
    split_platform: Decimal
    payout_minimum: Decimal
    payout_day: int
    honesty_fund_day: int
    team: list[TeamMember]
    team_total: int
    integrations: list[Integration]
    retention: list[tuple[str, str]]


def _task_day(name: str) -> int:
    from app.api.v1.routes.internal_cron import TASKS
    return int(TASKS[name].day_of_month or 1)


def _paymongo(db: Session) -> Integration:
    """Keys saved (test or live) or not. Either way payouts stay manual."""
    from app.services import paymongo_config
    c = paymongo_config.read(db)
    if not c.connected:
        return Integration("paymongo", "PayMongo", "not_connected",
                           "Automatic payouts to GCash, Maya and banks are not built")
    tested = (" · last test passed" if c.last_test and c.last_test.ok
              else " · last test failed" if c.last_test else "")
    # A key PayMongo refused is not a connection.
    status = "not_connected" if c.last_test and not c.last_test.ok else "connected"
    return Integration("paymongo", "PayMongo", status,
                       f"Keys saved ({'test' if c.test_mode else 'live'} mode){tested}. "
                       "Payouts stay manual: automatic transfers are not built")


def overview(db: Session, *, show_email: bool) -> SettingsOverview:
    staff = (MemberRole.administrator, MemberRole.super_admin)
    last = (select(ModerationLog.moderator_id, func.max(ModerationLog.created_at).label("at"))
            .where(ModerationLog.moderator_id.is_not(None))
            .group_by(ModerationLog.moderator_id).subquery())
    team_total = int(db.scalar(select(func.count(User.id)).where(User.role.in_(staff))) or 0)
    team = [TeamMember(id=u.id, name=u.display_name or (f"@{u.username}" if u.username else None),
                       email=u.email if show_email else None, role=u.role.value,
                       last_action_at=at)
            for u, at in db.execute(
                select(User, last.c.at).outerjoin(last, last.c.moderator_id == User.id)
                .where(User.role.in_(staff))
                .order_by(last.c.at.desc().nulls_last(), User.created_at)
                .limit(TEAM_LIMIT)).all()]

    imported = db.scalar(select(func.max(ModerationLog.created_at))
                         .where(ModerationLog.action == ModerationAction.csv_import))
    integrations = [
        Integration("affiliate", "Shopee / Lazada affiliate",
                    "connected" if imported else "not_connected",
                    f"Last report imported {imported:%d %b %Y}" if imported
                    else "No report imported yet"),
        Integration("paypal", "PayPal", "manual",
                    "Payouts are sent by hand from the Bluntly account"
                    + (" (API credentials present, not used for sending)"
                       if settings.paypal_client_id else "")),
        _paymongo(db),
        Integration("email", "Resend (email)",
                    "connected" if settings.email_provider == "resend" and settings.resend_api_key
                    else "not_connected",
                    "Sends sign-in codes and notification emails"
                    if settings.email_provider == "resend"
                    else "Console only: codes are logged, not emailed"),
    ]
    retention = [
        ("IP addresses", f"Hashed after 30 days, deleted after {RETENTION_DAYS} days"),
        # Figma 8076:16388 "Request geography": city buckets the edge resolved,
        # purged by the same sweep (retention_service.request_geo_buckets).
        ("Request geography", f"{RETENTION_DAYS} days, no IP addresses"),
        ("Reading telemetry", f"{settings.telemetry_retention_days} days"),
        ("Voting network fingerprints", f"{settings.vote_network_retention_days} days"),
        ("Activity log", "Kept permanently"),
    ]
    return SettingsOverview(
        wilson_gate=GATE_WILSON_LB, min_stage2_voters=GATE_MIN_STAGE2_VOTERS,
        split_reviewer=REVIEWER_SHARE, split_honesty_fund=HONESTY_FUND_SHARE,
        split_platform=PLATFORM_SHARE, payout_minimum=PAYOUT_MINIMUM_PHP,
        payout_day=_task_day("schedule_payouts"), honesty_fund_day=_task_day(
            "honesty_fund_distribution"),
        team=team, team_total=team_total, integrations=integrations, retention=retention)

"""People investigation for staff (Figma Screen/Admin/People/Person and tabs).

One read per person: the page's Overview, Activity, Interactions, Reports and
Moderation tabs are views over the same payload. Definitions, including what
"reciprocity" and "linked account" mean, are in person_investigation_service.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFoundError
from app.core.security import require_staff, require_super_admin
from app.db.session import get_db
from app.models.enums import MemberRole, ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.user import User
from app.services import person_investigation_service as svc

router = APIRouter(prefix="/admin/people", tags=["admin: people"],
                   dependencies=[Depends(require_staff)])

RANGE_DAYS = {"1M": 30, "6M": 182, "1Y": 365}


class PersonRefOut(BaseModel):
    id: uuid.UUID
    name: str
    username: str | None
    trust_stage: int
    trust_level_name: str | None


class PersonOut(BaseModel):
    id: uuid.UUID
    user_ref: str | None
    name: str
    username: str | None
    role: str
    trust_stage: int
    trust_level_name: str | None
    #: The EFFECTIVE Honesty Score (0..100): the override when set, else computed.
    reputation_score: str
    joined: datetime
    #: "active", "investigating" (votes count half) or "suspended" (no vote).
    status: str
    #: The algorithm's score, the administrator's override (null = none) and
    #: whether one is in force (0095; services/trust_override.py).
    computed_score: str = "0.00"
    score_override: str | None = None
    is_score_overridden: bool = False
    score_override_reason: str | None = None
    score_overridden_at: datetime | None = None
    #: The member's own profile photo (users.avatar_url); null = none.
    avatar_url: str | None = None


class DayOut(BaseModel):
    day: date
    up: int
    down: int


class InteractionOut(BaseModel):
    person: PersonRefOut
    up: int
    down: int
    comments: int
    up_back: int
    same_day: int
    share_pct: float
    reciprocity_pct: float
    same_network: bool
    last_at: datetime | None


class ActivityOut(BaseModel):
    kind: str
    at: datetime
    title: str
    subtitle: str | None
    other: PersonRefOut | None
    href: str | None


class PersonReportOut(BaseModel):
    id: uuid.UUID
    direction: Literal["filed", "received"]
    reason: str | None
    target_type: str | None
    target_label: str
    other: PersonRefOut | None
    status: str
    at: datetime
    href: str | None
    notes: str | None


class PersonModerationOut(BaseModel):
    id: uuid.UUID
    action: str
    target_type: str | None
    target_label: str
    moderator: str | None
    reason: str | None
    notes: str | None
    at: datetime


class LinkedAccountOut(BaseModel):
    person: PersonRefOut
    basis: Literal["shared_network", "shared_payout_account"]
    detail: str


class SignalsOut(BaseModel):
    reports_against: int
    reports_against_upheld: int
    reports_filed: int
    reports_filed_upheld: int
    moderation: int
    takedowns: int
    #: Lifetime earned and money not yet paid out; null when not computable.
    earned: str | None
    pending: str | None
    linked_accounts: int


class PersonInvestigationOut(BaseModel):
    person: PersonOut
    range: Literal["1M", "6M", "1Y"]
    votes_total: int
    votes_up: int
    votes_down: int
    daily: list[DayOut]
    spike: DayOut | None
    interactions: list[InteractionOut]
    interactions_total: int
    top3_share_pct: float
    activity: list[ActivityOut]
    activity_total: int
    reports: list[PersonReportOut]
    moderation: list[PersonModerationOut]
    linked: list[LinkedAccountOut]
    signals: SignalsOut


def _ref(r: svc.PersonRef | None) -> PersonRefOut | None:
    return PersonRefOut(**vars(r)) if r else None


@router.get("/{user_id}", response_model=PersonInvestigationOut,
            summary="Everything recorded about one member, for an investigation")
def person_investigation(
    user_id: uuid.UUID,
    range_: Literal["1M", "6M", "1Y"] = Query("1M", alias="range"),
    db: Session = Depends(get_db),
) -> PersonInvestigationOut:
    inv = svc.investigate(db, user_id, days=RANGE_DAYS[range_])
    p = inv.person
    spike = None
    if inv.spike:
        day, total = inv.spike
        match = next((d for d in inv.daily if d[0] == day), (day, total, 0))
        spike = DayOut(day=day, up=match[1], down=match[2])
    return PersonInvestigationOut(
        person=PersonOut(
            id=p.id, user_ref=p.user_id, name=p.display_name or p.username or "Member",
            username=p.username, role=p.role.value if hasattr(p.role, "value") else str(p.role),
            trust_stage=p.trust_stage, trust_level_name=p.trust_level_name,
            reputation_score=str(p.reputation_score), joined=p.created_at, status=inv.status,
            computed_score=str(p.computed_reputation_score),
            score_override=(str(p.reputation_score_override)
                            if p.reputation_score_override is not None else None),
            is_score_overridden=p.reputation_score_override is not None,
            score_override_reason=p.reputation_override_reason,
            score_overridden_at=p.reputation_override_at,
            avatar_url=p.avatar_url or None),
        range=range_,
        votes_total=inv.votes_total, votes_up=inv.votes_up, votes_down=inv.votes_down,
        daily=[DayOut(day=d, up=u, down=dn) for d, u, dn in inv.daily],
        spike=spike,
        interactions=[
            InteractionOut(person=_ref(i.person), up=i.up, down=i.down, comments=i.comments,
                           up_back=i.up_back, same_day=i.same_day, share_pct=i.share_pct,
                           reciprocity_pct=i.reciprocity_pct, same_network=i.same_network,
                           last_at=i.last_at)
            for i in inv.interactions
        ],
        interactions_total=inv.interactions_total,
        top3_share_pct=inv.top3_share_pct,
        activity=[ActivityOut(**{**vars(a), "other": _ref(a.other)}) for a in inv.activity],
        activity_total=inv.activity_total,
        reports=[PersonReportOut(**{**vars(r), "other": _ref(r.other)}) for r in inv.reports],
        moderation=[PersonModerationOut(**vars(m)) for m in inv.moderation],
        linked=[LinkedAccountOut(person=_ref(link.person), basis=link.basis, detail=link.detail)
                for link in inv.linked],
        signals=SignalsOut(
            reports_against=inv.reports_against,
            reports_against_upheld=inv.reports_against_upheld,
            reports_filed=inv.reports_filed, reports_filed_upheld=inv.reports_filed_upheld,
            moderation=len(inv.moderation), takedowns=inv.takedowns,
            earned=str(inv.earned) if inv.earned is not None else None,
            pending=str(inv.pending) if inv.pending is not None else None,
            linked_accounts=len(inv.linked)),
    )


class SuspensionIn(BaseModel):
    suspended: bool
    #: Why — kept in the audit log, never shown to the member.
    reason: str = Field(min_length=3, max_length=1000)


class SuspensionOut(BaseModel):
    user_id: uuid.UUID
    suspended: bool


@router.put("/{person_id}/suspension", response_model=SuspensionOut,
            summary="Suspend or reinstate a member account (Super Admin)")
def set_suspension(person_id: uuid.UUID, payload: SuspensionIn,
                   db: Session = Depends(get_db),
                   actor: User = Depends(require_super_admin)) -> SuspensionOut:
    """Figma Menu/Person/Actions: "Suspend account" (PRD: platform administration).

    The Super Admin's alone, like role changes: a suspended account cannot sign
    in, its votes weigh nothing (§11) and the members it voted for are
    re-evaluated now and again on reinstatement. Only member accounts: a staff
    account is demoted first (Users), never suspended from here. Audited, with
    the reason; reversible."""
    target = db.get(User, person_id)
    if target is None:
        raise NotFoundError("Person not found.", code="person_not_found")
    if target.id == actor.id:
        raise AppError("You cannot suspend your own account.", code="self_decision",
                       status_code=422, title="Invalid decision")
    if target.role in (MemberRole.administrator, MemberRole.super_admin):
        raise AppError("Staff accounts are not suspended here: change their role in Users first.",
                       code="staff_account", status_code=422, title="Invalid decision")
    if bool(target.is_suspended) != payload.suspended:
        target.is_suspended = payload.suspended
        from app.services.trust_service import recompute_authors_voted_on_by
        recompute_authors_voted_on_by(db, target.id)
        db.add(ModerationLog(
            target_type=ModerationTargetType.user, target_ref=target.id, moderator_id=actor.id,
            action=ModerationAction.suspend if payload.suspended else ModerationAction.restore,
            notes=payload.reason.strip()))
        db.commit()
    return SuspensionOut(user_id=target.id, suspended=bool(target.is_suspended))


class TrustScoreIn(BaseModel):
    #: 0..100 (two decimals) sets or changes the override; null clears it.
    score: float | None = Field(default=None)
    #: Why — required for every set, change and clear; kept in the audit log.
    reason: str = Field(min_length=3, max_length=1000)


class TrustScoreOut(BaseModel):
    user_id: uuid.UUID
    computed_score: str
    score_override: str | None
    #: What every reader uses (vote weight, lenses, profiles): override or computed.
    effective_score: str
    is_score_overridden: bool
    score_override_reason: str | None
    score_overridden_at: datetime | None
    score_overridden_by: uuid.UUID | None


@router.put("/{person_id}/trust-score", response_model=TrustScoreOut,
            summary="Set, change or clear a member's Honesty Score override (Administrator)")
def set_trust_score(person_id: uuid.UUID, payload: TrustScoreIn,
                    db: Session = Depends(get_db),
                    actor: User = Depends(require_staff)) -> TrustScoreOut:
    """The algorithm keeps computing the score; an override stands in for it
    until cleared (`score: null`). A reason is required each time and every
    change is audited (moderation_logs, action `override`). Not your own score.
    The trust STAGE is unaffected: it is not derived from the score."""
    from app.services import trust_override
    st = trust_override.set_override(db, actor, person_id, payload.score, payload.reason)
    return TrustScoreOut(
        user_id=st.user_id, computed_score=str(st.computed),
        score_override=str(st.override) if st.override is not None else None,
        effective_score=str(st.effective), is_score_overridden=st.is_overridden,
        score_override_reason=st.reason, score_overridden_at=st.overridden_at,
        score_overridden_by=st.overridden_by_id)

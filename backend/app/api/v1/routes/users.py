"""User trust profile + moderator role management (M2 slices 3-4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import (
    create_access_token,
    get_current_user,
    get_optional_user,
    hash_password,
    require_super_admin,
    verify_password,
)
from app.db.session import get_db
from app.models.enums import STAFF_ROLES, ModerationAction, ModerationTargetType
from app.models.moderation import ModerationLog
from app.models.review import Review
from app.models.user import TRUST_LEVEL_NAMES, User, UserBadge
from app.schemas.auth import PasswordChangeIn, ProfileUpdateIn, UserOut
from app.schemas.common import Problem
from app.schemas.user import (
    BadgeOut,
    EmailChangeConfirmIn,
    EmailChangeDoneOut,
    EmailChangePendingOut,
    EmailChangeStartIn,
    InteractionOut,
    NotificationPrefs,
    PublicProfileOut,
    RoleUpdate,
    TrustProgressOut,
    UserTrustOut,
)
from app.services import (
    contribution_streak,
    contributor_dashboard,
    dashboard_service,
    email_change_service,
    notification_service,
    payout_tips_service,
    profile_service,
)
from app.services.storage import delete_avatar_object, upload_avatar
from app.services.trust import next_stage_progress
from app.services.username import MAX_LENGTH, MIN_LENGTH, is_valid_username

router = APIRouter(prefix="/users", tags=["users"])

_AVATAR_PROBLEM = {401: {"model": Problem}, 413: {"model": Problem},
                   415: {"model": Problem}}


def _user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.", code="user_not_found")
    return user


class UsernameAvailability(BaseModel):
    username: str
    available: bool
    reason: str | None = None


# Registered before the `/{user_id}/...` routes so the literal segment is never
# considered as a UUID path parameter.
@router.get("/username-available", response_model=UsernameAvailability,
            summary="Whether a username is free to claim")
def username_available(request: Request, username: str,
                       db: Session = Depends(get_db),
                       user: User | None = Depends(get_optional_user),
                       ) -> UsernameAvailability:
    """Check a username *before* the signup wizard is finished (BUG-018).

    Availability was only ever discovered on submit, so someone could pick a
    handle, choose interests, read two more screens, and only then be told to
    start over with a different name.

    No enumeration concern: usernames are public handles, printed on every
    review and profile. Rate-limited anyway, because a cheap endpoint that
    answers questions about accounts should not be free to hammer.
    """
    enforce_rate_limit(request, "username-check", max_requests=60)
    candidate = (username or "").strip()
    # Same rule the write path enforces (services/username.py, mirrored in SQL by
    # migration 0016) rather than a second copy that could drift from it.
    if len(candidate) < MIN_LENGTH:
        return UsernameAvailability(
            username=candidate, available=False,
            reason=f"Usernames need at least {MIN_LENGTH} characters.")
    if len(candidate) > MAX_LENGTH:
        return UsernameAvailability(
            username=candidate, available=False,
            reason=f"Usernames are {MAX_LENGTH} characters at most.")
    if not is_valid_username(candidate):
        return UsernameAvailability(
            username=candidate, available=False,
            reason="Lowercase letters, numbers, and underscores only.")
    stmt = select(User.id).where(func.lower(User.username) == candidate.lower())
    # Your own current handle is "available" to you — otherwise the wizard would
    # flag the auto-generated name it prefilled for you as taken.
    if user is not None:
        stmt = stmt.where(User.id != user.id)
    if db.scalar(stmt) is not None:
        return UsernameAvailability(username=candidate, available=False,
                                    reason="That username is already taken.")
    return UsernameAvailability(username=candidate, available=True)


@router.patch("/me", response_model=UserOut,
              responses={401: {"model": Problem}, 409: {"model": Problem}},
              summary="Update the current user's profile")
def update_me(payload: ProfileUpdateIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> UserOut:
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.interests is not None:
        # De-duplicate while preserving pick order — the feed reads it as a
        # priority list, not a set.
        user.interests = list(dict.fromkeys(payload.interests))
    if payload.username is not None and payload.username != user.username:
        clash = db.scalar(select(User.id).where(
            func.lower(User.username) == payload.username.lower(),
            User.id != user.id))
        if clash is not None:
            raise AppError("That username is already taken.",
                           code="username_taken", status_code=409,
                           title="Username already registered")
        user.username = payload.username
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me/notification-prefs", response_model=NotificationPrefs,
            responses={401: {"model": Problem}},
            summary="Which store notifications reach the current user")
def get_notification_prefs(user: User = Depends(get_current_user)) -> NotificationPrefs:
    return NotificationPrefs(**notification_service.prefs_of(user))


@router.put("/me/notification-prefs", response_model=NotificationPrefs,
            responses={401: {"model": Problem}, 422: {"model": Problem}},
            summary="Turn store notifications on or off for the current user")
def put_notification_prefs(payload: NotificationPrefs, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)) -> NotificationPrefs:
    """Figma Screen/Seller/Settings 8218:24151. Only the store notices listed in
    notification_service.STORE_PREFS can be turned off; the account's own
    decisions, staff messages and payouts always arrive."""
    user.notification_prefs = payload.model_dump()
    db.commit()
    return NotificationPrefs(**notification_service.prefs_of(user))


@router.get("/me/email-change", response_model=EmailChangePendingOut | None,
            responses={401: {"model": Problem}},
            summary="The current user's pending email change, if any")
def get_email_change(db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> EmailChangePendingOut | None:
    row = email_change_service.pending(db, user)
    if row is None:
        return None
    return EmailChangePendingOut(new_email=row.new_email, expires_at=row.expires_at)


@router.post("/me/email-change", response_model=EmailChangePendingOut, status_code=202,
             responses={401: {"model": Problem}, 422: {"model": Problem},
                        429: {"model": Problem}, 502: {"model": Problem}},
             summary="Start a verified email change: a code to the current and the new address")
def start_email_change(payload: EmailChangeStartIn, request: Request,
                       db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> EmailChangePendingOut:
    """0084. Nothing changes until both codes are confirmed. Whether the new address
    is already in use is answered only at confirm time, to its proven owner."""
    enforce_rate_limit(request, "email_change")
    row = email_change_service.start(db, user, str(payload.new_email))
    return EmailChangePendingOut(new_email=row.new_email, expires_at=row.expires_at)


@router.post("/me/email-change/confirm", response_model=EmailChangeDoneOut,
             responses={401: {"model": Problem}, 409: {"model": Problem},
                        422: {"model": Problem}, 429: {"model": Problem}},
             summary="Confirm an email change with both codes")
def confirm_email_change(payload: EmailChangeConfirmIn, request: Request,
                         db: Session = Depends(get_db),
                         user: User = Depends(get_current_user)) -> EmailChangeDoneOut:
    """Both codes right: the address changes, every other session ends, the old
    address is told, and this browser gets a fresh token."""
    enforce_rate_limit(request, "email_change")
    changed = email_change_service.confirm(db, user, payload.current_code, payload.new_code)
    return EmailChangeDoneOut(email=changed.email,
                              access_token=create_access_token(changed.id, changed.role.value),
                              expires_in=settings.access_token_expire_minutes * 60)


@router.delete("/me/email-change", status_code=204, response_class=Response,
               responses={401: {"model": Problem}},
               summary="Cancel a pending email change")
def cancel_email_change(db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)) -> Response:
    email_change_service.cancel(db, user)
    return Response(status_code=204)


@router.post("/me/password", status_code=204, response_class=Response,
             responses={401: {"model": Problem}, 409: {"model": Problem},
                        422: {"model": Problem}, 429: {"model": Problem}},
             summary="Change the current user's password (current password required)")
def change_password(payload: PasswordChangeIn, request: Request,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> Response:
    """Figma Overlay/Store/Account "Change password". The account's own
    password only, behind the current one (rate-limited like sign-in, so it
    cannot be guessed through a stolen session). An account made with an email
    code has no password and is told so (409): setting a first password is not
    offered, because the web signs in by email code. A notice goes to the
    account's email, best effort."""
    enforce_rate_limit(request, "password_change")
    if not user.password_hash:
        raise AppError("This account signs in with a code sent to your email and has no "
                       "password.", code="no_password", status_code=409,
                       title="No password on this account")
    if not verify_password(payload.current_password, user.password_hash):
        raise AppError("The current password isn't right.", code="current_password_wrong",
                       status_code=422, title="Wrong password")
    if verify_password(payload.new_password, user.password_hash):
        raise AppError("Choose a password different from the current one.",
                       code="password_unchanged", status_code=422, title="Same password")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    try:
        from app.adapters.email import send_email
        send_email(user.email, "Your Bluntly password was changed",
                   "The password on your Bluntly account was just changed. If this wasn't "
                   "you, sign in with a code sent to this email and contact the team.")
    except Exception:  # noqa: BLE001 - the change stands without its notice
        pass
    return Response(status_code=204)


@router.post("/me/avatar", response_model=UserOut, responses=_AVATAR_PROBLEM,
             summary="Upload or replace the current user's avatar")
def set_avatar(file: UploadFile, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> UserOut:
    data = file.file.read()
    new_url = upload_avatar(user.id, data)
    previous = user.avatar_url
    user.avatar_url = new_url
    db.commit()
    db.refresh(user)
    # Only drop the old object once the new one is committed — a failure here
    # must never leave the user with no avatar at all.
    if previous:
        delete_avatar_object(previous)
    return UserOut.model_validate(user)


@router.delete("/me/avatar", status_code=204, responses=_AVATAR_PROBLEM,
               # response_model=None: without it FastAPI infers a model from the
               # `-> None` annotation, which a 204 may not carry.
               response_model=None, summary="Remove the current user's avatar")
def clear_avatar(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> None:
    previous = user.avatar_url
    user.avatar_url = None
    db.commit()
    if previous:
        delete_avatar_object(previous)


class PersonOut(BaseModel):
    """A member in people search: public fields only."""

    id: uuid.UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    trust_stage: int = 0
    trust_level_name: str | None = None
    review_count: int = 0
    is_claimed_seller: bool = False


@router.get("/search", response_model=list[PersonOut],
            summary="Find people by @handle or name, to open their profile")
def search_people(q: str = Query(..., min_length=1, max_length=80),
                  limit: int = Query(20, ge=1, le=50),
                  db: Session = Depends(get_db)) -> list[PersonOut]:
    """Public, like a profile: no session needed, no private field returned."""
    return [PersonOut(**vars(hit)) for hit in profile_service.search_people(db, q, limit)]


@router.get("/public/{handle}", response_model=PublicProfileOut,
            responses={404: {"model": Problem}},
            summary="A reviewer's public profile, by username or id")
def public_profile(handle: str, db: Session = Depends(get_db)) -> PublicProfileOut:
    """Resolve `/u/{handle}` (BUG-030). Public: no session, no private fields.

    The handle is a username or a UUID, because both are in circulation — the
    site links reviewers by id, and a person typing a profile URL types the
    @handle. Usernames are stored already lowercased and URL-safe
    (`services.username`), so the comparison is folded rather than exact: a
    capitalised link from someone's notes should not 404.

    Registered before `/{user_id}/...`: `public` is a literal segment, so the
    two shapes cannot collide, but the order makes that obvious to a reader.
    """
    user = _public_user_or_404(db, handle)
    published = db.scalar(
        select(func.count(Review.id)).where(
            Review.author_id == user.id,
            Review.published_at.isnot(None),
            Review.is_removed.is_(False),
        )
    ) or 0
    return PublicProfileOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        trust_stage=user.trust_stage,
        trust_level_name=user.trust_level_name,
        reputation_score=user.reputation_score,
        verified_review_count=user.verified_review_count,
        review_count=published,
        created_at=user.created_at,
        people_helped=profile_service.people_helped(db, user.id),
        comment_count=profile_service.comment_count(db, user.id),
        interacts_with_most=[InteractionOut(**vars(i))
                             for i in profile_service.interacts_with_most(db, user.id)],
        most_interacted_by=[InteractionOut(**vars(i))
                            for i in profile_service.most_interacted_by(db, user.id)],
        is_claimed_seller=user.is_claimed_seller,
    )


def _public_user_or_404(db: Session, handle: str) -> User:
    """The account behind a handle or an id, or 404 — never an exception."""
    handle = (handle or "").strip()
    if not handle:
        raise NotFoundError("Reviewer not found.", code="user_not_found")

    try:
        as_id = uuid.UUID(handle)
    except ValueError:
        as_id = None
    if as_id is not None:
        user = db.get(User, as_id)
        if user is not None:
            return user

    user = db.scalar(
        select(User).where(func.lower(User.username) == handle.lower())
    )
    if user is None:
        raise NotFoundError("Reviewer not found.", code="user_not_found")
    return user


@router.get("/{user_id}/trust", response_model=UserTrustOut,
            summary="Public trust profile (stage, reputation, badges)")
def get_trust(user_id: uuid.UUID, db: Session = Depends(get_db)) -> UserTrustOut:
    user = _user_or_404(db, user_id)
    user_badges = db.scalars(
        select(UserBadge).where(UserBadge.user_id == user.id)
        .options(joinedload(UserBadge.badge))
        .order_by(UserBadge.awarded_at)
    ).all()
    return UserTrustOut(
        id=user.id,
        trust_stage=user.trust_stage,
        trust_level_name=user.trust_level_name,
        reputation_score=user.reputation_score,
        verified_review_count=user.verified_review_count,
        helpfulness_ratio=user.helpfulness_ratio,
        badges=[BadgeOut(badge_id=ub.badge.badge_id, name=ub.badge.name,
                         awarded_at=ub.awarded_at) for ub in user_badges],
        progress=_trust_progress(db, user),
    )


def _trust_progress(db: Session, user: User) -> TrustProgressOut | None:
    """What this member needs to reach the next stage (profile Stats card).

    The published-review count is read here rather than stored: only stage 1
    depends on it, and `users` deliberately carries no denormalised total that
    a removal would have to walk back.
    """
    step = next_stage_progress(
        user.trust_stage,
        review_count=db.scalar(
            select(func.count(Review.id)).where(
                Review.author_id == user.id,
                Review.published_at.isnot(None),
                Review.is_removed.is_(False),
            )
        ) or 0,
        verified_review_count=user.verified_review_count,
    )
    if step is None:
        return None
    next_stage, have, needed = step
    return TrustProgressOut(
        next_stage=next_stage,
        next_level_name=TRUST_LEVEL_NAMES[next_stage],
        reviews_have=have,
        reviews_needed=needed,
    )


@router.patch("/{user_id}/role", response_model=UserOut,
              summary="Move an account between user and seller (Super Admin)")
def set_role(user_id: uuid.UUID, payload: RoleUpdate, db: Session = Depends(get_db),
             moderator: User = Depends(require_super_admin)) -> UserOut:
    # Owner decision C: changing anyone's role is user management, which is a
    # Super Admin's alone. This legacy surface moves user <-> seller only; the
    # staff roles have their own audited endpoint with the last-Super-Admin
    # invariant (PATCH /admin/users/{id}/role).
    if payload.role in STAFF_ROLES:
        raise AppError("Staff roles are assigned from user management.",
                       code="role_not_grantable", status_code=422,
                       title="Invalid role")
    user = _user_or_404(db, user_id)
    # Without a target-side guard this could DEMOTE staff by sending
    # {"role":"user"}, bypassing the invariant. Staff accounts are not here.
    if user.role in STAFF_ROLES:
        raise ForbiddenError(
            "Staff roles are managed from user management.",
            code="role_not_managed_here",
        )
    old_role = user.role
    user.role = payload.role
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        target_type=ModerationTargetType.user, target_ref=user.id,
        moderator_id=moderator.id, action=ModerationAction.override,
        notes="role change",
        context={"from": old_role.value, "to": payload.role.value},
    ))
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


class DashboardSeriesPoint(BaseModel):
    day: date
    #: String-decimal, like every other money field in this API.
    amount: str


class DashboardReviewRow(BaseModel):
    review_id: uuid.UUID
    title: str
    photo_url: str | None
    earnings: str
    views: int
    helped: int
    series: list[DashboardSeriesPoint]


class DashboardSummaryOut(BaseModel):
    range: str
    window_start: date
    window_end: date
    estimated_commission: str
    earned_in_window: str
    total_views: int
    #: Null today — nothing measures read time, and starting to would be
    #: reader-behaviour tracking rather than aggregate counting. Listed in
    #: `unavailable` so the client renders the tile honestly instead of
    #: substituting a plausible number.
    average_read_seconds: int | None
    unavailable: list[str]
    has_earnings: bool
    series: list[DashboardSeriesPoint]
    reviews: list[DashboardReviewRow]


@router.get("/me/dashboard", response_model=DashboardSummaryOut,
            summary="Earnings, views and ranked reviews for the signed-in user")
def my_dashboard(
    range: str = Query(default=dashboard_service.DEFAULT_RANGE),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> DashboardSummaryOut:
    """The contributor dashboard, for the caller and nobody else.

    There is no user id in the path on purpose: a reviewer's earnings are
    theirs alone, and an endpoint that accepts an id is an endpoint someone
    will eventually pass a different id to.
    """
    if range not in dashboard_service.RANGES:
        raise HTTPException(
            status_code=422,
            detail=f"range must be one of {sorted(dashboard_service.RANGES)}")

    result = dashboard_service.summary(db, me.id, range_key=range)
    return DashboardSummaryOut(
        range=result.range_key,
        window_start=result.window_start, window_end=result.window_end,
        estimated_commission=str(result.estimated_commission),
        earned_in_window=str(result.earned_in_window),
        total_views=result.total_views,
        average_read_seconds=result.average_read_seconds,
        unavailable=list(result.unavailable),
        has_earnings=result.has_earnings,
        series=[DashboardSeriesPoint(day=p.day, amount=str(p.amount))
                for p in result.series],
        reviews=[
            DashboardReviewRow(
                review_id=r.review_id, title=r.title, photo_url=r.photo_url,
                earnings=str(r.earnings), views=r.views, helped=r.helped,
                series=[DashboardSeriesPoint(day=p.day, amount=str(p.amount))
                        for p in r.series],
            )
            for r in result.reviews
        ],
    )


class EarningBreakdownOut(BaseModel):
    """What the History frame reveals when a row is expanded."""

    gross_amount: str
    #: Provider commission rate where the import recorded one; null otherwise.
    #: Never derived by dividing, because the two are rounded independently.
    commission_rate: str | None
    platform_share: str
    honesty_fund_share: str
    reviewer_share: str


class EarningRowOut(BaseModel):
    commission_id: str
    occurred_on: date
    review_id: uuid.UUID | None
    review_title: str | None
    product_name: str | None
    photo_url: str | None
    amount: str
    #: pending | to_earn | paid | returned — the reviewer-facing reading of the
    #: canonical lifecycle/settlement pair, never a substitute for either.
    status: str
    breakdown: EarningBreakdownOut
    #: A QA sandbox test earning: credited for testing payouts, not a sale.
    is_test: bool = False


class EarningsHistoryOut(BaseModel):
    all_time: str
    counts: dict[str, int]
    rows: list[EarningRowOut]
    has_data: bool


class ContributorBucketOut(BaseModel):
    label: str
    start: date
    end: date
    earned: Decimal
    returned: Decimal
    current: bool


class ContributorBestOut(BaseModel):
    review_id: uuid.UUID
    product_id: uuid.UUID | None = None
    product_name: str
    image_url: str | None = None
    views: int
    helped: int
    earned: Decimal


class ContributorRequirementOut(BaseModel):
    key: str
    label: str
    have: float
    needed: float
    done: bool


class ContributorReachOut(BaseModel):
    views: int
    helped: int
    clicks: int
    bought: int


class ContributorDashboardOut(BaseModel):
    """Figma Screen/Dashboard (7833:9534). Money is a decimal string."""

    total_balance: Decimal
    commission_balance: Decimal
    honesty_fund_balance: Decimal
    #: Credited but still clearing: not withdrawable yet (§15/§19).
    pending: Decimal
    withdrawable: Decimal
    minimum_cashout: Decimal
    period: str
    earned: Decimal
    returned: Decimal
    buckets: list[ContributorBucketOut]
    best: list[ContributorBestOut]
    stage: int
    level_name: str
    next_stage: int | None = None
    next_level_name: str | None = None
    #: What the next stage asks for, from the thresholds that promote.
    requirements: list[ContributorRequirementOut]
    #: Requirements met, promotion held for a moderator (vote concentration).
    held_for_review: bool
    honesty_score: int
    honesty_fund_earned: Decimal
    #: Any commission or Honesty Fund credit on record, ever.
    has_earned: bool = False
    reach_choice: str
    reach_month: str
    reach_previous_month: str
    reach: ContributorReachOut
    reach_previous: ContributorReachOut


@router.get("/me/contributor", response_model=ContributorDashboardOut,
            summary="The contributor dashboard: wallet, earnings, trust stage, reach")
def my_contributor_dashboard(
    period: str = Query(default="week", pattern="^(week|month)$"),
    reach: str = Query(default="this", pattern="^(this|last)$"),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> ContributorDashboardOut:
    """The redesigned dashboard (Figma 7833:9534), for the caller only — no
    user id in the path, like /me/dashboard."""
    d = contributor_dashboard.build(db, me, period=period, reach_month=reach)
    return ContributorDashboardOut(
        total_balance=d.total_balance, commission_balance=d.commission_balance,
        honesty_fund_balance=d.honesty_fund_balance, pending=d.pending,
        withdrawable=d.withdrawable, minimum_cashout=d.minimum_cashout,
        period=d.period, earned=d.earned, returned=d.returned,
        buckets=[ContributorBucketOut(**b.__dict__) for b in d.buckets],
        best=[ContributorBestOut(**b.__dict__) for b in d.best],
        stage=d.stage, level_name=d.level_name, next_stage=d.next_stage,
        next_level_name=d.next_level_name,
        requirements=[ContributorRequirementOut(**r.__dict__) for r in d.requirements],
        held_for_review=d.held_for_review,
        honesty_score=d.honesty_score, honesty_fund_earned=d.honesty_fund_earned,
        has_earned=d.has_earned, reach_choice=d.reach_choice, reach_month=d.reach_month,
        reach_previous_month=d.reach_previous_month,
        reach=ContributorReachOut(**d.reach.__dict__),
        reach_previous=ContributorReachOut(**d.reach_previous.__dict__))


class OpenQuestionOut(BaseModel):
    id: uuid.UUID
    body: str
    product_name: str | None = None
    created_at: datetime


class MissingProofOut(BaseModel):
    review_id: uuid.UUID
    product_name: str
    product_image_url: str | None = None
    published_at: datetime
    can_add_photo: bool


class PayoutTipsOut(BaseModel):
    answers_this_month: int
    earned_from_answers: Decimal
    #: The first category the member chose at onboarding; null = any category.
    category_label: str | None = None
    open_questions: list[OpenQuestionOut]
    #: Average net earning per published review, all reviewers; null = none yet.
    average_with_proof: Decimal | None = None
    average_without_proof: Decimal | None = None
    missing_proof: list[MissingProofOut]


@router.get("/me/payout-tips", response_model=PayoutTipsOut,
            summary="The Payout screen's tips: open questions to answer, reviews missing proof")
def my_payout_tips(db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)) -> PayoutTipsOut:
    """Figma 7844:9469 and 7843:9501, for the caller only."""
    t = payout_tips_service.build(db, me)
    return PayoutTipsOut(
        answers_this_month=t.answers_this_month, earned_from_answers=t.earned_from_answers,
        category_label=t.category_label,
        open_questions=[OpenQuestionOut(**q.__dict__) for q in t.open_questions],
        average_with_proof=t.average_with_proof, average_without_proof=t.average_without_proof,
        missing_proof=[MissingProofOut(**m.__dict__) for m in t.missing_proof])


class PerformanceProductOut(BaseModel):
    product_id: uuid.UUID
    name: str
    image_url: str | None = None
    reviews: int
    #: "Your reviews" rows: the period's views, people helped and earnings.
    views: int = 0
    helped: int = 0
    earned: Decimal = Decimal("0.00")
    published_at: datetime | None = None


class PerformanceDayOut(BaseModel):
    day: date
    earned: Decimal


class PerformanceOrdersOut(BaseModel):
    platform: str
    orders: int


class PerformanceBucketOut(BaseModel):
    label: str
    start: date
    end: date
    views: int
    helped: int
    earned: Decimal
    returned: Decimal
    current: bool
    #: Helpful / not-helpful votes cast in the bucket (Card/Votes).
    up: int = 0
    down: int = 0


class CommissionMarketplaceOut(BaseModel):
    platform: str
    gross_commission: Decimal
    orders: int


class CommissionProductOut(BaseModel):
    product_id: uuid.UUID | None = None
    name: str
    net_commission: Decimal
    orders: int
    #: None when no row reports a sales figure.
    sales: Decimal | None = None


class CommissionBreakdownOut(BaseModel):
    """The ⓘ sheet on "Where the commission went" (Figma 9057:47088)."""

    first_completed: datetime | None = None
    last_completed: datetime | None = None
    gross_sales: Decimal
    orders: int
    items: int
    #: What Gross sales is summed over: the orders and items reporting a sales figure.
    sales_orders: int = 0
    sales_items: int = 0
    gross_commission: Decimal
    #: Positive; drawn as −₱.
    reversals: Decimal
    cancelled_items: int
    refunded_items: int
    net_commission: Decimal
    #: The split of the net: the reviewer's Net earnings, the Honesty Fund, Bluntly.
    you: Decimal
    honesty_fund: Decimal
    bluntly: Decimal
    pending_commission: Decimal
    pending_orders: int
    #: The part of `you` the ledger actually credited to the member's wallet.
    credited: Decimal = Decimal("0.00")
    marketplaces: list[CommissionMarketplaceOut]
    #: Every product, most net commission first.
    products: list[CommissionProductOut]


class PerformanceOut(BaseModel):
    """Figma Screen/Performance (7848:9542): one product or all of them."""

    period: str
    product_id: uuid.UUID | None = None
    #: The product switcher: every product the caller has a published review of.
    products: list[PerformanceProductOut]
    totals: ContributorReachOut
    earned: Decimal
    returned: Decimal
    buckets: list[PerformanceBucketOut]
    #: Card/Review: average star rating and number of these reviews; all-time
    #: helpful votes and comments on them.
    rating: Decimal | None = None
    review_count: int = 0
    upvotes: int = 0
    comments: int = 0
    #: Card/Votes totals over the period.
    helpful: int = 0
    not_helpful: int = 0
    #: Card/Earnings: the last 30 Manila days, oldest first, with the 30- and 7-day sums.
    daily: list[PerformanceDayOut] = []
    earned_30d: Decimal = Decimal("0.00")
    earned_7d: Decimal = Decimal("0.00")
    #: Card/From view to buy: the last 7 days and the 7 before (its change chips).
    reach_week: ContributorReachOut | None = None
    reach_prev_week: ContributorReachOut | None = None
    #: Card/Commission: the split of every credited sale's net commission.
    share_you: Decimal = Decimal("0.00")
    share_honesty_fund: Decimal = Decimal("0.00")
    share_platform: Decimal = Decimal("0.00")
    #: Card/Buyers: completed orders per marketplace (Shopee and Lazada always).
    orders: list[PerformanceOrdersOut] = []
    commission: CommissionBreakdownOut | None = None


@router.get("/me/performance", response_model=PerformanceOut,
            summary="How your reviews perform: all products or one, by week or month")
def my_performance(
    product_id: uuid.UUID | None = Query(default=None),
    period: str = Query(default="month", pattern="^(week|month)$"),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> PerformanceOut:
    p = contributor_dashboard.performance(db, me, product_id=product_id, period=period)
    return PerformanceOut(
        period=p.period, product_id=p.product_id,
        products=[PerformanceProductOut(**x.__dict__) for x in p.products],
        totals=ContributorReachOut(**p.totals.__dict__), earned=p.earned, returned=p.returned,
        buckets=[PerformanceBucketOut(**b.__dict__) for b in p.buckets],
        rating=p.rating, review_count=p.review_count, upvotes=p.upvotes, comments=p.comments,
        helpful=p.helpful, not_helpful=p.not_helpful,
        daily=[PerformanceDayOut(**d.__dict__) for d in p.daily],
        earned_30d=p.earned_30d, earned_7d=p.earned_7d,
        reach_week=ContributorReachOut(**p.reach_week.__dict__) if p.reach_week else None,
        reach_prev_week=(ContributorReachOut(**p.reach_prev_week.__dict__)
                         if p.reach_prev_week else None),
        share_you=p.share_you, share_honesty_fund=p.share_honesty_fund,
        share_platform=p.share_platform,
        orders=[PerformanceOrdersOut(**o.__dict__) for o in p.orders],
        commission=CommissionBreakdownOut(
            **{k: v for k, v in p.commission.__dict__.items()
               if k not in ("marketplaces", "products")},
            marketplaces=[CommissionMarketplaceOut(**m.__dict__)
                          for m in p.commission.marketplaces],
            products=[CommissionProductOut(**x.__dict__) for x in p.commission.products]))


@router.get("/me/earnings", response_model=EarningsHistoryOut,
            summary="The signed-in reviewer's own earnings history")
def my_earnings(
    status: str = Query(default="all"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> EarningsHistoryOut:
    """Earnings for the caller and nobody else.

    No user id in the path, for the same reason as the dashboard: an endpoint
    that accepts one is an endpoint someone will eventually pass a different
    one to.
    """
    if status not in dashboard_service.EARNING_FILTERS:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {sorted(dashboard_service.EARNING_FILTERS)}")

    result = dashboard_service.earnings_history(db, me.id, status=status, limit=limit)
    return EarningsHistoryOut(
        all_time=str(result.all_time),
        counts=result.counts,
        has_data=result.has_data,
        rows=[
            EarningRowOut(
                commission_id=r.commission_id, occurred_on=r.occurred_on,
                review_id=r.review_id, review_title=r.review_title,
                product_name=r.product_name, photo_url=r.photo_url,
                amount=str(r.amount), status=r.status,
                breakdown=EarningBreakdownOut(
                    gross_amount=str(r.gross_amount),
                    commission_rate=(str(r.commission_rate)
                                     if r.commission_rate is not None else None),
                    platform_share=str(r.platform_share),
                    honesty_fund_share=str(r.honesty_fund_share),
                    reviewer_share=str(r.reviewer_share),
                ),
                is_test=r.is_test,
            )
            for r in result.rows
        ],
    )


class StreakDayOut(BaseModel):
    day: date
    contributed: bool


class ContributionStreakOut(BaseModel):
    current_streak: int
    last_contribution: date | None
    active_today: bool
    total_days: int
    calendar_month: date
    calendar: list[StreakDayOut]


@router.get("/me/streak", response_model=ContributionStreakOut,
            summary="The signed-in reviewer's contribution streak and calendar")
def my_streak(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
) -> ContributionStreakOut:
    """Days the caller contributed — never days they visited.

    Owner decision, 2026-08-27: this is a contribution streak. It is derived
    entirely from timestamps the application already stores (published reviews,
    questions, answers, price observations), so nothing here tracks reading or
    browsing, and no new telemetry was added to build it.

    No user id in the path, for the same reason as the dashboard and earnings.
    """
    result = contribution_streak.insights_streak(db, me.id)
    return ContributionStreakOut(
        current_streak=result.current_streak,
        last_contribution=result.last_contribution,
        active_today=result.active_today,
        total_days=result.total_days,
        calendar_month=result.calendar_month,
        calendar=[
            StreakDayOut(day=c.day, contributed=c.contributed)
            for c in result.calendar
        ],
    )

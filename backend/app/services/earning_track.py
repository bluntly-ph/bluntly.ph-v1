"""Which earning track a review is on (Business Rules §14). Pure; no database.

    "Which track a review is actually on - commission or Honesty Fund - is
    decided by the reviewer's own declared verdict (Yes / It's complicated /
    No), not the star rating: verdict decides cleanly for Yes or No, and star
    rating (>=3 vs <=2) only breaks the tie when the verdict is 'it's
    complicated.'"

This module is the ONLY place that rule is written down. Every caller — the
moderator's approval, the affiliate attach, a thread update that may flip the
track — asks `track_for` and does what it says.

The one hole in the rule is 2.5 stars. Ratings are 0 to 5 in half steps
(migration 0048), so "it's complicated" at 2.5 is a real review and the rule's
">= 3 vs <= 2" does not cover it. Owner decision A (2026-09-28) settles it:
such a thread goes to neither track automatically. It is ESCALATED — an
administrator's earnings approval lands it on `pending_superadmin_routing`, and
only a Super Admin sends it to the Honesty Fund or to the platform
(app/services/special_routing.py). `track_for` returns `SUPERADMIN_ROUTING`
for it; `effective_track` adds the Super Admin's decision once there is one.
"""

from __future__ import annotations

import enum
from decimal import Decimal

from app.models.enums import EarnEligibleStatus, SpecialRoute, Verdict

#: The one rating the tie-break does not decide on its own.
SPECIAL_ROUTING_STARS = Decimal("2.5")


class EarningTrack(str, enum.Enum):
    commission = "commission"
    honesty_fund = "honesty_fund"
    #: "It's complicated" at exactly 2.5 stars: a Super Admin decides.
    superadmin_routing = "superadmin_routing"


SUPERADMIN_ROUTING = EarningTrack.superadmin_routing


def _stars(value: float | Decimal | int) -> Decimal:
    return Decimal(str(value))


def _tie_break(stars: Decimal) -> EarningTrack:
    if stars >= 3:
        return EarningTrack.commission
    if stars <= 2:
        return EarningTrack.honesty_fund
    # 2 < stars < 3: on the half-step scale, exactly 2.5.
    return SUPERADMIN_ROUTING


def track_for(verdict: Verdict, star_rating: float | Decimal | int) -> EarningTrack:
    """The earning track a review's verdict (and, only for it_depends, its stars) selects."""
    if verdict == Verdict.yes_absolutely:
        return EarningTrack.commission
    if verdict == Verdict.hard_pass:
        return EarningTrack.honesty_fund
    return _tie_break(_stars(star_rating))


def effective_track(track: EarningTrack, special_route: SpecialRoute | None) -> EarningTrack:
    """The track once a Super Admin's 2.5 decision is taken into account.

    PLATFORM is the commission route (a link may be attached) with the
    reviewer's share kept by the platform — `earnings.split_for_review` reads
    `special_route` for the money; the track only says a link is allowed.
    """
    if track != SUPERADMIN_ROUTING or special_route is None:
        return track
    if special_route == SpecialRoute.honesty_fund:
        return EarningTrack.honesty_fund
    return EarningTrack.commission


def approved_status_for(track: EarningTrack) -> EarnEligibleStatus:
    """The earn_eligible status an administrator's approval lands on for a track."""
    if track == EarningTrack.honesty_fund:
        return EarnEligibleStatus.honesty_fund
    if track == EarningTrack.commission:
        return EarnEligibleStatus.approved
    return EarnEligibleStatus.pending_superadmin_routing


def verdict_star_mismatch(verdict: Verdict, star_rating: float | Decimal | int) -> bool:
    """A verdict the stars flatly contradict, outside the it_depends tie-break.

    "Yes, absolutely!" at 2 stars or fewer, or "Hard pass" at 3 or more. The
    verdict still decides the track — the stars never silently override it — but
    the contradiction is surfaced to moderators as an integrity signal.
    """
    stars = _stars(star_rating)
    if verdict == Verdict.yes_absolutely:
        return stars <= 2
    if verdict == Verdict.hard_pass:
        return stars >= 3
    return False


#: The fixed split of every monetized commission (§14): basis points of gross.
PLATFORM_BPS = 4000
REVIEWER_BPS = 3000
HONESTY_FUND_BPS = 3000
assert PLATFORM_BPS + REVIEWER_BPS + HONESTY_FUND_BPS == 10_000

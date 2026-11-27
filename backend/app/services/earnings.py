"""Commission split arithmetic (FR-6, §3.3).

The 40/30/30 split must be exact to the centavo and always re-sum to the gross
(no rounding leakage). The platform share absorbs the rounding remainder.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.constants import HONESTY_FUND_SHARE, REVIEWER_SHARE

_CENT = Decimal("0.01")


def split_commission(gross: Decimal) -> dict[str, Decimal]:
    """Split `gross` 40/30/30. Reviewer & Honesty Fund are rounded to the centavo;
    the platform share takes the remainder so the three always sum to `gross`.
    """
    gross = Decimal(gross).quantize(_CENT, rounding=ROUND_HALF_UP)
    reviewer = (gross * REVIEWER_SHARE).quantize(_CENT, rounding=ROUND_HALF_UP)
    honesty = (gross * HONESTY_FUND_SHARE).quantize(_CENT, rounding=ROUND_HALF_UP)
    platform = gross - reviewer - honesty

    return {
        "gross_amount": gross,
        "platform_share": platform,
        "reviewer_share": reviewer,
        "honesty_fund_share": honesty,
    }


# Above this the platform share would go negative before rounding is even
# considered (the 30% Honesty Fund is fixed). At exactly 7000 it can still
# land at -0.01 when both shares round up, which is what `platform` guards
# against below.
MAX_REVIEWER_SHARE_BPS = 7000


def split_commission_tiered(gross: Decimal, reviewer_share_bps: int) -> dict[str, Decimal]:
    """Tier-based split (M2 slice 6). Honesty Fund is a FIXED 30% (capstone
    invariant); the reviewer takes `reviewer_share_bps`/10000 (standard 3000,
    founding 3500, special 4000); the platform absorbs the rounding remainder so
    the three ALWAYS sum to `gross` to the centavo.
    """
    if not 0 <= reviewer_share_bps <= MAX_REVIEWER_SHARE_BPS:
        raise ValueError(f"reviewer_share_bps must be 0..{MAX_REVIEWER_SHARE_BPS}")
    gross = Decimal(gross).quantize(_CENT, rounding=ROUND_HALF_UP)
    reviewer = (gross * Decimal(reviewer_share_bps) / Decimal(10000)).quantize(
        _CENT, rounding=ROUND_HALF_UP)
    honesty = (gross * HONESTY_FUND_SHARE).quantize(_CENT, rounding=ROUND_HALF_UP)
    platform = gross - reviewer - honesty

    # At 7000 bps the shares are 70% and 30%, each rounded HALF_UP
    # independently - so when both round up they exceed `gross` by a centavo and
    # the platform, which absorbs the remainder, lands at -0.01. Measured on 373
    # of 4000 random amounts. No configured tier reaches 7000 (standard 3000,
    # founding 3500, special 4000), so this is a boundary rather than a live
    # bug - but a negative share should not be representable at all, and the
    # cap's own comment implied at-and-below it was safe.
    #
    # The reviewer gives up the centavo, not the Honesty Fund: the fund's 30% is
    # the capstone invariant, and a negative platform share would mean the
    # platform paid to broker the sale.
    if platform < 0:
        reviewer += platform
        platform = Decimal("0.00")

    return {
        "gross_amount": gross,
        "platform_share": platform,
        "reviewer_share": reviewer,
        "honesty_fund_share": honesty,
    }


#: Business Rules §14: every monetized review splits the same way, always —
#: 40% platform, 30% reviewer, 30% Honesty Fund. No tiers, no contracts.
FLAT_REVIEWER_BPS = 3000


def reviewer_routes_to_fund(review, author) -> bool:
    """True when this sale's reviewer share goes to the Honesty Fund instead.

    A thread on the fund track earns for the fund "from that point on" (§14),
    and a claimed seller never earns (§9). Neither claws back money already
    credited: this only decides the split of a sale being recognised now.
    """
    from app.models.enums import EarnEligibleStatus
    if author is not None and getattr(author, "is_claimed_seller", False):
        return True
    # Owner decision 2026-09-28: when the author deletes the review, its
    # "future earning stops immediately". A sale recognised after that — the
    # link's sub-ID lives on in buyers' carts — credits no reviewer; the share
    # follows the fund track's redirect, as §14 does for a thread that moved
    # to the fund "from that point on". Nothing already credited is touched.
    if getattr(review, "removed_by_author_at", None) is not None:
        return True
    return review.earn_eligible_status == EarnEligibleStatus.honesty_fund


def reviewer_routes_to_platform(review) -> bool:
    """Owner decision A: a Super Admin routed this 2.5-star "It depends"
    thread to the PLATFORM — the commission route, with the reviewer's share
    kept by the platform. The Honesty Fund's own share is untouched."""
    from app.models.enums import SpecialRoute
    return getattr(review, "special_route", None) == SpecialRoute.platform


def held_for_routing(review) -> bool:
    """A sale for a thread still waiting on a Super Admin is not recognised yet.

    Its destination is undecided, so crediting anyone would be a guess. The
    importers skip it as held; the same row is picked up once routed (the CSV
    importer dedupes by file and line, the lifecycle importer retries a
    completed sale that was never earned).
    """
    from app.models.enums import EarnEligibleStatus
    return review.earn_eligible_status == EarnEligibleStatus.pending_superadmin_routing


def split_for_review(gross: Decimal, review, author) -> tuple[dict[str, Decimal], int]:
    """The flat split for one recognised sale, and the reviewer bps it used."""
    split = split_commission(gross)
    if reviewer_routes_to_fund(review, author):
        split["honesty_fund_share"] += split["reviewer_share"]
        split["reviewer_share"] = Decimal("0.00")
        return split, 0
    if reviewer_routes_to_platform(review):
        split["platform_share"] += split["reviewer_share"]
        split["reviewer_share"] = Decimal("0.00")
        return split, 0
    return split, FLAT_REVIEWER_BPS

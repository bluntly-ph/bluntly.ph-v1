"""Store profile and giving a store up (Figma Screen/Seller/StoreProfile
8209:23011, Overlay/Store/RequestChange 8209:23626, Confirm/Store/GiveUp
8220:24024).

The profile is what buyers see plus how the claim was verified, for the
approved owner only. The registration number is never returned whole: the
frame shows "DTI · ending 4821", and nothing on this screen needs more.

Name, link and registration changes are not edits: the name and link come from
the marketplace, so the owner asks the team in a conversation (topic account)
and a moderator makes the change. Giving the store up is the one change the
owner makes alone, because it only takes their own access away.
"""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.enums import ModerationAction, SellerClaimStatus, StoreProductStatus
from app.models.moderation import ModerationLog
from app.models.seller import Seller, SellerClaim, SellerReview, StoreProduct
from app.models.user import User
from app.services.seller_insights import _short
from app.services.seller_service import normalize_seller_name, require_store_owner


@dataclass
class Ownership:
    registration_kind: str | None
    registration_last4: str | None
    registered_business_name: str | None
    marketplace_shop_name: str | None
    shop_name_matches: bool | None
    approved_at: datetime | None
    owner_name: str


@dataclass
class StoreProfile:
    id: uuid.UUID
    display_name: str
    platform: str
    store_url: str | None
    on_bluntly_since: datetime
    rating: float | None
    reviews: int
    ownership: Ownership


def _matches(shop_name: str | None, seller: Seller) -> bool | None:
    if not shop_name:
        return None
    try:
        return normalize_seller_name(shop_name) == seller.normalized_name
    except ValueError:  # blank after normalising: no name to match
        return False


def profile(db: Session, seller_id: uuid.UUID, user: User) -> StoreProfile:
    seller = db.get(Seller, seller_id)
    if seller is None:
        raise NotFoundError("Seller not found.", code="seller_not_found")
    require_store_owner(seller, user)
    ratings = [float(r) for r in db.scalars(select(SellerReview.overall_rating).where(
        SellerReview.seller_id == seller.id, SellerReview.is_removed.is_(False)))]
    claim = db.scalars(select(SellerClaim).where(
        SellerClaim.seller_id == seller.id, SellerClaim.user_id == user.id,
        SellerClaim.status == SellerClaimStatus.claimed)
        .order_by(SellerClaim.decided_at.desc().nulls_last())).first()
    number = (claim.registration_number or "") if claim else ""
    digits = "".join(ch for ch in number if ch.isalnum())
    return StoreProfile(
        id=seller.id, display_name=seller.display_name,
        platform=getattr(seller.platform, "value", str(seller.platform)),
        store_url=seller.store_url, on_bluntly_since=seller.created_at,
        rating=round(float(statistics.median(ratings)), 2) if ratings else None,
        reviews=len(ratings),
        ownership=Ownership(
            registration_kind=claim.registration_kind if claim else None,
            registration_last4=digits[-4:] if len(digits) >= 4 else None,
            registered_business_name=claim.registered_business_name if claim else None,
            marketplace_shop_name=claim.marketplace_shop_name if claim else None,
            shop_name_matches=_matches(claim.marketplace_shop_name if claim else None, seller),
            approved_at=claim.decided_at if claim else None,
            owner_name=_short(user)))


def give_up(db: Session, seller_id: uuid.UUID, user: User) -> None:
    """The owner gives the store up (Confirm/Store/GiveUp).

    The store becomes unclaimed: responses, answers and analytics close for this
    account at once. Past responses and store answers stay up (they were public
    when written). The §9 limits stay on the account: `is_claimed_seller` is
    one-way. Waiting product-link requests end with the ownership; approved
    links stay, since they describe the store, not the owner. Row-locked so a
    moderator approving a rival claim at the same moment sees one outcome.
    Audited as `store_release`.
    """
    seller = db.get(Seller, seller_id, with_for_update=True)
    if seller is None:
        raise NotFoundError("Seller not found.", code="seller_not_found")
    require_store_owner(seller, user)
    now = datetime.now(UTC)
    seller.claimed_by_id = None
    seller.claim_status = SellerClaimStatus.unclaimed
    db.execute(update(StoreProduct).where(
        StoreProduct.seller_id == seller.id, StoreProduct.status == StoreProductStatus.pending)
        .values(status=StoreProductStatus.cancelled, decided_at=now,
                decision_note="The owner gave up the store."))
    db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=user.id,
                         action=ModerationAction.store_release, target_ref=seller.id,
                         notes="the owner gave up the store",
                         context={"seller_id": str(seller.id), "store": seller.display_name}))
    db.commit()

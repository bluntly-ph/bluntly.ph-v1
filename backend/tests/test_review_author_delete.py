"""The author deletes their own review (Business Rules §4; owner decision
2026-09-28: "users still have no practical way to delete their own reviews").

What must hold, each tested against the real API and database:

* only the author can delete — not a stranger, not a claimed seller, not
  staff: a moderator removing content is a TAKEDOWN, a different action with
  a different record, never "removed by author";
* deleting the original takes the whole thread and needs the confirmation;
* a repeated or concurrent delete is safe;
* earning stops: the link is revoked and a sale recognised afterwards credits
  no reviewer; money already credited is never clawed back;
* a thread that had paid out leaves only the product's aggregate trace;
* the review disappears from every public read.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import (
    CommissionTarget,
    EarnEligibleStatus,
    ModerationAction,
    Platform,
    ReferralLinkStatus,
)
from app.models.moderation import ModerationLog
from app.models.review import ReferralLink, Review
from app.models.user import User
from app.services import earnings, wallet
from tests.conftest import owned_photo_url, register_and_token, requires_db

CONFIRM = "?confirm=delete-thread"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, h) -> str:
    r = client.post("/api/v1/products", headers=h,
                    json={"name": f"DeleteWidget {uuid.uuid4().hex[:8]}",
                          "category": "electronics"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _review(client, h, pid, title="Deletable review") -> str:
    r = client.post("/api/v1/reviews", headers=h, json={
        "product_id": pid, "title": title, "discussion": "Weeks of daily use.",
        "verdict": "yes_absolutely", "star_rating": 4, "photo_url": owned_photo_url(h)})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _author_and_review(client):
    uid, token, _ = register_and_token(client)
    h = _auth(token)
    pid = _product(client, h)
    return uid, h, pid, _review(client, h, pid)


def _set(review_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        r = db.get(Review, uuid.UUID(review_id))
        for k, v in fields.items():
            setattr(r, k, v)
        db.commit()
    finally:
        db.close()


def _audits(review_id: str, action: ModerationAction) -> int:
    db = SessionLocal()
    try:
        return db.scalar(select(func.count(ModerationLog.id)).where(
            ModerationLog.target_ref == uuid.UUID(review_id),
            ModerationLog.action == action)) or 0
    finally:
        db.close()


# ---------------------------------------------------------------- who may delete

@requires_db
def test_only_the_author_can_delete(client):
    _, h, _, rid = _author_and_review(client)
    url = f"/api/v1/reviews/{rid}{CONFIRM}"
    assert client.delete(url).status_code == 401

    _, stranger, _ = register_and_token(client)
    denied = client.delete(url, headers=_auth(stranger))
    assert denied.status_code == 403 and denied.json()["code"] == "not_review_author"

    seller_id, seller, _ = register_and_token(client)
    db = SessionLocal()
    try:
        db.get(User, uuid.UUID(seller_id)).is_claimed_seller = True
        db.commit()
    finally:
        db.close()
    assert client.delete(url, headers=_auth(seller)).status_code == 403

    # Staff cannot delete on the author's behalf: their tool is a takedown.
    _, mod, _ = register_and_token(client, role="administrator")
    assert client.delete(url, headers=_auth(mod)).status_code == 403
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200
    assert _audits(rid, ModerationAction.author_delete) == 0


@requires_db
def test_the_original_needs_the_confirmation_and_takes_the_thread(client):
    _, h, pid, rid = _author_and_review(client)
    refused = client.delete(f"/api/v1/reviews/{rid}", headers=h)
    assert refused.status_code == 409
    assert refused.json()["code"] == "thread_delete_confirmation_required"
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200

    ok = client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h)
    assert ok.status_code == 200, ok.text
    assert rid in ok.json()["removed_ids"]
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 404
    db = SessionLocal()
    try:
        r = db.get(Review, uuid.UUID(rid))
        # Never a hard delete and never blanked text: the row stays, marked.
        assert r.is_removed and r.removed_by_author_at is not None
        assert r.title == "Deletable review"
    finally:
        db.close()
    assert _audits(rid, ModerationAction.author_delete) == 1


@requires_db
def test_a_repeated_delete_is_safe(client):
    _, h, _, rid = _author_and_review(client)
    assert client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code == 200
    again = client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h)
    assert again.status_code == 200 and again.json()["removed_ids"] == []
    assert _audits(rid, ModerationAction.author_delete) == 1
    # Someone else probing a deleted review learns nothing new.
    _, stranger, _ = register_and_token(client)
    probe = client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=_auth(stranger))
    assert probe.status_code == 404


@requires_db
def test_concurrent_deletes_record_one_deletion(client):
    _, h, _, rid = _author_and_review(client)
    results: list[int] = []

    def go():
        results.append(client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code)

    threads = [threading.Thread(target=go) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(200) == 3, results
    assert _audits(rid, ModerationAction.author_delete) == 1


# ---------------------------------------------------------------- earning stops

@requires_db
def test_delete_while_earnings_are_pending(client):
    _, h, _, rid = _author_and_review(client)
    _set(rid, earn_eligible_status=EarnEligibleStatus.pending)
    assert client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code == 200
    _, mod, _ = register_and_token(client, role="administrator")
    # Nothing left to approve: the review is gone from the public site.
    approve = client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings", headers=_auth(mod))
    assert approve.status_code in (404, 409), approve.text


@requires_db
def test_delete_after_affiliate_approval_stops_future_earning(client):
    uid, h, _, rid = _author_and_review(client)
    sub_id = f"blt_{uuid.uuid4().hex[:10]}"
    db = SessionLocal()
    try:
        db.add(ReferralLink(review_id=uuid.UUID(rid), platform=Platform.shopee,
                            url="https://shopee.ph/p", sub_id=sub_id,
                            status=ReferralLinkStatus.active, review_version=1))
        db.get(Review, uuid.UUID(rid)).earn_eligible_status = EarnEligibleStatus.monetized
        db.commit()
    finally:
        db.close()
    assert client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code == 200

    db = SessionLocal()
    try:
        link = db.scalar(select(ReferralLink).where(ReferralLink.sub_id == sub_id))
        assert link.status == ReferralLinkStatus.revoked
        # A sale recognised after the deletion (the sub-ID lives on in carts):
        # the canonical split credits no reviewer.
        review = db.get(Review, uuid.UUID(rid))
        author = db.get(User, uuid.UUID(uid))
        split, bps = earnings.split_for_review(Decimal("100.00"), review, author)
        assert bps == 0 and split["reviewer_share"] == Decimal("0.00")
        assert split["honesty_fund_share"] == Decimal("60.00")
    finally:
        db.close()
    # The public redirect is gone too.
    assert client.get(f"/api/v1/r/{rid}", follow_redirects=False).status_code in (404, 410)


@requires_db
def test_delete_after_payment_keeps_the_money_and_the_aggregate_trace(client):
    uid, h, pid, rid = _author_and_review(client)
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(rid))
        author = db.get(User, uuid.UUID(uid))
        split, bps = earnings.split_for_review(Decimal("200.00"), review, author)
        db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                          target_type=CommissionTarget.review, review_id=review.id,
                          reviewer_id=author.id, reviewer_share_bps=bps, platform=Platform.shopee,
                          cleared_at=datetime.now(UTC), currency="PHP",
                          csv_source=f"delete-test:{uuid.uuid4().hex[:8]}", row_reference="1",
                          cycle_month=date(1975, 1, 1), **split))
        wallet.adjust(db, author.id, split["reviewer_share"])
        db.commit()
    finally:
        db.close()
    before = client.get(f"/api/v1/products/{pid}").json()["removed_after_payout_count"]

    assert client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code == 200

    db = SessionLocal()
    try:
        assert db.get(User, uuid.UUID(uid)).wallet_balance == Decimal("60.00")   # not clawed back
        assert db.get(Review, uuid.UUID(rid)).removed_after_payout is True
        assert db.scalar(select(func.count(Commission.id)).where(
            Commission.review_id == uuid.UUID(rid))) == 1                        # ledger intact
    finally:
        db.close()
    product = client.get(f"/api/v1/products/{pid}").json()
    assert product["removed_after_payout_count"] == before + 1
    # Only the aggregate: the review itself, and its earnings, stay unreachable.
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 404


# ---------------------------------------------------------------- public views

@requires_db
def test_a_deleted_review_leaves_every_public_read(client):
    _, h, pid, rid = _author_and_review(client)
    feed = client.get("/api/v1/reviews/feed", params={"product_id": pid, "limit": 10}).json()
    assert rid in [i["review"]["id"] for i in feed]
    assert client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code == 200
    feed = client.get("/api/v1/reviews/feed", params={"product_id": pid, "limit": 10}).json()
    assert rid not in [i["review"]["id"] for i in feed]
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 404
    assert client.get(f"/api/v1/reviews/{rid}/versions").status_code == 404
    assert client.get(f"/api/v1/reviews/{rid}/comments").status_code == 404


@requires_db
def test_author_deletion_and_staff_takedown_are_told_apart(client):
    """A takedown is staff removing content; it must never read as the author's
    choice, and it records who, why and what the review was before."""
    _, h, _, rid = _author_and_review(client)
    _, mod, _ = register_and_token(client, role="administrator")
    down = client.post(f"/api/v1/admin/reviews/{rid}/unpublish", headers=_auth(mod),
                       json={"reason": "Test content"})
    assert down.status_code == 200, down.text
    db = SessionLocal()
    try:
        r = db.get(Review, uuid.UUID(rid))
        assert r.published_at is None and r.removed_by_author_at is None
        assert r.removed_after_payout is False
        log = db.scalar(select(ModerationLog).where(
            ModerationLog.target_ref == r.id, ModerationLog.action == ModerationAction.unpublish))
        assert log.moderator_id is not None and log.notes == "Test content"
        assert "previous_status" in log.context and "previous_published_at" in log.context
    finally:
        db.close()
    assert _audits(rid, ModerationAction.author_delete) == 0
    # Members and sellers cannot take anything down.
    _, member, _ = register_and_token(client)
    assert client.post(f"/api/v1/admin/reviews/{rid}/unpublish", headers=_auth(member),
                       json={"reason": "x"}).status_code == 403
    # The author can still delete their own taken-down review, and that IS theirs.
    assert client.delete(f"/api/v1/reviews/{rid}{CONFIRM}", headers=h).status_code == 200
    assert _audits(rid, ModerationAction.author_delete) == 1


@requires_db
def test_a_takedown_without_a_reason_is_refused(client):
    """Owner decision 2026-09-28: staff always say why. A missing or blank
    reason is refused on the server, not only in the dialog, and nothing moves."""
    _, _, _, rid = _author_and_review(client)
    _, mod, _ = register_and_token(client, role="administrator")
    for body in ({}, {"reason": ""}, {"reason": "   "}):
        refused = client.post(f"/api/v1/admin/reviews/{rid}/unpublish",
                              headers=_auth(mod), json=body)
        assert refused.status_code == 422, (body, refused.text)
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200
    assert _audits(rid, ModerationAction.unpublish) == 0

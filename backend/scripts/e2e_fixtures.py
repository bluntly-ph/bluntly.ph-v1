"""Seed the state the browser journeys start from, and print it as JSON.

Browser journeys (e2e/br-journeys.spec.ts) drive the real production build
against the real API and a real Postgres. Signing in is an emailed code, which a
browser cannot receive in CI, so this creates the accounts directly — each with a
genuine access token the page's own session cookie carries — and every piece of
state a journey starts from: a product with a searchable alias, a review old
enough to take an update, cleared and uncleared money, a claimed store with a
buyer's review of it, a question with an answer.

It writes through the API in-process wherever an endpoint exists (so validation
and side effects are the real ones) and touches the database directly only for
what no endpoint may do: roles, trust stages, back-dating, and funding.

Refuses production before anything is written.

Usage:
  python -m scripts.e2e_fixtures out.json
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.env_guard import guard_cli


def main(out_path: str) -> None:
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.core.security import create_access_token
    from app.db.session import SessionLocal
    from app.main import app
    from app.models.commission import Commission
    from app.models.enums import CommissionTarget, MemberRole, Platform
    from app.models.honesty_fund import HonestyFundDistribution
    from app.models.review import Review
    from app.models.user import User

    settings.auth_rate_limit_max = 1_000_000
    settings.vote_rate_limit_max = 1_000_000
    c = TestClient(app)
    tag = uuid.uuid4().hex[:6]
    users: dict[str, dict] = {}

    def user(name: str, *, role: str = "user", stage: int = 1, age_days: int = 60,
             reputation: str = "80.00") -> dict:
        email = f"e2e_{name}_{tag}@example.com"
        r = c.post("/api/v1/auth/register", json={"email": email, "password": "password123"})
        assert r.status_code == 201, r.text
        uid = r.json()["user"]["id"]
        db = SessionLocal()
        try:
            u = db.get(User, uuid.UUID(uid))
            u.username = f"{name}{tag}"
            u.display_name = f"{name.title()} E2E"
            u.interests = ["electronics-tech"]
            u.role = MemberRole(role)
            u.trust_stage = stage
            u.reputation_score = Decimal(reputation)
            u.created_at = datetime.now(UTC) - timedelta(days=age_days)
            db.commit()
        finally:
            db.close()
        token = create_access_token(uuid.UUID(uid), role)
        users[name] = {"id": uid, "token": token, "username": f"{name}{tag}"}
        return {"Authorization": f"Bearer {token}"}

    reviewer = user("reviewer", stage=2)
    voter = user("voter", stage=2)
    commenter = user("commenter", stage=1)
    asker = user("asker", stage=1)
    user("claimant", stage=1)
    buyer = user("buyer", stage=1)
    user("suspect", stage=2)
    mod = user("administrator", role="administrator", stage=3)
    # The deterministic Super Admin (owner decision D): user management and the
    # 2.5-star routing queue.
    user("superadmin", role="super_admin", stage=3)
    # Mentioned by qa-round3's notification journey and by nothing else, so its
    # unread count moves only when that journey moves it.
    user("mentionee", stage=1)
    owner = user("owner", stage=1)

    def product(h: dict, name: str, category: str = "electronics") -> str:
        r = c.post("/api/v1/products", headers=h, json={
            "name": name, "category": category,
            "source_url": f"https://shopee.ph/x-i.1.{uuid.uuid4().int % 10**12}"})
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def review(h: dict, pid: str, title: str, **kw) -> str:
        body = {"product_id": pid, "title": title, "star_rating": kw.get("stars", 4),
                "discussion": kw.get("discussion", "Quiet on low, loud on turbo; a full commute."),
                "verdict": kw.get("verdict", "yes_absolutely")}
        r = c.post("/api/v1/reviews", headers=h, json=body)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    fan = product(reviewer, f"Jisulife Fanlife 9 {tag}")
    fresh_pid = product(reviewer, f"Anker Nano 737 {tag}")
    old_review = review(reviewer, fan, "Great fan for commuting")
    fresh_review = review(reviewer, fresh_pid, "Tiny and quick")
    doomed_pid = product(reviewer, f"Baseus Blade {tag}")
    doomed_review = review(reviewer, doomed_pid, "Thin power bank")
    db = SessionLocal()
    try:                        # the fan review is four months old: update-ready
        r = db.get(Review, uuid.UUID(old_review))
        r.created_at = r.published_at = datetime.now(UTC) - timedelta(days=125)
        db.commit()
    finally:
        db.close()

    # Money: ₱700 cleared through a real inflow, ₱300 credited but uncleared.
    # The sale's cycle is the run's own (a month is remitted once, and the
    # Affiliate Months row is how br-journeys records it): 1900-1969.
    cycle_n = int(tag, 16) % 840
    remit_cycle = date(1900 + cycle_n // 12, cycle_n % 12 + 1, 1)
    db = SessionLocal()
    try:
        rid = uuid.UUID(users["reviewer"]["id"])
        db.add(HonestyFundDistribution(
            distribution_id=f"hfd_e2e_{uuid.uuid4().hex[:8]}", cycle_month=date(1970, 1, 1),
            review_id=None, reviewer_id=rid, honesty_score=Decimal("1"),
            pool_amount=Decimal("700.00"), payout_amount=Decimal("700.00")))
        db.add(Commission(
            commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=uuid.UUID(old_review), reviewer_id=rid, reviewer_share_bps=3000,
            gross_amount=Decimal("1000.00"), platform_share=Decimal("400.00"),
            reviewer_share=Decimal("300.00"), honesty_fund_share=Decimal("300.00"),
            currency="PHP", csv_source=f"e2e:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=remit_cycle, platform=Platform.shopee, cleared_at=None))
        u = db.get(User, rid)
        u.wallet_balance = Decimal("1000.00")
        u.payout_account = "payee@example.com"
        db.commit()
    finally:
        db.close()

    # Q&A: the asker's question, answered by the reviewer.
    q = c.post("/api/v1/questions", headers=asker,
               json={"product_id": fan, "body": "Does it get hot after an hour on turbo?"})
    assert q.status_code == 201, q.text
    a = c.post(f"/api/v1/questions/{q.json()['id']}/answers", headers=reviewer,
               json={"body": "Warm, not hot. Fine for an hour.", "rating": "4"})
    assert a.status_code == 201, a.text

    # A claimed store (the owner's) with the buyer's review of it; and an
    # unclaimed store for the claim journey.
    store = c.post("/api/v1/sellers", headers=owner, json={
        "display_name": f"FanHub {tag}", "platform": "lazada"}).json()
    claim = c.post(f"/api/v1/sellers/{store['id']}/claims", headers=owner, json={
        "registration_kind": "dti", "registration_number": "DTI-7654321",
        "registered_business_name": "FanHub Trading",
        "marketplace_shop_name": store["display_name"],
        "evidence": None})
    assert claim.status_code == 201, claim.text
    decided = c.post(f"/api/v1/admin/seller-claims/{claim.json()['id']}/decision", headers=mod,
                     json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    seller_review = c.post(f"/api/v1/sellers/{store['id']}/reviews", headers=buyer, json={
        "accuracy": False, "order_completeness": True, "customer_service": 1,
        "packaging_quality": 2, "overall_rating": 1, "would_recommend": False,
        "comment": "Never arrived.", "order_id": "ORD-2409"})
    assert seller_review.status_code == 201, seller_review.text
    open_store = c.post("/api/v1/sellers", headers=voter, json={
        "display_name": f"OpenShop {tag}", "platform": "shopee"}).json()

    # Figma parity (2026-09-24). Two reviews of the OPEN store, one of them a
    # half star — a 4.5 must appear under the 4-star tick (QA-057). Kept off
    # the claimed store, whose single review the owner-response journey acts
    # on. And a store question the owner answered, for "N questions answered"
    # on the Sellers tab (QA-052).
    half = c.post(f"/api/v1/sellers/{open_store['id']}/reviews", headers=voter, json={
        "accuracy": True, "order_completeness": True, "customer_service": 5,
        "packaging_quality": 4, "overall_rating": 4.5, "would_recommend": True,
        "comment": "Arrived early, well packed.", "order_id": "ORD-2410"})
    assert half.status_code == 201, half.text
    slow = c.post(f"/api/v1/sellers/{open_store['id']}/reviews", headers=buyer, json={
        "accuracy": True, "order_completeness": True, "customer_service": 2,
        "packaging_quality": 3, "overall_rating": 2, "would_recommend": False,
        "comment": "Slow to ship.", "order_id": "ORD-2411"})
    assert slow.status_code == 201, slow.text
    store_q = c.post("/api/v1/questions", headers=asker, json={
        "seller_id": store["id"], "body": "Do you ship to Cebu?"})
    assert store_q.status_code == 201, store_q.text
    store_a = c.post(f"/api/v1/questions/{store_q.json()['id']}/answers", headers=owner,
                     json={"body": "Yes, two to four days."})
    assert store_a.status_code == 201, store_a.text
    # A review filed under a second category, for choosing several at once.
    beauty_pid = product(reviewer, f"Kojie San Soap {tag}", category="beauty")
    beauty_review = review(reviewer, beauty_pid, f"Gentle soap {tag}")

    # Comments need a thread to live on; the commenter's own comment.
    # QA sandbox payments (owner decision, 2026-09-27): a named QA tester with
    # one published review, for qa-payments.spec.ts. Naming a tester is the
    # site owner's action; fixtures write the list directly, the way the
    # owner's endpoint does, rather than impersonate the owner's account.
    qatester = user("qatester", stage=1)
    qa_review = review(qatester, product(qatester, f"Xiaomi Buds 5 {tag}"), "Buds for QA payouts")
    db = SessionLocal()
    try:
        from app.models.triage import PlatformSetting
        from app.services import qa_sandbox_service
        ids = qa_sandbox_service.tester_ids(db) | {uuid.UUID(users["qatester"]["id"])}
        row = db.get(PlatformSetting, qa_sandbox_service.SETTINGS_KEY)
        value = {"user_ids": sorted(str(i) for i in ids)}
        if row is None:
            db.add(PlatformSetting(key=qa_sandbox_service.SETTINGS_KEY, value=value))
        else:
            row.value = value
        db.commit()
    finally:
        db.close()

    comment = c.post(f"/api/v1/reviews/{fresh_review}/comments", headers=commenter,
                     json={"body": "Mine to delete."})
    assert comment.status_code == 201, comment.text
    _ = voter, mod

    # Reports (reporting-journeys.spec.ts): the June 1996 cycle belongs to these
    # journeys alone. Two reviewers either side of the PHP 300 cashout minimum,
    # both cleared by a recorded Shopee remittance; a Hard-pass review on the
    # Honesty Fund track with a sale of its own; and a second claimed store, so
    # one owner can be shown not to read another's rating summary.
    from app.models.commission import MarketplaceRemittance
    from app.models.enums import EarnEligibleStatus
    from app.services import earnings, wallet
    near = user("nearcash", stage=2)
    rich = user("atcash", stage=2)
    near_review = review(near, product(near, f"Report Fan {tag}"), "Report fan review")
    rich_review = review(rich, product(rich, f"Report Charger {tag}"), "Report charger review")
    fund_review = review(near, product(near, f"Report Lamp {tag}"), "Lamp flickers",
                         verdict="hard_pass", stars=1)
    cycle = date(1996, 6, 1)
    db = SessionLocal()
    try:
        def sale(review_id: str, gross: str) -> Decimal:
            r = db.get(Review, uuid.UUID(review_id))
            author = db.get(User, r.author_id)
            split, bps = earnings.split_for_review(Decimal(gross), r, author)
            db.add(Commission(
                commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
                review_id=r.id, reviewer_id=author.id, reviewer_share_bps=bps,
                currency="PHP", csv_source=f"e2e-report:{uuid.uuid4().hex}", row_reference="1",
                cycle_month=cycle, platform=Platform.shopee, cleared_at=datetime.now(UTC),
                order_status="Completed", **split))
            wallet.adjust(db, author.id, split["reviewer_share"])
            return Decimal(gross)

        db.get(Review, uuid.UUID(fund_review)).earn_eligible_status = \
            EarnEligibleStatus.honesty_fund
        db.flush()
        received = (sale(near_review, "999.97") + sale(rich_review, "1000.00")
                    + sale(fund_review, "20.00"))
        existing = db.scalar(select(MarketplaceRemittance).where(
            MarketplaceRemittance.platform == Platform.shopee,
            MarketplaceRemittance.cycle_month == cycle))
        if existing is None:
            db.add(MarketplaceRemittance(platform=Platform.shopee, cycle_month=cycle,
                                         amount_received=received, received_on=date(1996, 7, 20),
                                         reference="E2E-REMIT"))
        for who in ("nearcash", "atcash"):
            db.get(User, uuid.UUID(users[who]["id"])).payout_account = f"{who}@example.com"
        db.commit()
    finally:
        db.close()
    # The statement journeys' own reviewer and cycle (Nov 1996): one uncleared
    # Shopee sale of PHP 1,000.00. Kept apart from "reviewer", whose per-run cycle
    # sale br-journeys clears with a remittance while these journeys run.
    statementer = user("statementer", stage=2)
    statement_review = review(statementer, product(statementer, f"Report Kettle {tag}"),
                              "Statement kettle review")
    db = SessionLocal()
    try:
        r = db.get(Review, uuid.UUID(statement_review))
        author = db.get(User, r.author_id)
        split, bps = earnings.split_for_review(Decimal("1000.00"), r, author)
        db.add(Commission(
            commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=r.id, reviewer_id=author.id, reviewer_share_bps=bps, currency="PHP",
            csv_source=f"e2e-statement:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=date(1996, 11, 1), platform=Platform.shopee, cleared_at=None,
            order_status="Completed", **split))
        wallet.adjust(db, author.id, split["reviewer_share"])
        db.commit()
    finally:
        db.close()
    owner2 = user("ownertwo", stage=1)
    store2 = c.post("/api/v1/sellers", headers=owner2, json={
        "display_name": f"LampHub {tag}", "platform": "shopee"}).json()
    claim2 = c.post(f"/api/v1/sellers/{store2['id']}/claims", headers=owner2, json={
        "registration_kind": "dti", "registration_number": "DTI-5829413",
        "registered_business_name": "LampHub Trading",
        "marketplace_shop_name": store2["display_name"], "evidence": None})
    assert claim2.status_code == 201, claim2.text
    assert c.post(f"/api/v1/admin/seller-claims/{claim2.json()['id']}/decision", headers=mod,
                  json={"decision": "approve"}).status_code == 200

    # Owner decision patch 2026-09-28 (owner-patch-journeys.spec.ts): a reviewer
    # with an unpaid review, a previously-paid one and a mobile one to delete;
    # a stranger; a review for staff to take down; a third claimed store with
    # engagement to rank; and a product question for buyers and the store.
    deleter = user("deleter", stage=2)
    stranger = user("stranger", stage=1)
    unpaid = review(deleter, product(deleter, f"Patch Kettle {tag}"), "Kettle boils fast")
    paid = review(deleter, product(deleter, f"Patch Toaster {tag}"), "Toaster browns evenly")
    mobile = review(deleter, product(deleter, f"Patch Blender {tag}"), "Blender is loud")
    takedown = review(stranger, product(stranger, f"Patch Mixer {tag}"), "Mixer test content")
    db = SessionLocal()
    try:
        from app.models.enums import PayoutMethod, PayoutStatus
        from app.models.payout import Payout
        r = db.get(Review, uuid.UUID(paid))
        author = db.get(User, r.author_id)
        split, bps = earnings.split_for_review(Decimal("500.00"), r, author)
        db.add(Commission(
            commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=r.id, reviewer_id=author.id, reviewer_share_bps=bps, currency="PHP",
            csv_source=f"e2e-patch:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=date(1995, 2, 1), platform=Platform.lazada,
            cleared_at=datetime.now(UTC), order_status="Completed", **split))
        # Paid out in full: the wallet went up by the share and back down.
        db.add(Payout(payout_id=f"pay_e2e_{uuid.uuid4().hex[:8]}", user_id=author.id,
                      amount=split["reviewer_share"], method=PayoutMethod.paypal_sandbox,
                      status=PayoutStatus.paid, scheduled_for=date(1995, 3, 15),
                      created_at=datetime(1995, 3, 10, 4, 0, tzinfo=UTC),
                      paid_at=datetime(1995, 3, 15, 4, 0, tzinfo=UTC)))
        db.commit()
        paid_share = str(split["reviewer_share"])
    finally:
        db.close()
    patch_owner = user("patchowner", stage=1)
    store3 = c.post("/api/v1/sellers", headers=patch_owner, json={
        "display_name": f"DeskHub {tag}", "platform": "lazada"}).json()
    claim3 = c.post(f"/api/v1/sellers/{store3['id']}/claims", headers=patch_owner, json={
        "registration_kind": "dti", "registration_number": "DTI-3141592",
        "registered_business_name": "DeskHub Trading",
        "marketplace_shop_name": store3["display_name"], "evidence": None})
    assert claim3.status_code == 201, claim3.text
    assert c.post(f"/api/v1/admin/seller-claims/{claim3.json()['id']}/decision", headers=mod,
                  json={"decision": "approve"}).status_code == 200
    praised = c.post(f"/api/v1/sellers/{store3['id']}/reviews", headers=buyer, json={
        "accuracy": True, "order_completeness": True, "customer_service": 5,
        "packaging_quality": 4, "overall_rating": 5, "would_recommend": True,
        "comment": "Desk arrived with every screw.", "order_id": "ORD-3001"})
    assert praised.status_code == 201, praised.text
    grumble = c.post(f"/api/v1/sellers/{store3['id']}/reviews", headers=voter, json={
        "accuracy": True, "order_completeness": False, "customer_service": 3,
        "packaging_quality": 2, "overall_rating": 3, "would_recommend": False,
        "comment": "One leg was missing a bolt.", "order_id": "ORD-3002"})
    assert grumble.status_code == 201, grumble.text
    # Three helpful votes on the praise, two replies under the grumble: the
    # most engaged (3) and the most discussed (2 replies) are different reviews.
    for who in (asker, commenter, deleter):
        assert c.put(f"/api/v1/sellers/reviews/{praised.json()['id']}/vote", headers=who,
                     json={"direction": "up"}).status_code == 200
    for body in ("Same experience here.", "Did they include the manual?"):
        assert c.post(f"/api/v1/sellers/reviews/{grumble.json()['id']}/replies",
                      headers=commenter, json={"body": body}).status_code == 201
    desk_q = c.post("/api/v1/questions", headers=asker, json={
        "seller_id": store3["id"], "body": "Do you deliver to Davao?"})
    assert desk_q.status_code == 201, desk_q.text
    kettle_q = c.post("/api/v1/questions", headers=asker, json={
        "product_id": fan, "body": "Is the fan loud enough to hear across a room?"})
    assert kettle_q.status_code == 201, kettle_q.text

    # A claim waiting on an Administrator, for the admin approval journey.
    waiting = user("claimwaits", stage=1)
    waiting_store = c.post("/api/v1/sellers", headers=waiting, json={
        "display_name": f"WaitingDesk {tag}", "platform": "shopee"}).json()
    pending_claim = c.post(f"/api/v1/sellers/{waiting_store['id']}/claims", headers=waiting, json={
        "registration_kind": "dti", "registration_number": "DTI-2718281",
        "registered_business_name": "WaitingDesk Trading",
        "marketplace_shop_name": waiting_store["display_name"], "evidence": None})
    assert pending_claim.status_code == 201, pending_claim.text

    # Owner decisions A-D (admin-journeys.spec.ts): an account for the Super
    # Admin to promote, and two 2.5-star "It depends" reviews an Administrator
    # has approved, waiting on the Super Admin — one for each destination.
    user("promotee", stage=1)
    router_author = user("routeauthor", stage=2)
    routing = {}
    for key, title in (("fund", "Speaker works in quiet rooms"),
                       ("platform", "Router is fine for small flats")):
        title = f"{title} {tag}"  # unique on a cumulative test database
        rid = review(router_author, product(router_author, f"Routing {key} {tag}"), title,
                     verdict="it_depends", stars=2.5)
        db = SessionLocal()
        try:
            from app.models.enums import VerificationStatus
            # "Photo provided" without a storage round-trip: earning needs it.
            db.get(Review, uuid.UUID(rid)).verification_status = VerificationStatus.verified
            db.commit()
        finally:
            db.close()
        escalated = c.post(f"/api/v1/admin/reviews/{rid}/approve-earnings", headers=mod)
        assert escalated.status_code == 200, escalated.text
        assert escalated.json()["earn_eligible_status"] == "pending_superadmin_routing"
        routing[key] = {"id": rid, "title": title}

    # Dev/QA sync 2026-09-29 (ENG-0929-F): two reviews waiting in different
    # priority tiers, so the review queue's tier chips have something to count.
    # A Stage 0 member's first verified submission is High; a trusted Stage 3
    # author's is Low (the admin priority tiers of 2026-09-26). The proof photo
    # is one the author owns, in the shape upload_review_photo writes.
    from app.core.config import settings as _settings
    from app.services.storage import REVIEW_BUCKET

    def owned_photo(uid: str) -> str:
        base = (_settings.supabase_url or "https://test.supabase.co").rstrip("/")
        return f"{base}/storage/v1/object/public/{REVIEW_BUCKET}/{uid}/{uuid.uuid4().hex}.jpg"

    def queued(who: str, name: str) -> str:
        h = {"Authorization": f"Bearer {users[who]['token']}"}
        # Not named with the fixture tag: journeys search `q=<tag>` and sort by
        # date, and these back-dated reviews would lead every such list.
        pid = product(h, f"{name} {uuid.uuid4().hex[:6]}")
        r = c.post("/api/v1/reviews", headers=h, json={
            "product_id": pid, "title": name, "star_rating": 4, "verdict": "yes_absolutely",
            "discussion": "Two weeks of daily use; it does what the box says.",
            "photo_url": owned_photo(users[who]["id"])})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    # The 2026-09-29 meeting journeys' own people: they write, answer, report
    # and ask there, and delete what they wrote afterwards, which re-derives
    # their trust stage. Shared users would carry that into other specs.
    user("m29writer", stage=2)
    user("m29second", stage=2)
    user("m29asker", stage=1)
    # The Review Queue / Wilson / anti-farming journeys (QA 2026-09-29) and
    # nobody else. The three voters carry enough trust-weighted evidence
    # (Stage 5 x reputation 100 = weight 3.0 each, mature accounts) that three
    # up-votes pass the Post-Seeding earnings gate: 9 of 9 effective votes,
    # Wilson lower bound 0.70 >= 0.65, 3 Stage 2+ voters.
    user("rqwriter", stage=2)
    user("rqcopier", stage=1)
    for n in (1, 2, 3):
        user(f"rqvoter{n}", stage=5, age_days=400, reputation="100.00")
    # Three accounts under 30 days old for the network journey (N): voting from
    # one network, they meet the shared-network rule's "new accounts" branch.
    for n in (1, 2, 3):
        user(f"rqfresh{n}", stage=1, age_days=5)

    def ids_of(who: str) -> list[str]:
        db = SessionLocal()
        try:
            return [str(r.id) for r in db.query(Review).filter(
                Review.author_id == uuid.UUID(users[who]["id"]))]
        finally:
            db.close()

    user("tiernew", stage=0)
    user("tiertrusted", stage=3)
    tiered = [queued("tiernew", "Xiaomi Mi Band 8")]
    queued("tiertrusted", "Soundcore Q20i")
    tiered.append(queued("tiertrusted", "Soundcore Life P3"))
    db = SessionLocal()
    try:
        from app.models.enums import EarnEligibleStatus
        # Posting lifts a member to Stage 1; the tiers read the stage they have.
        db.get(User, uuid.UUID(users["tiernew"]["id"])).trust_stage = 0
        db.get(User, uuid.UUID(users["tiertrusted"]["id"])).trust_stage = 3
        # Admitted to the earnings queue, as the Post-Seeding vote gate does.
        # Dated older than every other fixture review, so the three do not push
        # anything off the first page of the Recent feed (qa-round2 QA-027/028
        # looks for the 125-day-old fan review there).
        old = datetime.now(UTC) - timedelta(days=400)
        for rid in [*tiered, *ids_of("tiertrusted")]:
            r = db.get(Review, uuid.UUID(rid))
            r.created_at = r.published_at = old
        for rid in tiered:
            db.get(Review, uuid.UUID(rid)).earn_eligible_status = EarnEligibleStatus.pending
        db.commit()
    finally:
        db.close()

    out = {
        "routing": routing,
        "remit_cycle": remit_cycle.isoformat(),
        "pending_claim": {"id": pending_claim.json()["id"], "store": waiting_store["id"],
                          "store_name": waiting_store["display_name"]},
        "patch": {
            "unpaid_review": unpaid, "paid_review": paid, "mobile_review": mobile,
            "paid_share": paid_share, "paid_cycle_year": 1995, "paid_cycle_month": 2,
            "takedown_review": takedown, "store": store3["id"],
            "store_name": store3["display_name"], "praised_review": praised.json()["id"],
            "grumble_review": grumble.json()["id"], "store_question": desk_q.json()["id"],
            "product_question": kettle_q.json()["id"],
        },
        "tag": tag,
        # Where an author's own review photo lives, for journeys that attach one.
        "photo_base": f"{(_settings.supabase_url or 'https://test.supabase.co').rstrip('/')}"
                      f"/storage/v1/object/public/{REVIEW_BUCKET}",
        "users": users,
        "products": {"fan": fan, "fresh": fresh_pid, "doomed": doomed_pid,
                     "fan_name": f"Jisulife Fanlife 9 {tag}"},
        "reviews": {"old": old_review, "fresh": fresh_review, "doomed": doomed_review},
        "question": q.json()["id"],
        "answer": a.json()["id"],
        "store": store["id"],
        "store_name": store["display_name"],
        "open_store": open_store["id"],
        "open_store_name": open_store["display_name"],
        "seller_review": seller_review.json()["id"],
        "half_star_seller_review": half.json()["id"],
        "store_question": store_q.json()["id"],
        "beauty_review": beauty_review,
        "comment": comment.json()["id"],
        "qa_review": qa_review,
        "report": {"cycle_year": 1996, "cycle_month": 6, "fund_review": fund_review,
                   "store2": store2["id"], "store2_name": store2["display_name"]},
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(f"e2e fixtures written to {out_path} (tag {tag})")


if __name__ == "__main__":
    guard_cli("e2e_fixtures", production_is_legitimate=False)
    main(sys.argv[1] if len(sys.argv) > 1 else "e2e-fixtures.json")

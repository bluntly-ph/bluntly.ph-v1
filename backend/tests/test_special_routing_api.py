"""Owner decision A (2026-09-28): "It depends" at exactly 2.5 stars.

An administrator's earnings approval escalates it; only a Super Admin routes
it, to the HONESTY FUND or the PLATFORM. Authorized, audited, idempotent, safe
under concurrent duplicate submissions — and the money follows the decision:
nothing is recognised while it waits, and a platform route keeps the
reviewer's share for the platform.
"""

from __future__ import annotations

import io
import threading
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import ModerationAction
from app.models.moderation import ModerationLog
from app.models.notification import Notification
from app.models.review import Review
from app.models.session import Session as ClickSession
from tests.conftest import owned_photo_url, register_and_token, requires_db

pytestmark = requires_db

SHOPEE_URL = "https://shopee.ph/product/abc-i.123.456"
HEADER = "click_ref,order_ref,gross_amount,currency,order_status,platform"
BASE = "/api/v1/admin/super/special-routing"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _people(client) -> dict:
    out = {}
    for key, role in (("author", "user"), ("admin", "administrator"),
                      ("super", "super_admin"), ("super2", "super_admin"),
                      ("member", "user")):
        uid, token, _ = register_and_token(client, role=role)
        out[key] = (uid, _auth(token))
    return out


def _review(client, h: dict, *, stars=2.5, verdict="it_depends") -> dict:
    pid = client.post("/api/v1/products", headers=h, json={
        "name": f"Routing {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
    created = client.post("/api/v1/reviews", headers=h, json={
        "product_id": pid, "title": "It depends on your use", "verdict": verdict,
        "discussion": "Weeks of daily use, some good and some bad.", "star_rating": stars,
        "photo_url": owned_photo_url(h)})
    assert created.status_code == 201, created.text
    return created.json()


def _escalated(client, p) -> str:
    rid = _review(client, p["author"][1])["id"]
    res = client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings", headers=p["admin"][1])
    assert res.status_code == 200 and res.json()["earn_eligible_status"] == \
        "pending_superadmin_routing", res.text
    return rid


def _route(client, h, rid, destination, confirm="route"):
    return client.post(f"{BASE}/{rid}", headers=h,
                       json={"destination": destination, "confirm": confirm})


def _audits(rid) -> list[ModerationLog]:
    with SessionLocal() as s:
        return list(s.scalars(select(ModerationLog).where(
            ModerationLog.target_ref == uuid.UUID(rid),
            ModerationLog.action == ModerationAction.special_routing)))


def test_an_administrators_approval_escalates_to_the_super_admin_queue(client):
    p = _people(client)
    rid = _escalated(client, p)
    queue = client.get(BASE, headers=p["super"][1])
    assert queue.status_code == 200
    item = next(i for i in queue.json() if i["review_id"] == rid)
    assert item["verdict"] == "it_depends" and Decimal(item["stars"]) == Decimal("2.5")
    assert item["photo_provided"] is True and item["escalated_at"]
    assert item["status"] == "pending_superadmin_routing"
    # The queue carries what the decision needs and nothing about money.
    assert not {"wallet_balance", "payout_account", "email"} & set(item)
    with SessionLocal() as s:
        escalation = s.scalar(select(ModerationLog).where(
            ModerationLog.target_ref == uuid.UUID(rid),
            ModerationLog.action == ModerationAction.escalate))
        assert escalation is not None
        assert escalation.context["routed_to"] == "pending_superadmin_routing"
    # A link waits for the Super Admin too.
    link = client.post(f"/api/v1/admin/reviews/{rid}/referral-link", headers=p["admin"][1],
                       json={"url": SHOPEE_URL, "platform": "shopee"})
    assert link.status_code == 409
    assert link.json()["code"] == "earning_track_pending_superadmin_routing"


def test_only_a_super_admin_may_route(client):
    p = _people(client)
    rid = _escalated(client, p)
    for who in ("admin", "member", "author"):
        h = p[who][1]
        assert client.get(BASE, headers=h).status_code == 403, who
        assert _route(client, h, rid, "honesty_fund").status_code == 403, who
        assert client.get(f"{BASE}/history", headers=h).status_code == 403, who
    assert client.get(BASE).status_code == 401
    assert _route(client, {}, rid, "platform").status_code == 401
    # Explicit confirmation, and exactly two destinations.
    assert _route(client, p["super"][1], rid, "honesty_fund", confirm="yes").status_code == 422
    assert _route(client, p["super"][1], rid, "commission").status_code == 422
    assert _audits(rid) == []


def test_routing_to_the_honesty_fund(client):
    p = _people(client)
    rid = _escalated(client, p)
    routed = _route(client, p["super"][1], rid, "honesty_fund")
    assert routed.status_code == 200, routed.text
    assert routed.json() | {"routed_at": None} == {
        "review_id": rid, "destination": "honesty_fund", "status": "honesty_fund",
        "routed_at": None, "changed": True}
    [audit] = _audits(rid)
    assert audit.moderator_id == uuid.UUID(p["super"][0])
    assert audit.context["destination"] == "honesty_fund"
    assert audit.context["previous_status"] == "pending_superadmin_routing"
    assert audit.context["new_status"] == "honesty_fund"
    assert audit.context["verdict"] == "it_depends" and audit.context["stars"] == "2.5"
    # Off the queue; on the fund track, where no link goes.
    assert rid not in [i["review_id"] for i in client.get(BASE, headers=p["super"][1]).json()]
    link = client.post(f"/api/v1/admin/reviews/{rid}/referral-link", headers=p["admin"][1],
                       json={"url": SHOPEE_URL, "platform": "shopee"})
    assert link.status_code == 409 and link.json()["code"] == "fund_track_no_link"
    with SessionLocal() as s:
        told = s.scalars(select(Notification.title).where(
            Notification.user_id == uuid.UUID(p["author"][0]))).all()
        assert "Your review joins the Honesty Fund" in told


def test_routing_to_the_platform_and_the_money_that_follows(client):
    p = _people(client)
    author_h, admin_h = p["author"][1], p["admin"][1]
    # A monetized thread that an update moves to 2.5 "It depends".
    root = _review(client, author_h, stars=4, verdict="yes_absolutely")
    rid = root["id"]
    assert client.post(f"/api/v1/admin/reviews/{rid}/referral-link", headers=admin_h,
                       json={"url": SHOPEE_URL, "platform": "shopee"}).status_code == 200
    assert client.get(f"/r/{rid}", follow_redirects=False).status_code == 302
    with SessionLocal() as s:
        click_ref = s.scalar(select(ClickSession.click_ref).where(
            ClickSession.review_id == uuid.UUID(rid)))
        row = s.get(Review, uuid.UUID(rid))
        row.created_at = row.published_at = datetime.now(UTC) - timedelta(days=95)
        s.commit()
    update = client.post(f"/api/v1/reviews/{rid}/updates", headers=author_h, json={
        "title": "It depends now", "discussion": "Half the features broke.",
        "verdict": "it_depends", "star_rating": 2.5, "photo_url": owned_photo_url(author_h)})
    assert update.status_code == 201, update.text
    detail = client.get(f"{BASE}", headers=p["super"][1]).json()
    assert rid in [i["review_id"] for i in detail]            # escalated by the update
    with SessionLocal() as s:
        flip = s.scalar(select(ModerationLog).where(
            ModerationLog.target_ref == uuid.UUID(rid),
            ModerationLog.action == ModerationAction.track_flip))
        assert flip.context["to"] == "pending_superadmin_routing" and flip.context["link_revoked"]

    # A sale arriving while it waits is nobody's money yet.
    csv_text = f"{HEADER}\n{click_ref},ORD-R1,100.00,PHP,completed,shopee\n"
    first = client.post("/api/v1/admin/commissions/import", headers=admin_h,
                        files={"file": ("routing.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert first.status_code == 200 and first.json()["imported"] == 0
    assert first.json()["held_pending_routing"] == [2]

    routed = _route(client, p["super"][1], rid, "platform")
    assert routed.status_code == 200 and routed.json()["status"] == "approved"
    with SessionLocal() as s:
        told = s.scalars(select(Notification.title).where(
            Notification.user_id == uuid.UUID(p["author"][0]))).all()
        assert "Your review's earnings go to the platform" in told

    # The same file again: recognised exactly once, with the reviewer's 30%
    # kept by the platform and the fund's 30% untouched.
    again = client.post("/api/v1/admin/commissions/import", headers=admin_h,
                        files={"file": ("routing.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert again.json()["imported"] == 1 and again.json()["held_pending_routing"] == []
    with SessionLocal() as s:
        c = s.scalar(select(Commission).where(Commission.review_id == uuid.UUID(rid)))
        assert (c.gross_amount, c.platform_share, c.reviewer_share, c.honesty_fund_share) == (
            Decimal("100.00"), Decimal("70.00"), Decimal("0.00"), Decimal("30.00"))
        assert c.reviewer_share_bps == 0

    # An administrator may put the official link back on a platform route.
    relink = client.post(f"/api/v1/admin/reviews/{rid}/referral-link", headers=admin_h,
                         json={"url": SHOPEE_URL, "platform": "shopee"})
    assert relink.status_code == 200 and relink.json()["earn_eligible_status"] == "monetized"


def test_the_decision_is_idempotent_and_final(client):
    p = _people(client)
    rid = _escalated(client, p)
    assert _route(client, p["super"][1], rid, "platform").json()["changed"] is True
    same = _route(client, p["super2"][1], rid, "platform")
    assert same.status_code == 200 and same.json()["changed"] is False
    other = _route(client, p["super2"][1], rid, "honesty_fund")
    assert other.status_code == 409 and other.json()["code"] == "already_routed"
    assert len(_audits(rid)) == 1


def test_what_cannot_be_routed(client):
    p = _people(client)
    plain = _review(client, p["author"][1], stars=4, verdict="yes_absolutely")["id"]
    refused = _route(client, p["super"][1], plain, "honesty_fund")
    assert refused.status_code == 409 and refused.json()["code"] == "not_pending_routing"
    assert _route(client, p["super"][1], str(uuid.uuid4()), "platform").status_code == 404


def test_concurrent_duplicate_submissions_decide_once(client):
    p = _people(client)
    rid = _escalated(client, p)
    barrier = threading.Barrier(2)
    results: list[tuple[int, dict]] = []

    def submit(h, destination):
        barrier.wait()
        res = _route(client, h, rid, destination)
        results.append((res.status_code, res.json()))

    threads = [threading.Thread(target=submit, args=(p["super"][1], "honesty_fund")),
               threading.Thread(target=submit, args=(p["super2"][1], "platform"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    codes = sorted(code for code, _ in results)
    assert codes == [200, 409], results
    assert [b["code"] for c, b in results if c == 409] == ["already_routed"]
    assert len(_audits(rid)) == 1


def test_history_lists_the_decisions(client):
    p = _people(client)
    fund, platform = _escalated(client, p), _escalated(client, p)
    _route(client, p["super"][1], fund, "honesty_fund")
    _route(client, p["super2"][1], platform, "platform")
    history = client.get(f"{BASE}/history?limit=200", headers=p["super"][1]).json()
    mine = {h["review_id"]: h["destination"] for h in history
            if h["review_id"] in (fund, platform)}
    assert mine == {fund: "honesty_fund", platform: "platform"}


def test_moving_off_two_and_a_half_clears_the_route(client):
    p = _people(client)
    author_h = p["author"][1]
    rid = _escalated(client, p)
    _route(client, p["super"][1], rid, "platform")
    with SessionLocal() as s:
        row = s.get(Review, uuid.UUID(rid))
        row.created_at = row.published_at = datetime.now(UTC) - timedelta(days=95)
        s.commit()
    update = client.post(f"/api/v1/reviews/{rid}/updates", headers=author_h, json={
        "title": "Fixed by the firmware", "discussion": "Works as promised now.",
        "verdict": "yes_absolutely", "star_rating": 4, "photo_url": owned_photo_url(author_h)})
    assert update.status_code == 201, update.text
    with SessionLocal() as s:
        row = s.get(Review, uuid.UUID(rid))
        assert row.special_route is None and row.special_routed_by_id is None
        assert row.earn_eligible_status.value == "approved"
        flip = s.scalars(select(ModerationLog).where(
            ModerationLog.target_ref == uuid.UUID(rid),
            ModerationLog.action == ModerationAction.track_flip)).all()[-1]
        assert flip.context["special_route_cleared"] == "platform"


def test_the_queue_and_history_carry_what_the_frame_draws(client):
    """Figma Screen/Admin/SpecialRouting 8178:20045 + Overlay/Routing/Track 8178:20344:
    the author's name, the entry's opening words, the product picture field, the
    note for the log, and who routed it."""
    p = _people(client)
    rid = _escalated(client, p)
    item = next(i for i in client.get(BASE, headers=p["super"][1]).json() if i["review_id"] == rid)
    assert item["excerpt"] == "Weeks of daily use, some good and some bad."
    assert item["author_name"]
    assert "product_image_url" in item and "approval_note" in item

    assert client.post(f"{BASE}/{rid}", headers=p["super"][1], json={
        "destination": "honesty_fund", "confirm": "route",
        "note": "Mixed verdict, low clicks."}).status_code == 200
    (audit,) = _audits(rid)
    assert audit.notes.endswith("· Mixed verdict, low clicks.")
    long = client.post(f"{BASE}/{_escalated(client, p)}", headers=p["super"][1], json={
        "destination": "platform", "confirm": "route", "note": "x" * 501})
    assert long.status_code == 422
    history = client.get(f"{BASE}/history?limit=200", headers=p["super"][1]).json()
    mine = next(h for h in history if h["review_id"] == rid)
    assert mine["actor_name"]

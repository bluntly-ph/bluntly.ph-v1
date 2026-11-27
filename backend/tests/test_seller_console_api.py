"""The Seller console's API (Figma Screen/Seller/*, 2026-10-03).

Claims the caller filed (store switcher, Claim status, Withdraw claim), the
store's appeals, and the Overview's derived figures — each the caller's own,
and never a way into another store.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from tests.conftest import all_pages, claim_body, register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _new_store(client, owner: dict) -> str:
    return client.post("/api/v1/sellers", headers=owner, json={
        "display_name": f"Console Store {uuid.uuid4().hex[:8]}", "platform": "lazada"}).json()["id"]


def _claimed_store(client) -> tuple[str, dict, dict]:
    _, owner, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = _new_store(client, _auth(owner))
    claim = client.post(f"/api/v1/sellers/{store}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                       headers=_auth(mod), json={"decision": "approve"}).status_code == 200
    return store, _auth(owner), _auth(mod)


def _rate(client, store_id, overall=4.0) -> str:
    _, buyer, _ = register_and_token(client)
    r = client.post(f"/api/v1/sellers/{store_id}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": False, "customer_service": 5,
        "packaging_quality": 3, "overall_rating": overall, "would_recommend": True,
        "comment": "Arrived on time. " + "Words " * 10})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_my_claims_lists_only_mine_and_withdraw_ends_a_pending_one(client):
    _, me, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = _new_store(client, _auth(me))
    mine = client.post(f"/api/v1/sellers/{store}/claims", headers=_auth(me),
                       json=claim_body("Mine.")).json()
    # Another member's claim, on another store: a store under review takes no
    # second claim (MQA-012, test_claim_under_review).
    theirs = client.post(f"/api/v1/sellers/{_new_store(client, _auth(other))}/claims",
                         headers=_auth(other), json=claim_body("Theirs.")).json()

    listed = client.get("/api/v1/sellers/claims/mine", headers=_auth(me)).json()
    assert [c["id"] for c in listed] == [mine["id"]]
    assert listed[0]["status"] == "pending" and listed[0]["seller_platform"] == "lazada"
    assert listed[0]["registration_number"]

    # Someone else's claim is not found, never forbidden (no enumeration).
    assert client.post(f"/api/v1/sellers/claims/{theirs['id']}/withdraw",
                       headers=_auth(me)).status_code == 404
    done = client.post(f"/api/v1/sellers/claims/{mine['id']}/withdraw", headers=_auth(me))
    assert done.status_code == 200 and done.json()["status"] == "withdrawn"
    assert done.json()["decided_at"]
    # Withdrawn: out of the administrators' queue, cannot be decided or withdrawn again.
    pending = all_pages(client, "/api/v1/admin/seller-claims", _auth(mod))
    assert mine["id"] not in {c["id"] for c in pending}
    assert theirs["id"] in {c["id"] for c in pending}
    assert client.post(f"/api/v1/admin/seller-claims/{mine['id']}/decision", headers=_auth(mod),
                       json={"decision": "approve"}).status_code == 409
    assert client.post(f"/api/v1/sellers/claims/{mine['id']}/withdraw",
                       headers=_auth(me)).status_code == 409
    # ...and the store can be claimed again later.
    again = client.post(f"/api/v1/sellers/{store}/claims", headers=_auth(me),
                        json=claim_body("Mine, again."))
    assert again.status_code == 201, again.text


def test_signed_out_callers_get_nothing(client):
    assert client.get("/api/v1/sellers/claims/mine").status_code == 401
    assert client.post(f"/api/v1/sellers/claims/{uuid.uuid4()}/withdraw").status_code == 401


def test_store_appeals_are_the_owners_and_hide_the_reviewers_proof(client):
    store, owner, mod = _claimed_store(client)
    rid = _rate(client, store, 1.5)
    appeal = client.post(f"/api/v1/sellers/reviews/{rid}/appeal", headers=owner,
                         json={"reason": "This order number was never ours."}).json()
    rows = client.get(f"/api/v1/sellers/{store}/appeals", headers=owner).json()
    assert [a["id"] for a in rows] == [appeal["id"]]
    assert rows[0]["review_rating"] == 1.5 and rows[0]["status"] == "open"
    assert rows[0]["substantiation_response"] is None and rows[0]["order_id"] is None
    # Another store's owner, a member and an administrator's own path: refused.
    _, other_store_owner, _ = _claimed_store(client)
    assert client.get(f"/api/v1/sellers/{store}/appeals",
                      headers=other_store_owner).status_code == 403
    _, member, _ = register_and_token(client)
    assert client.get(f"/api/v1/sellers/{store}/appeals", headers=_auth(member)).status_code == 403


def test_overview_figures_period_and_reply_time(client):
    from app.db.session import SessionLocal
    from app.models.seller import SellerReview

    store, owner, _ = _claimed_store(client)
    old = _rate(client, store, 2.0)
    new = _rate(client, store, 5.0)
    with SessionLocal() as db:  # the old review is from four months ago
        db.execute(update(SellerReview).where(SellerReview.id == old).values(
            created_at=datetime.now(UTC) - timedelta(days=120)))
        db.commit()
    assert client.post(f"/api/v1/sellers/reviews/{new}/response", headers=owner,
                       json={"body": "Thank you!"}).status_code == 200
    _, asker, _ = register_and_token(client)
    client.post("/api/v1/questions", headers=_auth(asker),
                json={"seller_id": store, "body": "Do you ship to Cebu?"})

    six = client.get(f"/api/v1/sellers/{store}/dashboard", headers=owner).json()
    assert six["period"] == "6m" and six["period_summary"]["review_count"] == 2
    month = client.get(f"/api/v1/sellers/{store}/dashboard", headers=owner,
                       params={"period": "30d"}).json()
    assert month["period_summary"]["review_count"] == 1
    assert month["period_summary"]["overall_average"] == 5.0
    a = six["analytics"]
    assert a["reviews_awaiting_response"] == 1
    assert a["median_reply_hours"] is not None and a["platform_median_reply_hours"] is not None
    row = next(r for r in six["reviews"] if r["id"] == new)
    assert row["reviewer_name"] == "Tester" and row["reviewer_trust_stage"] is not None
    assert six["waiting_questions"][0]["asker"] == "Tester"
    bad = client.get(f"/api/v1/sellers/{store}/dashboard", headers=owner, params={"period": "1d"})
    assert bad.status_code == 422


def test_store_questions_for_the_owner_with_the_stores_answer(client):
    store, owner, _ = _claimed_store(client)
    _, asker, _ = register_and_token(client)
    q1 = client.post("/api/v1/questions", headers=_auth(asker),
                     json={"seller_id": store, "body": "Do you ship to Cebu?"}).json()
    q2 = client.post("/api/v1/questions", headers=_auth(asker),
                     json={"seller_id": store, "body": "Is COD available?"}).json()
    assert client.post(f"/api/v1/questions/{q1['id']}/answers", headers=owner,
                       json={"body": "Yes, every weekday."}).status_code == 201

    every = client.get(f"/api/v1/sellers/{store}/questions", headers=owner).json()
    assert [q["id"] for q in every] == [q2["id"], q1["id"]]
    answered = next(q for q in every if q["id"] == q1["id"])
    assert answered["store_answer"]["body"].startswith("Yes, every weekday.")
    assert answered["answer_count"] == 1 and answered["asker"]["display_name"] == "Tester"
    # Figma's "Community answers" leaves the store's own out; "Following" counts followers.
    assert answered["community_answers"] == 0
    _, buyer, _ = register_and_token(client)
    assert client.post(f"/api/v1/questions/{q1['id']}/answers", headers=_auth(buyer),
                       json={"body": "Mine came to Cebu in three days."}).status_code == 201
    assert client.put(f"/api/v1/questions/{q1['id']}/subscription", headers=_auth(buyer),
                      json={"subscribed": True}).status_code == 200
    again = next(q for q in client.get(f"/api/v1/sellers/{store}/questions",
                                       headers=owner).json() if q["id"] == q1["id"])
    assert again["answer_count"] == 2 and again["community_answers"] == 1
    assert again["followers"] == 1
    # The asker following their own question is not counted: they are told anyway.
    assert client.put(f"/api/v1/questions/{q1['id']}/subscription", headers=_auth(asker),
                      json={"subscribed": True}).status_code == 200
    rows = client.get(f"/api/v1/sellers/{store}/questions", headers=owner).json()
    assert next(q for q in rows if q["id"] == q1["id"])["followers"] == 1
    needs = client.get(f"/api/v1/sellers/{store}/questions", headers=owner,
                       params={"status": "needs"}).json()
    assert [q["id"] for q in needs] == [q2["id"]]
    done = client.get(f"/api/v1/sellers/{store}/questions", headers=owner,
                      params={"status": "answered"}).json()
    assert [q["id"] for q in done] == [q1["id"]]
    # Not the store's owner: refused.
    assert client.get(f"/api/v1/sellers/{store}/questions",
                      headers=_auth(asker)).status_code == 403
    assert client.get(f"/api/v1/sellers/{store}/questions").status_code == 401


def test_the_owner_is_notified_of_a_new_store_review_and_question(client):
    store, owner, _ = _claimed_store(client)
    _rate(client, store, 2.0)
    _, asker, _ = register_and_token(client)
    client.post("/api/v1/questions", headers=_auth(asker),
                json={"seller_id": store, "body": "Is there a warranty in the Philippines?"})
    rows = client.get("/api/v1/notifications", headers=owner).json()
    by_kind = {n["kind"]: n for n in rows}
    assert by_kind["store_review_new"]["title"] == "New 2★ review"
    assert by_kind["store_review_new"]["link"] == f"/seller/{store}/reviews"
    assert by_kind["store_question_new"]["title"] == "New question"
    assert "warranty" in by_kind["store_question_new"]["body"]
    assert by_kind["store_question_new"]["link"] == f"/seller/{store}/questions"
    # An unclaimed store notifies nobody; the buyer gets nothing for their own posts.
    _, buyer, _ = register_and_token(client)
    open_store = _new_store(client, _auth(buyer))
    _, other, _ = register_and_token(client)
    client.post("/api/v1/questions", headers=_auth(other),
                json={"seller_id": open_store, "body": "Anyone home?"})
    assert not [n for n in client.get("/api/v1/notifications", headers=_auth(buyer)).json()
                if n["kind"].startswith("store_")]


def test_notifications_filter_by_kind_and_appeal_decisions_notify_the_owner(client):
    """Overlay/Store/Notifications tabs read GET /notifications?kind=… on the
    server, and a decided appeal reaches its owner (the Appeals tab)."""
    import uuid

    from app.db.session import SessionLocal
    from app.models.notification import Notification

    uid, token, _ = register_and_token(client)
    db = SessionLocal()
    try:
        for kind in ("store_review_new", "store_question_new", "case_message",
                     "seller_appeal_decided", "seller_claim_approved"):
            db.add(Notification(user_id=uuid.UUID(uid), kind=kind, title=kind))
        db.commit()
    finally:
        db.close()
    h = {"Authorization": f"Bearer {token}"}
    every = client.get("/api/v1/notifications", headers=h).json()
    assert len(every) == 5
    kinds = [("kind", "case_message"), ("kind", "seller_appeal_decided")]
    appeals = client.get("/api/v1/notifications", headers=h, params=kinds).json()
    assert sorted(n["kind"] for n in appeals) == ["case_message", "seller_appeal_decided"]

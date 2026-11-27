"""Chat on a seller claim (meeting 2026-10-02, 11:40): the claimant and staff
talk on the case; nobody else can read or write it."""

from __future__ import annotations

import uuid

from tests.conftest import all_pages, claim_body, register_and_token, requires_db
from tests.test_business_rules_api import _auth

pytestmark = requires_db


def _appeals(client, mod, **params) -> list[dict]:
    return all_pages(client, "/api/v1/admin/seller-review-appeals", mod, **params)


def test_claim_chat_is_the_claimant_and_staff_only(client):
    claimant_id, claimant, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, stranger, _ = register_and_token(client)
    store = client.post("/api/v1/sellers", headers=_auth(claimant), json={
        "display_name": f"Chat Store {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(claimant),
                        json=claim_body(shop_name=store["display_name"])).json()
    url = f"/api/v1/cases/claim/{claim['id']}/messages"

    assert client.get(url, headers=_auth(claimant)).json() == []
    asked = client.post(url, headers=_auth(admin), json={"body": "Can you send the DTI page?"})
    assert asked.status_code == 201 and asked.json()["from_staff"] is True
    replied = client.post(url, headers=_auth(claimant), json={"body": "Attached to my claim."})
    assert replied.status_code == 201 and replied.json()["from_staff"] is False
    thread = client.get(url, headers=_auth(admin)).json()
    assert [m["body"] for m in thread] == ["Can you send the DTI page?", "Attached to my claim."]

    notes = client.get("/api/v1/notifications", headers=_auth(claimant)).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n.get("kind") == "case_message" for n in items)

    assert client.get(url, headers=_auth(stranger)).status_code == 403
    assert client.post(url, headers=_auth(stranger), json={"body": "hi"}).status_code == 403
    assert client.get(url).status_code == 401
    assert client.post(url, headers=_auth(admin), json={"body": "   "}).status_code == 422
    missing = f"/api/v1/cases/appeal/{uuid.uuid4()}/messages"
    assert client.get(missing, headers=_auth(admin)).status_code == 404
    assert client.get(f"/api/v1/cases/order/{claim['id']}/messages",
                      headers=_auth(admin)).status_code == 422


def _appeal(client):
    from tests.test_business_rules_api import _claimed_seller
    _, seller, store, mod = _claimed_seller(client)
    _, buyer, _ = register_and_token(client)
    rated = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(buyer), json={
        "accuracy": True, "order_completeness": True, "customer_service": 1,
        "packaging_quality": 1, "overall_rating": 1, "would_recommend": False,
        "comment": "Cracked lid, ignored for a week.", "order_id": "ORD-240915"}).json()
    appeal = client.post(f"/api/v1/sellers/reviews/{rated['id']}/appeal", headers=_auth(seller),
                         json={"reason": "No order under this name."}).json()
    return appeal, store, _auth(seller), _auth(buyer), _auth(mod)


@requires_db
def test_reviewer_thread_asks_and_answers_and_unlocks_removal(client):
    """Overlay/Seller/Appeal (7996:11826): the reviewer thread is the request to
    back the review up; removal stays locked until the reviewer was asked."""
    appeal, store, seller, buyer, mod = _appeal(client)
    aid = appeal["id"]
    listed = next(a for a in _appeals(client, mod) if a["id"] == aid)
    assert listed["seller_name"] == store["display_name"] and listed["review_rating"] == 1.0
    assert listed["reviewer"] and listed["order_id"] == "ORD-240915"
    assert listed["substantiation_requested_at"] is None            # "Not asked"

    decide = f"/api/v1/admin/seller-review-appeals/{aid}/decision"
    locked = client.post(decide, headers=mod, json={"decision": "uphold"})
    assert locked.status_code == 422 and locked.json()["code"] == "reviewer_not_asked"

    thread = f"/api/v1/cases/appeal-reviewer/{aid}/messages"
    assert client.get(thread, headers=seller).status_code == 403    # the store can't read it
    assert client.post(thread, headers=mod, json={"body": "Can you share the order?"}
                       ).status_code == 201
    asked = next(a for a in _appeals(client, mod) if a["id"] == aid)
    assert asked["status"] == "substantiation_requested"             # "Waiting"
    assert client.post(thread, headers=buyer, json={"body": "Order ORD-240915, 15 Sept."}
                       ).status_code == 201
    answered = next(a for a in _appeals(client, mod) if a["id"] == aid)
    assert answered["substantiation_response"] == "Order ORD-240915, 15 Sept."  # "Answered"
    assert [m["from_staff"] for m in client.get(thread, headers=buyer).json()] == [True, False]
    assert client.post(decide, headers=mod, json={"decision": "uphold"}).status_code == 200
    # The store's owner hears the outcome (Notifications → Appeals).
    outcome = client.get("/api/v1/notifications", headers=seller,
                         params={"kind": "seller_appeal_decided"}).json()
    assert len(outcome) == 1 and "upheld" in outcome[0]["title"]
    assert outcome[0]["link"] == f"/seller/{store['id']}/appeals?tab=decided"


@requires_db
def test_claims_list_carries_the_claimant_and_store(client):
    _, claimant, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(claimant), json={
        "display_name": f"Claim Shop {uuid.uuid4().hex[:6]}", "platform": "lazada"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(claimant),
                        json=claim_body(shop_name=store["display_name"])).json()
    claims = all_pages(client, "/api/v1/admin/seller-claims", _auth(admin))
    row = next(c for c in claims if c["id"] == claim["id"])
    assert row["claimant"]["id"] and row["seller_platform"] == "lazada"
    assert row["shop_name_matches"] is True


@requires_db
def test_decided_appeals_are_listed_on_request(client):
    """Menu/Sellers/Appeals/Filter (8288:29871): Upheld and Dismissed are a separate read."""
    appeal, _store, _seller, buyer, mod = _appeal(client)
    aid = appeal["id"]
    client.post(f"/api/v1/cases/appeal-reviewer/{aid}/messages", headers=mod,
                json={"body": "Can you share the order?"})
    client.post(f"/api/v1/cases/appeal-reviewer/{aid}/messages", headers=buyer,
                json={"body": "Order ORD-240915."})
    assert client.post(f"/api/v1/admin/seller-review-appeals/{aid}/decision", headers=mod,
                       json={"decision": "dismiss"}).status_code == 200
    open_ids = {a["id"] for a in _appeals(client, mod)}
    decided = _appeals(client, mod, decided="true")
    assert aid not in open_ids
    assert next(a for a in decided if a["id"] == aid)["status"] == "dismissed"


@requires_db
def test_another_store_owner_cannot_read_or_write_a_stores_case(client, monkeypatch):
    """Seller A's appeal thread, its reviewer thread, its Inbox conversation and
    its files are closed to Seller B, another approved store owner (RBAC audit
    2026-10-04): owning *a* store gives no reach into another store's cases."""
    from app.services import storage
    from tests.test_business_rules_api import _claimed_seller

    monkeypatch.setattr(storage, "upload_attachment",
                        lambda conversation_id, data: (f"{conversation_id}/order.png", "image/png"))
    monkeypatch.setattr(storage, "signed_attachment_url",
                        lambda key, expires_in=300, download=None: f"https://signed.example/{key}")
    appeal, _, seller_a, _, mod = _appeal(client)
    _, seller_b_token, _, _ = _claimed_seller(client)
    seller_b = _auth(seller_b_token)
    case = f"/api/v1/cases/appeal/{appeal['id']}/messages"
    reviewer_case = f"/api/v1/cases/appeal-reviewer/{appeal['id']}/messages"

    assert client.post(case, headers=mod, json={"body": "Which order do you mean?"}
                       ).status_code == 201
    conv = next(c for c in client.get("/api/v1/conversations", headers=seller_a).json()["items"]
                if c["topic"] == "appeal")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    sent = client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=seller_a,
                       data={"body": "The order list."},
                       files={"file": ("orders.png", png, "image/png")})
    assert sent.status_code == 201, sent.text
    href = client.get(case, headers=mod).json()[-1]["attachment"]["href"]

    # Seller A, the appellant, reads its own case and file.
    assert client.get(case, headers=seller_a).status_code == 200
    assert client.get(href, headers=seller_a).status_code == 200

    # Seller B: nothing, on any route to it.
    assert client.get(case, headers=seller_b).status_code == 403
    assert client.post(case, headers=seller_b, json={"body": "hi"}).status_code == 403
    assert client.get(reviewer_case, headers=seller_b).status_code == 403
    assert client.post(reviewer_case, headers=seller_b, json={"body": "hi"}).status_code == 403
    assert client.get(href, headers=seller_b).status_code == 404
    assert client.get(f"/api/v1/conversations/{conv['id']}", headers=seller_b
                      ).status_code in (403, 404)
    assert client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=seller_b,
                       data={"body": "hi"}).status_code in (403, 404)
    assert all(c["id"] != conv["id"] for c in
               client.get("/api/v1/conversations", headers=seller_b).json()["items"])
    # The store can't read the reviewer's side either (the buyer's proof).
    assert client.get(reviewer_case, headers=seller_a).status_code == 403


@requires_db
def test_the_store_sees_where_its_appeal_stands_not_the_reviewer_thread(client):
    """Seller reports audit (2026-10-04): the store's Appeals list carries the
    dates (asked, answered) but not the admin's request to the reviewer, the
    reviewer's proof or the order id: all from a thread the store can't open."""
    appeal, store, seller, buyer, mod = _appeal(client)
    thread = f"/api/v1/cases/appeal-reviewer/{appeal['id']}/messages"
    assert client.post(thread, headers=mod, json={"body": "Please share your order page."}
                       ).status_code == 201
    assert client.post(thread, headers=buyer, json={"body": "Order ORD-240915, receipt here."}
                       ).status_code == 201
    mine = next(a for a in client.get(f"/api/v1/sellers/{store['id']}/appeals",
                                      headers=seller).json() if a["id"] == appeal["id"])
    assert mine["substantiation_requested_at"] and mine["substantiated_at"]
    assert mine["substantiation_request"] is None
    assert mine["substantiation_response"] is None
    assert mine["order_id"] is None
    text = str(mine)
    assert "order page" not in text and "receipt here" not in text
    # Staff still see all of it.
    staff = next(a for a in _appeals(client, mod) if a["id"] == appeal["id"])
    assert staff["substantiation_request"] == "Please share your order page."

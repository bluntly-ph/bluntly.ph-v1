"""Store change requests (MQA-017/018/019/020/025).

A claimed store's owner asks for several changes at once (MQA-017); they land
in ONE conversation (MQA-018) as one row per change with the value the store
had and the value asked for; a moderator's Approve applies the change to the
store, audits old -> new and tells the owner in the thread (MQA-019/025). A
store link must be on the store's own marketplace (MQA-020), and a claim on a
store whose link is on another marketplace is not approved until it is fixed.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from tests.conftest import all_pages, claim_body, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _claimed_store(client, platform: str = "shopee", store_url: str | None = None):
    """(owner headers, staff headers, store id) for a store its owner has claimed."""
    _, owner, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    body = {"display_name": f"Change Co {uuid.uuid4().hex[:8]}", "platform": platform}
    if store_url:
        body["store_url"] = store_url
    store = client.post("/api/v1/sellers", headers=_auth(owner), json=body).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body(shop_name=store["display_name"])).json()
    decided = client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                          headers=_auth(staff), json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    return _auth(owner), _auth(staff), store["id"], store["display_name"]


def _ask(client, headers, store_id, changes, note=""):
    return client.post(f"/api/v1/sellers/{store_id}/change-requests", headers=headers,
                       data={"changes": json.dumps(changes), "note": note})


@requires_db
def test_several_changes_are_one_request_in_one_thread(client):
    owner, staff, store_id, name = _claimed_store(client)
    res = _ask(client, owner, store_id, [
        {"field": "display_name", "value": f"{name} Official"},
        {"field": "store_url", "value": "https://shopee.ph/changeco.official"}],
        note="We rebranded last week.")
    assert res.status_code == 201, res.text
    body = res.json()
    conv = body["conversation_id"]
    assert [r["field"] for r in body["requests"]] == ["display_name", "store_url"]
    assert body["requests"][0]["current_value"] == name
    assert all(r["status"] == "pending" for r in body["requests"])

    # One thread, titled by what is asked; the owner's own words, no prefix.
    thread = client.get(f"/api/v1/admin/inbox/{conv}", headers=staff).json()
    assert thread["subject"] == "Store name and store link change"
    first = next(m for m in thread["messages"] if m["kind"] == "message")
    assert "Store link: https://shopee.ph/changeco.official" in first["body"]
    assert first["body"].endswith("We rebranded last week.")
    changes = client.get(f"/api/v1/admin/inbox/{conv}/changes", headers=staff).json()
    assert len(changes) == 2 and {c["label"] for c in changes} == {"Store name", "Store link"}


@requires_db
def test_approving_applies_it_to_the_store_and_tells_the_owner(client):
    owner, staff, store_id, name = _claimed_store(client)
    res = _ask(client, owner, store_id,
               [{"field": "store_url", "value": "https://shopee.ph/changeco.new"}])
    row = res.json()["requests"][0]
    conv = res.json()["conversation_id"]

    done = client.post(f"/api/v1/admin/store-changes/{row['id']}/decision", headers=staff,
                       json={"decision": "approve"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "approved"
    assert client.get(f"/api/v1/sellers/{store_id}").json()["store_url"] == \
        "https://shopee.ph/changeco.new"

    mine = client.get(f"/api/v1/sellers/{store_id}/change-requests", headers=owner).json()
    assert mine[0]["status"] == "approved"
    thread = client.get(f"/api/v1/conversations/{conv}", headers=owner).json()
    assert any("Store link change approved" in m["body"] for m in thread["messages"]
               if m["from_staff"])
    assert client.post(f"/api/v1/admin/store-changes/{row['id']}/decision", headers=staff,
                       json={"decision": "reject", "note": "x"}).status_code == 409

    from app.db.session import SessionLocal
    with SessionLocal() as db:
        audit = db.execute(text(
            "SELECT context FROM moderation_logs WHERE context->>'store_change_id' = :r"),
            {"r": row["id"]}).scalar()
    assert audit["old"] is None and audit["new"] == "https://shopee.ph/changeco.new"
    assert audit["outcome"] == "store_change_approved"


@requires_db
def test_a_rejection_needs_a_reason_and_changes_nothing(client):
    owner, staff, store_id, name = _claimed_store(client)
    row = _ask(client, owner, store_id,
               [{"field": "display_name", "value": "Totally Different"}]).json()["requests"][0]
    url = f"/api/v1/admin/store-changes/{row['id']}/decision"
    assert client.post(url, headers=staff, json={"decision": "reject"}).status_code == 422
    res = client.post(url, headers=staff, json={
        "decision": "reject", "note": "The marketplace still shows the old name."})
    assert res.status_code == 200 and res.json()["status"] == "rejected"
    assert client.get(f"/api/v1/sellers/{store_id}").json()["display_name"] == name


@requires_db
def test_a_link_on_another_marketplace_is_refused(client):
    """MQA-020: a Shopee store's link is a Shopee page."""
    owner, _, store_id, _ = _claimed_store(client)
    res = _ask(client, owner, store_id,
               [{"field": "store_url", "value": "https://www.lazada.com.ph/shop/ayala-malls/"}])
    assert res.status_code == 422
    assert res.json()["code"] == "store_link_mismatch"
    assert "Lazada page" in res.json()["detail"] and "Shopee" in res.json()["detail"]
    # ...and when a store is first added.
    _, member, _ = register_and_token(client)
    made = client.post("/api/v1/sellers", headers=_auth(member), json={
        "display_name": f"Wrong Link {uuid.uuid4().hex[:6]}", "platform": "shopee",
        "store_url": "https://www.lazada.com.ph/shop/x/"})
    assert made.status_code == 422


@requires_db
def test_a_claim_on_a_store_with_a_link_on_another_marketplace_waits_for_a_fix(client):
    """The production case: jisulife is a Shopee store whose link is on Lazada."""
    _, owner, _ = register_and_token(client)
    _, staff, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(owner), json={
        "display_name": f"Mismatch {uuid.uuid4().hex[:6]}", "platform": "shopee"}).json()
    from app.db.session import SessionLocal
    with SessionLocal() as db:      # written as it was on production, before this rule
        db.execute(text("UPDATE sellers SET store_url = :u WHERE id = :s"),
                   {"u": "https://www.lazada.com.ph/shop/ayala-malls/", "s": store["id"]})
        db.commit()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body(shop_name=store["display_name"])).json()
    listed = all_pages(client, "/api/v1/admin/seller-claims", _auth(staff))
    row = next(c for c in listed if c["id"] == claim["id"])
    assert "Lazada page" in row["link_problem"]
    approve = client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                          headers=_auth(staff), json={"decision": "approve"})
    assert approve.status_code == 409 and approve.json()["code"] == "store_link_mismatch"

    fixed = client.post(f"/api/v1/admin/sellers/{store['id']}/details", headers=_auth(staff),
                        json={"field": "store_url", "value": "https://shopee.ph/mismatch.shop",
                              "note": "The claimant's listing is on Shopee."})
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["status"] == "approved"
    approve = client.post(f"/api/v1/admin/seller-claims/{claim['id']}/decision",
                          headers=_auth(staff), json={"decision": "approve"})
    assert approve.status_code == 200, approve.text


@requires_db
def test_only_the_owner_asks_and_only_staff_decide(client):
    owner, staff, store_id, _ = _claimed_store(client)
    _, other, _ = register_and_token(client)
    change = [{"field": "display_name", "value": "Someone Else's Store"}]
    assert _ask(client, _auth(other), store_id, change).status_code == 403
    row = _ask(client, owner, store_id, change).json()["requests"][0]
    url = f"/api/v1/admin/store-changes/{row['id']}/decision"
    assert client.post(url, headers=owner, json={"decision": "approve"}).status_code == 403
    assert client.get(f"/api/v1/sellers/{store_id}/change-requests",
                      headers=_auth(other)).status_code == 403
    assert client.post(f"/api/v1/admin/sellers/{store_id}/details", headers=owner,
                       json={"field": "display_name", "value": "Mine Now"}).status_code == 403


@requires_db
def test_one_open_request_per_field_and_values_are_checked(client):
    owner, _, store_id, name = _claimed_store(client)
    assert _ask(client, owner, store_id,
                [{"field": "display_name", "value": f"{name} PH"}]).status_code == 201
    again = _ask(client, owner, store_id, [{"field": "display_name", "value": f"{name} Two"}])
    assert again.status_code == 409 and again.json()["code"] == "change_pending"
    for bad in ([], [{"field": "platform", "value": "lazada"}],
                [{"field": "store_url", "value": "javascript:alert(1)"}],
                [{"field": "registration", "value": "1234567", "kind": "dti"}],
                [{"field": "store_url", "value": "https://shopee.ph/a"},
                 {"field": "store_url", "value": "https://shopee.ph/b"}]):
        res = _ask(client, owner, store_id, bad)
        assert res.status_code == 422, (bad, res.text)
    reg = _ask(client, owner, store_id, [{"field": "registration", "value": "3318207",
                                          "kind": "dti"}])
    assert reg.status_code == 201, reg.text
    assert reg.json()["requests"][0]["requested_value"] == "DTI 3318207"

"""The finalized Business Rules (Full Record, 2026-09-23), end to end against Postgres.

One scenario per settled rule a person could break by using the API. The pure
halves of each rule are in test_business_rules_unit.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tests.conftest import (
    all_pages,
    claim_body,
    make_established,
    owned_photo_url,
    register_and_token,
    register_commenter,
    requires_db,
    set_trust_stage,
)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers, name: str = "RulesWidget") -> str:
    resp = client.post("/api/v1/products", headers=headers,
                       json={"name": f"{name} {uuid.uuid4().hex[:8]}", "category": "electronics"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _entry(headers, *, verdict="yes_absolutely", stars=4, title="Solid", photo=True) -> dict:
    body = {"title": title, "discussion": "Weeks of daily use.", "verdict": verdict,
            "star_rating": stars}
    if photo:
        body["photo_url"] = owned_photo_url(headers)
    return body


def _review(client, headers, product_id, **kw) -> dict:
    resp = client.post("/api/v1/reviews", headers=headers,
                       json={"product_id": product_id, **_entry(headers, **kw)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _backdate(review_id: str, *, days: int) -> None:
    from app.db.session import SessionLocal
    from app.models.review import Review
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(review_id))
        moment = datetime.now(UTC) - timedelta(days=days)
        review.created_at = moment
        review.published_at = moment
        db.commit()
    finally:
        db.close()


# --- §2 publication ----------------------------------------------------------


@requires_db
def test_a_review_is_public_everywhere_at_submission(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    pid = _product(client, ah)
    review = _review(client, ah, pid)
    assert review["published_at"] is not None
    assert client.get(f"/api/v1/reviews/{review['id']}").status_code == 200
    feed = client.get("/api/v1/reviews/feed", params={"product_id": pid, "limit": 10}).json()
    assert review["id"] in [item["review"]["id"] for item in feed]
    # Unverified (no photo) is public too; it just cannot earn.
    _, other, _ = register_and_token(client)
    plain = _review(client, _auth(other), pid, photo=False)
    assert plain["published_at"] is not None and plain["photo_provided"] is False


@requires_db
def test_cold_start_approval_is_its_own_audited_action(client):
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog
    _, token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    rid = _review(client, _auth(token), _product(client, _auth(token)))["id"]
    # The suite runs Seeding (queued at submission); force "no community
    # decision yet" to exercise the substitution.
    from app.models.enums import EarnEligibleStatus
    from app.models.review import Review
    db = SessionLocal()
    try:
        db.get(Review, uuid.UUID(rid)).earn_eligible_status = EarnEligibleStatus.none
        db.commit()
    finally:
        db.close()
    assert client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings",
                       headers=_auth(mod)).status_code == 200
    db = SessionLocal()
    try:
        actions = set(db.scalars(select(ModerationLog.action).where(
            ModerationLog.target_ref == uuid.UUID(rid))))
    finally:
        db.close()
    assert ModerationAction.cold_start_substitution in actions
    assert ModerationAction.approve in actions


# --- §3 ownership evidence ---------------------------------------------------------


@requires_db
def test_earning_needs_a_photo_or_receipt_but_publishing_does_not(client):
    _, token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    ah = _auth(token)
    rid = _review(client, ah, _product(client, ah), photo=False)["id"]
    refused = client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings", headers=_auth(mod))
    assert refused.status_code == 409 and refused.json()["code"] == "review_not_verified"
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200


# --- §4 threads, immutability, deletion ------------------------------------------------


@requires_db
def test_an_update_waits_three_months_then_stacks_on_the_thread(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    pid = _product(client, ah)
    root = _review(client, ah, pid, stars=5)
    early = client.post(f"/api/v1/reviews/{root['id']}/updates", headers=ah,
                        json=_entry(ah, stars=3, title="Later"))
    assert early.status_code == 409 and early.json()["code"] == "thread_update_cooldown"

    _backdate(root["id"], days=95)
    update = client.post(f"/api/v1/reviews/{root['id']}/updates", headers=ah,
                         json=_entry(ah, stars=3, title="Three months on"))
    assert update.status_code == 201, update.text
    entry = update.json()
    assert entry["thread_id"] == root["id"] and entry["is_thread_root"] is False
    thread = client.get(f"/api/v1/reviews/{root['id']}/thread").json()
    assert [e["id"] for e in thread["entries"]] == [root["id"], entry["id"]]
    assert thread["entries"][-1]["is_latest"] is True
    # Only the latest entry counts toward the product's rating.
    product = client.get(f"/api/v1/products/{pid}").json()
    assert Decimal(product["median_rating"]) == Decimal("3")
    assert product["review_count"] == 1
    # And the cooldown restarts from the newest entry.
    again = client.post(f"/api/v1/reviews/{entry['id']}/updates", headers=ah,
                        json=_entry(ah, stars=4, title="Too soon"))
    assert again.status_code == 409


@requires_db
def test_the_product_rating_is_the_median_of_each_threads_latest_entry(client):
    tokens = [register_and_token(client)[1] for _ in range(3)]
    pid = _product(client, _auth(tokens[0]))
    for token, stars in zip(tokens, (1, 4, 5), strict=True):
        _review(client, _auth(token), pid, stars=stars)
    product = client.get(f"/api/v1/products/{pid}").json()
    assert Decimal(product["median_rating"]) == Decimal("4")
    assert product["avg_rating"] == product["median_rating"]   # deprecated alias


@requires_db
def test_the_photo_can_be_swapped_once_within_72_hours_only(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    late = _review(client, ah, _product(client, ah))
    _backdate(late["id"], days=4)
    closed = client.patch(f"/api/v1/reviews/{late['id']}", headers=ah,
                          json={"photo_url": owned_photo_url(ah)})
    assert closed.status_code == 409 and closed.json()["code"] == "photo_swap_window_closed"


@requires_db
def test_deleting_an_update_keeps_the_thread_and_the_root_needs_confirmation(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    pid = _product(client, ah)
    root = _review(client, ah, pid, stars=5)
    _backdate(root["id"], days=95)
    update = client.post(f"/api/v1/reviews/{root['id']}/updates", headers=ah,
                         json=_entry(ah, stars=2, title="Worse now")).json()

    gone = client.delete(f"/api/v1/reviews/{update['id']}", headers=ah)
    assert gone.status_code == 200 and gone.json()["removed_ids"] == [update["id"]]
    assert client.get(f"/api/v1/reviews/{root['id']}").status_code == 200
    assert Decimal(client.get(f"/api/v1/products/{pid}").json()["median_rating"]) == Decimal("5")

    unconfirmed = client.delete(f"/api/v1/reviews/{root['id']}", headers=ah)
    assert unconfirmed.status_code == 409
    assert unconfirmed.json()["code"] == "thread_delete_confirmation_required"
    _, stranger, _ = register_and_token(client)
    assert client.delete(f"/api/v1/reviews/{root['id']}?confirm=delete-thread",
                         headers=_auth(stranger)).status_code == 403
    confirmed = client.delete(f"/api/v1/reviews/{root['id']}?confirm=delete-thread", headers=ah)
    assert confirmed.status_code == 200
    assert client.get(f"/api/v1/reviews/{root['id']}").status_code == 404
    # The author may review the product afresh once the thread is gone.
    assert client.post("/api/v1/reviews", headers=ah, json={
        "product_id": pid, **_entry(ah)}).status_code == 201


@requires_db
def test_a_paid_thread_leaves_only_an_aggregate_trace_when_deleted(client):
    from app.db.session import SessionLocal
    from app.models.commission import Commission
    from app.models.enums import CommissionTarget
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    author_id = client.get("/api/v1/auth/me", headers=ah).json()["id"]
    pid = _product(client, ah)
    rid = _review(client, ah, pid)["id"]
    db = SessionLocal()
    try:
        db.add(Commission(
            commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=uuid.UUID(rid), reviewer_id=uuid.UUID(author_id),
            reviewer_share_bps=3000, gross_amount=Decimal("100.00"),
            platform_share=Decimal("40.00"), reviewer_share=Decimal("30.00"),
            honesty_fund_share=Decimal("30.00"), currency="PHP",
            csv_source=f"test:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=datetime.now(UTC).date().replace(day=1)))
        db.commit()
    finally:
        db.close()
    assert client.delete(f"/api/v1/reviews/{rid}?confirm=delete-thread",
                         headers=ah).status_code == 200
    product = client.get(f"/api/v1/products/{pid}").json()
    assert product["removed_after_payout_count"] == 1


# --- §14 track flips ---------------------------------------------------------------


@requires_db
def test_an_update_that_crosses_to_the_fund_revokes_the_link_prospectively(client):
    _, token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    ah, mh = _auth(token), _auth(mod)
    pid = _product(client, ah)
    root = _review(client, ah, pid, verdict="yes_absolutely", stars=5)
    attach = client.post(f"/api/v1/admin/reviews/{root['id']}/referral-link", headers=mh,
                         json={"url": "https://s.shopee.ph/FlipTest1", "platform": "shopee"})
    assert attach.status_code == 200, attach.text
    _backdate(root["id"], days=95)
    assert client.post(f"/api/v1/reviews/{root['id']}/updates", headers=ah,
                       json=_entry(ah, verdict="hard_pass", stars=1,
                                   title="It broke")).status_code == 201
    after = client.get(f"/api/v1/reviews/{root['id']}").json()
    assert after["earn_eligible_status"] == "honesty_fund"
    assert after["referral_redirect_url"] is None
    links = client.get(f"/api/v1/admin/reviews/{root['id']}/referral-links", headers=mh).json()
    assert [link["status"] for link in links] == ["revoked"]


# --- §9 sellers ------------------------------------------------------------------


def _claimed_seller(client):
    seller_uid, seller_token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    store = client.post("/api/v1/sellers", headers=_auth(seller_token), json={
        "display_name": f"Rules Store {uuid.uuid4().hex[:8]}", "platform": "shopee"}).json()
    claim = client.post(f"/api/v1/sellers/{store['id']}/claims", headers=_auth(seller_token),
                        json=claim_body(shop_name=store["display_name"]))
    assert claim.status_code == 201, claim.text
    assert claim.json()["shop_name_matches"] is True
    decided = client.post(f"/api/v1/admin/seller-claims/{claim.json()['id']}/decision",
                          headers=_auth(mod), json={"decision": "approve"})
    assert decided.status_code == 200, decided.text
    return seller_uid, seller_token, store, mod


@requires_db
def test_a_claimed_seller_can_never_vote_review_or_earn_anywhere(client):
    _, seller, store, _ = _claimed_seller(client)
    sh = _auth(seller)
    _, author, _ = register_and_token(client)
    other_pid = _product(client, _auth(author), "UnrelatedProduct")
    rid = _review(client, _auth(author), other_pid)["id"]

    vote = client.post(f"/api/v1/reviews/{rid}/vote", headers=sh, json={"vote": "up"})
    assert vote.status_code == 403 and vote.json()["code"] == "seller_cannot_vote"
    review = client.post("/api/v1/reviews", headers=sh,
                         json={"product_id": _product(client, sh), **_entry(sh)})
    assert review.status_code == 403 and review.json()["code"] == "seller_cannot_review"
    rate = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=sh, json={
        "accuracy": True, "order_completeness": True, "customer_service": 5,
        "packaging_quality": 5, "overall_rating": 5, "would_recommend": True})
    assert rate.status_code in (403, 422)
    # Comments and replies are allowed (§8): no Stage-1 bar for a seller.
    comment = client.post(f"/api/v1/reviews/{rid}/comments", headers=sh,
                          json={"body": "Thanks for the honest review."})
    assert comment.status_code == 201, comment.text
    assert comment.json()["author"]["is_claimed_seller"] is True


@requires_db
def test_a_seller_appeal_goes_to_an_admin_who_asks_the_reviewer(client):
    _, seller, store, mod = _claimed_seller(client)
    _, buyer, _ = register_and_token(client)
    rated = client.post(f"/api/v1/sellers/{store['id']}/reviews", headers=_auth(buyer), json={
        "accuracy": False, "order_completeness": True, "customer_service": 1,
        "packaging_quality": 2, "overall_rating": 1, "would_recommend": False,
        "comment": "Never arrived.", "order_id": "2409ABC123"})
    assert rated.status_code == 201, rated.text
    assert rated.json()["order_id_provided"] is True
    assert "order_id" not in rated.json()                 # never public

    respond = client.post(f"/api/v1/sellers/reviews/{rated.json()['id']}/response",
                          headers=_auth(seller), json={"body": "We have refunded this order."})
    assert respond.status_code == 200 and respond.json()["seller_response"]

    appeal = client.post(f"/api/v1/sellers/reviews/{rated.json()['id']}/appeal",
                         headers=_auth(seller), json={"reason": "No such order in our records."})
    assert appeal.status_code == 201, appeal.text
    queue = all_pages(client, "/api/v1/admin/seller-review-appeals", _auth(mod))
    mine = next(a for a in queue if a["id"] == appeal.json()["id"])
    assert mine["order_id"] == "2409ABC123"               # admins see it
    asked = client.post(
        f"/api/v1/admin/seller-review-appeals/{mine['id']}/substantiation-request",
        headers=_auth(mod), json={"note": "Please share your order confirmation."})
    assert asked.json()["status"] == "substantiation_requested"
    # The reviewer can read what they are being asked (the notification's
    # link), without the order ID echoed back; nobody else can read it at all.
    seen = client.get(f"/api/v1/sellers/appeals/{mine['id']}", headers=_auth(buyer))
    assert seen.status_code == 200, seen.text
    assert seen.json()["substantiation_request"] == "Please share your order confirmation."
    assert seen.json()["order_id"] is None
    assert client.get(f"/api/v1/sellers/appeals/{mine['id']}",
                      headers=_auth(seller)).status_code == 404
    answered = client.post(f"/api/v1/sellers/appeals/{mine['id']}/substantiation",
                           headers=_auth(buyer), json={"response": "Order 2409ABC123, 3 Sept."})
    assert answered.status_code == 200
    kept = client.post(f"/api/v1/admin/seller-review-appeals/{mine['id']}/decision",
                       headers=_auth(mod), json={"decision": "dismiss"})
    assert kept.json()["status"] == "dismissed"
    assert rated.json()["id"] in [r["id"] for r in client.get(
        f"/api/v1/sellers/{store['id']}/reviews").json()]


# --- §8 comments -----------------------------------------------------------------


@requires_db
def test_commenting_needs_stage_one_and_a_reported_thread_needs_stage_two(client):
    _, author, _ = register_and_token(client)
    ah = _auth(author)
    rid = _review(client, ah, _product(client, ah))["id"]
    _, newcomer, _ = register_and_token(client)
    locked = client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(newcomer),
                         json={"body": "First!"})
    assert locked.status_code == 403 and locked.json()["code"] == "comment_stage_locked"

    commenter_id, commenter, _ = register_commenter(client)
    ok = client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(commenter),
                     json={"body": "Does it fold?"})
    assert ok.status_code == 201
    assert ok.json()["author"]["is_new_account"] is True

    _, reporter, _ = register_and_token(client)
    assert client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter),
                       json={"reason": "spam"}).status_code == 201
    barred = client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(commenter),
                         json={"body": "Pile on"})
    assert barred.status_code == 403 and barred.json()["code"] == "comment_thread_reported"
    set_trust_stage(commenter_id, 2)
    assert client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(commenter),
                       json={"body": "Measured reply"}).status_code == 201


@requires_db
def test_links_are_refused_in_every_free_text_field(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    pid = _product(client, ah)
    body = {"product_id": pid, **_entry(ah)}
    body["discussion"] = "Cheaper at shopee[dot]ph/cheap"
    assert client.post("/api/v1/reviews", headers=ah, json=body).status_code == 422
    q = client.post("/api/v1/questions", headers=ah,
                    json={"product_id": pid, "body": "Seen at www.example.com?"})
    assert q.status_code == 422
    profile = client.patch("/api/v1/users/me", headers=ah,
                           json={"display_name": "Best deals: bit.ly/deals"})
    assert profile.status_code == 422


# --- §7 Q&A ------------------------------------------------------------------------


@requires_db
def test_best_answer_is_the_askers_attributed_pick_and_never_a_sellers(client):
    _, asker, _ = register_and_token(client)
    _, helper, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    question = client.post("/api/v1/questions", headers=_auth(asker),
                           json={"product_id": pid, "body": "Is it quiet?"}).json()
    answer = client.post(f"/api/v1/questions/{question['id']}/answers", headers=_auth(helper),
                         json={"body": "Quiet on low.", "rating": 4}).json()
    _, seller, _, _ = _claimed_seller(client)
    competing = client.post(f"/api/v1/questions/{question['id']}/answers",
                            headers=_auth(seller), json={"body": "Ours is quieter."})
    assert competing.status_code == 403 and competing.json()["code"] == "seller_cannot_answer"

    _, follower, _ = register_and_token(client)
    assert client.put(f"/api/v1/questions/{question['id']}/subscription",
                      headers=_auth(follower), json={"subscribed": True}).status_code == 200
    picked = client.post(f"/api/v1/questions/{question['id']}/answers/{answer['id']}/best",
                         headers=_auth(asker))
    assert picked.status_code == 200
    assert picked.json()["best_answer_picked_by_asker"] is True
    assert picked.json()["best_answer_picked_at"] is not None
    detail = client.get(f"/api/v1/questions/{question['id']}", headers=_auth(follower)).json()
    assert detail["is_subscribed"] is True


# --- §12 reports -------------------------------------------------------------------


@requires_db
def test_reports_are_weighted_labelled_and_an_urgent_reason_escalates(client):
    _, author, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    rid = _review(client, _auth(author), _product(client, _auth(author)))["id"]
    _, newcomer, _ = register_and_token(client)
    assert client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(newcomer),
                       json={"reason": "personal_information"}).status_code == 201
    queue = client.get("/api/v1/admin/reports", headers=_auth(mod)).json()
    item = next(i for i in queue["items"] if i["report"]["target_ref"] == rid)
    assert item["report"]["report_source"] == "user_reported"
    assert item["origin"] == "user_reported"
    assert item["urgent_reason"] is True and item["escalated"] is True
    assert item["target_weighted_reports"] == 0.0       # a Stage-0 report weighs nothing


# --- §11 investigation ------------------------------------------------------------------


@requires_db
def test_under_investigation_halves_a_vote_and_is_a_moderator_action(client):
    from app.db.session import SessionLocal
    from app.models.vote import ReviewVote
    voter_id, voter, _ = register_and_token(client)
    make_established(voter_id)
    _, mod, _ = register_and_token(client, role="administrator")
    _, author, _ = register_and_token(client)
    rid = _review(client, _auth(author), _product(client, _auth(author)))["id"]
    assert client.put(f"/api/v1/admin/users/{voter_id}/investigation", headers=_auth(mod),
                      json={"under_investigation": True}).status_code == 200
    assert client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(voter),
                       json={"vote": "up"}).status_code == 200
    db = SessionLocal()
    try:
        from sqlalchemy import select
        weight = db.scalar(select(ReviewVote.vote_weight).where(
            ReviewVote.review_id == uuid.UUID(rid)))
    finally:
        db.close()
    assert Decimal(weight) == Decimal("0.5000")       # Stage 2 x 100% = 1.0, halved


# --- §6 search, §5 canonicalization ----------------------------------------------------


@requires_db
def test_search_tolerates_typos_learns_aliases_and_ignores_mid_token_matches(client):
    _, token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    ah = _auth(token)
    marker = uuid.uuid4().hex[:5]
    fan = client.post("/api/v1/products", headers=_auth(mod), json={
        "name": f"Zqxulife{marker} Handheld Fan", "category": "electronics"}).json()
    bank = client.post("/api/v1/products", headers=_auth(mod), json={
        "name": f"Zq{marker}bank 10000mAh", "category": "electronics"}).json()
    typo = client.get("/api/v1/products", params={"q": f"zqxulfe{marker}"}).json()
    assert fan["id"] in [p["id"] for p in typo]
    assert client.post(f"/api/v1/products/{fan['id']}/aliases", headers=_auth(mod),
                       json={"aliases": [f"pocket breeze {marker}"]}).status_code == 200
    alias = client.get("/api/v1/products", params={"q": f"pocket breeze {marker}"}).json()
    assert alias and alias[0]["id"] == fan["id"]
    short = client.get("/api/v1/products", params={"q": "ma", "limit": 100}).json()
    assert bank["id"] not in [p["id"] for p in short]
    del ah


@requires_db
def test_a_submitted_listing_attaches_to_the_existing_canonical_product(client):
    _, token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    canonical = client.post("/api/v1/products", headers=_auth(mod), json={
        "name": f"Attach Target {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()
    submitted = client.post("/api/v1/products", headers=_auth(token), json={
        "name": f"attach target lazada {uuid.uuid4().hex[:8]}",
        "source_url": f"https://www.lazada.com.ph/products/x-i{uuid.uuid4().int % 10**9}.html"
    }).json()
    assert submitted["status"] == "pending"
    attached = client.post(f"/api/v1/products/{submitted['id']}/attach", headers=_auth(mod),
                           json={"target_product_id": canonical["id"]})
    assert attached.status_code == 200, attached.text
    again = client.post(f"/api/v1/products/{submitted['id']}/attach", headers=_auth(mod),
                        json={"target_product_id": canonical["id"]})
    assert again.status_code == 409


# --- §17 profiles -----------------------------------------------------------------------


@requires_db
def test_the_public_profile_shows_relationships_but_never_reporters_or_earnings(client):
    author_id, author, _ = register_and_token(client)
    _, fan, _ = register_and_token(client)
    rid = _review(client, _auth(author), _product(client, _auth(author)))["id"]
    assert client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(fan),
                       json={"vote": "up"}).status_code == 200
    _, reporter, _ = register_and_token(client)
    client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter), json={"reason": "spam"})
    profile = client.get(f"/api/v1/users/public/{author_id}").json()
    assert profile["people_helped"] == 1
    assert profile["most_interacted_by"][0]["upvotes"] == 1
    text = str(profile)
    for private in ("reporter", "wallet", "earning", "payout", "commission"):
        assert private not in text


# --- §15 payouts ------------------------------------------------------------------------


def _free_remittance_cycle(platform):
    """A cycle month with no remittance recorded for `platform` yet, and no
    commissions either, so the test's pool and clearing are its own."""
    from datetime import date

    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.commission import Commission, MarketplaceRemittance
    db = SessionLocal()
    try:
        used = set(db.scalars(select(MarketplaceRemittance.cycle_month).where(
            MarketplaceRemittance.platform == platform)))
        used |= set(db.scalars(select(Commission.cycle_month).distinct()))
    finally:
        db.close()
    for year in range(1900, 2000):
        for month in range(1, 13):
            cycle = date(year, month, 1)
            if cycle not in used:
                return cycle
    raise AssertionError("no free remittance cycle")


@requires_db
def test_uncleared_commission_cannot_be_cashed_out_until_the_remittance(client):
    from app.db.session import SessionLocal
    from app.models.commission import Commission
    from app.models.enums import CommissionTarget, Platform
    from app.models.user import User
    uid, token, _ = register_and_token(client)
    _, mod, _ = register_and_token(client, role="administrator")
    ah = _auth(token)
    rid = _review(client, ah, _product(client, ah))["id"]
    platform = Platform.shopee
    # A remittance is unique per (platform, cycle): a fixed month collided with
    # the one an earlier run left in the shared test database (canonical CI
    # 35883412818 — 409 remittance_exists). Take a month nobody has used.
    cycle = _free_remittance_cycle(platform)
    db = SessionLocal()
    try:
        db.add(Commission(
            commission_id=f"com_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=uuid.UUID(rid), reviewer_id=uuid.UUID(uid), reviewer_share_bps=3000,
            gross_amount=Decimal("2000.00"), platform_share=Decimal("800.00"),
            reviewer_share=Decimal("600.00"), honesty_fund_share=Decimal("600.00"),
            currency="PHP", csv_source=f"test:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=cycle, platform=platform, cleared_at=None))
        user = db.get(User, uuid.UUID(uid))
        user.wallet_balance = Decimal("600.00")
        user.payout_account = "payee@example.com"
        db.commit()
    finally:
        db.close()
    balance = client.get("/api/v1/payouts/balance", headers=ah).json()
    assert Decimal(balance["pending_clearance"]) == Decimal("600.00")
    assert Decimal(balance["withdrawable"]) == Decimal("0.00")
    refused = client.post("/api/v1/payouts/cashout", headers=ah, json={})
    assert refused.status_code == 422 and refused.json()["code"] == "below_payout_minimum"

    recorded = client.post("/api/v1/admin/remittances", headers=_auth(mod), json={
        "platform": "shopee", "cycle_month": cycle.isoformat(), "amount_received": "2000.00",
        "received_on": cycle.isoformat()})
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["cleared_commissions"] >= 1
    assert Decimal(client.get("/api/v1/payouts/balance", headers=ah)
                   .json()["withdrawable"]) == Decimal("600.00")
    paid = client.post("/api/v1/payouts/cashout", headers=ah, json={})
    assert paid.status_code == 201 and Decimal(paid.json()["amount"]) == Decimal("600.00")


# --- QA-054: the rejected author is told why, on the review itself ---------------


@requires_db
def test_rejection_reason_reaches_only_the_author_on_the_review_read(client):
    _, author, _ = register_and_token(client)
    ah = _auth(author)
    _, mod, _ = register_and_token(client, role="administrator")
    _, stranger, _ = register_and_token(client)
    rid = _review(client, ah, _product(client, ah))["id"]
    assert client.post(f"/api/v1/admin/reviews/{rid}/reject", headers=_auth(mod),
                       json={"reason": "Photo is a stock image."}).status_code == 200

    own = client.get(f"/api/v1/reviews/{rid}/full", headers=ah)
    assert own.status_code == 200                      # still public (§2)
    assert own.json()["author_rejection_reason"] == "Photo is a stock image."
    assert client.get(f"/api/v1/reviews/{rid}/full",
                      headers=_auth(stranger)).json()["author_rejection_reason"] is None
    assert client.get(f"/api/v1/reviews/{rid}/full").json()["author_rejection_reason"] is None

    note = next(n for n in client.get("/api/v1/notifications", headers=ah).json()
                if n["kind"] == "earnings_rejected")
    assert note["link"] == f"/reviews/{rid}"

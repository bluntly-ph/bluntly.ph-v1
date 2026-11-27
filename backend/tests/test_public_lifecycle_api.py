"""Public on submission; earning decided separately (confirmed by Zient 2026-09-22).

Publication and earn eligibility used to be one moderator click: a review was
hidden until a moderator "published" it, and publishing also routed its
earnings. These pin the separated lifecycle:

* submitting makes a review public — detail page, feed, product, profile,
  search — and does not make it earn;
* the moderator's earn decisions (approve, attach, reject) never change
  visibility; take-down and restore never change earnings;
* the Post-Seeding gate queues a review from trust-weighted gate votes;
* the admin's awaiting-affiliate list holds exactly the approved, public,
  monetizable reviews without a link;
* the author's and staff's own opens do not count as views.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.core.config import Settings, settings
from tests.conftest import owned_photo_url, register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers, *, platform: str | None = None) -> tuple[str, str]:
    name = f"Lifecycle {uuid.uuid4().hex[:10]}"
    pid = client.post("/api/v1/products", headers=headers,
                      json={"name": name, "category": "electronics"}).json()["id"]
    if platform:
        from app.db.session import SessionLocal
        from app.models.enums import Platform
        from app.models.product import ProductPlatform
        db = SessionLocal()
        try:
            db.add(ProductPlatform(product_id=uuid.UUID(pid), platform=Platform(platform),
                                   platform_url=f"https://www.lazada.com.ph/products/{name}",
                                   is_monetizable=True))
            db.commit()
        finally:
            db.close()
    return pid, name


def _review(client, headers, pid: str, name: str, *, stars: float = 4, photo: bool = True,
            verdict: str = "yes_absolutely") -> dict:
    body = {"product_id": pid, "title": f"Review of {name}",
            "discussion": f"Weeks of daily use. {name}.", "verdict": verdict,
            "star_rating": stars}
    if photo:
        body["photo_url"] = owned_photo_url(headers)
    created = client.post("/api/v1/reviews", headers=headers, json=body)
    assert created.status_code == 201, created.text
    return created.json()


@requires_db
def test_submission_is_public_everywhere_it_should_be(client):
    author_id, token, _ = register_and_token(client)
    ah = _auth(token)
    pid, name = _product(client, ah)
    review = _review(client, ah, pid, name)
    rid = review["id"]

    assert review["published_at"] is not None
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200            # detail
    feed = lambda **p: [i["review"]["id"] for i in client.get(                 # noqa: E731
        "/api/v1/reviews/feed", params={"limit": 100, "sort": "newest", **p}).json()]
    assert rid in feed()                                                      # feed
    assert rid in feed(product_id=pid)                                        # product page
    assert rid in feed(author_id=str(author_id))                              # public profile
    assert rid in feed(q=name)                                                # search


APP_DEFAULT_PHASE = Settings.model_fields["earn_gate_phase"].default


def test_the_application_default_is_post_seeding():
    """Zient (2026-09-22): a review reaches the admin queue when enough votes
    accumulate. Seeding must never be the silent default."""
    assert APP_DEFAULT_PHASE == "post_seeding"


@pytest.mark.parametrize("configured", ["", "  ", "Seeding-ish", "postseeding", None])
def test_a_blank_or_unknown_phase_is_post_seeding(monkeypatch, configured):
    from app.services import earn_gate
    monkeypatch.setattr(settings, "earn_gate_phase", configured)
    assert earn_gate.current_phase(db=None) == "post_seeding"


@requires_db
def test_by_default_a_new_review_is_public_and_outside_the_earn_queue(client, monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", APP_DEFAULT_PHASE)
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    pid, name = _product(client, ah, platform="lazada")
    review = _review(client, ah, pid, name)

    assert review["published_at"] is not None
    assert review["earn_eligible_status"] == "none"
    assert client.get(f"/api/v1/reviews/{review['id']}").status_code == 200
    queue = client.get("/api/v1/admin/review-queue", headers=_auth(mod_token),
                       params={"q": name, "limit": 100}).json()
    assert review["id"] not in [i["review"]["id"] for i in queue["items"]]


@requires_db
def test_explicit_seeding_queues_at_submission(client):
    """The suite runs with Seeding configured explicitly (conftest)."""
    assert settings.earn_gate_phase == "seeding"
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    review = _review(client, ah, *(_product(client, ah)))
    assert review["earn_eligible_status"] == "pending"


@requires_db
def test_weighted_helpfulness_votes_are_the_earnings_gate(client, monkeypatch):
    """Business Rules §2/§11 supersede the separate gate vote: a review's own
    upvotes have a visible count and a backend trust weight, and enough
    weighted votes put it in the admin's earnings queue."""
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    rid = _review(client, ah, *(_product(client, ah)))["id"]
    for _ in range(6):
        uid, vt, _ = register_and_token(client)
        _promote(uid, stage=4, reputation="100", age_days=60)
        assert client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(vt),
                           json={"vote": "up"}).status_code == 200
    review = client.get(f"/api/v1/reviews/{rid}").json()
    assert review["helpful_votes"] == 6                      # the visible count
    assert review["earn_eligible_status"] == "pending"       # queued, not approved
    gate = client.get(f"/api/v1/admin/reviews/{rid}/gate", headers=_auth(mod_token)).json()
    assert gate["voters"] == 6 and gate["passes"] is True


@requires_db
def test_submission_alone_does_not_advance_trust_or_mint_tokens(client, monkeypatch):
    """Publication moved earlier; trust and the publish reward did not."""
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    uid, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    review = _review(client, ah, *(_product(client, ah)))       # verified: owned photo
    assert review["verification_status"] == "verified"

    def trust():
        return client.get(f"/api/v1/users/{uid}/trust").json()

    def tokens():
        return client.get("/api/v1/tokens/balance", headers=ah).json()["token_balance"]

    # §8: posting a review is Stage 1 (it unlocks commenting); Stage 2 and the
    # publish reward still wait for a moderator's look.
    assert trust()["trust_stage"] == 1
    assert tokens() == 0
    # A moderator's approval is the human look that used to be "publish".
    assert client.post(f"/api/v1/admin/reviews/{review['id']}/approve-earnings",
                       headers=_auth(mod_token)).status_code == 200
    assert trust()["trust_stage"] == 2
    assert tokens() == settings.tokens_on_review_published


@requires_db
def test_rejected_earnings_stop_counting_toward_trust(client):
    uid, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)
    rid = _review(client, ah, *(_product(client, ah)))["id"]
    assert client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings",
                       headers=mh).status_code == 200
    assert client.get(f"/api/v1/users/{uid}/trust").json()["trust_stage"] == 2
    # Earnings on the approved (non-monetized) review are rejected on second look.
    assert client.post(f"/api/v1/admin/reviews/{rid}/reject", headers=mh,
                       json={"reason": "Photo is a stock image."}).status_code == 200
    # Back to Stage 1: the review is still public (§2), so still "posted".
    assert client.get(f"/api/v1/users/{uid}/trust").json()["trust_stage"] == 1
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200     # still public


@requires_db
def test_publication_does_not_enable_earnings(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    pid, name = _product(client, ah, platform="lazada")
    rid = _review(client, ah, pid, name)["id"]

    body = client.get(f"/api/v1/reviews/{rid}").json()
    assert body["earn_eligible_status"] == "pending"      # queued for a decision (Seeding)
    assert body.get("referral_redirect_url") is None
    assert client.get(f"/r/{rid}", follow_redirects=False).status_code == 404


@requires_db
def test_earn_decisions_never_change_visibility(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)
    pid, name = _product(client, ah, platform="lazada")

    approve = _review(client, ah, pid, name, stars=4)
    # §14: the verdict decides the track; stars do not override it.
    fund = _review(client, ah, *(_product(client, ah)), stars=4, verdict="hard_pass")
    reject = _review(client, ah, *(_product(client, ah)), stars=5)

    a = client.post(f"/api/v1/admin/reviews/{approve['id']}/approve-earnings", headers=mh)
    assert a.status_code == 200, a.text
    assert a.json()["earn_eligible_status"] == "approved"
    assert a.json()["published_at"] == approve["published_at"]

    f = client.post(f"/api/v1/admin/reviews/{fund['id']}/approve-earnings", headers=mh)
    assert f.json()["earn_eligible_status"] == "honesty_fund"   # "Hard pass" -> fund
    assert f.json()["published_at"] == fund["published_at"]

    r = client.post(f"/api/v1/admin/reviews/{reject['id']}/reject", headers=mh,
                    json={"reason": "No receipt."})
    assert r.json()["earn_eligible_status"] == "rejected"
    assert client.get(f"/api/v1/reviews/{reject['id']}").status_code == 200

    # Deciding twice is refused rather than silently re-routed.
    again = client.post(f"/api/v1/admin/reviews/{approve['id']}/approve-earnings", headers=mh)
    assert again.status_code == 409
    assert again.json()["code"] == "earnings_already_decided"


@requires_db
def test_attach_approves_the_affiliate_path_without_touching_publication(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)
    pid, name = _product(client, ah, platform="lazada")
    review = _review(client, ah, pid, name, stars=4)

    attached = client.post(f"/api/v1/admin/reviews/{review['id']}/referral-link", headers=mh,
                           json={"url": "https://s.lazada.com.ph/s.TEST01?c=t",
                                 "platform": "lazada"})
    assert attached.status_code == 200, attached.text
    assert attached.json()["earn_eligible_status"] == "monetized"
    assert attached.json()["published_at"] == review["published_at"]
    redirect = client.get(f"/r/{review['id']}", follow_redirects=False)
    assert redirect.status_code == 302
    # Lazada: the review's sub-ID and a per-click ID are appended to Zient's link.
    assert "sub_id1=blt_" in redirect.headers["location"]
    assert "sub_id2=ref_" in redirect.headers["location"]


@requires_db
def test_a_taken_down_review_cannot_be_approved_until_restored(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)
    review = _review(client, ah, *(_product(client, ah)))

    assert client.post(f"/api/v1/admin/reviews/{review['id']}/unpublish", headers=mh,
                       json={"reason": "Report under review."}).status_code == 200
    blocked = client.post(f"/api/v1/admin/reviews/{review['id']}/approve-earnings", headers=mh)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "not_published"
    restored = client.post(f"/api/v1/admin/reviews/{review['id']}/restore", headers=mh)
    assert restored.json()["published_at"] == review["published_at"]
    assert client.post(f"/api/v1/admin/reviews/{review['id']}/approve-earnings",
                       headers=mh).status_code == 200


def _promote(user_id, *, stage: int, reputation: str = "90", age_days: int = 0) -> None:
    from datetime import UTC, datetime, timedelta

    from app.db.session import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(str(user_id)))
        user.trust_stage = stage
        user.reputation_score = Decimal(reputation)
        if age_days:
            user.created_at = datetime.now(UTC) - timedelta(days=age_days)
        db.commit()
    finally:
        db.close()


@requires_db
def test_post_seeding_gate_queues_a_review_from_trust_weighted_votes(client, monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    review = _review(client, ah, *(_product(client, ah)))
    rid = review["id"]
    assert review["earn_eligible_status"] == "none"   # Post-Seeding: waits for the gate

    def gate():
        return client.get(f"/api/v1/admin/reviews/{rid}/gate", headers=_auth(mod_token)).json()

    # A Stage 0 account may vote (the visible count moves) but its vote weighs
    # nothing toward the gate (§11).
    _, newbie, _ = register_and_token(client)
    assert client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(newbie),
                       json={"vote": "up"}).status_code == 200
    assert gate()["effective_total"] == 0

    # Three new Stage 3 accounts: each weight is halved (< 30 days), so the
    # effective n stays small and the Wilson lower bound cannot reach 0.65.
    for _ in range(3):
        uid, vt, _ = register_and_token(client)
        _promote(uid, stage=3)
        assert client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(vt),
                           json={"vote": "up"}).status_code == 200
    state = gate()
    assert state["stage2_plus_voters"] == 3 and state["passes"] is False
    assert client.get(f"/api/v1/reviews/{rid}").json()["earn_eligible_status"] == "none"

    # Mature, high-trust voters carry full weight (Stage 4 x 100% = 2.0 each).
    for _ in range(3):
        uid, vt, _ = register_and_token(client)
        _promote(uid, stage=4, reputation="100", age_days=60)
        client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(vt), json={"vote": "up"})
    state = gate()
    assert state["passes"] is True, state
    assert state["wilson_lower_bound"] >= 0.65
    assert client.get(f"/api/v1/reviews/{rid}").json()["earn_eligible_status"] == "pending"


@requires_db
def test_votes_do_not_reopen_a_moderator_decision(client, monkeypatch):
    monkeypatch.setattr(settings, "earn_gate_phase", "post_seeding")
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    rid = _review(client, ah, *(_product(client, ah)))["id"]
    # Cold-start substitution: the moderator approves before any vote exists.
    assert client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings",
                       headers=_auth(mod_token)).status_code == 200
    uid, vt, _ = register_and_token(client)
    _promote(uid, stage=4)
    client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(vt), json={"vote": "down"})
    assert client.get(f"/api/v1/reviews/{rid}").json()["earn_eligible_status"] == "approved"


@requires_db
def test_awaiting_affiliate_lists_exactly_the_approved_public_linkless_reviews(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)

    pid, name = _product(client, ah, platform="lazada")
    waiting = _review(client, ah, pid, name, stars=4)
    fund = _review(client, ah, *(_product(client, ah, platform="lazada")), stars=2,
                   verdict="hard_pass")
    no_listing = _review(client, ah, *(_product(client, ah)), stars=4)
    pending = _review(client, ah, *(_product(client, ah, platform="lazada")), stars=4)
    for rid in (waiting["id"], fund["id"], no_listing["id"]):
        assert client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings",
                           headers=mh).status_code == 200

    def listed() -> set[str]:
        body = client.get("/api/v1/admin/awaiting-affiliate", headers=mh,
                          params={"limit": 100}).json()
        return {i["review"]["id"] for i in body["items"]}

    ids = listed()
    assert waiting["id"] in ids
    assert fund["id"] not in ids          # Honesty Fund path, no link needed
    assert no_listing["id"] not in ids    # nothing monetizable to link to
    assert pending["id"] not in ids       # earnings not approved yet

    item = next(i for i in client.get("/api/v1/admin/awaiting-affiliate", headers=mh,
                                      params={"limit": 100}).json()["items"]
                if i["review"]["id"] == waiting["id"])
    assert item["suggested_sub_id"].startswith("blt_")
    assert [p["platform"] for p in item["platforms"]] == ["lazada"]
    assert set(item["momentum"]) >= {"last_24h", "last_7d", "open_reports"}

    assert client.post(f"/api/v1/admin/reviews/{waiting['id']}/referral-link", headers=mh,
                       json={"url": "https://s.lazada.com.ph/s.TEST02?c=t",
                             "platform": "lazada"}).status_code == 200
    assert waiting["id"] not in listed()

    # Non-moderators cannot read it.
    assert client.get("/api/v1/admin/awaiting-affiliate", headers=ah).status_code == 403


def _views(review_id: str) -> int:
    from sqlalchemy import func, select

    from app.db.session import SessionLocal
    from app.models.traffic import ReviewViewBucket
    db = SessionLocal()
    try:
        return int(db.scalar(select(func.coalesce(func.sum(ReviewViewBucket.view_count), 0))
                             .where(ReviewViewBucket.review_id == uuid.UUID(review_id))) or 0)
    finally:
        db.close()


@requires_db
def test_author_and_staff_opens_do_not_count_as_views(client):
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    rid = _review(client, ah, *(_product(client, ah)))["id"]
    beacon = {"review_id": rid, "country": "PH"}

    assert client.post("/api/v1/internal/traffic", json=beacon, headers=ah).status_code == 204
    assert client.post("/api/v1/internal/traffic", json=beacon,
                       headers=_auth(mod_token)).status_code == 204
    assert _views(rid) == 0
    # A reader, signed in or not, counts. An expired/garbage token is a reader.
    _, reader, _ = register_and_token(client)
    client.post("/api/v1/internal/traffic", json=beacon, headers=_auth(reader))
    client.post("/api/v1/internal/traffic", json=beacon)
    client.post("/api/v1/internal/traffic", json=beacon, headers=_auth("not-a-token"))
    assert _views(rid) == 3


@requires_db
def test_an_unverified_review_is_public_too(client):
    """Verification is an earning question, never a visibility one."""
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    review = _review(client, ah, *(_product(client, ah)), photo=False)
    assert review["verification_status"] == "unverified"
    assert review["published_at"] is not None
    assert client.get(f"/api/v1/reviews/{review['id']}").status_code == 200


@requires_db
def test_two_and_a_half_stars_on_it_depends_escalates_to_a_super_admin(client):
    """Owner decision A: the administrator's approval escalates rather than
    routes, and the link waits for the Super Admin; "Yes" and "Hard pass" at 2.5
    are still decided by the verdict alone."""
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    undecided = _review(client, ah, *(_product(client, ah)), stars=2.5, verdict="it_depends")
    escalated = client.post(f"/api/v1/admin/reviews/{undecided['id']}/approve-earnings",
                            headers=_auth(mod_token))
    assert escalated.status_code == 200, escalated.text
    assert escalated.json()["earn_eligible_status"] == "pending_superadmin_routing"
    again = client.post(f"/api/v1/admin/reviews/{undecided['id']}/approve-earnings",
                        headers=_auth(mod_token))
    assert again.status_code == 409 and again.json()["code"] == "earnings_already_decided"

    yes = _review(client, ah, *(_product(client, ah)), stars=2.5, verdict="yes_absolutely")
    approved = client.post(f"/api/v1/admin/reviews/{yes['id']}/approve-earnings",
                           headers=_auth(mod_token))
    assert approved.json()["earn_eligible_status"] == "approved"


@pytest.mark.parametrize("phase", ["seeding", "post_seeding"])
def test_gate_phase_override_is_respected(monkeypatch, phase):
    from app.services import earn_gate
    monkeypatch.setattr(settings, "earn_gate_phase", phase)
    assert earn_gate.current_phase(db=None) == phase


@requires_db
def test_the_overviews_pending_affiliate_is_the_queues_own_count(client):
    """Defense rehearsal: the affiliate-links page said "27 approved reviews still
    need a link" above a list of five. The headline counted approved reviews of
    products with no listing, which the queue rightly leaves out."""
    _, token, _ = register_and_token(client)
    ah = _auth(token)
    _, mod_token, _ = register_and_token(client, role="administrator")
    mh = _auth(mod_token)

    def numbers() -> tuple[int, int]:
        card = client.get("/api/v1/admin/analytics/overview", headers=mh).json()
        queue = client.get("/api/v1/admin/awaiting-affiliate", headers=mh,
                           params={"limit": 1}).json()
        return card["pending_affiliate"], queue["total"]

    before_card, before_queue = numbers()
    assert before_card == before_queue
    listed = _review(client, ah, *(_product(client, ah, platform="lazada")))
    unlisted = _review(client, ah, *(_product(client, ah)))
    for rid in (listed["id"], unlisted["id"]):
        assert client.post(f"/api/v1/admin/reviews/{rid}/approve-earnings",
                           headers=mh).status_code == 200

    card, queue = numbers()
    assert card == queue == before_queue + 1   # the unlisted one has nothing to link to

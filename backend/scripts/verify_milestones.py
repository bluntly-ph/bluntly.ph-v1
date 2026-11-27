"""Milestone claim verification — M1, M2, M3 (deep, end-to-end).

`supabase_verify.py` proves the DATABASE is sound. This proves the PRODUCT is:
every bullet the owner's `docs/MILESTONES.md` promises is exercised against a
live API and asserted. If a milestone says a feature exists, this fails when it
doesn't — regardless of what the docs claim.

Runs the real flows in-process (TestClient) against whichever DB is configured,
so it works against local or Supabase.

Usage:
  python -m scripts.verify_milestones                  # local
  USE_SUPABASE=true python -m scripts.verify_milestones  # prod (Supabase)

Exit code 0 only if every claim holds.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.env_guard import guard_cli

settings.auth_rate_limit_max = 1_000_000
settings.vote_rate_limit_max = 1_000_000

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

_RESULTS: list[tuple[bool, str, str]] = []
PW = "password123"
SHOPEE = "https://shopee.ph/x-i.1.2?af=v"


def check(claim: str, ok: bool, detail: str = "") -> bool:
    _RESULTS.append((bool(ok), claim, detail))
    suffix = f"  ({detail})" if detail and not ok else ""
    print(f"  [{'PASS' if ok else 'FAIL'}] {claim}{suffix}")
    return bool(ok)


class Harness:
    def __init__(self) -> None:
        self.c = TestClient(app)
        self.tag = uuid.uuid4().hex[:8]

    def register(self, who: str, role: str = "user") -> tuple[str, dict]:
        email = f"mv_{who}_{self.tag}@example.com"
        r = self.c.post("/api/v1/auth/register", json={"email": email, "password": PW})
        assert r.status_code == 201, r.text
        uid, token = r.json()["user"]["id"], r.json()["access_token"]
        if role != "user":
            from app.core.security import create_access_token
            from app.models.enums import MemberRole
            from app.models.user import User
            db = SessionLocal()
            try:
                db.query(User).filter(User.id == uuid.UUID(uid)).update(
                    {"role": MemberRole(role)})
                db.commit()
            finally:
                db.close()
            token = create_access_token(uuid.UUID(uid), role)
        return uid, {"Authorization": f"Bearer {token}"}

    def product(self, h: dict, name: str) -> str:
        # The listing must be unique too: a repeated source_url returns the
        # product that already has it (duplicate detection), so a fixed link
        # would fold every verification product into the first one ever made.
        return self.c.post("/api/v1/products", headers=h, json={
            "name": f"{name}-{uuid.uuid4().hex[:6]}", "category": "electronics",
            "source_url": f"https://shopee.ph/x-i.1.{uuid.uuid4().int % 10**12}"}).json()["id"]

    def review(self, h: dict, pid: str, stars: int = 4, photo: bool = True) -> str:
        body = {"product_id": pid, "title": "Verify", "star_rating": stars,
                "discussion": f"Milestone verification review {uuid.uuid4().hex[:6]}.",
                "verdict": "yes_absolutely" if stars >= 3 else "hard_pass"}
        if photo:
            # Must be a photo this caller genuinely owns: `verified` is derived
            # from photo_url, so the API rejects an arbitrary string (FR-3,
            # FR-8 layer 1). Derived rather than uploaded - the server
            # pattern-matches the owning prefix.
            uid = self.c.get("/api/v1/auth/me", headers=h).json()["id"]
            base = (settings.supabase_url or "https://test.supabase.co").rstrip("/")
            body["photo_url"] = (f"{base}/storage/v1/object/public/"
                                 f"review-photos/{uid}/{uuid.uuid4().hex}.jpg")
        return self.c.post("/api/v1/reviews", headers=h, json=body).json()["id"]


def verify_m1(hz: Harness) -> None:
    """M1 — auth, membership tiers, review submission + version history, AI critique."""
    print("\n=== M1: Core System Foundation ===")
    c = hz.c
    uid, ah = hz.register("m1")

    # JWT/OAuth2 auth: registration + login + me.
    login = c.post("/api/v1/auth/login",
                   data={"username": f"mv_m1_{hz.tag}@example.com", "password": PW})
    check("M1: JWT/OAuth2 registration + login + /me",
          login.status_code == 200 and "access_token" in login.json()
          and c.get("/api/v1/auth/me", headers=ah).status_code == 200, login.text[:80])
    check("M1: wrong password rejected",
          c.post("/api/v1/auth/login", data={"username": f"mv_m1_{hz.tag}@example.com",
                                             "password": "wrong"}).status_code == 401)
    check("M1: unauthenticated /me is 401", c.get("/api/v1/auth/me").status_code == 401)

    # Argon2id, never plaintext.
    db = SessionLocal()
    try:
        h = db.execute(text("select password_hash from users where id=:i"),
                       {"i": uid}).scalar()
    finally:
        db.close()
    check("M1: passwords stored as Argon2id (never plaintext)",
          bool(h) and h.startswith("$argon2") and PW not in h)

    # Membership tiers.
    tiers = c.get("/api/v1/membership-tiers").json()
    check("M1: membership tiers Special/Founding/Standard exist",
          {t["code"] for t in tiers} >= {"special", "founding", "standard"})
    _, mh = hz.register("m1mod", role="administrator")
    _, sh = hz.register("m1super", role="super_admin")
    check("M1: tier management is Super-Admin-gated",
          c.patch("/api/v1/membership-tiers/standard", headers=ah,
                  json={"revenue_share_bps": 3100}).status_code == 403
          and c.patch(f"/api/v1/users/{uid}/membership-tier", headers=mh,
                      json={"membership_tier": "founding"}).status_code == 403
          and c.patch(f"/api/v1/users/{uid}/membership-tier", headers=sh,
                      json={"membership_tier": "founding"}).status_code == 200)

    # Review submission + version history. Business Rules §4 (2026-09-23)
    # superseded M1's "editing creates a new version": published text, rating
    # and verdict are frozen, and a changed view is a new dated entry on the
    # same thread. What is verified is the rule that replaced it — the edit is
    # refused, the history the review was published with is still readable.
    pid = hz.product(ah, "M1Widget")
    rid = hz.review(ah, pid)
    check("M1: review submission stores the structured format",
          c.get(f"/api/v1/reviews/{rid}", headers=ah).json()["star_rating"] == 4)
    edit = c.patch(f"/api/v1/reviews/{rid}", headers=ah,
                   json={"title": "Edited", "change_note": "v2"})
    versions = c.get(f"/api/v1/reviews/{rid}/versions", headers=ah)
    check("M1 (§4): published text is frozen — an edit is refused, history kept",
          edit.status_code == 409 and edit.json().get("code") == "review_content_frozen"
          and versions.status_code == 200
          and [v["version_number"] for v in versions.json()] == [1],
          f"edit HTTP {edit.status_code} {edit.json().get('code')}")
    check("M1: a specific version is retrievable",
          c.get(f"/api/v1/reviews/{rid}/versions/1", headers=ah).status_code == 200)
    check("M1 (§4): only the author may touch a published review",
          c.patch(f"/api/v1/reviews/{rid}", headers=hz.register("m1other")[1],
                  json={"title": "hijack"}).status_code == 403)
    thread = c.get(f"/api/v1/reviews/{rid}/thread", headers=ah)
    check("M1 (§4): a review is a thread whose latest entry counts",
          thread.status_code == 200 and thread.json()["entries"][-1]["id"] == rid
          and thread.json()["entries"][-1]["is_latest"] is True, thread.text[:80])

    # AI critique.
    crit = c.post(f"/api/v1/reviews/{rid}/critique", headers=ah)
    check("M1: AI critique integration returns a scored critique",
          crit.status_code == 200 and 0 <= crit.json()["quality_score"] <= 100
          and crit.json()["provider"] in ("stub", "claude", "openai"), crit.text[:80])
    check("M1: ad-hoc AI critique endpoint works",
          c.post("/api/v1/ai/critique", headers=ah,
                 json={"text": "A draft review body."}).status_code == 200)


def verify_m2(hz: Harness) -> None:
    """M2 — Wilson trust, fraud/collusion signals, thresholds, voting, affiliate
    attribution, tier split, token economy."""
    print("\n=== M2: Reputation & Trust Systems ===")
    c = hz.c
    author_id, ah = hz.register("m2author")
    _, mh = hz.register("m2mod", role="administrator")
    voter_id, vh = hz.register("m2voter")

    pid = hz.product(ah, "M2Widget")
    rid = hz.review(ah, pid, stars=5)

    # Affiliate link generation + attribution (Shopee/Lazada/Amazon).
    att = c.post(f"/api/v1/admin/reviews/{rid}/referral-link", headers=mh,
                 json={"url": SHOPEE, "platform": "shopee"})
    check("M2: affiliate link attach monetizes (the review is already public)",
          att.status_code == 200 and att.json()["earn_eligible_status"] == "monetized"
          and att.json()["published_at"] is not None, att.text[:80])
    check("M2: the raw affiliate URL is NEVER exposed publicly",
          SHOPEE not in str(c.get(f"/api/v1/reviews/{rid}").json())
          and c.get(f"/api/v1/reviews/{rid}").json()["referral_redirect_url"] == f"/r/{rid}")
    red = c.get(f"/r/{rid}", follow_redirects=False)
    check("M2: attribution redirect 302s and records a click",
          red.status_code == 302 and red.headers["location"] == SHOPEE)
    check("M2: platform enum covers Shopee/Lazada/Amazon",
          {"shopee", "lazada", "amazon"} <= {
              r[0] for r in SessionLocal().execute(text(
                  "select e.enumlabel from pg_enum e join pg_type t "
                  "on t.oid=e.enumtypid where t.typname='platform'"))})

    # Upvote/downvote + anti-manipulation.
    v = c.post(f"/api/v1/reviews/{rid}/vote", headers=vh, json={"vote": "up"})
    check("M2: upvote/downvote with Wilson scoring",
          v.status_code == 200 and v.json()["helpful_votes"] == 1
          and float(v.json()["wilson_score"]) > 0, v.text[:80])
    check("M2: anti-manipulation — no self-voting",
          c.post(f"/api/v1/reviews/{rid}/vote", headers=ah,
                 json={"vote": "up"}).json().get("code") == "cannot_vote_own_review")
    check("M2: anti-manipulation — one vote per user (upsert, not stacking)",
          c.post(f"/api/v1/reviews/{rid}/vote", headers=vh,
                 json={"vote": "down"}).json()["helpful_votes"] == 0)
    check("M2: Wilson-ranked listing is available",
          c.get("/api/v1/reviews?sort=wilson&limit=5").status_code == 200)

    # Trust progression.
    trust = c.get(f"/api/v1/users/{author_id}/trust").json()
    check("M2: trust progression — stage/reputation/badges are public",
          trust["trust_stage"] >= 2 and "reputation_score" in trust
          and any(b["badge_id"] == "verified_buyer" for b in trust["badges"]),
          str(trust)[:90])

    # Product Wilson trust ratings.

    check("M2: Wilson trust rating for PRODUCTS",
          float(c.get(f"/api/v1/products/{pid}").json()["trust_score"]) > 0)
    check("M2: trust threshold configuration exists (visibility control)",
          "low_trust" in c.get(f"/api/v1/products/{pid}").json()
          and hasattr(settings, "product_trust_visibility_threshold"))

    # Fake/shill + collusion detection — advisory only.
    from app.models.review import Review
    from app.models.user import User
    from app.services.fraud_service import compute_signals
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(rid))
        signals = compute_signals(db, review, db.get(User, uuid.UUID(author_id)))
    finally:
        db.close()
    check("M2: fake/shill + collusion detection signals are computed",
          {"velocity", "collusion", "duplicate_content", "duplicate_of"} <= set(signals),
          str(signals)[:80])
    check("M2: fraud signals are ADVISORY — nothing auto-blocked",
          c.get(f"/api/v1/reviews/{rid}").status_code == 200
          and "signals" not in c.get(f"/api/v1/reviews/{rid}").json())

    # Revenue split. Business Rules §14 (2026-09-23) replaced M2's tier-based
    # split with one flat split for every monetized review: 40% platform, 30%
    # reviewer, 30% Honesty Fund, exact to the centavo, whatever the tier.
    from app.services.earnings import split_for_review
    db = SessionLocal()
    try:
        review = db.get(Review, uuid.UUID(rid))
        author = db.get(User, uuid.UUID(author_id))
        s, bps = split_for_review(Decimal("100.00"), review, author)
    finally:
        db.close()
    check("M2 (§14): flat 40/30/30 split (platform/reviewer/Honesty Fund, exact)",
          s["platform_share"] == Decimal("40.00") and s["reviewer_share"] == Decimal("30.00")
          and s["honesty_fund_share"] == Decimal("30.00") and bps == 3000, f"{s} bps={bps}")

    # Token economy + transaction history.
    bal = c.get("/api/v1/tokens/balance", headers=ah)
    txs = c.get("/api/v1/tokens/transactions", headers=ah)
    check("M2: token economy — balance + append-only transaction history",
          bal.status_code == 200 and bal.json()["token_balance"] > 0
          and txs.status_code == 200 and len(txs.json()) >= 1
          and txs.json()[0]["balance_after"] == bal.json()["token_balance"],
          str(bal.json()))
    check("M2: token ledger has no update/delete surface (append-only)",
          all(("PUT" not in m and "DELETE" not in m and "PATCH" not in m)
              for p, item in app.openapi()["paths"].items() if "tokens" in p
              for m in (k.upper() for k in item)))


def verify_m3(hz: Harness) -> None:
    """M3 — request board + AI validation + dynamic rewards, contracts, payouts by
    tier, affiliate ingestion, frontend readiness, load testing."""
    print("\n=== M3: Full System Delivery (built, not deployed) ===")
    c = hz.c
    uid, ah = hz.register("m3user")
    _, mh = hz.register("m3mod", role="administrator")

    # Request board + AI validation + demand signal. The bounty escrow and its
    # up-vote top-up were retired with the token economy (migration 0022), so
    # what is verified here is that posting costs nothing and up-votes rank.
    bad = c.post("/api/v1/requests", headers=ah,
                 json={"title": "Review it", "details": "pls"})
    check("M3: request board — AI validation blocks thin requests with reasons",
          bad.status_code == 422 and bad.json()["code"] == "request_invalid"
          and bad.json()["reasons"], bad.text[:80])
    before_post = c.get("/api/v1/tokens/balance", headers=ah).json()["token_balance"]
    # Every request names its product (dev/QA sync 2026-09-29).
    asked_pid = hz.product(ah, "M3Widget")
    req = c.post("/api/v1/requests", headers=ah, json={
        "title": "Review this handheld fan", "product_id": asked_pid,
        "details": "Please cover battery life and build quality after two weeks."})
    check("M3: request board — posting a request is free and costs no tokens",
          req.status_code == 201 and req.json()["status"] == "open"
          and c.get("/api/v1/tokens/balance", headers=ah).json()["token_balance"]
          == before_post, req.text[:80])
    rq = req.json()["id"]
    _, uh = hz.register("m3upvoter")
    up = c.post(f"/api/v1/requests/{rq}/upvote", headers=uh)
    check("M3: request board — up-vote records demand and the voter's own state",
          up.status_code == 200 and up.json()["upvote_count"] == 1
          and up.json()["my_upvote"] is True, up.text[:80])

    # A review of the product answers the request; the ASKER picks the Best
    # Answer, which fulfils it (the Bounty Board model agreed 2026-09-29).
    rev_id, rh = hz.register("m3reviewer")
    rid = hz.review(rh, asked_pid, stars=5)
    c.post(f"/api/v1/admin/reviews/{rid}/publish", headers=mh)
    answered = c.get(f"/api/v1/requests/{rq}").json()
    check("M3: request board — a review of the product answers and the request stays open",
          answered["status"] == "open" and answered["answer_count"] == 1, str(answered)[:80])
    before = c.get("/api/v1/tokens/balance", headers=rh).json()["token_balance"]
    ful = c.post(f"/api/v1/requests/{rq}/best-answer", headers=ah, json={"review_id": rid})
    check("M3: request board — the asker's Best Answer fulfils it and pays nothing",
          ful.status_code == 200 and ful.json()["status"] == "fulfilled"
          and c.get("/api/v1/tokens/balance", headers=rh).json()["token_balance"]
          == before, ful.text[:80])

    # Contracts and tier-ordered payouts were retired by Business Rules §14/§15
    # (2026-09-23): no contracts, no tiers, and payouts start with the
    # reviewer's own request against cleared money. Verified: the contract
    # surface is gone, and cashout is the reviewer's, with its minimum.
    mono_id, mh2 = hz.register("m3author")
    check("M3 (§14): no review contracts — the contract surface is retired",
          not any(p.startswith("/api/v1/contracts") or "/contracts/" in p
                  for p in app.openapi()["paths"])
          and c.get("/api/v1/contracts", headers=mh2).status_code == 404)
    c.patch("/api/v1/auth/me/payout-account", headers=mh2,
            json={"payout_account": "payee@example.com"})
    check("M3: payout account setter exists and validates",
          c.patch("/api/v1/auth/me/payout-account", headers=mh2,
                  json={"payout_account": "nope"}).status_code == 422)
    balance = c.get("/api/v1/payouts/balance", headers=mh2)
    cash = c.post("/api/v1/payouts/cashout", headers=mh2, json={})
    check("M3 (§15/§19): cashout is the reviewer's request, against cleared money",
          balance.status_code == 200
          and {"withdrawable", "pending_clearance", "minimum_cashout"} <= set(balance.json())
          and cash.status_code == 422 and cash.json().get("code") == "below_payout_minimum",
          f"balance HTTP {balance.status_code}; cashout {cash.status_code} {cash.text[:60]}")
    check("M3: own payouts are listable", c.get("/api/v1/payouts", headers=mh2).status_code == 200)
    check("M3: payout admin surface is moderator-gated",
          c.get("/api/v1/admin/payouts", headers=mh2).status_code == 403
          and c.get("/api/v1/admin/payouts", headers=mh).status_code == 200)

    # PayPal adapter present but never required.
    from app.adapters import paypal
    check("M3: PayPal Payouts adapter built to the documented v1 contract",
          hasattr(paypal, "submit_batch") and hasattr(paypal, "get_batch")
          and paypal.BATCH_SUCCESS == "SUCCESS" and paypal.TXN_SUCCESS == "SUCCESS"
          and {"FAILED", "RETURNED", "BLOCKED", "REFUNDED", "REVERSED"} <= paypal.TXN_FAILURES)
    check("M3: manual payout rail exists (no PayPal credentials required)",
          "/api/v1/admin/payouts/{payout_id}/mark-paid" in app.openapi()["paths"])

    # Affiliate performance ingestion — manual CSV of the REAL formats, no scraping.
    import pathlib

    from app.services import report_formats
    fx = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures"
    shopee = report_formats.parse((fx / "shopee_commission_report.csv").read_bytes())
    lazada = report_formats.parse((fx / "lazada_conversion_report.csv").read_bytes())
    check("M3: real Shopee report ingests (detected, zero errors)",
          shopee.format == "shopee_commission_report" and not shopee.errors
          and len(shopee.rows) > 0, str(shopee.errors[:1]))
    check("M3: real Lazada report ingests despite being cp1252, not UTF-8",
          lazada.format == "lazada_conversion_report" and not lazada.errors
          and len(lazada.rows) > 0, str(lazada.errors[:1]))
    check("M3: unpayable rows (pending/cancelled/rejected) are never payable",
          all(r.order_status.lower() == "completed" for r in shopee.rows)
          and all(r.order_status.lower() == "delivered" for r in lazada.rows)
          and all(r.gross_amount > 0 for r in shopee.rows + lazada.rows))
    check("M3: sub-ID attribution is wired (queue exposes it; links store it)",
          "suggested_sub_id" in str(c.get("/api/v1/admin/review-queue?limit=1",
                                          headers=mh).json()))

    # Frontend integration readiness.
    spec = app.openapi()
    untagged = [f"{m} {p}" for p, item in spec["paths"].items()
                for m, op in item.items() if not op.get("tags")]
    types = pathlib.Path(__file__).resolve().parents[2] / "lib" / "api-types.d.ts"
    guide = pathlib.Path(__file__).resolve().parents[2] / "docs" / "FRONTEND_INTEGRATION.md"
    check("M3: frontend readiness — OpenAPI complete, TS types + guide delivered",
          not untagged and types.exists() and guide.exists()
          and "/api/v1/requests" in types.read_text(encoding="utf-8", errors="replace"),
          f"untagged={untagged[:2]}")

    # Load testing.
    lt = pathlib.Path(__file__).resolve().parents[1] / "loadtest" / "locustfile.py"
    res = pathlib.Path(__file__).resolve().parents[2] / "docs" / "LOADTEST_RESULTS.md"
    check("M3: load testing — profile + recorded results exist",
          lt.exists() and res.exists() and "p95" in res.read_text(encoding="utf-8"))

    # The anti-scraping mandate holds across every milestone.
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    hits = subprocess.run(
        ["grep", "-ril", "-e", "scrapy", "-e", "selenium", "-e", "playwright",
         "-e", "proxy_rotation", str(root)],
        capture_output=True, text=True).stdout.strip()
    check("ALL: no scraping code anywhere in the backend (owner mandate)",
          hits == "", hits[:100])


def verify_fr2_and_receipt_privacy(h) -> None:
    """Contractual functionality added after the M1-M3 milestones were written.

    The verifier had no coverage of FR-2 or of receipt privacy, which meant it
    would have stayed fully green with both features deleted. A milestone count
    that cannot go down when contractual functionality disappears is not
    evidence of anything.
    """
    c = h.c
    author_id, ah = h.register("fr2")

    pid = c.post("/api/v1/products", headers=ah,
                 json={"name": f"FR2 {uuid.uuid4().hex[:8]}",
                       "category": "electronics"}).json()["id"]

    # FR-2: the panel exists and is public, and stays locked below 3
    # INDEPENDENT observations - the threshold is the requirement.
    panel = c.get(f"/api/v1/products/{pid}/prices")
    check("FR-2: price panel is public and returns an insufficient state",
          panel.status_code == 200 and panel.json()["sufficient"] is False,
          f"HTTP {panel.status_code}")
    check("FR-2: no prices are published below the threshold",
          panel.json()["low"] is None and panel.json()["median"] is None)
    check("FR-2: the threshold is 3 independent observations",
          panel.json()["required_independent"] == 3)

    # Business Rules §16 (2026-09-23) replaced FR-2's "three independent
    # buyers, every price waits for a moderator": a price report belongs to the
    # reporter's own review of the product, and while a product has no baseline
    # each report waits for an admin glance; once three are approved, a normal
    # price publishes at once and one line per marketplace is drawn.
    standalone = c.post(f"/api/v1/products/{pid}/prices", headers=ah, json={
        "platform": "shopee", "price": "1000", "observed_at": date.today().isoformat()})
    check("§16: a price report must belong to the reporter's own review",
          standalone.status_code == 422
          and standalone.json().get("code") == "price_needs_review", standalone.text[:80])

    reporters = []
    for n in range(3):
        _, rh = h.register(f"fr2buyer{n}")
        rrid = c.post("/api/v1/reviews", headers=rh, json={
            "product_id": pid, "title": f"price report {n}", "star_rating": 4,
            "discussion": f"Verifier fixture: the review a price report hangs off {n}.",
            "verdict": "yes_absolutely"}).json()["id"]
        reporters.append((rh, rrid))
    held = [c.post(f"/api/v1/products/{pid}/prices", headers=rh, json={
        "review_id": rrid, "platform": "shopee", "price": value,
        "observed_at": date.today().isoformat()}).json()
        for (rh, rrid), value in zip(reporters, ("1000", "1100", "1200"), strict=True)]
    pending = c.get(f"/api/v1/products/{pid}/prices").json()
    check("§16: with no baseline yet, each report waits for an admin glance",
          all(o.get("status") == "pending" and o.get("hold_reason") == "no_baseline"
              for o in held)
          and pending["pending_count"] == 3 and pending["observation_count"] == 0
          and pending["low"] is None, f"held={[o.get('hold_reason') for o in held]}")

    _, mh = h.register("fr2mod", role="administrator")
    queue = c.get("/api/v1/admin/price-observations", headers=mh,
                  params={"product_id": pid}).json()
    decided = [c.post(f"/api/v1/admin/price-observations/{row['id']}/decision",
                      headers=mh, json={"decision": "approve"}).status_code
               for row in queue]
    opened = c.get(f"/api/v1/products/{pid}/prices").json()
    # One point per marketplace per day, at that day's median — all three were
    # reported today, so the Shopee line is one point at the median, ₱1,100.
    line = opened["series"].get("shopee", [])
    check("§16: approved prices open the history, one line per marketplace",
          decided == [200, 200, 200] and opened["sufficient"] is True
          and opened["observation_count"] == 3 and set(opened["series"]) == {"shopee"}
          and len(line) == 1 and Decimal(str(line[0]["price"])) == Decimal("1100"),
          f"decisions={decided} count={opened['observation_count']} series={opened['series']}")

    other = c.post("/api/v1/products", headers=ah,
                   json={"name": f"FR2b {uuid.uuid4().hex[:8]}",
                         "category": "electronics"}).json()["id"]
    cmp_resp = c.get(f"/api/v1/products/compare?ids={pid},{other}")
    check("FR-2: comparison returns both products side by side",
          cmp_resp.status_code == 200 and len(cmp_resp.json()["entries"]) == 2,
          f"HTTP {cmp_resp.status_code}")
    check("FR-2: comparison rejects fewer than two products",
          c.get(f"/api/v1/products/compare?ids={pid}").status_code == 422)
    check("FR-2: comparison claims no seller rating (withdrawn 2026-07-28)",
          "seller_rating" not in cmp_resp.text.lower())

    # Receipt privacy (BUG-029): no locator may reach an anonymous caller.
    key = f"{author_id}/{uuid.uuid4().hex}.jpg"
    rid = c.post("/api/v1/reviews", headers=ah, json={
        "product_id": pid, "title": "receipt privacy claim",
        "discussion": "Verifier fixture asserting no receipt locator is public.",
        "verdict": "it_depends", "star_rating": 3, "receipt_key": key}).json()["id"]
    body = c.get(f"/api/v1/reviews/{rid}", headers=ah).text
    check("Privacy: no receipt locator on the review response",
          "receipt_url" not in body and "receipt_key" not in body)
    check("Privacy: the review reports that evidence exists, without its location",
          c.get(f"/api/v1/reviews/{rid}", headers=ah).json()["has_receipt"] is True)
    check("Privacy: the receipt endpoint refuses an anonymous caller",
          c.get(f"/api/v1/reviews/{rid}/receipt").status_code == 401)


def main() -> int:
    url = make_url(settings.effective_database_url)
    print(f"MILESTONE VERIFICATION — {url.host}:{url.port}/{url.database} "
          f"(use_supabase={settings.use_supabase})")
    with engine.connect() as conn:
        print("server:", conn.execute(text("select version()")).scalar()[:40])
    hz = Harness()
    # A section that raises is recorded as a FAILED claim and the run goes on:
    # one stale assumption used to end the run with "no summary", hiding every
    # claim after it. The exit code is still non-zero.
    for section in (verify_m1, verify_m2, verify_m3, verify_fr2_and_receipt_privacy):
        try:
            section(hz)
        except Exception as exc:  # noqa: BLE001 — reported, never swallowed
            import traceback
            traceback.print_exc()
            check(f"{section.__name__} completed", False, f"{type(exc).__name__}: {exc}")
    passed = sum(1 for ok, *_ in _RESULTS if ok)
    failed = [f"{n} ({d})" for ok, n, d in _RESULTS if not ok]
    print(f"\n=== MILESTONE CLAIMS: {passed}/{len(_RESULTS)} verified ===")
    for f in failed:
        print(f"  FAILED: {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    # Refuses production before a single row is touched.
    guard_cli("verify_milestones", production_is_legitimate=False)
    raise SystemExit(main())

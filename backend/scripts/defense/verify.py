"""Is the defense environment ready? Exit 0 only if every essential check passes.

    python -m scripts.defense.verify [--site https://<preview-or-local>] [--json out.json]

Read-only. Checks, in order:
  environment  the target is TEST (or local) and the schema is at the code's head
  personas     the six accounts exist with the right role, stage and flags
  catalogue    products, images, listings, stores, the pending submissions
  content      every review, Q&A and store-review state the walkthrough uses
  moderation   the queues a moderator opens are populated
  money        cleared, pending, below/above the ₱300 threshold, paid and requested
  prices       Shopee-only, Lazada-only, both, and a held outlier
  integrity    no orphaned or impossible relationships
  sweep        no gibberish, fixture or debug text anywhere a visitor can read
  routes       the API answers for the pages the walkthrough opens (and, with
               --site, the pages themselves)

On a local database there is no storage, so missing product images are a
warning there and a failure on TEST.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field

from sqlalchemy import text

from scripts.defense import dataset as D
from scripts.defense.guard import require_defense_target


@dataclass
class Result:
    group: str
    name: str
    ok: bool
    detail: str = ""
    essential: bool = True


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def check(self, group: str, name: str, ok: bool, detail: str = "",
              essential: bool = True) -> bool:
        self.results.append(Result(group, name, bool(ok), detail, essential))
        return bool(ok)

    @property
    def failed(self) -> list[Result]:
        return [r for r in self.results if not r.ok and r.essential]


#: Words and shapes that should never reach a panel. Word-bounded, so "latest"
#: or "contest" never match "test"; `sweep_hits` returns each hit for a human.
GARBAGE = re.compile(
    r"\b(lorem|ipsum|asdf\w*|qwerty\w*|dummy|placeholder|sample\s+sample|test\d+|"
    r"testing\s*\d+|test\s+(review|comment|post|product|account|user|data|only|lang)|"
    r"foo|bar\d|xxx+|tbd|todo|fixme|e2e|tester|fixture|undefined|null|nan)\b"
    r"|^\s*test\s*$|(?P<ch>.)(?P=ch){5,}|@example\.(com|ph)",
    re.IGNORECASE)

#: (table, id column, text columns, filter) for everything a visitor can read.
VISIBLE_TEXT = (
    ("reviews", "id", ("title", "discussion", "verdict_explanation", "target_audience",
                       "anti_target_audience"), "published_at IS NOT NULL"),
    ("review_comments", "id", ("body",), "TRUE"),
    ("questions", "id", ("body",), "TRUE"),
    ("answers", "id", ("body",), "TRUE"),
    ("seller_reviews", "id", ("title", "comment", "seller_response"), "TRUE"),
    ("products", "id", ("canonical_name", "brand"), "status = 'canonicalized'"),
    ("sellers", "id", ("display_name",), "TRUE"),
    ("users", "id", ("display_name", "username"), "TRUE"),
    ("review_requests", "id", ("title", "details"), "TRUE"),
)


def sweep_hits(db) -> list[dict]:
    hits = []
    for table, key, columns, where in VISIBLE_TEXT:
        for column in columns:
            rows = db.execute(text(
                f"SELECT {key}::text, {column} FROM {table} "
                f"WHERE {where} AND {column} IS NOT NULL")).all()
            for row_id, value in rows:
                match = GARBAGE.search(str(value))
                if match:
                    hits.append({"table": table, "id": row_id, "field": column,
                                 "match": match.group(0), "text": str(value)[:120]})
    # Pros and cons are JSON lists.
    for row_id, item in db.execute(text(
            "SELECT r.id::text, x FROM reviews r, jsonb_array_elements_text("
            "coalesce(r.pros, '[]'::jsonb) || coalesce(r.cons, '[]'::jsonb)) x "
            "WHERE r.published_at IS NOT NULL")).all():
        match = GARBAGE.search(str(item))
        if match:
            hits.append({"table": "reviews", "id": row_id, "field": "pros/cons",
                         "match": match.group(0), "text": str(item)[:120]})
    return hits


def scalar(db, sql: str, **params):
    return db.execute(text(sql), params).scalar()


def count(db, table: str, where: str, **params) -> int:
    return int(scalar(db, f"SELECT count(*) FROM {table} WHERE {where}", **params) or 0)


#: The scenarios the 2026-09-29 dev/QA sync asked to have ready for the
#: panel, each as the SQL that proves it exists in the database the site reads.
#: Scenario data proves a scenario can be SHOWN; it is not independent QA.
_ANSWERS = """
    SELECT count(*) FROM reviews rv
     WHERE rv.product_id = rr.product_id AND rv.published_at IS NOT NULL
       AND rv.is_removed = false AND (rv.thread_id IS NULL OR rv.thread_id = rv.id)
       AND rv.author_id <> rr.requester_id AND rv.created_at >= rr.created_at"""

SCENARIOS: tuple[tuple[str, str], ...] = (
    ("a member's report, open in the queue",
     "SELECT count(*) FROM moderation_logs WHERE action = 'report' AND resolution IS NULL "
     "AND report_source = 'user_reported'"),
    ("a system-detected copied review, with the matched review stored",
     "SELECT count(*) FROM moderation_logs WHERE action = 'report' AND resolution IS NULL "
     "AND report_source = 'system_detected' AND context->>'signal' = 'duplicate_content' "
     "AND context->'evidence'->>'duplicate_of' IS NOT NULL"),
    ("a system-detected vote collusion, with the reciprocal up-voters stored",
     "SELECT count(*) FROM moderation_logs WHERE action = 'report' AND resolution IS NULL "
     "AND report_source = 'system_detected' AND context->>'signal' = 'collusion' "
     "AND (context->'evidence'->>'reciprocal_upvoters')::int > 0"),
    ("a vote-concentration hold on a member, with its cohort facts",
     "SELECT count(*) FROM moderation_logs WHERE action = 'report' "
     "AND report_source = 'system_detected' AND context->>'signal' = 'vote_concentration' "
     "AND context ? 'cohort_share'"),
    ("an escalated report (left the queue, on the Overview)",
     "SELECT count(*) FROM moderation_logs WHERE action = 'report' "
     "AND resolution = 'escalated'"),
    ("a dismissed report",
     "SELECT count(*) FROM moderation_logs WHERE action = 'report' AND resolution = 'dismissed'"),
    ("a review waiting in the earnings queue (priority tier and its reasons)",
     "SELECT count(*) FROM reviews WHERE earn_eligible_status = 'pending' "
     "AND published_at IS NOT NULL AND is_removed = false"),
    ("Bounty Board: an open request nobody has answered yet",
     f"SELECT count(*) FROM review_requests rr WHERE rr.status = 'open' "
     f"AND rr.product_id IS NOT NULL AND ({_ANSWERS}) = 0"),
    ("Bounty Board: an open request with several answers, waiting for its asker",
     f"SELECT count(*) FROM review_requests rr WHERE rr.status = 'open' "
     f"AND ({_ANSWERS}) >= 2"),
    ("Bounty Board: a request with the asker's Best Answer, still on its own page",
     "SELECT count(*) FROM review_requests rr JOIN reviews rv "
     "ON rv.id = rr.fulfilled_by_review_id WHERE rr.status = 'fulfilled' "
     "AND rv.product_id = rr.product_id AND rv.is_removed = false"),
    ("an asker told \"Someone answered your request\", linked to the request",
     "SELECT count(*) FROM notifications WHERE kind = 'request_answered' "
     "AND link LIKE '/requests/%'"),
    ("a PayPal-sandbox payout (no real money)",
     "SELECT count(*) FROM payouts WHERE provider_ref LIKE 'PAYPAL-SANDBOX-%'"),
)


def run_scenarios(rep: Report, db) -> None:
    for name, sql in SCENARIOS:
        n = scalar(db, sql) or 0
        rep.check("defense scenarios (dev/QA sync 2026-09-29)", name, n > 0, f"{n}")


def run(kind: str, site: str | None) -> Report:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.db.session import SessionLocal

    rep = Report()
    db = SessionLocal()
    try:
        # ------------------------------------------------ environment
        rep.check("environment", "target is TEST or local", kind in ("test", "local"), kind)
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        current = scalar(db, "SELECT version_num FROM alembic_version")
        rep.check("environment", "schema at the code's migration head", current == head,
                  f"{current} (head {head})")

        # ------------------------------------------------ personas
        users = {row.username: row for row in db.execute(text(
            "SELECT username, role::text AS role, trust_stage, is_claimed_seller, "
            "is_under_investigation, created_at, id FROM users "
            "WHERE username = ANY(:u)"), {"u": [p.username for p in D.PEOPLE.values()]})}
        for p in D.PERSONAS:
            rep.check("personas", f"{p.key} ({p.username}) exists", p.username in users)
        rep.check("personas", "all community accounts exist",
                  len(users) == len(D.PEOPLE), f"{len(users)}/{len(D.PEOPLE)}")
        get = users.get
        rep.check("personas", "moderator has the moderator role",
                  get("admin_joanna") and get("admin_joanna").role == "administrator")
        rep.check("personas", "Kristine reached Stage 3 on real evidence",
                  get("kristinev") and get("kristinev").trust_stage == 3,
                  str(get("kristinev") and get("kristinev").trust_stage))
        rep.check("personas", "Maria is an established Stage 2 reviewer",
                  get("mariareyes") and get("mariareyes").trust_stage == 2)
        rep.check("personas", "Paolo is a new Stage 1 account (<30 days)",
                  get("paolo_mendoza") and get("paolo_mendoza").trust_stage == 1
                  and scalar(db, "SELECT now() - created_at < interval '30 days' FROM users "
                                 "WHERE username = 'paolo_mendoza'"))
        rep.check("personas", "Rico is a claimed seller (cannot vote or earn)",
                  get("rico_powerhub") and get("rico_powerhub").is_claimed_seller)
        rep.check("personas", "Jomar is under investigation",
                  get("jomar_deals") and get("jomar_deals").is_under_investigation)

        # ------------------------------------------------ catalogue
        products = db.execute(text(
            "SELECT canonical_name, status::text, category, image_url, review_count "
            "FROM products WHERE status = 'canonicalized'")).all()
        rep.check("catalogue", "all 15 featured products canonicalized",
                  len(products) >= len(D.PRODUCTS), str(len(products)))
        missing_images = [p.canonical_name for p in products if not p.image_url]
        rep.check("catalogue", "every featured product has an image", not missing_images,
                  f"{len(missing_images)} without" if missing_images else "",
                  essential=(kind == "test"))
        rep.check("catalogue", "every product has a category",
                  all(p.category for p in products))
        rep.check("catalogue", "every featured product has reviews",
                  all((p.review_count or 0) > 0 for p in products))
        rep.check("catalogue", "marketplace listings attached to products",
                  scalar(db, "SELECT count(DISTINCT product_id) FROM product_platforms "
                             "WHERE is_monetizable") >= 6)
        rep.check("catalogue", "two product submissions await a moderator",
                  count(db, "products", "status = 'pending'") >= 2)
        rep.check("catalogue", "search aliases present",
                  scalar(db, "SELECT count(*) FROM product_aliases") >= 20)
        rep.check("catalogue", "stores: one claimed, one claim pending, unclaimed ones",
                  count(db, "sellers", "claim_status::text = 'claimed'") >= 1
                  and count(db, "seller_claims", "status::text = 'pending'") >= 1
                  and count(db, "sellers", "claimed_by_id IS NULL") >= 2)

        # ------------------------------------------------ content
        pub = "published_at IS NOT NULL AND NOT is_removed"
        rep.check("content", "40+ published reviews",
                  scalar(db, f"SELECT count(*) FROM reviews WHERE {pub}") >= 40)
        for verdict in ("yes_absolutely", "it_depends", "hard_pass"):
            rep.check("content", f"verdict {verdict} present",
                      scalar(db, f"SELECT count(*) FROM reviews WHERE {pub} "
                                 "AND verdict::text = :v", v=verdict) >= 2)
        rep.check("content", "no 2.5-star 'it depends' review (owner's open rule)",
                  scalar(db, f"SELECT count(*) FROM reviews WHERE {pub} AND "
                             "verdict::text = 'it_depends' AND star_rating = 2.5") == 0)
        for status in ("monetized", "approved", "honesty_fund", "rejected", "pending", "none"):
            rep.check("content", f"earning state '{status}' present",
                      scalar(db, f"SELECT count(*) FROM reviews WHERE {pub} "
                                 "AND earn_eligible_status::text = :s", s=status) >= 1)
        rep.check("content", "verified and unverified reviews",
                  scalar(db, f"SELECT count(DISTINCT verification_status) FROM reviews "
                             f"WHERE {pub}") == 2)
        rep.check("content", "a review thread with an update",
                  scalar(db, "SELECT count(*) FROM reviews WHERE thread_id IS NOT NULL "
                             "AND thread_id <> id") >= 1)
        rep.check("content", "a heavily discussed review (8+ comments)",
                  scalar(db, "SELECT coalesce(max(n), 0) FROM (SELECT count(*) n "
                             "FROM review_comments GROUP BY review_id) t") >= 8)
        rep.check("content", "comment replies present",
                  count(db, "review_comments", "parent_id IS NOT NULL") >= 5)
        rep.check("content", "active affiliate links",
                  count(db, "referral_links", "status::text = 'active'") >= 5)
        rep.check("content", "questions: unanswered, answered, Best Answer, seller-directed",
                  scalar(db, "SELECT count(*) FROM questions q WHERE NOT EXISTS "
                             "(SELECT 1 FROM answers a WHERE a.question_id = q.id)") >= 1
                  and count(db, "questions", "best_answer_id IS NOT NULL") >= 3
                  and count(db, "questions", "seller_id IS NOT NULL") >= 2)
        rep.check("content", "store reviews with owner responses and a fake-review flag",
                  count(db, "seller_reviews", "seller_response IS NOT NULL") >= 2
                  and scalar(db, "SELECT count(*) FROM seller_review_appeals") >= 1)
        rep.check("content", "readers have opened reviews (dashboard views, momentum)",
                  count(db, "review_view_buckets", "bucket_start > now() - interval '7 days'") > 0
                  and count(db, "request_geo_buckets", "country = 'PH'") > 0)
        rep.check("content", "review requests with up-votes",
                  count(db, "review_requests", "upvote_count > 0") >= 2)

        # ------------------------------------------------ moderation
        open_reports = "action::text = 'report' AND resolution IS NULL"
        rep.check("moderation", "an urgent user report (personal information)",
                  scalar(db, f"SELECT count(*) FROM moderation_logs WHERE {open_reports} AND "
                             "reason::text = 'personal_information'") >= 1)
        rep.check("moderation", "a normal-priority user report",
                  count(db, "moderation_logs", f"{open_reports} AND reporter_id IS NOT NULL "
                        "AND reason::text <> 'personal_information'") >= 1)
        rep.check("moderation", "a system-detected report (vote concentration)",
                  scalar(db, f"SELECT count(*) FROM moderation_logs WHERE {open_reports} AND "
                             "report_source::text = 'system_detected'") >= 1)
        rep.check("moderation", "approved reviews awaiting an affiliate link",
                  scalar(db, "SELECT count(*) FROM reviews r WHERE r.published_at IS NOT NULL "
                             "AND NOT r.is_removed AND r.earn_eligible_status::text = 'approved' "
                             "AND NOT EXISTS (SELECT 1 FROM referral_links l WHERE l.review_id = "
                             "r.id AND l.status::text = 'active') AND EXISTS (SELECT 1 FROM "
                             "product_platforms pp WHERE pp.product_id = r.product_id AND "
                             "pp.is_monetizable)") >= 2)
        rep.check("moderation", "prices waiting for a moderator",
                  scalar(db, "SELECT count(*) FROM price_history WHERE status::text = "
                             "'pending'") >= 2)
        rep.check("moderation", "a seller claim waiting for a decision",
                  scalar(db, "SELECT count(*) FROM seller_claims WHERE status::text = "
                             "'pending'") >= 1)
        rep.check("moderation", "a resolved report in the history",
                  scalar(db, "SELECT count(*) FROM moderation_logs WHERE action::text = 'report' "
                             "AND resolution IS NOT NULL") >= 1)
        rep.check("moderation", "the activity log spans the site's history, not one morning",
                  scalar(db, "SELECT count(DISTINCT date(created_at)) FROM moderation_logs") >= 15)
        rep.check("moderation", "reviews waiting in the earnings queue",
                  scalar(db, "SELECT count(*) FROM reviews WHERE earn_eligible_status::text = "
                             "'pending'") >= 2)

        # ------------------------------------------------ money
        # payout_service.withdrawable: the wallet less what has not cleared (§15).
        cleared = {r.username: r.amount for r in db.execute(text(
            "SELECT u.username, u.wallet_balance - coalesce((SELECT sum(c.reviewer_share) "
            "FROM commissions c WHERE c.reviewer_id = u.id AND c.cleared_at IS NULL "
            "AND c.reviewer_share > 0), 0) AS amount FROM users u "
            "WHERE u.wallet_balance > 0"))}
        rep.check("money", "a reviewer can withdraw (cleared >= ₱300)",
                  any(v >= 300 for v in cleared.values()),
                  ", ".join(f"{k} {v}" for k, v in sorted(cleared.items())))
        rep.check("money", "a reviewer is below the ₱300 threshold",
                  any(0 < v < 300 for v in cleared.values()))
        # Overview "Below ₱300 threshold" (/admin/payouts/summary) reads the
        # same wallets the same way: claimed sellers aside, 0 < cleared < 300.
        from app.services import payout_service
        sellers = {r[0] for r in db.execute(text(
            "SELECT username FROM users WHERE is_claimed_seller"))}
        expected_below = sum(1 for k, v in cleared.items() if 0 < v < 300 and k not in sellers)
        got_below = payout_service.admin_summary(db)["below_minimum_count"]
        rep.check("money", "payout summary: members below the minimum",
                  got_below == expected_below >= 1, f"{got_below} vs {expected_below}")
        rep.check("money", "pending (uncleared) commissions",
                  count(db, "commissions", "cleared_at IS NULL") >= 1)
        rep.check("money", "a paid payout in the history",
                  count(db, "payouts", "status::text = 'paid'") >= 1)
        rep.check("money", "a requested payout waiting for the batch",
                  scalar(db, "SELECT count(*) FROM payouts WHERE status::text = "
                             "'scheduled'") >= 1)
        rep.check("money", "marketplace remittances recorded",
                  scalar(db, "SELECT count(*) FROM marketplace_remittances") >= 1)
        rep.check("money", "the Honesty Fund pool is accruing",
                  scalar(db, "SELECT coalesce(sum(honesty_fund_share), 0) FROM commissions") > 0)
        # The QA seed's windows (owner 2026-10-05): the Overview's affiliate
        # earnings equal the dataset's own totals - this 30 days and the 30
        # before - so a re-run or an import that doubled a row would show here.
        from app.services import overview_panels_service
        month = overview_panels_service.affiliate_earnings(db, "1M")
        rep.check("money", "Overview 1M verified = the dataset's last 30 days",
                  month.verified == D.money_in(0, 29, paid_only=True),
                  f"{month.verified} vs {D.money_in(0, 29, paid_only=True)}")
        rep.check("money", "Overview 1M previous = the dataset's 30 days before",
                  month.previous_verified == D.money_in(30, 59, paid_only=True),
                  f"{month.previous_verified} vs {D.money_in(30, 59, paid_only=True)}")
        rep.check("money", "every paid order is one commission (no duplicates)",
                  scalar(db, "SELECT count(*) FROM commissions")
                  == sum(1 for o in D.ORDERS if o.status == "completed"))
        rep.check("money", "no commission for an unpayable order",
                  scalar(db, "SELECT count(*) FROM commissions WHERE lower(coalesce("
                             "order_status, 'completed')) NOT IN ('completed', 'delivered')") == 0)

        # ------------------------------------------------ prices
        per = db.execute(text(
            "SELECT product_id, platform::text, count(*) FROM price_history "
            "WHERE status::text = 'approved' GROUP BY 1, 2")).all()
        platforms: dict = {}
        for product_id, platform, n in per:
            if n >= 2:  # a line needs two points; any approved price is plotted (§16)
                platforms.setdefault(product_id, set()).add(platform)
        rep.check("prices", "a Shopee-only price chart",
                  any(v == {"shopee"} for v in platforms.values()))
        rep.check("prices", "a Lazada-only price chart",
                  any(v == {"lazada"} for v in platforms.values()))
        rep.check("prices", "a chart with both marketplaces",
                  any(v == {"shopee", "lazada"} for v in platforms.values()))
        rep.check("prices", "an outlier held for a moderator's glance",
                  scalar(db, "SELECT count(*) FROM price_history WHERE status::text = 'pending' "
                             "AND hold_reason = 'outlier'") >= 1)

        # ------------------------------------------------ integrity
        checks = {
            "published reviews all have an author":
                "SELECT count(*) FROM reviews WHERE published_at IS NOT NULL AND author_id IS NULL "
                "AND NOT is_removed",
            "answers belong to a question":
                "SELECT count(*) FROM answers a LEFT JOIN questions q ON q.id = a.question_id "
                "WHERE q.id IS NULL",
            "every question is about a product or a store":
                "SELECT count(*) FROM questions WHERE product_id IS NULL AND seller_id IS NULL",
            "Best Answers belong to their question":
                "SELECT count(*) FROM questions q JOIN answers a ON a.id = q.best_answer_id "
                "WHERE a.question_id <> q.id",
            "commissions have a reviewer and a review":
                "SELECT count(*) FROM commissions WHERE reviewer_id IS NULL OR review_id IS NULL",
            "active links only on monetized reviews":
                "SELECT count(*) FROM referral_links l JOIN reviews r ON r.id = l.review_id "
                "WHERE l.status::text = 'active' AND r.earn_eligible_status::text <> 'monetized'",
            "claimed stores have an owner":
                "SELECT count(*) FROM sellers WHERE claim_status::text = 'claimed' "
                "AND claimed_by_id IS NULL",
            "no activity before an account existed":
                "SELECT count(*) FROM reviews r JOIN users u ON u.id = r.author_id "
                "WHERE r.created_at < u.created_at",
            "no votes before their review":
                "SELECT count(*) FROM review_votes v JOIN reviews r ON r.id = v.review_id "
                "WHERE v.created_at < r.created_at",
            "no comment before its review":
                "SELECT count(*) FROM review_comments c JOIN reviews r ON r.id = c.review_id "
                "WHERE c.parent_id IS NULL AND c.created_at < r.published_at",
            "no reply before the comment it answers":
                "SELECT count(*) FROM review_comments c JOIN review_comments p "
                "ON p.id = c.parent_id WHERE c.created_at < p.created_at",
            "no answer before its question":
                "SELECT count(*) FROM answers a JOIN questions q ON q.id = a.question_id "
                "WHERE a.created_at < q.created_at",
            "nothing dated in the future":
                "SELECT (SELECT count(*) FROM reviews WHERE created_at > now()) + "
                "(SELECT count(*) FROM review_comments WHERE created_at > now()) + "
                "(SELECT count(*) FROM answers WHERE created_at > now())",
            "no click through a link before the link existed":
                "SELECT count(*) FROM sessions s JOIN referral_links l "
                "ON l.review_id = s.review_id WHERE s.clicked_at < l.created_at",
            "no decision before the review it decides":
                "SELECT count(*) FROM moderation_logs m JOIN reviews r ON r.id = m.target_ref "
                "WHERE m.action IN ('approve', 'reject', 'affiliate_link_attach') "
                "AND m.created_at < r.published_at",
            "no negative wallet":
                "SELECT count(*) FROM users WHERE wallet_balance < 0",
            "prices are positive":
                "SELECT count(*) FROM price_history WHERE price <= 0",
        }
        for name, sql in checks.items():
            n = scalar(db, sql)
            rep.check("integrity", name, n == 0, f"{n} rows" if n else "")

        # ------------------------------------------------ sweep
        hits = sweep_hits(db)
        rep.check("sweep", "no gibberish, fixture or debug text visible", not hits,
                  "; ".join(f"{h['table']}.{h['field']} {h['id'][:8]} '{h['match']}'"
                            for h in hits[:8]))
        rep.hits = hits  # type: ignore[attr-defined]

        # ------------------------------------------------ scenarios
        run_scenarios(rep, db)
    finally:
        db.close()

    # ------------------------------------------------ routes
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    for path in ("/health", "/api/v1/reviews/feed?limit=20", "/api/v1/products?limit=50",
                 "/api/v1/products?q=power+bank", "/api/v1/sellers", "/api/v1/questions",
                 "/api/v1/requests", *(f"/api/v1/users/public/{p.username}"
                                       for p in D.PERSONAS)):
        r = c.get(path)
        rep.check("routes", f"GET {path}", r.status_code == 200, str(r.status_code))
    if site:
        base = site.rstrip("/")
        for path in ("/", "/feed", "/search?q=power+bank", "/questions", "/categories",
                     "/requests", "/how-it-works", "/membership", "/guidelines", "/login",
                     *(f"/u/{p.username}" for p in D.PERSONAS)):
            try:
                with urllib.request.urlopen(base + path, timeout=30) as resp:  # noqa: S310
                    status = resp.status
            except Exception as exc:  # noqa: BLE001 - reported as a failure
                status = str(exc)[:60]
            rep.check("routes", f"page {path}", status == 200, str(status))
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the defense environment is ready.")
    parser.add_argument("--site", default=None, help="also load these pages from a running site")
    parser.add_argument("--json", default=None, help="write the results as JSON here")
    parser.add_argument("--scenarios", action="store_true",
                        help="only check that every defense scenario exists (2026-09-29)")
    args = parser.parse_args(argv)
    kind = require_defense_target("verify")
    if args.scenarios:
        from app.db.session import SessionLocal
        rep = Report()
        db = SessionLocal()
        try:
            run_scenarios(rep, db)
        finally:
            db.close()
    else:
        rep = run(kind, args.site)
    group = None
    for r in rep.results:
        if r.group != group:
            group = r.group
            print(f"\n{group}")
        mark = "PASS" if r.ok else ("FAIL" if r.essential else "warn")
        print(f"  {mark}  {r.name}" + (f"  [{r.detail}]" if r.detail else ""))
    failed = rep.failed
    print(f"\n[defense] {len(rep.results) - len(failed)}/{len(rep.results)} checks passed"
          + (f"; {len(failed)} essential failure(s)" if failed else " - READY"))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"results": [r.__dict__ for r in rep.results],
                       "sweep_hits": getattr(rep, "hits", [])}, fh, indent=1, default=str)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

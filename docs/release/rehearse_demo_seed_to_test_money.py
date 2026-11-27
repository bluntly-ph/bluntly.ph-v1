"""Rehearse docs/release/DEMO_SEED_2026_10_TO_TEST_MONEY.sql on a fresh local DB.

Run from backend/ against a throwaway database (alembic upgrade head first):
  PYTHONPATH=. DATABASE_URL=postgresql+psycopg://.../rehearsal python ../docs/release/rehearse_demo_seed_to_test_money.py
The psycopg URL inside run() points at that same local database.

Rebuilds the production state the seed met (5 reviewers, @zienxt's two QA
credits + his ₱700 sandbox payout), runs the REAL seed SQL, the three demo-day
sandbox payouts, checks the report equals today's production figures, then runs
the conversion (twice), the rollback and the conversion again, checking every
rule of the QA sandbox design after each step.
"""
import re
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal as D
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.db.session import SessionLocal, engine
from app.main import app
from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import PayoutMethod, PayoutStatus
from app.models.payout import Payout
from app.models.user import User
from app.services import qa_sandbox_service
from app.services.reporting import financial, periods
from tests.conftest import register_and_token
from tests.test_priority_triage_api import _auth, _review

REPO = Path(__file__).resolve().parents[2]
SEED = (REPO / "docs/release/DEMO_SEED_2026_10.sql").read_text()
CONVERT = (REPO / "docs/release/DEMO_SEED_2026_10_TO_TEST_MONEY.sql").read_text()
ROLLBACK = (REPO / "docs/release/DEMO_SEED_2026_10_TO_TEST_MONEY_ROLLBACK.sql").read_text()

PROD = {
    "zienxt": "e9549322-2b5d-4f74-bcae-0c5998bff7a6",
    "zaisias": "e9b34162-ad41-47f1-8c4f-593af753b53a",
    "northpacificfan": "e4b60ac3-70cd-471f-852a-88a0bfe6d911",
    "suvango": "41b75551-964d-4957-83d4-7ff9b2b3bd14",
    "abelli": "3e86345c-23cf-4e7a-9111-a4ff2c5dd876",
}
PROD_REVIEWS = {  # review the seed / credits sit on
    "zienxt_capstone": "ae1d62d1-10bc-4064-97ed-88878e182178",
    "zienxt_budget": "edd1375f-8f43-44b4-9276-d464634e1ae3",
    "zaisias": "893c5ef1-fcca-4d63-aec6-46efe3a16cb7",
    "northpacificfan": "7f0a234b-91b0-4292-bdb9-f37c7bc056f8",
    "suvango": "7ece1a13-232a-4e65-b08a-501d4d966cad",
    "abelli": "ef4cbddb-4665-4654-8cae-921b33539f02",
}
PROD_CREDITS = {"capstone": "0abf02c1-1ad4-442d-b691-e5a04c4e705c",
                "budget": "9e79e63f-109f-4ad9-8039-f1bac9e15923"}


def ok(cond, what):
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        sys.exit(1)


client = TestClient(app)
ids, revs = {}, {}
_, admin_tok, _ = register_and_token(client, role="super_admin")
for name in PROD:
    uid, tok, _ = register_and_token(client)
    ids[name] = uid
    h = _auth(tok)
    if name == "zienxt":
        revs["zienxt_capstone"] = _review(client, h, "cap" + uuid.uuid4().hex[:6])
        revs["zienxt_budget"] = _review(client, h, "bud" + uuid.uuid4().hex[:6])
    else:
        revs[name] = _review(client, h, name[:4] + uuid.uuid4().hex[:6])

db = SessionLocal()
admin = db.scalar(select(User).where(User.role == "super_admin").order_by(User.created_at.desc()))
for name in PROD:
    u = db.get(User, uuid.UUID(ids[name]))
    u.payout_account = f"{name}@example.com"
db.commit()
# Pre-seed production: @zienxt is a tester with two QA credits, paid out ₱700 via sandbox.
qa_sandbox_service.add_tester(db, admin, ids_user := db.get(User, uuid.UUID(ids["zienxt"])).email)
db.commit()
credit_cap = qa_sandbox_service.credit(db, admin, uuid.UUID(revs["zienxt_capstone"]), D("350.00"))
credit_bud = qa_sandbox_service.credit(db, admin, uuid.UUID(revs["zienxt_budget"]), D("350.00"))
db.commit()
credits = {"capstone": str(credit_cap.id), "budget": str(credit_bud.id)}
z = db.get(User, uuid.UUID(ids["zienxt"]))
z.wallet_balance -= D("700.00")
db.add(Payout(payout_id="pay_zienxt", user_id=z.id, amount=D("700.00"), status=PayoutStatus.paid,
              method=PayoutMethod.paypal_sandbox, scheduled_for=date(2026, 10, 6),
              paid_at=datetime(2026, 10, 5, 19, 14, tzinfo=UTC)))
db.commit()

# Make the remittance's received_on land in October whatever "today" is.
SEED_LOCAL = SEED.replace("(now() AT TIME ZONE 'Asia/Manila')::date", "DATE '2026-10-06'")


def localise(sql: str) -> str:
    for name, pid in PROD.items():
        sql = sql.replace(pid, ids[name])
    for key, pid in PROD_REVIEWS.items():
        sql = sql.replace(pid, revs[key])
    for key, pid in PROD_CREDITS.items():
        sql = sql.replace(pid, credits[key])
    return sql


def run(sql: str):
    import psycopg
    with psycopg.connect("postgresql://bluntly:bluntly@localhost:5432/rehearsal", autocommit=True) as conn:
        conn.add_notice_handler(lambda d: print("  NOTICE", d.message_primary))
        conn.execute(localise(sql).encode())


run(SEED_LOCAL)
# Demo day: three of the four demo reviewers cashed out ₱350 through the sandbox.
for name, when in (("zaisias", datetime(2026, 10, 5, 22, 8, tzinfo=UTC)),
                   ("northpacificfan", datetime(2026, 10, 6, 5, 20, tzinfo=UTC)),
                   ("suvango", datetime(2026, 10, 6, 7, 55, tzinfo=UTC))):
    u = db.get(User, uuid.UUID(ids[name]))
    db.refresh(u)
    u.wallet_balance -= D("350.00")
    db.add(Payout(payout_id=f"pay_{name}", user_id=u.id, amount=D("350.00"), status=PayoutStatus.paid,
                  method=PayoutMethod.paypal_sandbox, scheduled_for=date(2026, 10, 6), paid_at=when))
db.commit()

OCT = periods.resolve(month=10, year=2026)


def report():
    db.expire_all()
    return financial.build(db, OCT)


def wallets():
    db.expire_all()
    return {n: db.get(User, uuid.UUID(i)).wallet_balance for n, i in ids.items()}


print("\nAFTER SEED + DEMO PAYOUTS (should equal production today)")
r = report()
ok(r.revenue.earned == D("8166.69"), f"revenue earned {r.revenue.earned} == 8166.69")
ok(r.money_in.received_total == D("8166.69"), f"money in {r.money_in.received_total} == 8166.69")
ok(r.liabilities.cleared_in_wallets == D("700.00"), f"still owed {r.liabilities.cleared_in_wallets} == 700")
w = wallets()
ok(w == {"zienxt": D("350.00"), "zaisias": D("0.00"), "northpacificfan": D("0.00"),
         "suvango": D("0.00"), "abelli": D("350.00")}, f"wallets {w}")
# (With this PR, the sandbox payouts are no longer counted as money out.)
ok(r.money_out.paid_out_total == D("0.00") and r.money_out.sandbox_excluded.amount == D("1750.00"),
   f"money out {r.money_out.paid_out_total}, sandbox excluded {r.money_out.sandbox_excluded.amount}")


def check_converted(label):
    print(f"\n{label}")
    db.expire_all()
    rows = db.scalars(select(Commission).where(Commission.reviewer_id.in_(
        [uuid.UUID(i) for i in ids.values()]))).all()
    ok(len(rows) == 6, f"{len(rows)} demo rows remain (7 minus com_demo_zienxt)")
    ok(all(c.is_test for c in rows), "every demo row is_test")
    ok(all(c.platform_share == 0 and c.honesty_fund_share == 0 for c in rows), "no platform/fund share")
    ok(all(c.gross_amount == c.reviewer_share == D("350.00") and c.reviewer_share_bps == 10000
           for c in rows), "gross = reviewer share = 350, bps 10000")
    ok(all(c.csv_source == "qa_sandbox" and c.order_status == "qa_sandbox" and c.platform is None
           and c.row_reference == f"review:{c.review_id}" for c in rows),
       "source/status/reference exactly as qa_sandbox_service.credit writes them")
    ok(len({c.review_id for c in rows}) == 6, "one test credit per review")
    ok(db.scalar(select(MarketplaceRemittance).where(
        MarketplaceRemittance.reference == "DEMO-remittance-2026-10")) is None, "invented remittance gone")
    r = report()
    ok(r.revenue.earned == D("0.00") and r.revenue.net == D("0.00"), f"revenue {r.revenue.earned}")
    ok(r.money_in.received_total == D("0.00"), f"money in {r.money_in.received_total}")
    ok(r.money_out.paid_out_total == D("0.00"), f"money out {r.money_out.paid_out_total}")
    ok((r.money_out.sandbox_excluded.count, r.money_out.sandbox_excluded.amount) == (4, D("1750.00")),
       "4 sandbox payouts (₱1,750) shown apart")
    w = wallets()
    ok(w == {"zienxt": D("0.00"), "zaisias": D("0.00"), "northpacificfan": D("0.00"),
             "suvango": D("0.00"), "abelli": D("350.00")}, f"wallets {w}")
    pool = db.execute(text("SELECT coalesce(sum(honesty_fund_share),0) FROM commissions "
                           "WHERE cycle_month = DATE '2026-10-01' AND NOT is_test")).scalar()
    ok(D(pool) == D("0.00"), f"October Honesty Fund pool from real commissions = {pool}")
    ok(db.execute(text("SELECT count(*) FROM payouts WHERE user_id = ANY(:u)"),
                  {"u": [uuid.UUID(i) for i in ids.values()]}).scalar() == 4, "all 4 payouts kept as history")


run(CONVERT)
check_converted("AFTER CONVERSION")
run(CONVERT)  # idempotent: a NOTICE, nothing changes
check_converted("AFTER RUNNING THE CONVERSION AGAIN")

run(ROLLBACK)
print("\nAFTER ROLLBACK (back to the seeded state)")
r = report()
ok(r.revenue.earned == D("8166.69") and r.money_in.received_total == D("8166.69"), "seed figures back")
ok(wallets()["zienxt"] == D("350.00"), "@zienxt's ₱350 back")

run(CONVERT)
check_converted("AFTER RE-APPLYING THE CONVERSION")
print("\nREHEARSAL PASSED")

"""Business-rules migration round trip, with data (fast lane only).

What `alembic downgrade`/`upgrade` on an EMPTY database cannot show: that rows
survive the trip and the rating column means the right thing on each side.

  1. at head, create real rows through the API: one product rated 5, 2 and 4
     by three reviewers (median 4, mean 3.67), plus an uncleared commission;
  2. downgrade to 0049 — the column must hold the MEAN again (0049's meaning),
     and no review or commission may be lost;
  3. upgrade to head — the column must hold the §4 MEDIAN again (0051), every
     review must be its own thread (0050), the commission's platform and
     clearing backfilled.

Refuses anything but a local database: a downgrade on the shared test project
would break every other run using it.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import make_url


def main() -> int:
    from alembic.config import Config
    from fastapi.testclient import TestClient

    from alembic import command
    from app.core.config import settings
    from app.db.session import SessionLocal, engine
    from app.main import app

    url = make_url(settings.effective_database_url)
    if url.host not in ("localhost", "127.0.0.1"):
        print(f"refusing: {url.host} is not a local, disposable database")
        return 2
    settings.auth_rate_limit_max = 1_000_000

    c = TestClient(app)

    def account(n: int) -> dict:
        r = c.post("/api/v1/auth/register", json={
            "email": f"mig_{n}_{uuid.uuid4().hex[:6]}@example.com", "password": "password123"})
        assert r.status_code == 201, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]

    h1, uid1 = account(1)
    pid = c.post("/api/v1/products", headers=h1, json={
        "name": f"Round trip {uuid.uuid4().hex[:6]}", "category": "electronics"}).json()["id"]
    review_ids = []
    for n, stars in enumerate((5, 2, 4)):
        h, _ = (h1, uid1) if n == 0 else account(n + 10)
        r = c.post("/api/v1/reviews", headers=h, json={
            "product_id": pid, "title": f"Entry {n}", "star_rating": stars,
            "discussion": f"Round-trip fixture {n}.",
            "verdict": "yes_absolutely" if stars >= 3 else "hard_pass"})
        assert r.status_code == 201, r.text
        review_ids.append(r.json()["id"])

    from app.models.commission import Commission
    from app.models.enums import CommissionTarget, Platform
    db = SessionLocal()
    try:
        commission_id = f"com_{uuid.uuid4().hex[:12]}"
        db.add(Commission(
            commission_id=commission_id, target_type=CommissionTarget.review,
            review_id=uuid.UUID(review_ids[0]), reviewer_id=uuid.UUID(uid1),
            reviewer_share_bps=3000, gross_amount=Decimal("100.00"),
            platform_share=Decimal("40.00"), reviewer_share=Decimal("30.00"),
            honesty_fund_share=Decimal("30.00"), currency="PHP",
            csv_source=f"mig:{uuid.uuid4().hex}", row_reference="1",
            cycle_month=date(1996, 1, 1), platform=Platform.shopee, cleared_at=None))
        db.commit()
    finally:
        db.close()

    def one(sql: str, **params):
        with engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()

    failures = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if not ok else ""))
        if not ok:
            failures.append(label)

    at_head = Decimal(str(one("SELECT avg_rating FROM products WHERE id = :p", p=pid)))
    check("at head: the rating column holds the median (4)",
          at_head == Decimal("4.00"), str(at_head))

    cfg = Config("alembic.ini")
    engine.dispose()
    command.downgrade(cfg, "0049_report_resolution")
    down = Decimal(str(one("SELECT avg_rating FROM products WHERE id = :p", p=pid)))
    check("at 0049: the column holds the mean again (3.67)", down == Decimal("3.67"), str(down))
    check("at 0049: no review lost", one(
        "SELECT count(*) FROM reviews WHERE product_id = :p", p=pid) == 3)
    check("at 0049: the commission survives", one(
        "SELECT count(*) FROM commissions WHERE commission_id = :c", c=commission_id) == 1)

    engine.dispose()
    command.upgrade(cfg, "head")
    up = Decimal(str(one("SELECT avg_rating FROM products WHERE id = :p", p=pid)))
    check("back at head: the median is recomputed (4), not the mean",
          up == Decimal("4.00"), str(up))
    check("back at head: every review is its own thread", one(
        "SELECT count(*) FROM reviews WHERE product_id = :p AND thread_id = id", p=pid) == 3)
    # 0050 takes a legacy commission's platform from its review's referral
    # link. This one has none, so its platform stays unknown — and it must not
    # be stranded: it is treated as cleared (next check), so no remittance for a
    # platform is needed before it can be withdrawn.
    check("back at head: a link-less legacy commission keeps no platform", one(
        "SELECT platform IS NULL FROM commissions WHERE commission_id = :c",
        c=commission_id) is True)
    check("back at head: legacy commission is treated as cleared (documented choice)", one(
        "SELECT cleared_at IS NOT NULL FROM commissions WHERE commission_id = :c",
        c=commission_id) is True)
    verdict = "OK" if not failures else "FAILED: " + ", ".join(failures)
    print(f"\n=== migration round trip: {verdict} ===")
    return 0 if not failures else 1


if __name__ == "__main__":
    from app.core.env_guard import guard_cli
    guard_cli("check_rules_migration_roundtrip", production_is_legitimate=False)
    sys.exit(main())

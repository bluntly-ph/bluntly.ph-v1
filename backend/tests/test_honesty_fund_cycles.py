"""The admin Payouts screen's Honesty Fund tab (Figma 8024:13286)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal as D

from app.models.commission import Commission
from app.models.enums import CommissionTarget, Platform
from app.models.honesty_fund import HonestyFundDistribution
from app.services import honesty_fund_cycles as hf
from tests.conftest import register_and_token, requires_db
from tests.test_payout_tips import _review, _user

pytestmark = requires_db

# 10 March 2030, Manila: a clock no other test's rows reach.
NOW = datetime(2030, 3, 10, 4, 0, tzinfo=UTC)


def _commission(db, review, author, cycle: date, fund: str, *, test: bool = False) -> None:
    db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                      target_type=CommissionTarget.review, review_id=review.id,
                      reviewer_id=author.id, platform=Platform.shopee, currency="PHP",
                      csv_source="hf-test", row_reference=uuid.uuid4().hex, cycle_month=cycle,
                      gross_amount=D("100"), platform_share=D("0" if test else "30"),
                      reviewer_share=D("40"), honesty_fund_share=D("0" if test else fund),
                      is_test=test, created_at=NOW))
    db.flush()


def test_cycles_count_pools_and_distributions(db):
    a, b = _user(db), _user(db)
    ra = _review(db, a, published=NOW)
    rb = _review(db, b, published=NOW)
    _commission(db, ra, a, date(2030, 3, 1), "30.00")
    _commission(db, rb, b, date(2030, 3, 1), "12.50")
    _commission(db, ra, a, date(2030, 2, 1), "90.00")
    _commission(db, rb, b, date(2030, 1, 1), "45.00")  # closed, never distributed
    for who, review, amount in ((a, ra, "60.00"), (b, rb, "29.99")):
        db.add(HonestyFundDistribution(
            distribution_id=f"hfd_{uuid.uuid4().hex[:12]}", cycle_month=date(2030, 2, 1),
            review_id=review.id, reviewer_id=who.id, honesty_score=D("1"),
            pool_amount=D("90.00"), payout_amount=D(amount),
            created_at=datetime(2030, 3, 1, 1, 0, tzinfo=UTC)))
    db.flush()

    f = hf.build(db, now=NOW)
    assert f.current.month == date(2030, 3, 1) and f.current.status == "collecting"
    assert f.current.pool == D("42.50")
    assert f.closes_on == date(2030, 3, 31)
    assert f.distributes_on.month == 4 and f.distributes_on.year == 2030
    feb = next(c for c in f.cycles if c.month == date(2030, 2, 1))
    assert (feb.status, feb.contributors, feb.largest_share, feb.distributed) == (
        "distributed", 2, D("60.00"), D("89.99"))
    assert f.last is not None and f.last.month == date(2030, 2, 1)
    jan = next(c for c in f.cycles if c.month == date(2030, 1, 1))
    assert jan.status == "not_distributed" and jan.contributors == 0
    assert [c.month for c in f.cycles] == sorted((c.month for c in f.cycles), reverse=True)


def test_endpoint_is_staff_only(client):
    _, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    url = "/api/v1/admin/payouts/honesty-fund"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": f"Bearer {member}"}).status_code == 403
    body = client.get(url, headers={"Authorization": f"Bearer {admin}"}).json()
    assert body["current"]["status"] == "collecting"
    assert {"closes_on", "distributes_on", "last", "cycles"} <= set(body)

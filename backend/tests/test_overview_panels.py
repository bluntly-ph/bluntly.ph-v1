"""The redesigned Overview's Review queue and Affiliate earnings cards
(Figma "Draft/Admin/Overview v3", meeting 2026-10-02).

The database is shared with the rest of the suite, so counts are asserted as
deltas or inside a far-future window no other test writes to.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.enums import AffiliateTxStatus, Platform
from app.services import admin_overview_service
from app.services import overview_panels_service as svc
from tests.conftest import register_and_token, requires_db

PREVIEW = "/api/v1/admin/analytics/queue-preview"
EARNINGS = "/api/v1/admin/analytics/affiliate-earnings"


# Periods (no database) ------------------------------------------------------

def test_six_months_end_on_the_current_month():
    buckets = svc._buckets("6M", date(2026, 10, 2))
    assert [b[0] for b in buckets] == ["May", "Jun", "Jul", "Aug", "Sep", "Oct"]
    assert buckets[-1][1] == date(2026, 10, 1) and buckets[-1][2] == date(2026, 11, 1)


def test_a_year_crosses_the_new_year():
    buckets = svc._buckets("1Y", date(2026, 2, 10))
    assert len(buckets) == 12
    assert buckets[0][1] == date(2025, 3, 1) and buckets[-1][1] == date(2026, 2, 1)


def test_one_month_is_four_weeks_starting_monday():
    buckets = svc._buckets("1M", date(2026, 10, 2))  # a Friday
    assert len(buckets) == 4
    assert all(b[1].weekday() == 0 for b in buckets)
    assert buckets[-1][1] == date(2026, 9, 28)


def test_no_previous_period_means_no_percentage_not_zero():
    e = svc.AffiliateEarnings(range="6M", verified=Decimal("10"), previous_verified=Decimal("0"),
                              returned=Decimal("0"), absorbed=Decimal("0"), pending=[],
                              buckets=[])
    assert e.delta_pct is None
    assert svc.AffiliateEarnings(
        range="6M", verified=Decimal("0"), previous_verified=Decimal("0"),
        returned=Decimal("0"), absorbed=Decimal("0"), pending=[], buckets=[],
    ).returned_pct is None


# Access ----------------------------------------------------------------------

@requires_db
def test_members_and_anonymous_are_denied(client):
    _, token, _ = register_and_token(client, role="user")
    for url in (PREVIEW, EARNINGS):
        assert client.get(url).status_code == 401
        assert client.get(url, headers={"Authorization": f"Bearer {token}"}).status_code == 403


@requires_db
def test_staff_get_both_cards(client):
    _, token, _ = register_and_token(client, role="administrator")
    h = {"Authorization": f"Bearer {token}"}
    preview = client.get(PREVIEW, headers=h)
    assert preview.status_code == 200
    assert [t["key"] for t in preview.json()["tabs"]] == [
        "earn_eligible", "flagged", "first_review", "new_product"]
    assert all(len(t["items"]) <= svc.PREVIEW_LIMIT for t in preview.json()["tabs"])

    for rng, n in (("1M", 4), ("6M", 6), ("1Y", 12)):
        body = client.get(EARNINGS, headers=h, params={"range": rng})
        assert body.status_code == 200 and len(body.json()["buckets"]) == n
    assert client.get(EARNINGS, headers=h, params={"range": "5Y"}).status_code == 422


# Agreement with the Overview breakdown ----------------------------------------

@requires_db
def test_tab_counts_equal_the_overview_breakdown_bars(db):
    tabs = {t.key: t.count for t in svc.queue_preview(db)}
    bars = {b.label: b.count for b in admin_overview_service.overview(db).breakdown}
    assert tabs["earn_eligible"] == bars["Earn Eligible"]
    assert tabs["flagged"] == bars["Flagged"]
    assert tabs["first_review"] == bars["First Submission"]
    assert tabs["new_product"] == bars["New Product"]


# Earnings figures ---------------------------------------------------------------

def _postback(db, status, payout, *, when=None, platform=Platform.shopee, unrecovered=None):
    from app.models.postback import AffiliatePostback

    row = AffiliatePostback(
        platform=platform, external_sub_order_id=f"t-{uuid.uuid4().hex}",
        reported_payout=Decimal(payout), canonical_status=status,
        unrecovered_amount=Decimal(unrecovered) if unrecovered else None)
    if status == AffiliateTxStatus.completed:
        row.completed_at = when
    if status == AffiliateTxStatus.returned:
        row.returned_at = when
    db.add(row)
    db.flush()
    return row


@requires_db
def test_verified_returned_and_absorbed_land_in_their_months(db):
    # March 2031: a window nothing else in the suite writes to.
    today = date(2031, 3, 20)
    _postback(db, AffiliateTxStatus.completed, "100.00", when=datetime(2031, 3, 5, 12))
    _postback(db, AffiliateTxStatus.completed, "50.00", when=datetime(2031, 1, 9, 12))
    _postback(db, AffiliateTxStatus.returned, "10.00", when=datetime(2031, 3, 6, 12),
              unrecovered="4.00")
    _postback(db, AffiliateTxStatus.completed, "40.00", when=datetime(2030, 8, 1, 12))

    e = svc.affiliate_earnings(db, "6M", today=today)
    by_label = {b.label: b for b in e.buckets}
    assert by_label["Mar"].verified == Decimal("100.00")
    assert by_label["Mar"].returned == Decimal("10.00")
    assert by_label["Jan"].verified == Decimal("50.00")
    assert e.verified == Decimal("150.00")
    assert e.previous_verified == Decimal("40.00"), "Aug 2030 is in the six months before"
    assert e.delta_pct == 275.0
    assert e.absorbed == Decimal("4.00")
    assert round(e.returned_pct, 2) == round(10 / 150 * 100, 2)


@requires_db
def test_pending_orders_are_counted_by_marketplace(db):
    before = {p.platform: p for p in svc.affiliate_earnings(db).pending}
    _postback(db, AffiliateTxStatus.pending, "30.00", platform=Platform.lazada)
    _postback(db, AffiliateTxStatus.pending, "20.00", platform=Platform.lazada)
    after = {p.platform: p for p in svc.affiliate_earnings(db).pending}
    was = before.get("lazada")
    assert after["lazada"].orders == (was.orders if was else 0) + 2
    assert after["lazada"].amount == (was.amount if was else Decimal("0")) + Decimal("50.00")

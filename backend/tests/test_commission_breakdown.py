"""The ⓘ "Commission breakdown" sheet (Figma 9057:47088) and its demo data.

The demo test runs the owner's two real Shopee reports through the same path
the seed uses and holds the sheet to the owner's summary figures. The rule
tests pin each line's meaning on rows built for it.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.models.commission import Commission
from app.models.enums import CommissionTarget, Platform
from app.models.postback import AffiliatePostback
from app.models.product import Product
from app.services import commission_breakdown, report_formats
from app.services.affiliate_ingest import _fill_item_detail
from app.services.affiliate_status import map_status
from tests.conftest import make_user, requires_db
from tests.test_affiliate_ingest import attributed_review, shopee_csv

DATA = Path(__file__).resolve().parents[1] / "scripts" / "data"


def _store(db, user, report: bytes) -> None:
    """Every row into the transaction store, credited to `user` (the seed's path)."""
    products: dict = {}
    for row in report_formats.parse_lifecycle(report).rows:
        mapped = map_status(row.platform, row.raw)
        p = AffiliatePostback(
            platform=Platform(row.platform), external_order_id=row.order_ref,
            external_sub_order_id=f"{uuid.uuid4().hex[:6]}|{row.identity}", raw=row.raw,
            canonical_status=mapped.status, order_status=mapped.raw_order_status,
            raw_item_status=mapped.raw_item_status, reported_payout=row.gross_amount,
            reviewer_id=user.id)
        db.add(p)
        db.flush()
        _fill_item_detail(db, p, row, products)
    db.flush()


@requires_db
def test_the_demo_reports_give_the_owners_figures(db):
    user = make_user(db)
    _store(db, user, (DATA / "commission_demo_shopee_orders.csv").read_bytes())
    want = json.loads((DATA / "commission_demo_summary.json").read_text())
    sheet = commission_breakdown.breakdown(db, user)

    assert sheet.gross_sales == Decimal("65969.00")
    assert (sheet.orders, sheet.items) == (want["orders"], want["items"])
    assert sheet.gross_commission == Decimal("1962.70")
    assert sheet.reversals == Decimal("0.00")
    assert (sheet.cancelled_items, sheet.refunded_items) == (3, 5)
    assert sheet.net_commission == Decimal("1962.70")
    assert (sheet.you, sheet.honesty_fund, sheet.bluntly) == (
        Decimal("588.81"), Decimal("588.81"), Decimal("785.08"))
    assert (sheet.pending_commission, sheet.pending_orders) == (Decimal("109.95"), 8)
    assert [(m.platform, m.gross_commission, m.orders) for m in sheet.marketplaces] == [
        ("shopee", Decimal("1962.70"), 91), ("lazada", Decimal("0.00"), 0)]
    assert len(sheet.products) == want["product_count"]
    # Exactly ₱250.015, rounded half up like the ledger (the summary's 250.01 is
    # a float artefact); the other four are the summary's.
    assert [(p.net_commission, p.orders, p.sales) for p in sheet.products[:5]] == [
        (Decimal("250.02"), 3, Decimal("3873.00")), (Decimal("246.40"), 1, Decimal("2580.00")),
        (Decimal("192.51"), 3, Decimal("2139.00")), (Decimal("123.30"), 1, Decimal("1666.00")),
        (Decimal("84.40"), 1, Decimal("2220.00"))]
    assert sheet.first_completed.date().isoformat() == "2026-04-05"
    assert sheet.last_completed.date().isoformat() == "2026-10-02"


def test_the_item_commission_is_the_items_own_not_the_orders():
    """Shopee writes the order's commission on one item and 0 on the rest."""
    header = ("Order id,Order Status,Conversion id,Item id,Model id,Promotion id,"
              "Affiliate Item Status,Item Total Commission(₱),Affiliate Net Commission(₱),"
              "Total Order Commission(₱)")
    report = (f"{header}\nO1,Completed,C1,I1,M1,,Completed,5.675,10.95,10.95\n"
              f"O1,Completed,C1,I2,M2,,Completed,5.275,0,0\n").encode()
    rows = report_formats.parse_lifecycle(report).rows
    assert [r.gross_amount for r in rows] == [Decimal("5.675"), Decimal("5.275")]
    assert [report_formats.shopee_item_detail(r.raw)["item_commission"] for r in rows] == [
        Decimal("5.675"), Decimal("5.275")]


@requires_db
def test_a_cancelled_item_of_a_completed_order_is_a_reversal(db):
    user = make_user(db)
    header = ("Order id,Order Status,Conversion id,Item id,Model id,Promotion id,"
              "Affiliate Item Status,Item Total Commission(₱),Purchase Value(₱),"
              "Refund Amount(₱),Qty,Affiliate Net Commission(₱)")
    _store(db, user, (f"{header}\n"
                      "O1,Completed,C1,I1,M1,,Completed,40,1000,0,1,0\n"
                      "O1,Completed,C1,I2,M2,,Cancelled,12.5,300,300,1,0\n"
                      "O2,Pending,C2,I3,M3,,Pending,7.125,200,0,1,0\n"
                      "O3,Cancelled,C3,I4,M4,,Cancelled,0,0,90,0,0\n").encode())
    sheet = commission_breakdown.breakdown(db, user)
    assert (sheet.gross_sales, sheet.orders, sheet.items) == (Decimal("1300.00"), 1, 2)
    assert (sheet.sales_orders, sheet.sales_items) == (1, 2)
    # Report rows are evidence, never money: nothing is credited for them.
    assert sheet.credited == Decimal("0.00")
    assert (sheet.gross_commission, sheet.reversals, sheet.net_commission) == (
        Decimal("52.50"), Decimal("12.50"), Decimal("40.00"))
    assert (sheet.cancelled_items, sheet.refunded_items) == (1, 2)
    assert (sheet.pending_commission, sheet.pending_orders) == (Decimal("7.13"), 1)
    assert sum((sheet.you, sheet.honesty_fund, sheet.bluntly), Decimal(0)) == Decimal("40.00")
    assert [p.net_commission for p in sheet.products] == [Decimal("40.00"), Decimal("0.00")]


@requires_db
def test_a_sale_attributed_to_your_review_is_yours_and_groups_by_its_product(db):
    from app.services import affiliate_ingest

    review, sub_id, author = attributed_review(db)
    report = shopee_csv(sub_id=sub_id, order=f"ORD{uuid.uuid4().hex[:8]}",
                        conversion=f"CNV{uuid.uuid4().hex[:8]}", commission="80.00")
    affiliate_ingest.apply(db, make_user(db).id, "shopee.csv", report)
    postback = db.scalar(select(AffiliatePostback).where(
        AffiliatePostback.review_id == review.id))
    assert postback.reviewer_id == author.id and postback.product_id == review.product_id
    sheet = commission_breakdown.breakdown(db, author)
    assert sheet.gross_commission == Decimal("80.00")
    assert sheet.products[0].product_id == review.product_id
    name = db.get(Product, review.product_id).canonical_name
    assert sheet.products[0].name == name
    # Someone else's sheet does not see it.
    assert commission_breakdown.breakdown(db, make_user(db)).orders == 0


@requires_db
def test_ledger_entries_without_a_report_row_still_count(db):
    review, _sub, author = attributed_review(db)
    entry = Commission(
        commission_id=f"com_{uuid.uuid4().hex[:8]}", target_type=CommissionTarget.review,
        review_id=review.id,
        reviewer_id=author.id, platform=Platform.lazada, gross_amount=Decimal("1166.67"),
        reviewer_share=Decimal("350.00"), honesty_fund_share=Decimal("350.00"),
        platform_share=Decimal("466.67"), csv_source="DEMO-seed-test", row_reference="1",
        cycle_month=review.created_at.date().replace(day=1))
    db.add(entry)
    db.flush()
    sheet = commission_breakdown.breakdown(db, author)
    assert (sheet.net_commission, sheet.you) == (Decimal("1166.67"), Decimal("350.00"))
    # A ledger entry records commission, not what was sold: no ₱0 "sales", its
    # order is not one of Gross sales', and its date is in the span.
    assert sheet.products[0].sales is None
    assert (sheet.orders, sheet.sales_orders, sheet.gross_sales) == (1, 0, Decimal("0.00"))
    assert sheet.first_completed is not None and sheet.credited == Decimal("350.00")
    assert [(m.platform, m.orders) for m in sheet.marketplaces] == [("shopee", 0), ("lazada", 1)]

    db.add(Commission(
        commission_id=f"com_{uuid.uuid4().hex[:8]}", target_type=CommissionTarget.review,
        review_id=review.id,
        reviewer_id=author.id, platform=Platform.lazada, gross_amount=Decimal("-1166.67"),
        reviewer_share=Decimal("-350.00"), honesty_fund_share=Decimal("-350.00"),
        platform_share=Decimal("-466.67"), csv_source="DEMO-seed-test", row_reference="2",
        cycle_month=entry.cycle_month, reverses_commission_id=entry.id))
    db.flush()
    sheet = commission_breakdown.breakdown(db, author)
    assert (sheet.gross_commission, sheet.reversals, sheet.net_commission) == (
        Decimal("1166.67"), Decimal("1166.67"), Decimal("0.00"))


@requires_db
def test_performance_carries_the_sheet_and_the_cards_read_it(db):
    from app.services import contributor_dashboard

    review, _sub, author = attributed_review(db)
    review.published_at = review.created_at
    _store(db, author, (DATA / "commission_demo_shopee_orders.csv").read_bytes())
    p = contributor_dashboard.performance(db, author)
    assert p.commission.you == Decimal("588.81") == p.share_you
    assert [(o.platform, o.orders) for o in p.orders] == [("shopee", 91), ("lazada", 0)]
    one = contributor_dashboard.performance(db, author, product_id=review.product_id)
    assert one.commission.orders == 0

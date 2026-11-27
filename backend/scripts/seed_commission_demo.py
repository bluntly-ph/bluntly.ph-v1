"""Seed the Commission breakdown demo account from two real Shopee reports.

Owner dev note (2026-10-19): the account perezgyber@gmail.com must show, on
Performance and its ⓘ "Commission breakdown" sheet, exactly the totals in
`scripts/data/commission_demo_summary.json` — the two Shopee affiliate reports
in `scripts/data/commission_demo_shopee_orders.csv` combined (Apr–Oct 2026).

What it writes:

1. The five products the sheet names, through the admin product CSV importer
   (a new product is created, an existing one gets the Shopee listing
   attached), so each report item finds its catalogue product by listing.
   The importer commits this step on its own.
2. (one transaction with 3) Every report row into the canonical transaction store
   (`affiliate_postbacks`), with the same status mapping and item detail as an
   admin report import, credited to the account (`reviewer_id`). A row the
   store already holds unattributed is claimed; one credited to someone else
   is refused. The reports carry no Sub_id, so no row is tied to a review and
   NOTHING is credited to a wallet: a report row is evidence, never money
   (Business Rules §15).
3. With --replace-demo-commissions: the account's earlier defense-demo ledger
   entries (csv_source DEMO-seed-*: 3 Lazada sales) are removed and their
   reviewer shares taken back off the wallet, so the sheet shows Shopee 91 /
   Lazada 0. Refused if that would leave the wallet below zero.

Then it reads the sheet back and compares it with the summary file.

    python -m scripts.seed_commission_demo                 # dry run: says what it would do
    python -m scripts.seed_commission_demo --replace-demo-commissions --apply
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import MemberRole, Platform, SettlementStatus
from app.models.postback import AffiliatePostback
from app.models.user import User
from app.services import commission_breakdown, product_admin_service, report_formats, wallet
from app.services.affiliate_ingest import _fill_item_detail
from app.services.affiliate_status import map_status

DATA = Path(__file__).resolve().parent / "data"
REPORT = DATA / "commission_demo_shopee_orders.csv"
SUMMARY = DATA / "commission_demo_summary.json"
ACCOUNT = "perezgyber@gmail.com"
IMPORT_ID = "demo:commission-breakdown-2026-10"

#: The catalogue names the sheet shows for the top five items (Item id -> naming).
PRODUCTS = {
    "23743555988": ("Jisulife", "Handheld Fan", "Pro1", "home-appliances"),
    "22836255418": ("Edifier", "W820NB", "Plus", "audio"),
    "17552845260": ("Baseus", "Bowie", "WM02", "audio"),
    "851073401": ("Imarflex", "Blend to Go", "IB-250P", "home-appliances"),
    "16998608895": ("Jisulife", "Handheld Fan", "Ultra1", "home-appliances"),
}


def _product_csv(report: bytes) -> bytes:
    shops = {}
    for row in csv.DictReader(io.StringIO(report.decode("utf-8-sig"))):
        shops.setdefault(row["Item id"], row["Shop id"])
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["brand", "line", "variant", "category", "source_url"])
    for item, (brand, line, variant, category) in PRODUCTS.items():
        writer.writerow([brand, line, variant, category,
                         report_formats.shopee_listing_url(shops[item], item)])
    return out.getvalue().encode()


def _staff(db) -> User:
    actor = db.scalar(select(User).where(User.role == MemberRole.super_admin)
                      .order_by(User.created_at).limit(1))
    if actor is None:
        sys.exit("No Super Admin to record the catalogue changes as.")
    return actor


def run(db, *, apply: bool, replace_demo: bool) -> int:
    user = db.scalar(select(User).where(func.lower(User.email) == ACCOUNT))
    if user is None:
        print(f"No account {ACCOUNT}.")
        return 1
    report = REPORT.read_bytes()

    # 1. Catalogue: create or attach the five named products.
    catalogue = product_admin_service.import_products(db, _staff(db), _product_csv(report),
                                                      apply=False)
    attach = {r.line for r in catalogue.rows if r.outcome == "exists" and r.attach_adds}
    print("catalogue:", [(r.name, r.outcome, r.matched_by) for r in catalogue.rows])
    blocked = [r for r in catalogue.rows if r.outcome in ("conflict", "error")]
    if blocked:
        print("refused: catalogue rows", [(r.name, r.outcome, r.errors) for r in blocked])
        return 1
    if apply:
        result = product_admin_service.import_products(
            db, _staff(db), _product_csv(report), apply=True, attach=attach,
            filename="commission-demo-products.csv")
        if result.failure:
            print("refused: catalogue import failed:", result.failure)
            return 1

    # 2. Report rows into the transaction store, credited to the account.
    parsed = report_formats.parse_lifecycle(report)
    if parsed.format != "shopee_commission_report" or parsed.errors or parsed.unidentified:
        print("refused: the report did not parse", parsed.format, parsed.errors[:3])
        return 1
    created = claimed = 0
    products: dict = {}
    for row in parsed.rows:
        postback = db.scalar(select(AffiliatePostback).where(
            AffiliatePostback.platform == Platform.shopee,
            AffiliatePostback.external_sub_order_id == row.identity))
        if postback is not None and postback.reviewer_id not in (None, user.id):
            print(f"refused: {row.identity} is credited to another member")
            db.rollback()
            return 1
        if postback is None:
            created += 1
            postback = AffiliatePostback(
                platform=Platform.shopee, external_order_id=row.order_ref,
                external_sub_order_id=row.identity, review_sub_id=row.sub_id,
                currency=row.currency, raw=row.raw, source_import_id=IMPORT_ID,
                settlement_status=SettlementStatus.not_earned)
            db.add(postback)
        elif postback.reviewer_id is None:
            claimed += 1
        mapped = map_status("shopee", row.raw)
        postback.canonical_status = mapped.status
        postback.order_status = mapped.raw_order_status
        postback.raw_item_status = mapped.raw_item_status
        postback.status_reason = mapped.reason[:255]
        postback.reported_payout = row.gross_amount
        postback.reviewer_id = user.id
        db.flush()
        _fill_item_detail(db, postback, row, products)
    print(f"report rows: {len(parsed.rows)} ({created} new, {claimed} claimed from unattributed)")

    # 3. The earlier defense-demo ledger entries.
    demo = list(db.scalars(select(Commission).where(
        Commission.reviewer_id == user.id, Commission.csv_source.like("DEMO-seed-%"))))
    if demo:
        share = sum((c.reviewer_share for c in demo), Decimal("0"))
        print(f"demo ledger entries: {len(demo)} (reviewer share ₱{share}, "
              f"wallet ₱{user.wallet_balance})", "- replacing" if replace_demo else "- kept")
        if replace_demo:
            if user.wallet_balance < share:
                print("refused: the wallet no longer holds those shares (paid out?)")
                db.rollback()
                return 1
            for c in demo:
                db.delete(c)
            wallet.adjust(db, user.id, -share)
    db.flush()

    sheet = commission_breakdown.breakdown(db, user)
    ok = _compare(sheet, json.loads(SUMMARY.read_text()))
    if apply:
        db.commit()
        print("applied.")
    else:
        db.rollback()
        print("dry run: nothing written (catalogue rows were previewed, not created).")
    return 0 if ok or not apply else 1


#: Where the sheet and the summary file differ on purpose.
KNOWN = {
    "top1": "Pro1 is ₱250.015 exactly (93.64 + 77.25 + 79.125); the sheet rounds half up "
            "like the ledger (₱250.02), the summary's ₱250.01 is a binary-float rounding",
}


def _compare(sheet, want: dict) -> bool:
    shopee = next(m for m in sheet.marketplaces if m.platform == "shopee")
    lazada = next(m for m in sheet.marketplaces if m.platform == "lazada")
    pairs = {
        "gross_sales": (sheet.gross_sales, want["gross_sales"]),
        "orders": (sheet.orders, want["orders"]),
        "items": (sheet.items, want["items"]),
        "gross_commission": (sheet.gross_commission, want["gross_commission"]),
        "reversals": (sheet.reversals, want["reversals"]),
        "cancelled_items": (sheet.cancelled_items, want["cancelled_items"]),
        "refunded_items": (sheet.refunded_items, want["refunded_items"]),
        "net_commission": (sheet.net_commission, want["net_commission"]),
        "you": (sheet.you, want["split"]["reviewer_30"]),
        "honesty_fund": (sheet.honesty_fund, want["split"]["honesty_fund_30"]),
        "bluntly": (sheet.bluntly, want["split"]["bluntly_40"]),
        "pending": (sheet.pending_commission, want["pending"]["net_commission"]),
        "pending_orders": (sheet.pending_orders, want["pending"]["orders"]),
        "shopee": ((shopee.gross_commission, shopee.orders),
                   (want["by_marketplace"]["Shopee"]["gross_commission"],
                    want["by_marketplace"]["Shopee"]["orders"])),
        "lazada": ((lazada.gross_commission, lazada.orders),
                   (want["by_marketplace"]["Lazada"]["gross_commission"],
                    want["by_marketplace"]["Lazada"]["orders"])),
        "product_count": (len(sheet.products), want["product_count"]),
    }
    for i, top in enumerate(want["top_products"]):
        got = sheet.products[i] if i < len(sheet.products) else None
        pairs[f"top{i + 1}"] = (
            (got.net_commission, got.orders, got.sales) if got else None,
            (top["net_commission"], top["orders"], top["sales"]))
    ok = True
    for name, (got, expected) in pairs.items():
        same = _same(got, expected)
        ok &= same or name in KNOWN
        mark = "ok " if same else "known" if name in KNOWN else "OFF"
        print(f"  {mark} {name}: {got} (summary {expected})"
              + (f" — {KNOWN[name]}" if not same and name in KNOWN else ""))
    print("names:", [p.name for p in sheet.products[:5]])
    return ok


def _same(got, expected) -> bool:
    if isinstance(got, tuple) and isinstance(expected, tuple):
        return len(got) == len(expected) and all(_same(a, b) for a, b in zip(got, expected,
                                                                              strict=True))
    if got is None:
        return False
    return Decimal(str(got)) == Decimal(str(expected))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--replace-demo-commissions", action="store_true",
                        help="remove the account's DEMO-seed ledger entries")
    args = parser.parse_args()
    with SessionLocal() as db:
        sys.exit(run(db, apply=args.apply, replace_demo=args.replace_demo_commissions))


if __name__ == "__main__":
    main()

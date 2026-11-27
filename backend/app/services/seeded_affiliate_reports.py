"""Seeded marketplace reports — the owner's plan for testing the money path
before real buyers exist (2026-09-28).

THE PROBLEM. A commission reaches Bluntly only through a marketplace report
(Shopee's Affiliate Commission Report, Lazada's Conversion Report) whose rows
carry OUR sub-ID, and a row only exists after a real buyer purchases through a
reviewer's link. Until then the platforms' own exports come back empty, so the
import -> match -> split -> reconcile -> report chain has nothing to run on.

THE PLAN (owner, agreed). Produce files in each marketplace's REAL export
shape, pre-filled with the sub-IDs of real active referral links, and submit
them through Bluntly's normal importer. Everything downstream — matching,
the 40/30/30 split, the ledger, remittance clearing, payouts, the reports —
then runs exactly as it will on a real export. Two ways to make one, both
inside the system:

    synthesize   rows invented from the active links (deterministic amounts,
                 a few non-payable rows to exercise skipping)
    fill         take a real export the team downloaded from Shopee/Lazada and
                 write our sub-IDs into its rows (the owner's "fill those values")

Lazada also has a signed API (`adapters.lazada.fetch_conversions`); it returns
the same data as the export and will replace the file for Lazada once real
conversions exist. Shopee offers no API, so its file stays the path.

SAFETY. Seeded rows are marked: every order reference starts with
`BLUNTLY-SEED-`. Generation is refused on production, and — the net that
matters — both importers refuse any file containing a seeded row when running
on production (`refuse_seeded_rows_in_production`), because importing one there
would credit real wallets with money no buyer paid.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_guard import production_signals
from app.core.errors import AppError
from app.models.enums import Platform, ReferralLinkStatus
from app.models.product import Product
from app.models.review import ReferralLink, Review
from app.services import report_formats

SEED_PREFIX = "BLUNTLY-SEED-"

#: The real exports' headers, column for column (tests/fixtures/*.csv are the
#: owner-supplied originals these were read from).
SHOPEE_COLUMNS = [
    "Order id", "Order Status", "Conversion id", "Order Time", "Complete Time", "Click Time",
    "Shop Name", "Shop id", "Shop Type", "Item id", "Item Name", "Model id", "Product Type",
    "Promotion id", "L1 Global Category", "L2 Global Category", "L3 Global Category",
    "Price(₱)", "Qty", "Offer Type", "Campaign Partner", "Purchase Value(₱)",
    "Refund Amount(₱)", "Item Shopee Commission Rate", "Item Shopee Commission(₱)",
    "Item Seller Commission Rate", "Item Seller Commission(₱)", "Item Total Commission(₱)",
    "Order Shopee Commission(₱)", "Order Seller Commission(₱)", "Total Order Commission(₱)",
    "Linked MCN Name", "MCN Contract id", "MCN Management Fee Rate", "MCN Management Fee(₱)",
    "Affiliate Agreement Fee Rate", "Affiliate Net Commission(₱)", "Affiliate Item Status",
    "Item Note", "Attribution Type", "Buyer Status", "Sub_id1", "Sub_id2", "Sub_id3",
    "Sub_id4", "Sub_id5", "Channel"]
LAZADA_COLUMNS = [
    "Conversion Time", "Fulfilled Time", "Delivered Time", "Returned Time", "Offer ID",
    "Product ID", "Product Name", "Status", "Platform", "Country", "Check Out ID",
    "Sku Order ID", "Sub Order ID", "SKU", "SKU Name", "Category L1", "Brand ID", "Brand Name",
    "Seller ID", "Seller Name", "Commission Rate", "New User", "Payout", "Currency",
    "Aff Sub ID", "Validity", "Order Amount", "Adjustment", "Invite Id", "Invite Name",
    "DM offerId", "DM Start Time", "DM End Time", "DM Commission Rate", "DM Commission Fee",
    "Guided Type", "Is Code", "Attribution", "Payment Advice ID", "Payment Bill Period",
    "Payment Status", "Sub ID 1", "Sub ID 2", "Sub ID 3", "Sub ID 4", "Sub ID 5", "Sub ID 6"]

#: Where our identifier goes, and which columns identify the order, per platform.
_SUB_ID_COLUMN = {"shopee": "Sub_id1", "lazada": "Aff Sub ID"}
_ORDER_COLUMNS = {"shopee": ("Order id", "Conversion id"),
                  "lazada": ("Check Out ID", "Sku Order ID", "Sub Order ID")}

MAX_ROWS = 5000


def _refuse(detail: str, code: str, status: int = 409) -> AppError:
    return AppError(detail, code=code, status_code=status, title="Seeded report refused")


def running_on_production() -> bool:
    """Any sign this process serves production: the setting, or a connection
    that points at the production project (env_guard's multi-signal check)."""
    return settings.is_production or bool(production_signals())


def refuse_seeded_rows_in_production(order_refs) -> None:
    """The importers' net: a seeded row never becomes money on production."""
    if not running_on_production():
        return
    if any((ref or "").startswith(SEED_PREFIX) for ref in order_refs):
        raise AppError("This file contains seeded test rows (BLUNTLY-SEED-). Seeded "
                       "marketplace reports are for the test environment only; nothing "
                       "was imported.", code="seeded_report_in_production", status_code=422,
                       title="Seeded report refused")


@dataclass(frozen=True)
class SeedLink:
    sub_id: str
    review_ref: str | None
    product: str | None


def active_links(db: Session, platform: Platform) -> list[SeedLink]:
    """The platform's active links, newest first.

    Newest first because a seeded report has a fixed number of rows (a real
    export is ~100), and the links the team is testing are the ones they just
    approved; the oldest links would otherwise take every row.
    """
    rows = db.execute(
        select(ReferralLink.sub_id, Review.review_id, Product.canonical_name)
        .join(Review, Review.id == ReferralLink.review_id)
        .outerjoin(Product, Product.id == Review.product_id)
        .where(ReferralLink.platform == platform,
               ReferralLink.status == ReferralLinkStatus.active,
               ReferralLink.sub_id.is_not(None), Review.author_id.is_not(None),
               Review.is_removed.is_(False))
        .order_by(ReferralLink.created_at.desc(), ReferralLink.id.desc())).all()
    return [SeedLink(sub_id=s, review_ref=r, product=p) for s, r, p in rows]


def _amount(seed: str, index: int) -> Decimal:
    """A deterministic commission between 12.00 and 211.99 for row `index`."""
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    cents = 1200 + int.from_bytes(digest[:4], "big") % 20000
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


def _stamp(cycle: date, index: int, fmt: str) -> str:
    day = 1 + (index * 7) % 27
    moment = datetime(cycle.year, cycle.month, day, 10 + index % 10, (index * 13) % 60, 0)
    return moment.strftime(fmt)


def _synth_row(platform: str, cycle: date, link: SeedLink, index: int, amount: Decimal,
               payable: bool, tag: str) -> dict[str, str]:
    order = f"{SEED_PREFIX}{tag}-{index:04d}"
    name = (link.product or "Seeded product")[:120]
    if platform == "shopee":
        status = "Completed" if payable else ("Pending" if index % 2 else "Cancelled")
        row = dict.fromkeys(SHOPEE_COLUMNS, "")
        row.update({
            "Order id": order, "Order Status": status, "Conversion id": f"CNV{order}",
            "Order Time": _stamp(cycle, index, "%Y-%m-%d %H:%M:%S"),
            "Complete Time": _stamp(cycle, index, "%Y-%m-%d %H:%M:%S") if payable else "--",
            "Click Time": _stamp(cycle, index, "%Y-%m-%d %H:%M:%S"),
            "Shop Name": "Seeded shop", "Item id": f"{index + 1}", "Item Name": name,
            "Model id": "1", "Promotion id": "", "Qty": "1",
            "Purchase Value(₱)": f"{(amount * 20):.2f}", "Refund Amount(₱)": "0",
            "Total Order Commission(₱)": f"{amount:.2f}",
            "Affiliate Agreement Fee Rate": "100%",
            "Affiliate Net Commission(₱)": f"{amount:.2f}",
            "Affiliate Item Status": status, "Attribution Type": "Ordered in Same Shop",
            "Buyer Status": "Existing", "Sub_id1": link.sub_id, "Channel": "Others"})
        return row
    status = "Delivered" if payable else ("Rejected" if index % 2 else "Returned")
    row = dict.fromkeys(LAZADA_COLUMNS, "")
    row.update({
        "Conversion Time": _stamp(cycle, index, "%Y-%m-%d"),
        "Delivered Time": _stamp(cycle, index, "%Y-%m-%d") if payable else "-",
        "Product Name": name, "Status": status, "Platform": "App", "Country": "PH",
        "Check Out ID": order, "Sku Order ID": f"{order}-SKU", "Sub Order ID": f"{order}-SUB",
        "Seller Name": "Seeded shop", "Commission Rate": "5%", "New User": "N",
        "Payout": f"{amount:.2f}", "Currency": "PHP", "Aff Sub ID": link.sub_id,
        "Validity": "valid" if payable else "invalid",
        "Order Amount": f"{(amount * 20):.2f}", "Payment Status": "-"})
    return row


def synthesize(db: Session, platform: Platform, cycle: date, *, rows_per_link: int = 1,
               include_unpayable: bool = True, seed: str = "bluntly") -> bytes:
    """A report in `platform`'s real export shape, one row per link (x N)."""
    _require_not_production()
    if platform not in (Platform.shopee, Platform.lazada):
        raise _refuse("Seeded reports exist for Shopee and Lazada only.",
                      "seeded_platform_unsupported", 422)
    links = active_links(db, platform)
    if not links:
        raise _refuse(f"No active {platform.value} referral links to seed a report for. "
                      "Attach an affiliate link first.", "seeded_no_active_links")
    tag = f"{cycle:%Y%m}-{hashlib.sha256(seed.encode()).hexdigest()[:6].upper()}"
    rows: list[dict[str, str]] = []
    index = 0
    for link in links:
        for _ in range(max(1, rows_per_link)):
            rows.append(_synth_row(platform.value, cycle, link, index,
                                   _amount(seed, index), True, tag))
            index += 1
    if include_unpayable:
        # Not money: the importer must skip these and say so.
        for link in links[:2]:
            rows.append(_synth_row(platform.value, cycle, link, index, _amount(seed, index),
                                   False, tag))
            index += 1
    if len(rows) > MAX_ROWS:
        raise _refuse(f"A seeded report holds at most {MAX_ROWS} rows.", "seeded_too_large", 422)
    columns = SHOPEE_COLUMNS if platform == Platform.shopee else LAZADA_COLUMNS
    return _write(columns, rows)


def fill_template(db: Session, platform: Platform, template: bytes) -> bytes:
    """The owner's plan verbatim: a real export, with our sub-IDs written in.

    Every row keeps the marketplace's own values (status, amounts, dates);
    the sub-ID column is filled round-robin from the active links, and the
    order references are prefixed so a seeded row can always be told apart.
    """
    _require_not_production()
    text = report_formats._decode(template)
    reader = list(csv.reader(io.StringIO(text)))
    if not reader:
        raise _refuse("The uploaded file is empty.", "seeded_template_empty", 422)
    header = reader[0]
    fmt = report_formats.detect_format(header)
    expected = ("shopee_commission_report" if platform == Platform.shopee
                else "lazada_conversion_report")
    if fmt != expected:
        raise _refuse(f"That file is not a {platform.value} export.", "seeded_template_wrong",
                      422)
    if len(reader) - 1 > MAX_ROWS:
        raise _refuse(f"A seeded report holds at most {MAX_ROWS} rows.", "seeded_too_large", 422)
    links = active_links(db, platform)
    if not links:
        raise _refuse(f"No active {platform.value} referral links to seed a report for.",
                      "seeded_no_active_links")
    norm = [report_formats._norm(c) for c in header]
    sub_col = norm.index(report_formats._norm(_SUB_ID_COLUMN[platform.value]))
    order_cols = [norm.index(report_formats._norm(c)) for c in _ORDER_COLUMNS[platform.value]
                  if report_formats._norm(c) in norm]
    out_rows = []
    for i, values in enumerate(reader[1:]):
        if not any(v.strip() for v in values):
            continue
        values = values + [""] * (len(header) - len(values))
        values[sub_col] = links[i % len(links)].sub_id
        for col in order_cols:
            if values[col].strip() and not values[col].startswith(SEED_PREFIX):
                values[col] = SEED_PREFIX + values[col].strip()
        out_rows.append(dict(zip(header, values, strict=False)))
    return _write(header, out_rows)


def _require_not_production() -> None:
    if running_on_production():
        raise _refuse("Seeded marketplace reports are disabled on production.",
                      "seeded_reports_disabled_in_production", 403)


def _write(columns: list[str], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\r\n",
                            extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def default_cycle(today: date) -> date:
    """The previous calendar month: the cycle a real monthly export covers."""
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)

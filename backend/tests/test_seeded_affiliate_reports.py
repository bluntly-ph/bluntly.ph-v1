"""The owner's plan for testing the money path before real buyers exist.

A seeded report in the marketplace's REAL export shape, pre-filled with our
sub-IDs, goes through Bluntly's normal importer, matches, splits, and shows up
in the Commission and Payout Report — and none of it can happen on production.
"""

from __future__ import annotations

import csv
import io
import pathlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import extract, select

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import EarnEligibleStatus, MemberRole, Platform, ReferralLinkStatus, Verdict
from app.models.product import Product
from app.models.review import ReferralLink, Review
from app.models.user import User
from app.services import earnings, report_formats, seeded_affiliate_reports
from tests.conftest import requires_db

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _staff() -> dict:
    db = SessionLocal()
    try:
        u = User(email=f"seed_{uuid.uuid4().hex}@example.com", password_hash="x",
                 role=MemberRole.administrator)
        db.add(u)
        db.commit()
        return {"Authorization": f"Bearer {create_access_token(u.id, 'moderator')}"}
    finally:
        db.close()


def _linked_review(platform: Platform) -> tuple[str, uuid.UUID]:
    db = SessionLocal()
    try:
        author = User(email=f"seedauthor_{uuid.uuid4().hex}@example.com", password_hash="x",
                      username=f"seed_{uuid.uuid4().hex[:10]}")
        product = Product(canonical_name=f"Seeded Product {uuid.uuid4().hex[:6]}")
        db.add_all([author, product])
        db.flush()
        review = Review(product_id=product.id, author_id=author.id, title="Seeded review",
                        discussion="Body text for the seeded review.",
                        verdict=Verdict.yes_absolutely, star_rating=Decimal("5"),
                        earn_eligible_status=EarnEligibleStatus.monetized,
                        published_at=datetime.now(UTC))
        db.add(review)
        db.flush()
        sub_id = f"blt_{uuid.uuid4().hex[:10]}"
        db.add(ReferralLink(review_id=review.id, platform=platform, url="https://x.ph/p",
                            sub_id=sub_id, status=ReferralLinkStatus.active, review_version=1))
        db.commit()
        return sub_id, review.id
    finally:
        db.close()


def _free_year() -> int:
    db = SessionLocal()
    try:
        used = {int(y) for y in db.scalars(
            select(extract("year", Commission.cycle_month)).distinct())}
    finally:
        db.close()
    # A past year no other row uses; never the future (see test_reporting_api).
    return next(y for y in range(2019, 1971, -1) if y not in used)


def _rows(content: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")


# ---------------------------------------------------------------- pure shape

def test_the_generated_columns_are_the_real_exports_columns():
    for name, columns, enc in (("shopee_commission_report.csv",
                                seeded_affiliate_reports.SHOPEE_COLUMNS, "utf-8-sig"),
                               ("lazada_conversion_report.csv",
                                seeded_affiliate_reports.LAZADA_COLUMNS, "cp1252")):
        real = next(csv.reader(io.StringIO((FIXTURES / name).read_bytes().decode(enc))))
        assert real == columns, name


# ---------------------------------------------------------------- end to end

@requires_db
@pytest.mark.parametrize("platform", [Platform.shopee, Platform.lazada])
def test_seeded_report_imports_and_reports(client, platform):
    sub_id, review_id = _linked_review(platform)
    year = _free_year()
    staff = _staff()

    r = client.get(f"/api/v1/admin/affiliate/seeded-report?platform={platform.value}"
                   f"&month=6&year={year}&seed=t{uuid.uuid4().hex[:6]}", headers=staff)
    assert r.status_code == 200, r.text
    assert r.headers["content-disposition"] == \
        f'attachment; filename="bluntly-seeded-{platform.value}-{year}-06.csv"'
    parsed = report_formats.parse(r.content)
    assert parsed.format == ("shopee_commission_report" if platform == Platform.shopee
                             else "lazada_conversion_report")
    # Up to two unpayable rows (one per link, for the first two links): skipped, not paid.
    assert parsed.errors == [] and 1 <= len(parsed.skipped) <= 2
    ours = [row for row in parsed.rows if row.sub_id == sub_id]
    assert len(ours) == 1 and ours[0].order_ref.startswith("BLUNTLY-SEED-")
    gross = ours[0].gross_amount

    imported = client.post("/api/v1/admin/affiliate/import", headers=staff,
                           files={"file": ("seeded.csv", r.content, "text/csv")})
    assert imported.status_code == 200, imported.text
    assert imported.json()["recognised"] >= 1

    db = SessionLocal()
    try:
        [commission] = db.scalars(select(Commission).where(Commission.review_id == review_id))
        assert commission.gross_amount == gross
        canonical = earnings.split_commission(gross)
        assert (commission.platform_share, commission.reviewer_share,
                commission.honesty_fund_share) == (canonical["platform_share"],
                                                   canonical["reviewer_share"],
                                                   canonical["honesty_fund_share"])
        assert commission.cycle_month.year == year and commission.cycle_month.month == 6
    finally:
        db.close()

    report = client.get(f"/api/v1/admin/reports/commissions-payouts?month=6&year={year}"
                        "&limit=5000", headers=staff).json()
    [row] = [c for c in report["commissions"] if c["sub_id"] == sub_id]
    assert row["imported_commission"] == f"{gross:.2f}"
    assert row["reviewer_share"] == f"{canonical['reviewer_share']:.2f}"
    assert row["reconciliation_status"] == "awaiting_remittance"

    # Importing the same seeded file again credits nothing twice.
    again = client.post("/api/v1/admin/affiliate/import", headers=staff,
                        files={"file": ("seeded.csv", r.content, "text/csv")})
    assert again.status_code == 200 and again.json()["recognised"] == 0


@requires_db
def test_fill_a_real_export_with_our_sub_ids(client):
    sub_id, _ = _linked_review(Platform.shopee)
    staff = _staff()
    real = (FIXTURES / "shopee_commission_report.csv").read_bytes()
    r = client.post("/api/v1/admin/affiliate/seeded-report/fill?platform=shopee",
                    headers=staff, files={"file": ("export.csv", real, "text/csv")})
    assert r.status_code == 200, r.text
    rows = _rows(r.content)
    assert len(rows) == 108
    assert all(row["Sub_id1"] for row in rows)
    assert all(row["Order id"].startswith("BLUNTLY-SEED-") for row in rows)
    assert sub_id in {row["Sub_id1"] for row in rows}
    # The marketplace's own values are untouched.
    original = _rows(real.replace(b"\xef\xbb\xbf", b"", 1) if real.startswith(b"\xef\xbb\xbf")
                     else real)
    assert [row["Affiliate Net Commission(₱)"] for row in rows] == \
        [row["Affiliate Net Commission(₱)"] for row in original]
    wrong = client.post("/api/v1/admin/affiliate/seeded-report/fill?platform=lazada",
                        headers=staff, files={"file": ("export.csv", real, "text/csv")})
    assert wrong.status_code == 422 and wrong.json()["code"] == "seeded_template_wrong"


@requires_db
def test_only_staff_generate_seeded_reports(client):
    url = "/api/v1/admin/affiliate/seeded-report?platform=shopee"
    assert client.get(url).status_code == 401
    db = SessionLocal()
    try:
        u = User(email=f"plain_{uuid.uuid4().hex}@example.com", password_hash="x")
        db.add(u)
        db.commit()
        headers = {"Authorization": f"Bearer {create_access_token(u.id, 'user')}"}
    finally:
        db.close()
    assert client.get(url, headers=headers).status_code == 403


# ---------------------------------------------------------------- production

@requires_db
def test_generation_is_refused_on_production(client, production):
    _linked_review(Platform.shopee)
    r = client.get("/api/v1/admin/affiliate/seeded-report?platform=shopee", headers=_staff())
    assert r.status_code == 403 and r.json()["code"] == "seeded_reports_disabled_in_production"


@requires_db
def test_importers_refuse_seeded_rows_on_production(client, monkeypatch):
    sub_id, _ = _linked_review(Platform.shopee)
    staff = _staff()
    seeded = client.get(f"/api/v1/admin/affiliate/seeded-report?platform=shopee&month=6"
                        f"&year={_free_year()}", headers=staff).content
    monkeypatch.setattr(settings, "app_env", "production")
    for path in ("/api/v1/admin/affiliate/import", "/api/v1/admin/affiliate/preview",
                 "/api/v1/admin/commissions/import"):
        r = client.post(path, headers=staff, files={"file": ("seeded.csv", seeded, "text/csv")})
        assert r.status_code == 422, (path, r.text)
        assert r.json()["code"] == "seeded_report_in_production"

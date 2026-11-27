"""The financial report (Reports screen + Generate report PDF), against a real
database, with exact money.

One deterministic world in a cycle YEAR no other row uses (the CI database is
cumulative), built through the split function the importers call:

    Y-08  Shopee 100.00 (RA, Yes 5*)                        -> remitted 90.00 on Y-09-10
    Y-09  Shopee 100.00 cleared   (RA)                      40.00 / 30.00 / 30.00
          Lazada  50.00           (RA)                      20.00 / 15.00 / 15.00
          Shopee  20.00 returned  (RA), 6.00 unrecoverable   8.00 /  6.00 /  6.00, then negated
          Shopee  40.00           (RB, Hard pass: fund)     16.00 /  0.00 / 24.00
          QA sandbox test earning 500.00                   excluded from revenue
          a Lazada order still pending (no commission)
    payouts: 300.00 paid Y-09-15, 120.00 failed in Y-09, 75.00 still to send
    Honesty Fund for Y-08 credited Y-09-01: 12.50
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import extract, select

from app.core.errors import AppError
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import (
    AffiliateTxStatus,
    CommissionTarget,
    EarnEligibleStatus,
    MemberRole,
    PayoutMethod,
    PayoutStatus,
    Platform,
    SettlementStatus,
    Verdict,
    VerificationStatus,
)
from app.models.honesty_fund import HonestyFundDistribution
from app.models.payout import Payout
from app.models.postback import AffiliatePostback
from app.models.product import Product
from app.models.review import Review
from app.models.triage import PlatformSetting
from app.models.user import User
from app.services import earnings, wallet
from app.services.reporting import financial, financial_pdf, periods
from tests.conftest import requires_db

D = Decimal


# ------------------------------------------------------------------ periods and labels

def test_quarter_resolves_and_is_validated():
    q = periods.resolve(quarter=2, year=2026)
    assert (q.start, q.end, q.kind, q.label, q.slug) == (
        date(2026, 4, 1), date(2026, 6, 30), "quarter", "Q2 2026", "2026-Q2")
    assert q.cycle_months == [date(2026, 4, 1), date(2026, 5, 1), date(2026, 6, 1)]
    for bad in ({"quarter": 2}, {"quarter": 5, "year": 2026},
                {"quarter": 1, "month": 2, "year": 2026},
                {"quarter": 1, "start_date": date(2026, 1, 1), "end_date": date(2026, 1, 2)}):
        with pytest.raises(AppError):
            periods.resolve(**bad)


def test_labels_read_like_the_design():
    sep = periods.resolve(month=9, year=2026)
    assert financial.span(sep) == "1–30 September 2026"
    assert financial.span(sep, short=True) == "1–30 Sep 2026"
    assert financial.title_for(sep) == "September 2026"
    assert financial.period_column(periods.resolve(quarter=2, year=2026)) == "Apr–Jun 2026"
    rng = periods.resolve(start_date=date(2025, 12, 28), end_date=date(2026, 1, 3))
    assert financial.span(rng, short=True) == "28 Dec 2025 – 3 Jan 2026"
    assert financial.in_label(sep) == "in September"


def test_unknown_or_empty_sections_are_refused():
    assert financial.clean_sections(["liabilities", "revenue"]) == ["revenue", "liabilities"]
    for bad in ([], ["revenue", "secrets"]):
        with pytest.raises(AppError):
            financial.clean_sections(bad)


# ------------------------------------------------------------------ the world

def _free_year(db) -> int:
    used = {int(y) for y in db.scalars(
        select(extract("year", Commission.cycle_month)).distinct())}
    used |= {int(y) for y in db.scalars(
        select(extract("year", MarketplaceRemittance.cycle_month)).distinct())}
    used |= {int(y) for y in db.scalars(
        select(extract("year", Payout.created_at)).distinct())}
    for year in range(2018, 1971, -1):
        if year not in used:
            return year
    raise AssertionError("no free report year")


def _user(db, **kw) -> User:
    u = User(email=f"fin_{uuid.uuid4().hex}@example.com", password_hash="x",
             display_name=kw.pop("display_name", "Finance Fixture"),
             username=f"fin_{uuid.uuid4().hex[:12]}", **kw)
    db.add(u)
    db.flush()
    return u


def _review(db, author, product, verdict, stars, status) -> Review:
    r = Review(product_id=product.id, author_id=author.id, title=f"Fixture {verdict.value}",
               discussion="Body text for the fixture review.", verdict=verdict,
               star_rating=D(str(stars)), earn_eligible_status=status,
               verification_status=VerificationStatus.verified,
               published_at=datetime.now(UTC))
    db.add(r)
    db.flush()
    return r


def _commission(db, review, author, gross: str, platform: Platform, cycle: date,
                *, cleared: bool = False, **kw) -> Commission:
    split, bps = earnings.split_for_review(D(gross), review, author)
    c = Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                   target_type=CommissionTarget.review, review_id=review.id,
                   reviewer_id=author.id, reviewer_share_bps=bps, platform=platform,
                   cleared_at=datetime.now(UTC) if cleared else None, currency="PHP",
                   csv_source=f"fin-test:{uuid.uuid4().hex[:8]}",
                   row_reference=uuid.uuid4().hex, order_status="Completed",
                   cycle_month=cycle, **split, **kw)
    db.add(c)
    wallet.adjust(db, author.id, split["reviewer_share"])
    db.flush()
    return c


@pytest.fixture(scope="module")
def world():
    db = SessionLocal()
    try:
        year = _free_year(db)
        aug, sep = date(year, 8, 1), date(year, 9, 1)
        staff = _user(db, role=MemberRole.administrator, display_name="Zient P.")
        a = _user(db)
        b = _user(db)
        product = Product(canonical_name=f"Finance Product {uuid.uuid4().hex[:6]}")
        db.add(product)
        db.flush()
        ra = _review(db, a, product, Verdict.yes_absolutely, 5, EarnEligibleStatus.monetized)
        rb = _review(db, b, product, Verdict.hard_pass, 1, EarnEligibleStatus.honesty_fund)

        _commission(db, ra, a, "100.00", Platform.shopee, aug, cleared=True)
        _commission(db, ra, a, "100.00", Platform.shopee, sep, cleared=True)
        _commission(db, ra, a, "50.00", Platform.lazada, sep)
        returned = _commission(db, ra, a, "20.00", Platform.shopee, sep)
        db.add(Commission(
            commission_id=f"rev_{uuid.uuid4().hex[:12]}", target_type=CommissionTarget.review,
            review_id=ra.id, reviewer_id=a.id, platform=Platform.shopee, currency="PHP",
            csv_source=returned.csv_source, row_reference=f"{returned.row_reference}#reversal",
            order_status="returned", cycle_month=sep, reverses_commission_id=returned.id,
            gross_amount=-returned.gross_amount, platform_share=-returned.platform_share,
            reviewer_share=-returned.reviewer_share,
            honesty_fund_share=-returned.honesty_fund_share))
        db.add(AffiliatePostback(
            platform=Platform.shopee, external_sub_order_id=f"fin-{uuid.uuid4().hex[:10]}",
            canonical_status=AffiliateTxStatus.returned,
            settlement_status=SettlementStatus.reversed, reported_payout=D("20.00"),
            reconciled_commission_id=returned.id, unrecovered_amount=D("6.00"),
            received_at=datetime(year, 9, 5, tzinfo=UTC)))
        db.add(AffiliatePostback(
            platform=Platform.lazada, external_sub_order_id=f"fin-{uuid.uuid4().hex[:10]}",
            canonical_status=AffiliateTxStatus.pending, reported_payout=D("9.00"),
            received_at=datetime(year, 9, 6, tzinfo=UTC)))
        _commission(db, rb, b, "40.00", Platform.shopee, sep)
        # A QA sandbox test earning: the tester's alone, never revenue.
        test_split = {"gross_amount": D("500.00"), "platform_share": D("0.00"),
                      "reviewer_share": D("500.00"), "honesty_fund_share": D("0.00")}
        db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                          target_type=CommissionTarget.review, review_id=rb.id,
                          reviewer_id=b.id, platform=Platform.shopee, currency="PHP",
                          csv_source="qa_sandbox", row_reference=uuid.uuid4().hex,
                          order_status="qa_sandbox", cycle_month=sep, is_test=True,
                          cleared_at=datetime.now(UTC), **test_split))

        db.add(MarketplaceRemittance(platform=Platform.shopee, cycle_month=aug,
                                     amount_received=D("90.00"),
                                     received_on=date(year, 9, 10), reference="SHP-AUG",
                                     recorded_by_id=staff.id))
        for amount, status, created, paid, updated in (
                ("300.00", PayoutStatus.paid, datetime(year, 9, 12, tzinfo=UTC),
                 datetime(year, 9, 15, tzinfo=UTC), datetime(year, 9, 15, tzinfo=UTC)),
                ("120.00", PayoutStatus.failed, datetime(year, 9, 13, tzinfo=UTC), None,
                 datetime(year, 9, 14, tzinfo=UTC)),
                ("75.00", PayoutStatus.scheduled, datetime(year, 9, 20, tzinfo=UTC), None,
                 datetime(year, 9, 20, tzinfo=UTC))):
            db.add(Payout(payout_id=f"pay_{uuid.uuid4().hex[:12]}", user_id=a.id,
                          amount=D(amount), status=status, method=PayoutMethod.manual,
                          scheduled_for=created.date(), created_at=created, paid_at=paid,
                          updated_at=updated))
        # A QA payout through the PayPal sandbox: no real money left (Vash's design).
        db.add(Payout(payout_id=f"pay_{uuid.uuid4().hex[:12]}", user_id=a.id,
                      amount=D("350.00"), status=PayoutStatus.paid,
                      method=PayoutMethod.paypal_sandbox,
                      scheduled_for=date(year, 9, 16), created_at=datetime(year, 9, 16, tzinfo=UTC),
                      paid_at=datetime(year, 9, 16, 1, tzinfo=UTC),
                      updated_at=datetime(year, 9, 16, 1, tzinfo=UTC)))
        db.add(HonestyFundDistribution(
            distribution_id=f"hfd_{uuid.uuid4().hex[:12]}", cycle_month=aug, review_id=rb.id,
            reviewer_id=b.id, honesty_score=D("1.0000"), pool_amount=D("30.00"),
            payout_amount=D("12.50"), created_at=datetime(year, 9, 1, 1, 0, tzinfo=UTC)))
        db.commit()
        yield {"year": year, "staff": staff.id, "a": a.id}
    finally:
        db.close()


def _september(world) -> periods.Period:
    return periods.resolve(month=9, year=world["year"])


def _auth(user_id, role="user") -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


# ------------------------------------------------------------------ figures

@requires_db
def test_revenue_and_split_are_exact(world):
    with SessionLocal() as db:
        r = financial.build(db, _september(world)).revenue
    assert (r.earned, r.reversed, r.net, r.absorbed) == (
        D("210.00"), D("20.00"), D("190.00"), D("6.00"))
    shares = {s.key: s.amount for s in r.shares}
    # Platform 40 + 20 + 8 - 8 + 16; reviewers 30 + 15 + 6 - 6 + 0; fund 30 + 15 + 6 - 6 + 24.
    assert shares == {"bluntly": D("76.00"), "reviewers": D("45.00"),
                      "honesty_fund": D("69.00")}
    assert sum(shares.values()) == r.net
    assert round(sum(s.rate for s in r.shares), 6) == 100
    by = {m.marketplace: (m.orders, m.commissions, m.earned) for m in r.by_marketplace}
    # Lazada: one commission plus the pending order that earned nothing.
    assert by == {"shopee": (3, 3, D("160.00")), "lazada": (2, 1, D("50.00"))}


@requires_db
def test_money_in_out_and_kpis(world):
    year = world["year"]
    with SessionLocal() as db:
        report = financial.build(db, _september(world))
    rows = [(r.marketplace, r.cycle_month, r.expected, r.received, r.shortfall, r.status)
            for r in report.money_in.rows]
    assert rows == [
        ("shopee", date(year, 8, 1), D("100.00"), D("90.00"), D("10.00"), "cleared"),
        ("shopee", date(year, 9, 1), D("140.00"), None, None, "clearing"),
        ("lazada", date(year, 9, 1), D("50.00"), None, None, "clearing"),
    ]
    assert (report.money_in.received_total, report.money_in.shortfall_total) == (
        D("90.00"), D("10.00"))
    out = report.money_out
    assert (out.sent.count, out.sent.amount) == (1, D("300.00"))
    assert (out.failed.count, out.failed.amount) == (1, D("120.00"))
    assert (out.to_send.count, out.to_send.amount) == (1, D("75.00"))
    assert (out.cancelled.count, out.cancelled.amount) == (0, D("0.00"))
    [credit] = out.honesty_fund
    assert (credit.cycle_month, credit.count, credit.amount) == (date(year, 8, 1), 1, D("12.50"))
    # The fund credit went to wallets: paid out is the payouts sent, once.
    assert out.paid_out_total == D("300.00")
    # The sandbox payout moved no real money: counted apart, said in the notes.
    assert (out.sandbox_excluded.count, out.sandbox_excluded.amount) == (1, D("350.00"))
    assert any("PayPal sandbox" in n and "₱350.00" in n for n in report.meta.notes)
    k = report.kpis
    assert (k.net_commission, k.money_in, k.money_out) == (D("190.00"), D("90.00"),
                                                           D("300.00"))
    assert k.still_owed == report.liabilities.cleared_in_wallets


@requires_db
def test_liabilities_split_wallets_into_cleared_and_clearing(db):
    period = periods.resolve(month=1, year=1975)
    before = financial.build(db, period).liabilities
    member = User(email=f"fin_{uuid.uuid4().hex}@example.com", password_hash="x",
                  display_name="Wallet Fixture", wallet_balance=D("500.00"))
    db.add(member)
    db.flush()
    product = Product(canonical_name=f"Finance Product {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    review = _review(db, member, product, Verdict.yes_absolutely, 5,
                     EarnEligibleStatus.monetized)
    db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                      target_type=CommissionTarget.review, review_id=review.id,
                      reviewer_id=member.id, platform=Platform.shopee, currency="PHP",
                      csv_source="fin-liab", row_reference=uuid.uuid4().hex,
                      cycle_month=date(1975, 1, 1), gross_amount=D("666.67"),
                      platform_share=D("266.67"), reviewer_share=D("200.00"),
                      honesty_fund_share=D("200.00")))
    db.flush()
    after = financial.build(db, period).liabilities
    assert after.cleared_in_wallets - before.cleared_in_wallets == D("300.00")
    assert after.still_clearing - before.still_clearing == D("200.00")


# ------------------------------------------------------------------ PDF and API

@requires_db
def test_pdf_renders_the_selected_sections(world):
    with SessionLocal() as db:
        report = financial.build(db, _september(world))
    pdf, pages = financial_pdf.render(report, list(financial.SECTIONS),
                                      generated_by="Zient P.")
    assert pdf.startswith(b"%PDF") and pages == 2
    one, single = financial_pdf.render(report, ["liabilities"])
    assert single == 1 and len(one) < len(pdf)
    assert financial_pdf.filename(report) == f"bluntly-financial-report-{world['year']}-09.pdf"


def test_long_tables_continue_on_new_pages():
    from app.schemas.reporting import (
        FinancialCountAmount,
        FinancialKpis,
        FinancialLiabilities,
        FinancialMoneyIn,
        FinancialMoneyInRow,
        FinancialMoneyOut,
        FinancialReportOut,
        FinancialRevenue,
        ReportMeta,
        ReportPeriod,
    )

    period = periods.resolve(year=2026)
    zero = FinancialCountAmount(count=0, amount=D("0.00"))
    rows = [FinancialMoneyInRow(marketplace="shopee", cycle_month=date(2026, 1, 1),
                                expected=D("1.00"), status="clearing") for _ in range(70)]
    now = datetime(2026, 10, 2, 6, 20, tzinfo=UTC)
    report = FinancialReportOut(
        meta=ReportMeta(title="Financial report", period=ReportPeriod(**period.as_dict()),
                        generated_at=now),
        span=financial.span(period), span_short=financial.span(period, short=True),
        kpis=FinancialKpis(net_commission=D("0"), money_in=D("0"), money_out=D("0"),
                           still_owed=D("0")),
        revenue=FinancialRevenue(earned=D("0"), reversed=D("0"), absorbed=D("0"), net=D("0")),
        money_in=FinancialMoneyIn(rows=rows, received_total=D("0"), shortfall_total=D("0")),
        money_out=FinancialMoneyOut(sent=zero, to_send=zero, failed=zero, cancelled=zero,
                                    paid_out_total=D("0")),
        liabilities=FinancialLiabilities(as_of=now, cleared_in_wallets=D("0"),
                                         payouts_to_send=D("0"), still_clearing=D("0"),
                                         unattributed=D("0"), unattributed_count=0))
    _, pages = financial_pdf.render(report, ["money_in"])
    assert pages == 4  # 70 rows of 27 pt over pages of ~650 pt


@requires_db
def test_generate_logs_and_downloads_again(client, world):
    staff = _auth(world["staff"], "administrator")
    year = world["year"]
    with SessionLocal() as db:
        saved = db.get(PlatformSetting, financial.LOG_KEY)
        before = None if saved is None else dict(saved.value)
    try:
        r = client.post("/api/v1/admin/reports/financial/generate", headers=staff,
                        json={"kind": "month", "year": year, "month": 9,
                              "sections": ["money_out", "revenue"]})
        assert r.status_code == 201, r.text
        entry = r.json()
        assert entry["sections"] == ["revenue", "money_out"]
        assert entry["title"] == f"Financial report · September {year}"
        assert entry["span_short"] == f"1–30 Sep {year}"
        assert entry["generated_by"] == "Zient P." and entry["pages"] >= 1

        listed = client.get("/api/v1/admin/reports/financial/history", headers=staff).json()
        assert listed[0]["id"] == entry["id"]

        pdf = client.get(entry["download_path"], headers=staff)
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
        assert f"bluntly-financial-report-{year}-09.pdf" in pdf.headers["content-disposition"]

        figures = client.get(f"/api/v1/admin/reports/financial?month=9&year={year}",
                             headers=staff)
        assert figures.status_code == 200
        assert figures.json()["kpis"]["net_commission"] == "190.00"
        quarter = client.get(f"/api/v1/admin/reports/financial?quarter=3&year={year}",
                             headers=staff).json()
        assert quarter["meta"]["period"]["label"] == f"Q3 {year}"
    finally:
        with SessionLocal() as db:
            row = db.get(PlatformSetting, financial.LOG_KEY)
            if before is None and row is not None:
                db.delete(row)
            elif row is not None:
                row.value = before
            db.commit()


@requires_db
def test_financial_report_is_staff_only_and_validated(client, world):
    member = _auth(world["a"])
    staff = _auth(world["staff"], "administrator")
    year = world["year"]
    body = {"kind": "month", "year": year, "month": 9, "sections": ["revenue"]}
    assert client.get("/api/v1/admin/reports/financial").status_code == 401
    assert client.get("/api/v1/admin/reports/financial", headers=member).status_code == 403
    assert client.post("/api/v1/admin/reports/financial/generate", headers=member,
                       json=body).status_code == 403
    assert client.get("/api/v1/admin/reports/financial/history",
                      headers=member).status_code == 403
    assert client.get("/api/v1/admin/reports/financial/history/abc123/pdf",
                      headers=member).status_code == 403
    for bad in ({**body, "sections": ["secrets"]}, {**body, "month": None},
                {**body, "kind": "custom"}, {**body, "sections": []}):
        r = client.post("/api/v1/admin/reports/financial/generate", headers=staff, json=bad)
        assert r.status_code == 422, (bad, r.text)
    assert client.get("/api/v1/admin/reports/financial/history/abc123/pdf",
                      headers=staff).status_code == 404

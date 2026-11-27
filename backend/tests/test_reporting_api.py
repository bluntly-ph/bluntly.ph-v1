"""The four system reports against a real database, with exact money.

One deterministic world, built once per module in a cycle YEAR no other row
uses (the isolated CI database is cumulative), through the same split function
the importers call — so every expected peso below is what the real import path
would have produced:

    reviewer A  review RA1 (Yes, 5*) with Shopee and Lazada links
                  Y-03 Shopee  100.00  cleared      -> 40.00 / 30.00 / 30.00
                  Y-03 Lazada   50.00  not cleared  -> 20.00 / 15.00 / 15.00
                  Y-04 Shopee   10.00  not cleared  ->  4.00 /  3.00 /  3.00
                review RA2 (Hard pass, 1*) on the Honesty Fund track
                  Y-03 Shopee   20.00  cleared      ->  8.00 /  0.00 / 12.00
                review RA3 (Hard pass) on the fund track, removed
                one paid payout of 30.00 requested and paid in Y-03
    reviewer B  Y-03 Shopee 999.97 cleared -> reviewer 299.99 (below PHP 300)
    reviewer C  Y-03 Shopee 1000.00 cleared -> reviewer 300.00 (at PHP 300)
    Shopee Y-03 remittance received: 2119.97 (exactly the attributed gross)
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import extract, select

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import (
    CommissionTarget,
    EarnEligibleStatus,
    MemberRole,
    ModerationAction,
    PayoutMethod,
    PayoutStatus,
    Platform,
    ReferralLinkStatus,
    SellerClaimStatus,
    Verdict,
    VerificationStatus,
)
from app.models.moderation import ModerationLog
from app.models.payout import Payout
from app.models.product import Product
from app.models.review import ReferralLink, Review
from app.models.seller import Seller, SellerReview
from app.models.user import User
from app.services import earnings, wallet
from app.services.seller_service import normalize_seller_name
from tests.conftest import requires_db

pytestmark = requires_db

D = Decimal


def _auth(user_id, role="user") -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _free_year(db) -> int:
    used = {int(y) for y in db.scalars(
        select(extract("year", Commission.cycle_month)).distinct())}
    used |= {int(y) for y in db.scalars(
        select(extract("year", MarketplaceRemittance.cycle_month)).distinct())}
    # A PAST year: audit rows dated in the future would be every other test's
    # "latest" entry in the cumulative CI database.
    for year in range(2019, 1971, -1):
        if year not in used:
            return year
    raise AssertionError("no free report year")


def _user(db, **kw) -> User:
    u = User(email=f"rep_{uuid.uuid4().hex}@example.com", password_hash="x",
             display_name="Report Fixture", username=f"rep_{uuid.uuid4().hex[:12]}", **kw)
    db.add(u)
    db.flush()
    return u


def _review(db, author, product, verdict, stars, status, **kw) -> Review:
    r = Review(product_id=product.id, author_id=author.id,
               title=kw.pop("title", f"Fixture {verdict.value}"),
               discussion="Body text for the fixture review.", verdict=verdict,
               star_rating=D(str(stars)), earn_eligible_status=status,
               verification_status=VerificationStatus.verified,
               published_at=kw.pop("published_at", datetime.now(UTC)), **kw)
    db.add(r)
    db.flush()
    return r


def _commission(db, review, author, gross: str, platform: Platform, cycle: date,
                cleared: bool) -> Commission:
    """As the importers write one: `earnings.split_for_review`, then the wallet."""
    split, bps = earnings.split_for_review(D(gross), review, author)
    c = Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                   target_type=CommissionTarget.review, review_id=review.id,
                   reviewer_id=author.id, reviewer_share_bps=bps, platform=platform,
                   cleared_at=datetime.now(UTC) if cleared else None, currency="PHP",
                   csv_source=f"report-test:{uuid.uuid4().hex[:8]}",
                   row_reference=uuid.uuid4().hex, order_status="Completed",
                   cycle_month=cycle, **split)
    db.add(c)
    wallet.adjust(db, author.id, split["reviewer_share"])
    db.flush()
    return c


@pytest.fixture(scope="module")
def world():
    db = SessionLocal()
    try:
        year = _free_year(db)
        march, april = date(year, 3, 1), date(year, 4, 1)
        in_march = datetime(year, 3, 15, 4, 0, tzinfo=UTC)

        staff = _user(db, role=MemberRole.administrator)
        a = _user(db, payout_account="alice.reviewer@gmail.com")
        b = _user(db, payout_account="b@example.com")
        c = _user(db, payout_account="c@example.com")
        product = Product(canonical_name=f"Report Product {uuid.uuid4().hex[:6]}")
        db.add(product)
        db.flush()

        ra1 = _review(db, a, product, Verdict.yes_absolutely, 5,
                      EarnEligibleStatus.monetized, title="=cmd|' /C calc'!A0")
        ra2 = _review(db, a, product, Verdict.hard_pass, 1, EarnEligibleStatus.honesty_fund,
                      title="Fund review", price_paid=D("499.00"))
        ra3 = _review(db, a, product, Verdict.hard_pass, 2, EarnEligibleStatus.honesty_fund,
                      title="Removed fund review", is_removed=True)
        late = _review(db, b, product, Verdict.it_depends, 2,
                       EarnEligibleStatus.honesty_fund, title="Routed after the period")
        rb = _review(db, b, product, Verdict.yes_absolutely, 4, EarnEligibleStatus.monetized)
        rc = _review(db, c, product, Verdict.yes_absolutely, 4, EarnEligibleStatus.monetized)
        # One ACTIVE link per review (uq_referral_active): RA1's earlier Lazada
        # link was revoked when its Shopee link replaced it, and its sales
        # still attribute through the revoked link's sub-ID.
        for review, platform, status in (
                (ra1, Platform.lazada, ReferralLinkStatus.revoked),
                (ra1, Platform.shopee, ReferralLinkStatus.active),
                (ra2, Platform.shopee, ReferralLinkStatus.active),
                (rb, Platform.shopee, ReferralLinkStatus.active),
                (rc, Platform.shopee, ReferralLinkStatus.active)):
            db.add(ReferralLink(review_id=review.id, platform=platform, status=status,
                                url=f"https://{platform.value}.ph/p", review_version=1,
                                sub_id=f"blt_{uuid.uuid4().hex[:10]}"))
            db.flush()
        # Routed to the fund in March (ra2) and in May (late: outside March).
        db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=staff.id,
                             action=ModerationAction.approve, target_ref=ra2.id,
                             context={"routed_to": "honesty_fund"}, created_at=in_march))
        db.add(ModerationLog(log_id=f"mlog_{uuid.uuid4().hex[:10]}", moderator_id=staff.id,
                             action=ModerationAction.approve, target_ref=late.id,
                             context={"routed_to": "honesty_fund"},
                             created_at=datetime(year, 5, 10, tzinfo=UTC)))

        _commission(db, ra1, a, "100.00", Platform.shopee, march, cleared=True)
        _commission(db, ra1, a, "50.00", Platform.lazada, march, cleared=False)
        _commission(db, ra1, a, "10.00", Platform.shopee, april, cleared=False)
        _commission(db, ra2, a, "20.00", Platform.shopee, march, cleared=True)
        _commission(db, rb, b, "999.97", Platform.shopee, march, cleared=True)
        _commission(db, rc, c, "1000.00", Platform.shopee, march, cleared=True)
        db.add(MarketplaceRemittance(platform=Platform.shopee, cycle_month=march,
                                     amount_received=D("2119.97"),
                                     received_on=date(year, 4, 20), reference="SHP-REMIT",
                                     recorded_by_id=staff.id))
        payout = Payout(payout_id=f"pay_{uuid.uuid4().hex[:12]}", user_id=a.id,
                        amount=D("30.00"), status=PayoutStatus.paid, method=PayoutMethod.manual,
                        batch_id=f"batch_{year}03", provider_ref="BANK-REF-1",
                        scheduled_for=date(year, 3, 16), created_at=in_march,
                        paid_at=in_march + timedelta(days=2))
        db.add(payout)
        wallet.adjust(db, a.id, D("-30.00"))

        # Stores: A's is claimed by `owner`, B's by `owner_b`, one pending claim.
        owner, owner_b, pending, buyer = _user(db), _user(db), _user(db), _user(db)

        def store(name, claimed_by=None):
            s = Seller(display_name=name, normalized_name=normalize_seller_name(name),
                       platform=Platform.lazada, claimed_by_id=claimed_by,
                       claim_status=(SellerClaimStatus.claimed if claimed_by
                                     else SellerClaimStatus.unclaimed))
            db.add(s)
            db.flush()
            return s

        s1 = store(f"Report Store {uuid.uuid4().hex[:8]}", owner.id)
        s2 = store(f"Other Store {uuid.uuid4().hex[:8]}", owner_b.id)
        empty = store(f"Empty Store {uuid.uuid4().hex[:8]}", owner.id)
        unclaimed = store(f"Unclaimed Store {uuid.uuid4().hex[:8]}")
        for overall, cs, pk, acc, comp, rec, when, removed in (
                ("5", 5, 4, True, True, True, in_march, False),
                ("3", 2, 4, False, True, False, in_march, False),
                ("4.5", 4, 5, True, False, True, in_march, False),
                ("1", 1, 1, False, False, False, datetime(year, 5, 2, tzinfo=UTC), False),
                ("1", 1, 1, False, False, False, in_march, True)):
            db.add(SellerReview(seller_id=s1.id, reviewer_id=_user(db).id,
                                overall_rating=D(overall), customer_service=cs,
                                packaging_quality=pk, accuracy=acc, order_completeness=comp,
                                would_recommend=rec, created_at=when, is_removed=removed,
                                order_id="PRIVATE-ORDER-123",
                                seller_response="Thanks!" if overall == "5" else None))
        db.commit()
        yield {"year": year, "staff": staff.id, "a": a.id, "b": b.id, "c": c.id,
               "ra1": ra1.id, "ra2": ra2.id, "ra3": ra3.id, "late": late.id,
               "owner": owner.id, "owner_b": owner_b.id, "pending": pending.id,
               "buyer": buyer.id, "s1": s1.id, "s2": s2.id, "empty": empty.id,
               "unclaimed": unclaimed.id}
    finally:
        db.close()


def _march(w) -> str:
    return f"month=3&year={w['year']}"


# ================================================================ 4. reviewer statement

def test_statement_totals_are_exact(client, world):
    w = world
    r = client.get(f"/api/v1/reports/earnings-statement?{_march(w)}", headers=_auth(w["a"]))
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["earned_in_period"] == "45.00"       # 30.00 + 15.00 + 0.00 (fund track)
    assert s["lifetime_earned"] == "48.00"        # + April's 3.00
    assert s["clearing"] == "18.00"               # Lazada 15.00 + April 3.00
    assert s["wallet_balance"] == "18.00"         # 48.00 earned - 30.00 paid
    assert s["withdrawable"] == "0.00"            # only cleared money; all 18.00 is clearing
    assert s["paid_in_period"] == "30.00" and s["paid_lifetime"] == "30.00"
    assert s["in_flight"] == "0.00" and s["minimum_cashout"] == "300.00"
    assert s["can_cash_out"] is False


def test_statement_per_review_and_line_items(client, world):
    w = world
    body = client.get(f"/api/v1/reports/earnings-statement?{_march(w)}",
                      headers=_auth(w["a"])).json()
    by_id = {r["review_id"]: r for r in body["reviews"]}
    ra1, ra2 = by_id[str(w["ra1"])], by_id[str(w["ra2"])]
    assert (ra1["sales"], ra1["commission_gross"], ra1["reviewer_earning"],
            ra1["cleared"], ra1["clearing"]) == (2, "150.00", "45.00", "30.00", "15.00")
    assert ra1["marketplaces"] == ["lazada", "shopee"]
    assert (ra2["reviewer_earning"], ra2["verdict"]) == ("0.00", "hard_pass")
    statuses = sorted((e["marketplace"], e["reviewer_earning"], e["status"])
                      for e in body["entries"])
    assert statuses == [("lazada", "15.00", "clearing"), ("shopee", "0.00", "cleared"),
                        ("shopee", "30.00", "cleared")]
    [payout] = body["payouts"]
    assert (payout["amount"], payout["status"], payout["destination"]) == \
        ("30.00", "paid", "a***@gmail.com")
    assert "alice.reviewer@gmail.com" not in str(body)


def test_statement_period_boundary(client, world):
    w = world
    april = client.get(f"/api/v1/reports/earnings-statement?month=4&year={w['year']}",
                       headers=_auth(w["a"])).json()
    assert april["summary"]["earned_in_period"] == "3.00"
    assert april["payouts"] == [] and april["summary"]["paid_in_period"] == "0.00"
    # A range spanning both months includes both cycles.
    both = client.get(f"/api/v1/reports/earnings-statement?start_date={w['year']}-03-10"
                      f"&end_date={w['year']}-04-05", headers=_auth(w["a"])).json()
    assert both["summary"]["earned_in_period"] == "48.00"


def test_statement_is_always_the_callers_own(client, world):
    w = world
    # B asks with A's id in every place a client could put it: B's own comes back.
    r = client.get(f"/api/v1/reports/earnings-statement?{_march(w)}&user_id={w['a']}",
                   headers=_auth(w["b"]))
    assert r.status_code == 200
    assert r.json()["reviewer"]["id"] == str(w["b"])
    assert r.json()["summary"]["earned_in_period"] == "299.99"
    # The staff route refuses non-staff, whoever they ask about.
    for who in ("a", "b"):
        assert client.get(f"/api/v1/admin/reports/earnings-statement/{w['a']}",
                          headers=_auth(w[who])).status_code == 403
    assert client.get("/api/v1/reports/earnings-statement").status_code == 401


def test_staff_may_read_a_reviewers_statement(client, world):
    w = world
    r = client.get(f"/api/v1/admin/reports/earnings-statement/{w['a']}?{_march(w)}",
                   headers=_auth(w["staff"], "administrator"))
    assert r.status_code == 200 and r.json()["summary"]["earned_in_period"] == "45.00"
    missing = uuid.uuid4()
    assert client.get(f"/api/v1/admin/reports/earnings-statement/{missing}",
                      headers=_auth(w["staff"], "administrator")).status_code == 404


def test_statement_csv(client, world):
    w = world
    r = client.get(f"/api/v1/reports/earnings-statement?{_march(w)}&format=csv",
                   headers=_auth(w["a"]))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == \
        f'attachment; filename="bluntly-earnings-statement-{w["year"]}-03.csv"'
    assert r.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["Recognised at", "Cycle month", "Commission ID"]
    earnings_col = rows[0].index("Your earning")
    assert sorted(row[earnings_col] for row in rows[1:]) == ["0.00", "15.00", "30.00"]
    # The formula-shaped review title is exported inert.
    title_col = rows[0].index("Review")
    assert any(row[title_col].startswith("'=cmd") for row in rows[1:])
    payouts = client.get(f"/api/v1/reports/earnings-statement?{_march(w)}&format=csv"
                         "&section=payouts", headers=_auth(w["a"]))
    assert payouts.status_code == 200 and "a***@gmail.com" in payouts.text
    assert "alice.reviewer" not in payouts.text
    assert client.get(f"/api/v1/reports/earnings-statement?{_march(w)}&format=csv"
                      "&section=secrets", headers=_auth(w["a"])).status_code == 422


def test_period_parameters_are_validated(client, world):
    h = _auth(world["a"])
    for query in ("month=3", "month=3&year=2026&start_date=2026-03-01&end_date=2026-03-02",
                  "start_date=2025-01-01&end_date=2026-06-01", "month=13&year=2026",
                  "start_date=2026-03-02&end_date=2026-03-01"):
        assert client.get(f"/api/v1/reports/earnings-statement?{query}",
                          headers=h).status_code == 422, query


# ================================================================ 3. seller rating

def test_seller_summary_values(client, world):
    w = world
    r = client.get(f"/api/v1/sellers/{w['s1']}/reports/rating-summary?{_march(w)}",
                   headers=_auth(w["owner"]))
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["period_summary"]
    assert p["review_count"] == 3                      # May's and the removed one excluded
    assert p["overall_median"] == 4.5 and p["overall_mean"] == 4.17
    assert p["recommendation_rate"] == 0.6667
    dims = {d["key"]: d for d in p["dimensions"]}
    assert set(dims) == {"accuracy", "order_completeness", "customer_service",
                         "packaging_quality"}
    assert (dims["customer_service"]["median"], dims["customer_service"]["mean"]) == (4.0, 3.67)
    assert (dims["packaging_quality"]["median"], dims["packaging_quality"]["mean"]) == (4.0, 4.33)
    assert dims["accuracy"]["rate"] == 0.6667 and dims["order_completeness"]["rate"] == 0.6667
    assert p["distribution"] == {"1": 0, "2": 0, "3": 1, "4": 1, "5": 1}
    assert p["responded"] == 1
    assert body["all_time_summary"]["review_count"] == 4
    assert "PRIVATE-ORDER-123" not in r.text          # the order ID is never reported


def test_seller_summary_empty_store(client, world):
    w = world
    body = client.get(f"/api/v1/sellers/{w['empty']}/reports/rating-summary",
                      headers=_auth(w["owner"])).json()
    assert body["period_summary"]["review_count"] == 0
    assert body["period_summary"]["overall_median"] is None
    assert body["period_summary"]["recommendation_rate"] is None
    assert body["rows"] == []


def test_seller_a_cannot_read_seller_b(client, world):
    w = world
    url = f"/api/v1/sellers/{w['s2']}/reports/rating-summary"
    denied = client.get(url, headers=_auth(w["owner"]))
    assert denied.status_code == 403 and denied.json()["code"] == "not_store_owner"
    for who in ("buyer", "pending", "a"):
        assert client.get(f"/api/v1/sellers/{w['s1']}/reports/rating-summary",
                          headers=_auth(w[who])).status_code == 403
    assert client.get(f"/api/v1/sellers/{w['unclaimed']}/reports/rating-summary",
                      headers=_auth(w["owner"])).status_code == 403
    assert client.get(url).status_code == 401
    assert client.get(f"/api/v1/sellers/{uuid.uuid4()}/reports/rating-summary",
                      headers=_auth(w["owner"])).status_code == 404
    assert client.get(url, headers=_auth(w["owner_b"])).status_code == 200
    assert client.get(url, headers=_auth(w["staff"], "administrator")).status_code == 200


def test_seller_summary_csv(client, world):
    w = world
    r = client.get(f"/api/v1/sellers/{w['s1']}/reports/rating-summary?{_march(w)}&format=csv",
                   headers=_auth(w["owner"]))
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == ["Date", "Reviewer", "Title", "Overall rating", "Customer service",
                       "Packaging", "Matched listing", "Complete order", "Would recommend",
                       "Store responded"]
    assert len(rows) == 4 and "PRIVATE-ORDER" not in r.text


# ================================================================ 2. commissions

def _commissions(client, w, extra=""):
    r = client.get(f"/api/v1/admin/reports/commissions-payouts?{_march(w)}{extra}",
                   headers=_auth(w["staff"], "administrator"))
    assert r.status_code == 200, r.text
    return r.json()


def test_commission_totals_are_exact(client, world):
    t = _commissions(client, world)["totals"]
    assert t["commissions"] == 5
    assert t["gross"] == "2169.97"
    assert t["platform_share"] == "867.99"
    assert t["reviewer_share"] == "644.99"
    assert t["honesty_fund_share"] == "656.99"
    assert D(t["platform_share"]) + D(t["reviewer_share"]) + D(t["honesty_fund_share"]) == \
        D(t["gross"])
    assert t["cleared_gross"] == "2119.97" and t["clearing_gross"] == "50.00"
    by = {p["marketplace"]: p for p in t["by_marketplace"]}
    assert (by["shopee"]["commissions"], by["shopee"]["gross"]) == (4, "2119.97")
    assert (by["lazada"]["commissions"], by["lazada"]["gross"]) == (1, "50.00")


def test_commission_rows_carry_the_canonical_split(client, world):
    body = _commissions(client, world)
    for row in body["commissions"]:
        gross = D(row["imported_commission"])
        canonical = earnings.split_commission(gross)
        if row["allocation"] == "honesty_fund":
            assert row["reviewer_share"] == "0.00"
            assert D(row["honesty_fund_share"]) == \
                canonical["honesty_fund_share"] + canonical["reviewer_share"]
        else:
            assert D(row["reviewer_share"]) == canonical["reviewer_share"]
            assert D(row["honesty_fund_share"]) == canonical["honesty_fund_share"]
        assert D(row["platform_share"]) == canonical["platform_share"]
        assert row["sub_id"] and row["sub_id"].startswith("blt_")
    statuses = {(r["marketplace"], r["reconciliation_status"]) for r in body["commissions"]}
    assert statuses == {("shopee", "cleared"), ("lazada", "awaiting_remittance")}
    lazada = next(r for r in body["commissions"] if r["marketplace"] == "lazada")
    assert lazada["reconciled_amount"] is None and lazada["reconciled_at"] is None


def test_remittances_reconcile(client, world):
    rem = {(r["marketplace"], r["status"]): r for r in _commissions(client, world)["remittances"]}
    shopee = rem[("shopee", "reconciled")]
    assert (shopee["attributed_gross"], shopee["amount_received"], shopee["difference"]) == \
        ("2119.97", "2119.97", "0.00")
    lazada = rem[("lazada", "awaiting_remittance")]
    assert lazada["attributed_gross"] == "50.00" and lazada["amount_received"] is None


def test_the_300_peso_threshold(client, world):
    w = world
    summary = {r["reviewer_id"]: r for r in _commissions(client, w)["payout_summary"]}
    b, c, a = summary[str(w["b"])], summary[str(w["c"])], summary[str(w["a"])]
    assert (b["withdrawable"], b["eligible_for_cashout"]) == ("299.99", False)
    assert (c["withdrawable"], c["eligible_for_cashout"]) == ("300.00", True)
    # Pending (uncleared) money is never withdrawable.
    assert (a["clearing"], a["withdrawable"], a["eligible_for_cashout"]) == \
        ("18.00", "0.00", False)
    assert a["latest_payout_status"] == "paid" and a["paid_in_period"] == "30.00"
    assert c["threshold"] == "300.00" and c["payout_account_on_file"] is True


def test_commission_paging_keeps_whole_period_totals(client, world):
    body = _commissions(client, world, "&limit=2&offset=0")
    assert len(body["commissions"]) == 2 and body["page"]["total"] == 5
    assert body["totals"]["gross"] == "2169.97"


def test_commission_report_is_staff_only(client, world):
    w = world
    url = f"/api/v1/admin/reports/commissions-payouts?{_march(w)}"
    assert client.get(url).status_code == 401
    for who in ("a", "owner", "buyer"):
        assert client.get(url, headers=_auth(w[who])).status_code == 403


def test_commission_csv_sections(client, world):
    w = world
    h = _auth(w["staff"], "administrator")
    base = f"/api/v1/admin/reports/commissions-payouts?{_march(w)}&format=csv"
    main = client.get(base, headers=h)
    assert main.headers["content-disposition"] == \
        f'attachment; filename="bluntly-commission-payout-{w["year"]}-03.csv"'
    rows = list(csv.reader(io.StringIO(main.content.decode("utf-8-sig"))))
    assert len(rows) == 6 and rows[0][0] == "Commission ID"
    summary = client.get(base + "&section=payout-summary", headers=h)
    assert 'payout-summary.csv"' in summary.headers["content-disposition"]
    assert "299.99" in summary.text and "300.00" in summary.text
    # The recipient's payout address is not an export column.
    assert "@example.com" not in summary.text and "gmail" not in summary.text


# ================================================================ 1. honesty fund

def _fund(client, w, query=None):
    r = client.get(f"/api/v1/admin/reports/honesty-fund?{query or _march(w)}",
                   headers=_auth(w["staff"], "administrator"))
    assert r.status_code == 200, r.text
    return r.json()


def test_fund_totals_come_from_the_ledger(client, world):
    body = _fund(client, world)
    assert body["fund_total"] == "656.99"
    assert body["fund_total_cleared"] == "641.99"     # all but Lazada's 15.00
    assert body["distributed_total"] == "0.00"
    [cycle] = body["cycles"]
    assert (cycle["fund_inflow"], cycle["distribution_status"]) == ("656.99", "not_distributed")


def test_fund_eligibility_and_inputs(client, world):
    w = world
    rows = {r["review_id"]: r for r in _fund(client, w)["reviews"]}
    ra2 = rows[str(w["ra2"])]
    assert ra2["eligibility"] == "eligible" and ra2["exclusion_reason"] is None
    assert (ra2["commission_base"], ra2["fund_attributable"]) == ("20.00", "12.00")
    assert ra2["routed_in_period"] is True and ra2["photo_provided"] is True
    assert ra2["meets_evidence_floor"] is False and ra2["honesty_score"] == "0.0000"
    ra3 = rows[str(w["ra3"])]
    assert (ra3["eligibility"], ra3["exclusion_reason"]) == ("excluded", "removed")
    # Routed in May: not on the fund track during March.
    assert str(w["late"]) not in rows
    # A commission-track review is never a fund row.
    assert str(w["ra1"]) not in rows


def test_the_distribution_is_never_guessed(client, world):
    """Even with the mechanism switched on (conftest does, for its own tests),
    the report computes no share: the formula is not approved (§14)."""
    body = _fund(client, world)
    assert body["formula"]["defined"] is False
    assert body["formula"]["holding_period_defined"] is False
    for row in body["reviews"]:
        assert row["computed_share"] is None
        assert row["computed_share_status"] == "pending_formula"
    csv_text = client.get(f"/api/v1/admin/reports/honesty-fund?{_march(world)}&format=csv",
                          headers=_auth(world["staff"], "administrator")).text
    assert "Pending distribution formula" in csv_text


def test_fund_period_boundary(client, world):
    w = world
    may = _fund(client, w, f"month=5&year={w['year']}")
    assert may["fund_total"] == "0.00"
    assert str(w["late"]) in {r["review_id"] for r in may["reviews"]}


def test_fund_report_is_staff_only(client, world):
    w = world
    for who in ("a", "owner"):
        assert client.get("/api/v1/admin/reports/honesty-fund",
                          headers=_auth(w[who])).status_code == 403
    assert client.get("/api/v1/admin/reports/honesty-fund").status_code == 401


def test_pending_two_and_a_half_is_counted_not_routed(client, world):
    """Owner decision A: a 2.5 "It depends" thread awaiting a Super Admin is
    counted as pending routing and never guessed into the fund's rows."""
    w = world
    before = _fund(client, w)["pending_routing_count"]
    db = SessionLocal()
    try:
        author = db.get(User, w["b"])
        product = db.scalar(select(Product).limit(1))
        review = _review(db, author, product, Verdict.it_depends, "2.5",
                         EarnEligibleStatus.pending_superadmin_routing, title="Two and a half")
        db.commit()
        after = _fund(client, w)
        assert after["pending_routing_count"] == before + 1
        assert str(review.id) not in {r["review_id"] for r in after["reviews"]}
    finally:
        db.close()
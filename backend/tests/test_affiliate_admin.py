"""The admin Affiliate screen's reads (meeting 2026-10-02 15:50): transactions,
the per-month breakdown, and the import history with each import's rows."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.models.commission import Commission, MarketplaceRemittance
from app.models.enums import (
    AffiliateTxStatus,
    CommissionTarget,
    EarnEligibleStatus,
    ModerationAction,
    Platform,
    Verdict,
    VerificationStatus,
)
from app.models.moderation import ModerationLog
from app.models.postback import AffiliatePostback
from app.models.product import Product
from app.models.review import Review
from app.services import affiliate_admin_service as svc
from tests.conftest import make_user, register_and_token, requires_db

D = Decimal
pytestmark = requires_db


def test_transactions_months_and_an_import(db):
    staff = make_user(db)
    author = make_user(db)
    product = Product(canonical_name=f"Aff {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    review = Review(product_id=product.id, author_id=author.id, title="Fixture",
                    discussion="Body text for the fixture review.",
                    verdict=Verdict.yes_absolutely, star_rating=D("5"),
                    earn_eligible_status=EarnEligibleStatus.monetized,
                    verification_status=VerificationStatus.verified,
                    published_at=datetime.now(UTC))
    db.add(review)
    db.flush()
    cycle = date(1977, 3, 1)
    import_id = uuid.uuid4().hex[:16]
    tag = uuid.uuid4().hex[:8]
    for i, status in enumerate((AffiliateTxStatus.completed, AffiliateTxStatus.pending)):
        db.add(AffiliatePostback(platform=Platform.lazada, external_order_id=f"ORD-{tag}-{i}",
                                 external_sub_order_id=f"{tag}-{i}", canonical_status=status,
                                 reported_payout=D("12.50"), product_name="Fixture fan",
                                 source_import_id=import_id))
    for gross in ("100.00", "-20.00"):
        db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                          target_type=CommissionTarget.review, review_id=review.id,
                          reviewer_id=author.id, platform=Platform.lazada, currency="PHP",
                          csv_source="aff-test", row_reference=uuid.uuid4().hex,
                          cycle_month=cycle, gross_amount=D(gross),
                          platform_share=D(gross) * D("0.4"), reviewer_share=D(gross) * D("0.3"),
                          honesty_fund_share=D(gross) * D("0.3")))
    db.flush()
    mine = db.query(Commission).filter_by(review_id=review.id)
    original = mine.filter_by(gross_amount=D("100.00")).first()
    mine.filter_by(gross_amount=D("-20.00")).update(
        {"reverses_commission_id": original.id})
    db.add(MarketplaceRemittance(platform=Platform.lazada, cycle_month=cycle,
                                 amount_received=D("80.00"), received_on=date(1977, 4, 20)))
    log_id = f"mlog_{uuid.uuid4().hex[:10]}"
    db.add(ModerationLog(log_id=log_id, moderator_id=staff.id, action=ModerationAction.csv_import,
                         context={"filename": "lazada-march.csv", "import_id": import_id,
                                  "format": "lazada", "total_rows": 2, "recognised": 1,
                                  "reversed": 0, "unattributed": 0, "held_pending_routing": 0,
                                  "lifecycle": {"completed": 1, "pending": 1},
                                  "recognised_amount": "12.50"}))
    db.flush()

    page = svc.transactions(db, q=f"ORD-{tag}")
    assert page.total == 2 and {r.status for r in page.rows} == {"completed", "pending"}
    assert svc.transactions(db, q=f"ORD-{tag}", status="pending").total == 1

    [march] = [m for m in svc.months(db, platform="lazada", limit=120) if m.cycle_month == cycle]
    assert (march.commissions, march.earned, march.reversed, march.net) == (
        1, D("100.00"), D("20.00"), D("80.00"))
    assert (march.remitted, march.status) == (D("80.00"), "remitted")

    [row] = [i for i in svc.imports(db, limit=200) if i.id == log_id]
    assert (row.kind, row.filename, row.recognised, row.recognised_amount) == (
        "lifecycle", "lazada-march.csv", 1, D("12.50"))
    detail = svc.import_detail(db, log_id)
    assert detail.lifecycle == {"completed": 1, "pending": 1}
    assert len(detail.transactions) == 2


def test_transactions_name_the_reviewer_and_filter_sort_and_count(db):
    author = make_user(db)
    product = Product(canonical_name=f"Aff {uuid.uuid4().hex[:6]}")
    db.add(product)
    db.flush()
    review = Review(product_id=product.id, author_id=author.id, title="Fixture",
                    discussion="Body text for the fixture review.",
                    verdict=Verdict.yes_absolutely, star_rating=D("5"),
                    earn_eligible_status=EarnEligibleStatus.monetized,
                    verification_status=VerificationStatus.verified,
                    published_at=datetime.now(UTC))
    db.add(review)
    db.flush()
    tag = uuid.uuid4().hex[:8]
    for i, (payout, rid) in enumerate(((D("5.00"), review.id), (D("40.00"), review.id),
                                       (D("9.00"), None))):
        db.add(AffiliatePostback(platform=Platform.shopee, external_order_id=f"SRT-{tag}-{i}",
                                 external_sub_order_id=f"{tag}-{i}", review_id=rid,
                                 canonical_status=AffiliateTxStatus.completed,
                                 reported_payout=payout, product_name="Fixture fan"))
    db.flush()

    page = svc.transactions(db, q=f"SRT-{tag}", sort="commission_desc")
    assert [r.commission for r in page.rows] == [D("40.00"), D("9.00"), D("5.00")]
    assert page.rows[0].reviewer.id == author.id and page.rows[1].reviewer is None
    assert page.rows[0].updated_at is not None
    assert page.facets["attribution"] == {"attributed": 2, "unattributed": 1}
    assert page.facets["platform"] == {"shopee": 3}
    assert page.facets["updated"]["7d"] == 3
    only = svc.transactions(db, q=f"SRT-{tag}", attribution="unattributed")
    assert only.total == 1 and only.facets["attribution"]["attributed"] == 2
    assert svc.transactions(db, q=f"SRT-{tag}", settlement="paid").total == 0
    assert [r.commission for r in svc.transactions(db, q=f"SRT-{tag}",
                                                   sort="commission_asc").rows][0] == D("5.00")


def test_affiliate_reads_are_staff_only(client):
    _, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    for path in ("/api/v1/admin/affiliate/transactions", "/api/v1/admin/affiliate/months",
                 "/api/v1/admin/affiliate/imports"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": f"Bearer {member}"}).status_code == 403
        assert client.get(path, headers={"Authorization": f"Bearer {admin}"}).status_code == 200
    missing = client.get("/api/v1/admin/affiliate/imports/mlog_nothere",
                         headers={"Authorization": f"Bearer {admin}"})
    assert missing.status_code == 404

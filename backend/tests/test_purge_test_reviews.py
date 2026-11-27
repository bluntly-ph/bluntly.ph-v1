"""scripts/purge_test_reviews: explicit selection only, refuses money evidence,
refuses real accounts, whole threads only, digest-confirmed, Super Admin only,
audited, and never against production (owner decision 2026-09-28)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.commission import Commission
from app.models.enums import (
    CommissionTarget,
    EarnEligibleStatus,
    MemberRole,
    ModerationAction,
    Platform,
    Verdict,
    VerificationStatus,
)
from app.models.moderation import ModerationLog
from app.models.product import Product
from app.models.review import Review
from app.models.user import User
from scripts import purge_test_reviews as P
from tests.conftest import requires_db

pytestmark = requires_db


def _user(db, domain="example.com", **kw) -> User:
    u = User(email=f"purge_{uuid.uuid4().hex}@{domain}", password_hash="x",
             display_name="Purge Fixture", username=f"pg_{uuid.uuid4().hex[:12]}", **kw)
    db.add(u)
    db.flush()
    return u


def _review(db, author, product, thread_id=None) -> Review:
    r = Review(product_id=product.id, author_id=author.id, title="Purge fixture",
               discussion="Body text for the purge fixture.", verdict=Verdict.yes_absolutely,
               star_rating=Decimal("4.0"), earn_eligible_status=EarnEligibleStatus.none,
               verification_status=VerificationStatus.verified, thread_id=thread_id,
               published_at=datetime.now(UTC))
    db.add(r)
    db.flush()
    return r


@pytest.fixture
def world():
    db = SessionLocal()
    try:
        product = Product(canonical_name=f"Purge Product {uuid.uuid4().hex[:6]}")
        db.add(product)
        db.flush()
        tester, real, showcase = _user(db), _user(db, "gmail.com"), _user(db, "showcase.bluntly.ph")
        root = _review(db, tester, product)
        update = _review(db, tester, product, thread_id=root.id)
        lone = _review(db, tester, product)
        paid = _review(db, tester, product)
        db.add(Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                          target_type=CommissionTarget.review, review_id=paid.id,
                          reviewer_id=tester.id, reviewer_share_bps=4000, platform=Platform.shopee,
                          gross_amount=Decimal("10.00"), reviewer_share=Decimal("4.00"),
                          platform_share=Decimal("3.00"), honesty_fund_share=Decimal("3.00"),
                          currency="PHP", csv_source="purge-test", row_reference=uuid.uuid4().hex,
                          order_status="Completed", cycle_month=date(1975, 1, 1)))
        real_review = _review(db, real, product)
        demo = _review(db, showcase, product)
        admin = _user(db, role=MemberRole.super_admin)
        staff = _user(db, role=MemberRole.administrator)
        db.commit()
        yield {"root": root.id, "update": update.id, "lone": lone.id, "paid": paid.id,
               "real": real_review.id, "demo": demo.id, "admin": admin.email,
               "staff": staff.email}
    finally:
        db.close()


def _file(tmp_path, *ids) -> str:
    path = tmp_path / "selection.tsv"
    path.write_text("# header line\n" + "".join(f"{i}\tREV\ttest_suite\n" for i in ids))
    return str(path)


def test_only_marked_accounts_are_ever_candidates(world):
    with SessionLocal() as db:
        found = {c.id: c.klass for c in P.candidates(db, [world[k] for k in
                                                          ("root", "real", "demo")])}
    assert found == {world["root"]: "test_suite", world["demo"]: "showcase"}


def test_the_listing_preselects_only_the_test_suite(world):
    import io
    with SessionLocal() as db:
        rows = P.candidates(db, [world[k] for k in ("lone", "paid", "demo")])
        blocked = P.financial_blockers(db, [c.id for c in rows])
    out = io.StringIO()
    P.write_listing(rows, blocked, out)
    lines = {line.lstrip("# ").split("\t")[0]: line for line in out.getvalue().splitlines()
             if "\t" in line and not line.startswith("# review_id")}
    assert not lines[str(world["lone"])].startswith("#")        # test suite: selected
    assert lines[str(world["demo"])].startswith("# ")           # showcase: opt-in only
    assert lines[str(world["paid"])].startswith("# ")           # money evidence: never
    assert "BLOCKED: 1 commissions" in lines[str(world["paid"])]


def test_a_dirty_selection_is_refused_line_by_line(world):
    with SessionLocal() as db:
        chk = P.check_selection(db, [world["real"], world["paid"], world["root"]])
    assert chk.unknown == [world["real"]]                       # a real person's review
    assert list(chk.blocked) == [world["paid"]]                 # payout evidence
    assert chk.partial_threads == {world["root"]: [world["update"]]}  # half a thread
    assert not chk.ok


def test_apply_needs_the_digest_and_a_super_admin(world, tmp_path, capsys):
    sel = _file(tmp_path, world["root"], world["update"], world["lone"])
    token = P.digest([world["root"], world["update"], world["lone"]])
    assert P.main(["--select", sel]) == 0                        # dry run: clean
    assert P.main(["--select", sel, "--apply", "--actor", world["admin"],
                   "--confirm", "000000000000"]) == 1            # wrong digest
    with pytest.raises(SystemExit, match="not a Super Admin"):
        P.main(["--select", sel, "--apply", "--actor", world["staff"], "--confirm", token])
    with SessionLocal() as db:
        assert db.get(Review, world["lone"]) is not None         # nothing deleted yet

    assert P.main(["--select", sel, "--apply", "--actor", world["admin"],
                   "--confirm", token]) == 0
    with SessionLocal() as db:
        for key in ("root", "update", "lone"):
            assert db.get(Review, world[key]) is None
        # Everything not selected is untouched.
        for key in ("paid", "real", "demo"):
            assert db.get(Review, world[key]) is not None
        logs = db.scalars(select(ModerationLog).where(
            ModerationLog.action == ModerationAction.remove,
            ModerationLog.target_ref.in_([world["root"], world["update"], world["lone"]]))).all()
        assert len(logs) == 3
        assert {log.context["selection_digest"] for log in logs} == {token}
        assert all(log.context["event"] == "test_data_purge" for log in logs)


def test_a_review_with_money_evidence_is_never_purged(world, tmp_path):
    sel = _file(tmp_path, world["paid"])
    token = P.digest([world["paid"]])
    assert P.main(["--select", sel, "--apply", "--actor", world["admin"],
                   "--confirm", token]) == 1
    with SessionLocal() as db:
        assert db.get(Review, world["paid"]) is not None


def test_apply_is_refused_against_production(world, tmp_path, monkeypatch):
    from app.core import env_guard
    monkeypatch.setattr(env_guard, "production_signals",
                        lambda extra=None: ["DATABASE_URL references the production project"])
    sel = _file(tmp_path, world["lone"])
    token = P.digest([world["lone"]])
    for extra in ([], ["--allow-production"]):
        with pytest.raises(SystemExit):
            P.main(["--select", sel, "--apply", "--actor", world["admin"],
                    "--confirm", token, *extra])
    with SessionLocal() as db:
        assert db.get(Review, world["lone"]) is not None


def test_the_default_listing_always_checks_clean(world):
    """A thread with one blocked entry is left out whole, never half-selected."""
    import io
    with SessionLocal() as db:
        c = Commission(commission_id=f"com_{uuid.uuid4().hex[:12]}",
                       target_type=CommissionTarget.review, review_id=world["update"],
                       reviewer_share_bps=4000, platform=Platform.lazada,
                       gross_amount=Decimal("5.00"), reviewer_share=Decimal("2.00"),
                       platform_share=Decimal("1.50"), honesty_fund_share=Decimal("1.50"),
                       currency="PHP", csv_source="purge-test", row_reference=uuid.uuid4().hex,
                       order_status="Completed", cycle_month=date(1975, 1, 1))
        db.add(c)
        db.commit()
        rows = P.candidates(db, [world["root"], world["update"], world["lone"]])
        blocked = P.financial_blockers(db, [r.id for r in rows])
        out = io.StringIO()
        P.write_listing(rows, blocked, out)
        selected = [line.split("\t")[0] for line in out.getvalue().splitlines()
                    if line and not line.startswith("#")]
        assert selected == [str(world["lone"])]
        assert P.check_selection(db, [uuid.UUID(i) for i in selected]).ok


def _report(db, target_type, target_ref, *, resolved=False) -> None:
    from app.models.enums import ModerationTargetType, ReportResolution
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}", action=ModerationAction.report,
        target_type=getattr(ModerationTargetType, target_type), target_ref=target_ref,
        resolution=ReportResolution.dismissed if resolved else None,
        resolved_at=datetime.now(UTC) if resolved else None))


def test_an_open_report_blocks_and_a_closed_one_does_not(world):
    """Someone's complaint still waiting on a decision is not test clutter:
    resolve it first. A closed report is history and stays behind."""
    from app.models.comment import ReviewComment
    with SessionLocal() as db:
        author = db.get(Review, world["lone"]).author_id
        comment = ReviewComment(review_id=world["root"], author_id=author, body="Reported reply")
        db.add(comment)
        db.flush()
        _report(db, "review", world["lone"])                      # open, on the review
        _report(db, "comment", comment.id)                        # open, on a comment under it
        _report(db, "review", world["demo"], resolved=True)       # closed: history
        db.commit()
        chk = P.check_selection(db, [world["root"], world["update"], world["lone"], world["demo"]])
    assert chk.blocked == {world["lone"]: ["1 open report"], world["root"]: ["1 open report"]}
    assert world["demo"] not in chk.blocked
    assert not chk.ok


def test_a_purge_takes_its_price_reports_and_refreshes_the_product(world, tmp_path):
    """Price reports made from purged reviews are test data too; left behind they
    would stay public with no source. The product's counts follow the purge."""
    from app.models.enums import PriceObservationSource, PriceObservationStatus
    from app.models.product import PriceHistory
    with SessionLocal() as db:
        lone = db.get(Review, world["lone"])
        product_id = lone.product_id
        db.add(PriceHistory(product_id=product_id, platform=Platform.shopee,
                            price=Decimal("499.00"), observed_at=date(2026, 9, 1),
                            submitted_by=lone.author_id, review_id=lone.id,
                            status=PriceObservationStatus.approved,
                            source=PriceObservationSource.review))
        db.commit()
        from app.services.review_service import recompute_product_aggregates
        recompute_product_aggregates(db, product_id)
        db.commit()
        before = db.get(Product, product_id).review_count

    sel = _file(tmp_path, world["lone"])
    token = P.digest([world["lone"]])
    assert P.main(["--select", sel, "--apply", "--actor", world["admin"],
                   "--confirm", token]) == 0
    with SessionLocal() as db:
        assert db.scalar(select(PriceHistory).where(
            PriceHistory.review_id == world["lone"])) is None
        # One thread (the lone review) left the product's public count.
        assert db.get(Product, product_id).review_count == before - 1

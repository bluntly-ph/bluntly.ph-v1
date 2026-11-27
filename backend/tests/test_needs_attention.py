"""The admin Overview's "Needs attention" panel (meeting 2026-10-02).

Counts are measured as deltas: the database is shared with the rest of the
suite, so a test asserts what its own rows changed, never an absolute number.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.enums import (
    ModerationAction,
    ModerationReason,
    ModerationTargetType,
    ProductStatus,
)
from app.services import needs_attention_service as svc
from tests.conftest import make_user, register_and_token, requires_db

ENDPOINT = "/api/v1/admin/analytics/needs-attention"


class _Boom:
    def __init__(self):
        self.rolled_back = 0

    def scalar(self, *a, **k):
        raise LookupError("simulated")

    def scalars(self, *a, **k):
        raise LookupError("simulated")

    def execute(self, *a, **k):
        raise LookupError("simulated")

    def rollback(self):
        self.rolled_back += 1


def _counts(groups) -> dict[str, int | None]:
    return {i.key: i.count for g in groups for i in g.items}


# Degradation ---------------------------------------------------------------

def test_a_failing_count_is_null_not_zero_and_the_panel_still_answers():
    session = _Boom()
    groups = svc.needs_attention(session, super_admin=True)
    counts = _counts(groups)
    assert counts and all(v is None for v in counts.values()), \
        "a count that could not be computed must not read as 'nothing waiting'"
    assert session.rolled_back == len(counts), "each failure rolls the session back"


def test_the_groups_are_in_the_meetings_order():
    groups = svc.needs_attention(_Boom(), super_admin=True)
    assert [g.key for g in groups] == ["moderation", "integrity", "catalog", "money"]


def test_an_administrator_does_not_get_the_super_admin_routing_count():
    admin = _counts(svc.needs_attention(_Boom(), super_admin=False))
    owner = _counts(svc.needs_attention(_Boom(), super_admin=True))
    assert "it_depends_routing" not in admin
    assert "it_depends_routing" in owner


# Access --------------------------------------------------------------------

@requires_db
def test_anonymous_is_denied(client):
    assert client.get(ENDPOINT).status_code == 401


@requires_db
def test_a_member_is_denied(client):
    _, token, _ = register_and_token(client, role="user")
    assert client.get(ENDPOINT, headers={"Authorization": f"Bearer {token}"}).status_code == 403


@requires_db
def test_staff_get_the_panel_scoped_to_their_role(client):
    _, admin, _ = register_and_token(client, role="administrator")
    _, owner, _ = register_and_token(client, role="super_admin")
    a = client.get(ENDPOINT, headers={"Authorization": f"Bearer {admin}"})
    o = client.get(ENDPOINT, headers={"Authorization": f"Bearer {owner}"})
    assert a.status_code == 200 and o.status_code == 200
    a_keys = {i["key"] for g in a.json()["groups"] for i in g["items"]}
    o_keys = {i["key"] for g in o.json()["groups"] for i in g["items"]}
    assert "it_depends_routing" not in a_keys
    assert o_keys - a_keys == {"it_depends_routing"}
    assert all(isinstance(i["count"], int)
               for g in o.json()["groups"] for i in g["items"])


# Counts --------------------------------------------------------------------

def _report(db, target_type, target_ref, *, reporter, resolved=False):
    from app.models.moderation import ModerationLog

    row = ModerationLog(action=ModerationAction.report, target_type=target_type,
                        target_ref=target_ref, reporter_id=reporter.id,
                        reason=ModerationReason.spam)
    if resolved:
        row.resolution = "dismissed"
        row.resolved_at = datetime.now(UTC)
    db.add(row)
    db.flush()
    return row


def _detail_items(groups) -> int:
    detail = next(i.detail for g in groups for i in g.items if i.key == "open_reports")
    return int(detail.split()[1]) if detail else 0


@requires_db
def test_two_reports_on_one_answer_are_two_reports_on_one_item(db):
    """MQA-045: "Open reports" is what the Reports view lists - one row per
    report - and the distinct items are named beside it, never swapped in."""
    before_groups = svc.needs_attention(db, super_admin=True)
    before = _counts(before_groups)
    answer = uuid.uuid4()
    _report(db, ModerationTargetType.answer, answer, reporter=make_user(db))
    _report(db, ModerationTargetType.answer, answer, reporter=make_user(db))
    after_groups = svc.needs_attention(db, super_admin=True)
    after = _counts(after_groups)
    assert after["answers_to_moderate"] == before["answers_to_moderate"] + 1
    assert after["open_reports"] == before["open_reports"] + 2
    assert _detail_items(after_groups) == _detail_items(before_groups) + 1


@requires_db
def test_the_overview_and_the_reports_view_give_the_same_numbers(client):
    """MQA-045 as the tester saw it: Overview 4, Reports tab 6, for the same
    open reports. Both are now read from report_service.count_reports."""
    from app.db.session import SessionLocal
    from app.models.moderation import ModerationLog

    _, admin, _ = register_and_token(client, role="administrator")
    headers = {"Authorization": f"Bearer {admin}"}
    with SessionLocal() as db:
        reporters = [make_user(db) for _ in range(3)]
        review = uuid.uuid4()
        for r in reporters:     # three reports on one review, one on another
            db.add(ModerationLog(action=ModerationAction.report,
                                 target_type=ModerationTargetType.review, target_ref=review,
                                 reporter_id=r.id, reason=ModerationReason.spam))
        db.add(ModerationLog(action=ModerationAction.report,
                             target_type=ModerationTargetType.review, target_ref=uuid.uuid4(),
                             reporter_id=reporters[0].id, reason=ModerationReason.spam))
        db.commit()

    panel = client.get(ENDPOINT, headers=headers).json()
    row = next(i for g in panel["groups"] for i in g["items"] if i["key"] == "open_reports")
    queue = client.get("/api/v1/admin/reports?limit=1", headers=headers).json()
    assert len(queue["items"]) == 1, "one row on this page..."
    assert queue["total"] == row["count"], "...but the total is every open report"
    assert row["detail"] == f"on {queue['items_total']} item" + \
        ("" if queue["items_total"] == 1 else "s")
    assert queue["total"] >= queue["items_total"] + 2


@requires_db
def test_a_paged_report_total_counts_every_match_not_the_page(client):
    """Resolved/escalated/all are paged in SQL; their total used to be the
    length of the page it came back with."""
    _, admin, _ = register_and_token(client, role="administrator")
    headers = {"Authorization": f"Bearer {admin}"}
    page = client.get("/api/v1/admin/reports?status=all&limit=1", headers=headers).json()
    everything = client.get("/api/v1/admin/reports?status=all&limit=100", headers=headers).json()
    assert len(page["items"]) <= 1
    assert page["total"] == everything["total"] >= len(everything["items"])


@requires_db
def test_a_resolved_report_is_not_waiting(db):
    before = _counts(svc.needs_attention(db, super_admin=True))
    _report(db, ModerationTargetType.review, uuid.uuid4(), reporter=make_user(db),
            resolved=True)
    after = _counts(svc.needs_attention(db, super_admin=True))
    assert after["open_reports"] == before["open_reports"]


@requires_db
def test_a_member_under_investigation_is_counted(db):
    before = svc.under_investigation(db)
    make_user(db, is_under_investigation=True)
    make_user(db)
    assert svc.under_investigation(db) == before + 1


@requires_db
def test_products_without_a_usable_picture_follow_the_sites_rule(db):
    from app.models.product import Product

    before = svc.products_without_image(db)
    for url in (None, "https://example.com/x.jpg", "/relative.png",
                "https://cdn.test/real.jpg"):
        db.add(Product(canonical_name=f"Fixture {uuid.uuid4().hex[:8]}",
                       status=ProductStatus.canonicalized, image_url=url))
    db.add(Product(canonical_name=f"Fixture {uuid.uuid4().hex[:8]}",
                   status=ProductStatus.pending, image_url=None))
    db.flush()
    assert svc.products_without_image(db) == before + 3, \
        "missing, placeholder and relative count; a real URL and a pending product do not"


def test_the_catalog_group_leads_with_the_product_queue():
    """Figma 7966:11087: the Products nav badge repeats the Queue tab's count."""
    catalog = next(g for g in svc.needs_attention(_Boom(), super_admin=False) if g.key == "catalog")
    assert [i.key for i in catalog.items][0] == "products_to_review"

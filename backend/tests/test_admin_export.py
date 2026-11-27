"""Admin Export CSV (Figma Overlay/Admin/Export 8237:25470; migration 0079)."""

from __future__ import annotations

import io
import uuid
import zipfile

from sqlalchemy import select

from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_the_export_is_staff_only_complete_and_audited(client, db):
    from app.models.enums import ModerationAction
    from app.models.moderation import ModerationLog

    admin_id, admin, _ = register_and_token(client, role="administrator")
    _, member, _ = register_and_token(client)
    url = "/api/v1/admin/export"
    assert client.get(url, headers=_h(member), params={"include": "activity"}).status_code == 403
    assert client.get(url, params={"include": "activity"}).status_code == 401

    res = client.get(url, headers=_h(admin), params={
        "include": "activity,moderation,earnings,analytics", "period": "30d"})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert res.headers["content-disposition"].startswith(
        'attachment; filename="bluntly-admin-export-')
    names = sorted(zipfile.ZipFile(io.BytesIO(res.content)).namelist())
    assert names == sorted([
        "activity-log.csv", "moderation.csv", "analytics-summary.csv",
        "earnings-commissions.csv", "earnings-payout-summary.csv", "earnings-remittances.csv",
        "earnings-honesty-fund-reviews.csv", "earnings-honesty-fund-cycles.csv"])
    analytics = zipfile.ZipFile(io.BytesIO(res.content)).read("analytics-summary.csv")
    assert analytics.decode("utf-8-sig").startswith("section,metric,value,previous")

    db.expire_all()
    log = db.scalars(select(ModerationLog).where(
        ModerationLog.action == ModerationAction.data_export,
        ModerationLog.moderator_id == uuid.UUID(admin_id))).one()
    assert log.context["period"] == "30d" and "earnings" in log.context["sections"]

    for params in ({"include": ""}, {"include": "activity,passwords"},
                   {"include": "activity", "period": "5y"}):
        assert client.get(url, headers=_h(admin), params=params).status_code == 422


def test_names_are_shortened_and_emails_removed():
    from app.services.admin_export import scrub, short_name

    assert short_name("Joanna Reyes") == "Joanna R."
    assert short_name("@mariareyes") == "@mariareyes"
    assert short_name("Andrea") == "Andrea"
    assert short_name(None) == ""
    assert scrub("Paid to maria.reyes+pp@gmail.com via PayPal") == (
        "Paid to [email removed] via PayPal")
    assert scrub(42) == 42

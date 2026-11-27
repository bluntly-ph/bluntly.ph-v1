"""Admin Analytics (Figma Screen/Admin/Analytics 8071:16115): staff only, every
range, and figures that move with recorded rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.db.session import SessionLocal
from app.models.enums import Verdict
from app.models.product import Product
from app.models.review import Review
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_analytics_summary_is_staff_only_and_counts_real_rows(client):
    author_id, member, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    assert client.get("/api/v1/admin/analytics/summary").status_code == 401
    assert client.get("/api/v1/admin/analytics/summary", headers=_auth(member)).status_code == 403
    assert client.get("/api/v1/admin/analytics/summary?range=2y",
                      headers=_auth(admin)).status_code == 422

    def published() -> int:
        body = client.get("/api/v1/admin/analytics/summary?range=7d", headers=_auth(admin)).json()
        return int(Decimal(next(k for k in body["kpis"]
                                if k["key"] == "reviews_published")["current"]))

    before = published()
    db = SessionLocal()
    try:
        product = Product(canonical_name=f"Analytics {uuid.uuid4().hex[:6]}")
        db.add(product)
        db.flush()
        db.add(Review(product_id=product.id, author_id=uuid.UUID(author_id), title="A",
                      discussion="Body text for the analytics review.",
                      verdict=Verdict.yes_absolutely, star_rating=Decimal("4"),
                      published_at=datetime.now(UTC)))
        db.commit()
    finally:
        db.close()
    assert published() == before + 1

    for r, points in (("7d", 7), ("30d", 30), ("90d", 13), ("12m", 53)):
        body = client.get(f"/api/v1/admin/analytics/summary?range={r}", headers=_auth(admin)).json()
        assert len(body["series"]) == points
        assert {k["key"] for k in body["kpis"]} == {"reviews_published", "votes_cast",
                                                    "affiliate_clicks", "orders", "commission"}
        assert set(body["funnel"]) == {"review_views", "affiliate_clicks", "orders", "commission"}
        assert set(body["needs_a_look"]) == {"voting_rings", "reused_photos",
                                             "under_investigation", "failed_payouts"}

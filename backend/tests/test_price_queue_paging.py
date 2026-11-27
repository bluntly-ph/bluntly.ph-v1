"""The admin Prices screen (MQA-043, MQA-007, MQA-042).

MQA-043: the page asked for 100 rows, said "100 prices waiting" and had no way
to reach the other 64. MQA-007: oldest first only. MQA-042: no filters, and one
product's prices were scattered through the list.

The list now pages (offset), counts (GET /count with the same filters), sorts
(oldest / newest / product) and filters (marketplace, source, why it waits,
product name, hide my own), and each row says what the product usually costs
there. Every test narrows by a product name unique to it, because the database
is shared with the rest of the suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.db.session import SessionLocal
from app.models.enums import Platform, PriceObservationSource, PriceObservationStatus
from app.models.product import PriceHistory
from tests.conftest import make_user, register_and_token, requires_db

QUEUE = "/api/v1/admin/price-observations"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _products(client, headers, token: str, n: int) -> list[str]:
    ids = []
    for i in range(n):
        res = client.post("/api/v1/products", headers=headers,
                          json={"name": f"{token} {chr(65 + i)} fan", "category": "electronics"})
        assert res.status_code == 201, res.text
        ids.append(res.json()["id"])
    return ids


def _observe(db, product_id: str, price: str, *, by, platform=Platform.shopee,
             source=PriceObservationSource.manual, hold="no_baseline",
             status=PriceObservationStatus.pending, minutes_ago: int = 0) -> PriceHistory:
    row = PriceHistory(product_id=uuid.UUID(product_id), submitted_by=by.id if by else None,
                       platform=platform, price=Decimal(price),
                       observed_at=date.today() - timedelta(days=1), variant=None,
                       source=source, status=status,
                       hold_reason=hold if status == PriceObservationStatus.pending else None)
    row.created_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    db.add(row)
    return row


def _setup(client):
    """Three products, eleven pending prices, one of them the moderator's own."""
    admin_id, admin_token, _ = register_and_token(client, role="administrator")
    headers = _auth(admin_token)
    token = f"PQ{uuid.uuid4().hex[:8]}"
    a, b, c = _products(client, headers, token, 3)
    with SessionLocal() as db:
        from app.models.user import User
        admin = db.get(User, uuid.UUID(str(admin_id)))
        people = [make_user(db) for _ in range(4)]
        minute = 100
        for product in (a, b, c):
            for i, person in enumerate(people[:3]):
                minute -= 1
                _observe(db, product, f"{700 + i}.00", by=person, minutes_ago=minute,
                         platform=Platform.lazada if i == 2 else Platform.shopee,
                         source=PriceObservationSource.review if i == 1 else
                         PriceObservationSource.manual)
        # An outlier: a fan that usually costs about ₱700 on Shopee.
        for person in people:
            _observe(db, a, "699.00", by=person, status=PriceObservationStatus.approved)
        _observe(db, a, "24444.00", by=people[3], hold="outlier", minutes_ago=1)
        _observe(db, b, "710.00", by=admin, minutes_ago=0)     # the moderator's own
        db.commit()
    return headers, token, (a, b, c)


def _walk(client, headers, params: dict, limit: int) -> list[dict]:
    seen, offset = [], 0
    while True:
        page = client.get(QUEUE, headers=headers,
                          params={**params, "limit": limit, "offset": offset})
        assert page.status_code == 200, page.text
        rows = page.json()
        seen += rows
        if len(rows) < limit:
            return seen
        offset += limit


@requires_db
def test_every_waiting_price_is_reachable_and_the_total_is_the_pages(client):
    """MQA-043: the total is every match, and walking the pages reaches all of
    them exactly once, for each filter set."""
    headers, token, (a, _, _) = _setup(client)
    for params in ({"q": token}, {"q": token, "platform": "lazada"},
                   {"q": token, "source": "review"}, {"q": token, "held": "outlier"},
                   {"q": token, "mine": "hide"}, {"q": token, "product_id": a},
                   {"q": token, "sort": "newest"}, {"q": token, "sort": "product"}):
        total = client.get(f"{QUEUE}/count", headers=headers, params=params).json()["total"]
        rows = _walk(client, headers, params, limit=4)
        assert len(rows) == total, params
        assert len({r["id"] for r in rows}) == total, f"a row repeated across pages: {params}"
    assert client.get(f"{QUEUE}/count", headers=headers, params={"q": token}).json()["total"] == 11


@requires_db
def test_the_orders(client):
    """MQA-007: newest first is one choice away; oldest stays the default."""
    headers, token, _ = _setup(client)
    oldest = _walk(client, headers, {"q": token}, limit=50)
    newest = _walk(client, headers, {"q": token, "sort": "newest"}, limit=50)
    assert [r["id"] for r in newest] == [r["id"] for r in reversed(oldest)]
    assert oldest[0]["created_at"] <= oldest[-1]["created_at"]
    by_product = _walk(client, headers, {"q": token, "sort": "product"}, limit=50)
    names = [r["product_name"] for r in by_product]
    assert names == sorted(names, key=str.lower), "one product's prices sit together"


@requires_db
def test_the_filters_narrow_to_what_they_say(client):
    """MQA-042: marketplace, source, why it waits, product, and my own."""
    headers, token, (a, b, _) = _setup(client)

    def rows(**params):
        return _walk(client, headers, {"q": token, **params}, limit=50)

    assert {r["platform"] for r in rows(platform="lazada")} == {"lazada"}
    assert {r["source"] for r in rows(source="review")} == {"review"}
    outliers = rows(held="outlier")
    assert [Decimal(r["price"]) for r in outliers] == [Decimal("24444.00")]
    assert {r["product_id"] for r in rows(product_id=b)} == {b}

    everything = rows()
    mine = [r for r in everything if r["reported_by_viewer"]]
    assert len(mine) == 1 and Decimal(mine[0]["price"]) == Decimal("710.00")
    assert not any(r["reported_by_viewer"] for r in rows(mine="hide"))
    assert len(rows(mine="hide")) == len(everything) - 1


@requires_db
def test_an_outlier_shows_what_the_product_usually_costs(client):
    """The ₱24,444 fan is shown beside its usual ₱699 on the same marketplace;
    a product with no approved prices says nothing rather than a guess."""
    headers, token, (a, b, _) = _setup(client)
    outlier = _walk(client, headers, {"q": token, "held": "outlier"}, limit=50)[0]
    assert Decimal(outlier["usual_median"]) == Decimal("699.00")
    assert outlier["usual_count"] == 4
    lazada_a = [r for r in _walk(client, headers, {"q": token, "product_id": a,
                                                   "platform": "lazada"}, limit=50)]
    assert lazada_a and all(r["usual_median"] is None and r["usual_count"] == 0
                            for r in lazada_a), "Shopee prices are not Lazada's range"
    assert all(r["usual_median"] is None
               for r in _walk(client, headers, {"q": token, "product_id": b}, limit=50))


@requires_db
def test_a_search_is_a_literal_not_a_pattern(client):
    headers, token, _ = _setup(client)
    assert client.get(f"{QUEUE}/count", headers=headers,
                      params={"q": f"{token[:4]}%"}).json()["total"] == 0


@requires_db
def test_bad_parameters_are_refused_and_members_are_denied(client):
    _, admin, _ = register_and_token(client, role="administrator")
    _, member, _ = register_and_token(client)
    for params in ({"sort": "random"}, {"platform": "ebay"}, {"held": "maybe"},
                   {"mine": "only"}, {"offset": -1}, {"limit": 0}):
        assert client.get(QUEUE, headers=_auth(admin), params=params).status_code == 422, params
    assert client.get(f"{QUEUE}/count", headers=_auth(member)).status_code == 403
    assert client.get(f"{QUEUE}/count").status_code == 401

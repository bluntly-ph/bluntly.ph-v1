"""FR-2: the community price panel and the product comparison tool.

FR-2 verbatim: *"Price panel from community-submitted purchase price
observations — displayed only when ≥ 3 independent observations exist;
partial-data empty states specified."* and *"Product comparison tool:
side-by-side comparison using verified review scores, seller ratings, and
community price data."*

The threshold tests are the point of this file. "Independent" is read as
distinct submitters rather than distinct rows, because otherwise one person
posting three prices unlocks the panel alone — which is the exact thing a
threshold of three is there to prevent.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.schemas.product import _ph_today
from app.services import price_service
from tests.conftest import register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers) -> str:
    resp = client.post("/api/v1/products", headers=headers,
                       json={"name": f"FR2 {uuid.uuid4().hex[:10]}",
                             "category": "electronics"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


_OWN_REVIEWS: dict[tuple[str, str], str] = {}


def _own_review(client, headers, product_id) -> str:
    """The reporter's review of the product. Business Rules §16: a price report
    always belongs to an existing review, never stands alone."""
    key = (headers["Authorization"], product_id)
    if key not in _OWN_REVIEWS:
        created = client.post("/api/v1/reviews", headers=headers, json={
            "product_id": product_id, "title": "Bought it", "discussion": "Weeks of use.",
            "verdict": "yes_absolutely", "star_rating": 4})
        assert created.status_code == 201, created.text
        _OWN_REVIEWS[key] = created.json()["id"]
    return _OWN_REVIEWS[key]


def _observe(client, headers, product_id, price, days_ago=0, platform="shopee"):
    return client.post(f"/api/v1/products/{product_id}/prices", headers=headers, json={
        "review_id": _own_review(client, headers, product_id),
        "platform": platform,
        "price": str(price),
        "observed_at": (date.today() - timedelta(days=days_ago)).isoformat(),
        "variant": None,
    })


def _approve_pending(client, moderator_headers, product_id):
    """Approve every pending observation on one product, as a moderator would.

    Filtered by product: the CI database is cumulative, and an oldest-first
    queue would otherwise put this test's rows behind every earlier run's.
    """
    queue = client.get("/api/v1/admin/price-observations", headers=moderator_headers,
                       params={"product_id": product_id, "limit": 200})
    assert queue.status_code == 200, queue.text
    for item in queue.json():
        resp = client.post(f"/api/v1/admin/price-observations/{item['id']}/decision",
                           headers=moderator_headers, json={"decision": "approve"})
        assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------
# The threshold rule, unit level (no DB)
# --------------------------------------------------------------------------

def test_a_baseline_is_three_approved_prices():
    assert price_service.BASELINE_MIN_OBSERVATIONS == 3


def test_median_is_used_not_mean():
    """A single absurd entry must not move the headline number much.

    Prices across platforms and variants are a skewed sample; the mean is
    deliberately not offered so nobody builds a "market price" claim on it.
    """
    assert price_service._median([Decimal("100"), Decimal("110"), Decimal("100000")]) \
        == Decimal("110")
    assert price_service._median([Decimal("100"), Decimal("200")]) == Decimal("150")


# --------------------------------------------------------------------------
# Panel behaviour
# --------------------------------------------------------------------------

@requires_db
def test_price_history_waits_for_a_baseline_then_publishes_normal_prices(client):
    """Business Rules §16: brand-new products with no price history default to
    an admin glance until a real baseline exists; after that a normal price
    publishes at once and only a wild one is held."""
    tokens = [register_and_token(client)[1] for _ in range(5)]
    _, token_mod, _ = register_and_token(client, role="administrator")
    mod = _auth(token_mod)
    product_id = _product(client, _auth(tokens[0]))

    def panel():
        resp = client.get(f"/api/v1/products/{product_id}/prices")
        assert resp.status_code == 200, resp.text
        return resp.json()

    empty = panel()
    assert empty["sufficient"] is False and empty["series"] == {}

    # No baseline yet: each of the first three is held for a glance.
    for token, price in zip(tokens[:3], (1000, 1100, 1200), strict=True):
        created = _observe(client, _auth(token), product_id, price)
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "pending"
        assert created.json()["hold_reason"] == "no_baseline"
    assert panel()["pending_count"] == 3
    _approve_pending(client, mod, product_id)

    # A baseline exists: a normal price publishes without anyone's approval...
    normal = _observe(client, _auth(tokens[3]), product_id, 1150)
    assert normal.json()["status"] == "approved" and normal.json()["hold_reason"] is None
    # ...and a price wildly outside the range is held.
    wild = _observe(client, _auth(tokens[4]), product_id, 25)
    assert wild.json()["status"] == "pending" and wild.json()["hold_reason"] == "outlier"

    full = panel()
    assert full["sufficient"] is True
    assert full["observation_count"] == 4
    assert full["pending_count"] == 1
    assert list(full["series"]) == ["shopee"]          # one line per marketplace
    assert Decimal(full["low"]) == Decimal("1000")
    assert Decimal(full["high"]) == Decimal("1200")


@requires_db
def test_a_price_report_must_belong_to_the_reporters_own_review(client):
    _, token, _ = register_and_token(client)
    _, other, _ = register_and_token(client)
    headers = _auth(token)
    product_id = _product(client, headers)
    standalone = client.post(f"/api/v1/products/{product_id}/prices", headers=headers, json={
        "platform": "shopee", "price": "900", "observed_at": date.today().isoformat()})
    assert standalone.status_code == 422
    assert standalone.json()["code"] == "price_needs_review"
    theirs = _own_review(client, _auth(other), product_id)
    borrowed = client.post(f"/api/v1/products/{product_id}/prices", headers=headers, json={
        "review_id": theirs, "platform": "shopee", "price": "900",
        "observed_at": date.today().isoformat()})
    assert borrowed.status_code == 422


@requires_db
def test_submitting_a_price_requires_authentication(client):
    _, token, _ = register_and_token(client)
    product_id = _product(client, _auth(token))
    anon = client.post(f"/api/v1/products/{product_id}/prices", json={
        "platform": "shopee", "price": "999",
        "observed_at": date.today().isoformat(), "variant": None})
    assert anon.status_code == 401


@requires_db
def test_panel_is_public(client):
    _, token, _ = register_and_token(client)
    product_id = _product(client, _auth(token))
    assert client.get(f"/api/v1/products/{product_id}/prices").status_code == 200


@requires_db
def test_unknown_product_panel_is_404(client):
    assert client.get(f"/api/v1/products/{uuid.uuid4()}/prices").status_code == 404


@pytest.mark.parametrize("bad", [
    {"price": "0"},                                    # must be > 0
    {"price": "-5"},
    # Tomorrow in MANILA, not in UTC. The validator checks against the
    # Philippine date on purpose — `date.today()` is UTC on Vercel, and for the
    # eight hours where Manila is already the next day, UTC's "tomorrow" is
    # Manila's today and is legitimately accepted. Using UTC here made this
    # case fail on a CI runner at 18:47 UTC while the product was behaving
    # exactly as specified.
    {"observed_at": (_ph_today() + timedelta(days=1)).isoformat()},  # future
])
@requires_db
def test_invalid_observations_are_rejected(client, bad):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    product_id = _product(client, headers)
    body = {"platform": "shopee", "price": "500",
            "observed_at": date.today().isoformat(), "variant": None}
    body.update(bad)
    assert client.post(f"/api/v1/products/{product_id}/prices",
                       headers=headers, json=body).status_code == 422


# --------------------------------------------------------------------------
# Moderation: pending -> approved | rejected
# --------------------------------------------------------------------------

@requires_db
def test_a_first_observation_waits_for_an_admin_glance(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    product_id = _product(client, headers)

    resp = _observe(client, headers, product_id, 800)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "pending"      # no baseline yet (§16)
    assert resp.json()["source"] == "manual"

    panel = client.get(f"/api/v1/products/{product_id}/prices").json()
    assert panel["observation_count"] == 0
    assert panel["pending_count"] == 1


@requires_db
def test_only_a_moderator_decides_prices_and_never_their_own(client):
    _, user_token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    user, mod = _auth(user_token), _auth(mod_token)
    product_id = _product(client, user)

    theirs = _observe(client, user, product_id, 900).json()
    own = _observe(client, mod, product_id, 950).json()
    url = "/api/v1/admin/price-observations/{}/decision"

    assert client.get("/api/v1/admin/price-observations", headers=user).status_code == 403
    assert client.post(url.format(theirs["id"]), headers=user,
                       json={"decision": "approve"}).status_code == 403

    queue = client.get("/api/v1/admin/price-observations", headers=mod,
                       params={"product_id": product_id}).json()
    assert {item["id"] for item in queue} == {theirs["id"], own["id"]}

    self_decided = client.post(url.format(own["id"]), headers=mod, json={"decision": "approve"})
    assert self_decided.status_code == 422
    assert self_decided.json()["code"] == "self_decision"

    approved = client.post(url.format(theirs["id"]), headers=mod,
                           json={"decision": "approve", "note": "Plausible for this model."})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    again = client.post(url.format(theirs["id"]), headers=mod, json={"decision": "reject"})
    assert again.status_code == 409
    assert again.json()["code"] == "price_observation_already_decided"


@requires_db
def test_a_rejected_price_never_counts(client):
    tokens = [register_and_token(client)[1] for _ in range(3)]
    _, mod_token, _ = register_and_token(client, role="administrator")
    mod = _auth(mod_token)
    product_id = _product(client, _auth(tokens[0]))
    ids = [_observe(client, _auth(token), product_id, price).json()["id"]
           for token, price in zip(tokens, (1000, 1100, 1), strict=True)]
    for obs_id, decision in zip(ids, ("approve", "approve", "reject"), strict=True):
        assert client.post(f"/api/v1/admin/price-observations/{obs_id}/decision",
                           headers=mod, json={"decision": decision}).status_code == 200

    panel = client.get(f"/api/v1/products/{product_id}/prices").json()
    assert panel["sufficient"] is True
    assert panel["independent_count"] == 2
    assert Decimal(panel["low"]) == Decimal("1000")      # the rejected 1 is not in it
    assert panel["pending_count"] == 0


def _review_body(product_id: str, **extra) -> dict:
    body = {"product_id": product_id, "title": "Kept the price honest",
            "discussion": "Used it daily for a month and it held up fine.",
            "verdict": "it_depends", "star_rating": 4}
    body.update(extra)
    return body


@requires_db
def test_the_price_paid_in_a_review_becomes_a_pending_observation(client):
    """Contract: "Let's Talk Money must feed" the price pipeline."""
    _, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    headers = _auth(token)
    product_id = _product(client, headers)

    resp = client.post("/api/v1/reviews", headers=headers, json=_review_body(
        product_id, price_paid="1299.00", price_platform="lazada"))
    assert resp.status_code == 201, resp.text

    queue = client.get("/api/v1/admin/price-observations", headers=_auth(mod_token),
                       params={"product_id": product_id}).json()
    assert len(queue) == 1
    assert queue[0]["source"] == "review"
    assert queue[0]["platform"] == "lazada"
    assert Decimal(queue[0]["price"]) == Decimal("1299.00")
    assert client.get(f"/api/v1/products/{product_id}/prices").json()["pending_count"] == 1


@requires_db
def test_a_price_without_a_marketplace_stays_on_the_review(client):
    """An observation needs a marketplace; guessing one would fabricate it."""
    _, token, _ = register_and_token(client)
    _, mod_token, _ = register_and_token(client, role="administrator")
    headers = _auth(token)
    product_id = _product(client, headers)

    resp = client.post("/api/v1/reviews", headers=headers,
                       json=_review_body(product_id, price_paid="1299.00"))
    assert resp.status_code == 201, resp.text
    queue = client.get("/api/v1/admin/price-observations", headers=_auth(mod_token),
                       params={"product_id": product_id}).json()
    assert queue == []


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------

@requires_db
def test_compare_two_products_side_by_side(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    first, second = _product(client, headers), _product(client, headers)

    resp = client.get(f"/api/v1/products/compare?ids={first},{second}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["entries"]) == 2
    assert body["not_found"] == []
    entry = body["entries"][0]
    # Every comparable field FR-2 names, minus seller ratings (withdrawn).
    for field in ("product", "price", "review_count", "avg_rating",
                  "trust_score", "verified_review_count"):
        assert field in entry
    assert entry["price"]["sufficient"] is False, "no price data yet"


@requires_db
def test_compare_is_public(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    a, b = _product(client, headers), _product(client, headers)
    assert client.get(f"/api/v1/products/compare?ids={a},{b}").status_code == 200


@requires_db
def test_compare_rejects_too_few_and_too_many(client):
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    ids = [_product(client, headers) for _ in range(5)]
    assert client.get(f"/api/v1/products/compare?ids={ids[0]}").status_code == 422
    assert client.get("/api/v1/products/compare?ids=").status_code == 422
    assert client.get(f"/api/v1/products/compare?ids={','.join(ids)}").status_code == 422


@requires_db
def test_compare_reports_missing_products_without_losing_the_rest(client):
    """A shared comparison link outliving one product must not 404 entirely."""
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    real_a, real_b = _product(client, headers), _product(client, headers)
    ghost = uuid.uuid4()

    resp = client.get(f"/api/v1/products/compare?ids={real_a},{real_b},{ghost}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["entries"]) == 2
    assert body["not_found"] == [str(ghost)]


@requires_db
def test_compare_rejects_non_uuid_ids(client):
    assert client.get("/api/v1/products/compare?ids=not-a-uuid,also-bad").status_code == 422


@requires_db
def test_compare_carries_price_data_once_prices_are_approved(client):
    _, t1, _ = register_and_token(client)
    _, t2, _ = register_and_token(client)
    _, t3, _ = register_and_token(client)
    h1 = _auth(t1)
    first, second = _product(client, h1), _product(client, h1)
    for token in (t1, t2, t3):
        assert _observe(client, _auth(token), first, 2500).status_code == 201
    _, mod_token, _ = register_and_token(client, role="administrator")
    _approve_pending(client, _auth(mod_token), first)

    body = client.get(f"/api/v1/products/compare?ids={first},{second}").json()
    by_id = {e["product"]["id"]: e for e in body["entries"]}
    assert by_id[first]["price"]["sufficient"] is True
    assert Decimal(by_id[first]["price"]["median"]) == Decimal("2500")
    # The other product has none, and says so rather than borrowing.
    assert by_id[second]["price"]["sufficient"] is False


@requires_db
def test_comparison_never_claims_a_seller_rating(client):
    """FR-2 named seller ratings; they were withdrawn 2026-07-28.

    Rather than invent a value, the field is absent. On a platform about honest
    reviews, a fabricated rating would be the worst possible shortcut.
    """
    _, token, _ = register_and_token(client)
    headers = _auth(token)
    a, b = _product(client, headers), _product(client, headers)
    body = client.get(f"/api/v1/products/compare?ids={a},{b}").json()
    blob = str(body).lower()
    assert "seller_rating" not in blob
    assert "seller_trust" not in blob


def test_compare_route_is_declared_before_the_product_id_route():
    """Route ORDER regression - genuinely no database.

    `/compare` and `/{product_id}` both match the path "compare", and FastAPI
    resolves in declaration order. When /compare was appended to the end of the
    module the id route won, tried to parse "compare" as a UUID, and every
    comparison 422'd in production while passing every DB-backed test - those
    build their URLs from real ids, so they exercise the query string rather
    than the path collision.

    An earlier version of this test issued a real request and claimed to need
    no database. It did: /compare queries products, so it failed for anyone
    without Postgres. Asserting on the route table tests the thing that
    actually broke and runs anywhere.
    """
    from app.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    compare_at = paths.index("/api/v1/products/compare")
    by_id_at = paths.index("/api/v1/products/{product_id}")
    assert compare_at < by_id_at, (
        "/products/compare must be declared before /products/{product_id}; "
        f"found compare at {compare_at}, id route at {by_id_at}"
    )

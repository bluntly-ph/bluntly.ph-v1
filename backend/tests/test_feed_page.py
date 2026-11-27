"""GET /reviews/feed/page and the card shape (cost work, 2026-10-22).

`/search` and `/feed` asked the API twice per render (the page, then its
total), and every card list carried each review's full text: up to 5,000
characters of discussion and three 2,000-character fields, for a card that
shows 180. The page and its total now come back in one call, and card lists
carry only what a card reads, with a 200-character excerpt cut in SQL.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import make_user, requires_db

NOW = datetime.now(UTC)


def _product(db, *, category="electronics", name=None):
    from app.models.product import Product

    product = Product(canonical_name=name or f"Page probe {uuid.uuid4().hex[:8]}",
                      category=category)
    db.add(product)
    db.flush()
    return product


def _review(db, product, *, title, discussion="Body.", stars=4, days_ago=1,
            helpful=0, verdict=None, **extra):
    from app.models.enums import Verdict
    from app.models.review import Review

    at = NOW - timedelta(days=days_ago, minutes=len(title))
    review = Review(product_id=product.id, author_id=make_user(db).id, title=title,
                    discussion=discussion, verdict=verdict or Verdict.it_depends,
                    star_rating=stars, is_removed=False, published_at=at, created_at=at,
                    helpful_votes=helpful, **extra)
    db.add(review)
    db.flush()
    return review


@pytest.fixture
def seeded(db):
    """Nine reviews under one tag, across two products, categories and ages."""
    from app.models.enums import Verdict

    tag = uuid.uuid4().hex[:10]
    phone = _product(db, category="electronics", name=f"Phone {tag}")
    serum = _product(db, category="beauty", name=f"Serum {tag}")
    rows = []
    for i in range(6):
        rows.append(_review(db, phone, title=f"{tag} phone take {i}", stars=5 if i % 2 else 3,
                            days_ago=2 + i * 40, helpful=i,
                            verdict=Verdict.yes_absolutely if i % 3 == 0 else None))
    for i in range(3):
        rows.append(_review(db, serum, title=f"{tag} serum take {i}", stars=2, days_ago=3 + i))
    db.commit()
    return tag, phone, serum, rows


# The filter combinations the search and feed pages send.
COMBINATIONS = [
    {},
    {"category": ["electronics"]},
    {"category": ["electronics", "beauty"]},
    {"stars": [5]},
    {"stars": [2, 3]},
    {"recommends": "true"},
    {"period": "month"},
    {"period": "year", "category": ["electronics"]},
    {"sort": "newest"},
    {"sort": "lowest", "stars": [3, 5]},
]


@requires_db
@pytest.mark.parametrize("filters", COMBINATIONS, ids=[json.dumps(c) for c in COMBINATIONS])
def test_the_pages_total_equals_count_feed(client, db, seeded, filters):
    from app.services import review_filters, review_service

    tag = seeded[0]
    params = {"q": tag, "limit": 4, **filters}
    page = client.get("/api/v1/reviews/feed/page", params=params)
    assert page.status_code == 200, page.text
    body = page.json()

    show = review_filters.FeedShow.of(
        stars=filters.get("stars"), photos=False, verified=False,
        recommends=filters.get("recommends") == "true", variant=None)
    expected = review_service.count_feed(
        db, q=tag, category=filters.get("category"), period=filters.get("period"),
        show=show)
    assert body["total"] == expected
    # And it agrees with the endpoint the filter sheet keeps using.
    count = client.get("/api/v1/reviews/feed/count",
                       params={k: v for k, v in params.items() if k not in ("limit", "sort")})
    assert count.json()["total"] == expected
    assert len(body["items"]) == min(4, expected)


@requires_db
def test_the_page_lists_exactly_what_feed_lists(client, seeded):
    tag = seeded[0]
    for offset in (0, 4, 8):
        params = {"q": tag, "limit": 4, "offset": offset, "sort": "newest"}
        page = client.get("/api/v1/reviews/feed/page", params=params).json()
        feed = client.get("/api/v1/reviews/feed", params=params).json()
        assert [i["review"]["id"] for i in page["items"]] == [i["review"]["id"] for i in feed]


@requires_db
def test_a_page_past_the_end_still_knows_the_total(client, seeded):
    """No row to carry count(*) OVER (): the fallback asks count_feed."""
    tag = seeded[0]
    body = client.get("/api/v1/reviews/feed/page",
                      params={"q": tag, "limit": 4, "offset": 40}).json()
    assert body["items"] == []
    assert body["total"] == 9


@requires_db
def test_no_match_is_an_empty_page_and_zero(client):
    body = client.get("/api/v1/reviews/feed/page",
                      params={"q": f"nothing-{uuid.uuid4().hex}"}).json()
    assert body == {"items": [], "total": 0}


CARD_REVIEW_KEYS = {
    "id", "title", "verdict", "star_rating", "excerpt", "photo_urls", "photo_url",
    "helpful_votes", "unhelpful_votes", "created_at", "my_vote", "has_trust_badge",
}


@requires_db
def test_cards_carry_only_card_fields(client, seeded):
    tag = seeded[0]
    for url in ("/api/v1/reviews/feed/page", "/api/v1/reviews/feed"):
        body = client.get(url, params={"q": tag, "limit": 2, "view": "card"}).json()
        item = (body["items"] if isinstance(body, dict) else body)[0]
        assert set(item) == {"review", "author", "product", "comment_count"}
        assert set(item["review"]) == CARD_REVIEW_KEYS, set(item["review"]) ^ CARD_REVIEW_KEYS
        for absent in ("discussion", "verdict_explanation", "target_audience",
                       "anti_target_audience", "pros", "cons"):
            assert absent not in item["review"]
        assert set(item["product"]) == {"id", "canonical_name", "category"}
        assert set(item["author"]) == {"id", "username", "display_name", "avatar_url",
                                       "trust_stage", "trust_level_name", "reputation_score"}


@requires_db
def test_the_default_feed_shape_is_unchanged(client, seeded):
    """Other API clients (the e2e suite, scripts) still get the full review."""
    tag = seeded[0]
    item = client.get("/api/v1/reviews/feed", params={"q": tag, "limit": 1}).json()[0]
    assert "discussion" in item["review"] and "excerpt" not in item["review"]


@requires_db
def test_the_excerpt_is_cut_in_sql_with_whitespace_collapsed(client, db):
    tag = uuid.uuid4().hex[:10]
    product = _product(db)
    text = "  First line.\n\n\n\nSecond   line " + "word " * 300
    _review(db, product, title=f"{tag} long", discussion=text)
    _review(db, product, title=f"{tag} short", discussion="Short and sweet.\n")
    db.commit()
    items = client.get("/api/v1/reviews/feed/page",
                       params={"q": tag, "sort": "newest"}).json()["items"]
    by_title = {i["review"]["title"]: i["review"]["excerpt"] for i in items}
    collapsed = " ".join(text.split())
    assert by_title[f"{tag} long"] == collapsed[:200]
    assert by_title[f"{tag} short"] == "Short and sweet."


@requires_db
def test_the_trust_badge_survives_the_card_shape(client, db):
    from app.models.enums import EarnEligibleStatus, VerificationStatus

    tag = uuid.uuid4().hex[:10]
    product = _product(db)
    _review(db, product, title=f"{tag} badge",
            verification_status=VerificationStatus.verified,
            earn_eligible_status=EarnEligibleStatus.approved)
    _review(db, product, title=f"{tag} plain")
    db.commit()
    params = {"q": tag, "sort": "newest"}
    cards = {i["review"]["title"]: i["review"]["has_trust_badge"]
             for i in client.get("/api/v1/reviews/feed/page", params=params).json()["items"]}
    full = {i["review"]["title"]: i["review"]["has_trust_badge"]
            for i in client.get("/api/v1/reviews/feed", params=params).json()}
    assert cards == full == {f"{tag} badge": True, f"{tag} plain": False}


@requires_db
def test_the_viewer_still_sees_their_own_vote(client, db, seeded):
    from tests.conftest import register_and_token

    tag, _, _, rows = seeded
    _, token, _ = register_and_token(client)
    auth = {"Authorization": f"Bearer {token}"}
    target = str(rows[0].id)
    assert client.post(f"/api/v1/reviews/{target}/vote", json={"vote": "up"},
                       headers=auth).status_code in (200, 201)
    items = client.get("/api/v1/reviews/feed/page", params={"q": tag, "limit": 20},
                       headers=auth).json()["items"]
    mine = {i["review"]["id"]: i["review"]["my_vote"] for i in items}
    assert mine[target] == "up"


@requires_db
def test_card_payload_size_for_24_long_reviews(client, db, capsys):
    """The E1 measurement in the PR: 24 reviews with 5,000-character
    discussions (and the three 2,000-character fields), one page of 24."""
    tag = uuid.uuid4().hex[:10]
    product = _product(db)
    body = ("This review is long on purpose. " * 160)[:5000]
    field = ("Who it suits and why. " * 100)[:2000]
    for i in range(24):
        _review(db, product, title=f"{tag} long review {i:02d}", discussion=body,
                verdict_explanation=field, target_audience=field, anti_target_audience=field)
    db.commit()

    params = {"q": tag, "limit": 24}
    before_list = client.get("/api/v1/reviews/feed", params=params)
    before_count = client.get("/api/v1/reviews/feed/count", params={"q": tag})
    after = client.get("/api/v1/reviews/feed/page", params=params)
    before_bytes = len(before_list.content) + len(before_count.content)
    after_bytes = len(after.content)
    with capsys.disabled():
        print(f"\n[feed/page payload] before: /feed {len(before_list.content):,} B "
              f"+ /feed/count {len(before_count.content):,} B = {before_bytes:,} B; "
              f"after: /feed/page {after_bytes:,} B "
              f"({before_bytes / after_bytes:.1f}x smaller)")
    assert after.json()["total"] == 24 and len(after.json()["items"]) == 24
    assert after_bytes * 5 < before_bytes

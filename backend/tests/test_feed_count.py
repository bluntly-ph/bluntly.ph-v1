"""The feed's total (MQA-036/037): the search's Reviews tab and the Feed number
their pages from GET /reviews/feed/count, which must agree with paging /feed."""

from __future__ import annotations

from tests.conftest import requires_db

pytestmark = requires_db


def _walk(client, query: str) -> list[str]:
    ids: list[str] = []
    offset = 0
    while True:
        url = f"/api/v1/reviews/feed?limit=100&offset={offset}&sort=newest{query}"
        page = client.get(url).json()
        ids += [i["review"]["id"] for i in page]
        if len(page) < 100 or offset >= 1000:
            return ids
        offset += 100


def test_the_count_matches_every_page_of_the_feed(client):
    for query in ("", "&category=electronics", "&period=month", "&trust=high", "&q=fan"):
        total = client.get(f"/api/v1/reviews/feed/count?{query.lstrip('&')}").json()["total"]
        walked = _walk(client, query)
        if total <= 1100:
            assert total == len(walked), query
            assert len(set(walked)) == len(walked), f"a review repeats across pages: {query}"


def test_the_count_rejects_what_the_feed_rejects(client):
    assert client.get("/api/v1/reviews/feed/count?period=decade").status_code == 422
    assert client.get("/api/v1/reviews/feed/count?max_price=-1").status_code == 422

"""Store-owner notification switches (Figma Screen/Seller/Settings 8218:24151, 0083).

NULL prefs mean every switch on, so accounts from before 0083 keep today's
notices; a switch only drops the store notice it names.
"""

from __future__ import annotations

from tests.conftest import register_and_token, requires_db
from tests.test_seller_console_api import _auth, _claimed_store, _rate

pytestmark = requires_db

URL = "/api/v1/users/me/notification-prefs"


def _kinds(client, headers) -> list[str]:
    return [n["kind"] for n in client.get("/api/v1/notifications", headers=headers).json()]


def _ask(client, store: str) -> None:
    _, asker, _ = register_and_token(client)
    resp = client.post("/api/v1/questions", headers=_auth(asker),
                       json={"seller_id": store, "body": "Do you ship to Davao?"})
    assert resp.status_code == 201, resp.text


def test_defaults_are_all_on_and_only_the_caller_reads_or_writes_them(client):
    _, token, _ = register_and_token(client)
    h = _auth(token)
    got = client.get(URL, headers=h)
    assert got.status_code == 200, got.text
    assert got.json() == {"store_reviews": True, "store_reviews_low_only": False,
                          "store_questions": True, "appeal_updates": True, "product_links": True,
                          "email": True, "weekly_summary": True}
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"store_reviews": False}).status_code == 401
    # Unknown keys are refused rather than stored.
    assert client.put(URL, headers=h, json={"case_messages": False}).status_code == 422
    put = client.put(URL, headers=h, json={"store_questions": False})
    assert put.status_code == 200, put.text
    assert put.json()["store_questions"] is False and put.json()["store_reviews"] is True
    assert client.get(URL, headers=h).json()["store_questions"] is False


def test_switches_drop_only_the_store_notices_they_name(client):
    store, owner, _ = _claimed_store(client)
    assert client.put(URL, headers=owner, json={"store_reviews": False,
                                                 "store_questions": False}).status_code == 200
    _rate(client, store, 2.0)
    _ask(client, store)
    kinds = _kinds(client, owner)
    assert "store_review_new" not in kinds and "store_question_new" not in kinds

    # Back on: they arrive again.
    assert client.put(URL, headers=owner, json={}).status_code == 200
    _rate(client, store, 5.0)
    _ask(client, store)
    kinds = _kinds(client, owner)
    assert kinds.count("store_review_new") == 1 and kinds.count("store_question_new") == 1


def test_only_low_reviews_lets_three_stars_or_fewer_through(client):
    store, owner, _ = _claimed_store(client)
    assert client.put(URL, headers=owner, json={"store_reviews_low_only": True}).status_code == 200
    _rate(client, store, 5.0)
    _rate(client, store, 4.0)
    _rate(client, store, 3.0)
    _rate(client, store, 1.0)
    titles = [n["title"] for n in client.get("/api/v1/notifications", headers=owner).json()
              if n["kind"] == "store_review_new"]
    assert sorted(titles) == ["New 1★ review", "New 3★ review"]

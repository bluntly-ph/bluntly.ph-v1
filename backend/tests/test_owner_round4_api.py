"""Owner requests of 2026-09-28: the dashboard's Answers tab and people search.

* Answers — "Clicking Answers on /dashboard brings me to /questions instead of
  answers for my queries": GET /questions/mine lists the member's own
  questions with their newest answers, and the questions they answered.
* People — "a searchable user on search so they can go to other people's
  profile": GET /users/search finds members by @handle or name, public fields
  only.
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models.user import User
from tests.conftest import register_and_token, requires_db

pytestmark = requires_db

API = "/api/v1"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers) -> str:
    return client.post(f"{API}/products", headers=headers, json={
        "name": f"Answers fixture {uuid.uuid4().hex[:8]}", "category": "electronics",
        "source_url": f"https://shopee.ph/x-i.1.{uuid.uuid4().int % 10**12}"}).json()["id"]


def _rename(uid: str, username: str, display_name: str | None = None,
            suspended: bool = False) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(uid))
        user.username = username
        if display_name is not None:
            user.display_name = display_name
        user.is_suspended = suspended
        db.commit()
    finally:
        db.close()


def test_the_answers_tab_lists_my_questions_with_their_answers(client):
    _, asker, _ = register_and_token(client)
    _, answerer, _ = register_and_token(client)
    _, stranger, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    q1 = client.post(f"{API}/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "Does the battery last a full workday?"}).json()["id"]
    q2 = client.post(f"{API}/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "Is the case scratch resistant?"}).json()["id"]
    other = client.post(f"{API}/questions", headers=_auth(stranger), json={
        "product_id": pid, "body": "Someone else's question entirely."}).json()["id"]
    for body in ("Mine lasts about nine hours.", "Closer to seven with the screen on."):
        assert client.post(f"{API}/questions/{q1}/answers", headers=_auth(answerer),
                           json={"body": body, "rating": 4}).status_code == 201
    assert client.post(f"{API}/questions/{other}/answers", headers=_auth(answerer),
                       json={"body": "Not the asker's.", "rating": 4}).status_code == 201

    res = client.get(f"{API}/questions/mine", headers=_auth(asker))
    assert res.status_code == 200, res.text
    rows = res.json()
    ids = [r["id"] for r in rows]
    # Only the asker's own questions, the one with the newest answer first.
    assert ids == [q1, q2]
    first = rows[0]
    assert first["answer_count"] == 2
    # Each answer's words (its stored body also carries its rating line).
    assert [a["parts"]["text"] for a in first["latest_answers"]] == [
        "Closer to seven with the screen on.", "Mine lasts about nine hours."]
    assert first["product_name"].startswith("Answers fixture")
    assert rows[1]["latest_answers"] == [] and rows[1]["answer_count"] == 0

    # The answerer's own list carries their answer on each question.
    answered = client.get(f"{API}/questions/mine", headers=_auth(answerer),
                          params={"role": "answered"}).json()
    assert [r["id"] for r in answered] == [other, q1]
    assert answered[1]["my_answer"]["parts"]["text"] == "Closer to seven with the screen on."

    # A session is required; "mine" is never read as a question id.
    assert client.get(f"{API}/questions/mine").status_code == 401
    assert client.get(f"{API}/questions/mine", headers=_auth(asker),
                      params={"role": "everyone"}).status_code == 422


def test_people_search_finds_members_by_handle_or_name_and_hides_the_suspended(client):
    tag = uuid.uuid4().hex[:6]
    exact_id, _, _ = register_and_token(client)
    prefix_id, _, _ = register_and_token(client)
    named_id, _, _ = register_and_token(client)
    hidden_id, _, _ = register_and_token(client)
    _rename(exact_id, f"vash{tag}", "Vash Stampede")
    _rename(prefix_id, f"vash{tag}_two", "Second Account")
    _rename(named_id, f"other{tag}", f"Maria vash{tag} Reyes")
    _rename(hidden_id, f"vash{tag}_banned", "Suspended One", suspended=True)

    res = client.get(f"{API}/users/search", params={"q": f"@vash{tag}"})
    assert res.status_code == 200, res.text
    handles = [p["username"] for p in res.json()]
    # Exact handle first, then handles that start with it, then names.
    assert handles[:3] == [f"vash{tag}", f"vash{tag}_two", f"other{tag}"]
    assert f"vash{tag}_banned" not in handles

    row = res.json()[0]
    assert set(row) == {"id", "username", "display_name", "avatar_url", "trust_stage",
                        "trust_level_name", "review_count", "is_claimed_seller"}
    assert "email" not in res.text

    # A handle's underscore is literal, not a LIKE wildcard.
    two = client.get(f"{API}/users/search", params={"q": f"vash{tag}_t"}).json()
    assert [p["username"] for p in two] == [f"vash{tag}_two"]

    assert client.get(f"{API}/users/search", params={"q": ""}).status_code == 422


def _store(client, headers: dict) -> dict:
    resp = client.post(f"{API}/sellers", headers=headers,
                       json={"display_name": f"Engage Store {uuid.uuid4().hex[:10]}",
                             "platform": "shopee"})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _seller_review_body() -> dict:
    return {"accuracy": True, "order_completeness": True, "customer_service": 4,
            "packaging_quality": 5, "overall_rating": 4, "would_recommend": True,
            "title": "Fast shipping", "comment": "Arrived in two days, well packed."}


def test_seller_reviews_take_votes_replies_and_reports(client):
    """QA-043: up, down, reply, share and ⋯ (report) on a seller review."""
    from tests.test_seller_dashboard_api import claim_body

    _, buyer, _ = register_and_token(client)
    _, reader, _ = register_and_token(client)
    _, owner, _ = register_and_token(client)
    _, moderator, _ = register_and_token(client, role="administrator")
    store = _store(client, _auth(buyer))
    claim = client.post(f"{API}/sellers/{store['id']}/claims", headers=_auth(owner),
                        json=claim_body("I run it.")).json()
    assert client.post(f"{API}/admin/seller-claims/{claim['id']}/decision",
                       headers=_auth(moderator), json={"decision": "approve"}).status_code == 200
    review = client.post(f"{API}/sellers/{store['id']}/reviews", headers=_auth(buyer),
                         json=_seller_review_body())
    assert review.status_code == 201, review.text
    rid = review.json()["id"]

    # Votes: helpfulness only; not the author, not the store's owner.
    up = client.put(f"{API}/sellers/reviews/{rid}/vote", headers=_auth(reader),
                    json={"direction": "up"})
    assert up.status_code == 200 and up.json() == {
        "helpful_votes": 1, "unhelpful_votes": 0, "my_vote": "up"}
    down = client.put(f"{API}/sellers/reviews/{rid}/vote", headers=_auth(reader),
                      json={"direction": "down"}).json()
    assert (down["helpful_votes"], down["unhelpful_votes"]) == (0, 1)
    assert client.put(f"{API}/sellers/reviews/{rid}/vote", headers=_auth(buyer),
                      json={"direction": "up"}).status_code == 422
    assert client.put(f"{API}/sellers/reviews/{rid}/vote", headers=_auth(owner),
                      json={"direction": "up"}).status_code == 403

    # Replies: any member but the store's owner, who has its one response; the
    # reviewer is told; no links.
    reply = client.post(f"{API}/sellers/reviews/{rid}/replies", headers=_auth(reader),
                        json={"body": "Same experience here."})
    assert reply.status_code == 201, reply.text
    assert client.post(f"{API}/sellers/reviews/{rid}/replies", headers=_auth(owner),
                       json={"body": "Thanks!"}).status_code == 409
    assert client.post(f"{API}/sellers/reviews/{rid}/replies", headers=_auth(reader),
                       json={"body": "see https://example.com"}).status_code == 422
    notes = client.get(f"{API}/notifications", headers=_auth(buyer)).json()
    assert any(n["kind"] == "seller_review_reply" for n in notes)

    listed = client.get(f"{API}/sellers/{store['id']}/reviews", headers=_auth(reader)).json()
    row = next(r for r in listed if r["id"] == rid)
    assert (row["helpful_votes"], row["unhelpful_votes"], row["my_vote"]) == (0, 1, "down")
    assert [r["body"] for r in row["replies"]] == ["Same experience here."]
    assert row["reply_count"] == 1

    # Only its author deletes a reply.
    reply_url = f"{API}/sellers/replies/{reply.json()['id']}"
    assert client.delete(reply_url, headers=_auth(buyer)).status_code == 403
    assert client.delete(reply_url, headers=_auth(reader)).status_code == 204

    # Report → the ordinary queue → a moderator removes it.
    report = client.post(f"{API}/sellers/reviews/{rid}/report", headers=_auth(reader),
                         json={"reason": "spam"})
    assert report.status_code == 201, report.text
    assert client.post(f"{API}/sellers/reviews/{rid}/report", headers=_auth(buyer),
                       json={"reason": "spam"}).status_code == 422   # own review
    report_id = report.json()["id"]
    queue = client.get(f"{API}/admin/reports", headers=_auth(moderator),
                       params={"limit": 100}).json()
    items = queue["items"] if isinstance(queue, dict) else queue
    mine = [i for i in items if i["report"]["id"] == report_id]
    if mine:
        assert mine[0]["target"]["link"] == f"/sellers/{store['id']}#seller-review-{rid}"
    removed = client.post(f"{API}/admin/reports/{report_id}/decision", headers=_auth(moderator),
                          json={"resolution": "content_removed", "notes": "spam"})
    assert removed.status_code == 200, removed.text
    after = client.get(f"{API}/sellers/{store['id']}/reviews").json()
    assert rid not in [r["id"] for r in after]

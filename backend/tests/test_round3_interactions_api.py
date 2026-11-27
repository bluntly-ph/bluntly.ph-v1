"""Round 3 interactions on a real database (QA-064, 065, 067, 068, 069).

* a notification can be marked read, unread, or cleared from the list — a
  soft dismissal that deletes nothing it describes (QA-065);
* upvotes, comments, replies, mentions and followed comments notify the right
  people exactly once, never the actor, and link to the content (QA-067);
* a vote does not move a comment in its thread (QA-068);
* another member's comment can be reported through the moderation pipeline,
  followed and saved; nobody learns who else followed or saved it (QA-069).
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models.notification import Notification
from tests.conftest import register_and_token, register_commenter, requires_db
from tests.test_votes_api import make_published_review

pytestmark = requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _person(client, *, stage: int | None = 1, role: str = "user"):
    uid, token, _ = (register_commenter(client, role) if stage else
                     register_and_token(client, role))
    return uid, _auth(token)


def _notes(client, headers, kind: str | None = None) -> list[dict]:
    rows = client.get("/api/v1/notifications?limit=100", headers=headers).json()
    return [n for n in rows if kind is None or n["kind"] == kind]


def _unread(client, headers) -> int:
    return client.get("/api/v1/notifications/unread-count", headers=headers).json()["count"]


def _username(client, headers) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["username"]


def _review(client):
    _, ah = _person(client)
    _, mh = _person(client, stage=None, role="administrator")
    rid, pid = make_published_review(client, ah, mh, name="Round3")
    return rid, pid, ah, mh


def _comment(client, headers, rid: str, body: str, parent: str | None = None) -> dict:
    res = client.post(f"/api/v1/reviews/{rid}/comments", headers=headers,
                      json={"body": body, "parent_id": parent})
    assert res.status_code == 201, res.text
    return res.json()


# --- QA-064/065: read, unread, dismiss ---------------------------------------

def test_mark_unread_and_dismiss_are_the_owners_and_soft(client):
    rid, _, ah, _ = _review(client)
    _, vh = _person(client)
    base = _unread(client, ah)           # publishing already told the author once
    assert client.post(f"/api/v1/reviews/{rid}/vote", headers=vh,
                       json={"vote": "up"}).status_code == 200
    [note] = _notes(client, ah, "review_upvoted")
    assert _unread(client, ah) == base + 1

    read = client.post(f"/api/v1/notifications/{note['id']}/read", headers=ah)
    assert read.status_code == 200 and read.json()["read_at"] is not None
    assert _unread(client, ah) == base

    again = client.post(f"/api/v1/notifications/{note['id']}/unread", headers=ah)
    assert again.status_code == 200 and again.json()["read_at"] is None
    assert _unread(client, ah) == base + 1

    # Someone else's notification is not found, for every verb.
    for verb, path in (("post", "read"), ("post", "unread")):
        assert getattr(client, verb)(f"/api/v1/notifications/{note['id']}/{path}",
                                     headers=vh).status_code == 404
    assert client.delete(f"/api/v1/notifications/{note['id']}", headers=vh).status_code == 404

    gone = client.delete(f"/api/v1/notifications/{note['id']}", headers=ah)
    assert gone.status_code == 204
    assert _notes(client, ah, "review_upvoted") == []
    assert _unread(client, ah) == base
    assert client.delete(f"/api/v1/notifications/{note['id']}", headers=ah).status_code == 404

    # Soft: the row is still there, and so is the vote it announced.
    db = SessionLocal()
    try:
        row = db.get(Notification, uuid.UUID(note["id"]))
        assert row is not None and row.dismissed_at is not None
    finally:
        db.close()
    assert client.get(f"/api/v1/reviews/{rid}").json()["helpful_votes"] == 1


# --- QA-067: upvotes ---------------------------------------------------------

def test_an_upvote_notifies_once_and_repeats_group(client):
    rid, _, ah, _ = _review(client)
    _, v1 = _person(client)
    _, v2 = _person(client)
    _, v3 = _person(client)

    def vote(h, direction="up"):
        assert client.post(f"/api/v1/reviews/{rid}/vote", headers=h,
                           json={"vote": direction}).status_code == 200

    vote(v1)
    [first] = _notes(client, ah, "review_upvoted")
    assert first["title"] == "Someone found your review helpful"
    assert first["link"] == f"/reviews/{rid}" and first["group_count"] == 1

    vote(v1)                                                     # same vote again
    assert client.delete(f"/api/v1/reviews/{rid}/vote", headers=v1).status_code == 200
    vote(v1)                                                     # taken back, cast again
    vote(v1, "down")
    vote(v1)                                                     # down, then up again
    assert [n["group_count"] for n in _notes(client, ah, "review_upvoted")] == [1]

    vote(v2)                                                     # a second person
    [grouped] = _notes(client, ah, "review_upvoted")
    assert grouped["id"] == first["id"] and grouped["group_count"] == 2
    assert grouped["title"] == "2 people found your review helpful"

    client.post(f"/api/v1/notifications/{first['id']}/read", headers=ah)
    vote(v3)                                                     # after it was read
    notes = _notes(client, ah, "review_upvoted")
    assert len(notes) == 2 and notes[0]["group_count"] == 1 and notes[0]["read_at"] is None


def test_a_downvote_notifies_nobody(client):
    rid, _, ah, _ = _review(client)
    _, vh = _person(client)
    before = _notes(client, ah)
    assert client.post(f"/api/v1/reviews/{rid}/vote", headers=vh,
                       json={"vote": "down"}).status_code == 200
    assert _notes(client, ah) == before


# --- QA-067: comments, replies, mentions, follows ----------------------------

def test_comment_reply_mention_and_follow_each_reach_the_right_people_once(client):
    rid, _, author, _ = _review(client)
    _, alice = _person(client)
    _, bob = _person(client)
    _, carol = _person(client)
    carol_name = _username(client, carol)

    top = _comment(client, alice, rid, "Battery lasts two days for me.")
    [on_review] = _notes(client, author, "review_comment")
    assert on_review["link"] == f"/reviews/{rid}#comment-{top['id']}"
    assert on_review["title"].endswith("commented on your review")

    # Carol follows Alice's comment; Bob replies and mentions Carol.
    assert client.put(f"/api/v1/comments/{top['id']}/follow", headers=carol).json()["followed"]
    reply = _comment(client, bob, rid, f"Same here, @{carol_name} asked about this.",
                     parent=top["id"])
    link = f"/reviews/{rid}#comment-{reply['id']}"

    [to_parent] = _notes(client, alice, "comment_reply")
    assert to_parent["link"] == link
    # Carol is both mentioned and a follower: told once, the specific way.
    carol_notes = [n for n in _notes(client, carol) if n["link"] == link]
    assert [n["kind"] for n in carol_notes] == ["comment_mention"]
    # The review's author hears about the reply too, once.
    assert len([n for n in _notes(client, author, "review_comment") if n["link"] == link]) == 1
    # Nobody is told about their own comment.
    assert [n for n in _notes(client, bob) if n["link"] == link] == []


def test_mentioning_yourself_or_nobody_notifies_nobody(client):
    rid, _, author, _ = _review(client)
    _, alice = _person(client)
    me = _username(client, alice)
    _comment(client, alice, rid, f"note to self @{me}; also @nobody_{uuid.uuid4().hex[:8]}")
    assert _notes(client, alice) == []
    assert len(_notes(client, author, "review_comment")) == 1


def test_a_comment_upvote_notifies_its_author_once(client):
    rid, _, _, _ = _review(client)
    _, alice = _person(client)
    _, bob = _person(client)
    top = _comment(client, alice, rid, "Runs cool under load.")
    for _ in range(2):
        client.post(f"/api/v1/comments/{top['id']}/vote", headers=bob, json={"vote": "up"})
    client.delete(f"/api/v1/comments/{top['id']}/vote", headers=bob)
    client.post(f"/api/v1/comments/{top['id']}/vote", headers=bob, json={"vote": "up"})
    notes = _notes(client, alice, "comment_upvoted")
    assert len(notes) == 1 and notes[0]["link"] == f"/reviews/{rid}#comment-{top['id']}"


# --- QA-068: a vote does not move a comment ----------------------------------

def test_voting_does_not_reorder_the_thread(client):
    rid, _, _, _ = _review(client)
    _, alice = _person(client)
    _, bob = _person(client)
    first = _comment(client, alice, rid, "First take.")
    second = _comment(client, alice, rid, "Second take.")
    third = _comment(client, alice, rid, "Third take.")
    order = [c["id"] for c in client.get(f"/api/v1/reviews/{rid}/comments").json()]
    assert order == [first["id"], second["id"], third["id"]]
    client.post(f"/api/v1/comments/{third['id']}/vote", headers=bob, json={"vote": "up"})
    client.post(f"/api/v1/comments/{first['id']}/vote", headers=bob, json={"vote": "down"})
    assert [c["id"] for c in client.get(f"/api/v1/reviews/{rid}/comments").json()] == order


# --- QA-069: report, follow, save --------------------------------------------

def test_follow_and_save_are_private_and_idempotent(client):
    rid, _, _, _ = _review(client)
    _, alice = _person(client)
    _, bob = _person(client)
    _, carol = _person(client)
    top = _comment(client, alice, rid, "Worth it at the sale price.")
    cid = top["id"]

    for _ in range(2):
        assert client.put(f"/api/v1/comments/{cid}/save", headers=bob).json()["saved"] is True
        assert client.put(f"/api/v1/comments/{cid}/follow", headers=bob).json()["followed"]

    mine = client.get(f"/api/v1/reviews/{rid}/comments", headers=bob).json()[0]
    assert mine["saved_by_me"] and mine["followed_by_me"]
    theirs = client.get(f"/api/v1/reviews/{rid}/comments", headers=carol).json()[0]
    assert not theirs["saved_by_me"] and not theirs["followed_by_me"]
    anonymous = client.get(f"/api/v1/reviews/{rid}/comments").json()[0]
    assert not anonymous["saved_by_me"] and not anonymous["followed_by_me"]

    saved = client.get("/api/v1/users/me/saved-comments", headers=bob).json()
    assert [s["id"] for s in saved] == [cid] and saved[0]["review"]["id"] == rid
    assert client.get("/api/v1/users/me/saved-comments", headers=carol).json() == []
    assert client.get("/api/v1/users/me/saved-comments").status_code == 401

    # One's own comment: nothing to follow or save.
    assert client.put(f"/api/v1/comments/{cid}/save", headers=alice).status_code == 409
    assert client.put(f"/api/v1/comments/{cid}/follow", headers=alice).status_code == 409

    for _ in range(2):
        assert client.delete(f"/api/v1/comments/{cid}/save", headers=bob).json()["saved"] is False
    assert client.get("/api/v1/users/me/saved-comments", headers=bob).json() == []


def test_a_removed_comment_leaves_the_saved_list(client):
    rid, _, _, _ = _review(client)
    _, alice = _person(client)
    _, bob = _person(client)
    top = _comment(client, alice, rid, "Changed my mind later.")
    client.put(f"/api/v1/comments/{top['id']}/save", headers=bob)
    client.delete(f"/api/v1/comments/{top['id']}", headers=alice)
    assert client.get("/api/v1/users/me/saved-comments", headers=bob).json() == []


def test_a_comment_report_goes_through_the_moderation_pipeline(client):
    rid, _, _, mh = _review(client)
    _, alice = _person(client)
    _, bob = _person(client)
    top = _comment(client, alice, rid, "Buy it from my other shop instead.")
    cid = top["id"]

    assert client.post(f"/api/v1/comments/{cid}/report", headers=alice,
                       json={"reason": "spam"}).status_code == 422        # own comment
    filed = client.post(f"/api/v1/comments/{cid}/report", headers=bob, json={"reason": "spam"})
    assert filed.status_code == 201, filed.text
    repeat = client.post(f"/api/v1/comments/{cid}/report", headers=bob, json={"reason": "spam"})
    assert repeat.json()["id"] == filed.json()["id"]                     # a repeat, not a new one

    queue = client.get("/api/v1/admin/reports?target_type=comment&limit=100", headers=mh).json()
    [item] = [i for i in queue["items"] if i["report"]["target_ref"] == cid]
    assert item["target"]["link"] == f"/reviews/{rid}#comment-{cid}"
    assert item["target"]["is_published"] is True
    assert item["target"]["title"].startswith("Comment: ")

    decided = client.post(f"/api/v1/admin/reports/{item['report']['id']}/decision", headers=mh,
                          json={"resolution": "content_removed", "notes": "self-promotion"})
    assert decided.status_code == 200, decided.text
    thread = client.get(f"/api/v1/reviews/{rid}/comments").json()
    assert all(c["id"] != cid for c in thread)
    # The comment is soft-removed like an author's own delete, not deleted.
    assert client.post(f"/api/v1/comments/{cid}/report", headers=bob,
                       json={"reason": "spam"}).status_code == 404


def test_report_links_serve_a_real_page_for_reviews_too(client):
    rid, _, _, mh = _review(client)
    _, bob = _person(client)
    client.post(f"/api/v1/reviews/{rid}/report", headers=bob, json={"reason": "spam"})
    items = client.get("/api/v1/admin/reports?target_type=review&limit=100",
                       headers=mh).json()["items"]
    [item] = [i for i in items if i["report"]["target_ref"] == rid]
    assert item["target"]["link"] == f"/reviews/{rid}"

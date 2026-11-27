"""MQA-003: the Reports view shows the reported review's integrity signals.

The tester found the Review Queue's checks - reverse image search, vote
velocity, collusion, copied text, edits after a link - missing from the
Reports view, so judging a report meant opening the review elsewhere. Each
reported review now carries `review_signals`, built by the queue's own card
builder (so the two can never disagree), plus whether the System found its
photo on an earlier review. Reports on anything but a review carry none.
"""

from __future__ import annotations

from tests.conftest import (
    all_report_queue_items,
    find_pending_queue_item,
    register_and_token,
    requires_db,
    unique_text,
)
from tests.test_fraud_signals import _fresh_product
from tests.test_votes_api import make_published_review


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _item(client, admin, target_id, **match):
    return next(i for i in all_report_queue_items(client, admin)
                if i["report"]["target_ref"] == target_id
                and all(i.get(k) == v for k, v in match.items()))


@requires_db
def test_a_reported_review_carries_the_queues_checks(client):
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, reporter, _ = register_and_token(client)
    rid, _ = make_published_review(client, _auth(author), _auth(admin), name="SignalWidget")
    assert client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter),
                       json={"reason": "spam"}).status_code == 201

    got = _item(client, _auth(admin), rid)["review_signals"]
    assert got is not None
    assert {"velocity", "collusion", "duplicate_content"} <= set(got["signals"])
    assert got["signals"]["velocity"] is False and got["signals"]["collusion"] is False
    # No provider is procured: "not configured", never a pass.
    assert got["integrity"] == {"plagiarism_status": "not_configured",
                                "reverse_image_status": "not_configured"}
    assert got["voting"]["velocity_threshold"] > 0
    assert got["has_photo"] is True and got["reused_photo"] is False
    assert got["edited_since_monetized"] is False


@requires_db
def test_copied_text_shows_in_the_report_as_it_does_on_the_queue_card(client):
    _, author, _ = register_and_token(client)
    _, copier, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    ah, ch, mh = _auth(author), _auth(copier), _auth(admin)
    body = unique_text("Kettle")
    pid = _fresh_product(client, ah)
    client.post("/api/v1/reviews", headers=ah, json={
        "product_id": pid, "title": "Original", "discussion": body,
        "verdict": "yes_absolutely", "star_rating": 4})
    copy = client.post("/api/v1/reviews", headers=ch, json={
        "product_id": pid, "title": f"Copy {unique_text('t')[:12]}",
        "discussion": body + " Really.", "verdict": "yes_absolutely",
        "star_rating": 4}).json()["id"]
    assert client.post("/api/v1/admin/integrity/sweep", headers=mh).status_code == 200

    report = _item(client, mh, copy, origin="system_detected")
    assert report["review_signals"]["signals"]["duplicate_content"] is True
    card = find_pending_queue_item(client, mh, copy)
    assert card is not None
    for key in ("velocity", "collusion", "duplicate_content"):
        assert report["review_signals"]["signals"][key] == card["signals"][key]


@requires_db
def test_a_reused_photo_found_by_the_system_is_said(client):
    from app.db.session import SessionLocal
    from app.models.enums import ModerationReason, ModerationTargetType
    from app.services.report_service import file_system_report

    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, reporter, _ = register_and_token(client)
    rid, _ = make_published_review(client, _auth(author), _auth(admin), name="ReusedPhoto")
    with SessionLocal() as db:
        file_system_report(db, target_type=ModerationTargetType.review, target_ref=rid,
                           signal="duplicate_image", reason=ModerationReason.fake_proof,
                           severity=1.0)
        db.commit()
    client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter),
                json={"reason": "fake_proof"})
    member = _item(client, _auth(admin), rid, origin="user_reported")
    assert member["review_signals"]["reused_photo"] is True


@requires_db
def test_a_report_on_a_comment_carries_no_review_signals(client):
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, reporter, _ = register_and_token(client)
    rid, _ = make_published_review(client, _auth(author), _auth(admin), name="CommentSig")
    # Commenting unlocks with a first review, so the author comments.
    comment = client.post(f"/api/v1/reviews/{rid}/comments", headers=_auth(author),
                          json={"body": "Update: mine broke in a week."})
    assert comment.status_code == 201, comment.text
    cid = comment.json()["id"]
    assert client.post(f"/api/v1/comments/{cid}/report", headers=_auth(reporter),
                       json={"reason": "spam"}).status_code == 201
    assert _item(client, _auth(admin), cid)["review_signals"] is None


@requires_db
def test_newest_first_puts_a_report_just_filed_at_the_top(client):
    """MQA-001: the open queue ranks by escalation; "newest" is the order a
    moderator picks to find what was just filed."""
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, reporter, _ = register_and_token(client)
    rid, _ = make_published_review(client, _auth(author), _auth(admin), name="NewestFirst")
    assert client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter),
                       json={"reason": "spam"}).status_code == 201
    page = client.get("/api/v1/admin/reports?sort=newest&limit=5", headers=_auth(admin)).json()
    assert page["items"][0]["report"]["target_ref"] == rid
    stamps = [i["report"]["created_at"] for i in page["items"]]
    assert stamps == sorted(stamps, reverse=True)

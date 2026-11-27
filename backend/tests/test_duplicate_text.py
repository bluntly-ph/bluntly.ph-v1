"""Suspicious duplicate text (QA, 2026-09-29): "fuzzy word matching for
suspicious/duplicated text ... to support moderation and help identify
suspicious or duplicated submissions".

Before: a raw `pg_trgm` similarity over reviews only, run by the daily sweep.
There was no length floor (two people's identical "Good product." on one
product scored 1.0), no normalisation beyond pg_trgm's own, no check at
submission, and nothing for answers or comments. Now there is one detector
(`duplicate_text` + `text_similarity`) for every path. A match files a
SYSTEM_DETECTED report and nothing else: the submission stays published.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.session import SessionLocal
from app.services.text_similarity import compare, is_meaningful, normalize
from tests.conftest import (
    all_report_queue_items,
    register_and_token,
    register_commenter,
    requires_db,
    unique_text,
)

ORIGINAL = ("I used this vacuum daily for six weeks. Battery life is superb, suction strong "
            "on hardwood, weaker on thick carpet. The dust bin is small but easy to empty. "
            "Highly recommended for small flats.")


# --- the pure comparison ----------------------------------------------------------------

def test_an_exact_long_copy_is_flagged():
    assert compare(ORIGINAL, ORIGINAL).flagged


def test_a_lightly_edited_copy_is_flagged():
    edited = (ORIGINAL.replace("six weeks", "two months").replace("superb", "excellent")
              .replace("small flats", "condos"))
    found = compare(ORIGINAL, edited)
    assert found.flagged and found.near_identical < 0.85        # caught as a copied passage


def test_a_copy_with_a_paragraph_added_is_flagged():
    padded = ORIGINAL + (" I bought it during the 9.9 sale and the courier was quick, "
                         "it arrived in two days to Cebu.")
    found = compare(ORIGINAL, padded)
    assert found.flagged and found.passage_share == 1.0


def test_an_unrelated_review_on_the_same_topic_is_not_flagged():
    other = ("Bought this for my dorm. It is loud and the charger feels cheap, but it picks "
             "up hair well. I empty it every day. Would buy again for the price.")
    assert not compare(ORIGINAL, other).flagged


@pytest.mark.parametrize("phrase", ["Good product.", "Good product. Fast delivery. Sulit!",
                                    "Highly recommended to everyone!"])
def test_short_generic_text_is_never_flagged_even_when_identical(phrase):
    assert not is_meaningful(normalize(phrase))
    assert not compare(phrase, phrase).flagged


def test_unicode_and_punctuation_cannot_hide_a_copy():
    disguised = ("ＩＵＳＥＤ this vácuum DAILY for six weeks… Battery life is “superb”, suction "
                 "strong on hard\u200bwood — weaker on thick carpet! The dust bin is small but "
                 "easy to empty. Highly recommended for small flats!!")
    assert normalize("Ｃａｆé “quoted”… zero\u200bwidth") == "cafe quoted zerowidth"
    assert compare(ORIGINAL, disguised).flagged


def test_the_comparison_is_symmetric_and_deterministic():
    edited = ORIGINAL.replace("superb", "excellent")
    assert compare(ORIGINAL, edited) == compare(edited, ORIGINAL) == compare(ORIGINAL, edited)


# --- on a real database: at submission, as moderation evidence -----------------------------

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _product(client, headers, name: str) -> str:
    res = client.post("/api/v1/products", headers=headers,
                      json={"name": name, "category": "electronics"})
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _post_review(client, headers, product_id: str, discussion: str, title: str = "Vacuum") -> str:
    res = client.post("/api/v1/reviews", headers=headers, json={
        "product_id": product_id, "title": title, "discussion": discussion,
        "verdict": "yes_absolutely", "star_rating": 4})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _system_duplicates(client, admin_headers, target_ref: str) -> list[dict]:
    return [i for i in all_report_queue_items(client, admin_headers)
            if i["report"]["target_ref"] == target_ref and i["origin"] == "system_detected"
            and (i.get("explanation") or {}).get("signal") == "duplicate_content"]


@requires_db
def test_a_copied_review_is_flagged_at_submission_and_stays_published(client):
    tag = uuid.uuid4().hex[:8]
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    pid = _product(client, _auth(a), f"Vacuum {tag}")
    text = unique_text("Vacuum")
    original = _post_review(client, _auth(a), pid, text)
    copy = _post_review(client, _auth(b), pid, f"{text} Really.", title="Copy")

    # No sweep ran: the submission itself filed the evidence.
    [item] = _system_duplicates(client, _auth(admin), copy)
    why = item["explanation"]
    assert why["summary"].startswith("Possible copied review: its text closely matches "
                                     "another review already in the database")
    lines = {e["label"]: e for e in why["evidence"]}
    assert lines["Matching review"]["link"] == f"/reviews/{original}"
    assert lines["Check"]["value"] == "text-dup-v1"
    assert "Near-identical text" in lines["How it matched"]["value"]
    # Evidence only: the copy is public, and the honest original is not flagged.
    assert client.get(f"/api/v1/reviews/{copy}").status_code == 200
    assert _system_duplicates(client, _auth(admin), original) == []
    # The stored evidence holds ids and scores, never the texts.
    from sqlalchemy import select

    from app.models.moderation import ModerationLog
    db = SessionLocal()
    try:
        log = db.scalar(select(ModerationLog).where(
            ModerationLog.target_ref == uuid.UUID(copy),
            ModerationLog.context["signal"].astext == "duplicate_content"))
        evidence = log.context["evidence"]
        assert evidence["duplicate_of"] == original and evidence["matched_kind"] == "review"
        assert 0.85 <= evidence["similarity"] <= 1 and evidence["detected_at"]
        assert text.split()[-1] not in str(evidence) and "vacuum" not in str(evidence).lower()
    finally:
        db.close()


@requires_db
def test_a_copy_on_another_product_by_another_member_is_found_by_the_daily_sweep(client):
    """Across products and authors the search needs the trigram index, about
    120 ms a review at 50,000 reviews: the daily sweep runs it for new reviews,
    a submission does not."""
    tag = uuid.uuid4().hex[:8]
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    text = unique_text("Travel adapter")
    original = _post_review(client, _auth(a), _product(client, _auth(a), f"Adapter {tag}"), text)
    copy = _post_review(client, _auth(b), _product(client, _auth(b), f"Plug {tag}"), text)
    assert _system_duplicates(client, _auth(admin), copy) == []      # not at submission
    assert client.post("/api/v1/admin/integrity/sweep", headers=_auth(admin)).status_code == 200
    [item] = _system_duplicates(client, _auth(admin), copy)
    assert {e["label"]: e for e in item["explanation"]["evidence"]}[
        "Matching review"]["link"] == f"/reviews/{original}"


@requires_db
def test_identical_short_generic_reviews_are_not_flagged(client):
    tag = uuid.uuid4().hex[:8]
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    pid = _product(client, _auth(a), f"Charger {tag}")
    _post_review(client, _auth(a), pid, "Good product. Fast delivery. Sulit!")
    second = _post_review(client, _auth(b), pid, "Good product. Fast delivery. Sulit!")
    assert _system_duplicates(client, _auth(admin), second) == []


@requires_db
def test_an_unrelated_review_is_not_flagged(client):
    tag = uuid.uuid4().hex[:8]
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    pid = _product(client, _auth(a), f"Vacuum {tag}")
    _post_review(client, _auth(a), pid, unique_text("Vacuum"))
    other = _post_review(client, _auth(b), pid, unique_text("Dorm vacuum"))
    assert _system_duplicates(client, _auth(admin), other) == []


@requires_db
def test_a_failed_check_never_blocks_publication(client, monkeypatch):
    from app.services import duplicate_text

    def broken(*_args, **_kwargs):
        raise RuntimeError("the check fell over")

    monkeypatch.setattr(duplicate_text, "review_duplicates", broken)
    tag = uuid.uuid4().hex[:8]
    _, a, _ = register_and_token(client)
    rid = _post_review(client, _auth(a), _product(client, _auth(a), f"Kettle {tag}"),
                       unique_text("Kettle"))
    assert client.get(f"/api/v1/reviews/{rid}").status_code == 200


@requires_db
def test_a_copied_answer_is_flagged_as_an_answer(client):
    tag = uuid.uuid4().hex[:8]
    _, asker, _ = register_and_token(client)
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    pid = _product(client, _auth(asker), f"Router {tag}")
    q = client.post("/api/v1/questions", headers=_auth(asker),
                    json={"product_id": pid, "body": f"Does it reach three floors? {tag}"})
    assert q.status_code == 201, q.text
    body = (f"Yes {tag}: in our three-storey house the mesh node on the second floor keeps "
            "the signal above 200 Mbps in the top bedroom, and video calls never drop.")
    first = client.post(f"/api/v1/questions/{q.json()['id']}/answers", headers=_auth(a),
                        json={"body": body, "rating": 4})
    assert first.status_code == 201, first.text
    second = client.post(f"/api/v1/questions/{q.json()['id']}/answers", headers=_auth(b),
                         json={"body": body + " Hope this helps.", "rating": 4})
    assert second.status_code == 201, second.text
    [item] = _system_duplicates(client, _auth(admin), second.json()["id"])
    assert item["explanation"]["summary"].startswith(
        "Possible copied answer: its text closely matches another answer")
    link = {e["label"]: e for e in item["explanation"]["evidence"]}["Matching answer"]["link"]
    assert link == f"/questions/{q.json()['id']}"


@requires_db
def test_a_long_comment_pasted_across_reviews_is_flagged(client):
    tag = uuid.uuid4().hex[:8]
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, spammer, _ = register_commenter(client)
    r1 = _post_review(client, _auth(author), _product(client, _auth(author), f"Fan {tag}"),
                      unique_text("Fan"))
    r2 = _post_review(client, _auth(author), _product(client, _auth(author), f"Heater {tag}"),
                      unique_text("Heater"), title="Other")
    body = (f"Everyone reading this {tag}: the seller on the other platform ships faster and "
            "the warranty is honoured without a receipt, so check before you buy here.")
    assert client.post(f"/api/v1/reviews/{r1}/comments", headers=_auth(spammer),
                       json={"body": body}).status_code == 201
    second = client.post(f"/api/v1/reviews/{r2}/comments", headers=_auth(spammer),
                         json={"body": body})
    assert second.status_code == 201, second.text
    [item] = _system_duplicates(client, _auth(admin), second.json()["id"])
    assert item["explanation"]["summary"].startswith("Possible copied comment")

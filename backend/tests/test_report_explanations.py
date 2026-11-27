"""Why was this reported? (dev/QA sync 2026-09-29, ENG-0929-B.)

"Open the reported item" left an administrator to work out on their own why
it had been flagged. Every report now carries an explanation written from
stored fields only: a member's category and note, or a system signal and the
evidence the integrity sweep stored when it fired. Nothing is generated, and
nothing is claimed that no check computed (reverse-image search is not built).
"""

from __future__ import annotations

from app.services.report_explainer import explain
from tests.conftest import (
    all_report_queue_items,
    register_and_token,
    requires_db,
    unique_text,
)
from tests.test_fraud_signals import _fresh_product
from tests.test_votes_api import make_published_review


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- the pure explainer --------------------------------------------------------------

def test_a_members_report_says_its_category_note_and_why_it_escalated():
    found = explain(origin="user_reported", reason="personal_information",
                    notes="Phone number in the second paragraph.", target_type="review",
                    context=None, report_count=2, weighted=0.0, escalated=True, urgent=True)
    assert found.summary.startswith("A member reported this review as “Personal information”.")
    assert "Phone number in the second paragraph." in found.summary
    assert "2 reports" in found.summary and "urgent reason" in found.summary
    assert found.signal is None and found.evidence_stored is True


def test_a_system_report_without_stored_evidence_says_so_instead_of_inventing_it():
    found = explain(origin="system_detected", reason="plagiarized", notes=None,
                    target_type="review", context={"signal": "duplicate_content"})
    assert found.evidence_stored is False and found.evidence == []
    assert "filed before its evidence was stored" in found.summary
    assert "%" not in found.summary  # no similarity it never recorded


def test_velocity_mismatch_and_concentration_are_explained_from_their_facts():
    velocity = explain(origin="system_detected", reason="other", notes=None,
                       target_type="review", context={"signal": "vote_velocity", "evidence": {
                           "max_upvotes_in_window": 14, "window_seconds": 3600, "threshold": 10}})
    assert "14 up-votes arrived within one hour" in velocity.summary
    mismatch = explain(origin="system_detected", reason="other", notes=None,
                       target_type="review", context={"signal": "verdict_star_mismatch",
                                                      "evidence": {"verdict": "hard_pass",
                                                                   "star_rating": 5.0}})
    assert "“Hard pass” with 5★" in mismatch.summary
    held = explain(origin="system_detected", reason="other", notes=None, target_type="user",
                   context={"signal": "vote_concentration", "cohort_share": 0.8,
                            "cohort_size": 5, "candidate_stage": 3, "held_at_stage": 2,
                            "distinct_voters": 7, "eligible_voters": 6})
    assert "80% of this member’s counted votes" in held.summary
    assert "held at Stage 2" in held.summary


def test_no_explanation_claims_reverse_image_search_or_an_ip_address():
    for context in ({"signal": "collusion", "evidence": {"upvoters": 5,
                                                          "reciprocal_upvoters": 4}},
                    {"signal": "duplicate_content", "evidence": {"duplicate_of": None}}):
        text = explain(origin="system_detected", reason="other", notes=None,
                       target_type="review", context=context).summary.lower()
        assert "reverse" not in text and "same ip" not in text


# --- on a real database ---------------------------------------------------------------

@requires_db
def test_the_queue_explains_a_members_report_beside_the_reported_content(client):
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    _, reporter, _ = register_and_token(client)
    rid, _ = make_published_review(client, _auth(author), _auth(admin), name="ExplainWidget")
    assert client.post(f"/api/v1/reviews/{rid}/report", headers=_auth(reporter),
                       json={"reason": "fake_proof",
                             "notes": "The photo is the shop's listing image."}).status_code == 201
    item = next(i for i in all_report_queue_items(client, _auth(admin))
                if i["report"]["target_ref"] == rid)
    why = item["explanation"]
    assert why["summary"].startswith("A member reported this review as “Fake photo or receipt”.")
    assert "The photo is the shop's listing image." in why["summary"]
    assert {"label": "Category", "value": "Fake photo or receipt", "link": None} in why["evidence"]
    # The reported content itself, so nobody has to open another tab to read it.
    target = item["target"]
    assert target["state"] == "published" and target["excerpt"]
    assert target["product_name"] and target["author_username"] is not None
    assert target["link"] == f"/reviews/{rid}"


@requires_db
def test_the_sweep_stores_the_copied_review_it_matched_and_the_queue_links_it(client):
    _, author, _ = register_and_token(client)
    _, copier, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    ah, ch, mh = _auth(author), _auth(copier), _auth(admin)
    # Unique (conftest.unique_text): the check searches the whole shared database.
    body = unique_text("Vacuum")
    pid = _fresh_product(client, ah)
    original = client.post("/api/v1/reviews", headers=ah, json={
        "product_id": pid, "title": "Original", "discussion": body,
        "verdict": "yes_absolutely", "star_rating": 4}).json()["id"]
    copy = client.post("/api/v1/reviews", headers=ch, json={
        "product_id": pid, "title": "Copy", "discussion": body + " Really.",
        "verdict": "yes_absolutely", "star_rating": 4}).json()["id"]
    assert client.post("/api/v1/admin/integrity/sweep", headers=mh).status_code == 200

    reports = [i for i in all_report_queue_items(client, mh)
               if i["report"]["target_ref"] == copy and i["origin"] == "system_detected"]
    dup = next(i for i in reports if i["explanation"]["signal"] == "duplicate_content")
    why = dup["explanation"]
    assert why["evidence_stored"] is True
    assert why["summary"].startswith("Possible copied review: its text closely matches another "
                                     "review already in the database")
    match = next(e for e in why["evidence"] if e["label"] == "Matching review")
    assert match["link"] == f"/reviews/{original}" and match["value"] == "Original"
    similarity = next(e for e in why["evidence"] if e["label"] == "Text similarity")
    assert 0.5 < float(similarity["value"]) <= 1.0
    # The original is not a copy of the later review: only the copy is flagged.
    assert not [i for i in all_report_queue_items(client, mh)
                if i["report"]["target_ref"] == original and i["origin"] == "system_detected"
                and (i["explanation"] or {}).get("signal") == "duplicate_content"]


@requires_db
def test_a_collusion_report_gives_the_reciprocal_voting_numbers(client):
    _, author, _ = register_and_token(client)
    _, admin, _ = register_and_token(client, role="administrator")
    ah, mh = _auth(author), _auth(admin)
    rid, _ = make_published_review(client, ah, mh, name="ExplainRing")
    ring = []
    for i in range(5):
        uid, tok, _ = register_and_token(client)
        assert client.post(f"/api/v1/reviews/{rid}/vote", headers=_auth(tok),
                           json={"vote": "up"}).status_code == 200
        their, _ = make_published_review(client, _auth(tok), mh, name=f"ExplainRing{i}-{uid[:6]}")
        ring.append(their)
    for their in ring[:4]:
        assert client.post(f"/api/v1/reviews/{their}/vote", headers=ah,
                           json={"vote": "up"}).status_code == 200
    assert client.post("/api/v1/admin/integrity/sweep", headers=mh).status_code == 200

    item = next(i for i in all_report_queue_items(client, mh)
                if i["report"]["target_ref"] == rid
                and (i["explanation"] or {}).get("signal") == "collusion")
    why = item["explanation"]
    assert "4 of this review’s 5 up-voters" in why["summary"]
    assert "no IP address or location is collected" in why["summary"]
    assert {"label": "Up-voted back by the author", "value": "4 (80%)", "link": None} \
        in why["evidence"]

    # The same numbers sit in the review queue's Voting Distribution panel.
    queue = client.get("/api/v1/admin/review-queue?q=ExplainRing&limit=100", headers=mh).json()
    card = next((c for c in queue["items"] if c["review"]["id"] == rid), None)
    if card is not None:  # only while the review still waits on a decision
        assert card["voting"]["upvoters"] == 5 and card["voting"]["reciprocal_upvoters"] == 4

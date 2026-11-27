"""The structured answer (meeting 2026-10-02: "very similar to the review flow"):
the asker's requested specifics, the good and the bad, a recommendation, a
rating and the answerer's own photos — stored as labelled lines after the
answer's words and returned parsed. No migration."""

from __future__ import annotations

from decimal import Decimal

from app.services import answer_parts as ap
from tests.conftest import owned_photo_url, register_and_token, requires_db
from tests.test_business_rules_api import _auth, _product


def test_compose_and_parse_round_trip():
    parts = ap.AnswerParts(text="I use it on my commute.\nStill fine.",
                           experience="Three months, daily.", good="Battery lasts all day.",
                           bad="The clip is\nflimsy.", recommend=True,
                           right_for_you="Yes, if you walk a lot.", rating=Decimal("4.5"),
                           photo_urls=["https://x.supabase.co/review-photos/u/1.jpg"])
    body = ap.compose(parts)
    assert body.endswith("Rating: 4.5/5\nPhotos: https://x.supabase.co/review-photos/u/1.jpg")
    back = ap.parse(body)
    assert back.text == "I use it on my commute.\nStill fine."
    assert (back.experience, back.good, back.bad) == (
        "Three months, daily.", "Battery lasts all day.", "The clip is flimsy.")
    assert (back.recommend, back.right_for_you, back.rating) == (
        True, "Yes, if you walk a lot.", Decimal("4.5"))
    assert back.photo_urls == ["https://x.supabase.co/review-photos/u/1.jpg"]


def test_a_plain_answer_is_all_text():
    plain = ap.parse("About nine hours on medium.\nGood enough: yes")
    assert plain.text == "About nine hours on medium.\nGood enough: yes"
    assert not plain.structured
    assert ap.compose(ap.AnswerParts(text="  Just words. ")) == "Just words."


def test_question_requirements_come_from_its_last_line():
    assert ap.requirements_of("Is it loud?\n\nLooking for: Experience, Rating") == [
        "Experience", "Rating"]
    assert ap.requirements_of("Is it loud?\n\nLooking for: Experience, Vibes") == []
    assert ap.requirements_of("Looking for: Experience") == []


@requires_db
def test_structured_answer_through_the_api(client):
    _, asker, _ = register_and_token(client)
    _, answerer, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    q = client.post("/api/v1/questions", headers=_auth(asker), json={
        "product_id": pid,
        "body": "Does the battery last a full shift?\n\nLooking for: Experience, Rating"}).json()
    assert q["requirements"] == ["Experience", "Rating"]

    photo = owned_photo_url(_auth(answerer))
    r = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_auth(answerer), json={
        "body": "About nine hours on medium.", "experience": "Two months of shifts.",
        "good": "Charges fast.", "bad": "Heavy.", "recommend": True, "rating": "4.5",
        "photo_urls": [photo]})
    assert r.status_code == 201, r.text
    parts = r.json()["parts"]
    assert parts["text"] == "About nine hours on medium."
    assert (parts["experience"], parts["rating"], parts["recommend"]) == (
        "Two months of shifts.", "4.5", True)
    assert parts["photo_urls"] == [photo]

    detail = client.get(f"/api/v1/questions/{q['id']}").json()
    assert detail["answers"][0]["parts"]["good"] == "Charges fast."
    assert detail["requirements"] == ["Experience", "Rating"]

    # Every answer to a product question carries a rating now (owner 2026-10-05),
    # so the shortest answer is its words and its stars.
    plain = client.post(f"/api/v1/questions/{q['id']}/answers", headers=_auth(asker),
                        json={"body": "Mine lasts eight. Two months of use.", "rating": "4",
                              "experience": "Two months."}).json()
    assert plain["parts"]["rating"] == "4" and plain["parts"]["good"] is None


@requires_db
def test_structured_answer_is_validated(client):
    _, asker, _ = register_and_token(client)
    _, answerer, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    qid = client.post("/api/v1/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "How loud is it at night?"}).json()["id"]
    url = f"/api/v1/questions/{qid}/answers"
    someone_elses = owned_photo_url(_auth(asker))
    for bad in ({"body": "", "rating": "4"},                       # no words at all
                {"body": "Quiet.", "rating": "4.3"},               # not a half star
                {"body": "Quiet.", "rating": "6"},
                {"body": "Quiet.", "good": "see https://evil.example"},
                {"body": "Quiet.", "photo_urls": [someone_elses]}):  # not their upload
        res = client.post(url, headers=_auth(answerer), json=bad)
        assert res.status_code == 422, (bad, res.text)
    ok = client.post(url, headers=_auth(answerer), json={"good": "Barely hear it.",
                                                         "rating": "4"})
    assert ok.status_code == 201 and ok.json()["parts"]["good"] == "Barely hear it."


def test_verdict_round_trip_and_older_yes_no():
    """Answer Page - Step 4 (7573:8635): four verdicts on the one line; Yes / No
    stay readable, and `recommend` is set only by an unqualified verdict."""
    for verdict, line, recommend in (("yes", "Yes", True), ("on_sale", "Only on sale", None),
                                     ("other_variant", "A different variant", None),
                                     ("no", "No", False)):
        body = ap.compose(ap.AnswerParts(text="Words.", verdict=verdict))
        assert body.endswith(f"Recommends it: {line}")
        back = ap.parse(body)
        assert (back.verdict, back.recommend) == (verdict, recommend)
    old = ap.compose(ap.AnswerParts(text="Words.", recommend=True))
    assert old.endswith("Recommends it: Yes") and ap.parse(old).verdict == "yes"


@requires_db
def test_verdict_through_the_api(client):
    _, asker, _ = register_and_token(client)
    _, answerer, _ = register_and_token(client)
    pid = _product(client, _auth(asker))
    qid = client.post("/api/v1/questions", headers=_auth(asker), json={
        "product_id": pid, "body": "Worth it at full price?"}).json()["id"]
    url = f"/api/v1/questions/{qid}/answers"
    r = client.post(url, headers=_auth(answerer), json={"body": "Wait for a sale.",
                                                        "verdict": "on_sale", "rating": "3.5"})
    assert r.status_code == 201, r.text
    assert (r.json()["parts"]["verdict"], r.json()["parts"]["recommend"]) == ("on_sale", None)
    assert client.post(url, headers=_auth(answerer), json={
        "body": "Hmm.", "verdict": "maybe"}).status_code == 422

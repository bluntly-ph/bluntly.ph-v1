"""Structured questions and answers (owner 2026-10-05, release blocker).

docs/STRUCTURED_QUESTIONS_FIGMA_SPEC.md §4/§8. On a question about a product:

* every member's answer carries a RATING (0.5-5, half stars);
* every specific the asker requested on the "Looking for:" line is REQUIRED -
  Experience -> experience, Pros & Cons -> good AND bad, Do you recommend
  this? -> a verdict, Is this right for me? -> right_for_you;
* a specific not requested stays optional (and is kept when sent);
* a legacy free-form question requests nothing (only the rating applies), and
  an older "Looking for: …, Rating" line still parses.

A store's own answer and a question about a store are outside the rule (a
store does not rate its own product; a store question has no rating step).
Storage is unchanged: no migration.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import answer_parts as ap
from tests.conftest import register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _ask(client, asker, body: str) -> str:
    pid = client.post("/api/v1/products", headers=asker, json={
        "name": f"Structured {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]
    res = client.post("/api/v1/questions", headers=asker, json={"product_id": pid, "body": body})
    assert res.status_code == 201, res.text
    return res.json()["id"]


FULL = {"body": "Two months in, it holds up well.", "rating": "4",
        "experience": "Two months, daily. Better than expected.",
        "good": "Quiet", "bad": "Heavy", "verdict": "yes", "right_for_you": "Yes"}


# ------------------------------------------------------------ pure rules

def test_requested_parts_follow_the_looking_for_line():
    assert ap.requested_parts("Is it loud?") == []                       # legacy free-form
    assert ap.requested_parts("Is it loud?\n\nLooking for: Experience") == ["experience"]
    assert ap.requested_parts("Q?\n\nLooking for: Do you recommend this?, Experience") == [
        "experience", "verdict"]                                          # step order
    assert ap.requested_parts("Q?\n\nLooking for: Experience, Rating") == ["experience"]
    assert ap.requested_parts("Q?\n\nLooking for: Experience, Experience") == ["experience"]
    assert ap.requested_parts("Q?\n\nLooking for: Experience, Vibes") == []   # unknown: none
    assert ap.requested_parts("Q?\n\nLooking for: Pros & Cons, Is this right for me?") == [
        "pros_cons", "fit"]


def test_missing_parts_reads_each_requested_part():
    empty = ap.AnswerParts(text="Words.")
    assert ap.missing_parts(empty, ["experience", "pros_cons", "verdict", "fit"]) == [
        "experience", "pros_cons", "verdict", "fit"]
    half = ap.AnswerParts(text="Words.", good="Quiet", bad="  ")
    assert ap.missing_parts(half, ["pros_cons"]) == ["pros_cons"]         # both sides needed
    done = ap.AnswerParts(text="W.", experience="A year.", good="Quiet", bad="Heavy",
                          recommend=True, right_for_you="If you travel.")
    assert ap.missing_parts(done, ["experience", "pros_cons", "verdict", "fit"]) == []


CERAVE = ("How long does a single bottle of this cleanser lasts?\n\n"
          "Looking for: Experience, Pros & Cons, Do you recommend this?")


@pytest.mark.parametrize("picked, parts", [
    # Owner correction 2026-10-06: the asker's "Looking for" chips are the
    # question's requirements, exactly; nothing else is added because of it.
    ("Experience, Pros & Cons, Do you recommend this?", ["experience", "pros_cons", "verdict"]),
    ("Experience", ["experience"]),
    ("Pros & Cons", ["pros_cons"]),
    ("Experience, Do you recommend this?", ["experience", "verdict"]),
    (None, []),
])
def test_the_question_requires_exactly_what_the_asker_picked(picked, parts):
    body = "Is it any good for travel?" + (f"\n\nLooking for: {picked}" if picked else "")
    assert ap.requested_parts(body) == parts
    assert ap.requested_parts(CERAVE) == ["experience", "pros_cons", "verdict"]


# ------------------------------------------------------------ through the API

@requires_db
def test_the_cerave_question_requires_its_three_chips_and_nothing_else(client):
    """The production question "How long does a single bottle of this cleanser
    lasts?" asks for Experience, Pros & Cons and Do you recommend this?"""
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), CERAVE)
    assert client.get(f"/api/v1/questions/{qid}").json()["requirements"] == [
        "Experience", "Pros & Cons", "Do you recommend this?"]
    url = f"/api/v1/questions/{qid}/answers"
    answer = {"body": "One bottle lasts me about two months, twice a day.", "rating": "4",
              "experience": "Two months, twice a day.", "good": "Gentle", "bad": "Pricey",
              "verdict": "yes"}

    for drop, part in (("experience", "experience"), ("bad", "pros_cons"), ("verdict", "verdict")):
        refused = client.post(url, headers=_auth(b),
                              json={k: v for k, v in answer.items() if k != drop})
        assert refused.status_code == 422, drop
        assert refused.json()["code"] == "answer_part_required"
        assert refused.json()["parts"] == [part]

    # "Is this right for me?" was not picked: an answer without it posts.
    ok = client.post(url, headers=_auth(b), json=answer)
    assert ok.status_code == 201, ok.text
    assert ok.json()["parts"]["right_for_you"] is None


@requires_db
def test_the_owner_scenario_experience_and_verdict(client):
    """Reviewer A asks for Experience + Verdict; Reviewer B must give rating,
    experience and a verdict; everything else is optional."""
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), "Is it loud at night?\n\n"
                                 "Looking for: Experience, Do you recommend this?")
    url = f"/api/v1/questions/{qid}/answers"
    words = {"body": "Barely audible on the lowest setting."}

    no_rating = client.post(url, headers=_auth(b), json={**words, "experience": "A year.",
                                                         "verdict": "yes"})
    assert no_rating.status_code == 422 and no_rating.json()["code"] == "answer_rating_required"
    assert no_rating.json()["parts"] == ["rating"]

    no_experience = client.post(url, headers=_auth(b), json={**words, "rating": "4",
                                                             "verdict": "yes"})
    assert no_experience.status_code == 422
    assert no_experience.json()["code"] == "answer_part_required"
    assert no_experience.json()["parts"] == ["experience"]

    no_verdict = client.post(url, headers=_auth(b), json={**words, "rating": "4",
                                                          "experience": "A year."})
    assert no_verdict.status_code == 422 and no_verdict.json()["parts"] == ["verdict"]

    neither = client.post(url, headers=_auth(b), json={**words, "rating": "4"})
    assert neither.json()["parts"] == ["experience", "verdict"]           # names every gap

    ok = client.post(url, headers=_auth(b), json={**words, "rating": "4.5",
                                                  "experience": "A year, nightly.",
                                                  "verdict": "yes"})
    assert ok.status_code == 201, ok.text
    parts = ok.json()["parts"]
    assert (parts["rating"], parts["experience"], parts["verdict"]) == (
        "4.5", "A year, nightly.", "yes")
    assert parts["good"] is None and parts["right_for_you"] is None       # optional, left out

    # Reviewer A sees it on the question, and can pick it as Best Answer.
    detail = client.get(f"/api/v1/questions/{qid}").json()
    assert [x["id"] for x in detail["answers"]] == [ok.json()["id"]]
    assert client.post(f"{url}/{ok.json()['id']}/best", headers=_auth(a)).status_code == 200


@requires_db
@pytest.mark.parametrize("asked, missing, fill", [
    ("Pros & Cons", "pros_cons", {"good": "Quiet", "bad": "Heavy"}),
    ("Is this right for me?", "fit", {"right_for_you": "Yes, for small rooms."}),
])
def test_each_requested_part_is_required(client, asked, missing, fill):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), f"Worth it?\n\nLooking for: {asked}")
    url = f"/api/v1/questions/{qid}/answers"
    base = {"body": "I have had it for a while now.", "rating": "3.5"}
    blocked = client.post(url, headers=_auth(b), json=base)
    assert blocked.status_code == 422 and blocked.json()["parts"] == [missing]
    if missing == "pros_cons":                                            # one side is not enough
        one_side = client.post(url, headers=_auth(b), json={**base, "good": "Quiet"})
        assert one_side.status_code == 422
    assert client.post(url, headers=_auth(b), json={**base, **fill}).status_code == 201


@requires_db
def test_unrequested_parts_are_optional_and_kept(client):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), "Does it fold flat?\n\nLooking for: Experience")
    res = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(b), json=FULL)
    assert res.status_code == 201, res.text
    parts = res.json()["parts"]
    assert (parts["good"], parts["bad"], parts["verdict"], parts["right_for_you"]) == (
        "Quiet", "Heavy", "yes", "Yes")


@requires_db
def test_rating_is_validated_and_required_on_a_legacy_question(client):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), "How long does the battery last?")        # free-form, legacy
    url = f"/api/v1/questions/{qid}/answers"
    words = {"body": "About nine hours on medium."}
    assert client.post(url, headers=_auth(b), json=words).json()["code"] == \
        "answer_rating_required"
    for bad in ("0", "4.3", "6", "-1"):
        assert client.post(url, headers=_auth(b), json={**words, "rating": bad}).status_code == 422
    ok = client.post(url, headers=_auth(b), json={**words, "rating": "5"})
    assert ok.status_code == 201 and ok.json()["parts"]["rating"] == "5"


@requires_db
def test_a_legacy_rating_line_parses_and_asks_only_for_the_rest(client):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), "Is it good?\n\nLooking for: Experience, Rating")
    detail = client.get(f"/api/v1/questions/{qid}").json()
    assert detail["requirements"] == ["Experience", "Rating"]             # stored line untouched
    url = f"/api/v1/questions/{qid}/answers"
    res = client.post(url, headers=_auth(b), json={"body": "Six months in, still solid.",
                                                   "rating": "4"})
    assert res.status_code == 422 and res.json()["parts"] == ["experience"]
    assert client.post(url, headers=_auth(b), json={"body": "Six months in, still solid.",
                                                    "rating": "4", "experience": "Six months."}
                       ).status_code == 201


@requires_db
def test_unknown_specifics_make_no_demands(client):
    """A line naming something the ask flow never offers is read as no request
    (requirements_of's rule), so the answer needs only words and a rating."""
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), "Is it good?\n\nLooking for: Experience, Vibes")
    res = client.post(f"/api/v1/questions/{qid}/answers", headers=_auth(b),
                      json={"body": "Works for me every day.", "rating": "4"})
    assert res.status_code == 201, res.text


# ------------------------------------------------------------ verdict "Why?"

def test_verdict_reason_round_trips_and_legacy_bodies_are_unchanged():
    """Answer Step 4.1 "Why? (optional)": its own labelled line, read back."""
    parts = ap.AnswerParts(text="Solid.", verdict="on_sale", verdict_reason="Full price is steep.",
                           rating=ap.Decimal("4"))
    body = ap.compose(parts)
    assert "Verdict reason: Full price is steep." in body
    back = ap.parse(body)
    assert (back.verdict, back.verdict_reason, back.text) == ("on_sale", "Full price is steep.",
                                                                "Solid.")
    legacy = "Works well.\n\nRecommends it: Yes\nRating: 4/5"   # written before the field
    old = ap.parse(legacy)
    assert old.verdict == "yes" and old.verdict_reason is None
    assert ap.compose(old) == legacy                              # unchanged on re-compose


@requires_db
def test_verdict_reason_is_optional_and_returned(client):
    _, a, _ = register_and_token(client)
    _, b, _ = register_and_token(client)
    qid = _ask(client, _auth(a), "Worth it?\n\nLooking for: Do you recommend this?")
    url = f"/api/v1/questions/{qid}/answers"
    base = {"body": "Had it for a year now.", "rating": "4", "verdict": "on_sale"}
    without = client.post(url, headers=_auth(b), json=base)
    assert without.status_code == 201, without.text
    assert without.json()["parts"]["verdict_reason"] is None
    _, c, _ = register_and_token(client)
    with_why = client.post(url, headers=_auth(c), json={
        **base, "verdict_reason": "Full price is steep; wait for a sale."})
    assert with_why.status_code == 201, with_why.text
    assert with_why.json()["parts"]["verdict_reason"] == "Full price is steep; wait for a sale."
    detail = client.get(f"/api/v1/questions/{qid}").json()
    reasons = {x["id"]: x["parts"]["verdict_reason"] for x in detail["answers"]}
    assert reasons[with_why.json()["id"]] == "Full price is steep; wait for a sale."
    assert reasons[without.json()["id"]] is None

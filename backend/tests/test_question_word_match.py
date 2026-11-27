"""QA-050 (Figma Questions v6, "Best match for your search"): the question
words of a search are matched one by one, and the question holding most of
them comes first."""

from __future__ import annotations

import uuid

from app.services.qa_service import question_words
from tests.conftest import register_and_token, requires_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_question_words_drop_stopwords_short_words_and_repeats():
    assert question_words("How much NOISE does it make in a quiet library? noise") == [
        "much", "noise", "make", "quiet", "library"]
    assert question_words("is it ok") == []
    assert question_words("100% legit_") == ["100", "legit"]


@requires_db
def test_words_apart_still_find_the_question_and_most_matches_rank_first(client):
    _, token, _ = register_and_token(client)
    h = _auth(token)
    pid = client.post("/api/v1/products", headers=h, json={
        "name": f"Word match fan {uuid.uuid4().hex[:8]}", "category": "electronics"}).json()["id"]

    def ask(body: str) -> str:
        resp = client.post("/api/v1/questions", headers=h, json={"product_id": pid, "body": body})
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    both = ask("How much noise does it make in a quiet library?")
    one = ask("Does it make noise when charging?")
    ask("How long does the battery last?")

    resp = client.get("/api/v1/questions", params={"product_id": pid, "q": "noise library"})
    assert resp.status_code == 200, resp.text
    ids = [q["id"] for q in resp.json()]
    # The phrase "noise library" appears nowhere, yet both questions are found,
    # the one with both words first, and the unrelated one is left out.
    assert ids == [both, one]

    oldest = client.get("/api/v1/questions",
                        params={"product_id": pid, "q": "noise library", "sort": "oldest"}).json()
    assert [q["id"] for q in oldest] == [both, one]

    # A wildcard inside a word is a literal character, not "anything".
    assert client.get("/api/v1/questions",
                      params={"product_id": pid, "q": "no%se lib_ary"}).json() == []

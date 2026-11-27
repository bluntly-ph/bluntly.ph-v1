"""Product search returns the closest match first (QA-001).

`GET /api/v1/products?q=` casts a deliberately wide net — `ilike %term%`, so a
reviewer who types "anker" still finds "Anker 737 Power Bank (24000mAh)" and one
who types part of a model number still finds the model. That width is wanted.

What was wrong was the ORDER. The net was sorted by `created_at DESC`, so the
newest row won no matter how badly it matched: searching "ma" put a product
somebody had just submitted above every genuine match, with "10000mAh" and
"MacBook" beneath it in arbitrary order. On the review composer's "What did you
buy?" step that reads as a broken search, and it is the step where a reviewer
either finds their product or gives up and creates a duplicate of it.

The ranking is explainable on purpose: exact name, then name-starts-with, then a
word inside the name starting with the term, then a bare substring; shorter
names break ties, and only then does recency matter.
"""

from __future__ import annotations

import random
import uuid

from app.models.product import Product
from tests.conftest import requires_db


def _product(db, name: str):
    product = Product(canonical_name=name)
    db.add(product)
    db.flush()
    return product


@requires_db
def test_search_ranks_the_closest_name_first(db, client):
    """Exact, then prefix, then word-start, then "it is in there somewhere"."""
    marker = uuid.uuid4().hex[:6]
    # Created newest-first in the order that would WIN under the old sort, so a
    # pass here cannot be recency accidentally agreeing with relevance.
    _product(db, f"Aukey 10000m{marker} Power Bank")   # substring only
    _product(db, f"Power Bank m{marker} Edition")      # word-start
    _product(db, f"m{marker} Air M2 (13-inch)")        # name prefix
    _product(db, f"m{marker}")                         # exact
    db.commit()

    body = client.get(f"/api/v1/products?q=m{marker}&limit=10").json()
    names = [row["canonical_name"] for row in body]

    assert names[0] == f"m{marker}", "the exact name is not first"
    assert names[1] == f"m{marker} Air M2 (13-inch)", "the prefix match is not second"
    assert names[2] == f"Power Bank m{marker} Edition", "the word-start match is not third"
    assert names[3] == f"Aukey 10000m{marker} Power Bank", "the substring match is not last"


@requires_db
def test_a_newer_worse_match_does_not_outrank_an_older_better_one(db, client):
    """The regression itself: recency used to be the only sort key."""
    marker = uuid.uuid4().hex[:6]
    exact = _product(db, f"k{marker}")
    db.commit()
    # Created AFTER the exact match, and matching only as a substring.
    _product(db, f"Something With k{marker} Buried Inside It")
    db.commit()

    body = client.get(f"/api/v1/products?q=k{marker}&limit=10").json()

    assert body[0]["id"] == str(exact.id)


@requires_db
def test_an_unfiltered_listing_is_still_newest_first(db, client):
    """No search term, no relevance to rank by — the catalogue listing keeps
    its own order rather than silently changing shape."""
    newest = _product(db, f"Listing fixture {uuid.uuid4().hex[:8]}")
    db.commit()

    body = client.get("/api/v1/products?limit=5").json()

    assert body[0]["id"] == str(newest.id)


def _letters(n: int) -> str:
    """n distinct letters no fixture elsewhere is built from, so trigram scores
    are exactly the ones the pattern below implies."""
    return "".join(random.sample("ghjkmnpqrstvwxyz", n))


@requires_db
def test_sharing_only_two_first_letters_is_not_a_typo_match(db, client):
    """QA-022/033: "man" suggested MacBook, "material" and "mattress".

    A three-letter query has four trigrams; a word that shares only its first
    two letters shares two of them, word_similarity exactly 0.5, which the old
    `>= 0.5` threshold accepted as a typo. Built from letters, not product names,
    so the case is the pattern and not one example."""
    w = _letters(7)
    query = w[0] + w[1] + w[2]               # "man"
    near_miss = w[0] + w[1] + w[3:7]         # "mac…": same first two letters only
    prefix = query + w[3:6]                  # "mandaue": a real word-start match
    _product(db, f"Brand {near_miss} Edition")
    kept = _product(db, f"{prefix} Foam")
    db.commit()

    names = [r["canonical_name"] for r in client.get(f"/api/v1/products?q={query}&limit=20").json()]

    assert kept.canonical_name in names
    assert f"Brand {near_miss} Edition" not in names, "a two-letter overlap ranked as a typo"


@requires_db
def test_a_genuine_one_letter_typo_still_matches(db, client):
    """The tolerance QA-008 and Business Rules §6 depend on stays: dropping one
    letter ("ankr" for "Anker", "tefl" for "Tefal") scores 0.6 and is found."""
    w = _letters(5)
    name = f"{w} Power Bank"                 # "anker …"
    typo = w[0:3] + w[4]                     # "ankr"
    product = _product(db, name)
    db.commit()

    body = client.get(f"/api/v1/products?q={typo}&limit=20").json()

    assert str(product.id) in [r["id"] for r in body]


def test_the_typo_threshold_is_strictly_above_one_half():
    """Pinned without a database: the constant is the whole fix."""
    from app.services.product_search import WORD_SIMILARITY

    assert 0.5 < WORD_SIMILARITY <= 0.6


@requires_db
def test_the_search_box_suggests_only_products_with_something_to_read(db, client):
    """QA-022/033 on live data: "ma" suggested a question typed into the product
    field and products named by a pasted link, with nothing behind them. The
    search box's `browse` mode leaves those out and, within a tier, puts the
    most-reviewed first; the composer's picker (no `browse`) still sees all."""
    from app.models.enums import QuestionDirectedTo
    from app.models.qa import Question
    from tests.conftest import make_user

    marker = uuid.uuid4().hex[:6]
    empty = _product(db, f"z{marker} material question?")
    link = _product(db, f"https://s.shopee.ph/z{marker}")
    few = _product(db, f"z{marker} Mattress Protector")
    few.review_count = 1
    many = _product(db, f"z{marker} Classic Mattress")
    many.review_count = 5
    asked = _product(db, f"z{marker} Pants")
    db.add(Question(product_id=asked.id, asker_id=make_user(db).id,
                    body="What is the material?",
                    directed_to=QuestionDirectedTo.buyers))
    db.commit()

    names = [row["canonical_name"] for row in client.get(
        f"/api/v1/products?q=z{marker}&limit=10&browse=true").json()]
    assert empty.canonical_name not in names and link.canonical_name not in names
    assert names[:2] == [many.canonical_name, few.canonical_name]
    assert asked.canonical_name in names

    picker = [row["canonical_name"] for row in client.get(
        f"/api/v1/products?q=z{marker}&limit=10").json()]
    assert empty.canonical_name in picker


@requires_db
def test_within_word_starts_the_earlier_word_ranks_first(db, client):
    """QA-022/033: for a short query every product with a word starting with it
    matches; the one whose SECOND word matches outranks the one whose fourth
    does, whatever was created last (and, in the search box, most reviewed)."""
    marker = uuid.uuid4().hex[:5]
    late = _product(db, f"Enzo Scents Le q{marker}le Elixir")   # 4th word
    late.review_count = 50
    _product(db, f"Uratex Classic q{marker}ttress")            # 3rd word
    _product(db, f"Apple q{marker}cBook Air")                  # 2nd word
    db.commit()
    names = [r["canonical_name"] for r in client.get(
        f"/api/v1/products?q=q{marker}&limit=10").json()]
    assert names == [f"Apple q{marker}cBook Air", f"Uratex Classic q{marker}ttress",
                     f"Enzo Scents Le q{marker}le Elixir"]

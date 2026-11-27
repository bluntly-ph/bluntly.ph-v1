"""Product search: exact, aliases, word prefixes, then typo tolerance (Business Rules §6).

    "Typo-tolerant matching and a maintained synonym/alias library are being
    built together at launch ... Typo tolerance runs on Postgres trigram
    similarity, already installed and running elsewhere in the codebase."

The ranking is written as explicit tiers, so a result's position can always be
explained:

    0  the name equals the query
    1  an alias (synonym) equals the query
    2  the name starts with the query
    3  a WORD of the name starts with the query — earlier words first
    4  an alias starts with the query, or a word of one does
    5  trigram similarity — typos and misspellings ("jisulfe" -> "Jisulife"),
       above WORD_SIMILARITY; sharing only a word's first two letters is not one
    6  a plain substring, only for queries of 4+ characters

Short queries (under 3 characters) only ever match at the START of a word: "ma"
finds "Mandaue" and "MacBook", and no longer "10000mAh", where "ma" sits in
the middle of a token.

Public typo tolerance is a separate system from the fraud checks'
duplicate-content similarity (fraud_service); they share the extension, not
thresholds or code.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import and_, case, exists, false, func, literal, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.product import Product, ProductAlias

#: Below this length a query matches word starts only.
MIN_FUZZY_LENGTH = 3
#: Below this length there is no plain-substring fallback either.
MIN_SUBSTRING_LENGTH = 4
#: pg_trgm word_similarity at or above this counts as a typo-tolerant match.
#:
#: Strictly above one half, not at it (QA-022/033). A three-letter query has
#: four trigrams, and any word sharing only its first two letters shares two of
#: them — exactly 0.5 — so "man" matched "MacBook", "material" and "mattress"
#: as if they were typos of it. Genuine misspellings sit clearly higher
#: (measured on Postgres 17, 2026-09-24): "ankr"→Anker 0.60, "tefl"→Tefal 0.60,
#: "powr"→Power 0.60, "jisulfe"→Jisulife 0.625, "matress"→Mattress 0.70.
WORD_SIMILARITY = 0.55

_NON_ALNUM = re.compile(r"[^0-9a-z]+")


def normalize(text: str | None) -> str:
    """Lower-case, accents folded, every run of non-alphanumerics one space."""
    folded = unicodedata.normalize("NFKD", text or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    return _NON_ALNUM.sub(" ", folded).strip()


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _normalized_name() -> ColumnElement:
    # Same normalization as `normalize`, done in SQL: lower-case, and every
    # run of non-alphanumerics becomes one space, so "Life9-Handheld" has a
    # word starting at "handheld".
    return func.regexp_replace(func.lower(Product.canonical_name), "[^0-9a-z]+", " ", "g")


def _word_start(column: ColumnElement, term: str) -> ColumnElement:
    escaped = _like_escape(term)
    return or_(column.like(f"{escaped}%", escape="\\"),
               column.like(f"% {escaped}%", escape="\\"))


def match_clause(term: str) -> ColumnElement:
    """A WHERE clause over `Product` for a normalized query term."""
    if not term:
        return literal(True)
    name = _normalized_name()
    alias_word_start = exists().where(
        ProductAlias.product_id == Product.id, _word_start(ProductAlias.normalized, term))
    clauses = [_word_start(name, term), alias_word_start]
    if len(term) >= MIN_FUZZY_LENGTH:
        clauses.append(func.word_similarity(term, name) >= WORD_SIMILARITY)
        clauses.append(exists().where(
            ProductAlias.product_id == Product.id,
            func.word_similarity(term, ProductAlias.normalized) >= WORD_SIMILARITY))
    if len(term) >= MIN_SUBSTRING_LENGTH:
        clauses.append(name.like(f"%{_like_escape(term)}%", escape="\\"))
    return or_(*clauses)


def rank_expression(term: str) -> ColumnElement:
    """The tier (lower is better) for ORDER BY; see the module docstring."""
    if not term:
        return literal(0)
    name = _normalized_name()
    escaped = _like_escape(term)
    alias_exact = exists().where(ProductAlias.product_id == Product.id,
                                 ProductAlias.normalized == term)
    alias_prefix = exists().where(ProductAlias.product_id == Product.id,
                                  _word_start(ProductAlias.normalized, term))
    fuzzy = (func.word_similarity(term, name) >= WORD_SIMILARITY
             if len(term) >= MIN_FUZZY_LENGTH else false())
    return case(
        (name == term, 0),
        (alias_exact, 1),
        (name.like(f"{escaped}%", escape="\\"), 2),
        (name.like(f"% {escaped}%", escape="\\"), 3),
        (alias_prefix, 4),
        (fuzzy, 5),
        else_=6,
    )


def browsable() -> ColumnElement:
    """A product a reader searching can find something on (QA-022/033).

    The search box's suggestions offered "What type of material used in
    Simwood pants?" and "https://s.shopee.ph/…" for "ma": products created
    by mistake (a question typed into the product field, a pasted link before
    names were read from it), with no review and no question behind them. A
    suggestion is a promise of something to read, so the search box lists
    only products with a published review or a question, and never one named
    by a bare link. The review composer's picker still sees every product, so
    a reviewer attaches to an existing one instead of creating a duplicate.
    """
    from app.models.qa import Question

    has_question = exists().where(Question.product_id == Product.id,
                                  Question.is_removed.is_(False))
    return and_(or_(Product.review_count > 0, has_question),
                ~Product.canonical_name.ilike("http%"))


def search(stmt, q: str | None, *, browse: bool = False):
    """Apply matching and ranking to a `select(Product)` statement.

    `browse` is the search box's mode: only `browsable()` products, and within
    a tier the most-reviewed first, so "ma" leads with what people have
    actually reviewed rather than with whatever was named first.
    """
    term = normalize(q)
    if browse:
        stmt = stmt.where(browsable())
    if not term:
        return stmt.order_by(Product.created_at.desc())
    name = _normalized_name()
    similarity = (func.word_similarity(term, name) if len(term) >= MIN_FUZZY_LENGTH
                  else literal(0.0))
    popularity = (Product.review_count.desc(),) if browse else ()
    return stmt.where(match_clause(term)).order_by(
        rank_expression(term), word_position(term), *popularity, similarity.desc(),
        func.length(Product.canonical_name), Product.created_at.desc())


def word_position(term: str) -> ColumnElement:
    """Where in the name the matching word starts (QA-022/033): within one tier,
    the earlier word is the closer match. For "ma", "Mandaue Foam …" (the first
    word) comes before "Apple MacBook …" (the second) and both before "Enzo
    Scents Le Male" (the fourth), whatever their review counts. No word match:
    sorts after every word match in the tier (typo and substring tiers)."""
    if not term:
        return literal(0)
    found = func.strpos(literal(" ") + _normalized_name(), literal(" ") + term)
    return case((found > 0, found), else_=literal(10_000))


def matching_product_ids(q: str | None):
    """A subquery of product ids matching `q`, for review and Q&A searches."""
    term = normalize(q)
    return select(Product.id).where(and_(match_clause(term)))

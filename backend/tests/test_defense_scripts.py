"""The defense scripts: where they may run, and what the dataset may contain.

The defense dataset is fabricated on purpose, so the one property that matters
most is that it can never be written anywhere but bluntly-ph-test or a local
database. The rest keeps the dataset honest with the rules it demonstrates:
no secrets, no placeholder text, nothing the platform itself would refuse.
"""

from __future__ import annotations

import re

import pytest

from scripts.defense import dataset as D
from scripts.defense import guard
from scripts.defense.reset import _DISPOSABLE
from scripts.defense.verify import GARBAGE

PROD_REF = "byobedbhodhvocgrkrse"


@pytest.fixture
def target(monkeypatch):
    """Point the guard at a database without touching the real configuration."""
    from app.core import env_guard
    from app.core.config import settings

    def aim(url: str, *, marker: bool = True, supabase_url: str = "", signals=()):
        monkeypatch.setattr(type(settings), "effective_database_url",
                            property(lambda self: url))
        monkeypatch.setattr(settings, "supabase_url", supabase_url)
        monkeypatch.setattr(env_guard, "is_test_target", lambda: marker)
        monkeypatch.setattr(env_guard, "production_signals", lambda extra=None: list(signals))
        monkeypatch.setattr(env_guard, "describe_target", lambda: "(target)")
    return aim


def test_production_is_refused_before_anything_else(target):
    target(f"postgresql+psycopg://u:p@db.{PROD_REF}.supabase.co/postgres",
           signals=["DATABASE_URL references the production Supabase project"])
    with pytest.raises(SystemExit) as exc:
        guard.require_defense_target("seed")
    assert exc.value.code == 2


def test_an_undeclared_target_is_refused(target):
    target("postgresql+psycopg://u:p@127.0.0.1:5432/defense", marker=False)
    with pytest.raises(guard.DefenseTargetError, match="test environment"):
        guard.classify_target()


def test_an_unrecognised_database_is_refused_even_when_declared(target):
    target("postgresql+psycopg://u:p@db.someoneelse.supabase.co/postgres")
    with pytest.raises(guard.DefenseTargetError, match="unrecognised"):
        guard.classify_target()


def test_the_test_project_and_a_local_database_are_the_only_targets(target):
    target(f"postgresql+psycopg://u:p@aws-0.pooler.supabase.com/postgres?x={guard.TEST_PROJECT_REF}")
    assert guard.classify_target() == "test"
    target("postgresql+psycopg://u:p@pooler.supabase.com/postgres",
           supabase_url=f"https://{guard.TEST_PROJECT_REF}.supabase.co")
    assert guard.classify_target() == "test"
    for host in ("127.0.0.1", "localhost", "postgres"):
        target(f"postgresql+psycopg://u:p@{host}:5432/defense")
        assert guard.classify_target() == "local"


def test_the_reset_never_treats_a_real_address_as_disposable():
    real = ("team.inbox@gmail.com", "team.inbox+maria@gmail.com", "someone@bluntly.ph",
            "user@example.com.ph.evil.org")
    for email in real:
        assert not any(re.search(p, email, re.IGNORECASE) for p in _DISPOSABLE), email
    for email in ("t_1a2b@example.com", "gio_salazar@demo.bluntly.ph", "x@bluntly.local"):
        assert any(re.search(p, email, re.IGNORECASE) for p in _DISPOSABLE), email


def test_the_dataset_carries_no_address_password_or_code():
    source = open(D.__file__, encoding="utf-8").read().lower()
    assert "password" not in source
    assert "@gmail" not in source
    assert not re.search(r"\botp\s*[:=]", source)
    # Persona addresses are derived at run time from an address the team owns.
    assert all("@" not in p.username for p in D.PEOPLE.values())


def test_every_account_is_one_the_site_would_accept():
    usernames = [p.username for p in D.PEOPLE.values()]
    assert len(set(usernames)) == len(usernames)
    assert all(re.fullmatch(r"[a-z0-9_]{3,32}", u) for u in usernames)
    assert {p.role for p in D.PEOPLE.values()} <= {"user", "administrator", "super_admin"}
    assert set(D.RING) <= set(D.PEOPLE)


def test_every_review_is_written_by_someone_about_something():
    for r in D.REVIEWS:
        assert r.author in D.PEOPLE, r.key
        assert r.product in D.PRODUCT, r.key
        # The earning rule for a 2.5-star "it depends" is the owner's open question.
        assert not (r.verdict == "it_depends" and r.stars == 2.5), r.key


def _texts():
    for r in D.REVIEWS:
        yield r.key, (r.title, r.discussion, r.explanation, r.target, r.anti, *r.pros, *r.cons)
        if r.update:
            yield r.key, (r.update.title, r.update.discussion, *r.update.pros, *r.update.cons)

    def thread(comments):
        for c in comments:
            yield c.body
            yield from thread(c.replies)
    for key, comments in D.COMMENTS.items():
        yield key, tuple(thread(comments))
    for q in D.QUESTIONS:
        yield q.key, (q.body, *(a.body for a in q.answers))
    for s in D.STORE_REVIEWS:
        yield s.key, (s.title, s.comment, s.response or "")


def test_no_placeholder_or_debug_text_in_the_dataset():
    hits = [(key, m.group(0)) for key, texts in _texts() for t in texts
            if t and (m := GARBAGE.search(t))]
    assert hits == []


# --------------------------------------------------------------- transactions (QA seed)

def test_every_report_window_has_orders_and_none_predates_its_review():
    """Owner 2026-10-05: the Admin Dashboard, analytics and affiliate views have
    money in every window they compare - this week, last week, 30d and the 30d
    before, 90d and the 90d before - and an order never comes before the review
    its reader clicked through."""
    from scripts.defense import dataset as D

    for label, lo, hi in D.REPORT_WINDOWS:
        assert D.money_in(lo, hi) > 0, f"no money in {label}"
    for order in D.ORDERS:
        review = D.REVIEW[order.review]
        assert order.days_ago < review.days_ago, (order, review.days_ago)
        assert order.status in ("completed", "pending", "cancelled")


def test_the_window_totals_are_fixed_numbers():
    """Deterministic: what each window should hold after a seed, whatever day it
    runs (orders are placed relative to the seed's own clock)."""
    from decimal import Decimal

    from scripts.defense import dataset as D

    assert D.money_in(0, 6) == Decimal("2143.00")           # this week (incl. 1 pending)
    assert D.money_in(7, 13) == Decimal("3008.00")          # last week (incl. 2 pending)
    assert D.money_in(30, 59) == Decimal("2914.00")         # the 30 days before "30d"
    assert sum(1 for o in D.ORDERS if o.status == "cancelled") == 2
    assert len(D.ORDERS) == 29


def test_every_member_answer_to_a_product_question_has_a_rating():
    """Structured Q&A (owner 2026-10-05): the API refuses a product answer
    without stars, so the seed must carry one for each - and none for a store."""
    for q in D.QUESTIONS:
        for n, _ in enumerate(q.answers):
            rated = (q.key, n) in D.ANSWER_RATINGS
            assert rated == (q.product is not None), (q.key, n)
    assert all(r in {f"{x / 2:g}" for x in range(1, 11)} for r in D.ANSWER_RATINGS.values())

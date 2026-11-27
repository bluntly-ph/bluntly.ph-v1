"""Shared test fixtures.

The import order in this file is load-bearing. `.env.test` is loaded into the
process environment, and the production guard runs, BEFORE anything from `app`
is imported - because importing `app.core.config` resolves the database URL and
importing `app.db.session` opens an engine against it. A guard that ran after
those imports would be checking a connection that already exists.
"""

from __future__ import annotations

import os
import pathlib
import sys

# --- 1. Load backend/.env.test, if present, into the real environment -------
# pydantic-settings gives actual environment variables precedence over its
# `env_file`, so this is what redirects the suite away from the repo-root .env
# (which is production). Set before any app import.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.core.env_guard import (  # noqa: E402
    ProductionTargetError,
    load_test_env,
    require_non_production,
)

load_test_env()

# --- 2. Refuse to continue if this is production -----------------------------

try:
    require_non_production("pytest")
except ProductionTargetError as exc:  # pragma: no cover - the abort path
    # Raising from conftest import aborts collection before a single test runs,
    # which is the point: no fixture, no user, no review reaches the database.
    raise SystemExit(str(exc)) from exc

# --- 3. Only now is it safe to import the application ------------------------
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

# The suite makes many auth/vote calls from one client IP; lift the rate limits so
# tests aren't self-throttled. (A dedicated limiter test can set them back locally.)
settings.auth_rate_limit_max = 1_000_000
settings.vote_rate_limit_max = 1_000_000
# Reports and comments too: against a nearby database the suite files more than
# five reports a minute from the one test IP, which a remote database's latency
# used to hide. Each limiter keeps its own dedicated test.
settings.report_rate_limit_max = 1_000_000
settings.comment_rate_limit_max = 1_000_000

# The suite must never reach Resend: no network, no spend, no codes in transit.
settings.email_provider = "console"
settings.resend_api_key = ""
# EXPLICIT Seeding configuration for the suite — NOT the application default
# (which is Post-Seeding: a new review waits for its gate votes). The queue
# ordering, attach and publish-alias suites need freshly submitted reviews to
# be in the earn_eligible queue at once, which is what Seeding does. Tests of
# the default switch it back (see test_public_lifecycle_api.py).
settings.earn_gate_phase = "seeding"
# The Honesty Fund's distribution formula is an open business decision (§14) and
# is OFF by default. The suite still exercises the existing mechanism's safety
# properties (idempotency, pool arithmetic), so it switches it on explicitly;
# test_business_rules.py asserts the default is off.
settings.honesty_fund_distribution_enabled = True


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


#: Seconds to wait for the probe below. Small on purpose: this decides whether
#: to *skip* tests, so being wrong costs a skipped suite, while being slow costs
#: every run and every CI job.
DB_PROBE_TIMEOUT_SECONDS = 3


def db_available() -> bool:
    """True when a real Postgres is reachable (integration tests).

    Runs at import, because `requires_db` is a module-level marker - so anything
    this blocks on blocks pytest *collection*, before a single test runs.

    It therefore gets its own engine with an explicit connect timeout rather
    than borrowing the application's. A refused connection fails in
    milliseconds, which is why this was fine for a long time; a port that
    silently drops packets instead does not fail at all, and the application
    engine has no timeout to stop it waiting. The symptom is not a failure but
    a hang: no output, no tests, nothing to read - and in CI, a job that sits
    there until the runner kills it.
    """
    from sqlalchemy import create_engine, text

    from app.core.config import settings

    probe = None
    try:
        probe = create_engine(
            settings.effective_database_url,
            connect_args={"connect_timeout": DB_PROBE_TIMEOUT_SECONDS},
            pool_pre_ping=False,
        )
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        if probe is not None:
            probe.dispose()


#: Resolved once, at import. Hoisted out of the marker below so that an autouse
#: fixture can ask "is there a database?" without paying another probe per test
#: — and, more importantly, without opening a connection on a machine that has
#: none, which does not fail fast but hangs.
DB_AVAILABLE = os.getenv("SKIP_DB_TESTS") != "1" and db_available()

requires_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="Postgres not available",
)


def _storage_configured() -> bool:
    from app.core.config import settings
    return bool(settings.supabase_url and settings.supabase_secret_key)


#: Tests that put a REAL object in a Supabase Storage bucket (the private receipts
#: bucket). Like a database, storage is an external service: CI's ephemeral-Postgres
#: job has none and skips them; the weekly run against the TEST project, which has
#: the credentials, still runs them. Not a way to quieten a failing test: it only
#: answers "is there a bucket to write to?".
requires_storage = pytest.mark.skipif(
    not _storage_configured(),
    reason="Supabase Storage credentials not configured",
)


def find_pending_queue_item(client, mod_headers: dict, review_id: str, *,
                            view: str = "waiting"):
    """Locate a review's card in the moderator queue (in one of its views:
    "waiting", the default, or "taken_down" - MQA-015).

    A long-lived dev DB accumulates thousands of never-published pending
    reviews, so scanning pages is O(n) requests and each page assesses every
    card it returns. This used to compute the review's offset from a created_at
    ordering; the queue is ordered by POLICY now — lane, then SLA, then score —
    so position in time says nothing about which page a card is on.

    The server's own `q` filter replaces that arithmetic: scoping the queue to
    the review's title narrows it to a handful of rows however deep the backlog
    is. We are testing that the endpoint returns the card, not that we can scan
    the whole backlog.
    """
    import uuid as _uuid
    from urllib.parse import quote

    from app.db.session import SessionLocal
    from app.models.review import Review

    db = SessionLocal()
    try:
        target = db.get(Review, _uuid.UUID(review_id))
        if target is None:
            return None
        title = target.title
    finally:
        db.close()

    PAGE = 100

    def fetch(offset: int):
        return client.get(
            f"/api/v1/admin/review-queue?limit={PAGE}&offset={offset}&q={quote(title)}"
            f"&view={view}",
            headers=mod_headers,
        ).json()

    def match(page):
        return next(
            (i for i in page.get("items", []) if i["review"]["id"] == review_id), None
        )

    first = fetch(0)
    hit = match(first)
    if hit is not None:
        return hit

    # `q` narrows, but fixture titles are not unique — this suite creates
    # hundreds of reviews titled "Great" — so one page is not a guarantee.
    # Policy order sorts a freshly created routine card LAST among its peers
    # (same lane, same SLA state, same score, newest queued_at), so walk
    # backwards from the final page rather than forwards from the first.
    total = int(first.get("total") or 0)
    offset = ((total - 1) // PAGE) * PAGE if total else 0
    while offset > 0:
        hit = match(fetch(offset))
        if hit is not None:
            return hit
        offset -= PAGE
    return None


def register_and_token(client, role: str = "user") -> tuple[str, str, str]:
    """Register a fresh user; optionally promote role. Returns (id, token, email)."""
    import uuid

    from app.core.security import create_access_token
    from app.db.session import SessionLocal
    from app.models.enums import MemberRole
    from app.models.user import User

    email = f"t_{uuid.uuid4().hex}@example.com"
    resp = client.post("/api/v1/auth/register", json={
        "email": email, "password": "password123", "display_name": "Tester"})
    body = resp.json()
    uid, token = body["user"]["id"], body["access_token"]
    if role != "user":
        db = SessionLocal()
        try:
            user = db.get(User, uuid.UUID(uid))
            user.role = MemberRole(role)
            db.commit()
        finally:
            db.close()
        token = create_access_token(uuid.UUID(uid), role)
    return uid, token, email


def set_trust_stage(user_id: str, stage: int) -> None:
    """Put a test account at a trust stage directly.

    Business Rules §8: commenting needs Stage 1 ("posted at least one review").
    Suites about comments, not about earning a stage, start their commenters
    there instead of writing a review first.
    """
    import uuid

    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(user_id))
        user.trust_stage = stage
        db.commit()
    finally:
        db.close()


def make_established(user_id: str, *, stage: int = 2) -> None:
    """An account whose votes and reports carry full weight (Business Rules §11):
    Stage 2+, reputation 100, and older than the 30-day halving."""
    import uuid
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from app.db.session import SessionLocal
    from app.models.user import User

    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(user_id))
        user.trust_stage = stage
        user.reputation_score = Decimal("100")
        user.created_at = datetime.now(UTC) - timedelta(days=60)
        db.commit()
    finally:
        db.close()


def unique_text(label: str = "Review") -> str:
    """A long, meaningful review text no other test or run has written.

    The duplicate-text check (QA 2026-09-29) searches the whole platform, and
    the test database is shared by every test and, locally, every run. Two
    tests writing the same sentence are, correctly, a copy of each other.
    """
    import uuid

    return f"{label} notes " + " ".join(uuid.uuid4().hex[:7] for _ in range(16)) + "."


def register_commenter(client, role: str = "user") -> tuple[str, str, str]:
    """A fresh account at Stage 1, the minimum to comment (§8)."""
    uid, token, email = register_and_token(client, role)
    set_trust_stage(uid, 1)
    return uid, token, email


def claim_body(evidence: str | None = "I run this store.", *,
               shop_name: str = "Test Shop") -> dict:
    """A seller claim with the ownership proof Business Rules §9 requires."""
    return {"registration_kind": "dti", "registration_number": "DTI-3145678",
            "registered_business_name": "Test Trading", "marketplace_shop_name": shop_name,
            "evidence": evidence}


def owned_photo_url(headers: dict) -> str:
    """A proof-photo URL the caller in `headers` genuinely owns.

    Reviews used to accept any string as `photo_url`, and since
    verification_status is derived from it being non-null, that made `verified`
    self-assertable - which also unlocks earning eligibility (FR-6) and makes
    FR-8's first fraud layer free to bypass. Ownership is enforced now, so
    fixtures have to hold a real one.

    Derived rather than uploaded: hitting Supabase Storage in every review
    fixture would make the suite slow and network-dependent for a value the
    server only pattern-matches. `upload_review_photo` writes
    `<REVIEW_BUCKET>/<user_id>/<uuid>.<ext>`, and that shape is what is checked.
    """
    import uuid as _uuid

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.services.storage import REVIEW_BUCKET

    uid = TestClient(app).get("/api/v1/auth/me", headers=headers).json()["id"]
    base = (settings.supabase_url or "https://test.supabase.co").rstrip("/")
    return f"{base}/storage/v1/object/public/{REVIEW_BUCKET}/{uid}/{_uuid.uuid4().hex}.jpg"


@pytest.fixture
def db():
    """A live database session, for tests that assert on the database itself.

    This did not exist. `test_postgrest_surface` and `test_wallet_concurrency`
    were both written taking a `db` argument, so all four of those tests failed
    at setup with "fixture 'db' not found" — and nobody saw it, because
    `requires_db` skipped them on every machine that has ever run the suite.
    They were counted as coverage while being incapable of passing. The first
    run against a real database surfaced them immediately.

    Rows outlive a rollback here, because the tests under it commit on purpose
    (that is the point of the concurrency ones), so anything `make_user` created
    is deleted by id afterwards rather than trusted to disappear with the
    transaction.
    """
    from app.db.session import SessionLocal

    session = SessionLocal()
    created: list = []
    session.info["created_users"] = created
    try:
        yield session
    finally:
        try:
            session.rollback()
            if created:
                from sqlalchemy import text

                from app.models.user import User
                # Test cleanup may remove the only Super Admin it created;
                # migration 0067's guard allows that for this transaction only.
                session.execute(text("SET LOCAL bluntly.allow_no_super_admin = 'on'"))
                session.query(User).filter(User.id.in_(created)).delete(
                    synchronize_session=False)
                session.commit()
        finally:
            session.close()


def make_user(db, **overrides):
    """A persisted user for a test that needs a real row rather than a client.

    Registered with the `db` fixture for deletion, so a committing test does not
    leave an account behind. Referenced by `test_wallet_concurrency` and, like
    the fixture above, never actually defined until now.
    """
    import uuid

    from app.models.user import User

    # Defaults, not fixed values. Passing them positionally alongside
    # **overrides meant `make_user(db, display_name="...")` raised
    # "got multiple values for keyword argument" — a helper that looks like it
    # takes overrides while rejecting the three fields a caller is most likely
    # to want to set.
    overrides.setdefault("email", f"t_{uuid.uuid4().hex}@example.com")
    overrides.setdefault("password_hash", "not-a-real-hash")
    overrides.setdefault("display_name", "Fixture User")
    user = User(**overrides)
    db.add(user)
    db.flush()
    created = db.info.get("created_users")
    if created is not None:
        created.append(user.id)
    return user


def all_pages(client, path: str, headers: dict, **params) -> list[dict]:
    """Every row of a list endpoint that pages with limit/offset (200 a page):
    the admin claims and appeals lists. A long-lived test database holds
    hundreds of pending claims, so a row filed a moment ago can sit past the
    first page; looking at one page made four tests depend on the DB's age."""
    rows: list[dict] = []
    for offset in range(0, 200 * 50, 200):
        page = client.get(path, headers=headers,
                          params={**params, "limit": 200, "offset": offset}).json()
        rows.extend(page)
        if len(page) < 200:
            break
    return rows


def all_report_queue_items(client, headers: dict, **params) -> list[dict]:
    """Every item of GET /admin/reports for these filters, page by page.

    The queue is capped at 100 a page and has no newest-first order, so in a
    long-lived test database a report filed a moment ago can sit past the first
    page. Looking at one page made two tests fail as the database grew, not as
    the code changed.
    """
    items: list[dict] = []
    offset = 0
    for _ in range(200):
        page = client.get("/api/v1/admin/reports", headers=headers,
                          params={**params, "limit": 100, "offset": offset}).json()
        batch = page.get("items", [])
        items.extend(batch)
        if len(batch) < 100:
            break
        offset += 100
    return items

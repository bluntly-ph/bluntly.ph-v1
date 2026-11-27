"""Migration 0065 on real rows: moderator -> administrator / super_admin, and back.

Runs the actual migrations (as subprocesses, so the scratch database's URL is
the one alembic's env resolves) against a throwaway database next to the test
one: blank -> 0063, seed the old shapes, -> head, check, -> 0063, check, ->
head again. Skipped where the test role cannot create a database.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings
from tests.conftest import requires_db

pytestmark = requires_db

BACKEND = Path(__file__).resolve().parents[1]
BEFORE = "0063_seller_support_requests"


@pytest.fixture(scope="module")
def scratch():
    raw = settings.effective_database_url
    name = f"rolemig_{uuid.uuid4().hex[:8]}"
    admin = create_engine(raw, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
    except Exception as exc:  # no CREATEDB: nothing to test here
        admin.dispose()
        pytest.skip(f"cannot create a scratch database: {exc.__class__.__name__}")
    # Only the database name changes; the rest of the URL (a socket host in a
    # query string, say) stays byte for byte what the test database uses.
    parts = urlsplit(raw)
    url = urlunsplit(parts._replace(path=f"/{name}"))
    try:
        yield url
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic(url, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": url}
    done = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr[-2000:]


def _rows(url, sql: str):
    engine = create_engine(url)
    try:
        with engine.connect() as c:
            return [tuple(r) for r in c.execute(text(sql))]
    finally:
        engine.dispose()


def test_roles_map_forward_and_back_without_losing_anyone(scratch):
    _alembic(scratch, "upgrade", BEFORE)
    engine = create_engine(scratch)
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO users (email, role, member_type, is_super_admin, username) VALUES
              ('owner@example.test', 'moderator', 'moderator', true,  'owner'),
              ('staff@example.test', 'moderator', 'moderator', false, 'staff'),
              ('member@example.test', 'user', 'shopper', false, 'member'),
              ('store@example.test', 'seller', 'seller', false, 'store')"""))
    engine.dispose()

    _alembic(scratch, "upgrade", "head")
    assert _rows(scratch, "SELECT username, role::text, member_type::text FROM users "
                          "ORDER BY username") == [
        ("member", "user", "shopper"), ("owner", "super_admin", "administrator"),
        ("staff", "administrator", "administrator"), ("store", "seller", "seller")]
    assert _rows(scratch, "SELECT enum_range(NULL::member_role)::text")[0][0] == \
        "{user,seller,administrator,super_admin}"
    assert _rows(scratch, "SELECT count(*) FROM information_schema.columns "
                          "WHERE table_name = 'users' AND column_name = 'is_super_admin'") \
        == [(0,)]

    _alembic(scratch, "downgrade", BEFORE)
    assert _rows(scratch, "SELECT username, role::text, member_type::text, is_super_admin "
                          "FROM users ORDER BY username") == [
        ("member", "user", "shopper", False), ("owner", "moderator", "moderator", True),
        ("staff", "moderator", "moderator", False), ("store", "seller", "seller", False)]

    _alembic(scratch, "upgrade", "head")
    assert _rows(scratch, "SELECT username, role::text FROM users ORDER BY username") == [
        ("member", "user"), ("owner", "super_admin"), ("staff", "administrator"),
        ("store", "seller")]

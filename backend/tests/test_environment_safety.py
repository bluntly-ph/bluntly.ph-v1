"""A non-production app must never start on the production database.

Found 2026-09-29: every Vercel Preview (APP_ENV=staging) carried the production
project's Supabase variables, so branch code under review ran on live data.
`env_guard.check_environment_safety` now refuses that at boot, and refuses any
configuration whose Supabase and Postgres targets name different projects.

Project refs are public identifiers (they are in every storage URL the site
serves). Every password below is fake, and no message may contain one.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.env_guard import (
    MIXED_TARGETS,
    PRODUCTION_PROJECT_REF,
    TEST_PROJECT_REF,
    UNSAFE_PRODUCTION_TARGET,
    UnsafeEnvironmentError,
    check_environment_safety,
    project_ref_of,
)

PROD, TEST = PRODUCTION_PROJECT_REF, TEST_PROJECT_REF
SECRET = "Sup3r-Secret-Pa55w0rd"


def supabase(ref: str) -> dict[str, str]:
    """A full, consistent Supabase configuration for one project."""
    return {
        "supabase_url": f"https://{ref}.supabase.co",
        "supabase_jwks_url": f"https://{ref}.supabase.co/auth/v1/.well-known/jwks.json",
        "supabase_connection_string":
            f"postgresql://postgres:{SECRET}@db.{ref}.supabase.co:5432/postgres",
        "supabase_connection_string_session_pooler":
            f"postgresql://postgres.{ref}:{SECRET}@aws-0-ap-southeast-1.pooler.supabase.com"
            ":5432/postgres",
        "supabase_connection_string_transaction_pooler":
            f"postgresql://postgres.{ref}:{SECRET}@aws-0-ap-southeast-1.pooler.supabase.com"
            ":6543/postgres",
        "supabase_publishable_key": "sb_publishable_not_a_real_key",
        "supabase_secret_key": "sb_secret_not_a_real_key",
        "database_url": "postgresql+psycopg://bluntly:bluntly@localhost:5432/bluntly",
    }


LOCAL = {"database_url": "postgresql+psycopg://bluntly:bluntly@localhost:5432/bluntly"}


def refused(app_env: str, values: dict[str, str]) -> str:
    with pytest.raises(UnsafeEnvironmentError) as caught:
        check_environment_safety(app_env, values)
    message = str(caught.value)
    assert SECRET not in message and "sb_secret" not in message and "@" not in message
    return message


# --- the ten required cases -------------------------------------------------

def test_1_production_app_on_production_is_allowed():
    assert set(check_environment_safety("production", supabase(PROD)).values()) == {PROD}


@pytest.mark.parametrize("app_env", ["preview", "test", "staging"])
def test_2_3_4_non_production_apps_on_test_are_allowed(app_env):
    assert set(check_environment_safety(app_env, supabase(TEST)).values()) == {TEST}


@pytest.mark.parametrize("app_env", ["preview", "staging", "test"])
def test_5_6_7_non_production_apps_on_production_are_refused(app_env):
    message = refused(app_env, supabase(PROD))
    assert UNSAFE_PRODUCTION_TARGET in message
    assert f"APP_ENV={app_env}" in message


def test_8_test_supabase_with_production_database_is_refused():
    values = supabase(TEST)
    values["supabase_connection_string_session_pooler"] = supabase(PROD)[
        "supabase_connection_string_session_pooler"]
    message = refused("staging", values)
    assert MIXED_TARGETS in message
    assert "SUPABASE_CONNECTION_STRING_SESSION_POOLER -> PRODUCTION" in message
    assert "SUPABASE_JWKS_URL -> TEST" in message


def test_9_production_supabase_with_test_database_is_refused_even_in_production():
    values = supabase(PROD)
    values["supabase_connection_string"] = supabase(TEST)["supabase_connection_string"]
    message = refused("production", values)
    assert MIXED_TARGETS in message
    assert "SUPABASE_CONNECTION_STRING -> TEST" in message


def test_10_local_development_on_a_local_database_is_allowed():
    assert check_environment_safety("local", LOCAL) == {}
    assert check_environment_safety("", LOCAL) == {}


# --- the edges that make those hold -----------------------------------------

def test_auth_on_test_with_database_on_production_is_refused():
    values = supabase(TEST)
    for key in ("supabase_connection_string", "supabase_connection_string_session_pooler",
                "supabase_connection_string_transaction_pooler"):
        values[key] = supabase(PROD)[key]
    assert MIXED_TARGETS in refused("staging", values)


def test_local_database_with_production_storage_is_refused_outside_production():
    # A developer's local database, but SUPABASE_URL (storage, auth) on
    # production: uploads would land in the live bucket.
    values = dict(LOCAL, supabase_url=f"https://{PROD}.supabase.co")
    assert UNSAFE_PRODUCTION_TARGET in refused("local", values)


def test_an_unset_app_env_counts_as_non_production():
    assert "APP_ENV=unset" in refused("", supabase(PROD))


@pytest.mark.parametrize(("value", "ref"), [
    (f"https://{TEST}.supabase.co", TEST),
    (f"https://{PROD}.supabase.co/auth/v1/.well-known/jwks.json", PROD),
    (f"postgresql://postgres:{SECRET}@db.{PROD}.supabase.co:5432/postgres", PROD),
    (f"postgresql+psycopg://postgres.{TEST}:{SECRET}@aws-0-ap-southeast-1.pooler.supabase.com"
     ":5432/postgres", TEST),
    (f"host=db.{PROD}.supabase.co port=5432 user=postgres password={SECRET}", PROD),
    (f"host=aws-0-ap-southeast-1.pooler.supabase.com user=postgres.{TEST} "
     f"password={SECRET}", TEST),
    ("postgresql+psycopg://bluntly:bluntly@localhost:5432/bluntly", None),
    ("sb_secret_not_a_real_key", None),
    ("", None),
])
def test_project_ref_of_reads_every_form(value, ref):
    assert project_ref_of(value) == ref


def test_a_password_cannot_move_the_pooler_to_another_project():
    # The pooler's user name decides the project; a password fragment that is
    # not a full host does not.
    value = (f"postgresql://postgres.{TEST}:db.{PROD}x@aws-0-ap-southeast-1.pooler"
             ".supabase.com:5432/postgres")
    assert project_ref_of(value) == TEST
    # A password that IS a full production host is read as production: the
    # check then refuses the mix, which is the safe way to be wrong.
    tricky = (f"postgresql://postgres.{TEST}:db.{PROD}.supabase.co@aws-0-ap-southeast-1"
              ".pooler.supabase.com:5432/postgres")
    values = supabase(TEST)
    values["supabase_connection_string_session_pooler"] = tricky
    message = refused("staging", values)
    assert "supabase.co" not in message and "postgres." not in message


def test_a_legacy_jwt_key_names_its_project_by_its_ref_claim():
    def jwt(ref: str) -> str:
        body = base64.urlsafe_b64encode(json.dumps({"ref": ref, "role": "anon"}).encode())
        return f"eyJhbGciOiJIUzI1NiJ9.{body.decode().rstrip('=')}.signature"

    assert project_ref_of(jwt(PROD)) == PROD
    values = supabase(TEST)
    values["supabase_publishable_key"] = jwt(PROD)
    message = refused("staging", values)
    assert "SUPABASE_PUBLISHABLE_KEY -> PRODUCTION" in message


# --- the real boot ----------------------------------------------------------

BACKEND = Path(__file__).resolve().parents[1]


def boot(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Import the app in a clean process, the way a deployment starts it."""
    clean = {k: v for k, v in os.environ.items()
             if not k.startswith(("SUPABASE_", "DATABASE_URL", "APP_ENV", "USE_SUPABASE"))}
    clean.update(env)
    return subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND,
                          env=clean, capture_output=True, text=True, timeout=120)


def test_the_app_refuses_to_start_as_a_preview_on_production():
    result = boot({"APP_ENV": "staging", "SUPABASE_URL": f"https://{PROD}.supabase.co",
                   "SUPABASE_CONNECTION_STRING_SESSION_POOLER":
                       supabase(PROD)["supabase_connection_string_session_pooler"]})
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert UNSAFE_PRODUCTION_TARGET in output
    assert SECRET not in output


def test_the_app_starts_as_a_preview_on_test():
    result = boot({"APP_ENV": "staging", "SUPABASE_URL": f"https://{TEST}.supabase.co",
                   "SUPABASE_CONNECTION_STRING_SESSION_POOLER":
                       supabase(TEST)["supabase_connection_string_session_pooler"]})
    assert result.returncode == 0, result.stderr[-2000:]

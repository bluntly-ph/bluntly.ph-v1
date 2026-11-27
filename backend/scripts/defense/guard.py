"""Where the defense scripts may run: the TEST project or a local database. Nowhere else.

The defense dataset is fabricated on purpose - believable people, reviews and
money - so it must never reach the live site, where it would be exactly the
kind of fake review the platform exists to stop. `env_guard` already refuses
production; this narrows further to the two targets the scripts are for, so an
unrecognised database (a new project, a teammate's copy) is refused too.
"""

from __future__ import annotations

import sys
from urllib.parse import urlsplit

#: bluntly-ph-test. Public identifier, not a secret (docs/ENVIRONMENTS.md).
TEST_PROJECT_REF = "miysywhcdqkoniaibglx"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}


class DefenseTargetError(RuntimeError):
    pass


def classify_target() -> str:
    """'test', 'local', or raise. Reads the connection the process will open."""
    from app.core import env_guard
    from app.core.config import settings

    signals = env_guard.production_signals()
    if signals:
        raise DefenseTargetError("refusing production: " + "; ".join(signals))
    if not env_guard.is_test_target():
        raise DefenseTargetError(
            f"the target has not declared itself a test environment "
            f"(set {env_guard.TEST_ENV_MARKER}=1)")
    url = (settings.effective_database_url or "").lower()
    host = (urlsplit(url).hostname or "").lower() if "://" in url else ""
    if TEST_PROJECT_REF in url or TEST_PROJECT_REF in (settings.supabase_url or "").lower():
        return "test"
    if host in _LOCAL_HOSTS:
        return "local"
    raise DefenseTargetError(
        f"unrecognised database ({env_guard.describe_target()}); the defense scripts "
        "run only against bluntly-ph-test or a local Postgres")


def require_defense_target(action: str) -> str:
    """Print the target and return its kind, or exit non-zero without writing."""
    from app.core import env_guard

    try:
        kind = classify_target()
    except DefenseTargetError as exc:
        print(f"[defense] {action}: REFUSED - {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    print(f"[defense] {action} -> {kind} | {env_guard.describe_target()}")
    return kind

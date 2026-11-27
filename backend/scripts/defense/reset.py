"""Clear the defense database back to an empty site, keeping accounts that matter.

TEST is shared with the canonical CI job, which leaves thousands of fixture
accounts, products and reviews behind on every run (see ci.yml). A panel
cannot be shown that, and deleting fixture users alone would not help:
`reviews.author_id` is ON DELETE SET NULL, so their reviews would stay behind
as "deleted account" posts. So this clears content wholesale and keeps only:

  * the schema and alembic_version;
  * reference tables: badges, membership_tiers, cron_credentials, cron_runs;
  * real accounts - any email that is not a known fixture or defense pattern
    (the owner's own logins on TEST are kept, content-free);
  * the defense personas' accounts, so a presenter's signed-in session
    survives a reset (their content is cleared and re-seeded).

Everything else in `public` is emptied, and on TEST the public photo buckets
too, so repeated rehearsals do not grow storage without bound.

Dry run by default. Refuses anything but bluntly-ph-test or a local database.

Usage:
    python -m scripts.defense.reset            # what would be cleared
    python -m scripts.defense.reset --apply    # clear it
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from scripts.defense.guard import require_defense_target

#: Tables whose rows are configuration, not content.
KEEP_TABLES = frozenset({
    "alembic_version", "badges", "membership_tiers", "cron_credentials", "cron_runs",
    "users",  # filtered below, never truncated
})

#: Accounts that are fixtures or defense community members (recreated by the
#: seed). Anything else is a real account and is kept.
#:   t_<hex>@example.com and e2e_*@example.com - the test suites;
#:   *@bluntly.local - early seed scripts; *@example.ph - a QA persona;
#:   *@showcase.bluntly.ph - the showcase seed; *@demo.bluntly.ph - this dataset.
_DISPOSABLE = (
    r"@example\.com$", r"@bluntly\.local$", r"@example\.ph$",
    r"@showcase\.bluntly\.ph$", r"@demo\.bluntly\.ph$",
)

_BUCKETS = ("review-photos", "product-images", "avatars")


def disposable_sql() -> str:
    return " OR ".join(f"email ~* '{pattern}'" for pattern in _DISPOSABLE)


def content_tables(db) -> list[str]:
    rows = db.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    )).scalars().all()
    return [t for t in rows if t not in KEEP_TABLES]


def _kept_tables_safe(db, truncate: list[str]) -> list[str]:
    """Kept tables that reference a truncated one (TRUNCATE CASCADE would empty them)."""
    rows = db.execute(text("""
        SELECT DISTINCT src.relname, dst.relname
          FROM pg_constraint c
          JOIN pg_class src ON src.oid = c.conrelid
          JOIN pg_class dst ON dst.oid = c.confrelid
          JOIN pg_namespace n ON n.oid = src.relnamespace
         WHERE c.contype = 'f' AND n.nspname = 'public'
    """)).all()
    return sorted({src for src, dst in rows if src in KEEP_TABLES and dst in truncate})


def plan(db) -> dict:
    tables = content_tables(db)
    counts = {t: db.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in tables}
    users_total = db.execute(text("SELECT count(*) FROM users")).scalar_one()
    disposable = db.execute(
        text(f"SELECT count(*) FROM users WHERE {disposable_sql()}")).scalar_one()
    kept = db.execute(text(
        f"SELECT email FROM users WHERE NOT ({disposable_sql()}) ORDER BY email")).scalars().all()
    return {"tables": counts, "users_total": users_total, "users_deleted": disposable,
            "users_kept": kept, "blocked_by": _kept_tables_safe(db, tables)}


def _purge_buckets(apply: bool) -> dict[str, int]:
    """Remove every object in the public photo buckets (TEST only)."""
    from app.core.supabase_client import get_service_client

    client = get_service_client()
    removed: dict[str, int] = {}
    for bucket in _BUCKETS:
        store = client.storage.from_(bucket)
        paths: list[str] = []
        folders = [""]
        while folders:
            prefix = folders.pop()
            offset = 0
            while True:
                page = store.list(prefix, {"limit": 1000, "offset": offset}) or []
                for entry in page:
                    name = f"{prefix}/{entry['name']}" if prefix else entry["name"]
                    # Folders come back without an id.
                    if entry.get("id") is None:
                        folders.append(name)
                    else:
                        paths.append(name)
                if len(page) < 1000:
                    break
                offset += 1000
        if apply:
            for i in range(0, len(paths), 500):
                store.remove(paths[i:i + 500])
        removed[bucket] = len(paths)
    return removed


def reset(apply: bool, *, kind: str) -> dict:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        before = plan(db)
        if before["blocked_by"]:
            raise SystemExit(f"refusing: kept tables {before['blocked_by']} reference content "
                             "tables and would be emptied by TRUNCATE CASCADE")
        if apply:
            tables = list(before["tables"])
            if tables:
                db.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables)
                                + " RESTART IDENTITY CASCADE"))
            # The persona Super Admin goes with the other disposable accounts
            # and the seed recreates it: this transaction, and only this one,
            # may pass through zero Super Admins (migration 0067's guard).
            db.execute(text("SET LOCAL bluntly.allow_no_super_admin = 'on'"))
            db.execute(text(f"DELETE FROM users WHERE {disposable_sql()}"))
            # Kept accounts start from a clean slate: no money, no trust history.
            db.execute(text("""
                UPDATE users SET wallet_balance = 0, trust_stage = 0, reputation_score = 0,
                       is_under_investigation = false, is_claimed_seller = false,
                       is_on_probation = false, is_suspended = false
            """))
            db.commit()
    finally:
        db.close()
    buckets = {}
    if kind == "test":
        buckets = _purge_buckets(apply)
    before["buckets"] = buckets
    return before


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="clear (default: dry run)")
    args = parser.parse_args(argv)
    kind = require_defense_target("reset" + ("" if args.apply else " (dry run)"))
    result = reset(args.apply, kind=kind)
    verb = "cleared" if args.apply else "would clear"
    nonempty = {t: n for t, n in result["tables"].items() if n}
    print(f"[defense] {verb} {sum(nonempty.values())} rows in {len(nonempty)} tables")
    for table, count in sorted(nonempty.items(), key=lambda kv: -kv[1]):
        print(f"    {table:34s} {count}")
    print(f"[defense] users: {result['users_total']} total, {verb} {result['users_deleted']}, "
          f"keeping {len(result['users_kept'])}")
    for bucket, count in result["buckets"].items():
        print(f"[defense] storage {bucket}: {verb} {count} objects")
    return 0


if __name__ == "__main__":
    sys.exit(main())

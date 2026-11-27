"""Row level security on every table, as the schema has always claimed.

Revision ID: 0087_rls_every_table
Revises: 0086_storage_buckets
Create Date: 2026-10-04

The rule since 0002 is "RLS on, nothing granted to anon / authenticated": the
application connects as `postgres`, which owns every table and is not subject
to RLS, so nothing it does changes, while a leaked anon key reads nothing.

Twelve tables were created without it (Supabase's security advisor, production,
2026-10-04: "11 table(s) have Row Level Security disabled"; email_otps had been
switched on by hand on production only, so a fresh database had twelve). None is
readable by the API roles, so nothing leaked - but table privileges were the
only layer between them and PostgREST, and supabase_admin's default privileges
open every table made through the dashboard to the API roles
(scripts/check_invariants.py). This makes the second layer real for them too.

ENABLE is idempotent (a table already on stays on). The REVOKEs are no-ops
today and keep the rule true. check_invariants now reports any table with RLS
off, so the next table created without it is caught.

Downgrade leaves RLS on: no older code needs it off (the owner bypasses it), and
turning it off is a security regression no rollback should make silently.
"""

from __future__ import annotations

from alembic import op

revision = "0087_rls_every_table"
down_revision = "0086_storage_buckets"
branch_labels = None
depends_on = None

TABLES = (
    "cron_credentials",
    "cron_runs",
    "email_otps",
    "notifications",
    "rate_limit_counters",
    "request_geo_buckets",
    "review_first_vote_geo_buckets",
    "review_reading_sessions",
    "review_view_buckets",
    "seller_claims",
    "seller_reviews",
    "sellers",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    revokes = "\n".join(f"    REVOKE ALL ON {t} FROM anon, authenticated;" for t in TABLES)
    op.execute(f"""
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon')
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
{revokes}
  END IF;
END $$;""")


def downgrade() -> None:
    pass

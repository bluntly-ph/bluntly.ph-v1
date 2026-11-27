"""Pin the search_path of the two trigger functions on `users`.

Revision ID: 0088_function_search_path
Revises: 0087_rls_every_table
Create Date: 2026-10-04

Supabase's security advisor (production and TEST, 2026-10-04, WARN
function_search_path_mutable): users_staff_ref_is_immutable (0038) and
users_keep_one_super_admin (0067) resolve `users` through the caller's
search_path, so a role that can create objects in a schema earlier on its path
could have the guard read a table of its own. Pinning it to `public, pg_temp`
is what they already assume; their bodies are unchanged.

Downgrade resets the setting (the functions behave exactly as before).
"""

from __future__ import annotations

from alembic import op

revision = "0088_function_search_path"
down_revision = "0087_rls_every_table"
branch_labels = None
depends_on = None

FUNCTIONS = ("users_staff_ref_is_immutable()", "users_keep_one_super_admin()")


def upgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"ALTER FUNCTION {fn} SET search_path = public, pg_temp")


def downgrade() -> None:
    for fn in FUNCTIONS:
        op.execute(f"ALTER FUNCTION {fn} RESET search_path")

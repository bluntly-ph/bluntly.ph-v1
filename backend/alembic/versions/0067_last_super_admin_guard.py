"""At least one active Super Admin always remains (owner decision D).

Revision ID: 0067_last_super_admin_guard
Revises: 0066_review_special_route
Create Date: 2026-09-28

The API enforces this in app/services/staff_roles.py. This trigger enforces it
for everything else — a script, a SQL console, a future endpoint that forgets:
an UPDATE that demotes or suspends, or a DELETE that removes, the last active
`super_admin` is refused with `last_super_admin`.

Race-safe: the check takes a transaction-scoped advisory lock before counting,
so two statements removing the last two Super Admins at the same moment
serialise, and the second one's count (a fresh snapshot, READ COMMITTED) sees
the first.

Only a transition AWAY from an active Super Admin is checked, so a database
with no Super Admin yet (a fresh TEST project, before bootstrap) is not
blocked. A reset that wipes every account on purpose says so for its own
transaction only: `SET LOCAL bluntly.allow_no_super_admin = 'on'` (the defense
reset and the e2e fixtures' teardown). Anyone able to run that could drop the
trigger anyway; the point is that nobody does it by accident.
"""

from __future__ import annotations

from alembic import op

revision = "0067_last_super_admin_guard"
down_revision = "0066_review_special_route"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION users_keep_one_super_admin() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.role::text <> 'super_admin' OR COALESCE(OLD.is_suspended, false) THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.role::text = 'super_admin'
                    AND NOT COALESCE(NEW.is_suspended, false) THEN
                RETURN NEW;
            END IF;
            IF COALESCE(current_setting('bluntly.allow_no_super_admin', true), '') = 'on' THEN
                RETURN COALESCE(NEW, OLD);
            END IF;
            PERFORM pg_advisory_xact_lock(hashtext('bluntly.users.last_super_admin'));
            IF NOT EXISTS (SELECT 1 FROM users
                           WHERE role::text = 'super_admin'
                             AND NOT COALESCE(is_suspended, false)
                             AND id <> OLD.id) THEN
                RAISE EXCEPTION 'last_super_admin: at least one active Super Admin must remain'
                    USING ERRCODE = 'P0001';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER users_keep_one_super_admin
        BEFORE UPDATE OF role, is_suspended OR DELETE ON users
        FOR EACH ROW EXECUTE FUNCTION users_keep_one_super_admin()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS users_keep_one_super_admin ON users")
    op.execute("DROP FUNCTION IF EXISTS users_keep_one_super_admin()")

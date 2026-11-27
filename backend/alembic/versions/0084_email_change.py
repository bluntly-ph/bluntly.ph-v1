"""A verified email change, and a way to end every other session.

Revision ID: 0084_email_change
Revises: 0083_notification_prefs
Create Date: 2026-10-04

Owner decision 2026-10-04: a member (store owners first, Figma Overlay/Store/Account
8232:25342) can change the address they sign in with, but only after proving both
ends: a code sent to the CURRENT address (it is really them) and one sent to the NEW
address (they own it). Codes are Argon2id hashes, never stored in plaintext.

* email_change_requests: one row per attempt. Its own table, NOT email_otps: a
  sign-in or sign-up code is looked up by address, so a change code parked under
  the new address could otherwise be consumed by a sign-in, or even create a second
  account for it.
* users.sessions_valid_after (nullable): a token issued before it is refused. An
  email change sets it, so every other signed-in browser has to sign in again.

Hidden from PostgREST like every table (RLS on, nothing granted to the API roles).
Downgrade drops the table and the column (pending requests are lost; harmless).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0084_email_change"
down_revision = "0083_notification_prefs"
branch_labels = None
depends_on = None

TABLE = "email_change_requests"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("new_email", sa.String(320), nullable=False),
        sa.Column("current_code_hash", sa.String(255), nullable=False),
        sa.Column("new_code_hash", sa.String(255), nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_email_change_requests_user", TABLE, ["user_id", "created_at"])
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON {TABLE} FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON {TABLE} FROM authenticated;
          END IF;
        END $$;""")
    op.add_column("users", sa.Column("sessions_valid_after", sa.DateTime(timezone=True),
                                     nullable=True))


def downgrade() -> None:
    op.drop_column("users", "sessions_valid_after")
    op.drop_index("ix_email_change_requests_user", table_name=TABLE)
    op.drop_table(TABLE)

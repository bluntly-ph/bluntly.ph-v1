"""The email outbox: notification emails and the weekly summary, sent reliably.

Revision ID: 0085_email_outbox
Revises: 0084_email_change
Create Date: 2026-10-04

Owner request 2026-10-04 (Resend infrastructure, notification emails, weekly
summary). A message is queued in `email_outbox` in the SAME transaction as the
event that causes it, so a rolled-back decision never emails anyone; the hourly
`send_emails` task (internal_cron) sends what is pending through Resend, retries a
failure with backoff, and gives up after a few attempts. Each row's id is Resend's
Idempotency-Key, so a retried send never becomes a second email. `dedupe_key`
(unique when set) stops a job that runs twice from queuing the same weekly summary
twice.

Personal data: the recipient address and the message. Sent and abandoned rows are
deleted 30 days after they settle (the same task), so the table never becomes an
archive of everyone's mail.

Hidden from PostgREST like every table (RLS on, nothing granted to the API roles).
Downgrade drops the table (unsent mail is lost: export first if that matters).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0085_email_outbox"
down_revision = "0084_email_change"
branch_labels = None
depends_on = None

TABLE = "email_outbox"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("text_body", sa.Text, nullable=False),
        sa.Column("html_body", sa.Text),
        sa.Column("headers", postgresql.JSONB),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(200)),
        sa.Column("dedupe_key", sa.String(160)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed', 'skipped')",
                           name="ck_email_outbox_status"),
    )
    op.create_index("ix_email_outbox_due", TABLE, ["status", "next_attempt_at"])
    op.create_index("uq_email_outbox_dedupe", TABLE, ["dedupe_key"], unique=True,
                    postgresql_where=sa.text("dedupe_key IS NOT NULL"))
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


def downgrade() -> None:
    op.drop_index("uq_email_outbox_dedupe", table_name=TABLE)
    op.drop_index("ix_email_outbox_due", table_name=TABLE)
    op.drop_table(TABLE)

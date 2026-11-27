"""Message edit, unsend and delete-for-me (MQA-011).

Revision ID: 0093_message_edits
Revises: 0092_support_waiting
Create Date: 2026-10-05

A chat message could not be corrected or taken back. Its sender may now edit
or unsend it for a short while after sending (the window is in
conversation_service), and anyone in the thread may hide a message from their
own view ("Delete for me").

* conversation_messages.edited_at / unsent_at: when the sender last edited it,
  and when they unsent it (its words and file are then gone from the thread).
* conversation_message_revisions: what a message said before each edit or
  unsend, and who changed it - an audit trail read by no screen, kept because
  a claim's or an appeal's thread is evidence.
* conversation_message_hides: one row per (message, person) who deleted it for
  themselves.

Additive only. Both tables are hidden from PostgREST like every table (RLS on,
nothing granted to the API roles). Downgrade drops the tables and columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0093_message_edits"
down_revision = "0092_support_waiting"
branch_labels = None
depends_on = None

REVISIONS = "conversation_message_revisions"
HIDES = "conversation_message_hides"


def _private(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON {table} FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON {table} FROM authenticated;
          END IF;
        END $$;""")


def upgrade() -> None:
    op.add_column("conversation_messages", sa.Column("edited_at", sa.DateTime(timezone=True)))
    op.add_column("conversation_messages", sa.Column("unsent_at", sa.DateTime(timezone=True)))
    op.create_table(
        REVISIONS,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("attachment_name", sa.String(160)),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("action IN ('edit', 'unsend')", name="ck_message_revision_action"),
    )
    op.create_index("ix_message_revisions_message", REVISIONS, ["message_id", "created_at"])
    _private(REVISIONS)
    op.create_table(
        HIDES,
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conversation_messages.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_message_hides_user", HIDES, ["user_id"])
    _private(HIDES)


def downgrade() -> None:
    op.drop_index("ix_message_hides_user", table_name=HIDES)
    op.drop_table(HIDES)
    op.drop_index("ix_message_revisions_message", table_name=REVISIONS)
    op.drop_table(REVISIONS)
    op.drop_column("conversation_messages", "unsent_at")
    op.drop_column("conversation_messages", "edited_at")

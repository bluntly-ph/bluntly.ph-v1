"""Store change requests: a store owner asks, a moderator approves or rejects.

Revision ID: 0091_store_change_requests
Revises: 0090_appeal_kind
Create Date: 2026-10-05

MQA-017/018/019/025: a change to a store's name, link or registration arrived
as free text in a message; nothing tied a moderator's answer to the store, so a
ticket could be closed while the store still showed the old link. Each change is
now a row (field, value when asked, value asked for, status, who decided) and
approving it applies it to the store. One partial unique index keeps one open
request per store and field.

Additive only: a new table, its indexes and constraints. Hidden from PostgREST
like every table (RLS on, nothing granted to the API roles). Downgrade drops it
(the requests are lost; the stores keep whatever was applied).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0091_store_change_requests"
down_revision = "0090_appeal_kind"
branch_labels = None
depends_on = None

TABLE = "store_change_requests"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("seller_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("conversations.id", ondelete="SET NULL")),
        sa.Column("field", sa.String(24), nullable=False),
        sa.Column("current_value", sa.Text),
        sa.Column("requested_value", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("field IN ('display_name', 'store_url', 'registration')",
                           name="ck_store_change_field"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')",
                           name="ck_store_change_status"),
    )
    op.create_index("ix_store_change_seller", TABLE, ["seller_id", "created_at"])
    op.create_index("ix_store_change_conversation", TABLE, ["conversation_id"])
    op.create_index("uq_store_change_pending", TABLE, ["seller_id", "field"], unique=True,
                    postgresql_where=sa.text("status = 'pending'"))
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
    op.drop_index("uq_store_change_pending", table_name=TABLE)
    op.drop_index("ix_store_change_conversation", table_name=TABLE)
    op.drop_index("ix_store_change_seller", table_name=TABLE)
    op.drop_table(TABLE)

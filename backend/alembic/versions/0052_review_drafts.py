"""Review drafts kept with the account, not the device (QA-003).

Revision ID: 0052_review_drafts
Revises: 0051_product_median_column
Create Date: 2026-09-24

Purely additive: one new table. The running build never reads it, so migrating
before deploying is safe, and the downgrade drops only this table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0052_review_drafts"
down_revision = "0051_product_median_column"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slot", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("saved_at_ms", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "slot", name="uq_review_draft_slot"),
    )
    op.create_index("ix_review_drafts_user_id", "review_drafts", ["user_id"])

    # PostgREST must not see it (0029's rule, as 0050 applies to its tables).
    op.execute("ALTER TABLE review_drafts ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON review_drafts FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON review_drafts FROM authenticated;
          END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_index("ix_review_drafts_user_id", table_name="review_drafts")
    op.drop_table("review_drafts")

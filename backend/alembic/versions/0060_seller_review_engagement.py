"""Seller reviews get votes and replies (QA-043, owner decision 2026-09-28).

Revision ID: 0060_seller_review_engagement
Revises: 0059_qa_sandbox_earnings
Create Date: 2026-09-28

* `seller_review_votes` — one up or down vote per (seller review, member).
  Helpfulness only: it moves no rating, no trust and no money.
* `seller_review_replies` — one flat thread of member replies under a seller
  review; the store keeps its single public response on the review itself.

Both are hidden from PostgREST (RLS on, no policy, nothing granted to the API
roles), as every new table is. Additive only; the downgrade drops exactly what
this adds.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "0060_seller_review_engagement"
down_revision = "0059_qa_sandbox_earnings"
branch_labels = None
depends_on = None


def _hide_from_postgrest(table: str) -> None:
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
    op.create_table(
        "seller_review_votes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("seller_review_id", UUID(as_uuid=True),
                  sa.ForeignKey("seller_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", ENUM("up", "down", name="vote_direction", create_type=False),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.UniqueConstraint("seller_review_id", "user_id", name="uq_seller_review_vote_once"),
    )
    op.create_index("ix_seller_review_votes_review", "seller_review_votes", ["seller_review_id"])
    op.create_table(
        "seller_review_replies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("seller_review_id", UUID(as_uuid=True),
                  sa.ForeignKey("seller_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_removed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    op.create_index("ix_seller_review_replies_review", "seller_review_replies",
                    ["seller_review_id", "created_at"])
    for table in ("seller_review_votes", "seller_review_replies"):
        _hide_from_postgrest(table)


def downgrade() -> None:
    op.drop_index("ix_seller_review_replies_review", table_name="seller_review_replies")
    op.drop_table("seller_review_replies")
    op.drop_index("ix_seller_review_votes_review", table_name="seller_review_votes")
    op.drop_table("seller_review_votes")

"""Seller support requests (owner decision 2026-09-28).

Revision ID: 0063_seller_support_requests
Revises: 0062_support_request_action
Create Date: 2026-09-28

A claimed store's owner contacts the administrators about their store: report
a review, ask for a takedown investigation, dispute a suspected fake, a claim
or listing concern, or general support. It is a REQUEST — the seller gains no
power over content; an administrator decides what, if anything, follows.

Why a table of its own rather than an existing one:
* `moderation_logs` reports are about a piece of content, filed by anyone,
  and their filer is never shown the outcome;
* `seller_review_appeals` is one specific flow on one seller review;
* a support request is a two-way conversation with a status the seller
  follows, about anything touching their store.

`internal_note` is staff-only and never returned to the seller. Hidden from
PostgREST like every table (RLS on, no policy, nothing granted to the API
roles). Additive; the downgrade drops exactly what this adds.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, UUID

revision = "0063_seller_support_requests"
down_revision = "0062_support_request_action"
branch_labels = None
depends_on = None

STATUS = ENUM("open", "in_review", "resolved", "rejected", name="support_request_status",
              create_type=False)
CATEGORY = ENUM("report_review", "takedown_investigation", "fake_review_dispute",
                "account_claim", "listing_product", "general",
                name="support_request_category", create_type=False)


def upgrade() -> None:
    STATUS.create(op.get_bind(), checkfirst=True)
    CATEGORY.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "seller_support_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("reference", sa.String(24), nullable=False, unique=True),
        sa.Column("seller_id", UUID(as_uuid=True),
                  sa.ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("category", CATEGORY, nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_seller_review_id", UUID(as_uuid=True),
                  sa.ForeignKey("seller_reviews.id", ondelete="SET NULL")),
        sa.Column("related_review_id", UUID(as_uuid=True),
                  sa.ForeignKey("reviews.id", ondelete="SET NULL")),
        sa.Column("related_product_id", UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="SET NULL")),
        sa.Column("status", STATUS, nullable=False, server_default="open"),
        sa.Column("assigned_admin_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("admin_response", sa.Text()),
        sa.Column("admin_responded_at", sa.DateTime(timezone=True)),
        sa.Column("internal_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_support_requests_seller", "seller_support_requests",
                    ["seller_id", "created_at"])
    op.create_index("ix_support_requests_status", "seller_support_requests",
                    ["status", "created_at"])
    op.execute("ALTER TABLE seller_support_requests ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON seller_support_requests FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON seller_support_requests FROM authenticated;
          END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_index("ix_support_requests_status", table_name="seller_support_requests")
    op.drop_index("ix_support_requests_seller", table_name="seller_support_requests")
    op.drop_table("seller_support_requests")
    CATEGORY.drop(op.get_bind(), checkfirst=True)
    STATUS.drop(op.get_bind(), checkfirst=True)

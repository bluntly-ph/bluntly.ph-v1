"""Store ↔ product links (Figma Screen/Seller/Products 8204:22648, Waiting
8214:23301, All 8214:23647, Overlay/Store/LinkProduct 8204:23173,
Confirm/Store/LinkProduct 8213:23439, Confirm/Store/CancelLink 8213:23484).

Revision ID: 0077_store_products
Revises: 0076_conversations
Create Date: 2026-10-04

A claimed store's owner asks to link product pages their store sells; an
Administrator approves or rejects each request ("A moderator checks each
link"). An approved link shows the product's figures in the Seller console. The
owner can never create or edit a product page through this (Business Rules §9:
claiming grants responding, nothing over content).

One row per request: pending → approved | rejected, or cancelled by the owner.
At most one live (pending or approved) row per store and product (partial
unique index); a rejected or cancelled pair can be asked again.

Adds 'store_product' to moderation_action (decisions are audited). Hidden from
PostgREST like every table. Additive; the downgrade drops what this adds (the
enum value stays: PostgreSQL cannot drop one).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID

from alembic import op

revision = "0077_store_products"
down_revision = "0076_conversations"
branch_labels = None
depends_on = None

STATUS = ENUM("pending", "approved", "rejected", "cancelled", name="store_product_status",
              create_type=False)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'store_product'")
    STATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "store_products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("seller_id", UUID(as_uuid=True),
                  sa.ForeignKey("sellers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", STATUS, nullable=False, server_default="pending"),
        sa.Column("requested_by_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_by_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
    )
    op.create_index("ix_store_products_seller", "store_products", ["seller_id", "status"])
    op.create_index("ix_store_products_status", "store_products", ["status", "created_at"])
    op.create_index("uq_store_products_live", "store_products", ["seller_id", "product_id"],
                    unique=True, postgresql_where=sa.text("status IN ('pending', 'approved')"))
    op.execute("ALTER TABLE store_products ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON store_products FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON store_products FROM authenticated;
          END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_index("uq_store_products_live", table_name="store_products")
    op.drop_index("ix_store_products_status", table_name="store_products")
    op.drop_index("ix_store_products_seller", table_name="store_products")
    op.drop_table("store_products")
    STATUS.drop(op.get_bind(), checkfirst=True)

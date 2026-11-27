"""Affiliate report rows keep the item detail the commission breakdown reads (owner, 2026-10-19).

Revision ID: 0096_affiliate_item_detail
Revises: 0095_trust_score_override
Create Date: 2026-10-19

The reviewer's "Commission breakdown" sheet (Figma 9057:47088) goes from gross
sales to net commission, then by marketplace and by product. Every figure is a
sum over the canonical transaction store, `affiliate_postbacks`, which already
holds one row per marketplace item. What it did not keep:

- item_commission   the report's own per-item commission, at the report's
                    precision (Shopee carries up to five decimals). Summed
                    first and rounded once, so ₱1,962.70265 shows as ₱1,962.70;
                    rounding each row first would show ₱1,962.75.
                    `reported_payout` stays the centavo figure the ledger
                    credits.
- purchase_value    the item's purchase value (Shopee "Purchase Value"), for
                    Gross sales
- item_qty          units on the row
- source_model_id   the marketplace's variant (Shopee "Model id")
- product_id        our catalogue product (Item id -> canonical product), so
                    products group by the catalogue and not by the
                    marketplace's title
- reviewer_id       the member the sale is credited to: the attributed
                    review's author, or the reviewer id carried in Sub_id1

Additive and nullable; nothing reads them yet. Downgrade drops them.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0096_affiliate_item_detail"
down_revision = "0095_trust_score_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("affiliate_postbacks", sa.Column("item_commission", sa.Numeric(14, 5)))
    op.add_column("affiliate_postbacks", sa.Column("purchase_value", sa.Numeric(14, 5)))
    op.add_column("affiliate_postbacks", sa.Column("item_qty", sa.Integer()))
    op.add_column("affiliate_postbacks", sa.Column("source_model_id", sa.String(128)))
    op.add_column("affiliate_postbacks", sa.Column(
        "product_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("products.id", ondelete="SET NULL")))
    op.add_column("affiliate_postbacks", sa.Column(
        "reviewer_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.create_index("ix_affiliate_postbacks_reviewer_id", "affiliate_postbacks", ["reviewer_id"])


def downgrade() -> None:
    op.drop_index("ix_affiliate_postbacks_reviewer_id", table_name="affiliate_postbacks")
    for column in ("reviewer_id", "product_id", "source_model_id", "item_qty",
                   "purchase_value", "item_commission"):
        op.drop_column("affiliate_postbacks", column)

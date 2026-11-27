"""A store's response shows "Edited" (Figma Confirm/Store/SaveResponse 8202:22699).

Revision ID: 0082_seller_response_edited_at
Revises: 0081_answer_edited_at
Create Date: 2026-10-04

Adds seller_reviews.seller_response_edited_at (nullable). Editing a response
used to overwrite seller_response_at, which the store's median reply time and
Insights read, so every edit made the store look slower. From now on
seller_response_at keeps the first response's time, and an edit sets this.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0082_seller_response_edited_at"
down_revision = "0081_answer_edited_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("seller_reviews",
                  sa.Column("seller_response_edited_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("seller_reviews", "seller_response_edited_at")

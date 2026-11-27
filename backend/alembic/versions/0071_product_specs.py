"""Product specs: the Edit product modal's "add spec" list (meeting 2026-10-02, 10:45).

Revision ID: 0071_product_specs
Revises: 0070_vote_network_fingerprints
Create Date: 2026-10-02

A product's specifics beyond its name parts: a short list of label / value
pairs ("Battery" / "4000 mAh", "Switch" / "Gateron Brown") that tell two
variants apart. One nullable JSONB column on `products`; null = none recorded.

Additive; the downgrade drops the column.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0071_product_specs"
down_revision = "0070_vote_network_fingerprints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("specs", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "specs")

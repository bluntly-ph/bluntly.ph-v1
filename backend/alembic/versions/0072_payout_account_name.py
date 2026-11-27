"""The name on the payout account (Figma Screen/Payout/Details 7843:9432).

Revision ID: 0072_payout_account_name
Revises: 0071_product_specs
Create Date: 2026-10-02

"Use the name on your account. Payouts to a different name are sent back":
the owner sends payouts by hand and checks the name before sending. One
nullable column on `users`; null = not given. Additive; the downgrade drops it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0072_payout_account_name"
down_revision = "0071_product_specs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("payout_account_name", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "payout_account_name")

"""An owner gives a store up (Figma Confirm/Store/GiveUp 8220:24024).

Revision ID: 0078_store_release
Revises: 0077_store_products
Create Date: 2026-10-04

Adds 'store_release' to moderation_action so giving a store up is audited.
No table changes: the store goes back to unclaimed through the existing
columns. The downgrade is a no-op (PostgreSQL cannot drop an enum value).
"""

from __future__ import annotations

from alembic import op

revision = "0078_store_release"
down_revision = "0077_store_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'store_release'")


def downgrade() -> None:
    pass

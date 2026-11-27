"""Product CSV imports are audited.

Revision ID: 0089_product_import_action
Revises: 0088_function_search_path
Create Date: 2026-10-04

Adds 'product_import' to moderation_action: applying a product CSV records one
Activity log entry with who imported, the file name and the counts (total,
imported, attached, skipped, invalid) and the created products' ids — never the
file itself. `csv_import` is the affiliate report's action and the Affiliate
Imports tab lists every row of it, so product imports need their own. No table
changes; the downgrade is a no-op (PostgreSQL cannot drop an enum value).
"""

from __future__ import annotations

from alembic import op

revision = "0089_product_import_action"
down_revision = "0088_function_search_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'product_import'")


def downgrade() -> None:
    pass

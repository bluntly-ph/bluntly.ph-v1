"""Admin Export CSV is audited (Figma Overlay/Admin/Export 8237:25470).

Revision ID: 0079_data_export
Revises: 0078_store_release
Create Date: 2026-10-04

Adds 'data_export' to moderation_action: each admin export is recorded in the
Activity log with its sections and period ("Exports are recorded in the
Activity log"). No table changes. The downgrade is a no-op (PostgreSQL cannot
drop an enum value).
"""

from __future__ import annotations

from alembic import op

revision = "0079_data_export"
down_revision = "0078_store_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'data_export'")


def downgrade() -> None:
    pass

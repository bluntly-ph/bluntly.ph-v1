"""Integration settings are audited (Figma Overlay/Settings/ConnectPayMongo 8237:25540).

Revision ID: 0080_integration_change
Revises: 0079_data_export
Create Date: 2026-10-04

Adds 'integration_change' to moderation_action: saving or removing the PayMongo
keys is recorded in the Activity log (never the keys). The keys themselves live
encrypted in platform_settings. No table changes; the downgrade is a no-op
(PostgreSQL cannot drop an enum value).
"""

from __future__ import annotations

from alembic import op

revision = "0080_integration_change"
down_revision = "0079_data_export"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'integration_change'")


def downgrade() -> None:
    pass

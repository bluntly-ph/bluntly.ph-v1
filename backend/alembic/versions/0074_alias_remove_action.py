"""Audit an alias removal (Figma Overlay/Product/Edit 7970:11204: "Also known as"
chips can be removed).

Revision ID: 0074_alias_remove_action
Revises: 0073_qa_engagement
Create Date: 2026-10-02

Adds 'alias_remove' to moderation_action so taking an alias off a product is
logged like adding one. `ALTER TYPE ... ADD VALUE` runs outside a transaction
(autocommit block). Additive; the downgrade leaves the value (PostgreSQL cannot
drop one, and rows may use it).
"""

from __future__ import annotations

from alembic import op

revision = "0074_alias_remove_action"
down_revision = "0073_qa_engagement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'alias_remove'")


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL; see the module docstring.
    pass

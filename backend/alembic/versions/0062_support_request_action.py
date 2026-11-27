"""Audit action for seller support requests.

Revision ID: 0062_support_request_action
Revises: 0061_commission_reviewer_index
Create Date: 2026-09-28

One `moderation_action` value, `support_request`: every state change of a
seller support request (created, assigned, answered, status changed) is audited
under it, the event named in the row's context.

`ALTER TYPE ... ADD VALUE` cannot share a transaction with other DDL, which is
why the table is in 0063. Additive; the downgrade leaves the value (PostgreSQL
cannot drop one, and a row that uses it must not be orphaned).
"""

from __future__ import annotations

from alembic import op

revision = "0062_support_request_action"
down_revision = "0061_commission_reviewer_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'support_request'")


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL; see the module docstring.
    pass

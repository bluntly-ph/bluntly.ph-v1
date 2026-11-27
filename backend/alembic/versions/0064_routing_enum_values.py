"""Enum values for the 2.5-star special routing (owner decision A).

Revision ID: 0064_routing_enum_values
Revises: 0063_seller_support_requests
Create Date: 2026-09-28

`earn_eligible_status` gains `pending_superadmin_routing`: an administrator
approved a 2.5-star "It depends" thread's earnings and only a Super Admin may
decide where they go. `moderation_action` gains `special_routing`, the audit
action for that decision.

`ALTER TYPE ... ADD VALUE` cannot share a transaction with other DDL, which is
why the role rebuild is 0065 and the routing columns are 0066. Additive; the
downgrade leaves the values (PostgreSQL cannot drop one, and rows may use it).
"""

from __future__ import annotations

from alembic import op

revision = "0064_routing_enum_values"
down_revision = "0063_seller_support_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE earn_eligible_status "
                   "ADD VALUE IF NOT EXISTS 'pending_superadmin_routing'")
        op.execute("ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS 'special_routing'")


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL; see the module docstring.
    pass

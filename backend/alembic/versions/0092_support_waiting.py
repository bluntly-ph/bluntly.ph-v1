"""Support: a "waiting for seller" status and a "store change" category.

Revision ID: 0092_support_waiting
Revises: 0091_store_change_requests
Create Date: 2026-10-05

MQA-022: when the team asks a seller for more information the request said
"In review", so the seller did not know they had to act and the queue could not
tell requests waiting on the seller from requests waiting on a moderator.
MQA-026: store changes were filed as "My account or store claim".

Two enum values, nothing else. ALTER TYPE ... ADD VALUE runs outside the
transaction (as 0080 and 0089 do). The downgrade is a no-op: PostgreSQL cannot
drop an enum value.
"""

from __future__ import annotations

from alembic import op

revision = "0092_support_waiting"
down_revision = "0091_store_change_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE support_request_status ADD VALUE IF NOT EXISTS "
                   "'waiting_for_seller' BEFORE 'resolved'")
        op.execute("ALTER TYPE support_request_category ADD VALUE IF NOT EXISTS "
                   "'store_change' BEFORE 'general'")


def downgrade() -> None:
    pass

"""A claimant can withdraw a pending store claim (Figma Overlay/Store/ClaimStatus
8232:25429, Confirm/Store/WithdrawClaim 8233:25386).

Revision ID: 0075_seller_claim_withdrawn
Revises: 0074_alias_remove_action
Create Date: 2026-10-03

Adds 'withdrawn' to seller_claim_status. A withdrawn claim leaves the
administrators' Claims queue (it lists pending claims only) and stays on record,
with its case chat, instead of being deleted. The partial unique index
uq_seller_claim_pending covers pending rows only, so a withdrawn claim never
blocks a new one. Additive; `ALTER TYPE ... ADD VALUE` runs outside a
transaction (autocommit block); the downgrade leaves the value (PostgreSQL
cannot drop one, and rows may use it).
"""

from __future__ import annotations

from alembic import op

revision = "0075_seller_claim_withdrawn"
down_revision = "0074_alias_remove_action"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE seller_claim_status ADD VALUE IF NOT EXISTS 'withdrawn'")


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL; see the module docstring.
    pass

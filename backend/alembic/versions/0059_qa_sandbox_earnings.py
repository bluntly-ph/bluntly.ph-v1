"""QA sandbox test earnings: `commissions.is_test`.

Revision ID: 0059_qa_sandbox_earnings
Revises: 0058_qa_sandbox_actions
Create Date: 2026-09-27

A test earning lets a named QA tester exercise the real payout flow — cleared
balance, cashout request, batch, PayPal sandbox, paid — without a marketplace
sale behind it. It is an ordinary ledger row with `is_test = true`, so the
tester's wallet, cashout and history work exactly as they do for real money,
and every revenue or Honesty Fund figure filters it out.

* `is_test` — NOT NULL DEFAULT false: every existing row is a real commission.
* `ck_commission_test_no_revenue` — a test row carries no platform share and
  no Honesty Fund share, so it cannot be counted as either even by a query
  that forgets the filter.
* `uq_commission_one_qa_test` — at most one test earning per review.

Additive only (a defaulted column, a CHECK every existing row satisfies, a
partial index over zero rows); the downgrade drops exactly what this adds.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059_qa_sandbox_earnings"
down_revision = "0058_qa_sandbox_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commissions", sa.Column(
        "is_test", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_check_constraint(
        "ck_commission_test_no_revenue", "commissions",
        "NOT is_test OR (platform_share = 0 AND honesty_fund_share = 0)")
    op.create_index(
        "uq_commission_one_qa_test", "commissions", ["review_id"], unique=True,
        postgresql_where=sa.text("is_test"))


def downgrade() -> None:
    op.drop_index("uq_commission_one_qa_test", table_name="commissions")
    op.drop_constraint("ck_commission_test_no_revenue", "commissions", type_="check")
    op.drop_column("commissions", "is_test")

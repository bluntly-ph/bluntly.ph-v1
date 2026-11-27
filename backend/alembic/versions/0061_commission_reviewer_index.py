"""Index commissions by reviewer and cycle (reporting module).

Revision ID: 0061_commission_reviewer_index
Revises: 0060_seller_review_engagement
Create Date: 2026-09-28

`commissions` had no index on `reviewer_id`, and three reads filter on it: a
reviewer's earnings statement (reviewer + cycle months), the dashboard, and
`payout_service.uncleared_share` — the check every cashout request runs.

Measured, not assumed (docs/REPORTING_MODULE.md, "Query performance"): with
200,000 commissions across 2,000 reviewers the cashout check was a parallel
sequential scan at 27 ms and the statement's period sum 1.9 ms; with this index
they are index scans at 0.23 ms and 0.09 ms. Today's tables are tiny (TEST 48
rows), so this is sized for growth, not a present fire: every marketplace sale
is a row.

One composite index covers both shapes (reviewer alone, reviewer + cycle
range). Additive; the downgrade drops exactly it.
"""

from __future__ import annotations

from alembic import op

revision = "0061_commission_reviewer_index"
down_revision = "0060_seller_review_engagement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_commissions_reviewer_cycle", "commissions",
                    ["reviewer_id", "cycle_month"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_commissions_reviewer_cycle", table_name="commissions", if_exists=True)

"""Index reviews for the Administrator's All Reviews list (QA, 2026-09-29).

Revision ID: 0068_all_reviews_indexes
Revises: 0067_last_super_admin_guard
Create Date: 2026-09-29

All Reviews pages every review newest-first by default, or by Wilson score
either way. Without an index each page sorted the whole table to keep fifty
rows.

Measured on a copy of the test database inflated to 50,472 reviews and 200,259
votes (docs/QA_CURRENT_RECONCILIATION.md, "Query performance"):

| page                      | before                          | after                  |
|---------------------------|---------------------------------|------------------------|
| newest, page 1            | 54.9 ms, seq scan + full sort   | 0.35 ms, index scan    |
| Wilson high → low, page 1 | 72.3 ms, seq scan + full sort   | 0.28 ms, index scan    |
| Wilson, page 200          | 127.0 ms, seq scan + full sort  | 17.3 ms, index scan    |

The total count stays a scan (about 15 ms at that size). Free-text search is
a scan too (about 155 ms at that size) and gets no index here: it is a staff
tool over a table that holds hundreds of rows today.

Each sort is the exact reverse of its pair (newest/oldest, Wilson high/low),
so one btree per pair serves both directions. Today's tables are small (TEST
has a few hundred reviews); this is sized for growth. Additive; the downgrade
drops exactly these two.
"""

from __future__ import annotations

from alembic import op

revision = "0068_all_reviews_indexes"
down_revision = "0067_last_super_admin_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_reviews_created_id", "reviews", ["created_at", "id"],
                    if_not_exists=True)
    op.create_index("ix_reviews_wilson_created_id", "reviews",
                    ["wilson_score", "created_at", "id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_reviews_wilson_created_id", table_name="reviews", if_exists=True)
    op.drop_index("ix_reviews_created_id", table_name="reviews", if_exists=True)

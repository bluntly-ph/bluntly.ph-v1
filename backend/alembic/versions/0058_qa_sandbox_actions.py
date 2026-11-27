"""Audit actions for QA sandbox test earnings.

Revision ID: 0058_qa_sandbox_actions
Revises: 0057_round3_interactions
Create Date: 2026-09-27

Three `moderation_action` values, nothing else:

* `qa_tester_add` / `qa_tester_remove` — the site owner names (or un-names) an
  account as a QA tester, the only accounts a test earning may be credited to.
* `qa_test_credit` — a moderator credits a QA tester's published review with a
  labelled sandbox test earning (`qa_sandbox_service.credit`).

`ALTER TYPE ... ADD VALUE` cannot share a transaction with other DDL, which is
why the column and its constraints are in 0059 (scripts/check_migration_safety.py).
Additive: deployed code that does not know the values never produces them.
The downgrade leaves them: PostgreSQL cannot drop an enum value, and a row
that uses one must not be orphaned.
"""

from __future__ import annotations

from alembic import op

revision = "0058_qa_sandbox_actions"
down_revision = "0057_round3_interactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS keeps a re-run harmless.
    with op.get_context().autocommit_block():
        for value in ("qa_tester_add", "qa_tester_remove", "qa_test_credit"):
            op.execute(f"ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL; see the module docstring.
    pass

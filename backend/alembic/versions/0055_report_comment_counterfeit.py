"""Comments can be reported, and "counterfeit" is a report reason.

Revision ID: 0055_report_comment_counterfeit
Revises: 0054_record_source_listings
Create Date: 2026-09-26

Two enum values, nothing else:

* `moderation_target_type.comment` — QA-069: a reader reports another
  member's comment through the same report pipeline reviews use
  (report_service.file_report, one open report per reporter and target).
* `moderation_reason.counterfeit` — the admin priority tiers (dev note,
  2026-09-26) weigh "fraud or counterfeit" reports differently from every
  other category. Fake proof of purchase and a seller posing as a buyer are
  fraud reasons that already exist; a counterfeit product had no reason of
  its own, so a reader could only file it as "other".

`ALTER TYPE ... ADD VALUE` cannot share a transaction with other DDL, which is
why this migration carries nothing else (scripts/check_migration_safety.py).
Additive: deployed code that does not know the values never produces them.
The downgrade leaves them: PostgreSQL cannot drop an enum value, and a row
that uses one must not be orphaned.
"""

from __future__ import annotations

from alembic import op

revision = "0055_report_comment_counterfeit"
down_revision = "0054_record_source_listings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS keeps a re-run harmless.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE moderation_target_type ADD VALUE IF NOT EXISTS 'comment'")
        op.execute("ALTER TYPE moderation_reason ADD VALUE IF NOT EXISTS 'counterfeit'")


def downgrade() -> None:
    # Enum values cannot be removed in PostgreSQL; see the module docstring.
    pass

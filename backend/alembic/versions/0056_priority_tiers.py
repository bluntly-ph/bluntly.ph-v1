"""Admin queue priority tiers: tunable thresholds and the aging record.

Revision ID: 0056_priority_tiers
Revises: 0055_report_comment_counterfeit
Create Date: 2026-09-26

The dev note "Admin Dashboard: Priority Tier System" (2026-09-26) tiers the
items ALREADY in the earn_eligible queue and the content-report queue as
Highest / High / Neutral / Low / Lowest. It changes nothing about how an item
enters either queue.

* `platform_settings` — one JSON value per key. The note asks for the Wilson
  band, the fraud-report thresholds, the aging window and the Low/Lowest stage
  boundaries to live outside the code "ideally without a redeploy each time",
  and nothing in the schema held tunable values before. Rows are optional:
  code defaults apply until an admin saves a value.
* `queue_triage` — one row per item currently in a queue: when it entered (or
  its clock last restarted), when the hourly job aged it one tier, and the
  tier last computed. Aging is scheduled, never a side effect of a page load,
  and opening an item writes nothing here.

Additive only. The downgrade drops both tables; nothing else references them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0056_priority_tiers"
down_revision = "0055_report_comment_counterfeit"
branch_labels = None
depends_on = None


def _hide_from_postgrest(table: str) -> None:
    """PostgREST must not see a new table (0029's rule, as 0050 and 0052 apply
    it): RLS on with no policy, and nothing granted to the API roles."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON {table} FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON {table} FROM authenticated;
          END IF;
        END $$;""")


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_table(
        "queue_triage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("queue", sa.String(16), nullable=False),
        sa.Column("target_type", sa.String(24), nullable=False),
        sa.Column("target_ref", UUID(as_uuid=True), nullable=False),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tier", sa.String(16), nullable=True),
        sa.Column("base_tier", sa.String(16), nullable=True),
        sa.Column("reasons", JSONB, nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("queue", "target_type", "target_ref", name="uq_queue_triage_item"),
    )
    for table in ("platform_settings", "queue_triage"):
        _hide_from_postgrest(table)


def downgrade() -> None:
    op.drop_table("queue_triage")
    op.drop_table("platform_settings")

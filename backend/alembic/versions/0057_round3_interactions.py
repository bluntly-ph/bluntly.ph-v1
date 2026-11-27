"""Round 3: notification controls, comment follow/save, request fulfilment time.

Revision ID: 0057_round3_interactions
Revises: 0056_priority_tiers
Create Date: 2026-09-26

* `notifications.dismissed_at` — QA-065: a member clears one notification from
  their list. A soft dismissal: the row, and the business event it describes,
  stay; only the list stops showing it.
* `notifications.group_count` — QA-067: repeated interactions of one kind on
  one item while the notice is still unread ("3 people found your review
  helpful") update one row instead of stacking a notice per vote.
* `notification_receipts` — QA-067: "this recipient was already told about
  this actor's action on this item" (`review_upvoted:<review>:<voter>`). A vote
  taken back and cast again, or a retried request, finds its receipt and stays
  silent; one row per (recipient, event key), never shown to anyone.
* `comment_follows`, `comment_saves` — QA-069: a reader follows another
  member's comment (and hears about replies to it) or saves it privately. One
  row per (comment, member); neither is ever shown to anyone else.
* `review_requests.fulfilled_at` — QA-073/074: when a published review
  answered the request, set once by the idempotent fulfilment.

Additive only; the downgrade drops exactly what this adds.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0057_round3_interactions"
down_revision = "0056_priority_tiers"
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


def _marks(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("comment_id", UUID(as_uuid=True),
                  sa.ForeignKey("review_comments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("comment_id", "user_id", name=f"uq_{name}_once"),
    )
    op.create_index(f"ix_{name}_user", name, ["user_id", "created_at"])


def upgrade() -> None:
    op.add_column("notifications", sa.Column("dismissed_at", sa.DateTime(timezone=True),
                                             nullable=True))
    op.add_column("notifications", sa.Column("group_count", sa.Integer(), nullable=False,
                                             server_default="1"))
    op.create_table(
        "notification_receipts",
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_key", sa.String(160), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    _marks("comment_follows")
    _marks("comment_saves")
    for table in ("notification_receipts", "comment_follows", "comment_saves"):
        _hide_from_postgrest(table)
    op.add_column("review_requests", sa.Column("fulfilled_at", sa.DateTime(timezone=True),
                                               nullable=True))


def downgrade() -> None:
    op.drop_column("review_requests", "fulfilled_at")
    op.drop_index("ix_comment_saves_user", table_name="comment_saves")
    op.drop_table("comment_saves")
    op.drop_index("ix_comment_follows_user", table_name="comment_follows")
    op.drop_table("comment_follows")
    op.drop_table("notification_receipts")
    op.drop_column("notifications", "group_count")
    op.drop_column("notifications", "dismissed_at")

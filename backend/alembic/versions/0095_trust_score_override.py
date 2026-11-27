"""An administrator can override a member's Honesty Score (owner, 2026-10-05).

Revision ID: 0095_trust_score_override
Revises: 0094_review_photos
Create Date: 2026-10-05

The algorithm keeps computing the score; an administrator may set a value in
its place, and clear it again. `users.reputation_score` stays the column every
reader uses (vote weight, review lenses, the Honesty Fund, profiles, cards) and
now holds the EFFECTIVE score:

    effective = reputation_score_override  if set
              = computed_reputation_score  otherwise

- computed_reputation_score  the algorithm's value (trust_service writes it);
                             backfilled from reputation_score, which held
                             only computed values until now
- reputation_score_override  NULL = no override; 0..100 (CHECK), the same
                             scale as the score (ADR-003)
- reputation_override_by_id / _at / _reason   who set it, when and why (the
                             reason is also in the audit log, moderation_logs)

Additive and nullable. Downgrade puts the computed score back in
reputation_score and drops the columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0095_trust_score_override"
down_revision = "0094_review_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "computed_reputation_score", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.execute("UPDATE users SET computed_reputation_score = reputation_score")
    op.add_column("users", sa.Column("reputation_score_override", sa.Numeric(5, 2), nullable=True))
    op.add_column("users", sa.Column(
        "reputation_override_by_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("users", sa.Column(
        "reputation_override_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("reputation_override_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_users_reputation_override_range", "users",
        "reputation_score_override IS NULL "
        "OR (reputation_score_override >= 0 AND reputation_score_override <= 100)")


def downgrade() -> None:
    op.execute("UPDATE users SET reputation_score = computed_reputation_score")
    op.drop_constraint("ck_users_reputation_override_range", "users", type_="check")
    op.drop_column("users", "reputation_override_reason")
    op.drop_column("users", "reputation_override_at")
    op.drop_column("users", "reputation_override_by_id")
    op.drop_column("users", "reputation_score_override")
    op.drop_column("users", "computed_reputation_score")

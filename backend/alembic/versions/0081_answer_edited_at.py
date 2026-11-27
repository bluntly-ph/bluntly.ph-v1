"""A store can edit its answer (Figma Overlay/Store/EditAnswer 8202:22530).

Revision ID: 0081_answer_edited_at
Revises: 0080_integration_change
Create Date: 2026-10-04

Adds answers.edited_at (nullable): set when the store's owner edits the
store's answer, so buyers see "Edited" next to it. updated_at cannot carry
this: vote counters change it too.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0081_answer_edited_at"
down_revision = "0080_integration_change"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("answers", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("answers", "edited_at")

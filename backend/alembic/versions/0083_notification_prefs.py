"""A store owner chooses which store notifications reach them (Figma Screen/Seller/Settings 8218:24151).

Revision ID: 0083_notification_prefs
Revises: 0082_seller_response_edited_at
Create Date: 2026-10-04

Adds users.notification_prefs (JSONB, nullable). NULL means "everything on", so
every existing account keeps today's behaviour; app/services/notification_service.py
reads it when it queues a notification. In the app only: nothing here sends email.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0083_notification_prefs"
down_revision = "0082_seller_response_edited_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notification_prefs", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "notification_prefs")

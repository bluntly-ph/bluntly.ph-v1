"""Vote-farming network signal: keyed network hashes, never addresses (QA, 2026-09-29).

Revision ID: 0070_vote_network_fingerprints
Revises: 0069_image_fingerprints
Create Date: 2026-09-29

One row per up-vote cast from now on, holding an HMAC-SHA256 (server secret)
of the voter's trusted client IP (an IPv6 address by its /64), truncated to 32
hex characters, the voter, the review and its author. No IP address is stored,
in this table or anywhere else the signal touches. Rows are deleted after 30
days by the existing retention sweep. Nothing is backfilled: no network was
ever recorded for past votes.

Indexed for the one question the signal asks: which accounts on this network
up-voted this author recently? (`ix_vote_network_author_network_created`), and
for the retention purge (`ix_vote_network_created`).

Additive; the downgrade drops the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0070_vote_network_fingerprints"
down_revision = "0069_image_fingerprints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vote_network_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("review_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voter_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("network", sa.String(32), nullable=False),
        sa.Column("new_account", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("review_id", "voter_id", name="uq_vote_network_review_voter"),
    )
    op.create_index("ix_vote_network_author_network_created", "vote_network_fingerprints",
                    ["author_id", "network", "created_at"])
    op.create_index("ix_vote_network_created", "vote_network_fingerprints", ["created_at"])
    # Hidden from PostgREST like every application table (0029): RLS with no
    # policy, and no privileges for the public roles.
    op.execute("ALTER TABLE vote_network_fingerprints ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON vote_network_fingerprints FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON vote_network_fingerprints FROM authenticated;
          END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_index("ix_vote_network_created", table_name="vote_network_fingerprints")
    op.drop_index("ix_vote_network_author_network_created",
                  table_name="vote_network_fingerprints")
    op.drop_table("vote_network_fingerprints")

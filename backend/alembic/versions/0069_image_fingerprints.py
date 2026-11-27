"""Image fingerprints for duplicate review photos (QA, 2026-09-29).

Revision ID: 0069_image_fingerprints
Revises: 0068_all_reviews_indexes
Create Date: 2026-09-29

One row per public review photo uploaded from now on: its SHA-256 (exact
copies) and a 64-bit difference hash (resized or re-encoded copies), so a new
review's photo can be compared with every other review's photo. Derived from
an image that is already public on the review; no personal data.

A partial index on `reviews.photo_url` lets the check read the few reviews
whose photo is near, instead of hashing every review: 141 ms to about 11 ms at
50,000 photos (EXPLAIN in docs/ANTI_FARMING_AND_PLAGIARISM.md).

Photos uploaded before this migration have no row. They are not compared
until fingerprinted (docs/ANTI_FARMING_AND_PLAGIARISM.md): nothing is invented
for them, and nothing is fetched from Storage by a migration.

Additive; the downgrade drops the table, its indexes and `ix_reviews_photo_url`.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0069_image_fingerprints"
down_revision = "0068_all_reviews_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_fingerprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("dhash", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("algorithm", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("url", name="uq_image_fingerprints_url"),
    )
    op.create_index("ix_image_fingerprints_sha256", "image_fingerprints", ["sha256"])
    op.create_index("ix_image_fingerprints_uploader_id", "image_fingerprints", ["uploader_id"])
    op.create_index("ix_reviews_photo_url", "reviews", ["photo_url"],
                    postgresql_where=sa.text("photo_url IS NOT NULL"))
    # Hidden from PostgREST like every application table (0029): RLS with no
    # policy, and no privileges for the public roles.
    op.execute("ALTER TABLE image_fingerprints ENABLE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            REVOKE ALL ON image_fingerprints FROM anon;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            REVOKE ALL ON image_fingerprints FROM authenticated;
          END IF;
        END $$;""")


def downgrade() -> None:
    op.drop_index("ix_reviews_photo_url", table_name="reviews")
    op.drop_index("ix_image_fingerprints_uploader_id", table_name="image_fingerprints")
    op.drop_index("ix_image_fingerprints_sha256", table_name="image_fingerprints")
    op.drop_table("image_fingerprints")

"""Products: keep the rating column's name; hold the §4 median in it.

Revision ID: 0051_product_median_column
Revises: 0050_business_rules
Create Date: 2026-09-24

The first cut of 0050 renamed products.avg_rating to median_rating without
recomputing it. Two defects, found in full-system QA:

  * Rollout. A rename is a drop and an add to the deployed build: the release
    workflow migrates production before it deploys, and the running build
    selects avg_rating, so product endpoints would 500 until the deploy
    finished. The column now keeps its name; the model maps median_rating to it.
  * Data. The renamed column still held each product's old AVERAGE, shown as
    the §4 median until some later review happened to recompute it.

0050 was corrected before reaching production. This revision reconciles any
database that already ran the first cut (the shared test project did): the
column is renamed back if needed, then every product's median is recomputed
with exactly the service's rule (review_service.recompute_product_aggregates):
one value per thread — its latest published, non-removed entry — combined by
median, 0 when there are none. Idempotent: running it twice changes nothing.
"""

from __future__ import annotations

from alembic import op

revision = "0051_product_median_column"
down_revision = "0050_business_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_schema = current_schema() AND table_name = 'products'
                         AND column_name = 'median_rating')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_schema = current_schema()
                                 AND table_name = 'products' AND column_name = 'avg_rating')
            THEN
                ALTER TABLE products RENAME COLUMN median_rating TO avg_rating;
            END IF;
        END $$;
    """)
    op.execute("""
        UPDATE products p
        SET avg_rating = COALESCE(m.median, 0)
        FROM products q
        LEFT JOIN (
            SELECT product_id,
                   round(percentile_cont(0.5) WITHIN GROUP (ORDER BY stars)::numeric, 2)
                       AS median
            FROM (
                SELECT DISTINCT ON (COALESCE(thread_id, id))
                       product_id, star_rating AS stars
                FROM reviews
                WHERE is_removed = false AND published_at IS NOT NULL
                ORDER BY COALESCE(thread_id, id), created_at DESC, id DESC
            ) latest
            GROUP BY product_id
        ) m ON m.product_id = q.id
        WHERE p.id = q.id
    """)


def downgrade() -> None:
    # Nothing to undo: the column name is the one 0050 (as corrected) expects,
    # and the values are the medians 0050's code computes. 0050's own downgrade
    # restores means for 0049.
    pass

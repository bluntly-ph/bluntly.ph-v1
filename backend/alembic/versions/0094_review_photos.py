"""Product reviews carry several photos (owner requirement, 2026-10-05).

Revision ID: 0094_review_photos
Revises: 0093_message_edits
Create Date: 2026-10-05

A review held one `photo_url`. It now holds an ordered list, `photo_urls`
(text[]), the same shape store reviews and answers already use - array order
is display order. `photo_url` stays as the list's first entry so every
existing reader (cards, dashboards, the duplicate-photo check, verification)
keeps working; the model keeps the two in step (models/review.py).

NO PHOTO = NO DEFAULT PHOTO: a review without reviewer photos has '{}' here.
Nothing writes the product's listing image into either column.

Backfill: every review with a photo_url gets photo_urls = {photo_url}. At most
MAX_REVIEW_PHOTOS (4) entries, enforced by a CHECK.

Additive. Downgrade drops the column (photo_url still holds the first photo).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0094_review_photos"
down_revision = "0093_message_edits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column(
        "photo_urls", postgresql.ARRAY(sa.Text()), nullable=False,
        server_default=sa.text("'{}'::text[]")))
    op.execute("UPDATE reviews SET photo_urls = ARRAY[photo_url] "
               "WHERE photo_url IS NOT NULL AND photo_url <> ''")
    op.create_check_constraint("ck_review_photo_count", "reviews",
                               "cardinality(photo_urls) <= 4")


def downgrade() -> None:
    op.drop_constraint("ck_review_photo_count", "reviews", type_="check")
    op.drop_column("reviews", "photo_urls")

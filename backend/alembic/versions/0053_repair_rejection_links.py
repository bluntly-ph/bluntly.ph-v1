"""Point legacy rejection notices at the review they are about (QA-054).

Revision ID: 0053_repair_rejection_links
Revises: 0052_review_drafts
Create Date: 2026-09-24

Before the Business Rules release, rejecting a review wrote a `review_rejected`
notification linking to /dashboard/history — the earnings list, not the review.
New notices link to /reviews/<id> (notification_service.review_decided), but
the rows already written kept the old link, and the independent tester's retest
opened exactly such a row (created 2026-09-22), landing on Earning History.

The old row stores no review id. It was written in the same transaction as the
moderator's `reject` log, so the two share a created_at to the microsecond, and
that log's target is the notified author's own review. This repairs a link only
when all three agree — same instant, a `reject` of a review, the review is the
recipient's — so it can never point anyone at someone else's review. Rows that
do not match keep their link.

Data only, idempotent. The downgrade does not restore the old link: it was the
defect.
"""

from __future__ import annotations

from alembic import op

revision = "0053_repair_rejection_links"
down_revision = "0052_review_drafts"
branch_labels = None
depends_on = None

REPAIR_SQL = """
UPDATE notifications AS n
   SET link = '/reviews/' || m.target_ref::text
  FROM moderation_logs AS m
  JOIN reviews AS r ON r.id = m.target_ref
 WHERE n.kind = 'review_rejected'
   AND n.link = '/dashboard/history'
   AND m.target_type = 'review'
   AND m.action = 'reject'
   AND m.created_at = n.created_at
   AND r.author_id = n.user_id
"""


def upgrade() -> None:
    op.execute(REPAIR_SQL)


def downgrade() -> None:
    pass

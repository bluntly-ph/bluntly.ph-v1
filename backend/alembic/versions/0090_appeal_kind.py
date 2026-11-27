"""A seller's flag says what is wrong with the review (MQA-041).

Revision ID: 0090_appeal_kind
Revises: 0089_product_import_action
Create Date: 2026-10-05

Until now a store could only flag a review "as fake" (the buyer never ordered).
A real buyer's review can still be untrue, or break the rules, and asking that
buyer to prove a purchase that did happen settles nothing. `kind` records which
problem the store raised, so the admin knows which check fits:

  never_ordered  the buyer never ordered -> ask for proof of purchase
  untrue         the details are untrue  -> ask for evidence of the claims
  breaks_rules   it breaks the rules     -> check it against the guidelines

Existing flags were all "fake" flags, so the default backfills them truthfully.
Additive (one NOT NULL column with a default, one CHECK); downgrade drops it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0090_appeal_kind"
down_revision = "0089_product_import_action"
branch_labels = None
depends_on = None

KINDS = ("never_ordered", "untrue", "breaks_rules")


def upgrade() -> None:
    op.add_column("seller_review_appeals", sa.Column(
        "kind", sa.String(20), nullable=False, server_default="never_ordered"))
    op.create_check_constraint(
        "ck_seller_review_appeal_kind", "seller_review_appeals",
        "kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")")


def downgrade() -> None:
    op.drop_constraint("ck_seller_review_appeal_kind", "seller_review_appeals", type_="check")
    op.drop_column("seller_review_appeals", "kind")

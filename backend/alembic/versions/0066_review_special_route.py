"""Where a Super Admin sent a 2.5-star "It depends" thread (owner decision A).

Revision ID: 0066_review_special_route
Revises: 0065_admin_superadmin_roles
Create Date: 2026-09-28

`reviews.special_route` (honesty_fund | platform), who decided and when. Set
on the thread root by the Super Admin's routing decision, cleared when a later
update moves the thread off 2.5 stars. The decision itself is audited in
moderation_logs under `special_routing`; these columns are the current state
the money path reads. Additive; the downgrade drops them.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0066_review_special_route"
down_revision = "0065_admin_superadmin_roles"
branch_labels = None
depends_on = None

special_route = postgresql.ENUM("honesty_fund", "platform", name="special_route",
                                create_type=False)


def upgrade() -> None:
    special_route.create(op.get_bind(), checkfirst=True)
    op.add_column("reviews", sa.Column("special_route", special_route, nullable=True))
    op.add_column("reviews", sa.Column("special_routed_at", sa.DateTime(timezone=True),
                                       nullable=True))
    op.add_column("reviews", sa.Column(
        "special_routed_by_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_reviews_special_routed_by"),
        nullable=True))
    # The Super Admin queue reads by status; the partial index keeps it cheap
    # however many decided reviews accumulate.
    op.create_index("ix_reviews_pending_superadmin_routing", "reviews", ["created_at"],
                    postgresql_where=sa.text(
                        "earn_eligible_status = 'pending_superadmin_routing'"))


def downgrade() -> None:
    op.drop_index("ix_reviews_pending_superadmin_routing", table_name="reviews")
    op.drop_column("reviews", "special_routed_by_id")
    op.drop_column("reviews", "special_routed_at")
    op.drop_column("reviews", "special_route")
    special_route.drop(op.get_bind(), checkfirst=True)

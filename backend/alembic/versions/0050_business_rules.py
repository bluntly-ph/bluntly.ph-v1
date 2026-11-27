"""the finalized Business Rules (Full Record, 2026-09-23)

One revision for the schema the settled rules need, so the release that adopts
them is one step forward and one step back. Section numbers are the Full
Record's.

reviews (§4 immutability and threads)
    thread_id             the thread a review belongs to: its own id for an
                          original, the root's id for a later update. Backfilled
                          to `id`, so every existing review is a one-entry thread.
    photo_replaced_at     the one photo swap allowed within 72 hours; set = used.
    removed_by_author_at  the author deleted this entry (never a hard delete: a
                          thread that paid out stays investigable).
    removed_after_payout  the deleted thread had triggered a payout, so it shows
                          in the product's aggregate "removed by author" note.

products (§4 rating)
    products.avg_rating now holds the median of each thread's latest entry
    (§4). The column is NOT renamed — see 0051, which recomputes it.

users (§9, §11)
    is_under_investigation  halves vote weight while true; the trigger is open.
    is_claimed_seller       permanent: set when a seller claim is approved and
                          never cleared, because the bar is "past, present and
                          future". Backfilled from approved claims.

review_votes (§11)
    vote_weight, trust_stage_snapshot  the backend weight of a visible vote,
                          snapshotted at vote time so a gate decision stays
                          auditable when the voter's trust later moves.

moderation_logs (§12)
    report_source         USER_REPORTED vs SYSTEM_DETECTED on every report row.
                          Backfilled: a report with no reporter is system-made.

seller_reviews / seller_review_appeals / seller_claims (§9, §10)
    order_id              self-reported at submission, never "verified".
    seller_review_appeals a claimed seller's "suspected fake" flag and the
                          admin's substantiation request/decision.
    seller_claims         DTI/SEC registration and the marketplace shop name the
                          moderator cross-checks.

product_aliases (§5, §6)  synonyms maintained through canonicalization, with
                          trigram indexes for typo-tolerant search.

questions / question_subscriptions (§7, QA-045, QA-058)
    best_answer_picked_by_id/_at  who picked the Best Answer, and when.
    question_subscriptions        "Notify me" on a question.

price_history (§16)
    hold_reason           why an observation waits for an admin (outlier, or no
                          baseline yet). The one-price-per-review index now
                          applies to the composer's price only, so a reviewer can
                          report later prices against the same review.

commissions / marketplace_remittances (§15, §19)
    platform, cleared_at  a commission becomes withdrawable only when the
                          marketplace's own payout for its cycle has been
                          received and reconciled. Existing commissions were
                          already credited under the old rule; they are
                          backfilled as cleared so no balance moves.

New enum values (moderation_action, moderation_reason) cannot be dropped by
PostgreSQL; the downgrade leaves them in place, unused.

Revision ID: 0050_business_rules
Revises: 0049_report_resolution
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0050_business_rules"
down_revision = "0049_report_resolution"
branch_labels = None
depends_on = None

NEW_ACTIONS = (
    "cold_start_substitution", "best_answer_pick", "seller_appeal",
    "substantiation_request", "appeal_decision", "track_flip",
    "investigation_set", "investigation_clear", "author_delete",
    "photo_replace", "alias_add", "listing_attach", "remittance_record",
    "cashout_request",
)
NEW_REASONS = ("safety_threat", "personal_information")


def _uuid(name: str, **kw) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), **kw)


def upgrade() -> None:
    for value in NEW_ACTIONS:
        op.execute(f"ALTER TYPE moderation_action ADD VALUE IF NOT EXISTS '{value}'")
    for value in NEW_REASONS:
        op.execute(f"ALTER TYPE moderation_reason ADD VALUE IF NOT EXISTS '{value}'")

    # --- reviews ---------------------------------------------------------
    op.add_column("reviews", _uuid("thread_id", nullable=True))
    op.create_foreign_key("fk_reviews_thread", "reviews", "reviews",
                          ["thread_id"], ["id"], ondelete="SET NULL")
    op.execute("UPDATE reviews SET thread_id = id WHERE thread_id IS NULL")
    op.create_index("ix_reviews_thread_created", "reviews", ["thread_id", "created_at"])
    op.create_index("ix_reviews_product_author", "reviews", ["product_id", "author_id"])
    op.add_column("reviews", sa.Column("photo_replaced_at", sa.DateTime(timezone=True)))
    op.add_column("reviews", sa.Column("removed_by_author_at", sa.DateTime(timezone=True)))
    op.add_column("reviews", sa.Column("removed_after_payout", sa.Boolean(),
                                       nullable=False, server_default=sa.false()))

    # --- products ----------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_name_trgm ON products "
               "USING gin (lower(canonical_name) gin_trgm_ops)")

    # --- users ---------------------------------------------------------------
    op.add_column("users", sa.Column("is_under_investigation", sa.Boolean(),
                                     nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("is_claimed_seller", sa.Boolean(),
                                     nullable=False, server_default=sa.false()))
    op.execute("""
        UPDATE users SET is_claimed_seller = true
        WHERE id IN (SELECT claimed_by_id FROM sellers
                     WHERE claimed_by_id IS NOT NULL AND claim_status = 'claimed')
    """)

    # --- review_votes --------------------------------------------------------
    op.add_column("review_votes", sa.Column("vote_weight", sa.Numeric(8, 4)))
    op.add_column("review_votes", sa.Column("trust_stage_snapshot", sa.SmallInteger()))

    # --- moderation_logs -----------------------------------------------------
    source = sa.Enum("user_reported", "system_detected", name="report_source")
    source.create(op.get_bind(), checkfirst=True)
    op.add_column("moderation_logs", sa.Column("report_source", source))
    op.execute("""
        UPDATE moderation_logs
        SET report_source = CASE WHEN reporter_id IS NULL THEN 'system_detected'
                                 ELSE 'user_reported' END::report_source
        WHERE action = 'report'
    """)

    # --- sellers -------------------------------------------------------------
    op.add_column("seller_reviews", sa.Column("order_id", sa.String(64)))
    # §8/§9: a claimed seller responds publicly; it can never remove or hide.
    op.add_column("seller_reviews", sa.Column("seller_response", sa.Text()))
    op.add_column("seller_reviews", sa.Column("seller_response_at", sa.DateTime(timezone=True)))
    op.add_column("seller_claims", sa.Column("registration_kind", sa.String(8)))
    op.add_column("seller_claims", sa.Column("registration_number", sa.String(64)))
    op.add_column("seller_claims", sa.Column("registered_business_name", sa.String(200)))
    op.add_column("seller_claims", sa.Column("marketplace_shop_name", sa.String(160)))
    op.create_check_constraint(
        "ck_seller_claim_registration_kind", "seller_claims",
        "registration_kind IS NULL OR registration_kind IN ('dti', 'sec')")

    op.create_table(
        "seller_review_appeals",
        _uuid("id", primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid("seller_review_id", nullable=False),
        _uuid("seller_id", nullable=False),
        _uuid("appellant_id", nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("substantiation_request", sa.Text()),
        sa.Column("substantiation_requested_at", sa.DateTime(timezone=True)),
        sa.Column("substantiation_response", sa.Text()),
        sa.Column("substantiated_at", sa.DateTime(timezone=True)),
        _uuid("decided_by_id", nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["seller_review_id"], ["seller_reviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["appellant_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('open', 'substantiation_requested', 'upheld', 'dismissed')",
            name="ck_seller_review_appeal_status"),
    )
    op.create_index("ix_seller_review_appeals_status", "seller_review_appeals",
                    ["status", "created_at"])
    op.create_index("uq_seller_review_appeal_open", "seller_review_appeals",
                    ["seller_review_id"], unique=True,
                    postgresql_where=sa.text("status IN ('open', 'substantiation_requested')"))

    # --- products: aliases -----------------------------------------------------
    op.create_table(
        "product_aliases",
        _uuid("id", primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid("product_id", nullable=False),
        sa.Column("alias", sa.String(160), nullable=False),
        sa.Column("normalized", sa.String(160), nullable=False),
        _uuid("created_by_id", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("product_id", "normalized", name="uq_product_alias"),
    )
    op.execute("CREATE INDEX ix_product_aliases_trgm ON product_aliases "
               "USING gin (normalized gin_trgm_ops)")

    # --- Q&A -------------------------------------------------------------------
    op.add_column("questions", _uuid("best_answer_picked_by_id", nullable=True))
    op.create_foreign_key("fk_questions_best_picked_by", "questions", "users",
                          ["best_answer_picked_by_id"], ["id"], ondelete="SET NULL")
    op.add_column("questions", sa.Column("best_answer_picked_at", sa.DateTime(timezone=True)))
    op.create_table(
        "question_subscriptions",
        _uuid("question_id", primary_key=True),
        _uuid("user_id", primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # --- price history ------------------------------------------------------------
    op.add_column("price_history", sa.Column("hold_reason", sa.String(40)))
    op.drop_index("uq_price_history_review", table_name="price_history")
    op.create_index("uq_price_history_review", "price_history", ["review_id"], unique=True,
                    postgresql_where=sa.text("review_id IS NOT NULL AND source = 'review'"))

    # --- money ------------------------------------------------------------------
    platform = postgresql.ENUM(name="platform", create_type=False)
    op.add_column("commissions", sa.Column("platform", platform))
    op.add_column("commissions", sa.Column("cleared_at", sa.DateTime(timezone=True)))
    op.execute("""
        UPDATE commissions c SET platform = rl.platform
        FROM (SELECT DISTINCT ON (review_id) review_id, platform FROM referral_links
              ORDER BY review_id, created_at DESC) rl
        WHERE rl.review_id = c.review_id AND c.platform IS NULL
    """)
    op.execute("UPDATE commissions SET cleared_at = created_at WHERE cleared_at IS NULL")
    op.create_index("ix_commissions_uncleared", "commissions", ["platform", "cycle_month"],
                    postgresql_where=sa.text("cleared_at IS NULL"))
    op.create_table(
        "marketplace_remittances",
        _uuid("id", primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("platform", platform, nullable=False),
        sa.Column("cycle_month", sa.Date(), nullable=False),
        sa.Column("amount_received", sa.Numeric(12, 2), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.Text()),
        _uuid("recorded_by_id", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("platform", "cycle_month", name="uq_remittance_cycle"),
        sa.CheckConstraint("amount_received >= 0", name="ck_remittance_non_negative"),
    )

    # PostgREST must not see the new tables either (0029's rule).
    for table in ("seller_review_appeals", "product_aliases",
                  "question_subscriptions", "marketplace_remittances"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON {table} FROM anon;
              END IF;
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON {table} FROM authenticated;
              END IF;
            END $$;""")


def downgrade() -> None:
    op.drop_table("marketplace_remittances")
    op.drop_index("ix_commissions_uncleared", table_name="commissions")
    op.drop_column("commissions", "cleared_at")
    op.drop_column("commissions", "platform")

    op.drop_index("uq_price_history_review", table_name="price_history")
    op.create_index("uq_price_history_review", "price_history", ["review_id"], unique=True,
                    postgresql_where=sa.text("review_id IS NOT NULL"))
    op.drop_column("price_history", "hold_reason")

    op.drop_table("question_subscriptions")
    op.drop_column("questions", "best_answer_picked_at")
    op.drop_constraint("fk_questions_best_picked_by", "questions", type_="foreignkey")
    op.drop_column("questions", "best_answer_picked_by_id")

    op.drop_table("product_aliases")

    op.drop_index("uq_seller_review_appeal_open", table_name="seller_review_appeals")
    op.drop_index("ix_seller_review_appeals_status", table_name="seller_review_appeals")
    op.drop_table("seller_review_appeals")
    op.drop_constraint("ck_seller_claim_registration_kind", "seller_claims", type_="check")
    for column in ("marketplace_shop_name", "registered_business_name",
                   "registration_number", "registration_kind"):
        op.drop_column("seller_claims", column)
    op.drop_column("seller_reviews", "seller_response_at")
    op.drop_column("seller_reviews", "seller_response")
    op.drop_column("seller_reviews", "order_id")

    op.drop_column("moderation_logs", "report_source")
    sa.Enum(name="report_source").drop(op.get_bind(), checkfirst=True)

    op.drop_column("review_votes", "trust_stage_snapshot")
    op.drop_column("review_votes", "vote_weight")

    op.drop_column("users", "is_claimed_seller")
    op.drop_column("users", "is_under_investigation")

    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm")
    # 0049 reads products.avg_rating as a mean: restore means on the way down.
    op.execute("""
        UPDATE products p
        SET avg_rating = COALESCE((
            SELECT round(avg(r.star_rating)::numeric, 2) FROM reviews r
            WHERE r.product_id = p.id AND r.is_removed = false
              AND r.published_at IS NOT NULL), 0)
    """)

    op.drop_column("reviews", "removed_after_payout")
    op.drop_column("reviews", "removed_by_author_at")
    op.drop_column("reviews", "photo_replaced_at")
    op.drop_index("ix_reviews_product_author", table_name="reviews")
    op.drop_index("ix_reviews_thread_created", table_name="reviews")
    op.drop_constraint("fk_reviews_thread", "reviews", type_="foreignkey")
    op.drop_column("reviews", "thread_id")

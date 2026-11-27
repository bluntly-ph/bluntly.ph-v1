"""commissions (FR-6, §3.3).

Reconciled from admin-imported Shopee/Lazada CSVs. The 40/30/30 split is stored
as explicit share columns. Idempotency: (csv_source, row_reference) is unique so
re-uploading the same CSV cannot double-count.

Deviation (changelog): the spec's polymorphic `commissions.review_id` TEXT (which
could point at a review OR an answer with no FK integrity) is replaced by a
`target_type` enum + nullable typed FKs `review_id` / `answer_id`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import CommissionTarget, ContractStatus, MembershipTier, Platform


class Commission(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "commissions"
    __table_args__ = (
        UniqueConstraint("csv_source", "row_reference", name="uq_commission_csv_row"),
        CheckConstraint(
            "(target_type = 'review' AND review_id IS NOT NULL AND answer_id IS NULL) OR "
            "(target_type = 'answer' AND answer_id IS NOT NULL AND review_id IS NULL)",
            name="ck_commission_target",
        ),
        # A QA sandbox test earning is the reviewer's alone: no platform
        # revenue and nothing for the Honesty Fund, so it can never be counted
        # as either (0058).
        CheckConstraint(
            "NOT is_test OR (platform_share = 0 AND honesty_fund_share = 0)",
            name="ck_commission_test_no_revenue",
        ),
        # At most one test earning per review (0058).
        Index("uq_commission_one_qa_test", "review_id", unique=True,
              postgresql_where=text("is_test")),
        # A reviewer's statement, dashboard and cashout check (0061).
        Index("ix_commissions_reviewer_cycle", "reviewer_id", "cycle_month"),
    )

    commission_id: Mapped[str | None] = mapped_column(String(48), unique=True, index=True)

    target_type: Mapped[CommissionTarget] = mapped_column(
        Enum(CommissionTarget, name="commission_target"), nullable=False
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="SET NULL")
    )
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answers.id", ondelete="SET NULL")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL")
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # Tier snapshot at reconciliation time (M2 slice 6) — immutable audit.
    reviewer_tier: Mapped[MembershipTier | None] = mapped_column(
        Enum(MembershipTier, name="membership_tier"))
    reviewer_share_bps: Mapped[int | None] = mapped_column(Integer)
    # Contract state at reconciliation (M3 slice 10): explains why the reviewer's
    # share was what it was, forever (0 bps once the contract isn't active).
    contract_status: Mapped[ContractStatus | None] = mapped_column(
        Enum(ContractStatus, name="contract_status"))

    gross_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    platform_share: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reviewer_share: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    honesty_fund_share: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="PHP", server_default="PHP")

    csv_source: Mapped[str] = mapped_column(String(255), nullable=False)
    row_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    order_status: Mapped[str | None] = mapped_column(String(64))
    is_disputed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    cycle_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)  # YYYY-MM-01

    #: Set on a reversal row, pointing at the commission it undoes (0031).
    #:
    #: A returned sale does not rewrite the original entry — that destroys the
    #: audit trail and makes the ledger disagree with what actually happened.
    #: It writes a second row whose shares are the negation of the first, and
    #: the pair sums to the truth. A partial unique index enforces at most one
    #: reversal per original, so a repeated `returned` cannot reverse twice.
    #:
    #: The `negative commission shares` invariant excludes these rows: it exists
    #: to catch a rounding bug that could push a *forward* share to -0.01, which
    #: is a different thing from a deliberate, paired reversal.
    reverses_commission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commissions.id", ondelete="SET NULL"))

    # Business Rules §15: "a postback is evidence, never money". A commission is
    # withdrawable only once the marketplace's own payout for its platform and
    # cycle has reached Bluntly and been reconciled (`marketplace_remittances`).
    platform: Mapped[Platform | None] = mapped_column(Enum(Platform, name="platform"))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: A QA sandbox test earning (0058; `qa_sandbox_service`): credited by a
    #: moderator to a named QA tester so the payout flow can be tested with no
    #: marketplace sale behind it. Real wallet money for the tester's own
    #: balance and cashout, never platform revenue or Honesty Fund pool.
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false",
                                          nullable=False)


class MarketplaceRemittance(Base, UUIDPrimaryKey):
    """The marketplace's payout for one platform and cycle, received and reconciled.

    Recording it is what clears that cycle's commissions for withdrawal
    (Business Rules §15, §19). One row per platform per cycle.
    """

    __tablename__ = "marketplace_remittances"
    __table_args__ = (
        UniqueConstraint("platform", "cycle_month", name="uq_remittance_cycle"),
        CheckConstraint("amount_received >= 0", name="ck_remittance_non_negative"),
    )

    platform: Mapped[Platform] = mapped_column(Enum(Platform, name="platform"), nullable=False)
    cycle_month: Mapped[date] = mapped_column(Date, nullable=False)
    amount_received: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(Text)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

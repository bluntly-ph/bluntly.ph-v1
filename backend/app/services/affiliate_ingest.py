"""Import a provider export into the canonical affiliate transaction store.

This is the money path, so its shape is deliberate:

  parse -> identify -> classify -> decide -> apply

Each step has one owner. `report_formats.parse_lifecycle` turns bytes into rows
with a stable provider identity. `affiliate_status` says what the provider's
vocabulary means. `affiliate_transitions` says what the ledger must do about a
change. This module only sequences them and writes the result.

WHY IT REPLACES THE OLD PATH FOR LIFECYCLE ROWS. Two defects, both latent only
because production has no commissions yet:

* Cross-file double credit. The old importer's idempotency key is
  `(csv_source=filename:sha256, row_reference=line)`. Re-importing the same
  file is caught; a DIFFERENT export containing the same order is not, and the
  order is credited twice. Here the key is the provider's own identity for the
  transaction, so the same order is the same row no matter which file carries
  it or what line it sits on.
* Returns could never reverse. The old parser drops non-payable rows, and a
  return arrives as a non-payable row — so it vanished from the import and the
  earlier `completed` row stood forever. Every row is kept now.

WITHDRAWABILITY. Commission is recognised only when the provider reports
finality (`completed`). A pending transaction never credits a wallet, which is
the owner's rule that affiliate commission is not withdrawable before provider
settlement.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commission import Commission
from app.models.enums import (
    AffiliateTxStatus,
    CommissionTarget,
    ModerationAction,
    Platform,
    SettlementStatus,
)
from app.models.moderation import ModerationLog
from app.models.postback import AffiliatePostback
from app.models.review import ReferralLink, Review
from app.models.user import User
from app.services import report_formats, wallet
from app.services.affiliate_status import map_status
from app.services.affiliate_transitions import Effect, evaluate
from app.services.commission_service import _tier_bps
from app.services.earnings import held_for_routing, split_for_review

HELD_REASON = "held: awaiting a Super Admin's 2.5-star routing"

ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _to_cents(amount: Decimal) -> Decimal:
    """The provider's figure as the ledger will actually store it.

    Providers report more precision than money has — Shopee's commissions carry
    five decimal places — and `split_commission_tiered` quantizes to the centavo
    before splitting. Summing the raw values would show a moderator a preview
    total that never matches the entries the import goes on to write.
    """
    return Decimal(amount or 0).quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass
class RowOutcome:
    """What happened to one provider row, and why."""

    line: int
    identity: str
    from_status: str | None
    to_status: str
    effect: str
    applied: bool
    reason: str
    amount: Decimal = ZERO
    #: Set only on a reversal that could not be fully recovered.
    unrecovered: Decimal = ZERO
    #: created | updated | unchanged | invalid
    provenance: str = "unchanged"


@dataclass
class ImportSummary:
    format: str
    total_rows: int
    recognised: int = 0
    reversed_count: int = 0
    dropped: int = 0
    #: Rows the LEDGER did nothing about. Named apart from the provenance
    #: `unchanged` below because they are different axes and a first import
    #: reports both — 108 rows created, 13 of which moved no money.
    no_ledger_effect: int = 0
    #: Transitions the matrix refuses. Never applied, always reported: an
    #: unlisted transition means the provider did something nobody has reasoned
    #: about, and guessing at it moves money.
    refused: int = 0
    #: Rows whose sale is real but cannot be traced to a review, so there is
    #: nobody to pay. Recorded, never dropped.
    unattributed: int = 0
    #: Owner decision A: attributed to a 2.5-star thread awaiting a Super Admin.
    held_pending_routing: int = 0
    unidentified: int = 0
    #: Row provenance, independent of the ledger effect: whether this import
    #: opened a new canonical transaction, changed one, or left it alone. A
    #: moderator asking "what will this file do" wants both — a row can be
    #: `updated` with no money effect at all (a status refinement), and one
    #: that is `unchanged` is proof the import is safely repeatable.
    created: int = 0
    updated: int = 0
    #: Rows this file said nothing new about. Proof the import is repeatable.
    unchanged: int = 0
    #: Rows that could not be used: no stable identity, or a transition the
    #: matrix refuses. Counted apart from `warnings`, which are usable.
    invalid: int = 0
    #: Usable but needing a human eye — currently, a real sale with no
    #: attributable review.
    warnings: int = 0
    #: The canonical lifecycle this file describes, before any ledger effect.
    lifecycle: dict[str, int] = field(default_factory=dict)
    recognised_amount: Decimal = ZERO
    reversed_amount: Decimal = ZERO
    #: Money a reversal could not claw back because it had already been paid
    #: out. Bluntly absorbs this; the wallet is never driven negative.
    unrecovered_amount: Decimal = ZERO
    dry_run: bool = True
    outcomes: list[RowOutcome] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "format": self.format, "total_rows": self.total_rows,
            "recognised": self.recognised, "reversed": self.reversed_count,
            "dropped": self.dropped,
            "no_ledger_effect": self.no_ledger_effect,
            "unchanged": self.unchanged,
            "refused": self.refused, "unattributed": self.unattributed,
            "held_pending_routing": self.held_pending_routing,
            "unidentified": self.unidentified,
            "created": self.created, "updated": self.updated,
            "invalid": self.invalid, "warnings": self.warnings,
            "lifecycle": dict(self.lifecycle),
            "recognised_amount": str(self.recognised_amount),
            "reversed_amount": str(self.reversed_amount),
            "unrecovered_amount": str(self.unrecovered_amount),
            "dry_run": self.dry_run,
        }


def _attribute(db: Session, row: report_formats.LifecycleRow) -> Review | None:
    """The review this sale belongs to, or None.

    The affiliate sub-ID is the only one of our own identifiers a marketplace
    echoes back, so it is the attribution key. An unattributable row is still
    recorded — the sale happened, we just cannot say whose review caused it,
    and deleting that fact would hide a real gap in attribution.
    """
    if not row.sub_id:
        return None
    link = db.scalar(select(ReferralLink).where(ReferralLink.sub_id == row.sub_id))
    if link is None:
        return None
    review = db.get(Review, link.review_id)
    return review if review is not None and review.author_id is not None else None


def _fill_item_detail(db: Session, postback: AffiliatePostback,
                      row: report_formats.LifecycleRow,
                      products: dict[str, uuid.UUID | None]) -> None:
    """Keep what the commission breakdown sums (0096): the item's own
    commission and purchase value at the report's precision, its variant, and
    our catalogue product for it (Item id -> the product carrying that Shopee
    listing; `products` caches one lookup per item for the file)."""
    if row.platform != "shopee":
        return
    from app.services.product_matching import product_for_listing

    detail = report_formats.shopee_item_detail(row.raw)
    postback.item_commission = detail["item_commission"]
    postback.purchase_value = detail["purchase_value"]
    postback.item_qty = detail["item_qty"]
    postback.source_item_id = detail["source_item_id"]
    postback.source_model_id = detail["source_model_id"]
    postback.product_name = detail["product_name"]
    postback.seller_name = detail["seller_name"]
    postback.refund_amount = _to_cents(detail["refund_amount"] or ZERO)
    postback.completed_at = detail["completed_at"] or postback.completed_at
    item = detail["source_item_id"]
    if postback.product_id is None and item:
        if item not in products:
            found = product_for_listing(
                db, report_formats.shopee_listing_url(detail["shop_id"], item))
            products[item] = found.id if found else None
        postback.product_id = products[item]


def _recognise(db: Session, postback: AffiliatePostback, review: Review,
               row: report_formats.LifecycleRow, tier_bps: dict) -> Commission:
    """Split the commission, credit the reviewer, and record the entry."""
    reviewer = db.get(User, review.author_id)
    # Business Rules §14: flat 40/30/30, no tiers, no contracts.
    split, bps = split_for_review(row.gross_amount, review, reviewer)
    try:
        platform = Platform(row.platform)
    except ValueError:
        platform = None

    occurred = row.occurred_on or (review.published_at or review.created_at).date()
    commission = Commission(
        commission_id=f"com_{uuid.uuid4().hex[:12]}",
        target_type=CommissionTarget.review,
        review_id=review.id,
        reviewer_id=reviewer.id,
        reviewer_share_bps=bps,
        platform=platform,
        # §15: "a postback is evidence, never money" — withdrawable only once
        # the marketplace's own payout for this cycle is recorded.
        cleared_at=None,
        currency=row.currency,
        # The provider's identity, not a filename and line: that is what makes
        # a re-import from a different export a no-op instead of a double
        # credit.
        csv_source=f"{row.platform}:lifecycle",
        row_reference=row.identity,
        order_status=postback.raw_item_status or postback.order_status,
        cycle_month=date(occurred.year, occurred.month, 1),
        **split,
    )
    db.add(commission)
    wallet.adjust(db, reviewer.id, split["reviewer_share"])
    db.flush()
    return commission


def _reverse(db: Session, postback: AffiliatePostback) -> tuple[Decimal, Decimal]:
    """Undo a recognised commission. Returns (reversed, unrecovered).

    A reversal is a NEW opposing entry pointing at the original, never an edit
    of it: editing destroys the record that the money was once recognised, and
    that record is the whole audit trail.

    The owner's policy for a return that arrives after payout is that Bluntly
    absorbs the shortfall — a user must never be pushed into debt by a buyer's
    return they had no part in. So the wallet is debited only by what is
    actually there, the remainder is recorded on the transaction for
    reconciliation, and `wallet_balance >= 0` holds by construction rather than
    by the database refusing the write.
    """
    original = (db.get(Commission, postback.reconciled_commission_id)
                if postback.reconciled_commission_id else None)
    if original is None:
        return ZERO, ZERO

    already = db.scalar(select(Commission.id).where(
        Commission.reverses_commission_id == original.id))
    if already is not None:
        # The partial unique index enforces this too; catching it here means a
        # re-import reports "unchanged" instead of raising on a constraint.
        return ZERO, ZERO

    reviewer_share = original.reviewer_share or ZERO
    reviewer = db.get(User, original.reviewer_id) if original.reviewer_id else None
    balance = (reviewer.wallet_balance if reviewer is not None else ZERO) or ZERO
    recoverable = min(reviewer_share, balance)
    unrecovered = reviewer_share - recoverable

    db.add(Commission(
        commission_id=f"rev_{uuid.uuid4().hex[:12]}",
        target_type=original.target_type,
        review_id=original.review_id,
        reviewer_id=original.reviewer_id,
        reviewer_tier=original.reviewer_tier,
        reviewer_share_bps=original.reviewer_share_bps,
        contract_status=original.contract_status,
        currency=original.currency,
        csv_source=original.csv_source,
        # NOT the original's reference. `commissions` carries
        # UNIQUE (csv_source, row_reference), so copying both would make the
        # reversal collide with the entry it is undoing and no reversal could
        # ever be written. The suffix keeps the provider identity legible while
        # making the pair distinct; `uq_commission_one_reversal` already
        # guarantees there is at most one of these per original.
        row_reference=f"{original.row_reference}#reversal",
        order_status="returned",
        cycle_month=original.cycle_month,
        reverses_commission_id=original.id,
        # The exact negation, so the pair sums to zero and the invariant
        # "a reversal opposes its original" holds.
        gross_amount=-(original.gross_amount or ZERO),
        platform_share=-(original.platform_share or ZERO),
        reviewer_share=-reviewer_share,
        honesty_fund_share=-(original.honesty_fund_share or ZERO),
    ))
    if reviewer is not None and recoverable > ZERO:
        wallet.adjust(db, reviewer.id, -recoverable)
    db.flush()
    return reviewer_share, unrecovered


def _run(db: Session, file_bytes: bytes, *, dry_run: bool) -> ImportSummary:
    parsed = report_formats.parse_lifecycle(file_bytes)
    summary = ImportSummary(format=parsed.format, total_rows=len(parsed.rows),
                            unidentified=len(parsed.unidentified),
                            invalid=len(parsed.unidentified), dry_run=dry_run)
    if parsed.format == "unknown" or parsed.errors:
        return summary
    # A seeded test report never becomes money on production (owner plan,
    # seeded_affiliate_reports). Checked before a single row is touched.
    from app.services.seeded_affiliate_reports import refuse_seeded_rows_in_production
    refuse_seeded_rows_in_production(
        [row.order_ref for row in parsed.rows] + [row.identity for row in parsed.rows])

    tier_bps = _tier_bps(db)
    platform = Platform(parsed.rows[0].platform) if parsed.rows else None
    products: dict[str, uuid.UUID | None] = {}

    for row in parsed.rows:
        mapped = map_status(row.platform, row.raw)
        postback = db.scalar(select(AffiliatePostback).where(
            AffiliatePostback.platform == platform,
            AffiliatePostback.external_sub_order_id == row.identity))
        current = postback.canonical_status if postback is not None else None
        decision = evaluate(current, mapped.status)

        summary.lifecycle[mapped.status.value] = (
            summary.lifecycle.get(mapped.status.value, 0) + 1)

        outcome = RowOutcome(
            line=row.line, identity=row.identity,
            from_status=current.value if current else None,
            to_status=mapped.status.value, effect=decision.effect.value,
            applied=False, reason=decision.reason,
            amount=_to_cents(row.gross_amount),
        )

        if not decision.allowed:
            summary.refused += 1
            summary.invalid += 1
            outcome.provenance = "invalid"
            summary.outcomes.append(outcome)
            continue

        # Provenance is decided by whether the row already existed and whether
        # this file says anything new about it, NOT by the ledger effect.
        is_new = postback is None
        changed = is_new or current is not mapped.status
        outcome.provenance = (
            "created" if is_new else "updated" if changed else "unchanged")

        if outcome.provenance == "created":
            summary.created += 1
        elif outcome.provenance == "updated":
            summary.updated += 1
        else:
            summary.unchanged += 1

        # A sale that was completed but unattributable stays `completed`, so a
        # later import evaluates completed -> completed and gets `none` — and
        # the money is orphaned forever, even once the referral link exists.
        # Retrying attribution here is safe precisely because nothing was ever
        # recognised for it: there is no entry to double.
        # `current` is the STORED status, read before anything is written.
        effect = decision.effect
        if (effect is Effect.none
                and postback is not None
                and current is AffiliateTxStatus.completed
                and mapped.status is AffiliateTxStatus.completed
                and postback.settlement_status is SettlementStatus.not_earned
                and postback.reconciled_commission_id is None):
            effect = Effect.recognise
            outcome.effect = effect.value
            outcome.reason = "previously unattributable; retrying attribution"

        if dry_run:
            # The preview must say what the import WILL do: a sale whose
            # sub-ID matches no review is credited to nobody, so it is counted
            # as unattributed here too, never as a recognition. Reading the
            # link writes nothing.
            attributed = _attribute(db, row) if effect is Effect.recognise else None
            if effect is Effect.recognise and attributed is None:
                summary.unattributed += 1
                summary.warnings += 1
                outcome.reason = "no attributable review"
            elif effect is Effect.recognise and held_for_routing(attributed):
                summary.held_pending_routing += 1
                outcome.reason = HELD_REASON
            else:
                _tally(summary, effect, outcome.amount, ZERO)
            outcome.applied = False
            summary.outcomes.append(outcome)
            continue

        if postback is None:
            postback = AffiliatePostback(
                # `platform` is the enum column and the only required one;
                # there is no separate `provider` field, and `event_type`
                # defaults to "order".
                platform=platform,
                external_order_id=row.order_ref,
                external_sub_order_id=row.identity,
                review_sub_id=row.sub_id,
                currency=row.currency,
                raw=row.raw,
            )
            db.add(postback)

        # The provider's own words, kept verbatim beside our translation.
        postback.canonical_status = mapped.status
        postback.order_status = mapped.raw_order_status
        postback.raw_item_status = mapped.raw_item_status
        postback.status_reason = mapped.reason[:255]
        postback.reported_payout = row.gross_amount
        postback.source_import_id = _import_id(file_bytes)
        _fill_item_detail(db, postback, row, products)

        unrecovered = ZERO

        if effect is Effect.recognise:
            review = _attribute(db, row)
            if review is None:
                # Real sale, nobody to pay. Recorded so the gap is visible.
                summary.unattributed += 1
                summary.warnings += 1
                postback.settlement_status = SettlementStatus.not_earned
                outcome.reason = "no attributable review"
                summary.outcomes.append(outcome)
                db.flush()
                continue
            if held_for_routing(review):
                # Owner decision A: a Super Admin has not routed this 2.5-star
                # thread. Left `not_earned` and unreconciled, which is exactly
                # the state the retry above picks up on a later import.
                summary.held_pending_routing += 1
                postback.settlement_status = SettlementStatus.not_earned
                outcome.reason = HELD_REASON
                summary.outcomes.append(outcome)
                db.flush()
                continue
            commission = _recognise(db, postback, review, row, tier_bps)
            postback.reconciled_commission_id = commission.id
            postback.review_id = review.id
            postback.reviewer_id = review.author_id
            postback.product_id = review.product_id or postback.product_id
            postback.settlement_status = SettlementStatus.earned
        elif effect is Effect.reverse:
            reversed_amount, unrecovered = _reverse(db, postback)
            outcome.amount = reversed_amount
            outcome.unrecovered = unrecovered
            postback.settlement_status = SettlementStatus.reversed
            postback.unrecovered_amount = unrecovered or None
        elif effect is Effect.drop_pending:
            postback.settlement_status = SettlementStatus.not_earned

        outcome.applied = True
        _tally(summary, effect, outcome.amount, unrecovered)
        summary.outcomes.append(outcome)
        db.flush()

    return summary


def _tally(summary: ImportSummary, effect: Effect, amount: Decimal,
           unrecovered: Decimal) -> None:
    if effect is Effect.recognise:
        summary.recognised += 1
        summary.recognised_amount += amount
    elif effect is Effect.reverse:
        summary.reversed_count += 1
        summary.reversed_amount += amount
        summary.unrecovered_amount += unrecovered
    elif effect is Effect.drop_pending:
        summary.dropped += 1
    else:
        summary.no_ledger_effect += 1


def _import_id(file_bytes: bytes) -> str:
    import hashlib

    return hashlib.sha256(file_bytes).hexdigest()[:16]


def preview(db: Session, file_bytes: bytes) -> ImportSummary:
    """What an import WOULD do. Writes nothing.

    A moderator is about to move money on the strength of a file they did not
    write, produced by a system they do not control. Being able to see the
    effect first — how many recognitions, how many reversals, how much cannot
    be clawed back — is what makes that a decision rather than a leap.
    """
    return _run(db, file_bytes, dry_run=True)


def apply(db: Session, moderator_id: uuid.UUID, filename: str,
          file_bytes: bytes) -> ImportSummary:
    """Import for real, in one transaction."""
    summary = _run(db, file_bytes, dry_run=False)
    db.add(ModerationLog(
        log_id=f"mlog_{uuid.uuid4().hex[:10]}",
        moderator_id=moderator_id, action=ModerationAction.csv_import,
        context={"filename": filename, "import_id": _import_id(file_bytes),
                 **summary.as_dict()},
    ))
    db.commit()
    return summary

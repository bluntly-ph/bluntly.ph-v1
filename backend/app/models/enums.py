"""Postgres enum types shared by models and migrations.

ADR-005 resolves the spec's undefined `verification_tier` / `member_type` enums.
Only `tier_0` is active at launch; the rest are enumerated now so the schema is
concrete (see the deviations changelog).
"""

from __future__ import annotations

import enum


class MemberRole(str, enum.Enum):
    """Owner decisions B-D (2026-09-28): there is no moderator role.

    administrator  the operational approval role (queues, claims, links,
                   takedowns, support); no user management
    super_admin    everything an administrator does, plus user and role
                   management and the 2.5-star special routing decision
    """

    user = "user"
    seller = "seller"
    administrator = "administrator"
    super_admin = "super_admin"


#: The two staff roles. Every operational staff endpoint admits both.
STAFF_ROLES: tuple[MemberRole, ...] = (MemberRole.administrator, MemberRole.super_admin)


class MemberType(str, enum.Enum):
    shopper = "shopper"
    seller = "seller"
    administrator = "administrator"


class Language(str, enum.Enum):
    en = "en"
    fil = "fil"
    tl_x_taglish = "tl-x-taglish"


class MembershipTier(str, enum.Enum):
    """Membership tiers (M1). Distinct from trust stages (reputation)."""

    special = "special"
    founding = "founding"
    standard = "standard"


class ProductStatus(str, enum.Enum):
    pending = "pending"          # submitted via source_url, awaiting canonicalization
    canonicalized = "canonicalized"
    rejected = "rejected"


class Platform(str, enum.Enum):
    shopee = "shopee"
    lazada = "lazada"
    amazon = "amazon"   # M2: affiliate attribution for Amazon
    other = "other"


class ReferralLinkStatus(str, enum.Enum):
    active = "active"
    revoked = "revoked"


class Verdict(str, enum.Enum):
    yes_absolutely = "yes_absolutely"
    it_depends = "it_depends"
    hard_pass = "hard_pass"


class VerificationStatus(str, enum.Enum):
    verified = "verified"
    unverified = "unverified"


class VerificationTier(str, enum.Enum):
    tier_0 = "tier_0"
    tier_1 = "tier_1"


class EarnEligibleStatus(str, enum.Enum):
    none = "none"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    monetized = "monetized"       # >=3 stars -> affiliate link attached
    honesty_fund = "honesty_fund"  # <=2 stars -> Honesty Fund pool
    #: Owner decision A (2026-09-28): "It depends" at exactly 2.5 stars. An
    #: administrator approved its earnings; only a Super Admin decides where
    #: they go (reviews.special_route). Nothing earns while it waits.
    pending_superadmin_routing = "pending_superadmin_routing"


class SpecialRoute(str, enum.Enum):
    """A Super Admin's destination for a 2.5-star "It depends" thread."""

    #: The Honesty Fund track, exactly as a Hard pass would be.
    honesty_fund = "honesty_fund"
    #: The commission route, with the reviewer's share kept by the platform.
    platform = "platform"


class QuestionDirectedTo(str, enum.Enum):
    buyers = "buyers"
    seller = "seller"


class ConversionStatus(str, enum.Enum):
    clicked = "clicked"
    converted = "converted"
    cancelled = "cancelled"


class CommissionTarget(str, enum.Enum):
    review = "review"
    answer = "answer"


class ModerationTargetType(str, enum.Enum):
    review = "review"
    answer = "answer"
    seller_review = "seller_review"
    question = "question"
    user = "user"
    #: QA-069 (0055): a reader reports another member's comment.
    comment = "comment"


class ModerationAction(str, enum.Enum):
    report = "report"
    approve = "approve"
    reject = "reject"
    remove = "remove"
    penalize = "penalize"
    suspend = "suspend"
    restore = "restore"
    override = "override"
    escalate = "escalate"
    # Admin/audit actions (moderation_logs doubles as the audit log — see changelog).
    csv_import = "csv_import"
    payout = "payout"
    honesty_fund_distribution = "honesty_fund_distribution"
    # Referral link flow (M2 slice 1).
    affiliate_link_attach = "affiliate_link_attach"
    affiliate_link_revoke = "affiliate_link_revoke"
    publish = "publish"
    unpublish = "unpublish"
    # Privacy/security enhancement (owner-approved, not contractually required):
    # a moderator opening private proof of purchase leaves an audit trail. The
    # record carries WHO and WHICH REVIEW and nothing else - never the object
    # key, the signed URL, or anything from the receipt itself.
    receipt_view = "receipt_view"
    # Staff role administration (owner-approved). A role change moves no money
    # and touches no content, which is exactly why it needs its own audit
    # action: it is otherwise invisible, and "who made this person a
    # moderator" is a question that gets asked after something has gone wrong.
    # Grant and revoke are separate values so the two can be counted apart
    # without parsing notes.
    role_grant = "role_grant"
    role_revoke = "role_revoke"
    cold_start_substitution = "cold_start_substitution"
    best_answer_pick = "best_answer_pick"
    seller_appeal = "seller_appeal"
    substantiation_request = "substantiation_request"
    appeal_decision = "appeal_decision"
    track_flip = "track_flip"
    investigation_set = "investigation_set"
    investigation_clear = "investigation_clear"
    author_delete = "author_delete"
    #: Owner decision A: a Super Admin routed a 2.5-star "It depends" thread.
    special_routing = "special_routing"
    photo_replace = "photo_replace"
    alias_add = "alias_add"
    #: 0074: an alias taken off a product (the Edit modal's chip x).
    alias_remove = "alias_remove"
    # Seller support requests (0062): created, assigned, answered, status set.
    support_request = "support_request"
    listing_attach = "listing_attach"
    remittance_record = "remittance_record"
    cashout_request = "cashout_request"
    # QA sandbox test earnings (0058): the owner names the QA testers, and a
    # moderator credits one of their published reviews with a clearly labelled
    # test earning so the payout flow can be exercised end to end in PayPal
    # sandbox. Separate values so an audit can count them apart from money.
    qa_tester_add = "qa_tester_add"
    qa_tester_remove = "qa_tester_remove"
    qa_test_credit = "qa_test_credit"
    # Inbox (0076): assign, status, close / reopen, move to Support.
    conversation = "conversation"
    # Store ↔ product links (0077): approve / reject.
    store_product = "store_product"
    # Store give-up (0078): the owner releases a store they run.
    store_release = "store_release"
    # Admin Export CSV (0079): who exported what, for which period.
    data_export = "data_export"
    # Integration settings (0080): PayMongo keys saved / removed (never the keys).
    integration_change = "integration_change"
    # Product CSV import (0089): who imported, how many created / attached / skipped.
    product_import = "product_import"


class ReportResolution(str, enum.Enum):
    """How a filed report was closed (owner requirement, 2026-09-16).

    Four outcomes, because a moderator looking at a report has four honest
    answers: the content stands, the content came down, content that was down
    goes back up, or this is above my pay grade. The action taken on the content
    itself is audited separately by the service that performs it; this records
    the report's own outcome so the queue can stop showing it.
    """

    dismissed = "dismissed"
    content_removed = "content_removed"
    content_restored = "content_restored"
    escalated = "escalated"


class ModerationReason(str, enum.Enum):
    fake_proof = "fake_proof"
    plagiarized = "plagiarized"
    spam = "spam"
    harassment = "harassment"
    conflict_of_interest = "conflict_of_interest"
    seller_posing_as_buyer = "seller_posing_as_buyer"
    other = "other"
    #: Safety and doxxing-adjacent reasons escalate near-immediately (§12).
    safety_threat = "safety_threat"
    personal_information = "personal_information"
    #: The product itself is fake (0055). A fraud category for the admin
    #: priority tiers, with fake_proof and seller_posing_as_buyer.
    counterfeit = "counterfeit"

class VoteDirection(str, enum.Enum):
    up = "up"
    down = "down"


class ReaderKind(str, enum.Enum):
    """Which identity column on a reading session is populated.

    Exactly one of `reader_ref` / `anon_ref` is non-null, enforced by CHECK
    constraints in migration 0041. This enum names which.
    """

    anon = "anon"
    user = "user"


class TokenKind(str, enum.Enum):
    """Token ledger entry kinds (M2 slice 7; request-board kinds added M3 slice 9)."""

    earn_review_published = "earn_review_published"
    earn_commission = "earn_commission"
    admin_grant = "admin_grant"
    admin_deduct = "admin_deduct"
    adjustment = "adjustment"
    # M3 slice 9 — request board escrow/reward flow.
    spend_request_escrow = "spend_request_escrow"
    earn_request_reward = "earn_request_reward"
    refund_request_escrow = "refund_request_escrow"
    platform_topup = "platform_topup"


class PayoutStatus(str, enum.Enum):
    """Payout lifecycle (M3 slice 11). The wallet is debited at `scheduled` and
    refunded on `failed`/`cancelled` — so scheduled/processing/paid are all
    'money has left the wallet' states."""

    scheduled = "scheduled"
    processing = "processing"
    paid = "paid"
    failed = "failed"
    cancelled = "cancelled"


class PayoutMethod(str, enum.Enum):
    paypal_sandbox = "paypal_sandbox"
    paypal_live = "paypal_live"
    manual = "manual"


class ContractStatus(str, enum.Enum):
    """Monetized-review revenue-share contract lifecycle (M3 slice 10)."""

    active = "active"
    expired = "expired"
    bought_out = "bought_out"


class RequestStatus(str, enum.Enum):
    """Review-request lifecycle (M3 slice 9)."""

    open = "open"
    fulfilled = "fulfilled"
    cancelled = "cancelled"
    expired = "expired"
    removed = "removed"


class OtpPurpose(str, enum.Enum):
    """What a one-time code authorises (Slice 1 Phase A)."""

    signup = "signup"
    login = "login"


class ImageSource(str, enum.Enum):
    seeded = "seeded"        # one-off backfill script, 2026-07-28
    moderator = "administrator"  # supplied by a human at link-attach time
    none = "none"            # no image resolved


# Human-readable trust stage names (FR-7). Index == trust_stage (0..5).
TRUST_STAGE_NAMES = [
    "Newcomer",
    "Contributor",
    "Verified Buyer",
    "Established Reviewer",
    "Trusted Reviewer",
    "Community Expert",
]


class AffiliateTxStatus(str, enum.Enum):
    """The canonical lifecycle of one affiliate transaction.

    Shopee and Lazada each have their own vocabulary, and neither maps cleanly:
    Lazada's live API returns `Fulfilled` — a state its own XLSX export never
    contains — and Shopee reports an order-level status that can disagree with
    the affiliate item-level one. Everything downstream of the adapter speaks
    these four words instead, so no dashboard, payout or earnings code has to
    know which marketplace a row came from.
    """

    pending = "pending"        # money may still happen; nothing is owed yet
    completed = "completed"    # finalised by the provider; commission recognisable
    cancelled = "cancelled"    # died before finality; never earned
    returned = "returned"      # was finalised, then reversed by the buyer


class SettlementStatus(str, enum.Enum):
    """What has happened to the *money*, which is not the same question.

    A sale can be `completed` and unpaid, or `returned` after being paid. Keeping
    the two dimensions apart is the whole reason a return can be represented as a
    reversal entry rather than by rewriting the original one.
    """

    not_earned = "not_earned"  # pending or cancelled: contributes nothing
    earned = "earned"          # recognised, payable, not yet paid
    paid = "paid"              # included in a sent payout
    reversed = "reversed"      # recognised, then reversed by a return


class SellerClaimStatus(str, enum.Enum):
    """Who, if anyone, speaks for a store (FR-4).

    `unclaimed` is the default and the common case: most sellers are reviewed
    by buyers long before the store notices the platform exists, and FR-4
    requires those profiles to be representable rather than waiting for a
    signup. The rest is the moderator's decision on a claim request, kept as a
    status rather than a boolean so a rejection is distinguishable from never
    having been asked — a retry should not look like a first attempt.
    """

    unclaimed = "unclaimed"
    pending = "pending"
    claimed = "claimed"
    rejected = "rejected"
    #: 0075: the claimant took a pending claim back (claims only, never a store).
    withdrawn = "withdrawn"


class PriceObservationStatus(str, enum.Enum):
    """Where a community price stands (FR-2, completion contract).

    Pending until a moderator decides it. The public price panel is built from
    approved observations only; a pending one is counted so the page can say
    something is waiting, and never priced.
    """

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PriceObservationSource(str, enum.Enum):
    """How a price reached the platform: the price endpoint, or the price a
    reviewer gave on the composer's "Let's talk money" card."""

    manual = "manual"
    review = "review"


class MaterialRelationship(str, enum.Enum):
    """What the reviewer declared about their relationship to the product
    (completion contract X.1). NULL on a review means never asked."""

    none = "none"
    free_or_discounted = "free_or_discounted"
    connected = "connected"


class ReportSource(str, enum.Enum):
    """Where a moderation-queue report came from (Business Rules §12)."""

    user_reported = "user_reported"
    system_detected = "system_detected"


class SupportRequestStatus(str, enum.Enum):
    """A seller support request's lifecycle (0063)."""

    open = "open"
    in_review = "in_review"
    #: MQA-022: the team asked the seller for something; the seller acts next.
    waiting_for_seller = "waiting_for_seller"
    resolved = "resolved"
    rejected = "rejected"


class SupportRequestCategory(str, enum.Enum):
    """What a seller support request is about (0063)."""

    report_review = "report_review"
    takedown_investigation = "takedown_investigation"
    fake_review_dispute = "fake_review_dispute"
    account_claim = "account_claim"
    listing_product = "listing_product"
    #: MQA-026: a change to the store's name, link or registration.
    store_change = "store_change"
    general = "general"


class ConversationAudience(str, enum.Enum):
    """Who the member on a conversation is to the Inbox (0076): a store's
    owner or claimant (the Sellers tab) or a reviewer (the Reviewers tab)."""

    seller = "seller"
    reviewer = "reviewer"


class ConversationTopic(str, enum.Enum):
    """What a conversation is about (0076; Figma Menu/Store/Chat/Topic,
    Screen/Messages/New, Menu/Inbox/Filter)."""

    appeal = "appeal"
    claim = "claim"
    product = "product"
    payout = "payout"
    review = "review"
    report = "report"
    account = "account"
    other = "other"


class ConversationStatus(str, enum.Enum):
    """Menu/Inbox/Status: Open, Waiting on them, Closed (0076)."""

    open = "open"
    waiting = "waiting"
    closed = "closed"


class ConversationMessageKind(str, enum.Enum):
    """A written message, or a line the system adds (closed, reopened, ...)."""

    message = "message"
    event = "event"


class StoreProductStatus(str, enum.Enum):
    """A store's request to link a product page (0077)."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"

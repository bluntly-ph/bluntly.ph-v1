# Honesty Fund — community Honesty Awards (meeting decision, 2026-09-26)

Recorded from the owner's round-3 brief so that later work stops assuming the
Fund model is entirely undefined, and does not assume more than was decided.
**Nothing here is implemented yet, and real Honesty Fund distribution stays
OFF** (`HONESTY_FUND_DISTRIBUTION_ENABLED=false`, the default in
`backend/app/core/config.py`).

## Where the code stands today

`backend/app/services/honesty_fund_service.py` implements the *earlier* model
(M2 slice 8, FR-6): a monthly pool (the 30% honesty share of the cycle's
commissions) split across fund-routed reviews by a trust-weighted Honesty
Score, behind the `honesty_fund_distribution_enabled` flag, which is off. The
meeting direction below **replaces the basis** of the Fund (answers that helped
someone avoid a purchase, awarded by the community) but leaves its money rules
open. That earlier service must not be switched on as a stand-in for the new
model.

## APPROVED DIRECTION

These are decided. Build to them when the Fund is built.

1. **The community supplies Honesty Awards.** Members give them; the platform
   does not assign them.
2. **One award per day.** An eligible member has at most one award to give per
   day.
3. **Who may give one.** Eligibility requires at least one
   **ownership-evidence-backed review** by the member — in current Bluntly
   terms, a review with a photo of the item or a receipt ("Photo provided" /
   `has_receipt`; Business Rules §3). Possession, never "verified purchase".
4. **What receives one.** An award attaches to the **specific answer** that
   helped someone avoid a purchase — the Q&A answer, not the question, the
   reviewer, or a review. Not extended to other content types without a newer
   owner decision.
5. **Awards are not cash.** An award is a mark on the answer, not money at the
   moment it is given.
6. **Awards accumulate on the answer.**
7. **Money only through review.** Reaching the (still open) threshold, **or**
   the answer's author requesting a payout, sends the case to the **admin
   review queue**.
8. **The admin checks the awarders before any money.** The review looks at the
   relationships and patterns among the people who gave the awards before
   approving a payout.

### Security requirement (approved)

Raw award volume is **not** independent evidence. Awards are counted with the
distinct-participant and collusion principles already in the trust-integrity
work, not as a raw tally:

* count **distinct awarders**, each once per answer, never award events;
* discount awarders who are connected to the answer's author or to each other
  the way vote-concentration findings already are (ADR-016;
  `trust_service.concentration_review_state`), and awarders under
  investigation, suspended, on probation or with an upheld concentration
  finding (the same enforcement state the priority tiers read);
* a threshold crossing is a **reason to review**, never an automatic payout.

## OPEN ECONOMIC PARAMETERS — not decided; do not invent

| Parameter | Status |
|---|---|
| Award threshold that sends an answer to review | OPEN |
| Peso value of an award | OPEN |
| Honesty Fund distribution formula (how the pool is divided) | OPEN |
| Payout holding period | OPEN |

Until the owner sets these, no screen shows a peso value for an award, no job
converts awards to money, and the distribution flag stays off.

## Also open (implementation questions, not economics)

* Whether the one-per-day allowance resets at Manila midnight (the platform's
  day everywhere else) — assumed yes, to be confirmed.
* Whether an awarder may award the same author's different answers on
  different days — the distinct-participant rule above limits the weight either
  way.
* What the answer's author sees before the review (a count of awards, or
  nothing).

## Not changed by this decision

* The review revenue share and its 30% honesty share of commissions.
* Earnings eligibility of reviews, the earnings gate, and the priority tiers.
* PayPal remains SANDBOX.

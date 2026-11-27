# Defense diagram alignment

How the capstone's Use Case, Activity and Class diagrams line up with the
system as built. The diagram images are not in this repository (the manuscript
and slides are out of scope here), so this is built from the documents the
diagrams were drawn from: the use case reports UC-01…UC-09 and the FR/NFR text
in `01-bluntly-ph-PRD.md`, and the rules that superseded them in
`BUSINESS_RULES_IMPLEMENTATION.md`. Where a diagram shows a superseded rule, the
system follows the newer rule and the row says so (**OUTDATED_DIAGRAM**) — the
old behaviour was not re-implemented for the presentation.

## Use case diagram — actors and use cases

| Diagram actor | System role | Defense persona |
|---|---|---|
| Visitor / Shopper | signed-out reader | (signed out) |
| Reviewer | `user`, Stage 0–5 | Paolo (1), Maria (2), Kristine (3) |
| Seller | `user` with a claimed store (`is_claimed_seller`) | Rico |
| Moderator / Administrator | `moderator` | Joanna |
| Root owner | the configured owner address (`require_root_owner`) | — (role management only) |
| System (scheduler) | cron jobs: Honesty Fund, retention, payouts batch | — |

Every use case maps to rows of [DEFENSE_SYSTEM_COVERAGE.md](DEFENSE_SYSTEM_COVERAGE.md).

## Activity diagrams — step → system transition → verification

| Activity (UC) | Step | System transition | Verified by |
|---|---|---|---|
| Register (UC-01) | enter email → receive code → verify | `otp/request` stores a hashed code; `otp/verify` creates or signs in the user, sets the session cookie | walkthrough sign-ins (6) |
| Onboard (UC-01) | username, interests | `PATCH /users/me`; username `^[a-z0-9_]{3,32}$`, interests = category slugs | seed, journeys |
| Submit product (UC-02) | paste a link or type a name | `products.status = pending`; duplicate link or name returns the existing product | walkthrough, `test_source_listing` |
| Canonicalize (UC-02) | moderator names it | `pending → canonicalized`; aliases added; **its link recorded as its listing** | walkthrough W6 |
| Attach duplicate (UC-02) | moderator picks the product | submission `→ rejected` (closed), listing + reviews move, name becomes an alias, **no longer listed** | walkthrough W6, test |
| Write review (UC-03) | 7 steps + price | `POST /reviews` → published at once; photo ⇒ `verified`, else `unverified` | walkthrough W2 |
| Vote (UC-03) | helpful / not | vote weight snapshotted by stage; aggregates and Wilson recomputed; gate evaluated | walkthrough W2, seed gate step |
| Earn gate (UC-06) | votes accumulate | Post-Seeding: Wilson LB ≥ 0.65 and ≥ 3 Stage 2+ voters ⇒ `earn_eligible_status = pending` (queued) | seed (19 and 18 votes) |
| Moderator decision (UC-06/07) | approve / fund / reject | `approved` (≥ 3★) or `honesty_fund` (≤ 2★) or `rejected` with reason + notification | walkthrough W6 |
| Attach link (UC-06) | paste marketplace link | `referral_links` active, sub-ID; review `monetized` | walkthrough W6 |
| Order → commission (UC-06) | import Shopee/Lazada export | ledger row per provider identity; `completed` ⇒ commission 40/30/30, wallet credited; `pending`/`cancelled` ⇒ no money | seed, `test_affiliate_ingest` |
| Clear → cash out (UC-06) | remittance recorded → request | month's commissions `cleared_at` set; cashout ≥ ₱300 of cleared money reserves it at once | walkthrough W3 |
| Report (UC-07/08) | reason → queue | urgent reasons escalate; decision removes/restores/dismisses; reporter weight adjusted | walkthrough W6 |
| Claim store (UC-04) | DTI registration → decision | claim `pending → claimed`; owner loses voting/earning | walkthrough W6, journeys |
| Best Answer (UC-05) | asker picks | `best_answer_id`, picker recorded; answerer's evidence | walkthrough W3 |

## Class diagram — entities

The as-built schema is documented in `schema.md` and `ARCHITECTURE_AS_BUILT.md`
(55 migrations, head `0054_record_source_listings`). Classes a diagram may
show under another name:

| Diagram class | As built |
|---|---|
| User / Reviewer / Seller / Moderator | one `users` table with `role`, `trust_stage`, `is_claimed_seller` |
| Product, Listing | `products`, `product_platforms` (one row per marketplace listing), `product_aliases` |
| Review, ReviewVersion | `reviews` (a thread: root + updates via `thread_id`), version history |
| SellerReview | `seller_reviews` (+ `seller_review_appeals`) |
| Question, Answer | `questions`, `answers` |
| Commission, Payout | `commissions`, `affiliate_postbacks` (the ledger), `marketplace_remittances`, `payouts` |
| Session (click) | `sessions` |
| ModerationLog | `moderation_logs` (reports are rows with `action = report`) |

## Differences from the diagrams (the system follows the newer rule)

| Diagram / PRD says | System does | Source | Status |
|---|---|---|---|
| Price panel needs ≥ 3 independent observations | any approved price is plotted per marketplace; a new price is *held* when outside 0.5–2× the 180-day median of ≥ 3 approved prices, or when there is no such baseline | Business Rules §16 | OUTDATED_DIAGRAM |
| Tiered revenue share / contracts | flat 40 / 30 / 30, no tiers, no contracts | §14 | OUTDATED_DIAGRAM |
| Seller ratings in the comparison tool | not shown (withdrawn 2026-07-28) | MILESTONES.md | OUTDATED_DIAGRAM |
| Stage 3 at ≥ 70 % helpfulness | Stage 3 at 5 verified counted reviews, helpfulness ≥ 49.5 and 20 distinct eligible voters | trust rules, `TRUST_DISTINCT_VOTER_SECURITY_FIX.md` | OUTDATED_DIAGRAM |
| Seeding phase: moderator reviews every qualifying submission | Post-Seeding gate is the default (Zient, 2026-09-22); Seeding activation policy pending | `config.earn_gate_phase` | OPEN_PRODUCT_DECISION |
| Commission CSV upload screen | import is an API operation (`admin/affiliate/import`); the console shows the ledger | — | API_ONLY |
| Moderator triggers Honesty Fund payout | distribution runs as a scheduled monthly job; no on-demand control by design | `/moderate/honesty-fund` | as designed |
| Earning rule for a 2.5★ "It depends" | unresolved; the dataset contains no such review | owner | OPEN_PRODUCT_DECISION |

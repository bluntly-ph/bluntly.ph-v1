# Defense system coverage

Every use case the capstone documents (UC-01 to UC-09, `01-bluntly-ph-PRD.md`
§4), traced to what the running system does, where, and how it was proven for
the defense. Business Rules (`BUSINESS_RULES_IMPLEMENTATION.md`) supersede the
PRD where they differ; those differences are listed in
[DEFENSE_DIAGRAM_ALIGNMENT.md](DEFENSE_DIAGRAM_ALIGNMENT.md), not implemented
back.

**Status key** — READY: works, and the walkthrough performs it ·
READY_WITH_DEMO_DATA: works and the dataset holds a live example to show ·
API_ONLY: works through the API, with no screen (stated, not hidden) ·
OPEN_PRODUCT_DECISION: waits on the owner, the system does what the current
rule says · OUTDATED_DIAGRAM: the document describes a superseded rule.

**Evidence** — *W n*: scene n of `e2e/defense-walkthrough.spec.ts` (real
browser, real sign-ins, real API and Postgres, 7/7 passed, 32 stops
photographed at 390 and 1440 px); *V*: `python -m scripts.defense.verify`
(95/95 on the seeded database); *J*: the existing journeys (38/38);
*T*: backend tests (2,325 passed locally; the 2 receipt-storage tests need
Supabase storage credentials and fail identically on a clean `main` here).

## UC-01 Account & profile (FR-1)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Sign up / sign in by emailed code | Visitor | `/login`, `/signup`, `/welcome` | `POST /auth/otp/request`, `/auth/otp/verify` | users | W2–W6 (six real code sign-ins) | 6 personas, "+" aliases of the team inbox | READY |
| Onboarding: username, interests | New member | `/onboarding` | `PATCH /users/me` | users.interests | J | every account onboarded | READY |
| Profile, public profile, trust badge | Member | `/profile`, `/u/{username}` | `GET /users/public/{handle}` | users | W1, W3, W4 | Stage 1/2/3 personas | READY |
| Notifications | Member | `/notifications` | `GET /notifications` | notifications | W3 | 116, older ones read | READY_WITH_DEMO_DATA |
| Roles (user, seller, moderator) | Root owner | `/moderate/users` | `PATCH /admin/users/{id}/role` | users.role | J | `mod_joanna` | READY |

## UC-02 Product discovery & consolidation (FR-2, §5, §6, §16)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Search with aliases and typo tolerance | Visitor | `/search?q=` | `GET /products?q=`, `GET /reviews/feed?q=` | products, product_aliases | W1 (`powercore` finds the 737 only), J | 36 aliases | READY |
| Browse by category, feed | Visitor | `/categories`, `/feed` | `GET /reviews/feed` | reviews | W1 | 47 reviews, 7 categories used | READY |
| Price history per marketplace | Visitor | review page sidebar | `GET /products/{id}/prices` | price_history | W1 (iPhone: Shopee + Lazada) | Shopee-only, Lazada-only, both | READY_WITH_DEMO_DATA |
| Report what you paid | Author | review page | `POST /products/{id}/prices` | price_history | J | — | READY |
| Price outlier / no-baseline hold, moderator glance | Moderator | `/moderate/prices` (now shows *why* it waits) | `POST /admin/price-observations/{id}/decision` | price_history.hold_reason | W6 (outlier rejected) | ₱24,999 iPhone outlier; Uratex with no baseline | READY |
| Submit an unknown product | Reviewer | `/reviews/new` | `POST /products` | products (pending) | W2 | 2 pending submissions | READY |
| Name a submission as a new product | Moderator | `/moderate/products` → **Name as a new product** (added: the API existed, the screen offered only Attach) | `POST /products/{id}/canonicalize` | products | W6 (Xiaomi named) | Xiaomi 20,000mAh | READY |
| Attach a duplicate submission | Moderator | `/moderate/products` → Attach | `POST /products/{id}/attach` | product_platforms, aliases | W6, J | Anker Nano duplicate | READY |
| Compare products | Visitor | `/compare` | `GET /products/compare` | — | T | any 2–4 products | READY |

## UC-03 Review submission (FR-3, §1, §2)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Seven-step composer; publishes immediately | Reviewer | `/reviews/new` | `POST /reviews` | reviews | W2 (full composer, price-paid dialog, live) | — | READY |
| Photo ⇒ verified; none ⇒ unverified | Reviewer | composer step 6 | `POST /reviews/photo` | reviews.verification_status | W2 (skip ⇒ unverified), V | 41 verified, 6 unverified | READY |
| Thread update after 3 months | Author | review page → Add an update | `POST /reviews` (`update`) | reviews.thread_id | W1 (update visible), J | Maria's Anker 737 + 5-month update | READY_WITH_DEMO_DATA |
| Author deletes (typed confirmation) | Author | review page | `DELETE /reviews/{id}?confirm=delete-thread` | reviews | J | one author-deleted review | READY |
| Helpfulness votes; comments, replies | Member | review page, feed card | `POST /reviews/{id}/vote`, `/comments` | review_votes, review_comments | W2 (vote), J | 276 votes, 37 comments | READY |
| Rejection with a reason | Moderator | review queue | `POST /admin/reviews/{id}/reject` | reviews, notifications | T, V | Ken's rejected review | READY_WITH_DEMO_DATA |
| Receipt upload (optional evidence) | Author | review page | `POST /reviews/receipt` | reviews.receipt_key | T (needs storage) | — | READY (TEST storage) |

## UC-04 Seller reviews & seller accounts (FR-4, §9, §10)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Rate a store (four dimensions + overall) | Buyer | `/sellers/rate` | `POST /sellers/{id}/reviews` | seller_reviews | J, T | 16 store reviews | READY_WITH_DEMO_DATA |
| Claim a store with DTI registration | Seller | store page → Claim | `POST /sellers/{id}/claims` | seller_claims | J | Cebu Gadget Hub pending | READY |
| Approve a claim | Moderator | `/moderate/sellers` | `POST /admin/seller-claims/{id}/decision` | sellers, users.is_claimed_seller | W6 (Cebu approved), J | — | READY |
| Respond publicly; flag a suspected fake | Store owner | store page | `POST /sellers/reviews/{id}/response`, appeals | seller_reviews, seller_review_appeals | W5 (response), J | PowerHub's responses; one appeal | READY |
| Seller dashboard | Store owner | `/sellers/{id}/dashboard` | `GET /sellers/{id}/dashboard` | — | W5 | PowerHub PH | READY |
| A claimed seller cannot vote or earn | System | — | 403 on vote | users | J, T | Rico | READY |

## UC-05 Community Q&A (FR-5, §7)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Ask other buyers or the store | Member | `/questions/new`, store page | `POST /questions` | questions | J | 11 questions, 2 to stores | READY_WITH_DEMO_DATA |
| Answer; First Responder | Member | question page | `POST /questions/{id}/answers` | answers | T | 17 answers | READY |
| Best Answer, by the asker only | Asker | question page | `POST /questions/{id}/answers/{answer}/best` | questions.best_answer_id | W3 (Maria picks), J | open question for the live pick | READY |
| Notify me | Member | question page | `PUT /questions/{id}/subscription` | question_subscriptions | J | subscribers seeded | READY |
| Answerer's reputation beside the badge | Visitor | question page | `GET /questions/{id}` | users.reputation_score | **fixed**: every answerer read "0" | — | READY |

## UC-06 Incentives, earnings & payouts (FR-6, §3, §4, §14, §15)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Earn gate (Post-Seeding: Wilson LB ≥ 0.65, ≥ 3 Stage 2+ voters) | System | review queue | vote → `earn_gate` | reviews.earn_eligible_status | V (2 queued by real votes) | Maria's Jisulife, Mark's iPhone | READY_WITH_DEMO_DATA |
| Seeding vs Post-Seeding phase | Owner | — | `settings.earn_gate_phase` | — | — | runs Post-Seeding (Zient 2026-09-22) | OPEN_PRODUCT_DECISION |
| Approve earnings / Honesty Fund track | Moderator | review queue | `POST /admin/reviews/{id}/approve-earnings` | reviews | W6 | 27 approved, 4 fund | READY |
| Attach the affiliate link | Moderator | `/moderate/affiliate-links` | `POST /admin/reviews/{id}/referral-link` | referral_links | W6 (link ⇒ monetized) | real Shopee/Lazada links; 5 awaiting (6 after the live approval) | READY |
| Affiliate-link queue lists single-marketplace products | System | same | `GET /admin/awaiting-affiliate` | product_platforms | **fixed** + migration 0054 | — | READY |
| Headline agrees with the list | Moderator | overview, affiliate page | `GET /admin/analytics/overview` | — | **fixed** (was 27 vs 5) | — | READY |
| Import Shopee / Lazada exports into the ledger | Moderator | — (no upload screen) | `POST /admin/affiliate/preview`, `/import` | affiliate_postbacks, commissions | V, T | 20 orders: completed, pending, cancelled | API_ONLY |
| Generic commission CSV pays finished orders only | Moderator | — | `POST /admin/commissions/import` | commissions | **fixed** (cancelled rows used to pay) | — | API_ONLY |
| Remittance clears a month | Moderator | `/moderate/affiliate-links` | `POST /admin/remittances` | marketplace_remittances | J, V | 4 months remitted | READY |
| Wallet, clearing, ₱300 threshold, cash out | Reviewer | `/dashboard`, `/dashboard/transfer` | `POST /payouts/cashout` | payouts | W3 (Maria withdraws ₱368.40) | above and below threshold | READY |
| Mark a payout paid (PayPal **sandbox** reference) | Moderator | — | `POST /admin/payouts/{id}/mark-paid` | payouts | T, V | one paid, one scheduled | API_ONLY |
| Honesty Fund distribution | System (monthly) | `/moderate/honesty-fund` (read) | scheduled job | honesty_fund_distributions | T | pool accruing | READY (scheduled by design) |
| Earnings history, insights | Reviewer | `/dashboard/history`, `/dashboard/insights` | `GET /users/me/dashboard`, `/users/me/earnings` | commissions, review_view_buckets | W3 | views over 90 days | READY_WITH_DEMO_DATA |

## UC-07 Moderation queue (FR-9, §12)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Earnings queue with evidence and SLA | Moderator | `/moderate/review-queue` | `GET /admin/review-queue` | reviews, moderation_logs | W6 | 2 queued | READY_WITH_DEMO_DATA |
| Reports: urgent, normal, system-detected | Moderator | `?tab=report` | `POST /admin/reports/{id}/decision` | moderation_logs | W6 (urgent PII report ⇒ removed) | 3 open, 1 resolved | READY |
| Answers tab | Moderator | `?tab=answers` | — | answers | J | 17 | READY |

## UC-08 Trust & abuse (FR-7, FR-8, §11, §12)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Trust stages from real evidence | System | profile badges | `recompute_user_trust` | users.trust_stage | V (Kristine Stage 3, Maria 2, Paolo 1) | — | READY |
| Voting-ring concentration hold → system report | System | report tab | trust service | moderation_logs | V | Jomar's five-account ring | READY_WITH_DEMO_DATA |
| Investigation halves vote weight | Moderator | `/moderate/users` | `PUT /admin/users/{id}/investigation` | users.is_under_investigation | J | Jomar | READY |
| Suspension, probation | Moderator | — | admin API | users | T | — | API_ONLY |

## UC-09 Administration & analytics (FR-9)

| Flow | Actor | Page | API | Entities | Evidence | Demo data | Status |
|---|---|---|---|---|---|---|---|
| Overview: queue, approvals, pending links, fund, ledger | Moderator | `/moderate` | `GET /admin/analytics/overview` | — | W6 | dated audit trail (not "8 minutes ago") | READY_WITH_DEMO_DATA |
| Request geography, analytics | Moderator | `/moderate/analytics` | `GET /admin/analytics/*` | request_geo_buckets | W6 | 13 Philippine cities | READY_WITH_DEMO_DATA |
| Activity (audit) log | Moderator | `/moderate/activity` | `GET /admin/activity` | moderation_logs | W6 | 114 entries over months | READY_WITH_DEMO_DATA |
| Reviewers | Moderator | `/moderate/reviewers` | `GET /admin/reviewers` | users | V | 32 accounts | READY |
| Review requests board | Member | `/requests` | `/requests` | review_requests | W1 | 3, up-voted | READY_WITH_DEMO_DATA |

## Defects found and fixed during readiness

| # | Defect | Where | Proof |
|---|---|---|---|
| 1 | A hand-built (generic) commission CSV credited cancelled, pending, returned and blank-status orders. | `commission_service._rows_from_bytes` | `test_commissions_api.py` (4 fail → pass) |
| 2 | A product's own marketplace link was never recorded as its listing, so its earnings-approved reviews never reached the affiliate-link queue. | `canonical_service.record_source_listing`, migration 0054 | `test_source_listing.py` (5 fail → pass) |
| 3 | The overview's "Pending Affiliate" and the affiliate page's headline counted reviews the queue rightly excludes (27 above a list of 5). | `monetization_attention.awaiting_affiliate_total` | `test_public_lifecycle_api.py` |
| 4 | Every Q&A asker and answerer showed reputation 0. | `qa_service._author` | `test_qa_gaps.py` |
| 5 | An attached (closed) submission stayed listed as a second product in search. | `GET /products` | `test_source_listing.py` |
| 6 | No screen could name a pending submission as a new product. | `ProductCatalogueActions` | W6 |
| 7 | The price queue did not say why a price was held. | `/moderate/prices` | W6 |
| 8 | "Reviewer paid ₱4799.00" without a thousands separator. | `ReviewAside`, `ReviewDetail` | W1 screenshots |
| 9 | The Transfer page never said a PayPal account was already saved. | `PayoutAccountForm` | W3 screenshots |

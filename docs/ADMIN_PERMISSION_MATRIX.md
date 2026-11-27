# Admin permission matrix

Owner decisions A–D (2026-09-28). There is no moderator role. Every row below
is enforced **on the server**, from the `users.role` read fresh on each request
(`app/core/security.py`: `require_staff`, `require_super_admin`). The console
hides what a role may not do, but that is presentation; the API refuses it.

| Role | Who | In short |
| --- | --- | --- |
| Anonymous | signed out | reads public content |
| User | any member | writes reviews, votes, answers, asks, reports, cashes out |
| Claimed seller | a member whose store claim was approved (`is_claimed_seller`) | responds to reviews of their store, flags suspected fakes, dashboard, support requests; never votes or earns |
| Administrator | `role = administrator` | the operational queues and approvals; **no user management, no 2.5-star routing** |
| Super Admin | `role = super_admin` | everything an Administrator does, plus user/role management, tier management and the 2.5-star routing decision |

Legend: ✅ allowed · ❌ 403 (401 when signed out) · 🔸 own resource only.

## Actions

| Action | Anonymous | User | Claimed seller | Administrator | Super Admin | Current endpoint | Target endpoint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Read reviews, products, sellers, Q&A | ✅ | ✅ | ✅ | ✅ | ✅ | `GET /reviews…`, `/products…`, `/sellers…`, `/questions…` | same | public |
| Write a review / update a thread | ❌ | ✅ | ❌ for own store | ✅ | ✅ | `POST /reviews`, `POST /reviews/{id}/updates` | same | §9: a claimed seller cannot review competitors or their own store |
| Delete own review (thread or update) | ❌ | 🔸 | 🔸 | 🔸 | 🔸 | `DELETE /reviews/{id}?confirm=delete-thread` | same | author only; paid trace kept; earning stops |
| Take a review down / restore | ❌ | ❌ | ❌ | ✅ | ✅ | `POST /admin/reviews/{id}/unpublish` · `/restore` | same | reason required in the UI, audited |
| Approve / reject earnings | ❌ | ❌ | ❌ | ✅ | ✅ | `POST /admin/reviews/{id}/approve-earnings` · `/reject` | same | a 2.5-star "It depends" approval **escalates** to a Super Admin |
| Attach the official affiliate link | ❌ | ❌ | ❌ | ✅ | ✅ | `POST /admin/reviews/{id}/referral-link` | same | refused while a 2.5 review waits on a Super Admin |
| **Route a 2.5-star "It depends" review** (Honesty Fund / Platform) | ❌ | ❌ | ❌ | ❌ | ✅ | — (was refused as an open owner rule) | `GET/POST /admin/super/special-routing[/{review_id}]`, `GET …/history` | decision A: audited, idempotent, final, concurrency-safe |
| Review queue, All Reviews, reports, investigation flag | ❌ | ❌ | ❌ | ✅ | ✅ | `GET /admin/review-queue`, `GET /admin/reviews`, `/admin/reports…`, `PUT /admin/users/{id}/investigation` | same | investigation is operational (§11), set from Reviewers |
| Seller claims, appeals, substantiation | ❌ | ❌ | ❌ | ✅ | ✅ | `/admin/seller-claims…`, `/admin/seller-review-appeals…` | same | |
| Support requests (seller side) | ❌ | ❌ | 🔸 own store | ❌ | ❌ | `POST/GET /sellers/{id}/support-requests[/{rid}]` | same | another store's → 403 / 404 |
| Support queue (assign, reply, status, note) | ❌ | ❌ | ❌ | ✅ | ✅ | `/admin/support-requests…` | same | internal note never reaches the seller |
| Products: canonicalize, attach, aliases, image | ❌ | ❌ | ❌ | ✅ | ✅ | `POST /products/{id}/canonicalize` · `/attach` · `/aliases` · `/image` | same | |
| Price observations | ❌ | ❌ | ❌ | ✅ | ✅ | `/admin/price-observations…` | same | |
| Commission import, remittances, payouts | ❌ | ❌ | ❌ | ✅ | ✅ | `/admin/commissions/import`, `/admin/affiliate/…`, `/admin/remittances`, `/admin/payouts…` | same | PayPal sandbox only in this environment |
| Reports (commissions, fund, ratings, any statement, the financial report and its PDFs) | ❌ | ❌ | 🔸 own store's rating summary | ✅ | ✅ | `/admin/reports/…` | same | a reviewer reads only their own statement |
| QA sandbox: credit a tester | ❌ | ❌ | ❌ | ✅ | ✅ | `POST /admin/qa-sandbox/credits` | same | |
| QA sandbox: name / remove testers | ❌ | ❌ | ❌ | ❌ | ✅ | `POST/DELETE /admin/qa-sandbox/testers` | same | was "root owner" (hard-coded email) |
| Priority tier thresholds | read ❌ | ❌ | ❌ | read ✅ | ✅ | `GET/PUT /admin/priority-settings` | same | PUT was "root owner" |
| **Find a user (User management)** | ❌ | ❌ | ❌ | ❌ | ✅ | `GET /admin/users` (was moderator) | same | returns email to the Super Admin only |
| **Assign Administrator / Super Admin / Member** | ❌ | ❌ | ❌ | ❌ | ✅ | `PATCH /admin/users/{id}/role` (was root owner, moderator only) | same | last active Super Admin cannot be demoted (409); claimed seller never staff (409); audited |
| Move an account user ↔ seller | ❌ | ❌ | ❌ | ❌ | ✅ | `PATCH /users/{id}/role` (was moderator) | same | refuses staff roles and staff targets |
| Membership tiers (edit, assign) | ❌ | ❌ | ❌ | ❌ | ✅ | `PATCH /membership-tiers/{code}`, `PATCH /users/{id}/membership-tier` (was moderator) | same | promoting a member up a tier is user management |
| **Suspend / reinstate a member account** | ❌ | ❌ | ❌ | ❌ | ✅ | `PUT /admin/people/{id}/suspension` (new, session 4) | same | reason required, audited (`suspend` / `restore`); member accounts only (staff: 422 `staff_account`), never yourself; votes weigh 0 and the token stops working |
| Run a scheduled job now (Activity log) | ❌ | ❌ | ❌ | ✅ derived-figure jobs | ✅ all | `POST /admin/jobs/{task}/run` (new, session 4) | same | money / data-deletion jobs (`honesty_fund_distribution`, `schedule_payouts`, `refresh_payout_batches`, `pii_retention`) are Super Admin only (403 `super_admin_only`); the scheduler's own period lease, so a run never doubles one done or in flight |
| Settings (read-only) | ❌ | ❌ | ❌ | ✅ (no staff emails) | ✅ (with staff emails) | `GET /admin/settings` (new, session 5) | same | nothing writable; earning rules editable only after an owner decision |
| Activity log read, summary, CSV export | ❌ | ❌ | ❌ | ✅ | ✅ | `GET /admin/activity` (filters), `/admin/activity/summary`, `/admin/activity.csv` | same | audit log only; no emails or payment destinations |
| Export CSV (Activity log, Analytics) | ❌ | ❌ | ❌ | ✅ | ✅ | `GET /admin/export` (new, session 8) | same | activity, moderation, earnings and analytics files in one zip; names shortened, email addresses removed from every cell; each export audited as `data_export` (Privacy) |
| Delete an account | — | — | — | — | — | none in the API | none | the 0067 trigger refuses removing the last Super Admin by any path |
| Purge selected TEST/seed reviews | — | — | — | — | ✅ named in `--actor` | none (script only) | `scripts/purge_test_reviews.py` | never production; see docs/SEEDING_RUNBOOK.md |
| Bootstrap the first Super Admin | — | — | — | — | — | none (script only) | `scripts/bootstrap_super_admin.py` | refused once any Super Admin exists |

## Verified by

- `backend/tests/test_admin_user_management.py` — the matrix for user management
  against the real API, token-claim spoofing (a member claiming `super_admin`,
  an Administrator's old `moderator` token), audit rows, the last Super Admin
  (service, database trigger, and two Super Admins demoting each other at once),
  the bootstrap script.
- `backend/tests/test_special_routing_api.py` — 2.5-star routing: who may,
  both destinations, idempotency, a concurrent duplicate, the money that
  follows, history.
- `backend/tests/test_support_requests_api.py`, `test_review_author_delete.py`,
  `test_membership.py`, and the contract tests that introspect every staff
  route's guard (`test_seller_api_contract.py`, `test_price_moderation_contract.py`,
  `test_integrity_checks_rules.py`).
- `e2e/admin-journeys.spec.ts` — 16 browser journeys on the real stack.

## Appendix: every API route and its guard

Generated from the running app's dependency tree (`require_super_admin`, `require_staff`, `get_current_user`). A route under `/admin` guarded by anything weaker than `require_staff` would be a defect; there are none.

### Super Admin (11)

| Method | Path | Summary |
| --- | --- | --- |
| PUT | `/api/v1/admin/priority-settings` | Retune the priority tiers (Super Admin) |
| POST | `/api/v1/admin/qa-sandbox/testers` | Name an account as a QA tester (Super Admin) |
| DELETE | `/api/v1/admin/qa-sandbox/testers/{user_id}` | Stop an account being a QA tester (Super Admin) |
| GET | `/api/v1/admin/super/special-routing` | 2.5-star It depends threads waiting on a Super Admin |
| GET | `/api/v1/admin/super/special-routing/history` | The Super Admins' routing decisions, newest first |
| POST | `/api/v1/admin/super/special-routing/{review_id}` | Route a 2.5-star It depends thread to the Honesty Fund or the platform |
| GET | `/api/v1/admin/users` | Find an account by staff reference, id, email or name (Super Admin) |
| PATCH | `/api/v1/admin/users/{user_id}/role` | Assign user, administrator or super_admin (Super Admin) |
| PATCH | `/api/v1/membership-tiers/{code}` | Update a tier's config (Super Admin) |
| PATCH | `/api/v1/users/{user_id}/membership-tier` | Assign a membership tier to a user (Super Admin) |
| PATCH | `/api/v1/users/{user_id}/role` | Move an account between user and seller (Super Admin) |

### Administrator + Super Admin (92)

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/v1/admin/activity` | The moderation audit log, newest first |
| POST | `/api/v1/admin/affiliate/import` | Import a provider export into the canonical lifecycle |
| GET | `/api/v1/admin/affiliate/imports` | Report imports, newest first, with what each did (staff) |
| GET | `/api/v1/admin/affiliate/imports/{import_log_id}` | One import: its summary and the rows it wrote (staff) |
| GET | `/api/v1/admin/affiliate/months` | Commission recognised, reversed and remitted per marketplace month (staff) |
| POST | `/api/v1/admin/affiliate/preview` | What a provider export WOULD do. Writes nothing. |
| GET | `/api/v1/admin/affiliate/seeded-report` | Generate a seeded Shopee/Lazada report from active links (TEST only) |
| POST | `/api/v1/admin/affiliate/seeded-report/fill` | Fill a real Shopee/Lazada export with our sub-IDs (TEST only) |
| GET | `/api/v1/admin/affiliate/transactions` | Affiliate transactions imported from the marketplace reports (staff) |
| GET | `/api/v1/admin/analytics/affiliate-earnings` | Overview: verified vs returned affiliate commission by period |
| GET | `/api/v1/admin/analytics/geo-probe` | What geography does the edge see for this request? |
| GET | `/api/v1/admin/analytics/needs-attention` | Overview: what is waiting, by Moderation, Integrity, Catalog and Money |
| GET | `/api/v1/admin/analytics/overview` | Headline counts, queue breakdown and recent activity |
| GET | `/api/v1/admin/analytics/queue-preview` | Overview: the Review queue card's four tabs and their most urgent cards |
| GET | `/api/v1/admin/analytics/request-distribution` | Aggregate request geography, ranked |
| GET | `/api/v1/admin/awaiting-affiliate` | Earnings-approved public reviews with no active affiliate link |
| POST | `/api/v1/admin/commissions/import` | Import a monthly commission CSV (all-or-nothing, idempotent) |
| GET | `/api/v1/admin/cron-runs` | Scheduled maintenance: last run per task, and recent history |
| GET | `/api/v1/admin/integrations/paymongo` | PayMongo settings state (staff; the secret key is never returned, only its last 4) |
| PUT | `/api/v1/admin/integrations/paymongo` | Save PayMongo keys / methods / test mode (Super Admin; encrypted; audited `integration_change`; moves no money) |
| POST | `/api/v1/admin/integrations/paymongo/test` | One read-only call with the saved key (Super Admin) |
| DELETE | `/api/v1/admin/integrations/paymongo` | Remove the PayMongo keys (Super Admin; audited) |
| GET | `/api/v1/admin/export` | Export CSV: activity, moderation, earnings, analytics for 7d / 30d / 90d / 12m as a zip (staff; names shortened, emails removed; audited `data_export`) |
| POST | `/api/v1/admin/honesty-fund/run` | Run the Honesty Fund distribution for a cycle (idempotent) |
| GET | `/api/v1/admin/inbox` | The team's inbox (tabs, topic, status, handled by, search, sort, pages) |
| GET | `/api/v1/admin/inbox/staff` | Who a conversation can be assigned to |
| GET | `/api/v1/admin/inbox/unread` | Open conversations the team has not read (the rail count) |
| GET | `/api/v1/admin/inbox/{conversation_id}` | One conversation, with its messages (marks it read for the team) |
| POST | `/api/v1/admin/inbox/{conversation_id}/assign` | Assign the conversation to an Administrator or Super Admin, or unassign it |
| POST | `/api/v1/admin/inbox/{conversation_id}/messages` | Reply as the Bluntly team (also emailed to the member) |
| POST | `/api/v1/admin/inbox/{conversation_id}/move-to-support` | Move a store's conversation to Queue → Support |
| POST | `/api/v1/admin/inbox/{conversation_id}/status` | Open, waiting on them, or closed |
| GET | `/api/v1/admin/integrity-providers` | Whether plagiarism and reverse image checks can run |
| POST | `/api/v1/admin/integrity/sweep` | File automated integrity signals as reports |
| GET | `/api/v1/admin/payouts` | All payouts, with each recipient's PayPal address (administrator) |
| POST | `/api/v1/admin/payouts/batches/{batch_id}/refresh` | Poll the provider and settle a batch (administrator) |
| GET | `/api/v1/admin/payouts/provider` | How payouts are sent right now (administrator; no secrets) |
| POST | `/api/v1/admin/payouts/run` | Process requested payouts now (administrator) |
| GET | `/api/v1/admin/payouts/summary` | The Payouts screen's cards: to send, sent this month, waiting in wallets |
| POST | `/api/v1/admin/payouts/{payout_id}/cancel` | Cancel a scheduled payout (administrator; refunds the wallet) |
| POST | `/api/v1/admin/payouts/{payout_id}/fail` | Mark a payout failed (administrator; refunds the wallet) |
| POST | `/api/v1/admin/payouts/{payout_id}/mark-paid` | Mark a payout paid by hand (administrator; manual rail) |
| POST | `/api/v1/admin/payouts/{payout_id}/retry` | Retry a failed payout (administrator) |
| GET | `/api/v1/admin/people/{user_id}` | Everything recorded about one member, for an investigation |
| POST | `/api/v1/admin/pii-retention/run` | Run the sessions PII retention sweep (idempotent) |
| GET | `/api/v1/admin/price-observations` | Price observations waiting for a decision, oldest first |
| POST | `/api/v1/admin/price-observations/{observation_id}/decision` | Approve or reject a price observation |
| GET | `/api/v1/admin/priority-settings` | The priority tiers' current thresholds |
| POST | `/api/v1/admin/products` | Add a named product to the catalogue; 409 on a duplicate (staff) |
| POST | `/api/v1/admin/products/import` | Import products from a CSV: preview or apply (staff) |
| GET | `/api/v1/admin/products/queue` | Submitted products waiting for the catalogue, with link preview (staff) |
| POST | `/api/v1/admin/qa-sandbox/credits` | Credit a QA tester's review with a sandbox test earning (administrator) |
| GET | `/api/v1/admin/qa-sandbox/testers` | The named QA testers and their published reviews (administrator) |
| POST | `/api/v1/admin/remittances` | Record a marketplace payout; clears that cycle |
| GET | `/api/v1/admin/reports` | Administrator queue: community content reports |
| GET | `/api/v1/admin/reports/commissions-payouts` | Commissions, reconciliation and payout readiness (staff) |
| GET | `/api/v1/admin/reports/earnings-statement/{user_id}` | A reviewer's earnings statement (staff) |
| GET | `/api/v1/admin/reports/financial` | The financial report's figures for a period (staff) |
| POST | `/api/v1/admin/reports/financial/generate` | Generate a financial report PDF and log it (staff) |
| GET | `/api/v1/admin/reports/financial/history` | Financial report PDFs generated so far, newest first (staff) |
| GET | `/api/v1/admin/reports/financial/history/{entry_id}/pdf` | Download a generated financial report again (staff) |
| GET | `/api/v1/admin/reports/honesty-fund` | Honesty Fund inputs and distribution status (staff) |
| POST | `/api/v1/admin/reports/{report_id}/decision` | Resolve a report: dismiss, remove, restore or escalate |
| POST | `/api/v1/admin/requests/{request_id}/remove` | Remove a request (administrator; refunds the requester) |
| GET | `/api/v1/admin/review-queue` | Administrator queue: one policy-prioritized, filtered page |
| GET | `/api/v1/admin/reviewers` | Contributors, with trust stage and published counts |
| GET | `/api/v1/admin/reviews` | All Reviews: every review that still exists, with both Wilson figures |
| POST | `/api/v1/admin/reviews/{review_id}/approve-earnings` | Approve earnings without a link (<=2* -> Honesty Fund, else approved) |
| GET | `/api/v1/admin/reviews/{review_id}/gate` | Post-Seeding earn_eligible gate progress for one review |
| POST | `/api/v1/admin/reviews/{review_id}/publish` | Deprecated alias of approve-earnings (reviews publish on submission) |
| DELETE | `/api/v1/admin/reviews/{review_id}/referral-link` | Revoke the active referral link (stays published) |
| POST | `/api/v1/admin/reviews/{review_id}/referral-link` | Approve earnings on the affiliate path by attaching the referral link |
| GET | `/api/v1/admin/reviews/{review_id}/referral-links` | Referral link history for a review |
| POST | `/api/v1/admin/reviews/{review_id}/reject` | Reject earnings (the review stays public) |
| POST | `/api/v1/admin/reviews/{review_id}/restore` | Put a taken-down review back on the public site |
| POST | `/api/v1/admin/reviews/{review_id}/unpublish` | Take a published review off the public site |
| GET | `/api/v1/admin/search` | The top bar's search: reviews, products, sellers, people (staff) |
| GET | `/api/v1/admin/seller-claims` | Seller claims waiting for a decision, oldest first |
| POST | `/api/v1/admin/seller-claims/{claim_id}/decision` | Approve or reject a seller claim |
| GET | `/api/v1/admin/seller-review-appeals` | Open seller appeals against reviews (oldest first) |
| POST | `/api/v1/admin/seller-review-appeals/{appeal_id}/decision` | Uphold (remove the review) or dismiss a seller's appeal |
| POST | `/api/v1/admin/seller-review-appeals/{appeal_id}/substantiation-request` | Ask the reviewer to substantiate an appealed review |
| POST | `/api/v1/admin/seller-reviews/{review_id}/removal` | Remove a seller review from the store's page and numbers |
| GET | `/api/v1/admin/store-products` | Stores' product link requests (pending by default) |
| POST | `/api/v1/admin/store-products/{link_id}/decision` | Approve or reject a store's product link (audited; the owner is notified) |
| GET | `/api/v1/admin/support-requests` | Support requests, oldest first (staff) |
| GET | `/api/v1/admin/support-requests/{request_id}` | One support request (staff) |
| POST | `/api/v1/admin/support-requests/{request_id}/assign` | Take a support request (staff) |
| POST | `/api/v1/admin/support-requests/{request_id}/respond` | Answer the seller, optionally moving the status (staff) |
| POST | `/api/v1/admin/support-requests/{request_id}/status` | Set a support request's status, with an internal note (staff) |
| PUT | `/api/v1/admin/users/{user_id}/investigation` | Mark or clear an account as under investigation (halves vote weight) |
| POST | `/api/v1/admin/users/{user_id}/tokens` | Admin token grant/deduct (administrator; audited via ledger) |
| POST | `/api/v1/products/{product_id}/aliases` | Add search aliases (synonyms) to a product (administrator) |
| POST | `/api/v1/products/{product_id}/attach` | Attach a pending submission to an existing product (administrator) |
| POST | `/api/v1/products/{product_id}/canonicalize` | Set a pending product's canonical name (administrator) |
| POST | `/api/v1/products/{product_id}/image` | Set or replace a product's image (administrator) |
| POST | `/api/v1/products/{product_id}/merge` | Merge a catalogue product into another: reviews, questions, prices, requests, store reviews, listings and aliases move; the merged name stays as an alias |

### Signed in (ownership checked in the service where it applies) (97)

| Method | Path | Summary |
| --- | --- | --- |
| POST | `/api/v1/ai/critique` | AI critique of arbitrary draft review text |
| GET | `/api/v1/auth/me` | Current authenticated user |
| PATCH | `/api/v1/auth/me/payout-account` | Set where your payouts are sent |
| DELETE | `/api/v1/comments/{comment_id}` | Remove your comment (or any comment, as an administrator) |
| DELETE | `/api/v1/comments/{comment_id}/follow` | Stop following a comment |
| PUT | `/api/v1/comments/{comment_id}/follow` | Follow a comment: hear about replies to it |
| POST | `/api/v1/comments/{comment_id}/report` | Report another member's comment to the administrators |
| DELETE | `/api/v1/comments/{comment_id}/save` | Remove a comment from your saved comments |
| PUT | `/api/v1/comments/{comment_id}/save` | Save a comment privately |
| DELETE | `/api/v1/comments/{comment_id}/vote` | Remove your vote from a comment |
| POST | `/api/v1/comments/{comment_id}/vote` | Cast or change a vote on a comment |
| GET | `/api/v1/conversations` | Your conversations with the Bluntly team (a store's, with `seller_id`: owner only) |
| POST | `/api/v1/conversations` | Start a conversation (store topics: the store's approved owner; links: your own only) |
| GET | `/api/v1/conversations/link-options` | What a new conversation can be linked to (your own appeals, claims, payouts, reviews, reports) |
| GET | `/api/v1/conversations/unread` | How many of your conversations have an unread reply |
| GET | `/api/v1/conversations/{conversation_id}` | One of your conversations (another's: 404) |
| POST | `/api/v1/conversations/{conversation_id}/email-copy` | Email yourself a copy (your own only) |
| POST | `/api/v1/conversations/{conversation_id}/messages` | Reply in your conversation (another's: 404); reopens a closed one |
| GET | `/api/v1/conversations/{conversation_id}/messages/{message_id}/attachment` | A 5-minute signed link to an attachment (the member or staff; others: 404) |
| POST | `/api/v1/conversations/{conversation_id}/resolve` | Mark your conversation resolved |
| GET | `/api/v1/notifications` | Your notifications, newest first |
| POST | `/api/v1/notifications/read-all` | Mark every notification read |
| GET | `/api/v1/notifications/unread-count` | How many are unread |
| DELETE | `/api/v1/notifications/{notification_id}` | Clear one notification from your list |
| POST | `/api/v1/notifications/{notification_id}/read` | Mark one notification read |
| POST | `/api/v1/notifications/{notification_id}/unread` | Mark one notification unread again |
| GET | `/api/v1/payouts` | Your payouts |
| GET | `/api/v1/payouts/balance` | Your cleared (withdrawable) and pending balances |
| POST | `/api/v1/payouts/cashout` | Request a cashout of cleared funds (no cooldown; batched) |
| GET | `/api/v1/payouts/simulate` | Preview a GCash or Maya payout of your balance (simulation; moves no money) |
| POST | `/api/v1/products` | Create a product, or return the existing one it duplicates |
| GET | `/api/v1/products/resolve-link` | What a pasted marketplace link tells us, without fetching it |
| POST | `/api/v1/products/{product_id}/prices` | Submit a community price observation (FR-2) |
| POST | `/api/v1/questions` | Ask a question about a product or a store |
| GET | `/api/v1/questions/mine` | Your questions and their answers, or the questions you answered |
| POST | `/api/v1/questions/{question_id}/answers` | Answer a question |
| POST | `/api/v1/questions/{question_id}/answers/{answer_id}/best` | Award Best Answer (asker only) |
| PUT | `/api/v1/questions/{question_id}/subscription` | Turn "Notify me" on or off for a question (QA-045) |
| GET | `/api/v1/reports/earnings-statement` | Your earnings statement for a period |
| POST | `/api/v1/requests` | Post a review request (AI-screened; free to post) |
| DELETE | `/api/v1/requests/{request_id}` | Cancel your open request (refunds the escrow) |
| POST | `/api/v1/requests/{request_id}/fulfill` | Claim a request with your own published review |
| DELETE | `/api/v1/requests/{request_id}/upvote` | Remove your up-vote |
| POST | `/api/v1/requests/{request_id}/upvote` | Up-vote a request (says you want this reviewed too) |
| GET | `/api/v1/review-drafts` | Your unfinished reviews, newest first |
| DELETE | `/api/v1/review-drafts/{slot}` | Discard an unfinished review |
| PUT | `/api/v1/review-drafts/{slot}` | Save an unfinished review (an older save never replaces a newer one) |
| POST | `/api/v1/reviews` | Submit a review |
| GET | `/api/v1/reviews/mine` | Your own reviews in every state, newest first |
| POST | `/api/v1/reviews/photo` | Upload a PUBLIC review photo; returns its URL |
| POST | `/api/v1/reviews/receipt` | Upload proof of purchase to private storage |
| DELETE | `/api/v1/reviews/{review_id}` | Delete your review entry (the root deletes the whole thread) |
| PATCH | `/api/v1/reviews/{review_id}` | Replace a review's photo (once, within 72 hours) |
| POST | `/api/v1/reviews/{review_id}/comments` | Post a comment or a reply |
| POST | `/api/v1/reviews/{review_id}/critique` | AI critique of a stored review (author or administrator) |
| GET | `/api/v1/reviews/{review_id}/receipt` | Signed, short-lived access to a review's proof of purchase |
| POST | `/api/v1/reviews/{review_id}/report` | Report a published review to the administrators |
| POST | `/api/v1/reviews/{review_id}/updates` | Add an update entry to your review's thread (every 3 months) |
| DELETE | `/api/v1/reviews/{review_id}/vote` | Remove your helpfulness vote from a review |
| POST | `/api/v1/reviews/{review_id}/vote` | Cast or change a helpfulness vote on a published review |
| POST | `/api/v1/sellers` | Find a store, or add it if it is new |
| GET | `/api/v1/sellers/appeals/{appeal_id}` | Read an appeal against your store review (reviewer) |
| POST | `/api/v1/sellers/appeals/{appeal_id}/substantiation` | Back up your store review when an admin asks (reviewer) |
| GET | `/api/v1/sellers/claims/mine` | Your own store claims, newest first, any status (caller only) |
| POST | `/api/v1/sellers/claims/{claim_id}/withdraw` | Withdraw your own pending store claim (another's: 404) |
| GET | `/api/v1/sellers/mine` | Stores this account runs (approved claims only) |
| DELETE | `/api/v1/sellers/replies/{reply_id}` | Delete your own reply under a seller review |
| POST | `/api/v1/sellers/reviews/{review_id}/appeal` | Flag a review of your store as suspected fake (claimed owner) |
| POST | `/api/v1/sellers/reviews/{review_id}/replies` | Reply under a seller review |
| POST | `/api/v1/sellers/reviews/{review_id}/report` | Report a seller review to the administrators |
| POST | `/api/v1/sellers/reviews/{review_id}/response` | Respond publicly to a review of your store (claimed owner) |
| DELETE | `/api/v1/sellers/reviews/{review_id}/vote` | Take back your vote on a seller review |
| PUT | `/api/v1/sellers/reviews/{review_id}/vote` | Vote a seller review helpful or not (helpfulness only) |
| GET | `/api/v1/sellers/{seller_id}/appeals` | The flags this store's owner raised (approved owner only; reviewer proof hidden) |
| POST | `/api/v1/sellers/{seller_id}/claims` | Ask to be recognised as this store's owner |
| GET | `/api/v1/sellers/{seller_id}/dashboard` | The approved owner's view of their store (review monitoring; `period`) |
| GET | `/api/v1/sellers/{seller_id}/export` | The store's own data as CSV files in a zip; `include`, `period` (approved owner only; buyer names shortened, no contact details or order IDs) |
| GET | `/api/v1/sellers/{seller_id}/export/sizes` | Rows in each export file (approved owner only) |
| POST | `/api/v1/sellers/{seller_id}/give-up` | Give the store up: it goes back to unclaimed (approved owner only; audited `store_release`; §9 limits stay on the account) |
| GET | `/api/v1/sellers/{seller_id}/insights` | Store review figures by month and against the median store on the marketplace; `period` (approved owner only; staff too get 403) |
| GET | `/api/v1/sellers/{seller_id}/products` | Your store's linked products and link requests (approved owner only; others 403) |
| POST | `/api/v1/sellers/{seller_id}/products` | Ask to link a catalogue product your store sells (owner only; a moderator approves) |
| GET | `/api/v1/sellers/{seller_id}/products/options` | Catalogue products your store could link (owner only) |
| POST | `/api/v1/sellers/{seller_id}/products/{link_id}/cancel` | Cancel a link request still waiting (owner only) |
| GET | `/api/v1/sellers/{seller_id}/products/{product_id}/analytics` | A linked product's figures (owner only, approved links only) |
| GET | `/api/v1/sellers/{seller_id}/profile` | The store and how its claim was verified; registration by its last 4 characters only (approved owner only) |
| GET | `/api/v1/sellers/{seller_id}/questions` | The store's questions with its own answers; `status` needs / answered / all (approved owner only) |
| GET | `/api/v1/sellers/{seller_id}/reports/rating-summary` | A store's rating summary (its approved owner, or staff) |
| POST | `/api/v1/sellers/{seller_id}/reviews` | Rate a store on FR-4's four dimensions |
| GET | `/api/v1/sellers/{seller_id}/search` | Search your store's reviews, questions and reviewed products (approved owner only; others: 403) |
| GET | `/api/v1/sellers/{seller_id}/support-requests` | Your store's support requests, newest first |
| POST | `/api/v1/sellers/{seller_id}/support-requests` | Contact the administrators about your store |
| GET | `/api/v1/sellers/{seller_id}/support-requests/{request_id}` | One of your store's support requests |
| GET | `/api/v1/tokens/balance` | Your token balance |
| GET | `/api/v1/tokens/transactions` | Your token transaction history (append-only ledger) |
| PATCH | `/api/v1/users/me` | Update the current user's profile |
| POST | `/api/v1/users/me/password` | Change your password: current one required, new ≥ 10 characters; rate-limited; 409 for an email-code account with no password; emails a notice |
| DELETE | `/api/v1/users/me/avatar` | Remove the current user's avatar |
| POST | `/api/v1/users/me/avatar` | Upload or replace the current user's avatar |
| GET | `/api/v1/users/me/dashboard` | Earnings, views and ranked reviews for the signed-in user |
| GET | `/api/v1/users/me/earnings` | The signed-in reviewer's own earnings history |
| GET | `/api/v1/users/me/saved-comments` | The comments you saved (visible to you only) |
| GET | `/api/v1/users/me/streak` | The signed-in reviewer's contribution streak and calendar |

| PUT | `/api/v1/questions/{question_id}/vote` | Up-vote a question (not your own; 0073) |
| PUT | `/api/v1/questions/{question_id}/answers/{answer_id}/vote` | Vote an answer up/down/null (not your own) |
| POST | `/api/v1/questions/{question_id}/answers/{answer_id}/replies` | Reply in an answer's thread |
| PUT | `/api/v1/questions/{question_id}/replies/{reply_id}/vote` | Vote a reply (not your own) |
| DELETE | `/api/v1/questions/{question_id}/replies/{reply_id}` | Remove a reply: its author, or Administrator / Super Admin |
| POST | `/api/v1/questions/{question_id}/answers/{answer_id}/report` | Report an answer (not your own) |

### Public (37)

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/` |  |
| POST | `/api/v1/auth/login` | Log in (OAuth2 password flow; username = email) |
| POST | `/api/v1/auth/otp/request` | Request a one-time login/signup code by email |
| POST | `/api/v1/auth/otp/verify` | Exchange a one-time code for an access token |
| POST | `/api/v1/auth/register` | Register a new account |
| POST | `/api/v1/internal/cron/{task}` | Run one scheduled maintenance task |
| POST | `/api/v1/internal/reading-telemetry` | Merge one private reading checkpoint |
| POST | `/api/v1/internal/traffic` | Record one request's aggregate geography |
| GET | `/api/v1/membership-tiers` | List membership tiers |
| GET | `/api/v1/membership-tiers/{code}` | Get a membership tier |
| GET | `/api/v1/postback/lazada` | Lazada order postback (public, shared-secret auth) |
| GET | `/api/v1/products` | List products |
| GET | `/api/v1/products/compare` | Side-by-side comparison of 2-4 products (FR-2) |
| GET | `/api/v1/products/{product_id}` | Get a product (always retrievable; low_trust computed) |
| GET | `/api/v1/products/{product_id}/prices` | Community price panel for a product (FR-2) |
| GET | `/api/v1/questions` | List questions |
| GET | `/api/v1/questions/{question_id}` | Get a question with its answers |
| GET | `/api/v1/requests` | List review requests |
| GET | `/api/v1/requests/{request_id}` | Get a request |
| GET | `/api/v1/reviews` | List reviews (published; author/mod see more) |
| GET | `/api/v1/reviews/feed` | Public feed: published reviews joined with author + product |
| GET | `/api/v1/reviews/{review_id}` | Get a review |
| GET | `/api/v1/reviews/{review_id}/comments` | List the comment thread on a review |
| GET | `/api/v1/reviews/{review_id}/full` | A review with its author + product (respects the publication gate) |
| GET | `/api/v1/reviews/{review_id}/thread` | A review's thread: every visible entry, the latest counts |
| GET | `/api/v1/reviews/{review_id}/versions` | List a review's version history |
| GET | `/api/v1/reviews/{review_id}/versions/{version_number}` | Get a specific review version |
| GET | `/api/v1/sellers` | Search stores |
| GET | `/api/v1/sellers/{seller_id}` | A store with its public rating summary |
| GET | `/api/v1/sellers/{seller_id}/reviews` | A store's ratings, newest first |
| GET | `/api/v1/users/public/{handle}` | A reviewer's public profile, by username or id |
| GET | `/api/v1/users/search` | Find people by @handle or name, to open their profile |
| GET | `/api/v1/users/username-available` | Whether a username is free to claim |
| GET | `/api/v1/users/{user_id}/comments` | List the comments a member has written |
| GET | `/api/v1/users/{user_id}/trust` | Public trust profile (stage, reputation, badges) |
| GET | `/health` | Liveness / identity probe |
| GET | `/r/{review_id}` | Referral attribution redirect (public) |

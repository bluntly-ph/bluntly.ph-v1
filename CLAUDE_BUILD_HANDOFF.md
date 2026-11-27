# BLUNTLY BUILD HANDOFF

Timestamp: 2026-10-05 — SESSION 14 in progress: QA closure campaign continued (BLUNTLY_QA.xlsm). Read SESSION 14, then 13.
Branch: defense-build-oct6 — THE ONLY DEVELOPMENT BRANCH (owner instruction, session 9). Sessions 7–8
  worked on claude/elegant-gauss-2ikk4a; session 9 fast-forwarded defense-build-oct6 onto it (e26619f).
HEAD / Remote HEAD: see CENTRAL BRANCH STATE (recorded at each push)
Working tree: clean at each pushed checkpoint

DEFENSE:
October 6, 2026 (build target October 5)

## SESSION 14 (2026-10-05, from ~03:15 UTC) — QA CLOSURE CONTINUED — READ THIS FIRST

START STATE: fresh container, tree clean. The interrupted session 13 had pushed EVERYTHING before its limit
  (PageNumbers.tsx landed in 9bf8625; QA-059/016/024/062/050, MQA-036/037 on defense at d7db78b). Nothing
  local to protect; the old scratch patch (claim evidence / CSV importer / skeletons) was not reapplied —
  remote defense is authoritative for those and session 12 had judged it non-unique.
BRANCH: defense-build-oct6 (fast-forward pushes only; each checkpoint mirrored to claude/vibrant-newton-msudxr).
CURRENT MAIN SHA: 370f702 (release 4, production; DB at 0085_email_outbox — verified via connector).
CURRENT DEFENSE SHA: see `git log origin/defense-build-oct6` (a0771bc at checkpoint 11; CI 233 + 235 green;
  230/231 were red on the 0092 dry-run list only — fixed bb96e5f).
MIGRATIONS NOT ON PRODUCTION: 0086, 0087, 0088, 0089, 0090 (session 12/13) + 0091_store_change_requests
  (session 14, additive: one table, RLS on, no grants) + 0092_support_waiting (two enum values; ALTER TYPE
  ADD VALUE, run OUTSIDE BEGIN…COMMIT like 0089) + 0093_message_edits (additive: 2 nullable columns on
  conversation_messages, 2 tables, RLS on, no grants). TEST project last recorded at 0089.
SESSION INTERRUPTION: a usage-limit/worker restart hit after the support cluster was browser-verified but before
  its commit; the tree survived intact, the stack was restarted, checks re-run (68 backend, 569 frontend) and it
  was committed as 76428ac.
DEFENSE WALKTHROUGH: 7/7 locally on a production build + fresh defense seed (after MQA-004/015 + skeletons).
WORKBOOK: BLUNTLY_QA.xlsm unchanged since 2026-10-04 21:22 UTC (re-downloaded, read with openpyxl).
CI: runs 221-223 (2ec55dc..ed9b0a6) failed ONLY at "Backend (no database) > ruff" (my tests/ lint; the
  PG17 full suite + frontend were green). Fixed in 7e5a8fa; reproduced locally first (ruff app/ scripts/
  tests/, then the no-DB pytest step: 2233 passed, 954 skipped). LESSON: run `ruff check app/ scripts/
  tests/` before every push, not app/ only.

### SESSION 14 QA LEDGER (engineering state; tester Status columns untouched)
| QA | Tester | Root cause | Fix | Files | Commit | Tests | Browser | State |
|---|---|---|---|---|---|---|---|---|
| QA-050 (Figma re-read) | Fail | Figma reauthenticated 2026-10-05 (owner): the file was reorganised, the Questions tab is now `Screen/Search/Questions` 7718:12930 (3481:1894 is gone). Against it, "<product> hot turbo" showed "No match for your search" while "Does it get hot after an hour on turbo?" sat under Related: qa_service.list_questions matched the question words as ONE phrase (`%hot turbo%`), so words apart never matched (the frame's own "noise library" → "How much noise … quiet library?" could not either). Also Similar questions was empty with one match, "See all 3 other questions" counted the best match itself, and the Ask card truncated with no tooltip | Words matched one by one (3+ letters, stopwords dropped, LIKE-escaped), ranked by how many a question holds (date order kept for sort=oldest); Similar fills to the frame's three with the product's other questions; "See all N other" excludes the best match; Ask card wraps | qa_service.py, app/search/page.tsx, components/search/QuestionMatch.tsx, tests/test_question_word_match.py | (this commit) | test_question_word_match (2); 244 question/search tests; ruff app/ scripts/ tests/ | 390 + 320 vs the frame: best match found, author header, 2 similar, "See all 2 other questions" | FIXED_PENDING_RETEST. Kept on purpose: All filters / Sort pills (functional), no "N watching" (no public watcher count) |
| QA-062 (follow-up) | Partially Fixed | Only message attachments translated a storage failure; with no credentials (or a missing bucket / storage down) POST /reviews/photo, avatar, receipt, product image answered a bare 500 | One `_put` writer in services/storage.py: 503 `storage_unavailable` "Photo uploads aren't available right now. Nothing was saved - please try again in a few minutes."; size/type validation still first (413/415 unchanged). Photo + receipt "8 MB" messages corrected to the enforced 4 MB | backend/app/services/storage.py, tests/test_storage_unavailable.py | b017adf | 14 new (each helper × no-creds/down, 415 before storage, cap text, route 503) + receipt/duplicate/product-image/claim-evidence suites | live API: 503 + sentence; non-image 415; all 3 photo forms show `detail` | FIXED_PENDING_RETEST. LOCAL = missing credentials (expected), not a production regression |
| MQA-045 | Open / Medium | Overview "Open reports" = distinct reported ITEMS (needs_attention_service); Reports tab = `reports.length` = report ROWS of a `limit=50` page that discarded `total`; non-open statuses' `total` = page length. Production: 6 open report rows on 4 items (exactly the tester's 6 vs 4) | `report_service.count_reports` (same status filter as the list, `_reports_where`) feeds both. Overview row "Open reports 6 · on 4 items"; tab badge = API total; table footer "6 open reports on 4 items" + console Pagination (?rpage=, 50/page, keeps status/tier/order); ReportQueueResponse.items_total; paged statuses count every match | report_service.py, admin_reports.py, needs_attention_service.py, admin_analytics.py, ReviewQueueScreen.tsx, review-queue-model.ts, NeedsAttentionCard.tsx, lib/moderation.ts, app/admin/review-queue/page.tsx | 2ec55dc | test_needs_attention (+3: rows vs items, Overview == API, paged total), report-counts.test.mjs (4) | 1440+390: Overview 33·on 23 items = tab 33 = footer; rstatus=all 52 → page 2 shows 51–52, Prev keeps filters, Next disabled at end | FIXED_PENDING_RETEST |
| MQA-043 | Open / Medium | Page fetched `limit=100`, no offset, header = rows.length ("100 waiting"); production has 164 pending (145 products) | GET /admin/price-observations gains offset + filters; GET /admin/price-observations/count shares the builder (`PendingQuery`/`_pending`); header "164 prices waiting." / "12 of 164 prices waiting match."; console Pagination 50/100 per page; stale ?page= clamps | price_service.py, admin_prices.py, schemas/product.py, app/admin/prices/page.tsx, components/admin/prices/prices-model.ts, lib/products.ts, AdminSkeletons (pager + toolbar) | e997b02 | test_price_queue_paging (6: walk pages == count for 8 filter sets, orders, filters, usual price, literal search, 422/403/401), prices-model.test.mjs (4) | 1440+390: 61 → page 2 = 51–61, 0 px overflow | FIXED_PENDING_RETEST |
| MQA-007 | Open / Medium | Oldest-first only | Sort: Oldest first (default, FIFO), Newest first, By product | as MQA-043 | e997b02 | test_the_orders | newest via Sort menu, kept with filters | FIXED_PENDING_RETEST |
| MQA-042 | Open / Medium | No filters; a product's prices scattered; outliers unreadable | Filters: Marketplace, Source, Why it waits, Hide prices I reported; product-name search; "Only this product's prices"; each row "Usually ₱699 · 4 approved" (median of approved prices, same window + marketplace as the hold rule); a moderator's own price says so instead of buttons the API refuses | as MQA-043 | e997b02 | test_the_filters_narrow…, test_an_outlier_shows… | outlier filter: ₱24,444 beside "Usually ₱699" | FIXED_PENDING_RETEST |
| MQA-036/037 (regression check) | — | PageNumbers hid Previous/Next at the ends (row shifted) | Disabled-but-present at both ends, like the console pager | components/site/PageNumbers.tsx | e997b02 | — | /feed + /search Reviews: first/middle/last at 390+1440, height constant 36 px | FIXED_PENDING_RETEST |
| MQA-009 | Open / Medium | (a) Composer `ready` required words; API `_clean` refused an empty body → a file alone could not be sent. (b) The attachment ERROR = message-attachments bucket missing on production (verified: storage.buckets has 4, production at 0085; fixed by 0086 on defense, NOT yet applied) | Replies (member + staff) may be a file alone; previews/notices/emails say "Sent a file: name.pdf" (`_said`); words-or-file still required | conversation_service.py, routes/conversations.py, components/messages/Thread.tsx | ba2fcd1, ed9b0a6 (OpenAPI) | test_attachment_only_reply (6) | Send enables with file only; POST goes; locally 503 attachments_unavailable = LOCAL missing credentials | FIXED_PENDING_RETEST (b) BLOCKED on release: apply 0086 to production |
| MQA-010 | Open / Low | Admin claim/appeal CaseChat was a one-line <input> for 2,000 chars; Composer used CSS field-sizing (Chromium only); console CountedTextarea fixed rows | Shared `components/ui/useAutoGrow.ts` (measures; grows to max then scrolls; never wider): Composer ≤160 px, CountedTextarea ≤320 px (Support reply + every staff note), CaseChat → textarea ≤160 px, Enter sends / Shift+Enter newline, bubbles pre-wrap + overflow-wrap:anywhere | useAutoGrow.ts, Thread.tsx, CountedTextarea.tsx, CaseChat.tsx | ba2fcd1 | — (UI) | composer 38→100→160 scroll; claim chat 36→160, Shift+Enter, Enter 201 + cleared, 9-line bubble no overflow; support reply 110→320 | FIXED_PENDING_RETEST |
| (wrap) Review claim/appeal modal | — | `grid md:grid-cols-[1fr_1fr]` = auto track on phones → body 420 px in a 358 px modal | minmax(0,1fr) tracks, wrapping values, 104 px label below sm | SellersScreen.tsx | ba2fcd1 | — | sideScrollers = [] for claim + appeal modal at 390 | FIXED_PENDING_RETEST |
| MQA-012 | Open / Medium | Store page always offered "Claim this store" (own pending claim refused only at submit); a second member could file a competing claim. Production: no store has 2 claims | RULE CHOICE (reversible, owner may override): one claim under review per store from anyone (store row locked; 409 `claim_under_review` "…message the Bluntly team"). Public detail `claim_under_review` (never whose). Claimant: "Your claim is being reviewed · Sent <date>" + Open Messages + Withdraw; others: "A claim on this store is being reviewed" | seller_service.py, schemas/seller.py, ClaimSellerForm.tsx, app/sellers/[id]/page.tsx, lib/sellers.ts | 2ed211f | test_claim_under_review (2), test_seller_console_api adapted (its "someone else's claim" moved to another store) | 390+1440: own / other / withdraw → form back | FIXED_PENDING_RETEST |
| MQA-013 | Open / Medium | Claim form had no upload (evidence only via Messages after the fact) | "Proof of registration (optional)": ≤3 photos/PDFs, 4 MB each, sent after the claim into the claim's case thread (start() may open a LINKED case thread with a file alone) — the admin Review claim modal already lists those files; a failed file is named and the claim stays in | ClaimSellerForm.tsx, conversation_service.start | 2ed211f | test_a_claims_proof_can_open_its_case_thread_alone | 390: two files listed → claim 201 → locally both uploads 503 (missing credentials) → "These files weren't attached… send them from Messages" | FIXED_PENDING_RETEST (production upload needs 0086) |
| MQA-004 | Open / Medium | Renaming always worked (Edit > From parts / As is), but "Add to catalogue" closed the modal and the product moved silently to Catalogue, where Edit was opacity-0 until hover | Admit reopens the new product in Edit with "Its name can be changed here at any time (Products > Catalogue > Edit)"; Edit visible on both tables, labelled with the product | ProductEditModal.tsx, ProductsScreen.tsx | d5053e9 | — (UI); defense walkthrough scene 6 updated | admit → reopen → rename → catalogue row renamed, Edit opacity 1 | FIXED_PENDING_RETEST |
| MQA-015 | Open / Medium | Taken-down reviews were queue candidates by design ("never stranded"), so they sat among the work and in the counts | Queue `view`: waiting (default; tab badge, Overview backlog, past-due) / taken_down (Restore on the card); note "13 taken down — decided, so not in this list"; Filters › Show with counts.by_view; ?open= finds either. The queue's hand-rolled pager → shared Pagination (+ `hrefFor` for offset/limit URLs) | referral_service.py, admin_referral.py, schemas/referral.py, QueueReviewsView.tsx, review-queue-model.ts, Pagination.tsx, review-queue/page.tsx | 7fb094b, ac48956 | queue suites 183 passed; 4 tests moved to the rule; queue-view.test.mjs (2) | 1440+390: 361 waiting, 13 taken down, page 2 via ?offset=50, Restore offered | FIXED_PENDING_RETEST |
| (skeletons) | — | Walkthrough scene 7 failed once (/search +48 px at 320): it measures at `load`, i.e. the streamed loading skeleton; 4 skeletons were wider than a phone | /search tabs, /questions header, /requests title+chip, profile tabs sized to the real phone layout | app/search|questions|requests/loading.tsx, ProfilePageSkeleton.tsx | 115194a | — | JS off (skeleton) + JS on, 64 route×role checks at 320: ALL CLEAN; walkthrough 7/7 on a production build, fresh defense seed | FIXED |
| (feed paging) | — | Feed/lens orders had no tiebreaker; reviews written in one transaction share created_at → an offset page repeated/skipped reviews (1,017 walked, 1,007 distinct) | Every feed and lens order ends on Review.id; paged report list on its id | review_service.py, review_lenses.py, report_service.py | f9a62e0 | test_feed_count now passes with tie data present | — | FIXED (MQA-036/037 retest covers it) |
| MQA-017 | Open / Low | One change per request | Request a change: tick several (name, link, registration); "Give it up instead" link | StoreProfileActions.tsx, profile-model.ts | bb7bfdb | seller-insights-model (payload/title) | 390: 2 changes sent together | FIXED_PENDING_RETEST |
| MQA-018 | Open / Medium | Each change opened its own thread | One request = one conversation, titled "Store name and store link change" | store_change_service.submit | bb7bfdb | test_several_changes_are_one_request_in_one_thread | admin thread shows both | FIXED_PENDING_RETEST |
| MQA-019 | Open / Medium | Change = free text; no current vs requested, no Approve/Reject, nothing applied | 0091 store_change_requests (field, current, requested, status, decider); Inbox panel Now → Asked for, Approve applies to the store (audited old/new, staff note in thread, notification), Reject needs a reason | store_change_service.py, routes/store_changes.py, StoreChangesPanel.tsx, InboxScreen.tsx | bb7bfdb | test_approving_applies…, test_a_rejection_needs_a_reason… | approve → store link set; reject → reason shown | FIXED_PENDING_RETEST |
| MQA-020 | Open / Medium | No marketplace check on store links; production jisulife = Shopee + lazada.com.ph link, claimed | link_mismatch: refused when asked for, when a store is added, and at claim approval (409 store_link_mismatch); claim modal shows it + inline "Save link" (POST /admin/sellers/{id}/details, recorded as an approved change) | as above + seller_service.decide_claim, SellersScreen.tsx, schemas/seller.py | bb7bfdb | test_a_link_on_another_marketplace…, test_a_claim_on_a_store_with_a_link… | seller dialog: "That link is a Lazada page, but this store is on Shopee." | FIXED_PENDING_RETEST; production jisulife row NOT edited (needs release + a moderator's correction) |
| MQA-025 | Open / Medium | No state tied to the store | Each change: pending / approved / rejected, on the thread panel AND the seller's Store profile ("Requested changes") | SellerStoreProfile.tsx, profile page, lib/seller-console.getStoreChanges | bb7bfdb | test_approving… (owner list) | seller sees Approved / Not approved + reason | FIXED_PENDING_RETEST |
| MQA-027 | Open / Medium | Claim-reply notice linked /sellers/{store} (public page) | Notices use the conversation link: pending claimant → /messages/{id}; approved owner → /seller/{id}/messages?c=…; store appeals → console thread; reviewer appeal keeps its page | case_chat_service.py, conversation_service._member_link | f32ea86 | test_claim_notice_link | — (API) | FIXED_PENDING_RETEST |
| MQA-021 | Open / Medium | Move to Support CLOSED the thread and copied it into a ticket with one overwritten reply | The thread stays the request's one history: Support replies are written into it, Inbox replies become the request's last reply, panel links "Open the conversation" | conversation_service.move_to_support/staff_reply, support_service.respond, SupportQueue.tsx | 76428ac | test_support_one_thread (4) | admin reply → seller thread shows it | FIXED_PENDING_RETEST |
| MQA-022 | Open / Medium | Reply defaulted to "In review"; two status controls | One choice at reply: Ask for more information (new status waiting_for_seller, 0092) / Keep in review / Resolve; second control = "Change the status without replying"; views Waiting on us / Waiting for seller (n) / Closed / All; Overview no longer counts waiting-for-seller | enums, 0092, support_service, needs_attention_service, SupportQueue.tsx, support-model | 76428ac | as above + support-model tests | radio "Ask…" → "Waiting on you" for the seller | FIXED_PENDING_RETEST |
| MQA-023 | Open / Medium | Request page had no reply path | Notice opens the thread (reply + attach there); page shows "Action needed" + "Reply in Messages"; seller reply → In review | support page, conversation_service._member_answered_request | 76428ac | test_the_ticket_reply_lands… | 390: Action needed, link, reply → In review | FIXED_PENDING_RETEST |
| MQA-024 | Open / Medium | Thread "closed" while ticket "In review"; left the Open list | Thread mirrors the request (waiting / closed / open); Inbox status menu moves the request; seller chip shows the request's words (support_status) | support_service.mirror_to_conversation, conversation_service.set_status/_detail, MemberMessages.tsx | 76428ac | test_resolving_closes… | chip "Waiting on you" | FIXED_PENDING_RETEST |
| MQA-026 | Open / Low | Title "Account · Store link change: https://…", message prefixed "Store · 5 Oct:", generic category, code in notice titles | Title = thread subject (store changes: "Store link change"), first message verbatim, category "A store change" (0092, team-filed only), code only in notice body | conversation_service.move_to_support, support-model | 76428ac (+ bb7bfdb titles) | test_conversations move test | admin panel title/message verbatim | FIXED_PENDING_RETEST |
| MQA-029 | Open / Low | "An administrator answered SUP-…" vs "Bluntly replied about…" | "Bluntly replied: <subject> · your reply is needed", "Bluntly is reviewing your request: <subject>", "<subject>: resolved" | support_service._tell_seller | 76428ac | test_the_ticket_reply_lands… (title/body) | — | FIXED_PENDING_RETEST |
| MQA-030 | Open / Low | Seller saw "Moved to Queue → Support (SUP-…)" | Member wording "Your request was passed to our support team"; staff wording unchanged | messages-model.eventText | 76428ac | messages-model test | seller thread: plain line, no code | FIXED_PENDING_RETEST |
| MQA-033 | Open / Medium | Sellers tab defaulted to Name A–Z | Default "ranked": Wilson lower bound (95%) of the share of 4★+ visible reviews + ≤0.1 for reviews in the last 90 days (cap 5); "reviews" / "name" stay as explicit orders; Sort sheet "Best evidenced / Most reviews / Name (A–Z)" with the rule as info | seller_service.list_sellers/seller_rank_score, routes/sellers.py, search-tabs-model.ts, SearchFilterBar.tsx, lib/sellers.ts | 4e710fe | test_seller_ranking (4), test_figma_search_filters pinned to name, search-tabs.test.mjs (+1) | /search?tab=sellers 1440+390: 5-review stores above 3-review; Name link → &sort=name | FIXED_PENDING_RETEST |
| MQA-035 | Open / Medium | /search desktop rail showed the review feed's controls on Sellers/Questions; every link left the tab | Per-tab rail: Sellers = order / marketplace / claimed; Questions = order / time; Reviews unchanged; same URLs as the sheets | app/search/page.tsx | 4e710fe | search-tabs tests | rail links stay on tab=sellers / tab=questions | FIXED_PENDING_RETEST |
| MQA-003 | Open / Medium | Reports view had none of the queue card's integrity checks | GET /admin/reports attaches `review_signals` to each reported review on the page, built by the queue's own card builder (referral_service.review_queue_cards) + reused-photo flag; row shows what fired; drawer lists every check, flagged first; "not_run" (no provider / no photo) never reads as a pass | admin_reports.py, referral_service.py, ReportDetailPanel.tsx, ReviewQueueScreen.tsx, review-queue-model.reviewIntegrityChecks, lib/moderation.ts | cf0c07c | test_report_signals (4), report-integrity-checks.test.mjs (4) | 1440+390: "Voting ring · 5 of 8 up-voters…" flagged, RIS/plagiarism "did not run" | FIXED_PENDING_RETEST (RIS/plagiarism providers still not procured — ADR-007) |
| MQA-011 | Open / Medium | No edit / unsend / delete-for-me | 0093: sender (on the side they sent from) may Edit or Unsend for 15 min (CHANGE_WINDOW); "Edited" / "This message was unsent."; unsent file deleted from storage; prior words kept in conversation_message_revisions (audit, no screen); anyone may Delete for me; staff edits/unsends in the moderation log; live thread refreshes on edits; case chat shows unsent | 0093_message_edits.py, models/conversation.py, conversation_service, case_chat_service, routes/conversations.py, Thread.tsx (MessageItem), messages-model.messageActions/threadSignature | 49de061 | test_message_edits (6), message-actions.test.mjs (4) | admin edit → "Edited"; unsend → both sides; seller Delete for me 5→4 rows; 1440+390 no overflow | FIXED_PENDING_RETEST. PRODUCT CHOICES (reversible): 15-min window; text kept for audit after unsend |
| MQA-034 | Open / Low | Claimed and unclaimed badges alike (49% ink) | Claimed = trust blue + filled seal; unclaimed keeps muted grey | SellerIdentity.ClaimStatusLine | 85f6385 | — | 390: claimed rgb(55,113,200) opacity 1 | FIXED_PENDING_RETEST |
| MQA-038 | Open / Low | Rate-a-seller title capped at 30 and cut mid-word; pastes silently shortened | 80 chars (API allows 200); no truncation on type/paste — counter says "5 characters over the limit" and contentBlocker holds Submit; description no longer truncates at 2,000 either | seller-model.ts, RateSellerForm.tsx | 85f6385 | seller-model.test.mjs (+2) | 390: 54-char headline kept, 85 → "5 over" | FIXED_PENDING_RETEST. Product-review titles keep their 30 (composer-gate-model) — separate decision |
| MQA-039 | Open / Low | "30/30 characters" vs "15 characters remaining" | One format: "54 / 80", "10 / 2000"; minimum in the hint ("at least 15 characters"); "5 more characters needed" while short (fieldCounter) | as MQA-038 | 85f6385 | fieldCounter tests | 390 screenshot | FIXED_PENDING_RETEST |
| MQA-044 | Open / Low | Six columns in the ~400px card → "comments" ran into "reports" | Three equal columns × two rows, capitalised wrapping labels; open reports red | QueueReviewModal.tsx | 85f6385 | — | each label 109–122px in its own cell at 390 and 1440 | FIXED_PENDING_RETEST |
| MQA-001 | Open / Low | Escalation order only; a new report hard to find | Sort "Newest first" (sort=newest) + "New" marker on open reports < 24h; default stays escalation (Business Rules §12) | admin_reports.py, review-queue-model (isNewReport), ReviewQueueScreen.tsx | 93fa215 | test_newest_first…, report-newest.test.mjs (2) | rsort=newest → 1m-old report first | FIXED_PENDING_RETEST |
| MQA-002 | Open / Low | Reason / actions no hierarchy | Drawer leads with "Reported for" block (reason 18px semibold + reporter's words or "Filed by the System"), then "Open the reported item" button and (phone) "Why was this reported?" jump; modal titled by the item; table reason medium | ReviewQueueScreen.tsx, ReportDetailPanel (id) | 93fa215 | — | 1440 + 390 screenshots | FIXED_PENDING_RETEST |
| MQA-032 | Open / Low | Seller top-bar icons: dot or nothing | Count badges (1–9, "9+", hidden at 0; unreadBadge); refreshed on every page/conversation opened and every 30s (useLiveCount); "Mark all seen" clears at once | components/ui/unread.ts, UnreadBadge.tsx, useLiveCount.ts, SellerShell.tsx, StoreNotifications.tsx | 608da4e | unread-badge.test.mjs | 390: chat 2, bell 9+; open one → chat 1 | FIXED_PENDING_RETEST |
| MQA-028 | Open / Low | Reply could go out with {{store_name}}; no template picker | Every staff box (Inbox, Support reply, case chat) warns "Fill in {{store_name}} and {{platform}} before sending." and holds Send; API 422 template_unfilled on Inbox reply/edit, case chat, Support respond; Inbox Templates menu (4 replies) filled from the thread (seller name, store, marketplace — rows now carry seller_platform) | messages-model (unfilledTags/fillTemplate/REPLY_TEMPLATES), Thread.Composer, InboxScreen, SupportQueue, CaseChat, conversation_service.no_template_tags, support_service.respond | 3b94014 | test_a_staff_reply_with_an_unfilled_template_tag…, reply-templates.test.mjs (2) | 1440: warning + Send disabled; template → "Hi Rico … PowerHub PH on Shopee" | FIXED_PENDING_RETEST |
| MQA-031 | Open / Low | Member /messages = 480px column, one page per thread; console two-pane only from lg | /messages + /messages/<id>: list (MessagesRail) left + thread right from lg, URL per conversation, phone unchanged (back arrow); console two-pane from md (280px list until xl) | app/messages/page.tsx, app/messages/[id]/page.tsx, ReviewerMessages.MessagesRail, MemberMessages.tsx | 72e2bf1 | — | 1440/1024/800/390, no overflow; switching keeps the rail | FIXED_PENDING_RETEST |
| (wrap) Console pagination | — | "Showing 1–25 of 305" shrank to 0 in the Inbox list and broke "Showin / g" | min-w-fit + nowrap; buttons wrap instead | components/console/Pagination.tsx | 4f375e0 | — | 1440/1024/390: one line | FIXED |
| (CI) runs 230/231 | — | test_migration_dryrun: 0092 downgrade is a deliberate no-op (enum values) but was not on DELIBERATE_NO_OP_DOWNGRADES; 3209 others passed | listed it | tests/test_migration_dryrun.py | bb96e5f | full no-DB suite locally 2249 passed | — | FIXED. LESSON: run the WHOLE no-DB suite (unreachable DB) before a push that adds a migration |

PAGINATION: ONE model (components/console/pagination-model.ts: pageCount, clampPage, pageSize, shownRange,
  pageWindow) with two skins — console `Pagination` (Figma 7998:11931) and public `PageNumbers` (pills).
  No duplicate primitive. Converted this session: Admin Reports tab (?rpage), Admin Prices (?page/&size).
  Already on it: People, Reviewers, Products, Sellers, Payouts, Affiliate, Inbox, Special routing, All
  reviews, search Reviews, Feed. Admin Sellers > Claims / Appeals read only the OLDEST 200 (found by the full
  suite on a 264-claim local DB): the API now takes `offset` with an id tiebreak and lib/sellers reads every
  page (≤5,000); the screen's own filters + pager then cover all (272 locally). Answers tab reads ≤100 threads.
REPORT COUNTS: authoritative = report_service.count_reports (rows + distinct items, same filter as the
  list). Production now: 6 open reports on 4 items; 5 escalated; 2 resolved.
SHARE: unchanged this session (session 13 QA-024 coverage stands).
SELLER CROP: unchanged (session 13 d7db78b); storage failure now a 503 sentence (b017adf).
SUPABASE (read-only, production byobedbhodhvocgrkrse): report rows/items; pending prices 164 (155
  no_baseline, 0 outlier, 145 products); seller claims (no store with >1 claim); storage.buckets (no
  message-attachments); alembic_version 0085_email_outbox.
FIGMA: not needed for the Moderator items. QA-050's Figma comparison is BLOCKED this session: the Figma (and
  supabase) MCP servers need re-authorisation (owner: claude.ai connector settings); google-sheets failed to
  connect. Nothing was compared against Figma from memory.
MODERATOR SHEET: every MQA-001..045 item now has an engineering state above or in session 13's matrix.
MAIN SHEET (Fail / Partially Fixed / Deferred): every item has a state in session 13's matrix; QA-005
  (Deferred, footer socials) = the "remove until official accounts exist" option is already live (SiteFooter
  SOCIALS commented out) → BLOCKED_PRODUCT_DECISION until the owner supplies the accounts.
REGRESSION (checkpoint 11, a0771bc):
  - Full backend suite (local, long-lived DB): 3222 passed, 3 skipped, 4 failed — all four were the admin
    claims/appeals 200-row cap (fixed a0771bc; those suites 46 passed + paging test). CI 233 and 235 green.
  - Frontend unit 585 passed; tsc + eslint clean; production `next build` clean.
  - Defense walkthrough 7/7 on a production build + a FRESH defense DB migrated to 0093 and reseeded
    (scripts.defense.seed + verify exit 0).
  - Wrapping audit with pathological strings (136-char words, a 200-char URL in a message, a 77-char store
    name): 13 pages × 320/390/1440 — one offender (two-pane /messages title, fixed 2e0db8b), then 0 px
    everywhere. Links in reviews/questions are refused by the API, so those got long words instead.
NEXT EXACT TASK: tester retest of the FIXED_PENDING_RETEST rows; on owner authorisation, apply 0086-0093 to
  production (0089/0092 outside a transaction) and promote. Figma comparison (QA-050 chips) once the Figma
  connector is re-authorised.

## SESSION 13 (2026-10-05) — QA CLOSURE CAMPAIGN — READ THIS FIRST

QA WORKBOOK: BLUNTLY_QA.xlsm (Drive 1GoRj6LbkaLlQnx-sqn9D8CO8qRNUBJuY, modified 2026-10-04 21:22 UTC), read
  with openpyxl. Main: 75 items (59 Resolved, 8 Partially Fixed, 7 Fail, 1 Deferred). Moderator:
  MQA-001..045 all Open (4 High, 26 Medium, 15 Low). Engineering QA = history only (old SHA e0a4e93).
  Tester-owned Status columns are NOT edited; engineering states live here.
START STATE: remote defense-build-oct6 had advanced to dea4c4f (session 12, another workspace: claim
  evidence 0086-0089, CSV importer, every skeleton). This workspace's older skeleton WIP was saved as a
  patch (scratchpad local-skeleton-wip.patch) and dropped; nothing of it was unique.

NOTE (not a bug): production logged ~7,600 GET /search and ~7,600 /api/v1/reviews/feed in 2 h on Oct 4
  (19:00-21:00 UTC). The page itself makes one request per load (measured, 20 s idle on /search and /feed),
  so this is an external crawler or monitor; each /search render calls the feed once server-side.

### QA CLOSURE MATRIX (engineering state; tester status unchanged)
| QA | Tester | Sev | Repro? | Root cause | Fix | Test | Browser | State |
|---|---|---|---|---|---|---|---|---|
| MQA-040 | Open | High | Yes (prod: 0 appeals, no appeal POST in Vercel logs 19:00-21:00 UTC Oct 4; locally the flag saves) | Flags were only findable under Sellers › Appeals; the Reports view (where moderators looked) never mentioned them | Reports tab shows "N flags from stores are waiting · Open store flags" → /admin/sellers?tab=appeals; admin row + detail show the flag type and the matching check | test_appeal_kind (3) | seller flags → callout → appeals row "Untrue details" (1440) | FIXED_PENDING_RETEST — tester: please retry the flag on production after the next deploy; the earlier flag never reached the server |
| MQA-036 | Open | High | Yes (Reviews tab fetched limit 24, no offset, no total) | No page parameter and no count anywhere | GET /reviews/feed/count (same `_feed_stmt` as the list, so page and total agree); /search?page=N, "189 reviews · page 2 of 8", numbered PageNumbers (‹ 1 2 3 … 8 ›, every page a link); past-the-end page says so | test_feed_count (2: count == walking every page for 5 filter sets; bad params 422), page-numbers unit | 1440 + 390: page 2 loads, 0 px overflow | FIXED_PENDING_RETEST |
| MQA-037 | Open | Low | Yes | Feed had Newer/Older only | Feed uses the same PageNumbers + "189 reviews · page 2 of 16"; falls back to Newer/Older if the count fails | as above | 1440 + 390 | FIXED_PENDING_RETEST |
| MQA-005 | Open | High | Yes (escalate = close as "escalated", listed under Resolved; no confirm, no owner) | Escalation was modelled as a resolution | Escalated is its own status (Open / Escalated / Resolved / All); Escalate asks first ("Escalate to a Super Admin?"), then the screen follows the report to Status › Escalated, opened; every Super Admin gets a "report_escalated" notice linking to it; only a Super Admin can decide an escalated report (API 403 before any content action; UI shows "A Super Admin decides it"); no double escalation (409). The automatic threshold reads "Queue priority: Top/Normal" so it no longer looks like a manual escalation | test_report_escalation_owner (3), test_escalation_behaviour updated (escalated is not "resolved" now) | admin: confirm → Escalated panel; Recent Activity "Escalated a report" opens it; super admin: Dismiss available, Escalate hidden | FIXED_PENDING_RETEST |
| MQA-006 | Open | Medium | Yes | A dismissal is audited as `approve`; the menu labelled by action only | Activity rows carry `outcome` (report resolution / price decision); Recent Activity and the Activity log label by it ("Dismissed a report") | test_report_escalation_owner, activity-outcome unit (2) | yes | FIXED_PENDING_RETEST |
| MQA-008 | Open | Medium | Yes | Price decisions wrote no audit row | price_service.decide_observation writes approve/reject with outcome price_approved/price_rejected, href /admin/prices | test_report_escalation_owner::price | — | FIXED_PENDING_RETEST |
| MQA-016 | Open | Medium | Yes (rows were plain text) | No href on report rows; the menu never rendered links | Every row with a target is a link (reports and their decisions open the report via ?report=<id>; reviews, people, questions, conversations, prices their pages); opening marks the list seen and closes the menu | test_report_escalation_owner | yes | FIXED_PENDING_RETEST |
| MQA-014 | Open | High | Yes (threads are server-rendered; nothing re-read them) | No live update path | useLiveThread (components/messages/Thread.tsx): while the tab is visible, read the open thread every 4 s and router.refresh() only when its newest message changed; paused in background tabs, catches up on focus. Member /messages, seller console Messages (same component), reviewer threads, admin Inbox; the admin claim/appeal CaseChat re-reads itself every 4 s without re-scrolling | — (polling UI) | member saw a staff reply in 4.3 s and admin saw a member reply in 4.8 s, no reload | FIXED_PENDING_RETEST (polling, not websockets: Vercel serverless has no long-lived sockets) |
| QA-027 | Fail | Medium | Yes: search result rows (mobile + desktop) showed a static "↑1 · 4 comments" — no Downvote, no Share | The list row never had controls; the Feed card got them earlier, the search list did not | ReviewListRow takes `viewer` and renders the Feed's engagement bar under the row link: Upvote, Downvote (ReviewVoteBar), Comment, Share (ShareButton); search rows carry the reader's own vote (token-bound fetch when signed in, cached when not) | — | 390: buttons Helpful/Not helpful/Share present | FIXED_PENDING_RETEST |
| QA-028 | Fail | Medium | Yes: the green ↑ on search rows looked pressable and did nothing (it was text inside the row link) | Static counts styled like a control | Same fix: real buttons outside the link; signed out a vote goes to /login?next= and back | — | 390: downvote 0→1 without navigating; share sheet opens; signed-out vote → /login?next=%2Fsearch | FIXED_PENDING_RETEST (Home rail + profile picture cards keep text-only counts by design: Figma FeaturedReviewCard) |
| QA-022 | Fail | Medium | Partly (prod "man" → only Mandaue Foam now; "ma" → 6 word-start matches ordered by review count, so "Enzo Scents Le Male" ranked 2nd); suggestions 0.6 s + 250 ms debounce; the dark overlay was the native search-cancel panel, fixed earlier (SearchAutocomplete comment) | Inside the word-start tier, popularity outranked position | product_search.word_position: within a tier the earlier matching word ranks first (then reviews); stored recent searches are de-duplicated on read | test_product_search_ranking (+1), recent-searches-model (+1) | anker/fan suggestions in 0.8 s at 390 | FIXED_PENDING_RETEST (a 2-letter query still lists every product with a word starting with it — that is the documented rule) |
| QA-033 | Fail | Medium | as QA-022 | as QA-022 | as QA-022 | as QA-022 | — | FIXED_PENDING_RETEST |
| QA-066 | Fail | Medium | No — current code draws the preset as a chip ("It depends") and the reviewer's words separately under "In the reviewer's words" (8869a53, 2026-09-26, the day of the tester's Fail; on main since). Production data: no stored explanation begins with a preset | — | none needed | — | local review page at 390 (screenshot) | CURRENT VERIFIED PASS — please retest |
| QA-073 | Partially Fixed | Medium | No — asker gets "Someone answered your request" as soon as another member's review of the product is published (review_service → request_service.announce_answer) | — | none needed | existing test_round3_catalogue_api | API repro: request → other member's review → notification | CURRENT VERIFIED PASS |
| QA-074 | Fail | Medium | Superseded rule: dev/QA sync 2026-09-29 replaced "the first review closes it" with "answers accumulate; the asker picks the Best Answer, then it leaves the board". Board shows "1 answer · waiting for the asker to pick"; the request page "Open: waiting for the Best Answer" + the answers + Pick | Asker's own card offered "Answer with a review" (their own review never counts) | Asker's card links to the answers: "Pick the Best Answer →" | — | board + request page at 390 | SUPERSEDED_BY_APPROVED_RULE (+ asker link fix) — please retest against the 2026-09-29 rule |
| QA-043 | Partially Fixed | Medium | No — the store page (the only place seller reviews render) gives a signed-in member Helpful, Not helpful, Reply, Share and the ⋯ menu at 390 and 1440. The store's OWNER sees Respond / Flag instead of votes (§9: a claimed seller never votes) | — | none needed | — | 390 + 1440 button inventory | CURRENT VERIFIED PASS — retest as a member, not the store owner |
| QA-059 | Partially Fixed | Medium | Yes: the ⋯ menu sits in the sticky header and stayed open while the page scrolled, so it ended up over the title and "Ask a question" | Menus closed on outside tap / Escape but not on scroll | ReviewOverflowMenu and the shared OverflowMenu close when the page scrolls | — | 390: open → scroll → closed; outside tap and Escape still close it; menu inside the viewport (x 112–320) | FIXED_PENDING_RETEST |
| QA-001 | Partially Fixed | Medium | No (images): production has 180 published reviews, 143 with reviewer photos and all 143 objects present in review-photos; every one renders. Placeholder appears only on reviews with no reviewer photo | Owner decision 2026-10-03: a review card never borrows the product listing image | none needed | — | review cards with + without photos at 390/1440 | CURRENT VERIFIED (images load); fallback = BLOCKED_PRODUCT_DECISION (owner rule: no product-image fallback) |
| QA-016 | Partially Fixed | Medium | No — every /dashboard subpage has a back control that lands on /dashboard: reviews (Back + Dashboard crumb), insights, history, statement, at 1440 and 390 | — | none needed | — | .qa/qa016.mjs: 8 page×width runs, each click → /dashboard | CURRENT VERIFIED PASS |
| QA-024 | Partially Fixed | Medium | Yes (reviews/comments/feed/search rows used the app's "Share to…" sheet, but the public profile's Share and each Q&A answer's Share still called navigator.share on phones and silently copied on desktops — so "Share" looked different by device and surface) | Two share paths left on the old code | ProfileShareButton and the answer Share open the same ShareSheet (system sheet stays one tap away as "More options…" where the browser has one); answer links keep their #answer- anchor | tsc, eslint | .qa/qa024.mjs: profile + answer → "Share to…" dialog with the right link, 1440 + 390, 0 px overflow | FIXED_PENDING_RETEST |
| QA-025 | Partially Fixed | Medium | No — phone "All filters" draws Category as checkboxes (14) and applies them together with the other groups: 3 categories + Trust 80–100 + Past year → `?category=audio,automotive,beauty&period=year&trust=high`, five chips, still ticked on reopening; the desktop rail toggles categories in and out of the set (aria-pressed); the API unions them (audio 0 + beauty 13 → 13) | — | none needed (55551fa, on main) | e2e figma-parity QA-025 journey (existing) | .qa/qa025.mjs + qa025b.mjs at 390 / 1440 | CURRENT VERIFIED PASS |
| QA-062 | Partially Fixed | Medium | Yes — the product review's photo step positions + crops (ImageCropper) before upload, but the store review ("Rate a seller") photo tiles and the one-time "Replace photo" uploaded the file as picked | Two upload paths never got the cropper | Both open the same ImageCropper first (drag / pinch / slider / arrow keys) and upload only the square crop; "Add more" / "Replace" wait while it is open | tsc, eslint | .qa/qa062.mjs at 390: rate a store → Tap to upload → cropper → "Use this crop" sends og-default-crop.jpg 630×630 from a 1200×630 pick → tile shows | FIXED_PENDING_RETEST (locally /reviews/photo 500s: this dev stack has no Supabase credentials; the request was intercepted to read the crop) |
| QA-050 | Fail | Medium | Partly — current Questions tab (390): product summary (best answers / unanswered / active now), All filters (Time) + Sort (Latest/Oldest), cards with product image, quoted question, answer counts. Figma not re-readable this session (Figma MCP needs auth) | Earlier fix 2026-09-24 (pills, by-date sort, product image) | — | e2e figma-parity "QA-050" (existing) | 390 screenshot | CURRENT VERIFIED for filters/sort/info; "Topics:" chips and per-card "N active" = BLOCKED_PRODUCT_DECISION (questions carry no topics and nothing counts participants; drawing them would invent data) |
| MQA-041 | Open | Medium | Yes | One option ("fake") only | 0090_appeal_kind: never_ordered / untrue / breaks_rules; seller console form + public store form ask "What's wrong with it?" with a per-kind prompt and next step | test_appeal_kind, appeal-kinds.test.mjs (3), e2e br-journeys updated | yes | FIXED_PENDING_RETEST |

## SESSION 12 (2026-10-04, from ~14:40 UTC) — READ THIS FIRST

CURRENT MAIN SHA: 370f702 (release 4; unchanged — nothing merged or deployed this session).
CURRENT DEFENSE SHA: see `git log origin/defense-build-oct6` (b260ae9 at the skeleton checkpoint).
START STATE: fresh cloud workspace, tree clean. The interrupted skeleton edits of the previous
  session (Skeleton.tsx +237/-40, AdminSkeletons.tsx +515) did NOT survive and were on no remote
  branch; rebuilt from scratch this session. The "SKELETON SYSTEM STATUS" section the old header
  pointed to was never written. Unmerged remote branches seen: claude/elegant-gauss-2ikk4a (3 commits,
  superseded by defense's later console field-state work) and claude/happy-thompson-xn5imb (Shopee
  catalog import data/SQL, another session's work) — neither merged here.
SUPABASE CONNECTOR: the `Supabase` connector (mcp__Supabase__*) works (projects byobedbhodhvocgrkrse
  = production, miysywhcdqkoniaibglx = TEST). A second server named `supabase` asks for OAuth; not needed.

### 1. CLAIM EVIDENCE UPLOAD BUG — FIXED (f7a633e)
REPRODUCED from production's storage log: 6 PDF uploads 13:54–14:28 UTC to
  /object/message-attachments/<conversation>/<uuid>.pdf, all HTTP 400 from Supabase Storage. Both
  conversations were claim threads (case_key claim:…), 0 attachments stored.
ROOT CAUSE: the private bucket `message-attachments` (used by every Inbox / case-chat attachment since
  0076) was never created — not on production, not on TEST (storage.buckets had avatars,
  product-images, review-photos, review-receipts only). 0076 had left it to a manual step. The API
  turned the storage error into 503 attachments_unavailable. Existing tests monkeypatched
  storage.upload_attachment, so nothing ever hit a real bucket.
SECOND DEFECT (linkage): a claim (or appeal) conversation STARTED from Messages opened a new thread with
  case_key NULL; the Admin claim review reads only the case thread, so evidence sent that way never
  reached the reviewer. Now it writes into the case's one thread (conversation_service.start →
  case_conversation).
ORPHANS: a file uploaded for a message that then fails to save (commit or anything before it) is
  removed again (`_saving` context, storage.delete_attachment_objects). A failed upload writes no row.
MIGRATION 0086_storage_buckets: inserts every bucket in storage.BUCKETS when missing (ON CONFLICT DO
  NOTHING; message-attachments private, 5 MB, png/jpeg/webp/pdf); no-op without a storage schema;
  downgrade no-op (Supabase refuses SQL bucket deletes).
TESTS: backend/tests/test_claim_evidence.py (7: bucket spec = storage.BUCKETS; 0086 creates the bucket
  and leaves existing ones; claimant A → evidence on the case, staff opens it, seller B 403/404
  everywhere, second start reuses the thread; HTML 415 / oversize 413 store nothing; missing bucket →
  503 and no rows; failed save removes the object; real-bucket round trip under requires_storage).
  The linkage and orphan tests fail on the old code.
PRODUCTION STILL NEEDS 0086 (until then claim evidence uploads keep failing). Apply by the usual
  procedure before the next merge: `alembic upgrade 0085_email_outbox:head --sql`, review, one
  BEGIN…COMMIT through the Supabase connector, then check storage.buckets + alembic_version.

### 2. DATABASE PARITY (owner: "check the Postgres the website uses is really implemented on Supabase")
VERIFIED with the connector, production vs a fresh `alembic upgrade head` of this repo:
  * the live site reads production (a product the live API returned exists only there);
  * alembic_version 0085_email_outbox = repo head before this session;
  * all 61 tables IDENTICAL (columns, types, nullability, defaults — per-table md5);
  * constraints (61 tables), indexes (61), 42 enums with labels, triggers: IDENTICAL;
  * the two trigger functions: same logic, whitespace only (applied from dedented offline SQL).
DRIFT FOUND: (a) message-attachments bucket missing (→ 0086); (b) RLS OFF on 11 tables (cron_credentials,
  cron_runs, notifications, rate_limit_counters, request_geo_buckets, review_first_vote_geo_buckets,
  review_reading_sessions, review_view_buckets, seller_claims, seller_reviews, sellers) — none granted
  to anon/authenticated, so nothing leaked, but it broke the "RLS on every table" rule; email_otps had
  RLS switched on by hand on production only (→ 0087_rls_every_table, 12 tables, idempotent; the app
  role owns every table so it is unaffected); (c) advisor WARN function_search_path_mutable on
  users_staff_ref_is_immutable / users_keep_one_super_admin (→ 0088_function_search_path).
  Left as is: pg_trgm in public (moving it would rebuild the trigram indexes); INFO "RLS enabled, no
  policy" on every table = the intended default-deny.
GUARDS ADDED: scripts/check_invariants.py reports any table with RLS off, and any bucket in
  storage.BUCKETS that is missing or has the wrong privacy (n/a on plain Postgres).
TEST PROJECT: migrated 0083 → 0088 through the connector (offline SQL, one transaction each): alembic
  0088, buckets 5 (message-attachments private), RLS off 0, API-readable 0, counts unchanged
  (users 4721, conversations 27); its security advisor no longer lists RLS-disabled tables.
PRODUCTION: untouched (read-only queries only). Pending for the next release: 0086, 0087, 0088.
NOTE: production products went 401 → 415 today and a product was created 15:00 UTC — something else
  (likely the Shopee import session) is writing to production.

### 3. SKELETONS — DONE (Admin b260ae9; Seller + public 66f36b1)
ONE SYSTEM: components/ui/Skeleton.tsx — Bar 8/10/14/18 (rounded-full), Block (12 px), Pill, Circle,
  fill token --skeleton-fill #e6e6e6 (app/tokens/colors.css; --border-subtle is translucent ink, so it
  could not be used as is), SkeletonRegion (one polite announcement; placeholders aria-hidden, never
  focusable), SegmentedSkeleton (wraps like the real control on a phone), IconButtonsSkeleton,
  MetricRowSkeleton, TableSkeleton (CSS-grid column tracks as wide as the real columns, 40 px header,
  ~52 px rows, the real min-width clipped not squeezed), PaginationSkeleton. Pulse off under reduced
  motion. The old `Skeleton` + ListSkeleton / CardGridSkeleton / ReviewCardSkeleton / TextLines /
  ListRowSkeleton are DELETED (no callers).
ADMIN (components/admin/AdminSkeletons.tsx): the fake 220 px rail in app/admin/loading.tsx is gone
  (loading.tsx renders inside AdminLayout); 21 route loading.tsx, one per app/admin page. The shell draws
  the title, so skeletons never do.
SELLER (components/seller/console/SellerSkeletons.tsx): all on the primitives; SELLER_LISTS gives
  Reviews / Questions / Appeals / Products their real columns (Products used the reviews shape);
  SellerProductSkeleton for /seller/[storeId]/products/[productId] (was the Overview's shape).
PUBLIC / MEMBER: SiteHeaderSkeleton (components/site/SiteHeader.tsx: real 72 px bar + wordmark,
  placeholder search/links/avatar — the real header needs the user and would flash "Log in") in every
  public loading.tsx, hidden below md where the page hides its header. /search rebuilt as the list it is
  (was a card grid) inside the real BrowseLayout; /questions and /requests rebuilt likewise; /feed uses
  the real BrowseNav. Inline "Loading…" text replaced in ProductEditModal and StoreNotifications.
KEPT: TrafficGlobe's canvas-loading pulse (a component overlay, reduced-motion aware).
BROWSER-CHECKED (loaded vs loading, real shell, API slowed by a delay proxy) — every route below was
  compared against its loaded screen, and the mismatches found were rebuilt (Seller Settings, Affiliate
  ledger, Price rows, search, questions, requests, profile, u/[id], questions/[id]):
  Admin overview, products, queue, payouts, activity, analytics, reports, reports/commissions, inbox,
  sellers, settings, people/[id], users, special-routing, affiliate, honesty-fund, prices, qa-sandbox,
  reports/honesty-fund at 1440 (reports/seller-ratings renders too fast to show a fallback);
  products, payouts at 390. Seller overview, reviews, questions, appeals, products, insights, profile,
  public, settings, messages at 1440 (rules renders too fast to show a fallback). Public feed,
  questions, requests, search, profile, u/[id], questions/[id], reviews/[id], categories at 1440; feed,
  dashboard, messages, search at 390.
  Seller products/[productId] checked too (trend chart height and the "What reviewers keep mentioning"
  card added).
  Public dashboard/statement and sellers/[id]/reports checked last: components/reports/ReportLoading
  was generic (title, 4 blocks, a slab) and is now ReportFrame's order (back link, title + downloads,
  period form, figure cards, sections), in the pages' own <main> padding.
EVERY loading.tsx route has now been compared against its loaded screen in a browser.

### 4. PRODUCT CSV IMPORT — EXTENDED, NOT REBUILT (faec19e)
CORRECTION: the previous session's "STATUS: MISSING" was wrong. POST /admin/products/import, the
  ProductImportModal and 6 tests existed (ba573d9, committed under the misleading title "feat(seller):
  loading states for the Seller console screens"). This session closed its gaps:
SCHEMA: docs/PRODUCT_CSV_IMPORT.md (every column: required / type / example / meaning / validation /
  normalization; outcomes; apply; permissions). Columns brand*, line*, category*, variant, type, aliases
  ("a | b"), source_url (alias header listing_url), specs ("Label: Value | …"). Headers any order / case,
  space or hyphen = "_"; repeated column refuses the file; unknown columns reported ("Not read").
  NO image column, on purpose: every catalogue image lives in product-images (production: 55 of 415
  products have one, all in that bucket, 0 hotlinks) and the platform never fetches a URL (owner decision
  "no scraping, ever", docs/MILESTONES.md 2026-07-15). Images are added with Edit after the import.
  OWNER DECISION IF WANTED: allowing staff-supplied image URLs to be copied server-side would relax that
  rule; the pieces exist (seed_product_images' SSRF-guarded fetcher, validate/upload_product_image).
  No platform column (read from the listing host), no external-id column (no such field in the model).
PREVIEW: new / exists (matched by listing — product link OR any product_platforms listing, URL
  normalised — or by exact name, via product_matching) / duplicate (earlier row) / conflict (listing on
  one product, name on another, or listing on two products; never written) / error (row number + reason).
DECISIONS: an exists row is skipped (default) or ATTACHED (form field attach=<lines>): its listing becomes
  another listing of that product, its name and aliases become aliases; name, category, specs, photo never
  change. Offered only when there is something to add.
APPLY: server re-reads and re-checks everything; one transaction; savepoints collect every failing row,
  then everything rolls back and those rows read "failed". Counts total / imported / attached / skipped /
  invalid / failed. Audit: one `product_import` Activity log entry (new enum value, migration 0089) with
  file name, counts, created ids and a notes line — never the file. GET /admin/products/import/template
  is generated from COLUMNS + EXAMPLE.
UI: ProductImportModal — summary chips, "Not read" columns, Outcome + Decision columns, per-row Attach
  checkbox + "Attach every match", "Import N new · attach M", failure message, template from the API.
TESTS: backend/tests/test_product_import_csv.py (12), test_product_admin_add_import.py (6, unchanged),
  tests/frontend/product-import-model.test.mjs (5). Browser E2E run: template download → preview (new /
  match / conflict / invalid / ignored column) → attach → import → product in the catalogue, alias added.
RBAC: require_staff (Administrator, Super Admin); member and seller 403, signed out 401 (tested).

### 5. MIGRATIONS ON THIS BRANCH NOT ON PRODUCTION (apply before the next merge to main)
0086_storage_buckets (creates message-attachments — the claim-evidence fix depends on it),
0087_rls_every_table, 0088_function_search_path, 0089_product_import_action (ALTER TYPE ADD VALUE: run
it OUTSIDE the BEGIN…COMMIT, as 0080 was). Procedure: `alembic upgrade 0085_email_outbox:head --sql`,
review (no DROP / DELETE / data UPDATE), apply through the Supabase connector, then check alembic_version,
storage.buckets, RLS-off count 0, the two functions' proconfig, the enum value.
TEST project (miysywhcdqkoniaibglx) is already at 0089.

### 6. PRODUCTION INVARIANTS (scripts/check_invariants queries, read-only through the connector)
26 of 29 hold. Failing: tables without RLS 11 (→ 0087), message-attachments missing (→ 0086), and
"star ratings out of range" 2 — a STALE CHECK, not bad data: two real 0.5-star hard-pass reviews; the
check still said 1–5 although 0048 made the rule 0–5 in half steps (ck_review_star_rating). Check fixed.

### 7. TESTS THIS SESSION
Backend full suite (local PG 16): first checkpoint 3122 passed, 3 skipped (1 error was my `-p no:logging`
  flag breaking a caplog test; it passes normally). FINAL (after the importer and the skeleton pass):
  3140 passed, 3 skipped, 0 failed (7m24s).
Skipped tests: requires_storage (no Supabase Storage credentials in this container) — including the new
  real-bucket round trip; they run in the weekly TEST-project job.
CI on defense-build-oct6: run 205 (5943504) success; run 206 (faec19e) success — Backend (ephemeral
  Postgres 17) full suite, Backend (no database), Production guard, Frontend (tsc, eslint, unit tests,
  production build); Backend (isolated database) skipped (schedule/dispatch only). Run 207 (66f36b1)
  success. Run 208 (6d1adb9) cancelled by the concurrency group (superseded by 209). Run 209 (aa6250c):
  see below.
Frontend: tsc clean, eslint clean, 551/551 unit tests.

### NEXT EXACT TASK
1. Release: apply 0086–0089 to production (procedure above), merge defense-build-oct6 → main, deploy, then
   upload a PDF on a claim thread in production and confirm a storage 200 + an attachment row.
2. Owner decision: image URLs in the product CSV (see §4).

## RELEASE 4 — email change, ephemeral-Postgres CI, email outbox (2026-10-04) — READ THIS FIRST

SITE_URL: production had none, and production CORS_ORIGINS answers only https://bluntly-ph.vercel.app
  (www.bluntly.ph gets a 400 on preflight; the site is same-origin through vercel.json rewrites, so that
  never mattered before). public_site_url would therefore have put vercel.app links in emails. Added
  SITE_URL=https://www.bluntly.ph (encrypted, production only, env id 9u0v5N1iFHTIxmsY) through the
  Vercel connector; it takes effect with this release's deploy.
MIGRATION: production (byobedbhodhvocgrkrse) 0083 → 0084_email_change → 0085_email_outbox BEFORE the
  merge. Offline SQL (`alembic upgrade 0083_notification_prefs:head --sql`): two CREATE TABLE (RLS on,
  anon/authenticated revoked), three indexes, one nullable ADD COLUMN users.sessions_valid_after, two
  alembic_version bumps; no DROP/TRUNCATE/DELETE/data UPDATE. Applied as one BEGIN…COMMIT through the
  Supabase connector. Pre: users 23, products 401, reviews 159, questions 17, answers 16, sellers 5,
  seller_reviews 4, notifications 123, moderation_logs 280, conversations 1. Post: alembic 0085; both
  tables + email_change_requests_pkey, ix_email_change_requests_user, email_outbox_pkey,
  ix_email_outbox_due, uq_email_outbox_dedupe (partial); ck_email_outbox_status and both FKs; RLS on
  (and still on users); 0 API-role grants; sessions_valid_after timestamptz/nullable/no default, 0 set;
  counts unchanged except reviews 160 (a live review posted meanwhile). Old code (458e951) healthy on it
  (/health, /, products API 200).
PR: https://github.com/bluntly-ph/bluntly.ph/pull/12 — CI on head c2a4c73: Production guard, Backend (no
  database), Backend (ephemeral Postgres 17), Frontend = success; Backend (isolated database) skipped
  (schedule/dispatch only); Vercel preview READY. Walkthrough rehearsal does not trigger on this PR's paths,
  so it was dispatched on defense-build-oct6 (populate_test=false): run 37207287447 success.
  MAIN BEFORE 458e951 · DEFENSE HEAD c2a4c73 · MAIN AFTER 370f702 (merge commit; tree f4fea5c identical to
  the tested head).
VERCEL: dpl_613uJ9nuknq13ufn2LpSTSyp1ZuQ READY, aliased www.bluntly.ph / bluntly.ph. Rollback candidate:
  dpl_GQWc1RfTPYmrhpE2tNsXgrnej9wN (458e951; runs fine on 0085, which is additive).
PRODUCTION SMOKE (read-only, signed out, no email sent): 200 on /health, /, /welcome, /login, /signup,
  /search?q=, /questions, /categories, /compare?ids=, /terms, /privacy, /sitemap.xml, /feed, a review, a
  question, a store page, /unsubscribe (and ?token=bad shows "This unsubscribe link isn't valid."). 307 →
  /login?next=… on /admin, /admin/activity, /seller/dashboard, /messages, /dashboard. APIs: products,
  questions, reviews, store reviews 200; 401 signed out on notification-prefs (GET/PUT), email-change
  (GET/POST), auth/me; unsubscribe GET/POST with a bad token → 404 "This unsubscribe link isn't valid.".
  No error digest in the server HTML; Vercel runtime errors in the last hour: 0. (/products/<id> is 404 —
  there is no such page; products are viewed through /compare?ids=.)
LIVE FROM NOW: the scheduler (main) runs send_emails hourly at :20 and weekly_summaries Mondays 00:00 UTC;
  store notices are emailed to owners whose "Also by email" is on.
DEFENSE SYNC: defense-build-oct6 fast-forwarded to 370f702 (not deleted).

## SESSION 11 (2026-10-04, after RELEASE 3, ~12:50–13:30 UTC) — READ THIS FIRST

PRODUCTION IS BEHIND THIS BRANCH BY TWO MIGRATIONS: 0084_email_change and 0085_email_outbox. Both are
  additive (two new tables with RLS on and anon/authenticated revoked, one nullable column
  users.sessions_valid_after). Apply them BEFORE the next merge to main, by the usual procedure:
  `alembic upgrade 0083_notification_prefs:head --sql`, review offline, one BEGIN…COMMIT through the
  Supabase connector, then check alembic_version, the tables/column, RLS, grants and the row counts.
  The released code (458e951) does not read either table, so it stays healthy on them.

1. VERIFIED EMAIL CHANGE (969a3dc, 0084). Seller Settings → Profile and password → Change email.
   A code goes to the CURRENT address and one to the NEW address; nothing changes until both are
   right (separate table email_change_requests, so a sign-in OTP can never spend a change code).
   "Address taken" is only revealed at confirm, after both codes (no enumeration). On success:
   users.sessions_valid_after = now, so every token issued before it gets 401 session_revoked; this
   browser gets a fresh token through the server action; the old address gets a masked notice.
   Tests: backend/tests/test_email_change.py (4), e2e/email-change.spec.ts, tests/frontend
   email-change-model.
2. CI ON AN EPHEMERAL POSTGRES (352b4fa, 05fe9a3). .github/workflows/ci.yml job `backend-pg`: a
   postgres:17 service, role stand-ins, `alembic upgrade head`, the full pytest suite, on every PR and
   on pushes to main and defense-build-oct6. Storage-bound tests skip via `requires_storage`. The
   remote TEST-project job runs only on schedule/workflow_dispatch. First green run 37203231104.
3–5. EMAIL INFRASTRUCTURE, NOTICES BY EMAIL, WEEKLY SUMMARY (0085, this checkpoint).
   * Outbox: email_outbox rows are queued in the SAME transaction as the event (a rolled-back event
     emails nobody) and sent by the hourly `send_emails` job (internal_cron, :20; workflow cron
     "20 * * * *"). Each row's id is Resend's Idempotency-Key. Failure: retry after 5/10/20/40 min,
     `failed` after 5 attempts. Settled rows are purged after 30 days. A dedupe_key (partial unique
     index) makes a re-run job queue nothing twice. NOTE: enqueue detects the insert with RETURNING —
     through the ORM session rowcount is always -1.
   * Notices: the store notices the Settings switches cover (new store review, new store question,
     appeal decided, product link decided) are also emailed when "Also by email" is on (default on).
     Other notices stay in-app only.
   * Weekly summary: `weekly_summaries`, a new WEEKLY cadence (period = Manila ISO week "2026-W41",
     due Monday 08:00 Manila; workflow cron "0 0 * * 1"). One email per claimed store whose owner is
     not suspended and has the switch on; a store with nothing new and nothing waiting gets none.
     Figures: overall rating, new reviews, store responses, new questions (7 days), reviews without a
     response, store questions the store hasn't answered. Dedupe key weekly:{store}:{ISO week}.
   * Unsubscribe: every such email has a signed link (HMAC-SHA256 with JWT_SECRET, per account and
     channel) to /unsubscribe (page; reading changes nothing, the button does) and, when SITE_URL is
     https, List-Unsubscribe + List-Unsubscribe-Post (RFC 8058 one-click) pointing at
     POST /api/v1/email/unsubscribe. A bad/tampered/orphaned token is one 404. Turning a channel back
     on is the Settings switch.
   * Settings: "Also by email" and "Weekly summary" switches are live (Weekly summary was drawn
     disabled before). Section subtitle "In the app, and by email if you choose".
   * Ops: production must have EMAIL_PROVIDER=resend (it does — the readiness guard refuses console)
     and SITE_URL=https://www.bluntly.ph (or a first CORS origin that is the https site) for the
     buttons and the one-click header. No email is sent until the send_emails job runs.
   Tests: backend/tests/test_email_outbox.py (14: send once + idempotency key, dedupe, backoff →
   failed, purge, Resend payload, notices only while on, only store kinds, rollback, escaping,
   token signing, headers https-only, unsubscribe GET/POST/404, weekly figures, weekly once + quiet
   + pref off, suspended owner), test_internal_cron (weekly + :20 cadence), e2e/unsubscribe.spec.ts
   (needs E2E_JWT_SECRET), e2e owner-patch 14b (switches), tests/frontend unsubscribe-model and
   seller-notification-prefs.

## RELEASE 3 — PR #11 (2026-10-04, ~12:25–12:45 UTC) — READ THIS FIRST

MIGRATION: production (byobedbhodhvocgrkrse) 0082 → 0083_notification_prefs BEFORE the merge. The
  offline SQL (`alembic upgrade 0082_seller_response_edited_at:head --sql`) is one ADD COLUMN plus the
  version bump, applied as one BEGIN…COMMIT through the Supabase connector. Post-check: alembic 0083,
  users.notification_prefs jsonb/nullable/no default, 0 non-null rows, RLS on public.users, 0
  anon/authenticated column grants, every pre-flight count unchanged (users 23, products 391, reviews 147,
  questions 17, answers 16, sellers 5, seller_reviews 4, notifications 123, moderation_logs 280,
  conversations 1). The old code (2f51c8e) stayed healthy on it.
PR: https://github.com/bluntly-ph/bluntly.ph/pull/11 — CI: Frontend, Backend (no database), Production
  guard, Walkthrough rehearsal (own Postgres 17) = success; Vercel preview ready. Merged with a merge
  commit (pinned to head c5bb727). MAIN BEFORE 2f51c8e → MAIN AFTER 458e951.
VERCEL: dpl_GQWc1RfTPYmrhpE2tNsXgrnej9wN READY, aliased to bluntly.ph / www.bluntly.ph. Rollback
  candidate: dpl_H47q8iBB8HaHMZXhy1SMva2fcCM2 (2f51c8e; it runs fine on 0083, which is additive).
PRODUCTION SMOKE (read-only, no sign-in): 200 on /health, /, /welcome, /login, /signup, /search
  (+q), /questions, /categories, /compare, /terms, /sitemap.xml, /feed, a store page. 307 →
  /login?next=… on /admin (+special-routing, analytics, activity), /seller/dashboard, /messages,
  /dashboard. Public APIs 200 (products, store, store reviews ?offset=, questions). 401 for anonymous
  callers on /users/me/notification-prefs (GET and PUT), /admin/super/special-routing (+history),
  store dashboard/appeals, needs-attention, activity and conversations. No error digest or error boundary
  in the server HTML of 6 key pages. Vercel runtime errors since the deploy: 0.
DEFENSE SYNC: defense-build-oct6 fast-forwarded to 458e951 (not deleted).
NOT DONE: signed-in production checks (no production session used).

## SESSION 10 (2026-10-04, ~07:34–11:25 UTC; a usage-limit pause ~08:45–11:10) — READ THIS FIRST

CURRENT MAIN SHA: 2f51c8e (the PR #10 release). Unchanged this session: nothing merged, nothing deployed.
CURRENT DEFENSE SHA: the tip of origin/defense-build-oct6 (this handoff commit; code tip 6d7131d).
MAIN vs DEFENSE AT SESSION START: defense was ahead of main only by the handoff commit 0ba24f2, so there
  was no merge (as instructed). main ahead of defense: 0. Defense is now ahead by this session's work (below).
POST-MERGE CI RESULT (main run 37183348786 on 2f51c8e): Frontend, Backend (no database), Production
  guard = SUCCESS. "Backend (isolated database)" (job 111380163314) = FAILURE at 11:08 UTC after
  4h31m. Classified as two separate issues:
  1. PRE-EXISTING TEST ISSUE — test_trust_computation_qa::test_many_people_voting_at_once_are_each_counted.
     Reproduced locally with CI's pool (DB_POOL_SIZE=2, MAX_OVERFLOW=3, TIMEOUT=30): only 5 of 12
     simultaneous votes got a connection; the rest hit "QueuePool limit … reached" after 30 s. It passes
     with the app's default pool. PR #10 changed no voting or DB code (272b7dc was already on main).
     FIXED on defense (6d7131d): the writer count is sized to the pool (≥2, which is enough for the race).
     Passes 3/3 under the CI pool. Nothing skipped.
  2. INFRASTRUCTURE ISSUE — the step "Migrate, test, and verify milestones" hit its 270-minute timeout
     (the run was still in test_trust_integrity_holds). The same suite runs in 7m17s locally (3053
     passed). The cost is the GitHub runner → ap-southeast-1 Supabase round trip on every query. PR #9's
     merge run also died this way after about 4h14m. No app change. RECOMMENDATION (owner decision; it
     touches CI): run the isolated-DB job against a Postgres service container in the runner, or shard
     it, rather than raising the timeout again.
  REAL REGRESSION: none found. TEST-DATA ISSUE: none.
PRODUCTION: untouched this session (no migration, no deploy, no data written).
MIGRATIONS ON THIS BRANCH NOT ON PRODUCTION: 0083_notification_prefs only (users.notification_prefs
  JSONB, nullable; NULL means all on; the downgrade drops it; repo checker: no contracting operations). Apply
  it to production BEFORE any deploy of this branch, using the same procedure as PR #9/#10.

DONE (each one tested and pushed to defense-build-oct6 only):
  9555829 Seller Overview (8190:20643): "Waiting on you" claimed oldest-first but read the newest-30 reviews.
    The API now adds waiting_reviews (oldest unanswered, ≤20). "See all N" takes N from the API totals.
  af443c4 Seller Reviews: columns per tab (Needs: Order; Responded: Your response + Responded; All: chip).
    An order problem shows as danger text. A review with no title shows its comment instead.
  4a59aca Seller Settings (8218:24151): REAL notification switches (0083), enforced in notify() for new
    store reviews (+ "only low" ≤3★), store questions, appeal decisions and product-link decisions.
    Account, staff and payout notices can't be turned off. GET/PUT /users/me/notification-prefs.
    In-app only: Weekly summary is drawn off and disabled, with the reason. "Give up this store" card added,
    two columns. Switch extracted to components/console/Switch.tsx.
  7e18426 CASE CHAT RBAC AUDIT — regression test: Seller B gets 403/404 on Seller A's appeal thread,
    reviewer thread, conversation and file link. No code change was needed.
  0075c6e SELLER REPORTS AUDIT — the store's Appeals list leaked substantiation_request (the admin's
    message in the reviewer thread); it is now null. No emails, private IDs, staff notes, fingerprints or
    investigation flags appear in any seller payload (schemas grepped; internal_note was already tested).
  b983739 Admin Analytics: "5h 20m" / "Was 7h 05m" (was "0h"), plus "Oldest waiting N days".
  aff94c7 Admin Activity log: answer, store-review and Inbox-conversation targets named and linked.
    Inbox events read as verbs. The day header no longer shows the page size as the day's total.
  040f161 Admin Settings: Request geography retention row (proof-of-purchase and deleted-account rows are
    not drawn because no job enforces them).
  5a786d5 / fac04f8 / b3e0f10 Pagination consolidated (Products, Sellers, Affiliate, Payouts). The Products
    nav badge now counts the product queue (products_to_review), as in Figma 7966:11087.
  525687e Review queue window: a photo that fails to load falls back to the placeholder instead of a
    broken image.
  f62b445 Admin Sellers: "DTI 2718281", not "DTI DTI-2718281".
  85f2216 / d909a78 Affiliate and Products empty states tell "nothing yet" apart from "no match".
  35575f7 SPECIAL ROUTING redrawn to Figma 8178:20045 + Overlay/Routing/Track 8178:20344: cards, table,
    pagination, the Route earnings overlay and a log note. API (additive): author_name, excerpt,
    product_image_url, approval_note, an optional note, history actor_name. Owner decision A beats the
    frame: Honesty Fund (40/60) or Platform (70/30), not "Commission". NOT drawn: Escalated
    reports/reviews tabs, Set a rule (no escalation flow and no routing rules exist).
  6d7131d CI test fix (above).
COMPARED, NO GAP: Seller Products, Insights, Store profile, Public page, Inbox, notifications overlay;
  Admin People (+ Under investigation), Person → Interactions, Jobs dialog, Admin Inbox, Sellers
  claims/appeals, Payouts (Process requests deliberately absent: no automated money movement), Reports.
  schedule_payouts was checked: it only prepares batches and never submits.

TESTS (session 10, all actually run):
  Backend FULL suite at 35575f7+: 3053 passed, 0 failed (test_receipt_privacy.py deselected: needs
    Supabase TEST storage). ruff clean (CI scope).
  Frontend: tsc clean, eslint (whole repo) clean, unit 542/542.
  e2e (local stack, fresh fixtures): owner-patch-journeys 19/19 + reporting 13/13 (32/32) after the
    Reviews/Overview changes; owner-patch 14b (Settings) passed; admin-console 14/14 (moderator token);
    admin-journeys 11–13 (Special routing) 3/3.
  DEFENSE WALKTHROUGH: 7/7 on next build + next start, fresh --reset seed (verify 109/109 READY). The
    spec was updated for "DTI 5902144".

PRODUCT DECISIONS REQUIRED:
  - Seller EMAIL change: Figma draws it read-only; the Backend Proposal asks for editing, which touches
    sign-in. NOT implemented.
  - CI isolated-DB job runtime (see INFRASTRUCTURE ISSUE above).
  - Notification email and weekly summary (nothing sends them today).
NOT BUILT (documented): Admin Team "Two-step login" column (no 2FA); the Overview's reply-time bar (it has
  no defined meaning); Special routing escalation tabs and rules.

NEXT (in order):
  1. Owner: decide on the CI isolated-DB approach. To release this branch: PR → apply 0083 to production
     first → merge.
  2. Seller Rules frames (8218:23740, 8225:*) and Admin Queue/Reports/Support/Answers tabs: compare again
     with text dumps (last compared in sessions 7–8).
  3. The review queue's offset pager is the last hand-rolled pager (kept deliberately: real links).

## RELEASE — PR #10 (2026-10-04, ~06:00–06:55 UTC) — READ THIS FIRST

RELEASE DATE/TIME: 2026-10-04 06:37 UTC (merge) · Vercel READY 06:38:51 UTC.
DEFENSE PRE-MERGE SHA: f7e6853   MAIN BEFORE: 7a2c791   MAIN AFTER: 2f51c8e (merge commit; tree
  byte-identical to f7e6853). PR: https://github.com/bluntly-ph/bluntly.ph/pull/10 (merge commit, no
  squash, no force). defense-build-oct6 fast-forwarded to 2f51c8e afterwards (not deleted).
MIGRATION BEFORE: 0074_alias_remove_action   MIGRATION AFTER: 0082_seller_response_edited_at
  (production, Supabase project byobedbhodhvocgrkrse), applied BEFORE the merge with the same procedure
  as PR #9: `alembic upgrade 0074_alias_remove_action:head --sql` (offline, reviewed), then through the
  Supabase connector — each enum ADD VALUE on its own, each transactional block as one BEGIN…COMMIT,
  alembic_version checked after every step. Audit: all forward changes additive (no DROP/DELETE/TRUNCATE;
  repo checker: "additive and safe"); 0076 copied the 1 existing case chat (1 message; source row kept).
  Post-check: 3 new tables, RLS on, 0 anon/authenticated grants, 12 indexes, 5 new types, enum values
  present, 2 nullable timestamptz columns, and EVERY pre-flight row count unchanged (users 23, products
  366, reviews 123, questions 17, answers 15, sellers 5, seller_reviews 4, seller_claims 1,
  moderation_logs 242, platform_settings 2, notifications 98). Old code (7a2c791) stayed healthy on the
  migrated schema until the deploy. No case-chat message was written in the old/new window (1 = 1).
  TEST project (miysywhcdqkoniaibglx) is also at 0082 (migrated by main's CI after the merge).
WALKTHROUGH RESULT: 7/7 locally (next build + next start of f7e6853, fresh --reset seed, verify 109/109
  READY) and 7/7 in PR CI ("Walkthrough rehearsal (own Postgres 17)").
BACKEND TEST RESULT: full suite 3054 passed / 0 failed at 94c259e (code-identical to the release; only
  the handoff changed after); release-sensitive subset re-run at f7e6853: 781 passed; ruff (CI scope
  app/ scripts/ tests/) clean. 2 receipt-privacy tests still need Supabase TEST storage locally.
FRONTEND TEST RESULT: tsc clean, eslint (whole repo) clean, unit 527/527.
BROWSER TEST RESULT: walkthrough above; CI journey set 107/107 on a fresh DB earlier in session 9.
CI STATUS: PR #10 — Frontend, Backend (no database), Production guard, Walkthrough rehearsal, Vercel
  preview: success; Backend (isolated database) + TEST seeding: skipped on PRs (by design). Post-merge
  main run 37183348786 — Frontend, Backend (no database), Production guard: success; Backend (isolated
  database) still RUNNING at handoff time (it takes ~4 h; on PR #9's merge it ended in FAILURE after
  4h14m — a pre-existing condition of that job, not introduced here). CHECK ITS RESULT next session.
VERCEL DEPLOYMENT: dpl_H47q8iBB8HaHMZXhy1SMva2fcCM2 READY, aliases bluntly.ph / www.bluntly.ph.
  Rollback candidate: dpl_76TdpS3A84mSBhuNBfcFSCzXFLX8 (7a2c791) — but the DB stays at 0082 (additive,
  old code was verified healthy on it).
PRODUCTION SMOKE RESULT (read-only GETs, no sign-in, no writes): 200 — /, /welcome, /login, /signup,
  /search (+q, +questions tab, +stores tab), product view /search?product=…, /questions, a question, a
  review, a store page, a member profile, /feed, /categories, /compare, /terms, /sitemap.xml, /health;
  server HTML of 10 key pages has no error boundary / Next error digest. Signed out: /admin, /admin/inbox,
  /admin/sellers, /admin/settings, /admin/analytics, /seller/dashboard, /seller/{id}(/questions,
  /appeals), /messages, /dashboard → 307 /login?next=…. APIs: products, question, review, store, store
  reviews ?offset= → 200; /conversations, /admin/inbox, store questions, /admin/integrations/paymongo,
  /cases/claim/{id}/messages, /notifications, /users/me/payout-tips → 401. Vercel runtime errors since
  deploy: 0. NOT DONE: signed-in production checks (no production session used) and a real-browser
  pass against production (this container's Chromium rejects the egress chain; documented, not bypassed).
KNOWN NON-BLOCKING ISSUES: main's "Backend (isolated database)" job (see CI STATUS); /products/<id>
  is not a route (products are viewed at /search?product=…) — not a regression.
NEXT DEVELOPMENT TASK (on defense-build-oct6 only): SESSION 9 — PART 2 → NEXT: compare the remaining
  Seller frames (Overview, Reviews, Products, Insights, StoreProfile, PublicPage, Settings, Inbox) and the
  Admin screens with Figma line by line and close real gaps. SELLER EMAIL CHANGE stays an explicit OWNER
  DECISION (Figma read-only vs Backend Proposal editable; touches sign-in) — do not implement silently.

## SESSION 9 — PART 2 (after the owner attached Backend Proposal.pdf and Figma, ~03:00–05:50 UTC) — READ FIRST

INPUTS NOW AVAILABLE: Backend Proposal.pdf (same content as session 8's classification: items 28–30
  + 10 implied items) and the Figma connector (file lso4Ri4hDaZxvCebhUqlY5; read with use_figma
  read-only scripts and get_screenshot — load the figma-use skill resource first).
MIGRATIONS ON THIS BRANCH NOT ON PRODUCTION: 0075–0082 (production is at 0074).
  0081_answer_edited_at (answers.edited_at), 0082_seller_response_edited_at
  (seller_reviews.seller_response_edited_at): both nullable columns, downgrades drop them.

DONE (part 2; each tested, browser-verified, pushed):
  62c9292 FIELD STATES read from Figma Admin Components · States 8265:27081: hover ink 50 %, focus brand
    border + 3px ring (brand 16 %), error danger border + 3px ring (14 %), disabled page grey / 10 %
    border / 50 % text. Tokens --border-input(-hover/-disabled), --text-disabled, --ring-field-*.
  e34b0b0 QUICK ACTIONS to Figma 8212:23261: centred 560px palette, "Type a command or search…", esc,
    icons, exactly the frame's actions (Respond to the oldest review, Answer the oldest question
    → /questions?answer=oldest, Link a product → /products?link=1, Download CSV). Selection follows
    real mouse MOVEMENT (a re-filtering list under a still cursor stole the keyboard selection).
    FOCUS BUG: the global :focus-visible outline (app/globals.css) is UNLAYERED, so Tailwind's
    outline-none never removed it; console fields drew outline + ring. `.console-field` opts out.
  9b09f81 EDIT A STORE ANSWER (Figma Questions/Answered 8201:22543 "Edit" → Overlay/Store/EditAnswer
    8202:22530; was listed as an owner question, but it is designed): PATCH /questions/{id}/answers/
    {answer_id} — store answer, its author, only while they still own the store; buyers see "· Edited".
  a4729df APPEALS + QUESTIONS Sort / Filter / Search (Figma Menu/Seller/Appeals/* 8198:21632/21642,
    Menu/Seller/Questions/* 8198:21562/21572) via the shared URL-driven ListControls (filter options
    may now carry counts); Questions columns per tab as the frames (Following = followers, the asker
    left out; Answers = community answers, the store's own left out). Confirms worded as the frames
    (PostResponse, SaveResponse, SendFlag, PostAnswer, SaveAnswer).
    BUG FIXED (0082): editing a response OVERWROTE seller_response_at, which the median reply time and
    Insights read (every edit made the store look slower) and RE-SENT "The store responded". An edit
    now keeps the first time, sets seller_response_edited_at, doesn't re-notify; buyers see "· Edited".
  94c259e CLAIM EVIDENCE FILES (Figma Overlay/Seller/Claim 7996:11538; proposal "image viewer opens files
    attached to … seller claims"): GET /cases/{kind}/{id}/messages now returns each message's attachment
    (signed-link href, parties + staff only); the admin CaseChat draws file cards; the claim window lists
    the claimant's files under Evidence. The seller claim form stays text-only (Figma ClaimStore has no
    upload); files reach the case through its thread.

FIGMA-CONFIRMED DECISIONS:
  - Seller EMAIL: Overlay/Store/Account 8232:25342 draws it masked + read-only → not built (the proposal
    asks for editing → still an OWNER DECISION; safe design recorded below in part 1).
  - evidence_url stays a labelled external link (security), not an inline image.
DEVIATIONS (documented in code): Questions filter/column "About: Your store / Products" left out — the
  list is store questions only and a claimed seller cannot answer a product question
  (seller_cannot_answer). Sending files FROM the case chat ("+") not built (staff attach from the Inbox).

TESTS (part 2): FULL backend suite at 94c259e (tip of code): 3054 passed, 0 failed, 2 deselected
  (receipt-privacy: need Supabase TEST storage). Frontend unit 527/527; tsc + eslint clean. e2e
  owner-patch-journeys 19/19 and br-journeys on fresh fixtures; CI journey set 94 passed / 3 failed on a
  CUMULATIVE fixture DB (admin-journeys 14 + QA-027/028 = known cumulative artifacts; owner-patch 14 was
  contention with a concurrent backend suite and PASSED alone: 19/19).
  NOT RE-RUN after part 2: the defense walkthrough (last 7/7 at 62e32d7) — rerun it first next session
  (production build + `python -m scripts.defense.seed --reset`; the defense DB must be at 0082).

NEXT (in order):
  1. Rerun the defense walkthrough on a production build (migrate lci_defense to head, --reset seed).
  2. Remaining Seller frames not yet compared line by line with Figma: Overview 8190:20643, Reviews
     8196:20870 (+ Responded/All), Products 8204:22648, Insights 8208:22905, StoreProfile 8209:23011,
     PublicPage 8217:23574, Settings 8218:24151, Inbox 8304:32524 — read each with a use_figma text dump
     (as done for Questions/Appeals) and close real gaps only.
  3. Admin screens vs Figma the same way (Overview, Queue, Sellers, Payouts, Settings, Analytics).
  4. Owner decisions (unchanged): seller email change; CI dispatch (touches TEST) or a PR; applying
     0075–0082 to production before any deploy of this branch.

## SESSION 9 (2026-10-04, from ~01:05 UTC; earlier timestamps in this section said 02:00/03:10 by mistake) — READ THIS FIRST

BRANCH RULE (owner, session 9): every commit and push goes to `defense-build-oct6` only
  (`git push origin HEAD:defense-build-oct6`). Never main, never a new branch, never force-push. Before
  each push: `git fetch origin` and reconcile against origin/defense-build-oct6 only.
CONTINUITY: sessions 7–8 pushed 48 commits to claude/elegant-gauss-2ikk4a (Seller console, messaging,
  Inbox, store↔product links, Insights, Export CSV, Scheduled jobs / All voters overlays, image viewer,
  Investigation Author/Originality tabs + Answer investigation, PayMongo config, Seller password,
  server-side notification filter, evidence_url as a link). That branch was a strict descendant of
  defense-build-oct6 (cd0119b), so session 9 FAST-FORWARDED defense-build-oct6 to it (cd0119b..e26619f,
  no merge commit, no force). Nothing was recreated. claude/happy-thompson-xn5imb (Shopee import record,
  d80b901) is a separate catalogue workflow: NOT brought in (out of scope; see SESSION 8 note on the
  scraper).
  InvestigationTabs.tsx / AnswerInvestigation.tsx / ConnectPayMongo.tsx: all present on the branch
  (24dd10c, 823e737, e26619f) — REMOTE HAS THE WORK.
MIGRATIONS ON THIS BRANCH NOT ON PRODUCTION: 0075–0080 (production is at 0074). Applying them needs
  owner authorization; do not deploy this branch before that.
INPUTS NOT IN THE REPO: "Backend Proposal.pdf" was not attached to session 9 (classification below is
  session 8's, from the PDF). No Figma connector in session 9 (sessions 7–8 had one).

DONE (session 9):
  9bd133f DESIGN SYSTEM — ledger item 5 + the field/textarea work session 8 had started:
    components/console/fields.ts (FIELD_INPUT / _COMPACT / TEXTAREA / LABEL / HINT / ERROR; error look
    from aria-invalid), CountedTextarea + counted-model.ts (NO maxLength: the Figma over-limit state —
    danger border, danger counter, "N characters over the limit" — is reachable; submit off while
    countState().over; counts code points like the API), Callout (6 inline copies replaced),
    --shadow-modal on every modal, new --shadow-segment token (17 copies). 11 console textareas moved
    onto it (list in docs/CONSOLE_DESIGN_SYSTEM.md); reviewer New message uses countState in its own
    in-field counter. Single-line inputs keep maxLength (no counter drawn). docs/CONSOLE_DESIGN_SYSTEM.md
    WRITTEN (tokens, components → files, field states, rules, evidence_url rule).
    Tests: frontend unit 521/521; tsc + eslint clean; e2e owner-patch-journeys 17/17 (new 7b over-limit),
    admin-console 14/14, review-queue-wilson + admin-journeys + br-journeys pass (fresh fixtures,
    container Chromium 1194 via a local pw config, not committed). Screenshot verified.

  9b2932e TESTS — full backend suite had 4 failures from session 8 code: migration dry-run (0078/0079/
    0080 enum-only no-op downgrades now listed with the reason) and trust boundaries
    (ConversationStatusIn.status — staff-only Inbox status — reviewed and listed).
  c01d825 CompareRow shared by Insights + Product analytics (no visual change).
  bf454dd + 2078c75 SELLER QUICK ACTIONS (Overlay/Store/QuickActions 8212:23261) — was PARTIAL: search box
    (⌘K), ↑/↓/Enter/Escape, each count opens its own screen, actions Respond to the oldest review
    (/reviews?respond=oldest opens Respond; only when one waits), Download CSV (dialog in place), Rating
    summary report, New message to the team, See your public page. quick-actions-model.ts (+unit tests).
    Phone: the panel spans the drawer's button.
  9b474d3 SELLER REVIEWS PAGING — was "newest 100 only": GET /sellers/{id}/reviews ?offset= (0–10,000,
    id tie-break); console loads 100/page up to 1,000 (getAllSellerReviews). test_seller_reviews_paging.
    Browser: 122 ratings all listed.
  0b9d9b4 REGRESSION FIX — the Rating Summary report (/sellers/{id}/reports) was unreachable after session 7
    redirected the old store dashboard to the console: link restored on Insights + Quick actions; report's
    back link → Insights. e2e meeting-0929 F updated: tier chips now live in the Queue's Filters menu.

  a224de6 PHONE LAYOUT — Seller Overview cards ("Waiting on you" + the next) were 465px and CLIPPED at 360px
    (grid's implicit auto column); fixed with grid-cols-[minmax(0,1fr)] there and on Admin Analytics /
    Activity. 360px sweep: 11 Seller screens + 10 Admin screens + reviewer /messages, /dashboard, /profile,
    /feed — no clipped section, no sideways scroll, no page error, no unlabelled control.
  038cff3 Overview Respond pills rendered 19px tall (h-8 on an inline <a>); breadcrumb / See all hit areas.
  c356674 evidence_url rendered as a link only when http(s) (pre-validator rows shown as text).
  4d66c17 ?respond=<review id> — Overview Respond / Edit open that review's Respond window.
  62e32d7 DEFENSE WALKTHROUGH was BROKEN by session 8 (scene 6: loose locators vs e109dc4's "No brand"
    checkbox and the closed "Merge into …?" confirm) — selectors fixed; product unchanged.
    REHEARSAL 7/7 PASS on `next build` + `next start`, fresh `--reset` seed, verify 109/109 READY.

ALSO VERIFIED (session 9, browser, defense dataset on a production build): Answer investigation overlay
  (Queue → Answers → question → "Investigate this answer"): Summary / Votes / Voters / Originality / Author
  tabs all load real data with truthful empty states, no page errors. PayMongo security read: staff read
  (router require_staff), save / test / delete require_super_admin, Fernet at rest, only sk_…last4 returned,
  audit context holds no key, one read-only GET /v1/payments?limit=1; nothing reads platform_settings
  generically.

CI NOTE: ci.yml runs on PRs and main only; db-fast on feat/** fix/**; so NOTHING in CI has run on
  defense-build-oct6's sessions 7–9 commits. Session 9 did NOT dispatch ci.yml by hand: its "Backend
  (isolated database)" job would migrate the shared TEST Supabase project to 0080 and write to it (where
  the defense dataset lives) — owner's call. Local equivalents were run instead (see TESTS RUN).

SELLER EMAIL CHANGE — INVESTIGATED, NOT BUILT (owner decision needed): Figma Overlay/Store/Account
  8232:25342 draws the email masked + read-only; the Backend Proposal asks for editing. Sign-in is by
  email code (otp_service), so a safe change needs: POST /users/me/email/request {new_email} (signed in,
  rate-limited, 409 if taken) → a code sent to the NEW address bound to the USER (new email_otps.user_id
  column or a pending_email_changes table + a new OtpPurpose 'email_change' enum value → migration),
  verify_otp must IGNORE email_change rows (else the code would sign up a new account), POST
  /users/me/email/confirm {code} → swap + notify the OLD address + audit. ~1 migration, auth-path change.

STATUS vs the session-9 brief:
  Seller claim/withdraw, filtered notifications, display name, username: DONE (session 7–8).
  Seller password change: DONE (e5ffaa1; POST /users/me/password; 409 no_password for email-code
    accounts). Seller EMAIL change: NOT BUILT — the frame shows it masked/read-only; a verified
    change-email flow is an OWNER QUESTION.
  Case-bound chat (claim/appeal ↔ staff): DONE (0076 conversations, case_key; RBAC 404 for strangers;
    e2e owner-patch 8–10 PASS this session).
  Seller reports: no Screen/Seller/Reports frame; the seller's reporting is Flag-as-fake → Appeals (DONE);
    the Rating Summary report is linked from Insights / Quick actions.
  Analytics 7D/30D/90D/12M: VERIFIED in the browser + API this session (real windows; previous equal
    period: e.g. reviews 90D 9 vs 1, 12M 10 vs 3; no page errors).
  Report import: VERIFIED (Shopee CSV → detected, 108 rows, preview, nothing applied until confirm).
  Process requests: VERIFIED hidden ("Manual transfers") without the PayPal Payouts API — by design.
  PayMongo: config only, payouts_enabled always false. No money movement.
  evidence_url: labelled external link, never an <img> (0b47092). Keep.

TESTS RUN (session 9, at 0b9d9b4 unless noted):
  Backend FULL suite at 9fe40f0 (tip of code): 3039 passed, 0 failed, 2 deselected (receipt-privacy,
    need Supabase TEST storage). Earlier at 9f61b9d + fixes: 3038 passed, 0 failed (2 receipt-privacy tests deselected:
    need Supabase TEST storage). Targeted after: seller/OpenAPI/contract 191 passed, paging 1 passed. ruff clean.
  Frontend unit: 525 passed (incl. counted-model 5, quick-actions 4). tsc + eslint clean.
  `next build`: PASS (at 9b474d3 and again at 4d66c17).
  Defense walkthrough rehearsal: 7/7 PASS at 62e32d7 (production build, fresh reset seed).
  e2e on a FRESH database (lci_fresh; exactly the CI "Browser journeys" spec list): 107 passed, 0 failed,
    2 skipped (own preconditions). admin-console (moderator token) 14/14.
  e2e on the cumulative local DB only: admin-journeys 14 and QA-027/028 fail (known cumulative-data
    artifacts; both PASS on the fresh DB).
  LOCAL STACK (session 9): PG 17 on 5433 (`pg_ctlcluster 17 main start`); venv + env.sh in the
    scratchpad; Playwright 1.62 with the container's Chromium 1194 through a throwaway config passing
    launchOptions.executablePath=/opt/pw-browsers/chromium-1194/chrome-linux/chrome (never committed).
    No `ss` in the container: find uvicorn's pid through /proc/*/cmdline before restarting it.

KNOWN DEVIATIONS / NOT DONE (need Figma or the owner):
  - Seller Appeals has no Sort / Filter / Search: not added without Figma confirmation (Questions has
    none either). Re-check frame 8196:21910 when a Figma connector is available.
  - Remaining inline patterns (Meter, Quick action item, Notification item, Step list, Option row,
    Inline reply) are one-screen each — extract when a second screen needs one.

NEXT (in order):
  1. With Figma access: audit Admin Components · States 8265:27081 against components/console (the
     states were implemented from the handoff's description, not re-read from Figma this session).
  2. Appeals sort/filter IF the frame draws it.
  3. DONE (a224de6, 038cff3) — 360px sweep. Remaining: nothing found.
  5. Owner: decide whether to run CI (ci.yml dispatch touches TEST) or open a PR from defense-build-oct6.
  4. Owner questions (unchanged): seller email change flow; editable payout day; answers Take down /
     Remove flagged votes; answer rewards; per-type notification settings; editing a store answer.

## SESSION 8 — LEDGER (updated 2026-10-04 ~00:55 UTC) — READ THIS FIRST

Sources, in order of authority: FIGMA (UX; file lso4Ri4hDaZxvCebhUqlY5) → BACKEND PROPOSAL
(owner's PDF "Backend Proposal", 2026-10-04: 3 explicit Seller items 28–30 + 10 implied by the new
admin screens + 1 frontend item) → this repository → this handoff. The Shopee scraper / product
seeding runs ELSEWHERE (separate Claude/Apify workflow): do not install Apify, call it, wait for it,
or reset product data here. Nothing in this app depends on it having run.

MIGRATIONS ADDED THIS SESSION (all NOT on production; owner authorization needed to apply):
  0076_conversations, 0077_store_products, 0078_store_release (enum value), 0079_data_export
  (enum value). Local DB is at 0079. Details: docs/ADMIN_SUPERADMIN_MIGRATION.md.

DONE this session (each: ruff/pytest or tsc/eslint/unit tests, browser-verified, pushed):
  d17beeb 65c38f5 a0b45d2 a83f19d 2086bd4  messaging + inbox + seller/reviewer messages + search
  0ad2294 admin list menus (Sellers claims/appeals, Payouts, Honesty Fund, Affiliate months/imports)
  e109dc4 products "As is" / No brand / merge two catalogue pages (POST /products/{id}/merge)
  0c1807d store ↔ product links backend (0077) · da396df Seller Products + analytics, admin
          Sellers → "Product links" tab (an addition: no admin frame exists)
  346f9e2 Seller Insights (8208:22905), Download CSV (8213:23286), Store profile (8209:23011) +
          Request a change (sends an Account conversation) + Give up (8220:24024; unclaims, audited
          store_release, 0078), Public page preview (8217:23574), loading states, rail items live
  0ec44c7 Scheduled jobs overlay (8237:25609; next_at) · All voters overlay (8237:25697; weight)
  967a545 Image viewer (8237:25416) for message attachments (signed links, ?download=true) and the
          review photo
  8528d56 Admin Export CSV (8237:25470) from Activity log / Analytics / Settings; server-side name
          shortening + email removal; audited data_export (0079)
  823e737 Connect PayMongo overlay (8237:25540) in its truthful unavailable state (nothing stored)
  24dd10c Investigation Author + Originality tabs (8112:*), vote places Count/Rate (8237:26485,
          from review_first_vote_geo_buckets), Answer investigation (8129:*, 8237:26795) from the
          Answers queue, Moderate → Unmark best answer (staff, audited override)

BACKEND PROPOSAL — CLASSIFICATION (audited in code 2026-10-04):
  28 Seller profile + password ......... PARTIAL. Display name, username, photo: DONE (PATCH
     /users/me). Figma Overlay/Store/Account 8232:25342 shows the email MASKED/READ-ONLY and a
     Change password block (current / new ≥10 / repeat): change password = MISSING → NEXT.
     Email EDIT is not in the frame (proposal asks for it): not built; needs a verified
     change-email flow → OWNER QUESTION. Note: web sign-in is email-code only (no password form);
     a password works only through POST /auth/login.
  29 Claim status + withdraw claim ...... DONE (ClaimStatusDialog 8232:25429 steps + registration
     last 4; Confirm/Store/WithdrawClaim 8233:25386; POST /sellers/claims/{id}/withdraw, 0075;
     opened from the store switcher; tests in test_seller_claims*).
  30 Filtered seller notifications ...... DONE (StoreNotifications: All/Reviews/Questions/Appeals
     over GET /notifications kinds; Mark all seen). Possible hardening: server-side kind filter
     so a tab is not limited to the latest page → in NEXT as a check.
  Image/attachment storage + retrieval .. PARTIAL. Message attachments: DONE (private bucket,
     signed 5-min links, viewer). Review receipt (Originality "View full image"): DONE via audited
     GET /reviews/{id}/receipt. Seller claims carry NO files (registration is text) → N/A.
     Affiliate imports are CSV, not images → N/A. Report evidence is a reporter-supplied URL
     (moderation_logs.evidence_url) → open it in the viewer when it is an image: NEXT.
  CSV export (Analytics, Activity log) .. DONE (8528d56).
  PayMongo ............................. PARTIAL: overlay only, nothing stored. The owner's
     2026-10-04 message allows secure config + test status + test mode WITHOUT transfers →
     NEXT: Super Admin saves keys encrypted (needs an encryption key env var), test connection,
     methods, test mode. No payout execution, ever, without a new owner decision.
  Scheduled jobs ........................ DONE (0ec44c7 + existing Run now / Super-Admin guard).
  Voter data ............................ DONE (reviews: weight/timing/signals/flagged + places
     Count/Rate; answers: timing/signals/circle flag; answer votes have no weight/place — stated).
  Analytics periods 7D/90D/12M .......... DONE (session 5: analytics_summary_service RANGES, real
     windows + previous equivalent period). Re-verify in the browser at the next pass.
  Payout processing ("Process requests") DONE (manual flow; the API button appears only when
     the PayPal Payouts API is configured).
  Report import (Settings) .............. DONE (Settings → Import report → Affiliate imports
     modal: preview, errors, confirm, audit csv_import). Re-verify once.
  Design tokens (warning/critical/watch, modal shadow) DONE in app/tokens/colors.css
     (--status-high/critical/watch-*) and effects.css (--shadow-modal). docs/CONSOLE_DESIGN_SYSTEM.md
     does not exist → NEXT: write it (token table + Admin/Chip tones), no new values.

SELLER CHAT (case-bound) .............. DONE: conversations (0076) with case_key per claim /
  appeal; seller ↔ staff only; RBAC 404 for strangers (test_conversations, e2e owner-patch 8–10);
  attachments private. No user-to-user chat (by design).
SELLER REPORTS (Figma audit 2026-10-04) . No Screen/Seller/Reports frame exists. The seller's
  reporting is "Flag a review you think is fake" (Overlay/Store/FlagFake 8197:21432) → Appeals
  screens (8196:21910, 8201:23146/23417): DONE. Reports filed by others against the store are
  staff-only in every frame → N/A for the seller (privacy).

OWNER QUESTIONS (open): email change flow (verified) for sellers; PayoutDay editability
  (code constant: internal_cron schedule_payouts day 5); answers "Take down" (answers have no
  is_removed; needs a migration + read-path filtering) and "Remove flagged votes" (signals never
  act today); answer rewards (none exist; the frame's "Reward decision" is inert); per-type
  notification settings; editing a store answer.

DEVIATIONS (intentional, documented): Payouts "Send to" filter omitted (PayPal only); Claims
  "Both" omitted; Product analytics durability row + question topics omitted; Insights themes
  unavailable (store reviews are free text); RequestProduct "Where you sell it" not stored;
  Insights peers = same marketplace (stores have no category); Originality: no photo comparison,
  no receipt checks, no marketplace/web text search; answers: no vote places.

NEXT (in order; continue autonomously) — SUPERSEDED: items 1–6 DONE by session 9 (see SESSION 9):
  1. Seller change password (Overlay/Store/Account; POST /users/me/password, current required,
     new ≥10, uniqueness n/a) + tests.
  2. Notifications: verify the Seller tabs against the API page size; add a server-side kind
     filter if a tab can miss rows.
  3. Report evidence URL → image viewer in the admin report panel (when it is an image).
  4. PayMongo secure configuration (encrypted keys, test mode, test connection; no transfers).
  5. docs/CONSOLE_DESIGN_SYSTEM.md (tokens + chip tones), Admin Components · States 8265:27081.
  6. Re-verify Analytics periods, Report import, Process requests in the browser.
  7. Responsive / error / loading / accessibility polish; full backend suite; e2e.

## SESSION 8 (2026-10-03, from 19:35 UTC) — NEW FIGMA FRAMES (8265+): MESSAGING, SEARCH, MENUS

Owner request: "build all of [the new Figma pages] along with their functionality" (new frames from
id 8265 on: the Inbox / Messages system for Admin, Seller and Reviewer, global search, more list
menus, product menus) plus the Seller screens still missing. Owner decisions (2026-10-03, asked):
(1) a claim's / appeal's case chat and its Inbox conversation are ONE thread ("merge into Inbox");
(2) New message REPLACES Contact support (existing support requests stay in Queue → Support; an
admin can move a seller conversation there).

MIGRATION 0076_conversations (NOT on production; owner authorization needed, like 0075):
  conversations + conversation_messages, 4 enums, moderation_action 'conversation'; COPIES the
  platform_settings case chats (rows left in place). Needs a PRIVATE Supabase bucket
  `message-attachments` before attachments work (text works without). Replies/closes are emailed
  via EMAIL_PROVIDER (console logs only); SITE_URL sets email links (default first CORS origin).
  Details: docs/ADMIN_SUPERADMIN_MIGRATION.md (0076).

DONE (each tested + browser-verified + pushed):
  d17beeb backend: /conversations (member) + /admin/inbox (staff), case chat through conversations,
          attachments (private, signed 5-min links), audit, email. tests/test_conversations.py (9).
  65c38f5 Admin Inbox /admin/inbox (8291:30461 …): rail item + unread pill, top-bar chat button,
          tabs/sort/filter/search, assign/status/more menus, close confirm, reopen, move to Support,
          loading/empty, phone layout. e2e admin-console 14/14 (+ /admin/inbox in the no-scroll set).
  a0b45d2 Seller Messages /seller/{id}/messages (8304:32524 …) + New message overlay (8276:29363);
          Contact support → New message; /sellers/{id}/support/new redirects; e2e owner-patch 8–10
          rewritten (seller writes → admin answers in Inbox → moved to Support → other owner 404):
          16/16 on fresh fixtures.
  a83f19d Reviewer Messages /messages, /messages/new, /messages/{id} (8296:31219 …): Link sheet,
          More sheet (Email me a copy → toast, Mark as resolved → confirm), Sent note, Sending /
          Not sent states; "Messages" in the profile side panel; /messages protected.
  2086bd4 Global search in both top bars (8289:29993 / 8289:30079 + No results): /admin/search,
          /sellers/{id}/search, keyboard nav. tests/test_global_search.py (2).
  Library check (owner republished 19:47): Admin/SearchResult, Admin/Message, Admin/ChatThread
  match what was built (pending bubble 60%).

NEXT (in order): admin list menus 8288:* (Sellers claims/appeals, Payouts, Honesty Fund,
  Affiliate months/imports: sort/filter/search) · product menus 8287:* (merge + Confirm/Product/Merge,
  category menu, merge search) + Menu/Settings/PayoutDay · Overlay/Product/Edit & Catalogue "As is" ·
  Overlay/Store/RequestProduct(+Similar) · remaining Seller screens (Products, Insights, Store profile
  + Request change, Public page, Export, Give up) · Admin gaps (Image viewer, Export, PayMongo UI —
  no payment execution, Jobs, Voters/All, Votes/Rate) · Admin Components · States (8265:27081).
LOCAL NOTE: if Postgres 17 is down after a container restart: `pg_ctlcluster 17 main start`.

## SESSION 7 (2026-10-03, 15:31–19:35 UTC) — OWNER BUGS + SELLER/ADMIN CONSOLE HANDOFF

SESSION 7 CLOSE (19:35 UTC): branch claude/elegant-gauss-2ikk4a, everything committed and pushed,
  local = remote, working tree clean. After the 19:20 close two small atomic items landed: ba573d9
  Seller loading states (6 screens + first-entry rail; verified on the production build) and
  f54d5d3 review modal "Open on site" (e2e admin-console 14/14 on the production build; `next
  build` PASS, frontend unit 488/488, tsc + eslint clean). 26 commits after cd0119b, on top of main 7a2c791 (+ the defense-build handoff
  commit cd0119b). NOT merged to main, NOT deployed. ONE MIGRATION ADDED: 0075_seller_claim_withdrawn
  (enum value; production must be migrated to 0075 before this code deploys — owner authorization).
FINAL TESTS AT THE TIP: frontend unit 488/488 · tsc clean · eslint clean on every file changed this
  session · ruff clean on every backend file changed · `next build` PASS (7 /seller routes) · backend
  targeted 602 passed (seller, Q&A, notifications, support, case chat, product add/import, drafts,
  all reviews, RBAC sweep, OpenAPI contract, migrations) · FULL backend suite 2963 passed at ~18:40
  (before the last 2 backend commits, both covered by the 602 run). Browser checks per feature (see
  the commits). e2e: owner-patch 5-8/10/15, review-queue-wilson Q/R/T/D, admin-journeys 7-10 PASS.

BRANCH: claude/elegant-gauss-2ikk4a (the session's designated branch; started at main 7a2c791 +
  the defense-build-oct6 handoff commit cd0119b, fast-forward). main untouched; nothing deployed.
  Never force-pushed. Local = remote after every push (verified with rev-parse).
DESIGN-SYSTEM GUIDE: docs/CONSOLE_DESIGN_SYSTEM.md DOES NOT EXIST in any branch, nor in Drive
  (searched). Worked from the Figma library instead (file lso4Ri4hDaZxvCebhUqlY5, library
  "bluntly.ph": Admin/Chip, Shadow/Modal, status/* variables, Pagination). If the owner has the
  guide elsewhere, add it to docs/ and re-check components/console against it.
FIGMA: connector works (whoami Zienxt). Node ids from the old handoff mostly still resolve
  (7998:11693 People, 8060:15564 All reviews, 7967:11173 Catalogue, 7943:11402 Queue,
  7879:10223 Overview, 7992:11327 Claims); 8037:13080 and 8042:13037 (modals) no longer do.

OWNER-REPORTED ITEMS — ALL DONE (each reproduced, root-caused, tested, browser-verified, pushed):
 1. d737eca PUBLISHED REVIEW STILL AN EDITABLE DRAFT. Root causes: the composer's 1.2 s debounced
    autosave PUT landed after the post-publish DELETE and re-created the draft; the DELETE was best
    effort; other devices re-uploaded their local copy. Server now: POST /reviews and
    /reviews/{id}/updates delete the product's draft in the publishing transaction; a product-slot
    draft saved no later than the caller's newest entry on that product is consumed — never listed
    by GET /review-drafts, refused by PUT with 409 draft_published (+thread_id). Composer: publish
    cancels the pending autosave and drops local copies the server reports as published.
    tests/test_review_drafts.py +5 (3 fail on old code). Browser: 12/12 checks.
 2. 7838a81 CANONICAL PRODUCT PHOTO SHOWN AS THE REVIEW'S PHOTO. Rendering fallback only (the API
    accepts only the author's own upload as photo_url). lib/review-media.ts reviewPhoto() is the one
    rule; review hero shows "No photo with this review", cards their hue placeholder. Product image
    kept in product context (review page product sidebar, thumbnails, pickers, OG share preview).
 3. fd1fa3e PEOPLE PAGINATION / LEFTOVER SUBTAB. Production's ~23 members fit the old 25-row page
    so no pager ever showed. Shared components/console/Pagination (Figma Pagination: range, ← pages
    →, 10/25/50 per page) on /admin/reviewers (?page=&size=, filters kept, page clamped, empty
    state); search is the toolbar popover; Open on row hover. The leftover "Members | Users" subtab
    row is gone; User management opens from Settings → Team → Manage roles and Quick actions
    (Super Admin); its search results page with the same component.
 4. 194796a QUEUE → ALL REVIEWS to Figma 8060:15564: toolbar Queue switch + Sort/Filter/Search
    menus; table Review (product thumbnail, product, "by" author) / Level / Rating / Earnings /
    Wilson / State / Posted; shared pager (apage/asize). QA's figures (gate Wilson, votes, queue
    reason) moved into the row tooltip + sr text (e2e review-queue-wilson R updated, PASS).
    Backend: GET /admin/reviews rows carry product.image_url (additive).
 5. 51c8438 + 175e0d3 REMOVED the "Catalogue | Prices" subtab row. /admin/prices unchanged; reachable
    from Needs attention + Quick actions ("Price observations"); pages without a subtab name
    themselves (title + crumb Admin / Products / Prices).
 6. bca9aa9 PRODUCTS: ADD PRODUCT + IMPORT PRODUCTS (no frame; console action-pill language).
    POST /admin/products (staff; one transaction; 409 product_exists on a duplicate by listing link
    or normalised name) and POST /admin/products/import (CSV preview/apply; columns brand*, line*,
    category*, variant, type, aliases "|", source_url, specs "Label: Value | …"; ≤500 rows, 1 MB).
    No product import format existed before — this one is NEW (documented in the service docstring
    and the modal; template download). Add product = Edit modal "create" mode → reopens in Edit for
    the photo. tests/test_product_admin_add_import.py (6). No migration, no new audit action.

DESIGN-SYSTEM COMPONENTS IMPLEMENTED (components/console/, shared by Admin and, next, Seller):
  Pagination (+ pagination-model.ts, unit-tested) · ProductThumbnail · Chip (Admin/Chip tones) ·
  popover.ts (usePopover, ICON_BUTTON = Figma IconButton, MENU panel). TOKENS: --shadow-modal (Figma
  Shadow/Modal; replaced 9 hardcoded menu shadows), --status-high-fg (#e94f1d, Figma), and
  --status-success-bg/-fg (success-600 on a DERIVED tint #e8f7ea — verify against Admin/Chip).
  Star ladder in admin cells bound to Figma tokens (success-500 / star / brand-coral / danger).
  STILL TO READ FROM FIGMA: status/watch, status/neutral, status/baseline values (variables exist;
  the MCP did not return their values from the frames tried).

TESTS THIS SESSION: backend targeted (drafts 14, double-submit, all-reviews 12, product add/import 6,
  RBAC sweep, OpenAPI contract, product specs) PASS; ruff clean on changed files; frontend unit
  479/479; tsc + eslint clean; e2e (local stack, container Chromium via a local config override
  pw.local.config.ts — not committed): review-queue-wilson Q/R/T/D PASS, admin-journeys 7-8 + 9-10
  PASS. NOT RUN: full backend suite, full e2e, `next build`.
LOCAL STACK NOTES: PG 17 on 5433 (roles created as in LOCAL ENVIRONMENT below); venv in the
  scratchpad; run uvicorn with --reload as a background task (never `pkill -f uvicorn` from the
  shell — it matches the shell's own command line and kills it).

SELLER DASHBOARD STATUS (session 7): the Seller console exists at /seller/[storeId] (approved
  owner only; /seller/dashboard opens the first store; /sellers/{id}/dashboard redirects there).
  Figma: 107 Seller frames found on Page 1 (Screen/Seller/*, Overlay/Store/*, Menu/Store/*,
  Menu/Seller/*, Confirm/Store/*, loading states) — list them with a read-only use_figma
  (findAllWithCriteria) rather than get_metadata on the page (395 top-level frames).
  DONE: Overview 8190:20643 (515ffed backend, 85760d9 UI) · Reviews 8196:20870 + Respond / Edit /
  Flag overlays + confirms + Sort / Filter / Search (556cda1) · Appeals 8196:21910 + Overlay/Store/
  Appeal (c09103d) · Questions 8196:21469 + Answer overlay + confirm (5c3d787 backend GET
  /sellers/{id}/questions, 6c5bb1d UI) · Notifications panel with tabs + owner notifications for a
  new store review / question (7e4f854 backend, 62a47fd UI) · Settings + Profile window (f300cb9) ·
  Claim status + Withdraw claim · Period menu · Store switcher.
SELLER SIDEBAR STATUS: DONE as the Admin rail (shared NavRow, 232px, pills, drawer < lg): store
  switcher header, Quick actions, Overview; Buyers Reviews / Questions / Appeals (count pills);
  Store Products / Insights / Store profile; footer Public page / Seller rules / Settings. Rows
  whose screens are not built are INERT with "Soon" + reason (Admin rail pattern), never links.
SELLER FUNCTIONALITY MAP (frontend / backend):
  Overview ............................ DONE / EXISTS+DERIVED (period_summary, medians, names)
  Seller Sidebar, switcher, period ..... DONE / EXISTS (+ GET /sellers/claims/mine)
  Claim status + Withdraw claim ........ DONE / NEW (POST /sellers/claims/{id}/withdraw, 0075)
  Reviews + Respond/Edit + Flag fake ... DONE / EXISTS (newest 100 — paging endpoint MISSING)
  Appeals + Appeal overlay ............. DONE / NEW (GET /sellers/{id}/appeals) — no sort/filter yet
  Quick actions ....................... PARTIAL (waiting counts only; command search + actions
                                         "Respond to the oldest review", "Download CSV" missing)
  Notifications panel + tabs ........... DONE / NEW kinds store_review_new, store_question_new
                                         (owner of a claimed store; never their own question) +
                                         existing GET, unread-count, read-all
  Questions + Answer .................. DONE / NEW GET /sellers/{id}/questions (owner) + existing
                                         POST /questions/{id}/answers. Edit answer: NO ENDPOINT (new
                                         behaviour for answers → decide); "About" (no store-product
                                         link) and "Following" (counts not served) columns not drawn
  Products (link product, request, ..)  BLOCKED — OWNER QUESTION: no store↔product link model
                                         ("Sold by <store>" with admin approval) exists; new schema
  Insights 8208:22905 .................. MISSING / PARTIAL (dashboard analytics: engagement,
                                         months, most engaged / discussed)
  Store profile + Request change ....... MISSING / likely via support requests (inspect frame)
  Public page 8217:23574 ............... PARTIAL (rail opens the public /sellers/{id})
  Seller rules (+5 subpages) ........... DONE as one page with "On this page" anchors (copy kept
                                         to what is enforced: links refused; phone/email/handles are
                                         "don't", not machine-blocked)
  Settings + Account (profile) ......... DONE (display name, username via PATCH /users/me; email
                                         shown masked; Contact support; Change photo via POST
                                         /users/me/avatar — verified up to the upload: local has no
                                         Supabase storage, so it shows the error; check on TEST). NOT
                                         BUILT: per-type /
                                         email notification switches (no backend). PASSWORD: NO
                                         PRODUCT BEHIND IT — sign-in is an email code, accounts have
                                         no password → OWNER QUESTION. EMAIL change needs a
                                         verification flow → OWNER QUESTION
  Give up store (Confirm/Store/GiveUp) . MISSING / MISSING (owner unclaim endpoint)
  Export (Overlay/Store/Export) ........ MISSING
  Requests to the administrators ....... KEPT on the Overview (old dashboard's only list) until the
                                         Contact overlay 8220:24077 / Settings exist
  Loading states (Screen/Seller/*/Loading) DONE for Overview 8228:24472, Reviews 8228:25327,
                                         Questions 8228:25961, Appeals 8228:26321, Settings
                                         8228:28761, Seller rules 8228:28562 (route loading.tsx,
                                         real rail kept; app/seller/loading.tsx draws rail + Overview
                                         for the first entry). Products / Insights / Store profile /
                                         Public page / Inbox loading frames wait for those screens.
                                         Verified on the production build (navigation held → skeleton
                                         inside the rail; phone 390px no overflow). Deviation: the
                                         shared Skeleton grey (--base-gray-200) is a shade darker than
                                         the frames' bars.
  Top-bar search ...................... MISSING (no store-scoped search endpoint)
RBAC (verified this session): non-owner member → "This isn't your store" (no figures); signed out →
  /login?next=…; another store's owner → 403 on appeals (test_seller_console_api) and support
  (e2e owner-patch 10); a claim id of someone else → 404. Claimed sellers still cannot vote,
  review or earn (unchanged bar_claimed_seller). The console never grants admin capability.

ADMIN FIGMA GAPS (from the owner brief; NOT started this session): Image viewer (report / claim /
  import attachments, Originality "View full image"), Export CSV modal (Analytics, Activity log,
  Settings → Export), Connect PayMongo UI (DO NOT build payment execution), Scheduled jobs full
  list + Run now, All voters (reviews, answers; weight / timing / flags), Vote Count ↔ Rate toggle,
  Analytics 7D / 90D / 12M — ALREADY DONE (session 5; real per-period figures), Payouts → Process
  requests, Settings → Import report, Investigate overlays Author 8112:17871 / Originality
  8112:17611, the Answer investigation's "Open on site" (Overlay/Answer/Investigate/*).
  CHECKED / DONE at session 7 close: review modal "Open on site" (8109:17496) → /reviews/{id} in a new
  tab, only while the review is published (QueueDecisionBar; e2e admin-console 14/14 on the
  production build). ALREADY PRESENT before this session (verified in code): Person → Open profile
  (PersonInvestigation → /u/{id}), Sellers → Open store / Open review (SellersScreen), Voters tab
  "See all voters" expand (ReviewInvestigation) — the Figma "All voters" full-list screen beyond that
  expand is still to compare.

KNOWN DEVIATIONS (session 7, intentional): no product image column in the product CSV (images are
  uploaded, never fetched); All reviews keeps QA's gate Wilson / votes / queue reason in the row
  tooltip + sr text; the Seller Overview keeps "Requests to the administrators"; seller screens not
  built are inert rail rows; Seller Reviews lists the newest 100.

CHECKPOINT (session 7, ~18:45 UTC): FULL BACKEND SUITE 2963 passed (receipt-privacy file excluded:
  TEST storage credentials, as before) · `next build` PASS (all /seller/* routes) · frontend unit
  487/487 · tsc + eslint clean · e2e on the PRODUCTION build: owner-patch, review-queue-wilson,
  route-guards → 38 passed, 2 failed, both NOT regressions: owner-patch 9 (two identically named
  support requests after running journey 8 twice on the cumulative local DB) and route-guards
  "/contracts" (app/contracts was deleted 2026-09-23 in 8d55b47; the spec still lists it —
  pre-existing, untouched).

NEXT EXACT TASK: (1) Verify Seller "Change photo" on TEST (storage). (2) [done: Seller rules]. (3) Insights
  8208:22905 (inspect; most figures derive from the dashboard). (4) Store profile 8209:23011 +
  Request change (likely a support request). (5) [done: Seller loading states]. (6) Admin
  gaps above, starting with the Image viewer (review report / claim / import attachments), then
  compare the Voters tab's "See all voters" with the Figma All voters frame. OWNER QUESTIONS to raise: password /
  email in the Seller Profile window; Products (store↔product links); "Give up this store";
  editing a store answer; per-type notification and email settings.

## MERGE STATUS (session 6, 2026-10-03 ~10:30 UTC)

MERGE STATUS: MERGED. PR #9 https://github.com/bluntly-ph/bluntly.ph/pull/9 (defense-build-oct6 -> main).
SOURCE BRANCH: defense-build-oct6   SOURCE SHA: 9848d0d
MAIN BEFORE: 87bf88e   MAIN SHA: 7a2c791 (merge commit; tree identical to 9848d0d)
MERGE METHOD: GitHub PR, merge commit (no squash, no force-push).
PRODUCTION MIGRATION (owner Zient authorized in writing, session 6): Supabase project byobedbhodhvocgrkrse
  ("bluntly.ph") 0070_vote_network_fingerprints -> 0074_alias_remove_action BEFORE the merge.
  How: no production DATABASE_URL in the cloud container, so the exact SQL from
  `alembic upgrade 0070_vote_network_fingerprints:head --sql` (offline, no DB contact) was applied
  through the Supabase connector: 0071-0073 in one transaction, then 0074's
  `ALTER TYPE moderation_action ADD VALUE 'alias_remove'` (autocommit, as the migration does), then
  the version row. Pre-flight: at 0070, none of the new objects existed. Post-check: alembic_version =
  0074; products.specs jsonb NULL-able; users.payout_account_name varchar NULL-able; answer_replies +
  qa_votes exist, RLS on, 0 anon/authenticated grants, 7 indexes; enum value present; users 23 /
  products 70 unchanged. Old code (87bf88e) stayed healthy on the 0074 DB until the deploy.
PRODUCTION STATUS: DEPLOYED AUTOMATICALLY by Vercel from main: dpl_76TdpS3A84mSBhuNBfcFSCzXFLX8, READY,
  commit 7a2c791, aliases bluntly.ph / www.bluntly.ph. Runtime: 0 errors, 0 5xx since deploy.
SMOKE TEST (non-destructive GETs, no sign-in, no writes): 200 — /, /welcome, /login, /signup, /search,
  /search?q=…&tab=questions, /questions, /questions/{id}, /reviews/{id}, /u/{id}, /sellers/{id}, /feed,
  /categories, /compare, /terms, /sitemap.xml, /health; API products (returns new `specs`), product
  search-card, reviews feed, review full, questions, question, seller. Signed-out admin (Overview, Queue,
  People, Payouts, Reports, Sellers, Settings, Analytics) and contributor dashboard/transfer redirect to
  /login?next=…; staff/member APIs return 401. NOT smoke-tested signed in (no production session used).
CI FIXES ON THE WAY IN: e5c43c2 ruff E501 in tests/test_payout_tips.py; 9848d0d REAL BUG — CaseChat's
  expression-bodied useEffect returned scrollIntoView(), which is a Promise in Chrome 151; React called
  it as cleanup ("is not a function") and the Sellers claim/appeal modal crashed into the error boundary
  (walkthrough scene 6). Reproduced locally with Chrome for Testing 151, fixed, 7/7 locally and in CI.
LATEST TEST STATUS (9848d0d): CI all green — Frontend, Backend (no database), Production guard,
  Walkthrough rehearsal 7/7 (own Postgres 17, Chrome 151). Local: tsc, eslint, frontend unit 467/467,
  next build, targeted backend 161 passed. Full backend suite last run at 50fb545 (2940 passed); not
  rerun at 9848d0d (CI "Backend (isolated database)" is skipped on PRs).
KNOWN BLOCKERS: 2 receipt-privacy tests need Supabase TEST storage credentials (never production).
UNMERGED WORK: none. The read-only Admin Settings screen (860740f) shipped in PR #9; no lost Settings work.
BRANCH CLEANUP: NOT DONE — owner wants an audit of merged/obsolete branches as a separate step.
NEXT DEVELOPMENT TASK (on defense-build-oct6, never on main): ledger item 4b — Investigate overlays
  Author tab (8112:17871), Originality tab (8112:17611), then the Answer overlays (8129:*).

## DEFENSE RELEASE CANDIDATE STATUS (updated 2026-10-03 ~01:50 UTC, end of session 4)

CENTRAL SHA: the commit carrying this section on origin/defense-build-oct6 (code verified at
  7428c6a; this commit is documentation only). main untouched.
HIGH: complete. MEDIUM: complete. APPROVED STRETCH: complete.
LOW: see REMAINING PRIORITY LEDGER below (Settings screen, Analytics to Figma, contributor
  states audit, …); cosmetic: animations. (Payouts "oldest requested Nd
  ago" shows a huge N only on the polluted local DB (fixture rows decades old) — real data is
  fine; per-vote timeline chart and "Reused" photo badge in the queue modal (no data behind them);
  admin "Admin-referred" fast-track referral (PRD FR-6, owner question still open).
DEFENSE WALKTHROUGH: 7/7 PASS — latest 2026-10-03 ~07:05 UTC (session 5), production `next build` of
  429f3dc + LOW 4 (All Reviews rating, Payouts Sent/Failed columns, Honesty Fund tab) on 3001, API 8001,
  freshly re-seeded `lci_defense`. Earlier session-5 run: 7/7 at ada4505. Re-seed before every run.
BACKEND: 2940 passed + receipt-privacy 15 passed / 2 BLOCKED (full suite, session 5 ~06:45 UTC, HEAD 50fb545); earlier 2946 at a2481a4 + suspension fix 7428c6a: people management 3/3,
  RBAC sweep, and gate / vote / trust / report / earn / honesty / triage / seller suites 684 passed.
FRONTEND UNIT: 464 PASS; tsc and eslint clean.
PRODUCTION BUILD: PASS (`next build`, 7428c6a).
KNOWN ENVIRONMENT-ONLY FAILURES:
  - BLOCKED — TEST STORAGE CREDENTIALS REQUIRED: tests/test_receipt_privacy.py::
    test_receipt_locator_never_reaches_an_unauthorized_caller and
    ::test_moderator_receipt_view_is_audited_without_any_locator (real upload to the private
    Supabase bucket). NOT VERIFIED IN THIS CLOUD ENVIRONMENT. Run only these two first once TEST
    credentials exist (CI). Never use production credentials; never weaken the assertions.
  - e2e on the shared, cumulative local DB (not regressions): admin-journeys 14 (165 Super Admin
    fixtures; the test also really demotes its fixture — regenerate fixtures after it),
    back-control "store page's Back" (production-only QA seller row), meeting-0929 B (report
    queue oldest-first pushes the new report pages away).
KNOWN INTENTIONAL FIGMA DEVIATIONS (keep them):
  - Payout: PayPal is the real rail (GCash/Maya simulated only); no "Add bank or e-wallet".
  - Performance: no bookmark / share counts (not recorded).
  - Linked accounts: recorded evidence only (shared network, same payout account); no device links.
  - Affiliate: extra "Needs link" view (the only place links are attached; walkthrough uses it);
    import "Rows" = total + unchanged; Months "Attributed" = net.
  - Products: name parts Line / Variant / Type, each once; Queue tab has no search.
  - Sellers: claim evidence is text only (no attachments stored).
  - People: Filter has Stage only (members-only list per meeting); role changes stay in Users;
    suspension is Super Admin only (owner decision).
  - Search: no Price History / 3D Model links; Ask opens the composer without the product.
  - Activity log: day headers count loaded rows; job runs live in the Jobs card, not the feed.
  - Queue modal: vote ring stated in counts (no per-vote timeline); no "Reused" photo badge.
  - Financial report PDF: "of which absorbed", Honesty Fund "credited to wallets" (correctness).
KNOWN DEMO RISKS:
  - Demo on a freshly seeded TEST/defense DB only: the walkthrough mutates state (votes, Best
    Answer, approvals, claim approval) — re-seed between rehearsals.
  - Review photos on a local DB point at a host that does not exist (DEFENSE_IMAGES cache covers
    the screenshots); on TEST the buckets hold them.
  - Suspension is live and signs a member out: do not suspend a defense persona during a demo.
  - Run-now on money / deletion jobs is Super Admin only; integrity sweep / priority tiers run for
    Administrators and report "already completed" when the period is done (by design).
TEST CREDENTIALS STILL NEEDED: Supabase TEST service-role (storage) for the two receipt tests.
PRODUCTION DEPLOYED: YES (7a2c791).   MAIN MERGED: YES (PR #9; see MERGE STATUS).
NEXT SAFE ACTION: owner review of defense-build-oct6 → re-seed TEST with scripts.defense.seed
  (guarded to TEST/local) → rehearse the 7 scenes → only on explicit owner authorization, promote.

## REMAINING PRIORITY LEDGER (for session 5 — resume at the first open item)

Built from the Figma Screen/* inventory (file lso4Ri4hDaZxvCebhUqlY5, Page 1) on Oct 3 02:40 UTC.
"Defense-ready" is a checkpoint, not the end: continue in this order.

REMAINING HIGH: none known.  REMAINING MEDIUM: none functional.
REMAINING STRETCH: none functional. (A seller chat, B deep People, C linked accounts — recorded
  evidence only, D account switcher (session 3; re-audit vs Figma once), E Activity log jobs,
  F spec builder: done.)

REMAINING LOW — functional Figma gaps, in order:
 1. DONE (session 5) — ADMIN SETTINGS 8076:16388, READ-ONLY. GET /admin/settings (staff; staff
    emails only for the Super Admin): Team (10 most recently active staff by latest audited action —
    no sign-in time is stored; "Manage roles" -> Users for the Super Admin), Earning rules (Wilson
    gate 0.65, min Stage-2 voters 3, split 30/30/40 — the live constants), Payouts (₱300 minimum,
    5th / 1st of the month from the scheduler), Notifications (states honestly that staff email
    alerts are not set up; points at the bell / Needs attention / Jobs card), Integrations
    (affiliate last import, PayPal by hand, PayMongo not built, email provider), Data & privacy
    (IP 30/90 days, telemetry 90, voting network 30, activity log permanent; Export -> activity.csv).
    Rail item is live (no inert items left). Tests: test_admin_settings; admin-console 13/13.
    STILL OWNER DECISION: making earning rules / split / payout days EDITABLE (moves money);
    staff email notifications (needs a sender + per-admin prefs).
 2. DONE (session 5) — ADMIN ANALYTICS 8071:16115. GET /admin/analytics/summary?range=7d|30d|90d|12m
    (services/analytics_summary_service.py; every figure counts recorded rows): KPI tiles vs previous
    period (reviews published, votes, affiliate clicks = sessions.clicked_at, orders = postbacks,
    commission = real commissions), reviews per day / per week with the previous period (SVG bars +
    dashed line, legend, per-bar tooltip, sr-only table), funnel review views (reading sessions) ->
    clicks -> orders -> commission, Moderation (median published->decision, queue, decision mix,
    reports opened/closed/median close), Community (new members, active reviewers, returning
    voters, reviewers by stage), Top products by commission, Where readers are (edge-resolved
    request buckets; no IP), Needs a look (open collusion system reports, photos shared across
    uploaders, under investigation, failed payouts). The old request-location panel stays as a
    collapsible "Request detail by location". Export CSV from the frame NOT built (no owner ask;
    the Activity log and Reports already export). tests/test_analytics_summary.py.
 3a. DONE (session 5) — CONTRIBUTOR HISTORY rebuilt to Screen/History 8098:17238 (was the older
    frame 5762:472): month-grouped wallet ledger from GET /reports/earnings-statement (last 2
    cycles): header Earned in <month> / Paid out + pending note; rows Commission (Pending / Cleared
    / Sandbox test + "QA test earning · not real money"), Order returned (Reversed), Honesty Fund
    share, Payout to PayPal (Requested / Processing / Sent), Payout cancelled / failed (Refunded);
    "All types" filter (?type=); "Showing the last 2 months · Full statement". Commissions sit in
    their CYCLE month (the statement's own period rule), payouts in their date's month. No
    "Request reward" / "Adjustment by Bluntly" rows: no record exists for them. No product photos
    on rows (the statement has none) — type icons instead. components/dashboard/history-model.ts
    (+3 unit tests). EarningItem.tsx removed. e2e: dashboard-navigation (Full statement), qa-payments
    PASS; br-journeys PASS. LOCAL-ONLY failure: qa-round2 QA-027/028 (fixture review not on the
    first page of the recent feed on the cumulative DB).
 3. DONE (session 5) — CONTRIBUTOR STATES:
    - Dashboard/Empty 7855:10383 (9011854): "No earnings yet" mascot card + Write your first review
      when GET /users/me/contributor has_earned=false (no commission and no Honesty Fund credit ever).
    - Payout/No wallet 7855:11265 + Payout/Requested 7855:11171 (204acee): no wallet -> one "Add a
      payout wallet" row, disabled "Request ₱X", "Add a wallet to request your payout". Open request
      and nothing new to add -> ring "Request sent" (one arc: payouts record no commission/fund
      split, so none is drawn), "Payout status" Requested -> Checking · 3–5 days -> Sent to PayPal,
      disabled "Payout requested" + "₱X is locked until it's sent to your PayPal"; money cleared
      since is noted. br-journeys cashout e2e asserts the Requested state after reload.
      No-wallet visual verified on lci_defense (matches 7855:11265).
    - Payout/Details/Error 7855:11365 (bd821ea): field-level errors (red border, aria-invalid,
      message under the field) for missing/malformed email and server validation errors.
      INTENTIONAL DEVIATION: "This name doesn't match your account" needs a provider name check;
      manual PayPal payouts have none.
    - Payout tips 7844:9469 / 7844:9529 / 7843:9501 (0f62146): /dashboard/transfer/answers,
      /honest-reviews, /proof, fed by GET /users/me/payout-tips (caller only; tests
      test_payout_tips 4/4): answers this month, earned from answers (net, no QA money), 3
      unanswered questions in the member's first category; 3★+ -> commission, 2★- -> Honesty Fund
      with the Honesty Score; average earning per review with/without proof (all reviewers, shown
      as counted — the local DB shows WITHOUT higher, so the frame's "get bought from more" claim
      is not made), reviews missing proof with "Add photo" only inside the 72h one-time window.
    - Performance/Choose review 7849:9886 (cb7fe4a): searchable bottom sheet (<dialog>), All
      reviews + count + earned this period, per product thumbnail / earned / latest review date
      (performance products now carry published_at).
    - Dashboard/Loading 7855:10750 (3f6621b): real action cards + grey wallet / chart / ladder frames.
    e2e: dashboard-navigation 3/3 (History, tips, chooser).
 4. DONE (session 5) — ADMIN SECONDARY FRAMES:
    - Queue/AllReviews 8060:15564 (aa5e3f8): Rating column added (star in the site's rating colour,
      grey when no longer published). KEPT on purpose: both Wilson figures, votes, and the "why
      (not) queued" line (QA-requested). Thumbnails / "by author" layout not copied.
    - Payouts/Sent 8085:17825 + Failed 8085:18136 (c2fa217): Sent = Reference + Sent on; Failed =
      Reason + request age (no failure time is stored — not invented). Each tab fetches its own
      statuses (204acee^ fix: Sent used to show 17 of 82); "Showing N of M" when capped.
    - Payouts/HonestyFund 8024:13286 (429f3dc): in the Payouts tab row (PayoutTabs); cards pool /
      cycle closes + distribution day / last distributed; cycles table (pool, contributors, largest
      share, distributed date, Collecting / Distributed / Not distributed). GET
      /admin/payouts/honesty-fund (staff); tests/test_honesty_fund_cycles.py.
    - People Active / Under investigation / Suspended 8085:16380…: match (no change).
    - Mobile Search 6852:641: recents match. INTENTIONAL DEVIATION kept: "Most searched today"
      needs site-wide logging of free-text queries shown to other readers — a privacy/product
      decision (OWNER QUESTION if wanted), not built.
    LOCAL-ONLY e2e failure: review-queue-wilson D (Reports tab loads 50 rows; the cumulative local
    DB has more open reports, so the new system report is off the first page).
 4b. INVESTIGATE OVERLAYS (found session 5 — Figma Overlay/Review/Investigate 8109–8117 and
    Overlay/Answer/Investigate 8129:*, never audited before; functional gap):
    - DONE (c93e613, d57ee5e): GET /admin/reviews/{id}/investigation (staff, read-only;
      services/review_investigation.py, tests 3/3) + modal tabs Summary (adds "If you leave out the
      N flagged votes") / Votes (log-time timeline, first-10-min vs category median, flagged by
      stage, gate with vs without flagged) / Voters (strip of votes on the author's last 20
      reviews, agreement, signals). FLAGGED (this view only) = same network as another voter on
      this review (fingerprints, 30-day retention) OR voting circle (up-voted >= 80% of the
      author's published reviews, min 5). e2e admin-console "investigates" PASS.
    - NEXT: Author tab (8112:17871) + Originality tab (8112:17611); then the Answer overlays.
    - NOT BUILT (honest): "Where votes came from" (no per-vote location is stored);
      "Remove flagged votes" (OWNER DECISION — signals never act; a manual vote-removal power
      changes trust and earnings); receipt checks "product matches / bought before posting / no
      editing traces" (no such checks exist).
 5. DONE (6792a19+1): Payouts ages past 60 days show the date ("oldest requested on 20 Sept
    1985" on polluted local data). Keep out: per-vote timeline + "Reused" badge (no data).
 6. Owner question still open: "Admin-referred" fast-track referral (PRD FR-6).
POST-DEFENSE / EXCLUDED: automated payout execution (PayMongo / PayPal API transfers), device
  fingerprints (never recorded — never shown), production deployment, main merge.

## CENTRAL BRANCH STATE

CENTRAL BRANCH: defense-build-oct6 (the only development branch). main = production (370f702, release 4;
production DB at 0085_email_outbox). Promote to main only on explicit owner authorization. Never
force-push.
LOCAL = REMOTE: YES at each pushed checkpoint
LATEST PUSHED CHECKPOINT: session 12 — see `git log origin/defense-build-oct6` (code 66f36b1 + the
invariant fix and this handoff); migration head 0089_product_import_action (TEST at 0089; production at
0085 — 0086..0089 pending, see SESSION 12 §5).
UNPUSHED COMMITS: 0
UNCOMMITTED FILES: 0

## SOURCES

- Transcript (read in full, both sessions): Drive folder "10/02/2026 Meeting",
  `2026-10-02 18-32-17 - transcript.md` (file id 1wVYy-MTW_NOWp8aNgWJFUV1ad80mfe7U);
  raw timestamps id 1ibHuiUqKcIxFu8AypGHDzYJrYigD1nZQ.
- Figma file key lso4Ri4hDaZxvCebhUqlY5, page "Page 1" (0:1). Sessions 2 and 3 HAVE the connector
  (session 3: it lost its OAuth mid-session — "needs you to sign in again" — and came back after the
  owner reconnected it in claude.ai connector settings; retry get_metadata before giving up).
  Admin frames (node ids): Draft/Admin/Overview v3 7879:10223 · Overlay/Admin/Activity 7881:10289 ·
  Queue: Reviews 7943:11402, Answers 7956:11661, Reports 7949:10664, Support 7943:12025,
  Overlay/Queue/Review 8042:13037, Confirm/Queue/{Approve 8037:13080, AttachLink 8037:13117,
  Reject 8037:13158, TakeDown 8037:13195}, menus Menu/Reviews/Sort 7958:10978, Filter 7958:10988 ·
  People 7998:11693, Person 8005:11974, Activity 8007:12069, Interactions 8007:12991,
  Reports 8007:13917, Moderation 8007:14746, Overlay/Person/Activity 8008:12324,
  Overlay/Person/Relationship 8008:12399 · Payouts 8024:12721, HonestyFund 8024:13286,
  Overlay/Payout/Send 8025:12833, Confirm/Payout/Sent 8025:12896 · Reports 8028:12886,
  Overlay/Report/Generate 8028:13346, PDF pages 8029:12942 / 8029:13078 · Products Catalogue
  7967:11173, Queue 7966:11087 · Sellers Claims 7992:11327, Appeals 7992:11823 · Affiliate
  8015:12542 · Contributor: Screen/Dashboard 7833:9534, Screen/Payout 7840:9380,
  Screen/Performance 7848:9542 · Component library section 7801:9204.
  Before get_design_context, read MCP resource skill://figma/figma-design-to-code/SKILL.md.

## CURRENT TASK

Contributor dashboard (HIGH 6): Screen/Dashboard 7833:9534, Screen/Payout 7840:9380 (Locked
7840:9462, Details 7843:9432), Screen/Performance 7848:9542. Reports (HIGH 5) is DONE (session 3).

## COMPLETED IN SESSION 3

- BACKEND FIRST (owner instruction mid-session; Figma OAuth kept expiring) — APIs ready for the
  three remaining HIGH screens, UI still to build from Figma:
  - Answer flow (HIGH 7): POST /questions/{id}/answers accepts optional structured parts —
    experience, good, bad, recommend (bool), right_for_you, rating (half stars 0.5-5), photo_urls
    (<=4, must be the answerer's own uploads via POST /reviews/photos; `answer_photo_not_owned`).
    NO MIGRATION: stored as labelled lines after the answer's words (services/answer_parts.py, the
    same idea as the question's "Looking for:" line); every AnswerOut now carries `parts` (parsed,
    null for a plain answer) and every QuestionOut `requirements` (the asker's specifics).
    Notifications carry the words, never photo URLs. Tests: tests/test_answer_parts.py.
  - Contributor Payout (HIGH 6): GET /payouts/balance gains withdrawable_commission /
    withdrawable_honesty_fund (pie chart), short_of_minimum (Locked state), in_flight,
    payout_account_masked (Details). payout_service.member_breakdown. tests/test_payout_member_breakdown.py.
  - Contributor Performance (HIGH 6): GET /users/me/performance?product_id=&period=week|month —
    product switcher list, per-bucket views / helped / earned / returned, totals funnel.
    contributor_dashboard.performance; tests in tests/test_contributor_dashboard.py.
  - Affiliate (MEDIUM 11) backend: GET /admin/affiliate/transactions (platform/status/q, paged,
    status counts), /admin/affiliate/months (per marketplace + cycle month: commissions, earned,
    reversed, net, remitted), /admin/affiliate/imports (the csv_import audit rows, newest first) and
    /admin/affiliate/imports/{log_id} (summary + the rows that file last wrote). No migration.
    services/affiliate_admin_service.py, schemas/affiliate_admin.py, tests/test_affiliate_admin.py.
  - Sellers (MEDIUM 10) chat: GET/POST /api/v1/cases/{claim|appeal}/{id}/messages — the filer
    (claimant / appellant) and staff only (403 otherwise); a staff message notifies the filer
    (kind case_message). Stored per case in platform_settings `chat:<kind>:<id>` (row-locked,
    capped 200): NO MIGRATION. services/case_chat_service.py, routes/case_chat.py,
    tests/test_case_chat.py. Claims already carry DTI/SEC number, business name, shop name, evidence.
  - Frontend types/fetchers ready: lib/qa.ts (AnswerParts, requirements), lib/dashboard.ts
    (PayoutBalance fields, getPerformance).
  - Products queue (MEDIUM 9): GET /admin/products/queue?sort=oldest|newest — pending submissions
    with submitter (+ trust stage), link preview read from the URL only (host, known marketplace,
    https; a look-alike host is not a marketplace), age, review count. services/product_queue_service.py.
  - Products (MEDIUM 9) Edit modal backend: MIGRATION 0071_product_specs (nullable JSONB
    `products.specs`, additive; branch head is now 0071). POST /products/{id}/canonicalize also
    stores the name parts (line / key_spec / descriptor — before, only brand was kept) and takes
    `specs: [{label, value}]` (<=12, one value per label, no links; omitted = unchanged, [] =
    clear). Every ProductOut now carries brand, line, key_spec, descriptor, specs.
    tests/test_product_specs.py; docs/ADMIN_SUPERADMIN_MIGRATION.md §5a lists 0071.
  - Mobile search product switcher needs NO new backend: GET /products?q=&browse=true (matches,
    most-reviewed first) + GET /reviews/feed?product_id=&sort=wilson&limit=1 (its top review).
- Queue Answers count: admin read is uncached, up to 100 threads (count = list shown).
- Duplicate h2 removed on Activity log and Products. Permission matrix lists the new staff endpoints.
- Production `next build`: PASS (session 3, after the Reports + Dashboard checkpoints).

- Contributor dashboard (HIGH 6, part 1) per Figma Screen/Dashboard 7833:9534 (meeting 3:00-5:20):
  - Backend `app/services/contributor_dashboard.py` + GET /api/v1/users/me/contributor?period=week|month
    &reach=this|last (caller only, no id in the path): wallet total / commission / Honesty Fund (fund
    credits capped at the balance; payouts counted against commission first) / pending (= clearing,
    not withdrawable yet); earned vs returned per day (7) or per week (4), Honesty Fund credits count
    as earned; best performing (top 3 reviews in the window: views, people helped, earned); trust
    ladder with the NEXT stage's real requirements (services/trust.py thresholds: receipt reviews,
    voter evidence "Helpful votes", helpfulness, best answers / no strikes / months active) and
    `held_for_review` when all are met but the vote-concentration check holds the promotion (jomar);
    Honesty Score = reputation_score (as on profiles; copy says "Shown on your reviews and profile",
    NOT "sets your share of the Honesty Fund" — the fund formula is undefined); reach funnel views ->
    people helped -> link clicks -> purchases, this month so far vs the same days of last month.
  - Frontend: components/dashboard/ContributorDashboard.tsx (+ DashboardSelect, contributor-model.ts),
    app/dashboard/page.tsx rebuilt on it (white page at every width; SiteHeader from md, the frame's
    NavBar below md via DashboardNav tone="light"); Payment history (#history), "Your reviews" and
    "Answers" (?tab=answers -> AnswersPanel, owner round 4) kept below. Wallet card assets in
    public/figma/dashboard/ (swoosh decor + mark + 4 reach rings, downloaded from the frame).
    New token --status-high-bg (#fbede3). Loading skeleton redrawn.
  - Old `ReviewerDashboard` component is now only used for its AnswersPanel export (candidate cleanup).

- Reports (HIGH 5) per Figma Screen/Admin/Reports 8028:12886, Overlay/Report/Generate 8028:13346,
  PDF/Financial report 8029:12942 + 8029:13078 (meeting 18:06 and 29:16), all on real ledger data:
  - Backend `app/services/reporting/financial.py`: Revenue & split (earned / reversed / absorbed /
    net; Bluntly, Reviewers, Honesty Fund = stored shares summed; QA test money excluded), By
    marketplace (orders = commissions + orders recorded in the period that earned none), Money in
    (remittances received in the period vs attributed; shortfall; period cycles "Clearing"), Money out
    (payouts sent = paid out; to send / failed / cancelled; Honesty Fund credits listed, NOT added to
    paid out — they go to wallets and leave when wallets are paid), Liabilities AS OF GENERATION
    (cleared in wallets, payouts to send, still clearing, unattributed sales).
  - Periods gain QUARTER (`quarter` + `year`, kind "quarter", label "Q3 2026", slug "2026-Q3").
  - Routes (staff = Administrator + Super Admin, `require_report_staff`):
    GET /api/v1/admin/reports/financial?month&year | quarter&year | year | start_date&end_date;
    POST /api/v1/admin/reports/financial/generate {kind month|quarter|year|custom, …, sections[]};
    GET /api/v1/admin/reports/financial/history; GET …/financial/history/{id}/pdf (attachment).
  - PDF `financial_pdf.py`: ReportLab canvas (NEW DEPENDENCY reportlab>=4.2,<5 in pyproject, BSD),
    A4 = Figma 595x842 pt, Poppins + one-glyph DejaVu subset for ₱ (Poppins has no ₱), the `bluntly`
    wordmark with the swoosh in the head (owner: "logo dapat ang bluntly ... swoosh"), page flow with
    continued tables, "Page n of N". Assets + licences: backend/app/assets/report/ (package-data set).
  - History: logged in platform_settings key `financial_report_log` (newest 24) WITH the report's
    figures, so Download re-renders the same document. NO MIGRATION.
  - Frontend: /admin/reports is the Reports screen (components/admin/reports/ReportsScreen.tsx):
    month dropdown, Generate report, Net commission split card, Money in / Money out / Still owed
    cards, generated-reports table (Download on row hover/focus). GenerateReportDialog.tsx (560px):
    Month/Quarter/Year/Custom chips, select or two dates, four section switches, "Figures as of now,
    Manila time.", Cancel / Generate PDF -> POST, download starts, list refreshes.
  - The CSV reports (Honesty Fund, Commissions & Payouts, Seller Ratings) are now shell tabs of the
    Reports section (AdminNav SECTION_TABS); the in-page ReportTabs component was removed.
  - Verified in a browser (local stack, Super Admin): screen, dialog, Generate -> 2-page PDF
    downloaded (bluntly-financial-report-2026-09.pdf), history row shown.
- Deviations from the Figma PDF template, all for correctness (documented in docs/REPORTING_MODULE.md):
  "Absorbed" printed as "of which absorbed" (it is part of Reversed; the template's net already
  excluded it); Honesty Fund line says "credited to wallets" and is not in "Paid out"; Liabilities
  say "As of <generation time>" (no balance history exists); Rate = each share's actual % of net.

## COMPLETED THIS SESSION

- Overview (HIGH 2) per Figma 7879:10223, all on real data:
  - Review queue card: tabs Earn eligible / Flagged / First review / New product with the 5 most
    urgent cards each (new GET /admin/analytics/queue-preview; membership = the existing Overview
    breakdown rule, test asserts the counts agree).
  - Needs attention card on GET /admin/analytics/needs-attention, every row a quick link.
  - Affiliate earnings card: verified vs returned per month (1M = 4 weeks, 6M, 1Y), delta vs the
    previous equal period, returned %, absorbed (unrecovered), pending orders by marketplace
    (new GET /admin/analytics/affiliate-earnings over affiliate_postbacks).
- Shell + navigation (MEDIUM 14, done early because every admin frame uses it):
  - Rail per Admin/Sidebar: Overview; Moderate (Queue, Special routing [Super]); Manage (Products,
    Sellers, People); Money (Affiliate, Payouts, Reports); footer Analytics, Activity log,
    Settings (inert, says why). Pills from needs-attention (Queue = sum of moderation rows, red when
    reviews are past due).
  - Merged sections keep their old routes as tabs under the top bar: Products (Catalogue, Prices),
    People (Reviewers, Users [Super Admin only]), Payouts (Payouts, Honesty Fund, QA payments).
  - Workspace menu ("Bluntly Admin" caret): Home / Feed and Log out (meeting decision; no add user).
  - Quick actions (⌘K) popover; top-bar search (opens All reviews with `aq`); activity bell per
    Overlay/Admin/Activity (GET /admin/activity, receipt_view excluded, per-browser "Mark all seen").
  - The shell renders the page h1 (visible 24px title; sr-only on the Overview).
- Queue (HIGH 1) per Figma 7943:11402 / 7956:11661 / 7949:10664 / 7943:12025 / 8042:13037:
  - Segmented views Reviews / Answers / Reports / Support with counts; the page title follows the
    view (Review / Answer / Report / Support Queue); "Queue" switch = queue vs All reviews.
  - Reviews: full-width table (Review, Level, Rating, Earnings path, Evidence, Priority tier, Age red
    when overdue), sort menu, filter menu (tier/band/SLA/lane/edited-after-link chips with server
    counts, Clear all), search popover, pagination + per-page. Row opens the review MODAL: header
    (tier, earning path, prev/next "i of N", J/K), author card, review, engagement, checks passed,
    problems that fired (voting ring with reciprocal counts, vote spike, copied text, open reports,
    edited after link), why-this-tier, history + "Open person" (/admin/people/<id>). Footer: Take
    down / Restore, keyboard hints (A, L, R, J/K), Reject earnings, Approve & attach link, Approve
    earnings — each through a Confirm dialog (ConfirmDialog.tsx) on the existing endpoints.
    `?open=<review id>` opens the modal (looked up across the queue when not on the page).
  - Answers: Question / Asked by (trust) / Answers / Best answer (author, trust) / Asked; the thread
    opens in a modal. Backend: QuestionOut.best_answer_by (additive; only the asker's recorded pick).
  - Reports: Open/Resolved/All dropdown (new `rstatus` -> API `status`), tier/sort controls, table
    Reported / Reason (+ member note) / From (member or System) / Reports / Priority / Filed; the
    report, its evidence panel and the decision open in a modal.
  - Support: Waiting/Closed/All dropdown, table Request / Category / Handled by / Status / Updated;
    the request and its response form open in a modal.
  - Removed now-dead code: ReviewDecision.tsx and the old side panel (logic moved to
    queue/QueueDecisionBar.tsx; same endpoints and rules).
- People (HIGH 3 + MEDIUM 12) per Figma 7998:11693 / 8005:11974 / 8007:12069 / 8007:12991 /
  8007:13917 / 8007:14746:
  - GET /api/v1/admin/people/{id}?range=1M|6M|1Y (staff; services/person_investigation_service.py):
    votes per day + spike (>= 5 votes and >= 3x the median day), interactions per other member
    (up/down/comments given, up-votes returned, same-day mutual up-votes, share of votes,
    RECIPROCITY = 2*min(a,b)/(a+b)), activity with exact links (/reviews/<id>,
    #comment-<id>, /questions/<id>#answer-<id>), reports filed/received with outcome, staff
    moderation history (receipt_view excluded), earnings (lifetime earned; pending = clearing +
    in flight, from the earnings statement), LINKED ACCOUNTS only from recorded links: shared
    keyed network hash (vote_network_fingerprints, 30 days) and identical payout account (the
    destination is never returned). No device data exists; none is shown.
  - /admin/people/[id]: header (status Investigating/Suspended/Active, level, @username, USR ref,
    role, joined), Open profile, Actions (investigation toggle); views Overview (votes chart with
    1M/6M/1Y, top interactions + "X% of votes go to 3 people", recent activity, signals incl.
    linked accounts), Activity, Interactions (+ relationship modal), Reports, Moderation.
  - People list (/admin/reviewers, tab "Members"): All / Active / Under investigation / Suspended
    with counts, search, members only (GET /admin/reviewers?scope=members: no staff, no claimed
    sellers, per the meeting), each row opens the investigation. Endpoint change is additive.
- Payouts admin (HIGH 4) per Figma 8024:12721 / 8025:12833 / 8025:12896: views To send / Sent /
  Failed + Honesty Fund + QA payments links; cards To send (total, count, oldest), Sent in <month>,
  Waiting in wallets (new GET /admin/payouts/summary; wallet less uncleared, the §19 rule);
  table Reviewer / Amount / Send to (masked) / Requested / Scheduled; Open -> Send payout modal
  (full address + Copy, requested, payout ID, Transfer reference) -> Mark as sent -> Confirm ->
  existing mark-paid. Cancel payout (refund) and Mark failed (reason) confirm dialogs; Failed view
  has Retry. "Process requests" (PayPal API batch) shows ONLY when the API is configured — no
  automated payout execution was built. AdminPayoutOut gained display_name/trust fields
  (additive). PayoutsConsole.tsx deleted (replaced by components/admin/payouts/PayoutsScreen.tsx).
- Owner question answered from Figma: the queue has NO "Earnings" tab. Tabs are Reviews / Answers /
  Reports / Support; "Earnings" is a COLUMN of the Reviews table (Commission / Honesty Fund /
  Super Admin / Taken down).

## STATUS MAP

### HIGH
1. Review / Admin Queue — DONE (this session). Not built from the frame: the per-vote timeline
   chart in the modal (needs vote timestamps the queue card does not serve; the ring is stated in
   counts instead) and "Reused" photo badges (single photo_url per review).
2. Admin Overview — DONE (this session).
3. Collusion / investigation demo path — DONE for the defense walkthrough: queue modal (voting
   ring counts) -> Open person -> Interactions (reciprocity %, same-day mutual votes, same
   network) -> relationship modal. The seeded scenario (local seed) shows Jomar Aquino under
   investigation with 5 accounts at 28.6% reciprocity. NO device data exists.
4. Payouts — admin DONE (manual flow per Figma). Contributor payout screen (Screen/Payout
   7840:9380, Locked 7840:9462, Details 7843:9432) still to do with the contributor dashboard.
5. Reports — DONE (session 3): screen + Generate dialog + branded PDF + history; CSV tabs kept.
6. Contributor dashboard — PARTIAL: Dashboard DONE (session 3); Payout + Performance screens next.
   7. Answer / Q&A flow — PARTIAL. 8. RBAC — DONE (model kept;
   Super Admin-only items/tabs hidden for Administrators, APIs still refuse).

### MEDIUM
9 Products DONE · 10 Sellers DONE (incl. claim/appeal chat) · 11 Affiliate DONE · 12 People DONE (list + sort/filter, investigation, Actions menu with Super Admin suspend; role changes stay in Users) ·
13 Search/user-side DONE (mobile product bar + Switch sheet + question match) · 14 Navigation DONE (this session).

### APPROVED STRETCH
A seller chat DONE (with MEDIUM 10) · B deep people interactions DONE (Reports scope; device links never — no data) · C account switcher DONE
(Home/Feed + Log out) · D top-bar / job indicators DONE (Activity log: Scheduled jobs + Run now, today by type) ·
E flexible spec builder DONE with MEDIUM 9 (Edit / Add-to-catalogue modal per 7970:11204: name parts Line / Variant / Type, specs with In-name, Saves as; repeating a part kind would need new storage and no frame shows it).

### LOW / POST-DEFENSE
Automated payout execution; cosmetic animations; extra analytics; unrelated refactors.

## FILES CHANGED (session 3)

- backend/app/services/reporting/financial.py, financial_pdf.py (new); periods.py (quarter)
- backend/app/schemas/reporting.py (Financial* schemas), backend/app/api/v1/routes/reporting.py (4 routes)
- backend/app/assets/report/* (Poppins TTFs + OFL, DejaVu ₱ subset + licence, wordmark PNG, README)
- backend/pyproject.toml (reportlab dependency, package-data), backend/tests/test_financial_report.py (new)
- app/admin/reports/page.tsx (the Reports screen), app/admin/reports/layout.tsx (tabs moved to shell)
- components/admin/reports/{ReportsScreen,GenerateReportDialog}.tsx, financial-model.ts (new)
- components/admin/AdminNav.tsx (Reports SECTION_TABS); components/reports/ReportTabs.tsx (deleted)
- lib/moderation.ts (getFinancialReport, getFinancialReportHistory + types), lib/site-map.ts,
  docs/SITEMAP.md, docs/REPORTING_MODULE.md (Report 5), docs/openapi.json + lib/api-types.d.ts
- tests/frontend/financial-report-model.test.mjs (new), e2e/reporting-journeys.spec.ts (test 3)

## FILES CHANGED (session 2)

- backend/app/services/overview_panels_service.py (new), referral_service.py (open_queue_cards)
- backend/app/api/v1/routes/admin_analytics.py (queue-preview, affiliate-earnings)
- backend/tests/test_overview_panels.py (new, 9 tests)
- app/admin/layout.tsx, app/admin/page.tsx, app/tokens/colors.css (status-critical tokens)
- components/admin/AdminNav.tsx, AdminShell.tsx (rewritten), AdminActivityMenu.tsx, AdminSearch.tsx,
  components/admin/overview/{ReviewQueueCard,NeedsAttentionCard,AffiliateEarningsCard}.tsx (new)
- components/admin/AdminOverview.tsx (deleted; replaced by the cards)
- lib/moderation.ts (fetchers), docs/openapi.json + lib/api-types.d.ts (regenerated, additive)
- e2e/admin-journeys.spec.ts, tests/frontend/roles-model.test.mjs (new rail labels)
- Queue: components/admin/ReviewQueueScreen.tsx (rewritten render), queue/{QueueCells,
  QueueReviewsView,QueueReviewModal,QueueDecisionBar}.tsx, ConfirmDialog.tsx, AdminModal.tsx,
  QaAnswersTab.tsx, SupportQueue.tsx, review-queue-model.ts (rstatus), qa-answers-model.ts,
  app/admin/review-queue/page.tsx (?open), ReviewDecision.tsx (deleted)
- backend/app/schemas/qa.py, services/qa_service.py (best_answer_by), tests/test_qa_best_answer_by.py
- e2e: review-queue-wilson, meeting-0929, defense-walkthrough updated to the table + modal flow
- People: backend/app/services/person_investigation_service.py, routes/admin_people.py (new,
  registered in router.py), routes/admin_console.py (reviewers: scope/status/q/counts, additive),
  tests/test_person_investigation.py; app/admin/people/[id]/page.tsx,
  components/admin/people/PersonInvestigation.tsx, app/admin/reviewers/page.tsx (People list),
  lib/site-map.ts + docs/SITEMAP.md, e2e/br-journeys.spec.ts (investigation via Actions menu)

MIGRATIONS: none.

## TESTS RUN (session 3)

- FULL BACKEND SUITE (first time on this branch): 2876 passed; 5 Q&A source-inspection tests
  failed only because qa_service.py was edited during the run (re-run: 6/6 pass); 2 receipt-privacy
  tests need Supabase service-role credentials (absent locally: environmental, not a regression).
- Backend-first checkpoint: test_answer_parts (5) + Q&A suites 116 passed; payout breakdown +
  payouts API 24 passed; contributor dashboard + performance 8 passed; openapi contract 9 passed;
  tsc PASS. Production `next build` PASS.

- Dashboard checkpoint: pytest test_contributor_dashboard (6) + openapi contract + seller dashboard +
  trust level names: 31 passed · ruff PASS · tsc PASS · eslint PASS · test:frontend 451 passed ·
  browser: /dashboard at 390px and 1280px for mariareyes and jomar_deals (held), no sideways scroll.

- pytest test_financial_report (10, DB) + test_reporting_api + test_reporting_units +
  test_openapi_contract + test_payout_summary: 72 passed (local Postgres 17)
- ruff (changed backend files): PASS · npx tsc --noEmit: PASS · eslint (changed files): PASS
- npm run test:frontend: 445 passed (437 + 8 new)
- Browser (playwright-core + /opt/pw-browsers/chromium, local stack): Reports screen, dialog,
  Generate PDF download (2 pages), history row, shell tabs. PDF rasterised and compared with
  Figma 8029:12942 / 8029:13078.

## TESTS RUN (session 2)

- ruff (changed backend files): PASS
- pytest test_overview_panels, test_needs_attention, test_admin_overview, test_openapi_contract:
  62 passed (DB tests on local Postgres)
- npx tsc --noEmit: PASS · eslint (changed files): PASS · npm run test:frontend: 437 passed
- Checkpoint 2: pytest (openapi contract, qa authz/gaps/search, best_answer_by, overview, needs
  attention): 85 passed · eslint app components lib: clean · tsc: PASS · test:frontend 437 passed ·
  ruff app tests: PASS · visual check of all four queue views, the review modal and Confirm dialog.
- Checkpoint 3: pytest test_admin_console + test_person_investigation + openapi contract: 21
  passed · ruff app tests: PASS · tsc: PASS · eslint app components lib: clean · test:frontend
  437 passed · visual: people list, person overview, interactions.
- Checkpoint 4: pytest payouts_api, qa_sandbox_payouts_api, internal_cron, scheduler_financial_safety,
  qa_authz, openapi contract: 84 passed; test_payout_summary: 2 passed · ruff · tsc · eslint ·
  test:frontend 437 passed · visual: payouts table + Send payout modal. e2e qa-payments updated.
- Visual: local stack (uvicorn + next dev, local DB seeded with scripts.defense.seed) screenshots of
  /admin and /admin/payouts at 1280x832 match the Figma structure.

## E2E (session 3, local stack, `next dev` + uvicorn, fixtures from scripts.e2e_fixtures)

Run with a LOCAL config override (not committed; this Playwright 1.62 expects browser build 1234,
the container has /opt/pw-browsers/chromium): projects=[chromium with launchOptions.executablePath
"/opt/pw-browsers/chromium"]; env E2E_FIXTURES=<json> E2E_API_URL=http://localhost:8000.
- PASS: reporting-journeys, owner-round4 (dashboard Answers), dashboard-navigation (23 passed);
  admin-journeys 1-10 + review-queue-wilson after fixing stale selectors (rail "Queue" link name now
  includes its count pill; two "Refresh" buttons on All reviews; the shell's top-bar search is a
  `search` landmark on every admin page -> assertions scoped to `main`).
- Fail ONLY on a cumulative local DB (fine on a fresh one): admin-journeys 11-13 (each fixture run
  adds another identically titled 2.5★ item); meeting-0929 B (rsort=oldest puts the new report
  beyond page 1; there is no "newest" report sort). Re-seed fixtures before each re-run.
- PASS after re-seeding fixtures: br-journeys "a vote is counted" (the earlier failure was a
  consumed-fixture run artifact); qa-payments (rows are now found by the tester's /admin/people link
  instead of their display name, which several payout rows share on a cumulative DB).

## TESTS RUN (session 3, Figma-reconnected checkpoint ~17:40 UTC, HEAD after 673d1cf)

- Full backend suite: 2898 passed, 0 failed (tests/test_receipt_privacy.py excluded: needs
  Supabase service-role credentials, environmental).
- Production `next build`: PASS (compiled successfully).
- Frontend unit tests: 456 passed. tsc + eslint clean on changed files.
- e2e (local stack): qa-payments, br-journeys cashout, qa-round2 QA-016: PASS.
- Browser: Payout met / locked / details (Change -> Save), Performance, answer flow 1-7 -> posted.

## TESTS NOT RUN

Full Playwright suite in one run (specs were run individually above); visual check of the Figma
screens still to be built (Payout, Performance, answer form). Full backend suite (2876 passed, only
Supabase-credential failures) and `next build` DID run in session 3.

## LOCAL ENVIRONMENT (the container is fresh each session)

- Session 3 container: PostgreSQL 17 was ALREADY ONLINE on port 5433 (PGHOST=127.0.0.1,
  PGPORT=5433 in the env); PG 16 on 5432 was down. Roles/db were created on 5433 via the socket:
  `su postgres -c "psql -h /var/run/postgresql -p 5433"`, and
  `DATABASE_URL=postgresql+psycopg://bluntly:bluntly@localhost:5433/lci`. Python: /root/.local/bin/python3.12.
  Editable install leaves backend/build and backend/*.egg-info: never commit them (added to
  .git/info/exclude locally).
- Python 3.12 venv: `uv venv -p /usr/bin/python3.12 <dir>/venv`, then FROM backend/:
  `VIRTUAL_ENV=<dir>/venv uv pip install -r requirements-dev.txt` and `uv pip install -e .`
  (requirements.txt installs `.` relative to the cwd; run it from backend/).
- Postgres: this container had only PG 16 (port 5432): `pg_ctlcluster 16 main start`. Roles:
  `create role bluntly login superuser password 'bluntly'; create role anon nologin; create role
  authenticated nologin; create role service_role nologin; create role supabase_admin nologin;`
  then `createdb -O bluntly lci` (as postgres).
- Env: `DATABASE_URL=postgresql+psycopg://bluntly:bluntly@localhost:5432/lci APP_ENV=development
  USE_SUPABASE=false BLUNTLY_TEST_ENV=1`; `python -m alembic upgrade head` (head = 0070).
- After any API change: `python -m scripts.export_openapi` (in backend/) then `npm run gen:api`.
- Local demo data (LOCAL DB ONLY; the script refuses anything but local/test):
  `python -m scripts.defense.seed`.
- Local UI check: uvicorn on :8000, `API_URL=http://localhost:8000 npx next dev -p 3000`; login is
  OTP, so set cookie `bluntly_session` to a token from `app.core.security.create_access_token`.
  The Playwright MCP needs /opt/google/chrome (absent): drive playwright-core with
  executablePath /opt/pw-browsers/chromium instead.

## KNOWN BUGS

- None open. (Resolved: the queue's Answers count now reads the uncached admin list; the doubled
  section headings are gone with the redesigned pages.)

## BLOCKERS

None.

## OWNER DECISIONS

- RESOLVED (owner, Oct 3): account suspension stays exactly as built — Super Admin only, member
  accounts only, never self, reason required, suspend / reinstate audited (actor, target,
  reason, time), reversible, suspended member cannot sign in and their votes stop counting while
  suspended. Do NOT extend it to Administrators.

- Central branch: RESOLVED (defense-build-oct6). Figma before UI: RESOLVED (connector loaded).
- RESOLVED from Figma: no Earnings tab; Earnings is a Reviews-table column.
- OPEN: admin fast-track "Admin-referred" referral (PRD FR-6) — not built; not blocking.

## OPERATIONS

- Researchers seed on the live site daily: never truncate or reset shared data.

## HIGH 8 — RBAC SWEEP: PASS (session 4, ~23:05 UTC)

tests/test_rbac_sweep.py (5) reads the routes from the app, so new routes are swept too:
- every /api/v1/admin route (82: 74 staff, 8 Super Admin) carries a staff or Super Admin guard
  in its dependency tree (none relies on the service alone);
- every role-guarded route anywhere: signed out -> 401, member -> 403, a claimed store's owner
  -> 403; an Administrator -> 403 on every Super Admin route (role changes, membership tiers,
  user management, special routing);
- store owners isolated: another store's owner / a member get 403/404 on a store's dashboard,
  rating summary and support requests; signed out 401;
- money is the caller's own: payouts/balance, payouts, contributor, performance, earnings,
  earnings statement take no user id; another reviewer's statement is staff-only (403).
Plus existing tests/test_qa_authz.py (ownership sweep) and the Q&A thread tests (self votes,
reply removal by author/staff). Frontend: /admin layout requireStaff (server); Users and
Special routing render SuperAdminOnly server-side for Administrators. NO DEFECTS FOUND.
HIGH 1-8: ALL DONE.

## MEDIUM 9 — PRODUCTS: DONE (session 4)

Figma: Queue 7966:11087, Catalogue 7967:11173, Overlay/Product/Edit 7970:11204, Overlay/Product/
Catalogue ("Add to catalogue", with Merge into) 7970:11467.
Backend (c00fc14): GET /admin/products/catalogue (q / category / sort / limit / offset; aliases,
  approved price trend <= 8 points + latest, catalogue_count + queue_count); spec `in_name`
  (joins the canonical name, kept on a rename without specs); DELETE /products/{id}/aliases
  (audited) + MIGRATION 0074_alias_remove_action (enum value; no-op downgrade, registered).
Frontend: app/admin/products/page.tsx -> components/admin/products/ProductsScreen.tsx (tabs with
  counts, sort / category filter / search panels, tables, Edit on hover, pagination + page size,
  URL-driven) and ProductEditModal.tsx (both modals: photo, brand, category, name parts Line /
  Variant / Type -> products.line / key_spec / descriptor, Also known as chips add/remove, specs
  with In name switch, Saves as, Merge into -> attach). product-edit-model.ts (+ tests).
  Old ProductCatalogueActions removed. Older products without stored parts: Line = name minus brand.
Deviations: the name-part kinds are the three the catalogue stores (Line, Variant, Type), each once
  (the frame's free part list would need new storage). The Queue has no search (frame: sort only
  is meaningful there; filter/search icons show on Catalogue).
Tests: product specs/catalogue/alias tests, product-edit-model (4); e2e figma-parity QA-001 and
  br-journeys alias PASS (both now go through the modals); defense-walkthrough product step
  rewritten for the modals — PASS later (see DEFENSE WALKTHROUGH).

## MEDIUM 10 — SELLERS: DONE (session 4, ~23:50 UTC)

Figma: Claims 7992:11327, Appeals 7992:11823 (+ their Review modals with the case chat).
Backend (63de465): admin claim / appeal lists carry the context the modals show (claimant
  PersonCell fields, platform, store URL; appealed review rating / title / text / date / reviewer).
  Chat kind `appeal-reviewer`: the admin <-> reviewer thread of an appeal. The admin's first message
  there IS the substantiation request (status -> substantiation_requested); the reviewer's first
  reply IS the substantiation. Uphold ("Remove review") refuses 422 reviewer_not_asked until the
  reviewer was asked. No migration.
Frontend: app/admin/sellers/page.tsx -> components/admin/sellers/SellersScreen.tsx (Claims /
  Appeals tabs with counts, tables per frame, Review on hover, ?tab=&page= pagination, 10 a page,
  oldest first) and CaseChat.tsx. Review claim modal: registration / business / shop-name match,
  claimant, evidence, chat with the claimant, Reject / Approve -> confirm. Review appeal modal:
  appealed review card, seller's reason, reviewer status, Seller / Reviewer chat tabs, Dismiss /
  Remove review (locked until asked) -> confirm. Old SellerClaimDecision / SellerAppealDecision
  and the unused getPendingSellerClaims / getOpenSellerAppeals removed.
Deviations: evidence is text only (no files/attachments are stored). No in-screen search (none
  in the frame). Pager: windowed pages, arrows and 10/25/50 per page (added later in session 4).
Also: next.config `devIndicators: false` — the dev-only Next badge sat exactly on the admin mobile
  nav button and blocked e2e taps in `next dev`. e2e fixtures: routing titles now carry the run tag;
  br-journeys payout uses a per-run cycle month (a cycle can be recorded once).
Tests: tests/test_case_chat.py (reviewer thread, claims context); frontend unit 464 PASS; e2e
  br-journeys 26/26 PASS incl. appeal (Reviewer thread ask -> buyer answers) and DTI claim approval
  via the modal; admin-journeys PASS except 14 (see below); 16 (phone) PASS after the badge fix.
  defense-walkthrough Sellers step rewritten for the modal — PASS later (see DEFENSE WALKTHROUGH).
KNOWN LOCAL-ONLY FAILURE: admin-journeys 14 "last Super Admin cannot be demoted" cannot pass on
  the cumulative local DB (165 super_admin rows from fixture runs, so the guard correctly does not
  fire and the fixture Super Admin really is demoted; regenerate fixtures after it). Passes on a
  fresh DB. Not a regression; not changed.

## MEDIUM 11 — AFFILIATE: DONE (session 4, ~00:30 UTC Oct 3)

Figma: Screen/Admin/Affiliate 8015:12542 (Transactions), Months 8015:13183, Imports 8015:13726,
  Overlay/Affiliate/Import 8017:12742, Overlay/Affiliate/Remittance 8017:12816, proposed Sort
  8019:12729 / Filter 8019:12742 / Search 8019:12873.
Backend (4bc36d4 + this checkpoint): GET /admin/affiliate/transactions now returns `reviewer`
  (the review author, QAAuthor shape; None = unattributed) and `updated_at` (latest of imported /
  completed / returned); new params sort (newest|oldest|commission_desc|commission_asc),
  settlement, attribution (attributed|unattributed), updated (7d|30d|year); `facets` = chip
  counts per filter group under the search. Months return up to 600 rows. No migration.
Frontend: app/admin/affiliate-links/page.tsx -> components/admin/affiliate/AffiliateScreen.tsx
  (tabs Transactions / Months / Imports with counts, Ledger + Order status + Settlement panel from
  the Overview's affiliate block, Sort / Filter chips / Search panels, tables per frames,
  pagination + page size, URL-driven), AffiliateModals.tsx (Import report: file -> dry-run
  preview -> Apply import; Record remittance from a Clearing month row, live shortfall),
  AwaitingLinks.tsx, lib/affiliate-admin.ts. Old AffiliateReportImport / RemittanceForm removed.
Deviations: a 4th view "Needs link" (?tab=links, only while reviews wait) keeps attaching
  affiliate links to approved reviews — the only place in the app that does it, used by the
  defense walkthrough and the Overview's "needs link" item (now linked to it). Import modal "Rows"
  shows total + unchanged (the importer does not split new vs updated). Imports tab shows the
  latest 200. Months: "Attributed" = net (earned - reversed) of the cycle; remittance is recorded
  only from a month row (no free-form month).
Also fixed: two sr-only elements on /admin escaped to the document (AdminNav inert item,
  AdminSearch label) -> `relative`; admin-console spec's stale expectations (Sellers is live,
  Overview has no #admin-kpis, queue pagination nav is "Pages").
Tests: test_affiliate_admin (3, new: reviewer/facets/filters/sort); frontend unit 464 PASS (site
  map regenerated); e2e br-journeys 26/26 (remittance via Months -> Record on the fixture's
  per-run cycle `remit_cycle`), reporting-journeys PASS (rows scoped to the run's user),
  admin-console 13/13 PASS (needs E2E_MODERATOR_TOKEN). Browser: all views + both modals checked
  (import preview of a seeded Shopee report: 118 rows, 116 recognised; nothing applied).
  defense-walkthrough affiliate stop now /admin/affiliate-links?tab=links — PASS later.

## MEDIUM 12 — PEOPLE MANAGEMENT: DONE (session 4, ~00:55 UTC Oct 3)

Figma: Screen/Admin/People 7998:11693 (+ Active / Under investigation / Suspended 8085:*),
  Menu/People/Sort 7999:11850, Menu/People/Filter 7999:11860, Menu/Person/Actions 8010:12514.
Backend (7c6d84c): NEW PUT /admin/people/{id}/suspension {suspended, reason} — SUPER ADMIN ONLY
  (same owner model as role changes; the permission matrix had "none in the API"). Reason
  required (3..1000), audited as moderation_logs `suspend` / `restore` (target_type user);
  member accounts only (staff -> 422 staff_account: demote in Users first); never yourself (422);
  recomputes the trust of members they voted for; the existing auth check refuses a suspended
  token. GET /admin/reviewers: sort (published|newest|oldest), stage (0..5) filter, `stages`
  counts per stage (scope=members). No migration. docs/ADMIN_PERMISSION_MATRIX.md row updated.
Frontend: People list (app/admin/reviewers/page.tsx) gains Sort and Filter (Stage chips with
  counts, Clear all) menus, URL-driven, kept with the inline search. Person page Actions is now
  the Figma menu (components/admin/people/PersonActions.tsx): Mark / Clear investigation (staff)
  and Suspend / Reinstate account (Super Admin; locked with "Super Admin only" for Administrators,
  "change the role in Users first" for staff) -> confirm with reason. Moderation tab labels a
  user-target restore "Account reinstated".
Deviations: Filter has Stage only — Status is the tabs, and Role is moot because the meeting
  limited People to members (no staff, no claimed sellers); the Users tab keeps role changes.
Tests: tests/test_people_management.py (2: RBAC member/admin 403, reason 422, suspended token
  refused, reinstate, audit actions, self/staff/404; sort + stage + counts); rbac sweep +
  person investigation PASS; frontend unit 464 PASS; e2e br-journeys 14/14 (Actions menu:
  investigation; Suspend locked for an Administrator), qa-payments + admin-console 14/14.
  Browser: suspend -> Suspended -> reinstate -> Active on a throwaway local member.

## MEDIUM 13 — SEARCH / USER-SIDE: DONE (session 4, ~01:30 UTC Oct 3)

Figma: Mobile Search v10B Reviews (Product bar) 7693:7490, Switch sheet 7693:7489 / 7708:8117,
  Questions v6 Match 7718:12930, No match 7724:7520.
Backend (99c1b31): NEW public GET /products/{id}/search-card (services/product_search_card.py):
  review_count, median_rating, recommend_pct (share of published reviews "Yes, absolutely"),
  latest approved community price + date, questions / best_answers / unanswered, and active_now =
  distinct members who asked, answered, replied or voted on the product's questions in the last
  hour (from those rows' timestamps). tests/test_product_search_card.py (2). No migration.
Frontend: lib/search-product.ts resolves the product a query names (leading word runs against
  GET /products?browse=true; the longest run whose top match is the best-reviewed; the words the
  product's name lacks are the QUESTION words). components/search/SearchProductBar.tsx (product
  bar with the frame's three stats per tab + Switch bottom sheet; a pick adds `product=`),
  components/search/QuestionMatch.tsx (Best match + top answer, Similar questions, See all N,
  "Can't find your question? Ask the … community"; No match + Related questions). Reviews narrow to
  the product only after Switch; Questions narrow when the query has question words or after
  Switch — otherwise both tabs keep the plain text search (the bar summarises its best match).
Deviations: no "Price History" / "3D Model" links on the bar (no product page / no 3D data);
  "Ask" opens /questions/new without the product prefilled (the composer takes no product param);
  "See all" re-opens the search on the product (there is no per-product questions page).
Tests: frontend unit 464 PASS; e2e journeys, figma-parity (QA-050 fixed after narrowing rule),
  owner-round4, console-health PASS. LOCAL-ONLY failures, unrelated: back-control "store page's
  Back" (needs the production QA seller row 5e11e700-…999), meeting-0929 B (report queue sorted
  oldest-first: the new report is pages away on the cumulative DB; no newest sort exists).
  Browser (390px): bar stats, Switch sheet + pick, match ("jisulife fan battery"), no match.

## STRETCH B + D — PERSON REPORTS SCOPE; ACTIVITY LOG WITH JOBS: DONE (session 4, ~00:40 UTC Oct 3)

Figma: Person/Reports 8007:13917 + Menu/Person/ReportScope 8086:17314; Screen/Admin/ActivityLog
  8074:16245 with Card/Jobs 8074:16919, Confirm/Jobs/RunNow 8081:16369, Menu/ActivityLog/
  Person 8080:16618 / Action 8080:16653 / Target 8080:16694 / Range 8080:16735.
Person Reports: "Against <name>" / "Filed by <name>" menu; columns Reported (type icon) / Reason /
  From / Outcome / Filed / Open. Frontend only (rows already carry their direction).
Activity log backend (f454831): GET /admin/activity gains actor (id|system), action (type
  moderation|money|access|privacy|system, or one action), target, range (today|7d|30d|all), q;
  rows add group, actor_id, target_label (review: product + author; member: name; question:
  opening words), href, reason, notes (additive). NEW /admin/activity/summary (today by type,
  proof-of-purchase views this week, team today, actors for the Person menu), NEW
  /admin/activity.csv (filtered, <= 5,000 rows), NEW POST /admin/jobs/{task}/run (staff; via the
  scheduler's own period lease, source=admin; money / deletion jobs Super Admin only). Services:
  activity_log_service.py. tests/test_activity_log.py (2). No migration. Matrix rows added.
Frontend: app/admin/activity/page.tsx -> components/admin/activity/ActivityScreen.tsx (search,
  Anyone / All actions / All targets / range menus, Export CSV, day-grouped sentences "<actor>
  <verb> <target>" with notes, Load older up to 200; Scheduled jobs card (unhealthy first with Run
  now, healthy with last success), Today by type bars, Proof-of-purchase views, Team today).
  lib/activity-admin.ts. Old components/admin/SchedulerHealth.tsx removed.
Deviations: day headers count the loaded rows, not the day's total; scheduled-job runs live in
  cron_runs (the Jobs card), not in the feed; "Next in Xh" not shown (last success instead).
Tests: test_activity_log (2), rbac sweep PASS; e2e admin-console 13/13; unit 464. Browser: list,
  Privacy filter (3), Run now priority tiers ("already completed" — period lease), CSV 200.

## SUSPENSION — VOTE EXCLUSION FIX (session 4, ~01:50 UTC Oct 3)

Found in the final RBAC check: the earnings gate summed each vote's snapshotted weight without
looking at the voter, so a suspended member's past upvotes still counted. Fixed at read time
(earn_gate.gate_states excludes votes whose voter is suspended; trust.weight_of returns 0 for a
suspended account, which covers report weights). Snapshots are unchanged, so reinstating restores
them. Honesty Fund and stage evidence already excluded suspended voters.
Tests: test_people_management (3) now covers member / Administrator / claimed seller refused,
Super Admin allowed, self / staff refused, reason required, sign-in refused, gate weight 0 while
suspended and restored after, audit trail (action, actor, target type, reason, timestamp).
Related suites (gate / vote / trust / report / earn / honesty / triage / seller): 684 passed.

## FULL BACKEND SUITE (session 4 close, ~01:15 UTC Oct 3, HEAD a2481a4)

2946 passed. 2 FAIL for environment only, also failing in session 3's run: tests/test_receipt_privacy
::test_receipt_locator_never_reaches_an_unauthorized_caller and ::test_moderator_receipt_view_is_
audited_without_any_locator upload a REAL object to the private Supabase bucket and this container
has no Supabase service-role credentials (none may be used here). They pass in CI with TEST creds.

## DEFENSE WALKTHROUGH: 7/7 PASS (session 4, ~01:05 UTC Oct 3) + production `next build` PASS

Run on an ISOLATED local stack so the shared local data is never reset:
  1. runuser -u postgres -- psql -p 5433 -h /var/run/postgresql -c "CREATE DATABASE lci_defense
     OWNER bluntly"   (+ CREATE EXTENSION pg_trgm in it); DATABASE_URL=...5433/lci_defense
     alembic upgrade head; python -m scripts.defense.seed --reset --out $SP/defense-seed-isolated.json
     (--reset touches ONLY lci_defense; the guard reports "local").
  2. API: DATABASE_URL=...lci_defense uvicorn app.main:app --port 8001 > $SP/uvicorn-defense.log
  3. Web: `next build` once, then API_URL=http://localhost:8001 npx next start -p 3001
  4. DEFENSE_SEED=$SP/defense-seed-isolated.json E2E_API_LOG=$SP/uvicorn-defense.log
     PLAYWRIGHT_BASE_URL=http://localhost:3001 E2E_API_URL=http://127.0.0.1:8001
     npx playwright test e2e/defense-walkthrough.spec.ts  -> 7 passed. Re-seed before each run
     (the scenes change state: votes, Best Answer, approvals).
Spec fixes this session: product step (Products modals), Sellers claim via the Review modal,
  affiliate stop -> ?tab=links, Prices outlier row scoped to "Apple iPhone 17", Reports step via
  the report table row -> modal (the session-3 queue redesign).

## FIGMA -> IMPLEMENTATION GAP MAP (session 3, Figma reconnected ~17:05 UTC)

Contributor Payout (HIGH 6) — Screen/Payout 7840:9380, Locked 7840:9462, Details 7843:9432
  Figma: cleared-money ring (commission / Honesty Fund), "Minimum met" or "₱x to go", How payouts
    work stepper, Send-to card + Change, Get there faster tips, Request ₱x / disabled Request payout;
    Details: method card, account name + number, Save.
  Frontend: DONE (/dashboard/transfer, /dashboard/transfer/details; PayoutRing, CashoutButton,
    PayoutDetailsForm, DashboardParts shared with the dashboard).
  Backend: balance split / short_of_minimum / masked account already existed. GAP: "Account name"
    had no storage -> MIGRATION 0072 users.payout_account_name + PATCH /auth/me/payout-account takes
    account_name (address optional) + balance and admin payouts return it.
  Deviations (correctness): the method is PayPal, not GCash/Maya (Completion contract X.4: GCash/Maya
    are simulated only; transcript "payouts use PayPal"); "Add bank or e-wallet" not drawn (no other
    rail exists); the PayPal email field shows the masked address (the full one is never sent to the
    page). Kept beyond the frame for function: QA tester note, "Your requests" list (status +
    reference), "still clearing" line. PayoutSimulation (GCash/Maya preview) is no longer rendered;
    the component and GET /payouts/simulate remain.
  Tests: test_payout_member_breakdown (account name), payoutRing model test, e2e qa-payments +
    br-journeys cashout PASS on the new screen, browser Change -> Save flow verified.
  Status: DONE.
Contributor Dashboard (HIGH 6) — 7833:9534: DONE earlier in session 3.
Contributor Performance (HIGH 6) — Screen/Performance 7848:9542
  Figma: product Switcher; review card (stars, avg, count, earned/views/helped, community row);
    Earnings last 30 days line + "+₱x this week"; Votes helpful/not helpful + bars (Weekly);
    From view to buy rings with "this week" chips; Where the commission went donut (You / Honesty
    Fund / Bluntly); Where they bought bar; Your reviews (Most earned) + See all.
  Frontend: DONE (/dashboard/insights; ReachRings + ParentLink moved to DashboardParts and shared
    with the dashboard; DashboardSelect gains tone="brand" = Figma Switcher).
  Backend GAP closed WITHOUT migration (c693024): performance() returns rating/review_count,
    upvotes/comments, up/down per bucket, helpful/not_helpful, daily 30 days + earned_30d/7d,
    reach_week vs reach_prev_week, stored share_you/honesty_fund/platform, orders per marketplace,
    per-product views/helped/earned.
  NOT drawn (no real data): bookmarks (no server record) and shares (reading telemetry only, kept
    out of money screens); the title's ArrowsDownUp icon (no behaviour in the file); the "30 days"
    pill is a label (only one range exists). "Weekly/Monthly" switches all period-based cards.
  Tests: test_contributor_dashboard (9), model tests (earningsLine, voteBars), QA-016 e2e PASS,
    browser screenshot at 390 + 1280, no overflow.
  Status: DONE. HIGH 6 is now COMPLETE (Dashboard, Payout, Performance).
Answer / Q&A (HIGH 7) — answer flow: Answer Page - Step 1..7 + All done (7573:8215 … 7573:9158)
  Figma: 1 words (30-char countdown, mascot with the question, asker's context quoted); 2 usage
    (6 chips) + expectations (3 chips) + optional note; 3 pros/cons chips; 4 verdict (Yes / Only on
    sale / Different variant / No); 5 right for them (3); 6 stars; 7 photo or skip; All done.
  Frontend: DONE — /questions/[id]/answer (AnswerFlow + answer-flow-model), proxy-gated; question
    page shows an "Answer" button for product questions. Reuses the review composer's pieces
    (exported from app/reviews/new/WriteReviewForm.tsx: CrowdBand, BluntlyTextarea, PhrasePicker,
    RatingStepDecor, ProductPhotoCard [receipt now optional, skip label a prop], CHIP_SHELL,
    PRO/CON_SUGGESTIONS, STAR_ARC; no behaviour change to the review flow).
  Backend GAP closed (de956e1, no migration): AnswerCreate.verdict (yes/on_sale/other_variant/no)
    on the "Recommends it" line; parts.verdict returned; older Yes/No still parse. Step 2 is composed
    into the existing `experience` text; pros/cons into good/bad.
  Kept beyond the frame: the one-line AnswerForm under the button (quick replies; store questions,
    which have no product; e2e-covered). All done's stats are LatestStats (real 90-day figures,
    hidden when unreadable).
  Tests: test_answer_parts (verdict round trip + API), answer-flow-model tests; browser run through
    all 7 steps posted an answer whose parts read back verdict=on_sale, right_for_you, rating 4.
  Status: answer flow DONE.
Question page (HIGH 7, part 2) — Question Detail v6B 7731:15601: DONE (session 4).
  Backend (81ef7fa): MIGRATION 0073_qa_engagement — qa_votes (one row per member per target;
    exactly one of question/answer/reply via CHECK; partial unique index per target; questions
    up-only) and answer_replies (depth 1..3, soft removal); both RLS-locked. Rules in
    services/qa_engagement.py (= the seller-review engagement rules): helpfulness only, no money
    or trust stage; no self votes (422 self_vote); suspended = read-only; replies no links,
    <=1000 chars, the answer's / parent's author notified (kind answer_reply); a reply to a
    level-3 reply joins level 3; author or staff removes. Answer helpful/unhelpful/wilson are
    recomputed from rows (they already ordered answers). Routes: PUT /questions/{id}/vote,
    PUT …/answers/{aid}/vote, POST …/answers/{aid}/replies, PUT …/replies/{rid}/vote,
    DELETE …/replies/{rid}, POST …/answers/{aid}/report. QuestionDetailOut: upvotes, my_upvote,
    reply_count; AnswerOut: unhelpful_votes, my_vote, replies[], reply_count.
  Frontend: app/questions/[id]/page.tsx rebuilt: ProductStrip + Verdict Summary (counted from
    answers' verdicts), asker/question/context/Looking for, Reactions (up-vote toggle + count),
    Best Answer card (verdict, stars, Experience / Pros & Cons / Is it for them / photos, Show
    less), "N more answers" + Most helpful/Newest chip, AnswerRow with VoteBar / Reply (n) /
    Share, nested threads with rails and inline reply boxes, sticky "Write your answer…" ->
    the answer flow. components/qa/QuestionThread.tsx + question-thread-model.ts.
  Kept (flows depend on them): About a product/store, Notify me!, Pick as Best Answer, the
    one-line answer form (store answers). Not drawn (no data): 3D Model, Price History, "⋯"
    menus (answer reports exist via API only), avatars (QAAuthor has none: initials).
  Tests: tests/test_qa_engagement.py (5), question-thread-model (4), e2e/question-thread.spec.ts
    (2) PASS; br-journeys Best Answer + owner-patch 11-14 PASS; browser sequence verified.

## NEXT EXACT TASK

Session 8: follow "SESSION 8 — LEDGER → NEXT" at the top (item 1: Seller change password).
Older list below kept for reference:
LOW 1-5 done; 6 is an owner question. Continue with regression + polish:
1. Full backend suite (last full run 2946 at a2481a4; session 5 added tests for settings,
   analytics, payout tips, honesty fund cycles, contributor dashboard).
2. Accessibility pass on the session-5 screens (keyboard through the Choose-review sheet, the
   Honesty Fund table, the Payout tips; contrast of grey text on white).
3. Re-audit STRETCH D account switcher vs Figma once (ledger note).

## DO NOT DO NEXT

- Do not develop on main or force-push. Do not reset researcher data (the seed script is for the
  local DB only).
- Do not build automated payout execution.
- Do not fabricate device/linked-account data or fraud results.

## UNCOMMITTED WORK

None at the session-3 Reports checkpoint.

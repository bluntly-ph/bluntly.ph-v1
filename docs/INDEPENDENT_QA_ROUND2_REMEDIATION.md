# Independent QA — Round 2 remediation (engineering record)

Source: the tester's workbook `BLUNTLY_QA` (sheet *QA Issues(Main)*, 61 items; retest notes in
*Engineering QA → QA Comment*), read in full on 2026-09-24. Tester Status is the tester's and is not
changed here. Engineering outcomes use only: FIXED_PENDING_INDEPENDENT_RETEST,
NO_CHANGE_REQUIRED_BY_CURRENT_RULES, NOT_REPRODUCIBLE_WITH_VALID_TEST_SETUP, BLOCKED_FIGMA_ACCESS,
BLOCKED_PRODUCT_DECISION.

- Base: `e0a4e93` (main = production). Branch: `fix/independent-qa-round-2`. Not merged, not deployed.
- Production was read, never written: read-only SQL through the read-only production connector and public
  GETs. No fixtures, no test users, no money moved.
- Figma: in the local round the connector needed OAuth, so no frame was read. **Cloud continuation
  (2026-09-24, branch `fix/cloud-round2-security-design`):** the Figma connector was authenticated and
  the current frames of file `lso4Ri4hDaZxvCebhUqlY5` were read; QA-020, 024, 025, 043, 050, 052, 053
  and 057 are updated below against them, with node references. Details and every intentional
  difference: `docs/FIGMA_ROUND2_VERIFICATION.md`.
- New migrations (apply to production **before** deploying, like 0050/0051):
  - `0052_review_drafts`: one additive table, with RLS on and PostgREST access revoked.
  - `0053_repair_rejection_links`: data only, idempotent. It re-points one legacy rejection notice.

## Active items

| QA ID | Tester Status | Engineering Classification | Reproduced? | Root Cause | Files Changed | Regression Test | Result | Needs Figma? | Needs Tester Retest? | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| QA-001 | Partially Fixed | PARTIAL_DEFECT | Yes | **Images.** 19 of 25 public reviews have no reviewer photo and their product has no stored image (case B), so the placeholder is correct. All 6 stored images load (object and render endpoint both 200). **2026-09-25:** production has 38 of 43 products without an image, and nothing in the app could store one (only the owner-run seeder), so the placeholder could never go away. **Relevance.** Same root cause as QA-033. | `backend/app/services/product_search.py`; `POST /products/{id}/image` (`canonical_service.set_product_image`), `ProductCatalogueActions.tsx`, `app/moderate/products/page.tsx` | `test_product_search_ranking.py` (3 new); `test_product_image_upload.py` (7: stored and served, audited, staff only, bytes sniffed, 5 MB cap, 404); journey *QA-001* (moderator adds a picture) | Relevance: FIXED_PENDING_INDEPENDENT_RETEST. Images: FIXED_PENDING_INDEPENDENT_RETEST (moderator path); the 38 existing products still need a moderator to add their pictures after release | No | Yes | Moderators add or replace a product's picture from Products (PNG, JPEG or WebP, 5 MB, checked by its bytes, audited as `photo_replace`). Code still never fetches or invents images. |
| QA-003 | Partially Fixed | REAL_DEFECT | Yes (code) | Drafts lived only in the browser's `localStorage`. The local key was also shared by every account on a device. | `review_draft` model/service/route, `0052`, `review-drafts-model.ts`, `WriteReviewForm.tsx`, `app/reviews/new/page.tsx` | `test_review_drafts.py` (9, incl. cross-user and newer-save-wins); `review-drafts-model.test.mjs`; journey *QA-003 + QA-038* (desktop and 390px phone, new device) | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Drafts live with the account and in a local copy scoped to the account. The newer save wins on both sides. Ten are kept. |
| QA-006 | Partially Fixed | EXPECTED_BY_CURRENT_RULES | Yes: state 1 | "No shop link" shows on reviews with no active admin-attached link (§2/§14). State 2 was verified on production: 18 reviews (10 Shopee, 8 Lazada) render "Buy it here" → `/r/<id>`. | `backend/tests/test_referral_api.py` | New Lazada attach→302 test; the Shopee flow is already covered | NO_CHANGE_REQUIRED_BY_CURRENT_RULES | No | Yes: retest on a linked review | **Ops follow-up:** `e0001`–`e0005` and the Guapo review are earnings-approved without a valid link. Their old store-level links were revoked. An admin should attach exact product pages. |
| QA-016 | Partially Fixed | PARTIAL_DEFECT | Yes | On the website the only back control was the hero's white arrow on the gradient card beside the content. | `components/dashboard/DashboardScreen.tsx` | Journey *QA-016*: 4 subpages at 1440 by direct URL; the arrow at 390 | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | From `lg`: a worded "← Dashboard" link to the parent page. |
| QA-020 | Fail | PARTIAL_DEFECT | Yes | Round 2: comments had no Share and no Reply on replies (QA-029). Cloud continuation, frame read (comment blocks `4305:2114`, `4305:2113`): the measured metrics already matched (36px disc, 8px byline gap, 12px to body and row, 36px between actions, 36px reply indent, 20px reply offset, 40px between threads). What made rows uneven was the author's Delete inside the action row; the frame puts per-comment actions in the header's DotsThree, and the byline carries the Honesty Score. | `CommentThread.tsx`, `lib/comments.ts`, `schemas/comment.py` (`reputation_score`) | Journeys *QA-029*, *QA-039* (Delete via ⋯), *QA-020* in `figma-parity-journeys.spec.ts` | FIXED_PENDING_INDEPENDENT_RETEST | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | Every comment and reply: votes, Reply, Share. The author's Delete is in a ⋯ drawn only when it holds an action; two-step confirm kept. |
| QA-022 | Fail | REAL_DEFECT | Yes | (a) Weak trigram matches, as in QA-033. (b) The browser's own form-history list (`name="q"`, no `autocomplete="off"`) opened a dark native panel repeating earlier terms. | `product_search.py`, `SearchAutocomplete.tsx` | Search ranking tests | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Debounce (250 ms) and the stale-response guard were already correct. |
| QA-023 | Fail | REAL_DEFECT | Yes | The row was already one full-width link but had no hover or pressed state. | `QuestionResultRow.tsx` | Journey *QA-023* (hover changes background, pointer cursor, Enter opens) | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | |
| QA-024 | Fail | REAL_DEFECT | Yes | Round 2: Share went to `navigator.share` or a silent copy. Continuation, frame `1731:1571`: header "Share to…", preview card, rule, destination row (Facebook, Messenger, Instagram, Add to Story, Reddit, X, Viber, Telegram, WhatsApp), Copy link, Bookmark, More. | `share-model.ts`, `ShareSheet.tsx`, `ShareButton.tsx`, `ReviewDetail.tsx`, `FeedCard.tsx` | `share-model.test.mjs` (destinations, encoding, hostile path); journeys *QA-024* (desktop and phone, author prompt) | FIXED_PENDING_INDEPENDENT_RETEST | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | Not drawn, with reasons: Instagram and Add to Story (no web share address; reachable via More on phones), Bookmark (omitted by owner decision). Messenger and Viber only on touch devices (app links). The "boost your commission" caption only for the author, and commission only when the review has its shop link. |
| QA-025 | Fail | REAL_DEFECT (multi-select) | Yes | The live Category group took one choice. The frame's All filters (`1587:4658`) has no Category group, so the tester's expectation is the only spec for it, and the API can serve it. | `routes/reviews.py` (`category` repeats), `review_service.list_feed`, `SearchFilterBar.tsx`, `search-tabs-model.ts`, `app/search/page.tsx` | `test_figma_search_filters.py`; `search-tabs.test.mjs`; journeys *QA-025/053 (phone)*, *QA-025 (desktop)* | FIXED_PENDING_INDEPENDENT_RETEST | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | Categories are checkboxes; a review in any chosen category is shown. The desktop rail's categories add to or remove from the set. |
| QA-027 | Fail | REAL_DEFECT | Yes | The feed card showed counts as plain text inside the row link: no downvote, no share. | `FeedCard.tsx`, `lib/reviews.ts`, `app/feed/page.tsx` | Journey *QA-027/028* | FIXED_PENDING_INDEPENDENT_RETEST | Layout only | Yes | Author and claimed sellers (§9) see counts, not controls. The API still enforces this. |
| QA-028 | Fail | REAL_DEFECT | Yes | The "buttons" were text inside a link, so a tap only opened the review. An author tapping vote on their own review was also sent to sign-in. | `ReviewVoteBar.tsx` (read-only mode), `ReviewDetail.tsx`, `app/reviews/[id]/page.tsx`, `schemas/auth.py` (`is_claimed_seller` on `/auth/me`) | Journey *QA-027/028* (vote recorded, no navigation); `test_auth_me_claimed_seller.py` | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Controls sit outside the link, so there is no nested interactive element. |
| QA-029 | Fail | REAL_DEFECT | Yes | Reply rows had no Reply button. | `CommentThread.tsx`, `comment-tree-model.ts` | `comment-tree-model.test.mjs`; journey *QA-029* | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Threads stay two levels (the API refuses a third). A reply to a reply joins the thread, opened with "@handle". |
| QA-030 | Partially Fixed | REAL_DEFECT | Yes | Only the upvote button set the count's 12px Light type. | `ReviewVoteBar.tsx` | Journey *QA-030* (computed type equal) | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | |
| QA-033 | Fail | REAL_DEFECT | Yes | pg_trgm `word_similarity` is exactly 0.5 for any word sharing only a 3-letter query's first two letters. The threshold accepted 0.5 or more. | `product_search.py` (0.55) | `test_product_search_ranking.py` | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Measured: `ankr` 0.60, `tefl` 0.60, `jisulfe` 0.625 all still match. For "ma", MacBook, "material" and Mattress are genuine word-prefix matches. **Data:** one product record is named "What type of material used in Simwood pants?", and some pending products are named with raw URLs. These need moderator cleanup. |
| QA-038 | Fail | NOT_REPRODUCIBLE (Enter/blur) + hardening | No | On the real stack, Enter and leaving the field both add and keep a custom phrase. The reported "appears while typing" is the browser's form-history list. | `WriteReviewForm.tsx` | Journey *QA-003 + QA-038*: Enter, blur, Add, duplicate, Continue→Back, account copy; desktop and phone | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Added `autocomplete="off"` and an explicit **Add** button. |
| QA-039 | Partially Fixed | REAL_DEFECT | Yes | A confirmed delete left a "[removed]" row that stayed, and came back on refresh. | `CommentThread.tsx`, `routes/comments.py` | `test_comments_api.py` (new); journey *QA-039* (gone, and gone after reload) | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | A top comment with live replies keeps a tombstone. |
| QA-043 | Fail | PARTIAL / BLOCKED_PRODUCT_DECISION | Yes | Seller Account clarification (owner, 2026-09-24): claiming grants a public, editable response and a flag-as-fake / substantiation path, never suppression, voting or earning. No rule or API defines votes, threaded replies or an ordinary viewer's report on a seller review. | `SellerReviewActions.tsx` (unchanged) | br-journey (owner responds and flags) | Share: FIXED_PENDING_INDEPENDENT_RETEST. Votes, replies, viewer report/⋯: BLOCKED_PRODUCT_DECISION | Read (frame `4218:2148` draws them) | Yes | Not added just to match the frame or the old expectation; no empty ⋯. See `docs/FIGMA_ROUND2_VERIFICATION.md`. |
| QA-050 | Fail | PARTIAL_DEFECT | Yes | Frame `3481:1894` draws All filters and Sort on the Questions tab and a 100px product image; neither existed. "3 active" and "Topics" chips have no data behind them. | `routes/qa.py` (`period`, `sort`), `qa_service`, `QuestionOut.product_image_url`, `QuestionResultRow.tsx`, `SearchFilterBar.tsx` | `test_figma_search_filters.py`; journey *QA-050* | FIXED_PENDING_INDEPENDENT_RETEST | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | Time (all / past year / past month) and Sort by date (Latest / Oldest); the product tile when an image is stored. "3 active" and Topics remain product gaps. |
| QA-052 | Fail | PARTIAL_DEFECT | Yes | Frame `3954:650` draws All filters and Sort and "128 reviews · 39 questions answered"; the tab had no pills and no answered count. | `routes/sellers.py` (`claimed`, `sort`), `seller_service` (`answered_question_count`), `SellerResultRow.tsx`, `SearchFilterBar.tsx` | `test_figma_search_filters.py`; journey *QA-052* (checked against the API) | FIXED_PENDING_INDEPENDENT_RETEST | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | Filters: marketplace, claimed profiles only. Sort: name, most reviews. Private claim data stays private. |
| QA-053 | Fail | PARTIAL_DEFECT / BLOCKED_PRODUCT_DECISION | Yes | Frame `1587:4658` groups: Review score (Most Helpful, Hidden Gems, Controversial, Trending), Trust rating (All / 0–70 / 80–100), Budget (Thrifty ↔ Balanced), Time (All time / Past year / Past month). Only Category existed live. | `routes/reviews.py` (`period`, `sort=oldest`), `review_service`, `listing_filters.py`, `SearchFilterBar.tsx` | `test_figma_search_filters.py`; journeys *QA-025/053*, *QA-053 Sort* | Time and Oldest: FIXED_PENDING_INDEPENDENT_RETEST. Hidden Gems / Controversial / Trending / Budget: BLOCKED_PRODUCT_DECISION (no definition). Trust rating: BLOCKED_PRODUCT_DECISION (§21) | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | No decorative filters: each undefined group is documented, not drawn. |
| QA-054 | Fail | REAL_DEFECT (legacy data) | Yes | Production's only rejection notice (2026-09-22, old code) linked to `/dashboard/history`. New notices already link to the review, which shows the author the "won't earn" reason. | `0053_repair_rejection_links.py` | `test_notification_link_repair.py` (repair, decoy untouched, idempotent; new-notice link) | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | A link is repaired only when the reject log shares the notice's exact instant and targets the recipient's own review. |
| QA-055 | Fail | PARTIAL_DEFECT | Partly | No production account had both read and unread notices, so the states were never seen side by side. | `NotificationList.tsx` | Unit tests; manual | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Unread rows now also carry a worded **New** label, announced as unread. |
| QA-057 | Fail | REAL_DEFECT | Yes | Frame `4218:2148` (Group 691 `4281:870`) draws All filters and Sort pills under the Reviews/Questions tabs; the page had a native select. **Also found:** the list filter matched exact ratings against whole stars, so every half-star seller review (0048) was missing from the list. | `SellerReviewsSection.tsx`, `seller-model.ts` | `seller-model.test.mjs`, `seller-page-model.test.mjs` (half stars, Time, Oldest); journeys *QA-057* (phone and desktop) | FIXED_PENDING_INDEPENDENT_RETEST | Read (Figma file `lso4Ri4hDaZxvCebhUqlY5`, read 2026-09-24) | Yes | All filters: rating (same ticks as the card) and Time. Sort: Latest / Oldest, Highest / Lowest, With photos first. The median aggregate is untouched. "Top mentions" chips: no data (gap). |
| QA-059 | Fail | REAL_DEFECT | Yes | The menu was always anchored to its trigger's right edge. From `md` the trigger is at the column's left, so the menu hung out of the column over the title. | `ReviewOverflowMenu.tsx` | Journey *QA-059* at 1280/390/320 | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | The menu opens toward the side with room, and upward if there is no room below. |
| QA-061 | Fail | INVALID_TEST_SETUP | Yes: setup A only | One browser profile has one cookie jar. `/login` sends a signed-in tab to `/`, so a second account needs Log out first, which ends the session for every tab of that profile. | none (tests only) | Journeys *QA-061 E* (two browser processes), *B* (two isolated contexts), *A* (same profile) with real code sign-ins | NOT_REPRODUCIBLE_WITH_VALID_TEST_SETUP | No | Yes, with separate profiles | E and B stay isolated. Cookie is host-only, httpOnly, SameSite=Lax. Authenticated fetches are never cached. No service worker. No per-tab auth added. |

## Open item

| QA ID | Tester Status | Engineering Classification | Reproduced? | Root Cause | Files Changed | Regression Test | Result | Needs Figma? | Needs Tester Retest? | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| QA-058 | Open | REAL_DEFECT (legacy data) | Yes | Production's 3 Best Answers predate recorded picks: no picker, no audit entry, badge shown anyway. New picks were already asker-only, audited and attributed. | `qa_service.py` | `test_best_answer_attribution.py`: clean question, non-asker refused, reload, notification, legacy unattributed pick hidden | FIXED_PENDING_INDEPENDENT_RETEST | No | Yes | Unattributed picks are not presented as Best Answer, and the rows are untouched. The asker can pick again. |

## Deferred (not implemented)

- **QA-005:** social accounts deferred. None invented.
- **QA-049:** §21 naming is still open.

## Resolved items: regression protection

The shared subsystems I touched are search, votes, comments, share, notifications, the dashboard shell and the composer. The resolved items behind them are protected as follows.

**Covered by the real-stack journeys** (`br-journeys.spec.ts` 13/13, re-run on every push):
- QA-008/009/010: search suggestions. Word-prefix and alias tiers are unchanged, and "jisu" still returns Jisulife.
- QA-011: vote toggling.
- QA-044: new comments appear immediately.
- QA-045: Notify me.

**Checked by reading the code:**
- QA-015/017/018: the dashboard root still uses its own nav. The QA-018 back target is unchanged.
- QA-060: the review image is not touched.

**Earlier engineering outcomes left intact:** QA-002, QA-036, QA-037 (composer); QA-031 and QA-004 (rules).

## Security regression check

- **Drafts:** no cross-user access (list, write and delete are all scoped to the caller). A slot is validated as a UUID or a fixed marker; payload is capped at 64 KB.
- **Links:**
  - Share paths are same-site only; off-site input falls back to `/`.
  - Notification links are same-site only, as before.
  - The "@handle" reply opener is plain text, sanitised to `[A-Za-z0-9_.-]`.
  - No user-generated links: the link policy is unchanged.
- **Receipts:** no receipt data is exposed.
- **Votes and authorisation:**
  - Claimed sellers still cannot vote; the API enforces it and `/auth/me` only mirrors it.
  - Best Answer stays asker-only (403/404 for anyone else).
- **Sessions:** no auth cache change; authenticated fetches are never cached by construction.
- **XSS:** unchanged. Every new text is rendered by React as text, and the existing hostile-input journey passes.

## Cloud continuation (2026-09-24): trust-integrity security fix

Not a QA item: a security report ("trust-stage evidence check counts vote volume, not voter identity").
Confirmed and fixed on `fix/cloud-round2-security-design`: stage evidence now counts distinct eligible
voters; a repeating voter cohort holds promotion for a moderator; Honesty Fund eligibility inherits the
same evidence. See `docs/TRUST_DISTINCT_VOTER_SECURITY_FIX.md`, `docs/adr/016-distinct-voter-evidence.md`
and the read-only production audit `docs/TRUST_STAGE_PRODUCTION_AUDIT.md` (no member at Stage 3+).

## Verification (local round)

- **Local:**
  - `tsc` clean, eslint clean, frontend unit tests 363/363.
  - `ruff` clean.
  - Backend: 1,730 passed; database tests skip locally.
- **CI:** the DB fast lane runs, on each push:
  - the full pytest suite on Postgres 17;
  - the milestone verifier;
  - the migration round-trip;
  - the production build plus `br-journeys` and `qa-round2-journeys`.
- **Latest green run:** recorded in the final report.

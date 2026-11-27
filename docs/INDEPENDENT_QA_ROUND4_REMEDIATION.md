# Owner requests and QA round 4 (engineering record, 2026-09-28)

Sources: the owner's requests of 2026-09-28, and the tester's workbook `BLUNTLY_QA` on Drive
(sheet *QA Issues(Main)*, items still marked Fail / Partially Fixed / Open). The workbook was read,
**not edited**; its Tester Status column is quoted as it stands. Nothing here says "QA Passed": every
item below waits for independent retest.

- Base: `main` at `684bb8b` (PR #3) plus `76e4563` (telemetry test isolation). Branch
  `fix/independent-qa-round-2`.
- Migration: `0060_seller_review_engagement` (two new tables, RLS on and `anon`/`authenticated`
  revoked, as every table since 0050). Additive; downgrade drops both tables.
- Evidence: backend `tests/test_owner_round4_api.py` (3), `tests/test_review_lenses.py` (7),
  `tests/test_product_search_ranking.py` (+1); frontend `search-tabs.test.mjs` (+5),
  `listing-link-model.test.mjs` (4), `account-switch-model.test.mjs` (4),
  `account-menu-guards.test.mjs` (+3); browser journeys `e2e/owner-round4-journeys.spec.ts` (10), plus
  the extended QA-061 journey in `qa-round2-journeys.spec.ts`. All 55 journeys pass on a fresh
  CI-equivalent database.

## Owner requests

| Request | What changed | Evidence |
|---|---|---|
| Dashboard "Answers" opened /questions | Dashboard has a Reviews / Answers toggle (`/dashboard?tab=answers`): **Answers to your questions** (each question you asked, newest answer activity first, with up to two answers, the Best Answer first once you pick it) and **Questions you answered** (with your answer). API: `GET /questions/mine?role=asked|answered`. | `test_the_answers_tab_lists_my_questions_with_their_answers`; journey "Dashboard → Answers" |
| Search for people | Search has a **People** tab (`/search?tab=people`) matching @handle or name (exact handle, then handle prefix, then name, then word start; ties by review count). Suspended accounts and accounts without a handle are never listed; only public fields are returned. The search box also suggests up to three people ("Profile"). API: `GET /users/search`. | `test_people_search_…`; journeys "Search → People", "search box suggests a person" |
| Long text overflowed /reviews | The page body breaks overlong words (`overflow-wrap: break-word`), so an unbroken 3,921-character string wraps inside its column on every page. | journey "4,000-character unbroken string" at 390 and 1280 px |
| /profile: no Log out, no Earnings / Edit chips, ⋯ instead of Share | The profile header's ⋯ (**Profile options**) holds **Share profile** and **Edit profile**. Log out stays in the side navigation only; Earnings stays reachable from Dashboard. | `account-menu-guards.test.mjs`; journey "/profile keeps Log out in the side navigation…" |
| Feed in the side navigation | **Feed** is the first entry of the side navigation, signed in and signed out. | `account-menu-guards.test.mjs`; journeys "side navigation has Feed" |
| QA payment tester | `@bluntly_ph` (bluntly.ph@gmail.com) was added to the production QA tester list, with its `qa_tester_add` audit entry. See `docs/QA_PAYMENT_TESTING.md`. | production `platform_settings.qa_testers` |

## Workbook items still Fail / Partially Fixed / Open

Every other Fail / Partial / Open item was re-checked on the current build (local real stack) and
behaves as its round-3 fix describes: QA-003, 016, 020, 023, 024, 025, 027, 028, 029, 030, 038, 039,
050, 052, 055, 057, and QA-062..075. The items below needed more work.

| QA | Tester status | Engineering outcome | What changed |
|---|---|---|---|
| QA-001 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST (search order) / **content gap** (images) | Search-box product suggestions now skip products nobody can read anything about (no review, no question) and products named by a bare link, and put the most-reviewed first within a relevance tier. Images: every stored product image loads (checked live); **42 of 47 products have no image at all**, 26 of them with published reviews. Engineering cannot invent product photos; a moderator adds them on **Admin → Products** (list below). |
| QA-006 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST | A review with no affiliate link now links the product's own marketplace listing (**View on Shopee / Lazada**, https and a known marketplace host only, `rel="nofollow noopener noreferrer"`), labelled "Not an affiliate link — nobody earns from this click." Approved affiliate links keep **Buy it here**. |
| QA-022 / QA-033 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | On production, "ma" suggested *What type of material used in Simwood pants?* (a question typed into the product field) and products named by pasted links. Those are no longer suggested (see QA-001); "ma" now leads with Mandaue Foam and MacBook. The review composer's picker still sees every product, so reviewers attach to existing ones. |
| QA-043 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | Seller reviews take **Helpful / Not helpful** votes (one per member; not the author, not the store's owner; they move no rating, trust or money), a flat **Reply** thread (no links, 1,000 characters; the reviewer is notified; the store's owner answers with its one public response instead), **Share**, and **⋯ → Copy link / Report this review** into the ordinary moderation queue, where a moderator can remove or restore it. |
| QA-053 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | All filters now has the frame's **Review score** (Most Helpful / Hidden Gems / Controversial / Trending), **Trust rating** (All / 0–79 / 80–100) and **Budget** (Thrifty ↔ Any price, stops ₱500 … ₱10,000), with Time and Category; the desktop rail offers the same. Definitions (written once in `backend/app/services/review_lenses.py` and shown in each section's info): Hidden Gems = helpful reviews of products at most three people reviewed; Controversial = readers split (a vote each way, the smaller side at least half the larger), most votes first; Trending = most helpful votes and comments in the past 7 days; Trust rating = the author's 0–100 trust score shown on every review; Budget = what the reviewer paid, at most the amount (reviews without a price are left out once a budget is set). The frame's "0–70" band became "0–79" so no score falls between the two bands. |
| QA-054 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | The "Not published" note on the author's own rejected review now shows the moderator's reason (it showed the takedown reason field). |
| QA-059 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | On desktop the review's Copy link and Report sit inline in the author row, so there is no pop-up to overlap the title or "Ask a question". Phones keep the ⋯ menu, anchored to its button. |
| QA-061 | Fail | INVALID_TEST_PROTOCOL + FIXED_PENDING_INDEPENDENT_RETEST (notice) | Separate browsers and separate browser profiles keep separate sessions (journeys QA-061 E/B). Tabs or windows of **one** profile share one sign-in cookie, as on any website. New: when another tab of the same browser signs in as a different account, every other tab shows "You signed in as @… in another tab of this browser … reload", so no tab silently acts as an account it does not show. Retest with two browser profiles (or Chrome and Edge) for isolation. |

### Products with published reviews and no image (for Admin → Products)

Guapo Car Shampoo · High-Quality Wooden Chopping Board · ACTIVE Whey Protein 1lb · Apple iPad 11th Gen
A16 (Wi-Fi) · Apple iPhone 17 · Apple iPhone 17 Pro · DJI Osmo Action 6 · DJI Pocket 4 · JewelryPalace
925 Sterling Silver Chain Necklace · Jisulife Life7 Handheld Fan · Joyce & Diana Comfy Rest Pro Sofa Bed ·
Mandaue Foam Waterproof Mattress Protector · Member's Value Antibacterial Hand Soap · Multipurpose
Cleaning Cream · New Balance 530 (MR530SG) · PUMA Ballet Flats Light Sole · Samsung Sound Tower ·
Seaways All-Purpose Cleaner Spray · Sony PlayStation 5 Digital Edition · Sony PlayStation 5 Slim
Digital Edition · Sony WH-1000XM5 · soundcore R60i NC · Steam Deck OLED · Uniqlo AIRism Crew Neck Tee ·
Uratex Classic Mattress (6 inches) · and one product named by its Lazada link (a Vaseline lotion), which
also needs renaming.

### Production data left as it is (owner's call)

Products created by mistake, with no review, question or listing: *What type of material used in
Simwood pants?*, *ModLoopProbe 1786340188*, and two named by bare Shopee/Lazada short links. They no
longer appear in search suggestions. Deleting them is a production data change, so it is left to the
owner (Admin → Products, or ask for a scripted cleanup).

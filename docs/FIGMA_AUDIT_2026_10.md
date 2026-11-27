# Figma 1:1 design audit — October 2026

Source of truth: Figma file `lso4Ri4hDaZxvCebhUqlY5`, Page 1 (`0:1`), read 2026-10-05/06.
Figma controls presentation; existing product/API requirements control functionality.
Branch `claude/relaxed-euler-oycbod`. Status/next steps: `CLAUDE_PIM_STATUS.md`.

Phone frames are 390 wide with a mock status bar (43–48px) above the 72px NavBar; that band is
device chrome and is not built. No consumer screen has a desktop frame, so desktop is checked
for breakage only (1280: no overflow, no console errors).

## Checklist — FIGMA FRAME → ROUTE → STATUS → DIFFERENCES → FIX

| Figma frame | Node | Route | Status | Differences found | Fix (commit) |
|---|---|---|---|---|---|
| Screen/Question | 7731:15601 | /questions/[id] | Aligned (gaps 3D, menus) | No Detail bar, no strip icons, no sheets, no avatars, no ⋯ menus, unbounded reply depth, no FAB | Detail bar, strip, sheets, menus, depth-3 cap + "Continue this thread", FAB (df3d60a) |
| Screen/Question/Thread | 7735:8020 | /questions/[id]?reply= | Aligned | No reply composer | Thread composer (df3d60a) |
| Composer/Progress | 8475:38260 | every composer | Aligned | Green last step, grey hairline | 2px #ececec track, orange fill, Figma values (cec9984) |
| Screen/Answer/Step 1, 1.1 | 7573:8215, 8403 | /questions/[id]/answer | Aligned | Double focus ring | `.own-focus` (a2d1125) |
| Screen/Answer/Step 2a, 2a.1 | 7573:8936, 8983 | 〃 | Aligned (16px field) | White cards, 2px ring, 44px note, 20px offset | Grey cards, 1px border, chip note, 46px (cec9984) |
| Screen/Answer/Step 2b | 7573:8591 | — | **Not built** | "Where's this from?" source rows | Backend: no answer-source field |
| Screen/Answer/Step 3, 3.1 | 7573:8792, 8864 | 〃 | Aligned | Card 416px wide on a 390 phone (page scrolled sideways) | Input `w-0 flex-1` (4ca1da8) |
| Screen/Answer/Step 4, 4.1, 5, 5.1 | 7573:8635, 8678, 8714, 8753 | 〃 | Aligned | Offsets; 4.1/5.1 marks missing | Offsets (cec9984), marks (a2d1125) |
| Screen/Answer/Step 6, 6.1, 6.2 | 7573:9030… | 〃 | Aligned | Clouds 154px too low (margin collapse) | Padding (4ca1da8) |
| Screen/Answer/Step 7 | 7573:9133 | 〃 | Aligned (enabled Post) | — | — |
| Screen/Answer/Done | 7573:9158 | 〃 | Aligned | Offsets, no card decor, no asker photo | (a8a54b7) |
| Screen/Ask/Step 1, 4 | 7573:10945, 10886 | /questions/new | Aligned (Shopee field) | — | — |
| Screen/Ask/Step 2–2.3 | 7573:10506… | 〃 | Aligned (no photo) | "Would you like to share a photo?" | Backend: no question photo |
| Screen/Ask/Step 3 (done) | 7573:11005 | 〃 | Aligned | Stats 32px not 83px | (fe972bd) |
| Screen/WriteReview/Step 1, 1.1 | 2403:762, 4435:863 | /reviews/new | Desktop n/a; mobile aligned | — | — (16px field, focus ring fixed a2d1125) |
| Screen/WriteReview/Step 2, 2.1 | 4435:1092, 4493:2972 | 〃 | Mobile aligned | Choices 11px high; right mark at left 310px overflowed 320 | mb-8, right-anchored (276c2cb) |
| Screen/WriteReview/Step 3.1–3.6 | 4435:1344… | 〃 | Mobile aligned | Clouds 154px low; right clouds overflowed 320 (389px page) | (4ca1da8, 276c2cb) |
| Screen/WriteReview/Step 4, 4.1 | 4512:5073, 4519:7505 | 〃 | Mobile aligned | Card 416px wide on 390 | (4ca1da8) |
| Screen/WriteReview/Step 5, 5.1 | 4519:5414, 4519:5811 | 〃 | Mobile aligned (bubble copy) | — | — |
| Screen/WriteReview/Step 6, 6.1 | 4443:555, 4449:692 | 〃 | Mobile aligned except up-to-4 photos | — | Kept: multiple review photos (owner, P1) |
| Screen/WriteReview/Step 7, 7.1 | 4452:748, 4512:4973 | 〃 | Partly: disclosure added | Disclosure question + preview below it; no pills on preview | Kept: material-relationship disclosure is required |
| Screen/WriteReview/Price, Price/Filled | 4550:8677, 4550:8771 | 〃 (dialog) | Aligned (+ marketplace once an amount is typed) | Focus drew a box inside the pill | Pill's own 1px edge (see next commit) |
| Screen/WriteReview/Done | 4550:8882 | 〃 | Partly | Blurb text; no illustrative pills, so stats sit higher | Kept (recorded): earning is decided later |
| Screen/Product | 7651:5805 | /reviews/[id] | Desktop OK (1280); mobile aligned except gap 11 | Extra search glyph; no FAB; inline comment composer at the top, "N comments" | Bar + FAB (b5a3a40); "N replies" + sticky Composer bar at the thread's end, FAB lifts over it (3109645). Tested: unit 628, tsc, lint, browser 390 signed in/out + post, 1280 |
| Screen/Home | 1902:1504 | / | Aligned | Tilted card stack instead of ReviewQuoteCard; no FAB | (9fd0c18) |
| Screen/Search | 6852:641 | /search | **Partly** | Typing state with recent + "Most searched today" | Not built: no search-history/trending API |
| Screen/Search/Reviews | 7693:7336 | /search?q= | Resting state aligned (functional extras) | People tab, downvote + Share on cards | Kept (functionality) |
| Screen/Search/Reviews/Sort open | 7762:9948 | 〃 "Most helpful" | **Aligned** | The Menu: 220px, 8px under the bar, ✓ on the current order, tap applies; Most helpful / Newest / Lowest rated as drawn, plus Oldest (kept) | SortMenu.tsx (a9e9398; Lowest rated: step 2) |
| Screen/Search/Reviews/Filters | 7762:9999 | 〃 "Filters" | **Aligned** (+ our groups after the frame's) | Rating (All, 5★–1★, several), Show only (With photos, Verified buyers, Recommends it), Variant (with one product, its reviewers' variants), and the live "Show 42 reviews"; then Review score, Trust rating, Budget, Time, Category (kept) | ChipSheet.tsx (a9e9398; step 2) |
| Sheet/Filter sellers | 8462:36591 | /search?tab=sellers "All filters" | **Aligned** | Profile (Claimed by the owner / Unclaimed), Sells on with logos, Rating (4★ & up / 3★ & up / Any), Answers buyers (Within a day / Within a week: the store's median time to its own answer), live "Show 24 sellers" | (a9e9398; step 2) |
| Screen/Search/Reviews/Switch product | 7693:7489 | 〃 "Switch" | Aligned (minor) | Rows omit the ★ rating; the check is circled | — |
| Screen/Search/Sellers | 7664:7178 | /search?tab=sellers | Aligned | "Sort" opens the Menu; the "Best evidenced" definition sits under it (MQA-033, kept) | (a9e9398) |
| Search/Categories/Profile/Dashboard/Performance/History/Store | see `QuickActions` | various | FAB aligned | Retired "Action Menu" FAB on /search and /sellers/[id] | (375023d) |
| Screen/Search/Questions | 7718:12930 | /search?tab=questions | **Not 1:1** (not edited) | Figma: no filter/sort pills; "Best match" card, "Similar questions", "See all N other questions", "Ask the community". Code adds "All filters"/"Sort" pills and a flat list | `defense-build-oct6` owns QuestionMatch |
| Screen/Product/Questions/All, Switcher open, Sort open, Search | 7753:7873… | — | **Not built** | "All questions · 39" dropdown (All/Unanswered/Answered), "Newest" sort dropdown, inline search | Figma's "See all" target; no route exists |
| Screen/Dashboard | 7833:9534 | /dashboard | **Aligned** (+ kept extras) | Nav tiles, wallet card, Earnings + Best performing, trust stepper, requirements, Honesty Score, Your reach. Requirements were five-in-a-row at 390; now three to a row as drawn, labels hyphenated. Kept below the frame: Your reviews / Answers links, Payment history | ContributorDashboard (f92df74) |
| Screen/Payout, /Locked | 7840:9380, 7840:9462 | /dashboard/transfer | **Aligned** | Ring, Commission / Honesty Fund, Get there faster tips, disabled Request; Chat link added to the bar. Kept: the "still clearing" note | (fecd889) |
| Screen/Payout/Details | 7843:9432 | /dashboard/transfer/details | Aligned (PayPal only) | The platform pays by PayPal only, so no GCash / Maya rows or "Add bank or e-wallet" | — |
| Screen/Payout/Tip/* | 7843:9501, 7844:9469, 7844:9529 | /dashboard/transfer/{proof,answers,honest-reviews} | Aligned | Real figures and honest copy ("all reviewers") | — |
| Screen/History | 8098:17238 | /dashboard/history | **Aligned** | Month = one white panel in the 3px frame, header inside, no row rules, grey statuses (Reversed red); Chat link | (fecd889) |
| Screen/Performance | 7848:9542 | /dashboard/insights | **Aligned** (recorded gaps) | Names wrap to two lines, filled upvote arrow. Not drawn by us: bookmarks and shares (no per-review record), the title sort icon (no behaviour in the file), the static "Most earned" / "30 days" carets | (fecd889) |
| Screen/Profile/Reviews, Comments, Stats | 5446:4328, 6398, 6532 | /profile, /profile/[username] | Aligned (recorded gaps) | Followers and bio are not served; stats show Verified reviews and Honesty Score where the frame has People helped / Buyers guided (not served per member); a Saved tab is ours | ProfileHeader.tsx |
| Admin chrome (Sidebar, TopBar, page title) | 8058:14420, 8444:38623 | /admin/* | **Aligned** | Bluntly mark on the peach tile; 32px nav rows, 18px labels; current row = ink label + orange outline glyph (frames disagree on Overview's glyph: ink there, orange elsewhere — orange kept everywhere); title 24px under the bar in a 32px line | (9031430) |
| Admin tables | 7943:11402, 7998:11693, 8024:12721 | queue, people, payouts, sellers, affiliate, routing, all reviews | **Aligned** | Two-line cells 20/16px, rows 61px; the trust mark is the bluntly mark | (8f40582) |
| Screen/Admin/Overview v4 | 8444:38623 | /admin | Aligned (data-driven rows) | "Honesty Fund to approve", "No 3D model yet", "New seller sign-ups" show only when the data has them (no 3D data at all) | — |
| Screen/Admin/Queue/* | 7943:11402… | /admin/review-queue | Aligned | Our description line and refresh button are kept | — |
| Screen/Admin/People | 7998:11693 | /admin/reviewers (/admin/people redirects) | Aligned (+ Trust Score column, owner) | — | (8f40582) |
| Screen/Admin/Payouts, HonestyFund | 8024:12721, 8024:13286 | /admin/payouts, /admin/honesty-fund | Aligned | "Manual transfers · minimum ₱300" where the frame has "Process requests" (payouts are sent by hand); QA payments tab is ours | — |
| Screen/Admin/Reports | 8028:12886 | /admin/reports | Aligned | 16px label/note lines, 26px amounts; the section tabs (Honesty Fund, Commissions & Payouts, Seller Ratings) are ours | (8f40582) |
| Screen/Admin/Products, Sellers, Affiliate | 7966:11087, 7992:11327, 8015:12542 | /admin/products, /admin/sellers, /admin/affiliate-links | Aligned | Queue tab hides filter/search (the submissions API has neither); Import / Add product, Product links and Needs link tabs are ours | — |
| Screen/Admin/Analytics | 8071:16115 | /admin/analytics | **Aligned** | Period under the title with range then Export at its right; decision-mix swatches; stage bar + legend | (be3c199) |
| Screen/Admin/ActivityLog | 8074:16245 | /admin/activity | **Aligned** | 328px side column; header rhythm; day labels no longer break hydration | (be3c199, 6e25b1b) |
| Screen/Admin/SpecialRouting | 8178:20045 | /admin/special-routing | Aligned (one tab not drawn) | "Escalated reports" links to Queue › Reports › Escalated with its count; "Escalated reviews" and "Set a rule" not drawn (nothing escalates a review; routing has no rules) | (6e25b1b) |
| Screen/Admin/Settings, Inbox | 8076:16388, 8291:30461 | /admin/settings, /admin/inbox | Aligned | Settings shows the rules read-only and the real integration states | — |
| Screen/Auth/Email, Code | 5348:2789, 5357:2935 | /login | Aligned (+ kept) | "Continue with Google — Coming soon" (asked for; Google sign-in not built) and the sign-up link are ours | — |
| Screen/Onboarding/* | 5369:3079… | /onboarding | Aligned | The idle field keeps the component state set's edge (newer than this frame); availability check as drawn | — |
| Screen/Messages/* | 8296:31219… | /messages | Aligned | — | — |
| Screen/Seller/Overview, Insights | 8190:20643, 8208:22905 | /seller/[id], /seller/[id]/insights | **Aligned** | The store's initial on a grey tile; rail labels; single-star rating cells; coral 2★ bar. Kept: Requests to the administrators, Rating summary report | (latest) |

## Search & filters (surveyed 2026-10-07, live d356750 at 390/1280)

The flow map (7763:9173) fixes the intended interactions: Reviews results → "Most helpful" →
**Sort menu**, "Filters" → **Filters sheet**, "Switch" → product switch sheet; Questions results →
best match / See all / Ask (no sort or filter controls).

| Control | Figma | Code today | Gap |
|---|---|---|---|
| Reviews "Most helpful" | Dropdown Menu anchored under the pill, 3 rows, ✓ on the current one, brand text | Bottom sheet, radio rows ("Review score: Most Helpful", "By date: Latest/Oldest"), Reset + "Sort Reviews" | Pattern (dropdown vs sheet); options: Figma "Newest / Lowest rated" vs code "Latest / Oldest"; API has no rating sort |
| Reviews "Filters" | Bottom sheet with a handle, "Filters" + Reset, chip groups, full-width "Show N reviews" | Sheet with a glyph title + X, radios, budget slider, Category, Reset + "Filter Reviews" | Control style (chips vs radios/slider); groups differ: API supports lens, trust, budget, period, category; it has **no** star-rating, with-photos, verified-buyer, recommends, or variant filter, and no live result count |
| Questions tab | No pills | "All filters" (Time) / "Sort" (Latest/Oldest) radio sheets | Extra controls; layout owned by defense-build-oct6 |
| Sellers tab | "All filters" / "Sort" pills, open state not drawn | Radio sheets | Undrawn — follow the Reviews patterns once chosen |
| Search focus | Recent searches + "Most searched today" | Recent searches only | No trending API |
| Typing | Not drawn | Autocomplete dropdown of products | Functional extra |
| Desktop (≥lg) | No frame | Right "Refine" rail of text links; the pills are hidden | No frame to follow |

Elsewhere in the file the newer screens use the same Menu dropdown (Product/Questions switcher and
sort; admin `Menu/*/Sort`, `Menu/*/Filter`), while older frames keep radio sheets
(RecentReads/Sort open 2236:801, Sheet/Sort reviews 8093:18101). The search page follows the older
pattern, so it is out of date against its own current frames.

## Component states (2026-10-07)

Figma keeps a state set for each control ("Forms & inputs" 7801:9208, "Question Page Components"
7761:7856, "Sheet & popover building blocks" 7808:9171, "Admin Components · States" 8265:27081).
Root cause of the broken ones: the global `:focus-visible` outline was unlayered, so it beat every
Tailwind class — a field that drew its own focus still got a second ring 2px outside and 4px
corners (the home search). It now sits in `@layer base`; each control below draws its own state.

| Figma state set | States | Code | Where |
|---|---|---|---|
| SearchField/Inline 7761:7998 | Default #d1d1d1 edge · Focused 1.5px brand, brand caret, clear | `SEARCH_FIELD_STATES`, `SEARCH_FOCUS`, `SEARCH_INPUT` (components/ui/search-styles.ts) | Home hero, header, /search bar, store keyword search, Choose a review |
| LinkField 6943:925 | Default · Filled · Focus 1px brand edge | `LINK_FIELD_STATES` | Rate a seller, Write Review product link, "add your own" phrase |
| TextField 6808:456 | Default · Hover · Focus · Filled · Error · Success · Disabled | `PUBLIC_INPUT`…, new `PUBLIC_EDGE_STATES` (field-styles.ts) | all public forms (P4/P10) + comment box, store reply/remove, product proposal |
| OtpDigit 6809:457 | Empty · Filled · Active (10% tint, no edge) | OtpInput | sign-in / sign-up code (Active had an extra edge — removed) |
| Chip/Action 7166:4933 | Default dark outline · Active brand outline + #fbede3 tint | SearchFilterBar `outline()` | search pills (Active had no tint — added) |
| Menu/Option 7761:7914 | Selected brand Medium + Check | SortMenu, dashboard History | (History showed selected as a grey fill — fixed) |
| Admin/Input 8265:27239 (Text, Search, Select) | Default · Hover · Focus (brand + 3px halo) · Filled · Error · Disabled | `FIELD_STATES` (console/fields.ts) | every console field and select (8 had their own rings — moved) |
| Admin/TopSearch 8265:27300 | Default grey · Hover 5% · Focus white + edge + halo + Esc · Filled | `TOP_SEARCH_STATES` | console top search, Activity, Q&A answers, reviewers, all reviews, users, seller reviews |
| Admin/ToolbarSearch 8270:28869 | Default · Hover · Focus · Filled | `TOOLBAR_SEARCH_STATES` | list search popovers (ListControls, Inbox, Review queue) |
| Dropdown/Pill 8267:27483 | Default · Hover · Pressed · Open · Disabled | `DROPDOWN_PILL_STATES` | dashboard period, admin category / role / report / support pickers |
| Admin/MenuItem 7958:10889 | Hover 5% · Pressed 9% · Selected Medium + Check, never a fill | `MENU_ITEM` | every console menu (4 showed selected as a fill — fixed) |
| FilterChip / StoreChip / SortOption | Selected | ChipSheet / SortMenu (a9e9398) | search sheets |

Verified at 390/1280 on the local stack (computed styles + screenshots): no outline on any of
them, one brand edge on focus, radius kept; journeys 109/109 (2 skipped by design), unit 628.

NOT DRAWN, so not built: a Hover for SearchField/Inline; a Focus for Dropdown/Pill (keyboard
focus keeps the base ring there).

## Not 1:1 (and why)

1. **Answer Step 2b** "Where's this from?" — no API field for the answer's source.
2. **Ask Step 2** photo — a question has no photo in the API.
3. **Question strip "3D Model"** — no 3D data.
4. **Best-answer label** keeps "Best Answer · picked by the person who asked" (QA-058 + four
   e2e specs) where the frame shows a shorter label.
5. **Mascot bubble copy** — frames show the Tip component's default ("Help users know more about
   the price!"); code shows the real question / step prompt.
6. **Phone text fields are 16px** (QA-036, stops iOS zoom) where frames draw 12–14px; long
   placeholders ellipsize.
7. **Ask idle** shows "Paste Shopee link"; **Ask** pill reads "Submit" (recorded difference).
8. **Answer Step 7** "Post answer" is enabled before a photo (photo optional; Skip does the same).
9. **⋯ menus** — frames draw the trigger, not the menu; contents chosen (Copy link, Report, Remove).
10. **Review page comments** — aligned in 3109645 (sticky Composer, "N replies", separate cards).
    The send button (PaperPlaneRight) is not drawn: the frame shows only the empty pill.
11. **FAB position** — frames put it 24px up; on the question and review pages it rises by the
    composer's height while that bar is docked, so it never covers the pill.
12. **Review page "What people paid"** panel is not in the frame (price-report feature, kept);
    pros/cons sub-labels and icon Experience rows in the frame have no data fields.
13. **Search typing state** (recent searches, "Most searched today") — no API.
13a. **Search filter options** — DONE in step 2 (2026-10-07): every group the frames draw is served by
    the API (`stars`, `photos`, `verified`, `recommends`, `variant`, `sort=lowest` on /reviews/feed;
    `claimed=false`, `min_rating`, `answers_within` and /sellers/count) and offered in the sheets and
    the desktop rail. Kept, not drawn: the ⓘ definitions beside each group (QA-053), the sellers' sort
    note (MQA-033), and our own extra review groups after the frame's. Variant shows only with one
    product chosen (a variant name means nothing across products).
13b. **Every sort is the dropdown Menu** (owner 2026-10-07: "Dropdown, it shouldn't be like pills"):
    search, the review page's comment sort (headed "By rating" / "By date") and the store page's
    review sort (headed "By date" / "Rating" / "Photos"). The radio "Sort" sheet (1591:5408) is gone;
    the Menu opens above its pill when there is no room below.
14. **Search** keeps the People tab, downvotes and Share (functionality).
15. **Write Review**: step 6 takes up to 4 photos (frame: one); step 7 adds the disclosure question;
    Done's blurb explains earning is decided later and omits the frame's illustrative pills; a
    saved draft shows the "Unfinished review" banner (BUG-024) above any step.
16. **SiteFooter** shows on phones; frames end at the content.
17. **Audit complete** (2026-10-07): every screen group above is compared. Overflow sweep: 34 routes
    (public, member, admin, seller) × 320 / 390 / 768 / 1280 px — no horizontal overflow anywhere.

## Verification

- `npx tsc --noEmit`, eslint on changed files, `npm run test:frontend` (628/628) on every push.
- Backend: `tests/test_openapi_contract.py`, `test_structured_answers.py`, `test_qa_engagement.py`,
  `test_qa_gaps.py`, `test_answer_parts.py` — 46 passed (ci DB).
- e2e: `e2e/action-menu.spec.ts` 14 passed, 1 skipped (no store record locally); run method in
  `CLAUDE_PIM_STATUS.md`.
- Browser: each changed screen captured at 390 beside its frame (scratchpad `sbs.py`), and at
  320/1280 for overflow (0) and console errors (none besides blocked external images).

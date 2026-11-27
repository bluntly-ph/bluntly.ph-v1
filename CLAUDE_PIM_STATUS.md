# CLAUDE PIM STATUS (Figma / frontend worker)

## OWNER DECISIONS 2026-10-07 (afternoon) — supersede older notes below

- DEFENSE-DAY RULES LIFTED. The demo review ae1d62d1 (CAPSTONE-DEMO-EARN-001) is no longer
  reserved, and components/search/QuestionMatch.tsx may be edited (PR #20, defense-build-oct6,
  is still open: coordinate edits with it rather than avoiding the file).
- SORT IS A DROPDOWN (SortMenu), never pills or a sort sheet, wherever Figma draws either.
- CI MINUTES: done in f153180 (one hourly maintenance run; remote TEST job manual-only; push
  only on main; docs-only changes run the guard alone).
- DONE (afternoon, all on claude/relaxed-euler-oycbod → PR #21):
  * a71e6b0 every sort is the dropdown SortMenu (comment sort, store sort; sections; flips up).
  * 8e75717 search filters step 2: reviews stars/photos/verified/recommends/variant + Lowest
    rated; sellers claimed=false/min_rating/answers_within; /feed/count, /feed/variants,
    /sellers/count; live "Show N" pills; desktop rail; tests (backend, unit, journeys).
  * Figma audit finished (docs/FIGMA_AUDIT_2026_10.md, item 17 "Audit complete"):
    f92df74 dashboard requirements 3-up; fecd889 Chat link on every dashboard screen, History
    month panels, Performance rows; 9031430 admin chrome; 8f40582 admin tables 20/16px cells,
    bluntly trust mark, /admin/people redirect; be3c199 analytics + activity hydration;
    6e25b1b special-routing Escalated reports tab, activity column, affiliate copy; seller
    console tile/labels/rating cells. Overflow sweep: 34 routes × 320/390/768/1280, none.
- STILL OPEN: GitHub Actions billing (CI cannot run; PRs #20/#21 cannot merge); the owner
  must run docs/release/DEMO_SEED_2026_10_TO_TEST_MONEY.sql in the Supabase SQL editor.

## DEMO SEED → BACK TO VASH'S TEST-MONEY DESIGN (owner, 2026-10-07)

The owner reversed their 2026-10-05 override ("treat the seeded demo values as real money") now the
demo is over: Vash's QA sandbox design (0059) is the rule again — test earnings are `is_test`, no
platform / Honesty Fund share, one per review, named testers only, excluded from revenue and the pool.

- PRODUCTION BEFORE (read-only, admin API 2026-10-07 12:51 UTC): October report revenue ₱8,166.69
  (7 real-flagged demo commissions), money in ₱8,166.69 (invented DEMO-remittance-2026-10), money out
  ₱1,750 (4 PayPal-SANDBOX payouts: @zienxt ₱700, @zaisias / @northpacificfan / @suvango ₱350), still
  owed ₱700 (@zienxt ₱350 + @abelli ₱350). QA testers: @bluntly_ph, @zienxt. The October Honesty Fund
  pool would have been ₱2,450 of money that does not exist.
- OWNER DECISIONS: add @zaisias, @northpacificfan, @suvango, @abelli as QA testers (their rows become
  labelled test credits, history kept); exclude PayPal-sandbox payouts from Money out.
- DATA: docs/release/DEMO_SEED_2026_10_TO_TEST_MONEY.sql (+ _ROLLBACK). 6 rows → test credits exactly
  as qa_sandbox_service.credit writes them; com_demo_zienxt deleted (one test credit per review) and
  its ₱350 taken from @zienxt's wallet; the invented remittance deleted; audit mlog_demorevert2610.
  Testers are added through POST /api/v1/admin/qa-sandbox/testers (audited), not in SQL.
- CODE: financial report leaves sandbox payouts out of Sent / Paid out and shows them apart
  (`sandbox_excluded`; web card "· N sandbox not counted"; PDF row; note).
- REHEARSAL (docs/release/rehearse_demo_seed_to_test_money.py, fresh DB, real seed SQL): before =
  production figures; after = revenue / money in / money out ₱0, 4 sandbox payouts (₱1,750) apart,
  wallets @zienxt ₱0, @abelli ₱350, others ₱0, October real pool ₱0, payouts kept; idempotent; rollback
  restores the seed; re-apply passes.
- QA testers: DONE via POST /api/v1/admin/qa-sandbox/testers (201 ×4): abelli, northpacificfan, suvango, zaisias (+ existing bluntly_ph, zienxt).
- APPLYING the data script: BLOCKED. The Supabase connector holds any statement containing DELETE for a destructive-statement
  approval this session cannot show (proved: a `DELETE … AND false` that matches nothing also times out at 60s; a DO block
  with no DML returns at once). Three attempts timed out; production re-checked after each: UNCHANGED (seeded_left 7,
  test_credits 0, remittance 1, revert log 0, @zienxt wallet 350.00, nothing running). The script is guarded/idempotent, so
  a late run of any held request is harmless. NEXT: owner runs docs/release/DEMO_SEED_2026_10_TO_TEST_MONEY.sql
  (sha256 4587776a…) in the Supabase SQL editor, or approves it in an interactive session; then verify (6 test credits,
  com_demo_zienxt + remittance gone, mlog_demorevert2610, zienxt 0 / abelli 350, Oct revenue/money-in ₱0, fund pool ₱0).

## PRIORITY TASK — ADMIN UPVOTE → EARNINGS REVIEW QUEUE (2026-10-07, branch feat/admin-earnings-review-queue)

Phase 1 done: PR #18 merged at 65e99b5 (completed Figma work), production dpl_GV8q5ryVe6EHwJBHgLMcy2BPHXeb
READY at 65e99b5; live smoke at 390/1280 clean (home, search, question, review, Ask, Answer, Write Review:
all 200, no runtime errors, 0px overflow, FAB on phones).

### Current path in production (traced 2026-10-07, main 65e99b5)
1. UI: the review page's ReviewVoteBar — `canVote` is false only for your own review or a claimed seller
   (app/reviews/[id]/page.tsx), so administrators and super admins see and can press Helpful.
2. API: POST /api/v1/reviews/{id}/vote → vote_service.cast_vote:
   - `_votable_or_404` (published, not removed); claimed seller → 403; own review → 409
     `cannot_vote_own_review`; review row lock; one row per (review, voter) (`uq_review_vote_once`).
   - Snapshot weight = `weight_of(voter)` (trust stage × reputation; Stage 0 = 0, Stage 1 = 0.25,
     halved under 30 days / under investigation). Admin accounts are Stage 0 → weight 0.
   - PR #17 (Zient, 2026-10-06): an administrator's or super admin's UP vote calls
     `earn_gate.nominate` → `earn_eligible_status` none → pending + queue-entry time, in any phase,
     regardless of the community gate. Never approves, never reopens a decision, no payout.
   - Then `earn_gate.maybe_queue` (members' gate, Post-Seeding): Wilson LB ≥ 0.65 on effective n
     from snapshotted weights AND ≥ 3 Stage 2+ voters → none → pending.
   - Vote-network tail records a keyed network hash on upvotes (flags only).
3. Queue: GET /api/v1/admin/review-queue (referral_service._all_queue_candidates: status pending,
   not removed, published or not taken down). UI: Admin → Review Queue (/admin/review-queue).
4. Approval is separate: POST /api/v1/admin/reviews/{id}/approve-earnings (or /reject), from the queue.
   Commissions come later from imports; nothing is created by voting or queueing.
5. `earn_eligible_votes` (EarnEligibleVote) exists as a model but the gate reads review_votes snapshots.

### Conflict to resolve with the owner before changing anything
The 2026-10-07 brief asks for "normal vote weight, no special weight, must not bypass eligibility
rules". With normal weight an admin's vote weighs 0 (Stage 0) and is not a Stage 2+ voter, so it can
NEVER complete the members' gate — that was the original bug. PR #17 (live, Zient's explicit spec)
instead makes an admin upvote a nomination into the queue.
**Owner chose (2026-10-07): keep PR #17's nomination.** No rule change.

### PR #19 (this branch)
- Queue helper line names the admin-upvote route (asserted sentence kept); defense script
  docs/release/DEFENSE_ADMIN_UPVOTE_DEMO.md (CAPSTONE-DEMO-EARN-001 = ae1d62d1…, reserved, unvoted).
- CI "Browser journeys" (db-fast.yml runs only on feat/**, so PR #18's claude/ branch never ran it)
  found two regressions already on main, both fixed here:
  1. Question page lost "About a product" in the Figma strip (df3d60a) → restored (QA-045).
  2. Seller Settings: two quick switches raced two whole-state PUTs; the later click could be lost
     (journey 14b) → saves are sent one at a time, in click order.
  Local db-fast equivalent on a fresh DB: 109 passed, 2 skipped (N, I by design); unit 628; tsc; lint.

## SHIPPING (owner, 2026-10-07): completed audit work goes to main as-is; the audit stays OPEN

This branch (merged with main at e0e6bd9, PRs #16/#17 included) is opened as a PR to main to ship
the completed, tested Figma fixes. The audit is NOT finished. The unfinished dashboard Chat link
stays in `git stash` and is NOT part of the PR.

### PENDING AFTER PRIORITY TASK (do not mark complete)
- Review page remaining work: send-button styling vs drawn pill; "What people paid" not in frame;
  pros/cons sub-labels + icon Experience rows (no data) — see docs/FIGMA_AUDIT_2026_10.md.
- Write Review remaining audit: Done-screen spacing vs frame (illustrative pills omitted), step 7
  disclosure layout, multi-photo step 6 — recorded differences to re-check with the owner.
- Profile / Dashboard / Payout internals (Dashboard, Empty, Loading, Payout + Details/Locked/
  No wallet/Requested/Tips, Performance + Review/Choose review, History, Profile Reviews/
  Comments/Stats) — Dashboard Chat link in stash.
- Admin audit (Overview, Queue, Products, People/Trust, Payouts, Honesty Fund, Reports, Activity
  log, QA Sandbox, Inbox).
- Auth / Onboarding / Messages.
- Remaining Search / Questions work (Search typing state; Search/Questions after
  defense-build-oct6 merges; Search/Sellers; Categories; Store pages).
- Overflow sweep 320/390/768/1280 and the final report table.
- All remaining gaps listed under "Not 1:1" in docs/FIGMA_AUDIT_2026_10.md.

## ⚠ FIGMA AUDIT POSTPONED (owner, 2026-10-06) — ALL ITEMS BELOW ARE PENDING

Owner switched priority to "admin upvote → earnings review queue" (PR #16, branch
`claude/admin-upvote-earnings-queue`, off main; it does NOT contain this branch's audit commits).
Resume the audit here afterwards, in this order:

1. PENDING — Dashboard Chat link (Screen/Dashboard 7833:9536): finished in `git stash`
   ("figma: dashboard Chat link …" on this branch: components/dashboard/DashboardScreen.tsx +
   app/dashboard/page.tsx, getMyUnread → DashboardNav `unread`). tsc + eslint clean; NOT yet
   browser-verified. `git stash pop`, verify at 390/320/1280, commit, push.
2. PENDING — Rest of Profile/Dashboard/Payout internals: Dashboard (5-ring requirement row looked
   cramped at 390 — "Helpfulness Score" label crowds its card), Dashboard/Empty 7855:10383,
   Dashboard/Loading 7855:10750, Payout 7840:9380 (+ Details, Locked, No wallet, Requested,
   Tips), Performance 7848:9542 (+ Review, Choose review), History 8098:17238,
   Profile/Reviews 5446:4328, Profile/Comments 5446:6398, Profile/Stats 5446:6532.
3. PENDING — Admin screens (Overview, Queue, Products, People/Trust, Payouts, Honesty Fund,
   Reports, Activity log, QA Sandbox, Inbox).
4. PENDING — Auth / Onboarding / Messages.
5. PENDING — Remaining Search/Questions screens not owned by defense-build-oct6 (never touch
   components/search/QuestionMatch.tsx while that branch is open).
6. PENDING — Overflow sweep at 320/390/768/1280 and the final report table.
7. NOT TO MAIN YET — this branch's audit commits (through 0088b6e + docs) await owner approval.

## CURRENT — FULL FIGMA 1:1 AUDIT (micro-push mode) — updated 2026-10-05

- Branch `claude/relaxed-euler-oycbod`, rebuilt on `origin/main` cfe22f6 (PR #15 merged).
- LAST PUSHED SHA: 0088b6e (see git log for later micro-pushes)
- Commits: df3d60a question page + thread · cec9984 progress + answer steps · 4ca1da8 rating
  clouds + pros overflow · a2d1125 composer focus ring + 4.1/5.1 marks · a8a54b7 answer Done +
  QAAuthor.avatar_url populated in qa_service._author · fe972bd ask Done spacing · b5a3a40 review page Detail bar + FAB · 9fd0c18 home hero
  ReviewQuoteCard + FAB (FeaturedReviewCard deleted) · 375023d QuickActions on Search,
  Categories, Profile, /u, Dashboard, Insights, History, Store; ActionMenu retired ·
  3109645 review replies: sticky Composer (components/ui/ComposerShell.tsx), FAB auto-lift ·
  276c2cb WR verdict spacing + 320px overflow (shared clouds) · 0088b6e price field focus.
  WRITE REVIEW COMPLETE (all frames in docs/FIGMA_AUDIT_2026_10.md).
- Figma file `lso4Ri4hDaZxvCebhUqlY5`, Page 1 `0:1`. Frame list: scratchpad `figma_inventory.tsv`
  (not in repo; regenerate with get_metadata on 0:1).
- BATCH 1 (Question, Thread, Answer 1–7 + Done, Ask 1/2/Done) COMPLETE.

### Done (verified at 390, question page also 320/1280, no overflow, no console errors)
| Frame | Node | Route | State |
|---|---|---|---|
| Screen/Question | 7731:15601 | /questions/[id] | aligned (Detail bar, strip, sheets, menus, avatars, FAB) |
| Screen/Question/Thread | 7735:8020 | /questions/[id]?reply= | aligned (depth cap, composer) |
| Composer/Progress | 8475:38260 | all composers | 2px #ececec track, orange fill, Figma values |
| Screen/Answer/Step 1–7, 2a.1, 4.1, 5.1, 6 | 7573:8215…9133 | /questions/[id]/answer | aligned (see gaps) |
| Screen/Answer/Done | 7573:9158 | answer done | aligned (decor, spacing, asker photo) |
| Screen/Product | 7651:5805 | /reviews/[id] | bar + FAB aligned; gaps 11–12 |
| Screen/Home | 1902:1504 | / | hero card + FAB aligned; gap 13 |
| Screen/Ask/Step 1/2/2.3/3/4 | 7573:10945, 10506, 10791, 11005, 10886 | /questions/new | aligned except gaps 4, 9 |

### Running e2e locally (this container)
Repo Playwright wants chromium build 1234; /opt/pw-browsers has 1194. Use a throwaway config
`.pim-pw.config.ts` (git-excluded) that spreads playwright.config, sets `webServer: undefined`
and `launchOptions.executablePath: "/opt/pw-browsers/chromium"`, then
`PLAYWRIGHT_BASE_URL=http://localhost:3100 npx playwright test -c .pim-pw.config.ts <spec>`.
(127.0.0.1 blocks Next dev scripts, so pages never hydrate.) action-menu.spec: 14 pass, 1 skip.

### Tests run at 4ca1da8
`npx tsc --noEmit` ok · eslint on changed files ok · `npm run test:frontend` 628/628 ·
backend `tests/test_openapi_contract.py` 9 passed · browser smoke (scratchpad `.pim-shot.mjs`).
Full e2e NOT re-run (best-answer label kept, so QA-058 specs should hold).

### Known remaining mismatches (document in final report)
1. Answer Step 2b "Where's this from?" (7573:8591): no API field for answer source — not built.
2. Mascot bubble: Figma's Tip instance reads "Help users know more about the price!" (component
   default); code shows the real question / step prompt.
3. Phone text fields are 16px (QA-036, stops iOS zoom); Figma draws 14px, so the step 2 note
   placeholder ellipsizes.
4. Ask idle shows "Paste Shopee link" (Figma idle omits it) — kept, functional.
5. Question "3D Model" strip item: no data. Best-answer label text kept (QA-058 + 4 e2e specs).
6. ⋯ menus' contents are not drawn in Figma (Copy link / Report / Remove chosen).
7. Answer Step 7: Figma draws "Post answer" disabled before a photo; code allows posting (photo
   optional, Skip does the same).
8. SiteFooter on phones; no desktop frames for consumer screens.
9. Ask Step 2 "Would you like to share a photo?": no photo on a question in the API — not built.
   Pill reads "Submit" (recorded intentional difference) where the frame's instance says Continue.
10. Questions search cards not re-audited this pass: `defense-build-oct6` is changing
    components/search/QuestionMatch.tsx — re-check after it merges.
11. Review page comments: Figma Composer (7660:6153) is a sticky bottom "Join the discussion..."
    bar and comments are separate cards titled "N replies"; code keeps the inline textarea +
    "Comment" button and "N comments" (CommentThread). Not converted yet — next candidate.
12. Review page "What people paid" panel is not in the frame (price reports feature; kept).
    Pros/cons sub-labels and icon Experience rows in the frame have no data fields.
13. Home search field 16px on phones (QA-036) vs 12px Light drawn.

### NEXT (exact)
- Owner priority (2026-10-06): 1 review comments DONE (3109645) → 2 Write Review DONE (0088b6e)
  → 3 Profile/Dashboard/Payout internals (NEXT) →
  4 Admin → 5 Auth/Onboarding/Messages → 6 remaining Search/Questions not owned by
  defense-build-oct6 (do not touch components/search/QuestionMatch.tsx).
- Local stack after a container restart: `service postgresql start; service redis-server start`,
  then the API (uvicorn, env in the summary above) on :8000 and `next dev -p 3100`.

## Figma access

- 2026-10-05 (P1, P2): connector was `needs_reconnect`; that work used recorded frame notes only.
- 2026-10-05 (P3 on): connector working (whoami: Zienxt, pro). File `lso4Ri4hDaZxvCebhUqlY5`,
  "Page 1" (0:1). Frames were renamed since the code's notes: "Reviewer Page - Step N" is now
  `Screen/WriteReview/Step N`; the old "Review page" (4218:1196) no longer exists — the published
  review is now `Screen/Product` (7651:5805).

## FIGMA MAP — review flow (read 2026-10-05)

| Frame | Node | Code (0-based `step`) |
|---|---|---|
| Step 1 / 1 · results / 1.1 / 1.2 | 2403:762, 4431:442, 4435:863, 4435:1015 | 0 product + discussion |
| Step 2 / 2.1 / 2.2 | 4435:1092, 4493:2972, 4508:4053 | 1 verdict |
| Step 3.1–3.6 | 4435:1344, 4508:4202…4374 | 2 stars |
| Step 4 / 4.1 | 4512:5073, 4519:7505 | 3 pros & cons |
| **Step 5 / 5.1** — "No product is for everybody" | **4519:5414, 4519:5811** | 4 who should skip |
| Step 6 / 6.1 — "Show, don't tell" | 4443:555, 4449:692 | 5 photos |
| Step 7 / 7.1 — "Final touch" | 4452:748, 4512:4973 | 6 title + disclosure + preview |
| Price / Price/Filled | 4550:8677, 4550:8771 | price capture card |
| Done — "Your review is now live!" | 4550:8882 | done screen (preview + latest stats) |

"Step 5" in Figma is literally the who-should-skip step; it has no media and no stats. The
owner's "Step 5 / final review" with review media and latest stats can only be Step 7 / 7.1 +
Done (the last frames, the only ones with a review preview and "Your latest stats:"). Treated
as such; flag to the owner if they meant the who-should-skip step.

## Checkpoint P1 — multiple review photos, NO PHOTO = NO DEFAULT PHOTO (2026-10-05)

- REMOTE SHA STARTED FROM: dfd41b5; rebased onto cd581be (RESEARCH R1, review media backend)
- FIGMA INSPECTED: none (blocked, above). Used the recorded notes for "Reviewer Page -
  Step 6" (4443:555) / 6.1, "Reviewer Page - Step 7" (4452:748), "All done" (4550:8882),
  "Review page" (4218:1196: the hero carousel with a "1/3" badge and dots), and the
  seller review's multi-photo tiles (RateSellerForm PhotoTiles).
- TASK:
  - Composer photo step (0-based step 5 = frame "Step 6") takes several photos:
    multi-select, crop each in turn (QA-062: only the crop is uploaded), upload
    one POST /reviews/photo per photo, per-photo uploading / error tile with Retry
    and Remove, Replace and Remove on each placed photo, Clear all, "n of 4 photos".
    No reordering (no frame draws one).
  - Limit 4 = MAX_REVIEW_PHOTOS from the backend contract (same as store reviews and answers).
  - Draft holds `photoUrls: string[]`; older drafts' single `photoUrl` is adopted, nothing else.
  - Submission sends `photo_urls` (ordered) and `photo_url` (= first, or null).
  - Skip clears every photo (photoUrls: []) and abandons uploads/crops in flight;
    submission sends `photo_urls: []`, `photo_url: null`.
  - Step 7 preview card / All done: first photo plus a "+N" badge; zero photos keep
    the empty glyph. Never the product image.
  - Published review page: one photo stays a still; several draw the Figma carousel
    (N/M badge, dots, scroll-snap swipe); zero = "No photo with this review".
  - Answer flow keeps its single photo (max=1) on the same component.
- FILES: components/reviews/review-media-model.ts (new; replaces photo-step-model.ts),
  components/reviews/ReviewPhotosField.tsx (new), components/review/ReviewPhotoCarousel.tsx
  (new), app/reviews/new/WriteReviewForm.tsx, components/reviews/ReviewPreviewCard.tsx,
  components/reviews/composer-gate-model.ts, components/review/ReviewDetail.tsx,
  components/qa/AnswerFlow.tsx, lib/reviews.ts (type), e2e/qa-round3-journeys.spec.ts,
  tests/frontend/{review-media,round3-models,composer-gate-model}.test.mjs
- VISUAL VERIFICATION: a throwaway harness page (not committed) mounted the real
  ProductPhotoCard + ReviewPreviewCard + ReviewPhotoCarousel with mocked uploads, driven
  by Playwright at 320 / 390 / 768 / 1280: empty, cropping, 3 photos, an upload error
  then Retry, remove one, Clear all, one photo, Skip after selecting (payload empty),
  long file names. No horizontal overflow, no page errors. Screenshots read; the tile
  row moved to a three-up grid after the first pass wrapped "Add more" at 390.
  NOT compared against Figma (blocked).
- TESTS: frontend 595 passed; tsc clean; eslint clean on touched files. The composer
  e2e journey (QA-062/063) was updated to the new labels and now also asserts
  `photo_urls: []` on Skip; not run here (no local API stack in this session).
- RESEARCH DEPENDENCIES: none open for this task.
- FIGMA RE-CHECK when the connector is back: photo step with several photos (tile size,
  Replace/Remove affordances, Clear all), the "+N" badge on the preview card, the
  carousel badge/dot styling, and which frame the owner means by "Step 5 / final review".
## Checkpoint P2 — the one photo swap edits the whole set (2026-10-05)

- REMOTE SHA STARTED FROM: 1679b43
- TASK: "Replace photo (once)" PATCHed a single `photo_url`, which the contract reads as
  a set of one, so on a multi-photo review it would have silently dropped photos 2-4.
  It now opens the same ReviewPhotosField seeded with the review's photos: keep, remove,
  replace, add; "Save photos (uses your one swap)" PATCHes `{photo_urls}` in order.
  Save is disabled while unchanged, empty (422 photo_required) or uploading. A review
  with no photos offers "Add photos (once)".
- FILES: components/review/ReviewThreadPanel.tsx, app/reviews/[id]/page.tsx
- VISUAL/BEHAVIOUR: harness at 390, mocked PATCH: unchanged → Save disabled; remove
  photo 2 of 3 → PATCH {photo_urls:[1,3]}; success notice; no page errors.
- TESTS: tsc, eslint clean; frontend suite unchanged.

## Checkpoint P3 — final review preview is the ReviewQuoteCard; published gallery per Figma (2026-10-05)

- REMOTE SHA STARTED FROM: 040ab1c (origin unchanged)
- FIGMA INSPECTED: Step 5 (4519:5414), Step 6.1 (4449:692), Step 7 (4452:748), Step 7.1
  (4512:4973), Done (4550:8882), ReviewQuoteCard set (7702:7587; Photos=Yes 7702:7585,
  Photos=No 7702:7586; placed 7804:9249 / 7804:9287), RateSeller Step 3.3 (4652:12635, photo
  tile + "Add more"), Screen/Product (7651:5805) → Gallery (7651:5840).
- FINDINGS vs P1:
  - Step 7 / Done no longer use the tilted ReviewCard with a 100px media square; they place
    ReviewQuoteCard: white, r16, p16, gap12, 36px avatar, name 12 Medium + age 12 ExtraLight,
    stage (bluntly mark + level name) · Honesty Score, title 16 Italic in quotes, up to four 72px
    r12 thumbnails 6px apart with "+N" over the 4th (45% black), reactions (ArrowFatUp, ChatCircle).
    → implemented `components/reviews/ReviewQuoteCard.tsx`; Step 7 and Done use it. Zero photos =
    Photos=No (no media row at all). The tilted ReviewPreviewCard stays only where its own frames
    still use it (Ask a question, Rate seller).
  - Published gallery: radius 12 (was 16), count pill #8c8c8c 13x7 r20 12px #f2f2f2 at 12/12, pager
    = #8c8c8c 20px pill 24px above the bottom with 8px dots on a 12px pitch, INSIDE the photo (P1
    had orange dots below it). → restyled ReviewPhotoCarousel; single-photo / no-photo hero r12.
    Frame draws all dots alike; inactive dots dimmed to 50% so the pager reads (visual decision).
  - Photo step: no multi-photo composer frame exists. RateSeller Step 3.3 confirms the tile +
    "Add more" language P1 used; P1's three-up fluid grid (≈111px at 390 vs the seller frame's 120px)
    is kept so four photos fit one row. Crop, Replace/Remove, Clear all, "n of 4", per-photo error
    have no frame; they keep the design system's tokens. Skip label matches Step 6.1.
  - Stats on Done: already real (GET /users/me/dashboard?range=90d), labels match the frame.
- REAL DATA: card stage + score are the signed-in reviewer's (/auth/me reputation_score,
  trust_stage, trust_level_name, now passed through PanelUser); age "now"; counts 0; the frame's
  "Earned ₱45.50 today" and question pills are sample annotations and are not drawn.
- FILES: components/reviews/ReviewQuoteCard.tsx (new), app/reviews/new/WriteReviewForm.tsx,
  app/reviews/new/page.tsx, components/site/ProfileNavPanel.tsx (optional trust fields),
  components/review/ReviewPhotoCarousel.tsx, components/review/ReviewDetail.tsx
- VISUAL: harness (not committed) at 320/390: card with 0/1/3/6 photos, empty title, missing
  stage/score, 60-char username, unbroken long title; carousel 1/3. Compared with the Figma
  screenshots of 7702:7585 and 4550:8957; no overflow, no page errors.
- TESTS: frontend 595 passed; tsc and eslint clean.
- NOT DONE HERE: the rest of `Screen/Product` (the published review is now a white card with a
  product "Hero" and Price history / 3D model / Ask a question tools) — only its Gallery was
  applied. Recorded as a follow-up; 3D model stays out (owner rule).

## Checkpoint P4 — shared public input states from Figma TextField / FormField (2026-10-05)

- REMOTE SHA STARTED FROM: 377360e (origin unchanged)
- FIGMA INSPECTED: TextField set (6808:456: Default, Hover, Focus, Filled, Error, Disabled,
  Success), UsernameField (6818:488 / Taken 6818:477), FormField + PasswordField descriptions,
  "Forms & inputs" section (7801:9208), Sheet/Product/ReportPrice/Error (8422:35520). Admin
  Input/Textarea (8265:27081) were already implemented on 2026-10-04 (components/console/fields.ts)
  and were not changed.
- FINDING: public bordered fields were drawn five different ways — 40/48/52/53px, focus as a 2px
  outer ring, an inset shadow or a border, white or grey fills, almost no hover/disabled/error —
  and the global :focus-visible outline (unlayered) doubled the focus ring and squared corners.
- TASK: `components/ui/field-styles.ts` (PUBLIC_INPUT / _TEXTAREA / _SELECT / _LABEL / _HINT,
  PUBLIC_FIELD_STATES for frame-specific shapes) + `components/ui/FieldMessage.tsx` (error with
  Warning, success with CheckCircle — FormField: colour never alone). TextField rebuilt on them
  (adds `success`; `fieldSize` removed — the component set snapped every field to 48/16).
  Migrated: signup, onboarding (username Success/Checking now TextField states), ClaimSellerForm,
  ReportPriceForm (white per its sheet frame), RequestForm, PayoutDetailsForm, NewMessageForm select.
  `.public-field:focus-visible` opts out of the global outline, as `.console-field` does.
- LEFT AS DRAWN (their own frames, not TextField): composer cards (white + card shadow, Steps 1-7),
  search pills, OTP boxes, Messages composer (orange border, 8296:31389), seller-review inline reply.
- VISUAL/BEHAVIOUR: harness at 390 — computed borders: default rgba(32,32,32,.3), hover .5, focus
  rgba(239,88,33,.8) with no outline and 12px radius, error #d80027 (also while focused), success
  #1faf38, disabled #f2f2f2 + .1 border + 50% text, read-only #f2f2f2; all 48px / 16px; Tab skips
  disabled; aria-invalid + aria-describedby resolve to the message. No page errors.
- TESTS: frontend 595 passed; tsc, eslint clean.

## Checkpoint P5 — Admin Overview to v4 (2026-10-05)

- REMOTE SHA STARTED FROM: db5ec7c (origin unchanged)
- FIGMA INSPECTED: Screen/Admin/Overview v4 (8444:38623) — Row/Top (8444:38628: Card/ReviewQueue
  8444:38629, Card/NeedsAttention 8444:38688), Row/Middle (8444:38776: Card/Inbox 8444:38777,
  Card/Activity 8444:38818), Row/Money (8444:38851: Card/Money 8444:38852, Card/PayoutCycle 8444:38954).
- CHANGES vs the v3 build: Needs attention in v4's columns (Moderation, Integrity, Money | Catalog,
  Sellers; "Escalated" + Super chip for the Super Admin routing row); new Inbox card; new Recent team
  activity card; new This payout cycle card beside Affiliate earnings; the skeleton gained both.
- REAL DATA: Inbox = GET /admin/inbox?status=open&sort=waiting&size=3 (open = waiting on us; total =
  "N waiting on us"); Activity = GET /admin/activity?limit=5, worded by the Activity log's own verbs
  (moved to components/admin/activity/activity-words.ts, shared); Payout cycle = /admin/payouts/summary
  (to_send_total, to_send_count, failed_count) + SettingsOut.payout_day (next date computed in Manila)
  + /admin/payouts/honesty-fund (current.pool, distributes_on). Each card fails on its own.
- VISUAL DECISIONS: every API attention row is kept (Products to review, Support requests are not in
  v4 but are real counts; dropping them would make "N open" disagree with the API's total). v4's
  "No 3D model yet" (3D not built) and "New seller sign-ups" (seller sign-up DEFERRED — OWNER REQUEST)
  are not drawn. Activity sentences use the log's wording ("approved earnings on"), not the frame's
  sample copy.
- RESEARCH DEPENDENCY: "Below ₱300 threshold" (Card/PayoutCycle) needs a count of members whose
  withdrawable balance is > 0 and < payout_minimum, e.g. `below_minimum_count` on
  GET /admin/payouts/summary (payout_service.summary already walks the wallets). The card draws the row
  as soon as the field exists; until then it is left out, not guessed.
- FILES: app/admin/page.tsx, components/admin/overview/{InboxCard,ActivityCard,PayoutCycleCard,
  OverviewCardHeader}.tsx (new), overview-model.ts (new), NeedsAttentionCard.tsx,
  components/admin/activity/activity-words.ts (new; ActivityScreen imports it), AdminSkeletons.tsx,
  tests/frontend/admin-overview-v4.test.mjs (new, 4)
- VISUAL: harness at 1280 and 390 with fixtures (incl. long store/product names, null and empty
  states, skeleton) compared with the v4 screenshot; no overflow, no page errors.
- TESTS: frontend 599 passed; tsc, eslint clean.

## Checkpoint P6 — Price History sheet / window (2026-10-05)

- REMOTE SHA STARTED FROM: d1597a3 (origin unchanged)
- FIGMA INSPECTED: section "Price history & 3D model · mobile" (8395:34272) and "· desktop"
  (8395:34275): Sheet/Product/PriceHistory (8375:32412) + /30D /1Y /All (8460:36440/36484/36528),
  /Loading (8375:32513), /Empty (8375:32583), /Error (8375:32647); Overlay/Product/PriceHistory
  (8372:32116) + states. Placement: Screen/Product (7651:5805) "Price history" product tool.
  3D model frames in the same sections NOT built (owner rule).
- TASK: `components/product/PriceHistorySheet.tsx` — native <dialog>: bottom sheet (handle, chips) on
  phones, 760px window (segmented range, legend beside it, tiles in a row, footer) from md. Chart from
  the real series: 3 round gridlines, Shopee #EF5821 solid / Lazada #3771C8 dashed 5 4, lowest point
  ringed with its tip under it, hover tip on the nearest point, 4 date ticks, sr-only table. Tiles:
  Latest report, Lowest (green), Highest, Usual price (median of the range). States: ready, range with
  no points ("Try a longer one"), single report, Empty (incl. pending count), Error with Try again
  (refetches /products/{id}/prices) and Loading (shared skeleton). Range chips are a radio group with
  arrow keys. The review page's "Price History" pill now opens it at every width (it reuses the
  page's /prices read; the inline panel and report form stay).
- `components/product/price-history-model.ts` (pure): inRange, priceStats, comparisonLine,
  priceTicks (smallest round step covering the data: 1099–1449 → 1000/1250/1500), dateTicks, dayMonth.
- DATA: GET /products/{id}/prices as it is (no range param — the range filters the series client-side;
  not a RESEARCH dependency). Nothing below `sufficient`; nothing invented.
- VISUAL DECISIONS / INTENTIONAL DIFFERENCES: the frames' copy describes a scraper ("Checked daily from
  public listings", "We start tracking once a listing is linked", "Now … lowest today", "Open on
  Shopee · ₱1,249"). Prices here are buyers' checked reports, so: "Latest report" tile, the footer says
  "What buyers here reported paying, checked by an administrator. Not a listing price.", the empty
  state says history starts with the first checked report, and "Open on <marketplace>" carries no price
  and appears only when the review has that listing link. Frame draws all range chips; arrows added.
  Also fixed: ICU's "Sept" in the Overview payout date (fixed month names, test added).
- FILES: components/product/PriceHistorySheet.tsx, price-history-model.ts (new),
  components/review/ReviewDetail.tsx, app/reviews/[id]/page.tsx, components/admin/overview/overview-model.ts,
  tests/frontend/price-history-sheet.test.mjs (new, 4), tests/frontend/admin-overview-v4.test.mjs
- VISUAL: harness at 390 and 1280 compared with 8375:32412 / 8372:32116 / Empty / Error / Loading;
  keyboard (Enter opens, arrows change range, Escape closes); no overflow, no page errors.
- TESTS: frontend 603 passed; tsc and eslint clean (whole app/components/lib).

## Checkpoint P7 — published review to Screen/Product (2026-10-05, RESEARCH offline)

- REMOTE SHA STARTED FROM: 1b395e8 (origin unchanged)
- FIGMA INSPECTED: Screen/Product (7651:5805) — Hero/ProductPanel (7651:5807, 7660:5862; ProductPanel
  7659:6042, ProductTool 7659:6007), Review/Card (7651:5839: Author 7660:5901, Review/Top + Lead 7651:6027/
  6028, RatingMeta 7659:6243, Rating 6805:783, Gallery 7651:5840, Section/Verdict 7651:5849, Pros & Cons
  7651:5852 with Attribute 7659:5998, Experience 7651:5887, Not for 7651:5905, General info 7651:5908,
  ActionBar 7659:6160). No desktop review frame exists; desktop keeps its layout and gets the same card.
- CHANGES: ProductPanel on every width (40px product thumbnail — product context only — name, Price history
  and Ask a question tiles; no 3D tile). The review is one white r24 card: shared AuthorHeader (36px avatar,
  name + age, bluntly-mark stage · Honesty Score), the title as the reviewer's words in 20px Medium, RatingMeta
  (20px stars · verdict preset, keeps data-verdict), Gallery, sections with 12px trust-blue labels in the frame's
  order (Verdict quote, Pros & Cons as Attribute circles on #f2f2f2, Experience = discussion with
  id="review-body", Best for, This is not for, General info = price paid), then the existing ActionBar.
- PHOTO RULE: zero photos now draws NO media area (the grey "No photo with this review" box is gone — owner
  rule restated 2026-10-05, matching ReviewQuoteCard Photos=No). One = the still, several = the carousel.
  Verified: the only product image on the page is inside the ProductPanel.
- SHARED: components/review/AuthorHeader.tsx (new; the Figma Author) now used by ReviewQuoteCard and the review
  page; PriceHistorySheet takes `triggerContent` so the ProductTool tile opens it.
- KEPT: votes, comments, Shop / listing link / "No shop link", share, report, takedown/rejection notices,
  photo-provided + disclosure, telemetry ids, orange phone bar and its overflow menu, md overflow menu.
- FILES: components/review/ReviewDetail.tsx, components/review/AuthorHeader.tsx (new),
  components/reviews/ReviewQuoteCard.tsx, components/product/PriceHistorySheet.tsx
- VISUAL: harness with ReviewDetail + fixtures at 320 / 390 / 768 / 1280 (0, 1, 3 photos; 60-char username,
  unbroken title, long product name, long URL): no overflow, no page errors; keyboard Tab → Price history →
  Enter opens → Escape returns focus.
- TESTS: frontend 603 passed; tsc, eslint clean.

## Checkpoint P8 — Ask-a-question Done preview (2026-10-05)

- FIGMA INSPECTED: Screen/Ask/Step 3 "Now, we wait.." (7573:11005), Step 4 (7573:10886, product search —
  no preview). Step 3 places ReviewQuoteCard Photos=No.
- CHANGES: AskQuestionForm Done step uses ReviewQuoteCard (question in quotes, asker's stage + Honesty Score
  from /auth/me via PanelUser, zero counts) instead of the tilted ReviewPreviewCard; the product's image is
  no longer drawn in the card's media slot (a question has no photo). Blurb copy per frame ("other buyers").
- FILES: components/qa/AskQuestionForm.tsx, app/questions/new/page.tsx
- TESTS: frontend 603; tsc, eslint clean. Card already checked at 320/390 with long text (P3/P7).

## Checkpoint P9 — Rate-seller Done preview; one preview card (2026-10-05)

- FIGMA INSPECTED: Screen/RateSeller/Done (4652:12914) — ReviewQuoteCard.
- CHANGES: RateSellerForm Done step uses ReviewQuoteCard (title in quotes, reviewer's stage + Honesty Score
  from /auth/me, zero counts, the reviewer's own photos as Photos=Yes thumbnails; none → no photo row).
  `components/reviews/ReviewPreviewCard.tsx` (the old tilted card) had no consumers left and is deleted:
  the review composer, Ask a question and Rate a seller previews are now one component (ReviewQuoteCard,
  built on the shared AuthorHeader).
- FILES: components/sellers/RateSellerForm.tsx, app/sellers/rate/page.tsx, components/reviews/ReviewPreviewCard.tsx (deleted)
- TESTS: frontend 603; tsc, eslint clean.

## Checkpoint P10 — three more fields on the shared states (2026-10-05)

- Substantiation answer, Ask-the-store question (textareas) and Request-a-product name (input) moved from the
  old hairline-shadow + 2px ring field to PUBLIC_TEXTAREA / PUBLIC_INPUT (Figma TextField states). The two
  textareas now set aria-invalid + aria-describedby and use FieldMessage (Warning glyph) for their error.
- Left as drawn by their own frames: review/takedown/delete dialogs and the answer composer (white card +
  card shadow), the Messages composer, OTP boxes, search pills.
- FILES: components/sellers/SubstantiationForm.tsx, components/sellers/AskSellerQuestionForm.tsx,
  components/requests/RequestProductField.tsx
- TESTS: frontend 603; tsc, eslint clean.

## Checkpoint P11 — review replies to Screen/Product Body (2026-10-05)

- FIGMA INSPECTED: Screen/Product → Body (7651:5838): Section/Header (count + Chip/Action sort), ReplyCard
  (7651:5951), Author Type=Reviewer/Seller (7659:5991), SellerReply (7659:6109), VoteBar (6958:944).
- CHANGES: CommentThread — the full-bleed hairline is gone; the count in 16px Medium beside the sort chip,
  which now names its order ("Most helpful" / "Least helpful"); each thread a white r16 ReplyCard (p20,
  16px apart); comments use the shared AuthorHeader (stage · Honesty Score; New account chip; overflow menu
  unchanged); body 14px Light on 1.5; actions 24px apart; a claimed seller's reply sits in the grey
  SellerReply panel and reads "Seller · ✓ Claimed" (AuthorHeader `seller`), other replies keep the indent
  connector. Removed comments keep their tombstone.
- KEPT: votes, reply (two levels), share, delete confirm, report/follow/save menu, collapse, sort sheet,
  composer, `#comments` and `#comment-<id>` anchors.
- FILES: components/review/CommentThread.tsx, components/review/AuthorHeader.tsx
- VISUAL: harness at 320 / 390 / 1280 (seller reply, removed parent with live reply, 60-char username,
  long URL): no overflow, no page errors. e2e sort specs checked: none target the comment sort.
- TESTS: frontend 603; tsc, eslint clean.

## Checkpoint P12 — Screen/Question/Thread (2026-10-05, RESEARCH offline)

- REMOTE SHA STARTED FROM: 089f281 (origin unchanged)
- FIGMA INSPECTED: Screen/Question/Thread (7735:8020) — ThreadContext (7735:8031), ThreadSheet (7735:8035),
  EarlierReplies (7736:8212), Root/Reply/Thread/Rail (7735:8036 …), Continue (7735:8241); Author 7659:5991,
  ActionBar compact, VoteBar 6958:944.
- MAP → CODE: Author → the question page's local Author now renders the shared AuthorHeader (stage · Honesty
  Score; seller variant "Seller · ✓ Claimed"; "· Edited" badge) — no second author header. Reply/Thread/Rail →
  ReplyItem + Rail (unchanged rails, 12px / 1.5px #d9d9d9). Continue → new: past THREAD_MAX_DEPTH (3) rails, a
  reply with more below ends in "Continue this thread · N more replies" (N = every descendant). ThreadContext +
  ThreadSheet + EarlierReplies → new ThreadView on the question page at `?thread=<reply id>#thread`: "Thread
  started from" card with the answer (Author, text, "View full discussion" → `#reply-<id>`), then the white
  top-r24 sheet with "Show N earlier replies · names" (→ the topmost ancestor's thread) and the focused reply
  with its own three levels. "Reply (n)" shows a reply's direct-reply count, as drawn.
- DATA: built from the replies the page already loads (question-thread-model `focusThread`, `descendantCount`;
  cycle-safe). No API change, no RESEARCH dependency. An unknown `thread` id falls back to the normal page.
- KEPT: voting (VoteBar, own-vote guard, sign-in redirect), reply composer at every level, Remove (own/staff),
  best answer card + "picked by" line, Pick as Best Answer, Share, seller answers, edited marker, `#answer-*`,
  `#reply-*`, data-testid best-answer / answer / thread / reply-toggle / reply-submit. The page's question
  header, reactions and Notify me are unchanged (the frame's ThreadView sits under them).
- NOT IN THE PRODUCT, NOT INVENTED: removed/tombstone replies (the API deletes), new-account chips on Q&A.
- FILES: components/qa/QuestionThread.tsx, components/qa/question-thread-model.ts, app/questions/[id]/page.tsx,
  tests/frontend/question-thread-view.test.mjs (new, 3)
- VISUAL: harness at 320 / 390 / 768 / 1280, normal and `?thread=` (best answer, seller answer with a long store
  name + edited, a 5-deep chain, 50-char username, long URL, unbroken word): no overflow, no page errors; prose
  wraps with overflow-wrap:anywhere (no break-all); keyboard Tab reaches "Continue this thread".
- TESTS: frontend 606 passed; tsc, eslint clean.

## DEFENSE DEMO PREP — 2026-10-05 evening (production read-only discovery; no production writes by PIM)

### Production facts (read-only, Supabase)
- Reviewer perezgyber@gmail.com = e9549322-2b5d-4f74-bcae-0c5998bff7a6 (@zienxt, "viole"): role user, stage 1,
  score 0.00, wallet ₱0.00, no payout account, 7 reviews (2 published, 0 fund-routed), 0 commissions, 0 payouts.
- Admin bluntly.ph@gmail.com = b9b2f61d-192a-44eb-ad60-627e1d518be0 (@bluntly_ph): super_admin; the only QA tester.
- Platform: 0 commissions, 0 remittances, 0 payouts, 0 Honesty Fund rows; 298 affiliate postbacks (234 unattributed).
- honesty_fund_distribution: the scheduler completed the 2026-10 period on 1 Oct (nothing to distribute), so
  Activity → Run now this month answers skipped_already_completed.

### Scenario A — payout request (owner chose: done in the live UI by the owner)
- Path: qa_sandbox_service (owner decision 2026-09-27): a Super Admin names a QA tester; an admin credits one of
  the tester's published reviews with an is_test commission (default ₱350, max ₱1,000, ONE per review via
  uq_commission_one_qa_test), cleared at once, no platform/fund share (ck_commission_test_no_revenue), audited
  (qa_test_credit), tester notified; refused on paypal_live. request_cashout calls no provider: payout
  `scheduled`, wallet debited, cashout_request audit; only an admin's batch submission moves money, and a live
  batch skips anyone holding test money.
- @zienxt has 2 published reviews → 2 credits. The UI's cashout withdraws the whole cleared balance, so credits
  of ₱350 + ₱250 give a ₱600 request.

### Scenario B — Honesty Fund (owner chose: prove locally, show the live page)
- Production cannot be made distributable legitimately: the pool is the previous cycle's REAL commission fund
  share (production has none; test earnings are excluded by design); eligibility needs a fund-routed review with
  ≥ 4 people of trusted up-vote evidence; there is no Distribute button by design (Activity → Run now, Super Admin,
  and this month's period is already completed); HONESTY_FUND_DISTRIBUTION_ENABLED defaults off (§14).
- PROOF on a disposable copy of the local defense seed (dropped afterwards), real code path
  internal_cron.run_task("honesty_fund_distribution", source="admin") = the Run now button:
  - cycle 2026-09, pool ₱1,515.60 (real seeded commissions; test earnings' share 0), 4 eligible reviews:
    @kristinev score 5.0472 → ₱480.78; @trisha_navarro 4.4204 → ₱421.07; @dennis_ocampo 3.2694 → ₱311.43;
    @mariareyes 3.1736 → ₱302.30. Paid ₱1,515.58, ₱0.02 dust kept by the pool. Each wallet rose by exactly its
    payout; 1 audit row {cycle, pool, recipients: 4}.
  - Run now again → skipped_already_completed; distribute() again → already_distributed; rows, wallets and audit
    unchanged.

## RELEASE PREP — PIM as integration / release worker (2026-10-05, evening; RESEARCH frozen)

### Release head
- origin/defense-build-oct6 = the commit carrying this section (code head bc359af; e766608 before it).
- Backend commits included (git merge-base --is-ancestor): 4284300 structured Q&A validation ✓,
  769c038 Honesty Score override + 0095 ✓, 36492f7 verdict_reason ✓. Not modified.
- Feature work frozen (no Seller Signup, 3D, "Where's this from?", Ask photo, Q&A avatar API, Quick Actions).

### Integration gate (local, against the release head)
- Frontend unit 624/624; tsc clean; `npm run lint` clean; `next build` OK.
- CI browser journey list (db-fast.yml's 11 specs — that workflow does NOT run on this branch, so it was run
  here exactly as CI defines it: fresh Postgres, scripts.e2e_fixtures, APP_ENV=test, console email,
  `next start` on the production build):
  - on e766608: 99 passed / 2 failed — both regressions from PIM's search redesign (lost h2 on /questions
    rows and on review results; phone journeys clicked "All filters"/"Sort" where Figma's ListHeader now
    draws "Filters" and "Most helpful"). Fixed in bc359af (h2 restored; selectors accept both layouts;
    assertions unchanged).
  - on bc359af, fresh fixtures: **109 passed, 0 failed, 2 skipped** (same skips as before).
- Defense walkthrough (fresh defense seed, verify 113/113 READY): **7/7**.
- question-thread.spec: 2/2.
- Spot checks on the production build + defense seed: legacy question answers with words + rating only
  (rating gate holds, steps 2–5 say "Optional"); Reviews search 9 cards + "9 reviews" header; Price History
  opens; Admin People has the Trust Score column with effective scores; override Save disabled without a
  reason; dialog shows System / Admin override / Effective.

### CI / PR
- PR: https://github.com/bluntly-ph/bluntly.ph/pull/13 (defense-build-oct6 → main), open, mergeable, NOT merged.
- e766608: CI (Frontend, Backend no-DB, Backend ephemeral Postgres 17, Production guard) and Defense
  walkthrough rehearsal all green (runs 37335261944 / 37335252231 / 37335261972, head_sha verified).
- bc359af and later: see the final report; CI must be green on the LAST commit before merge.

### Production database (Supabase `byobedbhodhvocgrkrse`, read-only SELECTs only, 2026-10-05)
- CURRENT HEAD: **0085_email_outbox**.
- MISSING: 0086_storage_buckets, 0087_rls_every_table, 0088_function_search_path,
  0089_product_import_action, 0090_appeal_kind, 0091_store_change_requests, 0092_support_waiting,
  0093_message_edits, 0094_review_photos, 0095_trust_score_override. Confirmed absent on production:
  reviews.photo_urls, users.computed_reputation_score, store_change_requests, enum 'product_import',
  support 'waiting_for_seller' / 'store_change'; 4 buckets (0086 adds message-attachments); 11 public tables
  with RLS off — exactly 0087's list (its 12th, email_otps, is already on).
- SPECIAL HANDLING: 0089 and 0092 are `ALTER TYPE … ADD VALUE` inside `autocommit_block()` — alembic runs
  them outside a transaction by itself; the offline SQL shows them standalone between the three transactions.
- SCHEMA RISKS (all low):
  - 0094 backfill: 223 reviews (174 with a photo) — trivial lock. CHECK cardinality ≤ 4.
  - 0095 backfill: 26 users. Between migrate and deploy the OLD code writes reputation_score only, so
    computed_reputation_score can lag until the next trust recompute — harmless (no override exists yet).
  - 0087 RLS: tables are owned by `postgres`, not FORCE'd; the API connects through Supavisor as `postgres`
    (pg_stat_activity) — the owner bypasses RLS, so the API is unaffected. PostgREST roles lose nothing they had.
  - Every new NOT NULL column has a server default: the current production build keeps working on the
    migrated schema (expand-first is safe).
- Reviewable SQL: docs/release/RELEASE_5_MIGRATIONS_0086_0095.sql (alembic offline; no migration inspects
  the DB at runtime, so it matches an online upgrade).

### Release sequence (needs the owner's explicit approval at step 2)
1. Final CI green on the last commit of PR #13 (no further code changes).
2. OWNER APPROVES production migrations.
3. Re-read production: alembic_version = 0085_email_outbox (read-only).
4. Apply, per docs/ENVIRONMENTS.md, from a machine holding the production `.env`:
   `alembic -x allow_production=1 current` (confirm target = production, 0085) then
   `alembic -x allow_production=1 upgrade head`. (Alternative only if the owner asks: run the reviewed SQL file
   through the Supabase connector in its order — three transactions plus the four standalone ALTER TYPEs.)
5. Verify (read-only): head 0095_trust_score_override; count(reviews where cardinality(photo_urls)>0) = 174;
   users.computed_reputation_score = reputation_score for all 26; no public table with RLS off; 5 buckets;
   enum values present; Supabase security advisor clean.
6. Merge PR #13 → Vercel deploys main (frontend + API).
7. Smoke on www.bluntly.ph: /welcome; /search?q=<product> (Reviews + Questions tabs, Price History);
   a review with several photos and one with none (no product-image fallback); a question page and ?thread=;
   answer flow up to the rating gate (staff account, do not post); /admin/reviewers Trust Score column.
8. Rollback: revert the merge (Vercel redeploys the previous build). No DB rollback needed — the schema is
   additive and the previous build runs on it.

### PRODUCTION MIGRATION RUN — 2026-10-05 16:28–16:32 UTC — STOPPED AT 0091 (owner approved option 2: Supabase connector)
- Pre-check 16:28:20: production at 0085_email_outbox; CI green on 657f143 (CI 37340354031 + 37340362811, Defense 37340362879).
- Applied docs/release/RELEASE_5_MIGRATIONS_0086_0095.sql verbatim, in alembic's order, as five pieces:
  - A (tx: 0086, 0087, 0088): OK → head 0088; 5 buckets; no public table with RLS off.
  - B (0089 ALTER TYPE, standalone): OK → 'product_import' present.
  - C (tx: 0089 version, 0090, 0091): OK → head 0091_store_change_requests; store_change_requests exists.
  - D (0092 two ALTER TYPEs, standalone): OK → 'waiting_for_seller' (before resolved), 'store_change' (before general).
  - E (tx: 0092 version, 0093, 0094, 0095): **connector timed out after 60 s; the transaction did NOT commit**
    (head still 0091; no 0093/0094/0095 columns; no lingering session or lock; connector role postgres,
    statement_timeout 2min, lock_timeout 0 — most likely queued behind live-traffic locks on users/reviews).
- Current production state: alembic_version = **0091_store_change_requests**, plus the two 0092 enum values (this
  is exactly where alembic itself stands if 0092's non-transactional block ran and the next transaction failed;
  `alembic upgrade head` resumes from here and the 0092 ADD VALUE IF NOT EXISTS are no-ops).
- Live site after the stop: /, /search, /questions → 200. The running (main) build is unaffected: everything applied
  is additive.
- Retries of E (owner-approved, unchanged): 16:43:40 and 16:50:30 — both timed out at the connector (60 s).
  Diagnosis (read-only): E NEVER REACHED POSTGRES on any of the three attempts — postgres_logs record
  statements A 16:28:54, B 16:29:22, C 16:29:44, D 16:30:18 and nothing from E; pg_stat_statements has no E
  statement; lock monitors during/after each attempt saw no blocked or active session and no lock on
  users / reviews / conversation_messages. Not a database lock: the connector/management API does not deliver
  piece E (A, of similar size, went through). A lock_timeout would not help.
- State after the third attempt (16:51:37): head 0091_store_change_requests; both 0092 enum values present;
  no 0093/0094/0095 objects; no busy session. No further retries via the connector.
- PR #13 NOT merged. Next step (owner): `alembic -x allow_production=1 current` (expect 0091) then
  `alembic -x allow_production=1 upgrade head` from a machine with the production `.env` — it resumes at 0092
  (enum IF NOT EXISTS no-ops) and applies 0093–0095 in one transaction. Then PIM verifies read-only, merges.

### RELEASE 5 SHIPPED — 2026-10-05 ~17:10 UTC
- Piece E applied by the owner through the Supabase plugin (the connector in this session could not deliver it).
- Post-migration read-only verification (17:05): head 0095_trust_score_override; 174/174 legacy photos backfilled
  exactly (photo_urls = {photo_url}), 49 photo-less reviews still empty, 0 product images injected, 0 over 4;
  users 26, computed_reputation_score = reputation_score for 26/26, 0 override values, override nullable;
  score and photo fingerprints identical to the pre-migration baseline; buckets 5; enums 0089 + 0092 present;
  no public table with RLS off (new tables on); all 0086–0095 constraints/indexes/columns present; sanity counts
  unchanged (questions 17, answers 16, products 462, price_history 197, payouts 0, moderation_logs 308,
  seller_claims 5). Security advisor: INFO "RLS enabled, no policy" by design; WARN pg_trgm in public (pre-existing).
- CI green on PR head 5571ccf (CI push 37344089218, CI PR 37344096667, Defense 37344096979).
- PR #13 merged → main a4eee655a9874849ba4f7ab60897827361530e39 (merge commit).
- Vercel production deployment dpl_Difupb15rAafUZ6vSHDh3hWc1nJB (githubCommitSha a4eee65), live ~75 s after merge.
- Live smoke (anonymous): /, /search Reviews + Questions tabs, /questions (17 ThreadCards), a review with photos and
  one without, a question page and ?thread=, a profile with an avatar — 200, no page errors; Price History button
  present; Ask, Answer, /admin, /admin/reviewers → 307 to /login?next=… (signed out). API: feed carries
  photo_urls, backfill consistent; question detail carries requirements and answer.parts; admin API 401 unauth.
  Vercel for the new deployment: 0 runtime errors, 0 error/warning logs, no 5xx (1289×200, 1×404).
- NOT run live (need a production sign-in, email OTP): posting an answer through the structured gate, the Admin
  People page and the Trust Score override dialog, the Admin dashboard. Verified on the production build against
  the local defense seed instead (see the gate above).
- Rollback needed: NO.

### Remaining blockers
- None for release 5. Follow-up: an authenticated live check of the answer flow and Admin People by a staff user.

## Checkpoint P13 — PIM primary frontend owner: structured Q&A, search pages, Admin People (2026-10-05, afternoon)

FIGMA: re-pulled Page 1 LIVE and diffed every frame against the morning cache. All Ask (7573:10506…11005)
and Answer (7573:8215…9158) frames are UNCHANGED. New since the cache: `QuickActions/Button` (56×56 FAB,
x318 y764) on Search/Question/Product/reviewer screens, `Overlay/QuickActions` (8502:40871) and
`/SignedOut` (8511:41142); Honesty Fund, store claim/dispute and Seller Signup frames (not in scope).
Admin Overview v4 ReviewQueue card grew (8444:38629, 467→526 high) and Sellers/Claims gained dispute rows —
NOT re-audited this round.

Commits (all on origin/defense-build-oct6):
- 46a65f9 docs/feat(structured-question-figma-contract) — spec + answer gate (earlier this session)
- f773da3 docs: spec VERIFIED against live Figma (corrections below)
- 680ef3a design(answer-flow-figma): verdict/fit fold with "Change", It-depends reason, Done card
- 7c3ecde design(answer-flow-figma): verdict "Why? (optional)" (on RESEARCH 36492f7 verdict_reason)
- fe9f175 design(questions-search-figma): Questions tab + question lists
- 923fc35 design(reviews-search-figma): Reviews tab
- 21add52 feat(admin-people): Trust Score column, override dialog, real avatars

### STRUCTURED QUESTIONS / ANSWERS (spec: docs/STRUCTURED_QUESTIONS_FIGMA_SPEC.md)
- Frames: Ask Step 4/1/2/2.1–2.3/3 (7573:10886, 10945, 10506, 10601/10696/10791, 11005); Answer Step 1…7 +
  2b + Done (7573:8215 … 9158); Screen/Question 7731:15601; Thread 7735:8020.
- Ask: four multi-select chips, exactly "Experience", "Pros & Cons", "Do you recommend this?", "Is this right
  for me?" (no Rating chip). Selected = 1px orange border + green Plus; no required/optional marker.
- Answer: seven steps, "Step N out of 7" always. Validation:
  - words ≥ 30 and RATING (0.5–5) ALWAYS required;
  - a requested specific is required (experience: usage + expectation; pros & cons: ≥1 each; verdict; fit);
  - unrequested steps optional; photo never required;
  - "It depends" needs a ≥15-character reason whether or not requested (LIVE 5.1: Continue disabled) —
    stored as right_for_you "It depends: <reason>" (no API change);
  - "Why? (optional)" under the verdict: optional, no counter → verdict_reason (RESEARCH 36492f7).
- Answer media: ONE photo (Step 7 draws one slot). Review media stays the separate multi-photo set (max 4).
- Done: ReviewQuoteCard quoting the QUESTION with the asker's Author row, real votes/replies; "View the question".
- Answer card: verdict row with stars; Details: "Why?" (no Figma slot — smallest placement, leads Details),
  Experience, Pros & Cons, "Is it for them?" fit then its reason, photos.
- "Looking for:" chips on cards: NO Figma frame draws them (checked live); RESEARCH's LookingFor kept as the
  smallest treatment; Rating never shown; legacy questions show none.
- Backend contract: implemented by RESEARCH (4284300 rating + parts 422s; 36492f7 verdict_reason).
- Open (owner): Step 2a vs 2b "Where's this from?" (both "Step 2 out of 7"; 2b not built, no API field);
  the Ask "Would you like to share a photo?" tile (no API field).

### SEARCH — Questions tab (Screen/Search/Questions 7718:12930) and question lists
- Product card (ProductSwitcher 7702:7501, shared with Reviews): 14px Medium name; ProductLink "Price History"
  (opens the shared sheet, read lazily on first open); Switch pill as drawn; StatStacks 16 Medium / 10 Light;
  no shadow. "3D Model" NOT drawn (no product has one; owner: do not build 3D).
- Best match: 18px SemiBold; answer box #f9f9f9/#e9e9e9/18px with the shared Author row (was a trust pill);
  "Read what N others said" with overlapping 20px avatars of the other answerers.
- Lists (/search Questions tab without question words, and /questions): ThreadCard 7761:7892 (the old
  QuestionPreviewCard 7158:4877 is gone from the file). Real data only.

### SEARCH — Reviews tab (Screen/Search/Reviews 7693:7336)
- ReviewQuoteCard results: Author row, quoted title, up to 4 of the reviewer's own photos (+N), reactions.
  ReviewListRow removed (unused). NO PHOTO = NO DEFAULT PHOTO holds (Photos=No card).
- Reactions stay LIVE (QA-027/028) in the frame's styling: Helpful, Not helpful, comments, Share
  (INTENTIONAL DIFFERENCE: the frame shows up-votes + comments only).
- With a product chosen: ListHeader "N reviews" + "Most helpful" (current order) + "Filters" chips over the
  existing sheets. Without a product the "All filters" / "Sort" pills stay (e2e journeys unchanged).

### ADMIN PEOPLE (Screen/Admin/People 7998:11693, Person 8005:11974)
- Column order: Person, Account, Role, Trust Score, Published, Status, Joined, Action.
- Trust Score = backend effective `reputation_score`; "Override · system N" when overridden. Never computed.
- Person page: Trust Score line; Actions → Set / Change / Clear Trust Score override (ConfirmDialog): System
  score, Admin override, Effective score; new score 0–100 (two places) + reason ≥3; PUT trust-score.
- Avatars: components/ui/Avatar is the ONE avatar (own photo, initials when null or failing to load); used by
  AuthorHeader, PersonCell, the person header, ThreadCard, OthersSaid.
- Trust labels: the stage names come from trust_stage (RESEARCH: the score never moves the stage) — the
  frontend shows trust_level_name / the stage as sent; it maps nothing from the score.

### Verification
- Local stack this round: Postgres 16 + defense seed (113 steps OK) + API on :8000, web on :3100. Every changed
  screen checked at 320/390/768/1280: no horizontal overflow, no page errors (long names, long product titles,
  unbroken words). Q&A answer flow additionally checked on a harness with a mocked POST.
- Frontend unit tests 624 passed; tsc and eslint clean at 21add52.
- Seen once, not reproduced: a dev-only "Router action dispatched before initialization" page error on
  /admin/reviewers at 1280 right after load (Next dev runtime; no user action had happened).

### Remaining CURRENT-FIGMA mismatches (precise)
- Search tabs: the app has a fourth "People" tab and the "All filters"/"Sort" pills on the Questions tab;
  neither is in the frames (existing features, kept). Desktop: no Search/Question/Answer desktop frames exist.
- ThreadCard: "N here now", the reply teaser, up-votes and participant faces not drawn (no list-API data).
- Asker/answerer avatars on Q&A cards are initials: QAAuthor has no avatar_url.
- QuickActions/Button + Overlay/QuickActions (new): the existing ActionMenu FAB was not re-audited against them.
- Admin Overview v4 ReviewQueue card and Sellers/Claims dispute rows changed in Figma: not re-audited.

## OPEN / NEXT

- RESOLVED: "Below ₱300 threshold" — RESEARCH c12a7fa added `below_minimum_count`; PayoutCycleCard already
  renders the row when the field is a number.
- No other backend dependency found this round. Price history uses GET /products/{id}/prices as is.
- Figma follow-ups (frontend only, not started):
  - ProductPanel on the question page if the question detail frame gains one (the component description
    says "review and question detail pages"; only Screen/Product draws it today). ProductPanel lives inside
    components/review/ReviewDetail.tsx — export it when a second page needs it.
- DEFERRED — OWNER REQUEST: seller sign-up frames; every 3D model frame (Screen/Product/3DModel*,
  Overlay/Product/3DModel*, the ProductPanel "3D model" tile).

## FOR RESEARCH (when you are back)

- P13 (2026-10-05 afternoon) backend asks, none blocking:
  - QuestionOut (list): `upvotes`, a top-answer teaser (`top_answer_excerpt` + its author) and participant
    count/faces for ThreadCard; `QAAuthor.avatar_url` so Q&A cards can show real photos.
  - Answer flow Step 2b "Where's this from?" (own / used to own / returned / researched) has no field — owner
    decision first (spec §11 q1).
- P13 frontend files: components/qa/{AnswerFlow,answer-flow-model,structured-question-model,QuestionThread,
  LookingFor}.tsx/ts, components/search/{SearchProductBar,QuestionMatch,QuestionResultRow,SearchFilterBar},
  components/reviews/ReviewQuoteCard, components/review/{AuthorHeader,ReviewVoteBar}, components/product/
  PriceHistorySheet, components/ui/Avatar (new), components/admin/people/* , components/admin/queue/QueueCells,
  app/search, app/questions, app/admin/reviewers, lib/{qa,reviews,landing-data,moderation}.ts (types only;
  lib/api-types.d.ts and docs/openapi.json untouched). components/review/ReviewListRow.tsx deleted.

- Defense head after PIM: see `git log origin/defense-build-oct6` (PIM commits this round: 6d9186e, 33d77d4,
  09789cc, 55b408f, a697c14, plus this status update).
- Frontend components changed this round: ReviewDetail (Screen/Product layout), CommentThread (ReplyCard),
  AuthorHeader (new, shared), ReviewQuoteCard, PriceHistorySheet (triggerContent), AskQuestionForm,
  RateSellerForm, SubstantiationForm, AskSellerQuestionForm, RequestProductField. ReviewPreviewCard deleted.
- Shared API/type files: NOT changed (lib/api-types.d.ts, docs/openapi.json, lib/reviews.ts types untouched
  this round). Pages now pass reputation_score / trust_stage / trust_level_name from /auth/me into the
  composers (app/reviews/new, app/questions/new, app/sellers/rate) — read only, no new fields.
- Behaviour notes: a review with zero photos now renders NO media area on its page (no placeholder).
  The review page's h1 is the review title alone (the product is in the ProductPanel); e2e heading checks
  match by substring and still pass.

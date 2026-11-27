# Independent QA — Round 3 remediation (engineering record)

Source of truth: the tester's workbook `BLUNTLY_QA` (sheet *QA Issues(Main)*, 61 items; retest notes in
*Engineering QA → QA Comment*) plus QA-062..075 from the owner's round-3 brief — **75 items**. The
**Tester Status** column is copied from the workbook and is not changed here; the workbook itself was not
edited. Nothing here says "QA Passed": every fix below waits for independent retest.

Engineering outcomes: `FIXED_PENDING_INDEPENDENT_RETEST`, `NO_CHANGE_REQUIRED_BY_CURRENT_RULES`,
`NOT_REPRODUCIBLE_WITH_VALID_TEST_SETUP`, `INVALID_TEST_PROTOCOL`, `BLOCKED_PRODUCT_DECISION`,
`SUPERSEDED_BY_OWNER_DECISION`.

- Base: `e6f1730` (main = production). Branch: `fix/qa-round3-priority`. Not merged, not deployed.
- Environments: local PostgreSQL 17 only (databases `ci`, `r3`, and a fresh `e2e` built exactly as the CI
  journey job builds it). **TEST was not touched** (defense freeze); production was read only for the
  freeze's availability checks.
- Migrations: `0055_report_comment_counterfeit` (enum values), `0056_priority_tiers` (two tables),
  `0057_round3_interactions` (additive: two notification columns, three small tables, one request
  column). All additive; downgrades tested. Apply to production before deploying, as with 0052–0054.
  **Correction (2026-09-27, before either reached TEST or production):** 0056 and 0057 created five
  tables without the RLS-and-revoke every new table gets (0050, 0052). Both now enable RLS and revoke
  `anon`/`authenticated` on `platform_settings`, `queue_triage`, `notification_receipts`,
  `comment_follows` and `comment_saves`; `test_migration_privileges` now fails any migration from 0050
  on that creates a table without it.
- Payments round (2026-09-27): `0058_qa_sandbox_actions` (enum values) and `0059_qa_sandbox_earnings`
  (`commissions.is_test`). See `docs/QA_PAYMENT_TESTING.md`.
- Figma: file `lso4Ri4hDaZxvCebhUqlY5`, frames read through the connector on 2026-09-26 (node IDs per
  item below; older ones in `docs/FIGMA_ROUND2_VERIFICATION.md`).

## Evidence key

| Tag | What it is |
|---|---|
| **B-r3** | `backend/tests/test_round3_rules.py` (8 tests, 93 cases, no DB), `test_round3_interactions_api.py` (11), `test_round3_catalogue_api.py` (12) |
| **B-tier** | `backend/tests/test_priority_tiers.py` (46), `test_priority_triage_api.py` (6), `test_internal_cron.py` (hourly period, workflow mapping) |
| **F-r3** | `tests/frontend/round3-models.test.mjs` (14) |
| **E-r3** | `e2e/qa-round3-journeys.spec.ts` (6 journeys; runs in the CI "Browser journeys" job) |
| **E-r2 / E-fig / E-br** | the existing `qa-round2-journeys`, `figma-parity-journeys`, `br-journeys` specs — all 44 journeys pass on a fresh CI-equivalent database |
| **L** | local-stack Playwright runs on the final build, independent browser contexts per identity, at 320/390/768/1440: 246 checks, 0 failures (photo 46, notifications+comments 63, catalogue 70, layout sweep 64, drafts/comments 3) |

## QA-062 .. QA-075 (round-3 items)

| QA ID | Outcome | What was wrong | What changed | Evidence |
|---|---|---|---|---|
| QA-062 | FIXED_PENDING_INDEPENDENT_RETEST | The photo step uploaded the file as picked; no way to position or crop it. | A crop step before any upload (`components/ui/ImageCropper.tsx`, geometry in `lib/crop-geometry.ts`, generalised from the profile-photo cropper): drag with a mouse or one finger, pinch or slider or +/− to zoom, arrow keys to nudge, a live square window. **Only the crop is uploaded**, as a JPEG capped at 1600px and never upscaled; the picked file stays in the browser. "Adjust position" re-crops from the original. An undecodable file (HEIC outside Safari) is refused with a way forward, never uploaded blind. Server limits and byte-sniffing unchanged. Figma Step 6 `4443:555` draws only the upload card: the crop step is an intentional addition in the same card language. | F-r3 (geometry: cover, clamp, zoom anchor, source square, cap); E-r3 (touch pinch at 390px, uploaded JPEG is square and not the original); L: landscape, portrait, receipt-shaped and a 12 MB phone photo at 390px (touch) and 1440px (mouse + slider) — 0 uploads before crop, every upload square, re-adjust works |
| QA-063 | FIXED_PENDING_INDEPENDENT_RETEST | Skip moved on but kept the uploaded photo, which was then submitted. | Skip clears everything the step holds — the in-flight upload (aborted), the picked file, the crop, the preview — and the draft's `photoUrl` (`skipPhotoStep`). A late upload response after Skip is ignored. The private receipt (a separate control) is left alone. | F-r3 (skip → `photo_url` null); E-r3 (upload, Skip, submit → request body `photo_url: null`); L: Skip after upload on 4 image types, and Skip *during* a 2.5 s upload → saved draft and submitted body both have no photo |
| QA-064 | FIXED_PENDING_INDEPENDENT_RETEST | Opening a notification marked it read in the background and navigated; the header badge kept its old count until a refresh. | One shared unread count (`components/site/unread-store.ts`) read by the header badge and the list; every action adjusts it at once and then takes the server's answer; other tabs follow over a BroadcastChannel. Opening a notice sends "read" and waits (up to 1.5 s) before navigating. | F-r3 (`applyNotificationAction` deltas); B-r3 (read/unread counts); E-r3 + L on desktop and phone: badge −1 on arrival with no reload, server already read, a second tab's badge follows |
| QA-065 | FIXED_PENDING_INDEPENDENT_RETEST | No per-notification controls. | A "⋯" menu on every row: Mark as read / Mark as unread, and Remove from list. Removal is a **soft dismissal** (`notifications.dismissed_at`): the row leaves the list and the count; the notice row and whatever it described are kept. `POST /notifications/{id}/unread`, `DELETE /notifications/{id}`; another account's id is a 404. | B-r3 `test_mark_unread_and_dismiss_are_the_owners_and_soft` (row kept, vote kept, other account 404, second delete 404); E-r3; L (row gone after reload, comment still exists) |
| QA-066 | FIXED_PENDING_INDEPENDENT_RETEST | The preset verdict ran straight into the reviewer's sentence ("It depends. Great if you commute…"). | The preset is a labelled chip (`data-verdict`); the reviewer's text sits under it as their quote ("In the reviewer's words"). The stored verdict and explanation are unchanged and still immutable after publishing. | L (desktop + phone: chip "It depends", blockquote with the insight) |
| QA-067 | FIXED_PENDING_INDEPENDENT_RETEST | No interaction notifications. | Notified: an upvote on your review or comment (never who voted; repeats group while unread — "3 people found your review helpful"), a comment on your review, a reply to your comment, an @mention (plain-text parse, at most 5, not inside an email address), a reply to a comment you follow, an up-vote on your request, and your request being answered. **Never** the actor; **once** per actor and item (`notification_receipts`), so re-voting, vote toggling and retries stay silent; taking a vote back never notifies. **Downvotes notify nobody** — no product rule asks for it (owner may decide otherwise). Links go to the content: `/reviews/<id>#comment-<id>` for comment events, `/requests#request-<id>` for request up-votes (grouped per request, never across requests — a defect caught in the final screenshots). | B-r3: once-and-grouping, downvote silent, reply + mention + follower each told once and the most specific way, self-mention silent, comment upvote once; E-r3 + L (mention link lands on the comment) |
| QA-068 | FIXED_PENDING_INDEPENDENT_RETEST | The thread was re-sorted by helpfulness on every render, so the comment just voted on jumped. | The order is fixed when the page loads and when the reader picks a sort (`arrangeByOrder`); a vote changes counts only. New comments come first; removed ones drop out. Server order was already stable (oldest first). | F-r3; B-r3 `test_voting_does_not_reorder_the_thread`; E-r3; L (up- and down-vote at 390/1440, order identical) |
| QA-069 | FIXED_PENDING_INDEPENDENT_RETEST | Another member's comment had no ⋯ (nothing to put in it). | ⋯ on others' comments: **Report** (the same dialog, reasons, rate limit and self-report rule as review reports; lands in the moderator report queue, which now shows comment targets, links to the comment, and can remove or restore it), **Follow comment** (replies to it notify you), **Save comment** (a private list, the new *Saved* tab on your own profile only). Only the viewer's own follow/save state is ever served. Your own comment's ⋯ still holds only Delete. No Recent Reads, no review bookmarks. Figma: comment blocks `4305:2114`/`4305:2113`, DotsThree `7140:3330`. | B-r3 (private and idempotent, removed comment leaves the saved list, report pipeline end to end incl. moderator removal); E-r3; E-fig QA-020 (updated: author's ⋯ = Delete; others' = Report/Follow/Save); L |
| QA-070 | FIXED_PENDING_INDEPENDENT_RETEST | The share sheet had no picture, and review links unfurled with no image (static title, no OpenGraph image). | Review pages emit `og:*` and `twitter:*` (summary_large_image) with the review's photo, else the product's image, else a branded 1200×630 site card; `metadataBase` makes them absolute. Unpublished reviews get the generic, unindexed title. The share sheet shows the same picture as a square beside the excerpt, as Figma "Share to" `1731:1571` draws it. Receipts are private object keys, never URLs, so they cannot appear. | F-r3 (photo → product → card); E-r3 (absolute og:image, large card, no receipt; picture in the sheet); L (og:image = review photo; product image when no photo; site card elsewhere) |
| QA-071 | FIXED_PENDING_INDEPENDENT_RETEST | A product added from a link carried no category, so its review never appeared under any category. | The picker asks for a category; a duplicate submission fills a missing category (never replaces one); canonicalising **requires** a category (the moderator's form now has the select, pre-set to the reviewer's); attaching fills the canonical product's missing category. Category stays on the canonical product. | B-r3 `test_the_category_survives_submit_attach_and_browse` (submit → attach → category feed finds the review), duplicate fill, canonicalise requires; L (canonicalise keeps "audio"; search by category finds the review) |
| QA-072 | FIXED_PENDING_INDEPENDENT_RETEST | With nothing typed, the pasted URL became the product's name. | `GET /products/resolve-link` reads the link **without fetching it** (the owner's no-scraping rule): which marketplace, the product already on bluntly for that exact listing, and the name written in the link's path, offered as an editable *proposed* name. No name in the link → an empty field and "type it"; nothing is made up. A URL is refused as a name on both sides. A moderator still names the canonical product. | B-r3 (Shopee/Lazada/short-link cases; the module imports no network client; URL-as-name 422); F-r3; E-r3; L (proposal, short link, same listing recognised) |
| QA-073 | FIXED_PENDING_INDEPENDENT_RETEST | Requesters were never told. | When a request is answered, its requester is told "Your review request was answered" and each up-voter "A review you were waiting for is up", each once, linking to the review. | B-r3; L (the requester's notice opens the review) |
| QA-074 | FIXED_PENDING_INDEPENDENT_RETEST | A request was only fulfilled if someone claimed it manually. | A newly published review fulfils every open request for its **canonical product** — same product id, or (for a request that named none) the exact same listing. One conditional update (`… WHERE status = 'open'`) makes it idempotent across retries and races; `fulfilled_at` is set once. A request posted with a known listing is pinned to that product. Attaching a submission moves its requests too. Never matched by name. | B-r3: single, multiple requesters + up-voter, retry (0 closed), already fulfilled, similar name not matched, listing match, the requester's own and older reviews do not answer it; L (leaves the open board) |
| QA-075 | FIXED_PENDING_INDEPENDENT_RETEST | Any 3+ characters passed. | One format rule on both sides (`lib/registration-format.ts`, `backend/app/core/registration_format.py`), held to one case table (`shared/registration-numbers.json`, 37 cases) by a test on each side: DTI 6–10 digits (an optional "DTI" prefix), SEC up to three letters + 5–15 digits with an optional suffix, placeholders refused. Send stays disabled until it passes; the server refuses the same. The copy says the format is checked and a moderator checks the registration — nothing says "verified". Real ownership is still decided by a moderator against the DTI/SEC document and the shop name. | B-r3 (case table ×2, API 422); F-r3 (same table; no "verif" wording); E-r3; L |

## Earlier items not marked Resolved by the tester (27)

| QA ID | Tester Status | Outcome | Evidence and notes |
|---|---|---|---|
| QA-001 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Re-checked: search results for "power bank" and "anker" draw each product's stored picture. Products with no picture still show the placeholder until a moderator adds one (the Products screen, since round 2). |
| QA-003 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Tester's note: drafts did not follow to mobile. Drafts are saved to the account since round 2. Re-checked: a draft started in a desktop browser is offered, with its text, in a separate phone browser (L; E-r2 QA-003 on desktop and phone). |
| QA-005 | Deferred | — | Deferred by the tester (footer social links need the owner's accounts). No change. |
| QA-006 | Partially Fixed | NO_CHANGE_REQUIRED_BY_CURRENT_RULES | "No shop link on this review" is correct where no approved affiliate link exists: links are attached by an admin after earnings approval (Business Rules; admin-mediated links). Reviews with an approved link show "Buy it here". **Owner decision available:** whether a non-affiliate "View listing" link should show meanwhile. |
| QA-016 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Re-checked: "← Dashboard" on desktop and the arrow on phone (E-r2 QA-016). |
| QA-020 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | Tester's note: Share missing from comments. Re-checked: all 8 comments and replies on a threaded review show vote, Reply and Share (L); E-fig QA-020 updated for QA-069's ⋯. Frames `4305:2114`, `4305:2113`. |
| QA-022 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | **Real defect found:** where the search field draws its own × it also drew the browser's native one — two clear buttons side by side. The native one is now hidden on those fields only (before/after screenshots). Relevance: short queries already match word starts only; "MacBook" and "Mattress" are word-start matches for "ma" by design (round 2). |
| QA-023 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Re-checked: whole question row (390×165) is the link; E-r2 QA-023. |
| QA-024 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | Tester's note: system share sheet. The app's own "Share to…" sheet opens on desktop and phone (E-r2 QA-024); it now carries the preview picture (QA-070). Frame `1731:1571`; Instagram/Bookmark tiles intentionally absent (round-2 note). |
| QA-025 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Several categories at once; E-fig QA-025/053. Frame `1587:4658`. |
| QA-027 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Feed cards carry Helpful, Not helpful and Share (L); E-r2 QA-027/028. |
| QA-028 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Vote toggles without navigating; Share opens the sheet (L; E-r2). |
| QA-029 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Reply on every comment and reply (L; E-r2 QA-029). |
| QA-030 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Down count shown in the same type as up (E-r2 QA-030). |
| QA-033 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | Same as QA-022. |
| QA-038 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | **Real defect found:** a typed pro/con vanished when unticked (chips were derived from what was chosen), so it could not be chosen again; and an 11th pick was accepted and then refused at submission. Typed phrases now stay as chips for the step; picks are capped at 10 per list with a message. L (add → untick → still there → tick again, desktop and phone); E-r2 QA-038. |
| QA-039 | Partially Fixed | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Re-checked: your own comment's ⋯ holds only Delete, which asks for confirmation (L; E-r2 QA-039). |
| QA-043 | Fail | BLOCKED_PRODUCT_DECISION | The seller-review frame (`4218:2148`) draws votes, replies and ⋯, but no rule or data model gives seller reviews a helpfulness score or a comment thread. Share and the owner's respond/flag controls exist. Proposal for the owner: a ⋯ with Copy link and Report (through the report pipeline, target `seller_review`) needs no new rule; votes and replies do. |
| QA-050 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | All filters and Sort on the Questions tab (frame `3481:1894`, card `7158:4877`). "3 active" and Topics need data models (owner). |
| QA-052 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Sellers tab pills and row facts (frame `3954:650`, card `7159:4873`). |
| QA-053 | Fail | BLOCKED_PRODUCT_DECISION (in part) | Category, Time and Sort (Oldest) are in (frame `1587:4658`, Sort `1591:5408`). Hidden Gems / Controversial / Trending / Budget / Trust rating have no product definition; building them would be decorative. Proposal needs owner definitions. |
| QA-054 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | **Real defect found:** a taken-down review told its author only "taken down". The moderator's reason is now served to the author (`author_takedown_reason`) and shown on the review ("Reason: …"); other readers still get 404. B-r3 `test_the_author_sees_why_their_review_was_taken_down`; L. |
| QA-055 | Fail | FIXED_PENDING_INDEPENDENT_RETEST | "New" label and tint (round 2); the tint now covers the whole row including the new ⋯ column; read state is immediate (QA-064). |
| QA-057 | Fail | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | All filters and Sort on the seller page (frame `4218:2148`); E-fig QA-057. |
| QA-058 | Open | FIXED_PENDING_INDEPENDENT_RETEST (round 2) | Best Answer only after the asker picks it; notice to the answerer. |
| QA-059 | Fail | NOT_REPRODUCIBLE_WITH_VALID_TEST_SETUP | The review ⋯ menu opens beside its trigger inside the viewport at 1280, 390 and 320 (menu boxes measured); E-r2 QA-059. |
| QA-061 | Fail | INVALID_TEST_PROTOCOL | Two tabs of one browser profile share one session, as on every cookie-based site. Separate profiles/processes stay apart (E-r2 QA-061 A/B/E). No per-tab auth is built. |

## Resolved by the tester (34) — not reopened

QA-002, 004, 007, 008, 009, 010, 011, 012, 013, 014, 015, 017, 018, 019, 021, 026, 031, 032, 034, 035,
036, 037, 040, 041, 042, 044, 045, 046, 047, 048, 049, 051, 056, 060. Their suites (backend, frontend unit,
all browser journeys) pass on this branch.

## Other defects found and fixed in this round

- **Scheduler:** the daily 21:00 UTC workflow entry named `sweep_contracts`, a task the cron endpoint
  does not have, so the **daily integrity sweep never ran from the schedule in production**. Mapped to
  `integrity_sweep` (test: every workflow task name exists). Takes effect only after merge.
- **Report queue link:** "Open the reported item" always pointed at `/reviews/<target id>`, a 404 for
  anything that is not a review. It now uses a server-provided link, or none.
- **Test isolation:** one priority-tier test read only the first page of open reports; on a long-lived
  database it missed its own. It now pages through.

## Payments before the defense (2026-09-27)

The owner lifted the freeze for the payment workflow: a reviewer's earnings must be payable, and real
QA testers must be able to test getting paid (PayPal SANDBOX, no real money). Walking the real path
through the API (import → record marketplace payout → cashout → batch → mark paid) found:

- **No admin screen** to import a marketplace report or to process a withdrawal: only raw API calls.
  Now **Affiliate Links → Import a marketplace report** (preview, then import) and **Finance →
  Payouts** (send to PayPal sandbox when configured; mark paid with the reference, mark failed with a
  reason, cancel, retry, check PayPal).
- **The reviewer was never told** a withdrawal was paid, failed or cancelled, and a settled request
  vanished from Transfer. Every outcome now notifies the reviewer, and Transfer lists **Your
  withdrawals** with status, date and reference.
- **Payout steps were not audited** (who marked what paid, with which reference). Each step now writes
  an audit entry with the moderator's id.
- **The import preview overstated credits:** a sale whose sub-ID matches no review was previewed as
  "would be credited" and then credited nobody. The preview now counts it as unattributed
  (`test_preview_counts_an_unattributable_sale_as_unattributed`).
- **Sandbox safety:** sandbox mode never submits to a non-sandbox PayPal host; the console shows the
  payout method and whether the PayPal API is configured (never a credential).

QA sandbox test earnings (owner decision; owner-named testers only): `docs/QA_PAYMENT_TESTING.md`.
Evidence: `backend/tests/test_qa_sandbox_payouts_api.py` (9), `e2e/qa-payments.spec.ts` (credit →
labelled earning → withdrawal → paid with reference, on the real stack).

## Admin priority tiers

Separate document: `docs/ADMIN_PRIORITY_TIERS.md` (rules, the provisional voter-risk mapping, trend,
aging, thresholds, UI, and the queue-admission regression test).

## Honesty Fund

Separate document: `docs/HONESTY_FUND_MEETING_DECISION.md` (approved direction vs open economic
parameters; distribution stays off).

## Needs from the owner

1. QA-043: seller-review engagement model (votes/replies) — or approve ⋯ with Copy link + Report only.
2. QA-053: definitions for Hidden Gems, Controversial, Trending, Budget, Trust rating.
3. QA-006: whether a non-affiliate listing link may show before an affiliate link is approved.
4. QA-067: whether downvotes should notify (currently no).
5. Priority tiers: confirm or replace the provisional voter-risk mapping.
6. Honesty Awards: the four open economic parameters.
7. QA payments: the QA testers' usernames or emails (the owner adds them on **QA Payments**), and
   whether the production API should carry PayPal **sandbox** credentials (otherwise sandbox payouts
   are paid by hand from sandbox.paypal.com and marked paid with the reference).

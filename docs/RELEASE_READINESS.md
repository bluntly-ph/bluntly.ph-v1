# Release readiness — reporting, owner patch, Administrator / Super Admin (2026-09-28)

| | |
|---|---|
| Checked | 2026-09-28 |
| Candidates | PR #5 `feat/reporting-module` (draft); `feat/admin-superadmin-architecture` (draft, stacked on it) |
| `main` | `087a45b` (production, Vercel auto-deploys it), so **merging is deploying** |
| Production | **Not mutated.** No migration, no write, no role change, no deploy, no environment change, no payout. |
| Code migration head | `0067_last_super_admin_guard` (0061 reporting index; 0062–0063 support requests; 0064–0067 roles and routing) |

## What must happen before a merge

| # | Step | Who | State |
| --- | --- | --- | --- |
| 1 | Exact-SHA CI green on both branches (`db-fast`, `ci`) | engineering | **GitHub CI blocked**: Actions has allocated no runners since 14:33 UTC (account billing/usage). Local CI-equivalent run passes on both heads (PR #5 `746e291`, PR #7 `e69c980`), and Vercel Preview builds succeed: [LOCAL_CI_EQUIVALENCE.md](LOCAL_CI_EQUIVALENCE.md). Fresh exact-SHA CI is still owed once runners return. |
| 2 | Migrate TEST to 0067, **at the merge, not before**: after #5 and #7 reach `main`, `main`'s own CI run migrates TEST; then Defense environment → populate_test for the TEST Super Admin. Dispatching CI on this branch earlier would leave TEST ahead of `main`'s code (0065 rebuilds the role type), and `main`'s isolated-database job would then fail. | owner (merge) | not run. TEST is at `0061` (#5's index), applied by #5's verification run 36420305158. |
| 3 | Independent QA retest of the affected items ([QA_CURRENT_RECONCILIATION.md](QA_CURRENT_RECONCILIATION.md)) | QA team | **not done**. The workbook could not be read. |
| 4 | Owner confirms **who is production's Super Admin**: the migration would make USR-000001 one ([ADMIN_SUPERADMIN_MIGRATION.md](ADMIN_SUPERADMIN_MIGRATION.md) §2) | owner | open |
| 5 | Owner confirms **PLATFORM's accounting**: the reviewer's 30% goes to the platform; the fund's 30% is unchanged ([ADR-017](adr/017-administrator-super-admin-roles.md)) | owner | open |
| 6 | Owner confirms that a **deleted review's later sales** go to the Honesty Fund (the §14 "from that point on" precedent) | owner | open |
| 7 | Coordinated production rollout: migrate + promote together ([ADMIN_SUPERADMIN_MIGRATION.md](ADMIN_SUPERADMIN_MIGRATION.md) §3) | owner authorisation | not started |
| 8 | Seeding day: [SEEDING_RUNBOOK.md](SEEDING_RUNBOOK.md) (dry run → list → verify → cleanup → seed → verify) | team | ready |

## Verified in this session (engineering, not independent QA)

- Backend: the full suite passes on the cumulative local CI database. The
  only failures are the two receipt-privacy tests that upload to real
  Supabase storage, which need credentials this container does not have.
- Milestones: 59/59.
- Migrations:
  - blank → head;
  - 0063 → head → 0063 → head with moderator rows, preserving data.
- Frontend: typecheck, lint, 423 unit tests, production build.
- Browser, real stack: 96 journeys in the CI set, including 16 owner-patch
  and 16 admin journeys.
- Integrations (read-only): [INTEGRATION_VERIFICATION.md](INTEGRATION_VERIFICATION.md).

## Known, not blocking this release

`e2e/admin-console.spec.ts`, `moderator-a11y.spec.ts` and
`dashboard-navigation.spec.ts` need an `E2E_MODERATOR_TOKEN` and are not in CI.
Run locally with an Administrator token, 6 of their checks fail, and they
predate this work:
- rail items below the fold at 720–832px tall;
- an sr-only element without a positioned ancestor;
- controls under 24px;
- `/admin/qa-sandbox` navigation;
- a stale expectation that Sellers is unavailable.

---

# Release readiness — `fix/cloud-round2-security-design` (PR #1)

| | |
|---|---|
| Checked | 2026-09-25 |
| Candidate | the head of PR #1 (draft, open), on `fix/cloud-round2-security-design` |
| `main` | `e0a4e93`. It is what production serves (Vercel auto-deploys `main`), so **merging is deploying** |
| Production | **Not mutated**: no migration, no write, no deploy, no setting change |

## 1. At a glance

| Question | Answer |
|---|---|
| Preview database | **PREVIEW DATABASE TARGET UNVERIFIED**. Testers must not use a Preview yet (§2) |
| Code migration head | `0053_repair_rejection_links` |
| TEST (`miysywhcdqkoniaibglx`) | `0051_product_median_column`; no `review_drafts` table |
| PROD (`byobedbhodhvocgrkrse`) | `0051_product_median_column`; no `review_drafts` table |
| Production still needs 0052 and 0053 | **Yes, both** |
| Engineering blockers | None open in code |
| Waiting on | Preview proof (owner), TEST migration (after the proof), independent QA (§4), owner decisions (§5), release authorisation (§6) |

Both database revisions were read on 2026-09-25 inside `BEGIN TRANSACTION READ ONLY`, and each result
carried `transaction_read_only = on`.

## 2. Preview database target — UNVERIFIED

**What was checked (metadata only; nothing decrypted, nothing written):**
- **The deployment.** This branch's Preview (`dpl_J8T7uXBsPSHtf7b42Ev3anxQ9BzQ`, sin1) is Ready.
  - It sits behind Vercel Authentication: an anonymous request is redirected to Vercel's login.
  - The Vercel connector cannot fetch it, and its runtime logs return 403.
  - `/health` does not name a database.
- **The variables.** Preview has its own records for `SUPABASE_URL`, `SUPABASE_CONNECTION_STRING`,
  `SUPABASE_CONNECTION_STRING_SESSION_POOLER`, `SUPABASE_SECRET_KEY`, `SUPABASE_PUBLISHABLE_KEY`,
  `SUPABASE_JWKS_URL` and 16 others.
  - Each was created about 5 seconds after its Production twin, on 2026-07-23 (UTC).
  - None is scoped to a branch.
  - Every one is `sensitive`, which on Vercel means write-only: nobody can read the value back, the
    owner included.
- **The app itself.** Nothing stops a non-production deployment from opening the production database.
  The production guard covers scripts and tests, not the web process.
  - A Preview carrying production values would therefore read and write live data.
  - Its schema would lack 0052 as well.

**What now makes it provable (this change).**
- The boot log line `production readiness` now carries a `database` field:
  `<label> | db host: <host> | supabase project: <ref>`.
  - It never includes a user, password or query string.
  - A regression test pins that even a password containing a stray `@` is not printed.
- How to read it:
  1. Open the Preview of the PR head while signed in to Vercel. Any page will do, for example `/health`.
  2. In Vercel, open project `bluntly-ph` → Deployments → that Preview → Logs, then search for
     `production readiness`.
  3. Read `database`:
     - **`supabase project: miysywhcdqkoniaibglx`**: Preview uses TEST. Carry on with §3.
     - **`supabase project: byobedbhodhvocgrkrse`**: **UNSAFE FOR TESTER WRITES.** Apply the correction below.
     - **Anything else**: OTHER. Stop and ask engineering.

     The ref decides which database it is. If the label reads `PRODUCTION` beside the TEST ref,
     Preview's `APP_ENV` says production; set it to `staging` as well.

**The smallest correction, if the ref is not TEST** (a Vercel change, owner-authorised, Preview only):
1. Overwrite the **Preview-scoped** values of these variables with the `bluntly-ph-test` project's values:
   - `SUPABASE_URL`
   - `SUPABASE_CONNECTION_STRING`
   - `SUPABASE_CONNECTION_STRING_SESSION_POOLER`
   - `SUPABASE_SECRET_KEY`
   - `SUPABASE_PUBLISHABLE_KEY`
   - `SUPABASE_JWKS_URL`

   They are the same values as in `backend/.env.test` and the `TEST_SUPABASE_*` repository secrets.
2. Leave every Production-scoped variable untouched.
3. Redeploy the Preview and read the log line again.

**Also worth confirming while in that screen:** Preview has its own `EMAIL_PROVIDER`, `RESEND_API_KEY`,
`PAYOUT_PROVIDER` and `PAYPAL_*`. For testers they should be console and sandbox values, not live ones.
Payouts stay manual and the Fund stays off either way.

## 3. Database state for QA and release

- **TEST needs 0052 and 0053 before QA on a Preview.**
  - Without 0052, Drafts (QA-003) fail: the table does not exist.
  - Only run this after §2 shows the Preview uses TEST.
- **How to migrate TEST.** Dispatch the `CI` workflow on `fix/cloud-round2-security-design` (Actions →
  CI → Run workflow).
  - Its "Backend (isolated database)" job migrates TEST to this branch's head, then runs the suite and
    the milestone verifier.
  - It refuses a production target by construction.
- **Consequence.** Until PR #1 merges, the same job on a `main` push would fail: `main` does not know
  revision 0053. Merging clears it.
- **TEST is shared with CI.** It holds about 4,250 never-published fixture reviews from past runs
  (`ci.yml`), so testers will see fixture content beside their own. Pruning it is destructive and waits
  on the owner.

## 4. Independent QA handoff

**Where to test.** Every item below needs the candidate build: production still serves `main`, which
has none of these fixes. So each needs the PR's Preview, **once §2 proves it uses TEST and §3 has
migrated TEST**. The exceptions are marked "Production OK".

**Recording results.** The tester records results in `BLUNTLY_QA.xlsm`. Engineering does not edit the
Retest Result fields. The full wording of each item is in `docs/INDEPENDENT_QA_ROUND2_RETEST.md`.

**Accounts.** "Member" means any signed-in account. "Store owner" means an account holding an approved
claim on that store. "Moderator" means an admin account on TEST.

### 4a. The Figma items

| QA ID | Route | Account | Precondition | Steps | Expected | Device | Preview/TEST |
|---|---|---|---|---|---|---|---|
| QA-020 | `/reviews/<id>` with comments and replies | Member | You have posted one comment on it (post one first) | 1. Compare your comment's row with other people's comments and replies. 2. Open ⋯ on yours → Delete → "Yes, delete". 3. Reload. | Every comment and reply has the same row: Upvote, Downvote, Reply, Share. The name line shows the Honesty Score. Only your own comment has ⋯, and Delete asks "Delete this comment?" first. It is gone after the reload. | Mobile and desktop | Yes (writes) |
| QA-024 | `/reviews/<id>` (Share by the title, and on a comment), `/feed` card, `/sellers/<id>` review | None. The author of a review for the caption | For the caption: your own published review | 1. Press Share at each place. 2. Look at the destinations. 3. Copy link. 4. On a phone, More. **Close each destination's tab without posting.** | "Share to…" with a preview card, then Facebook, Reddit, X, Telegram and WhatsApp (plus Messenger and Viber on a phone), Copy link, and More where the device has one. Each destination opens with this page's link. No Instagram, no Bookmark (both by design). The caption shows only on your own review. It mentions commission only if an admin attached a shop link. | Mobile and desktop | Yes (candidate build) |
| QA-025 | `/search` (Reviews) | None | Reviews exist in two or more categories | Phone: All filters → tick Beauty **and** Electronics & Tech → Filter Reviews. Desktop: click two categories in the rail. | Results include both categories, with one chip per category. On desktop the second click adds a category rather than replacing the first. | Mobile and desktop | Yes (candidate build) |
| QA-050 | `/search?tab=questions` | None | Questions of different ages; one on a product with a stored image | 1. All filters → Past year → apply. 2. Sort → Oldest. | Each choice changes the list. The row shows the product's image where one is stored. No "3 active" and no Topics (no data behind them). | Mobile and desktop | Yes (candidate build) |
| QA-052 | `/search?tab=sellers` | None | At least one claimed and one unclaimed store | 1. All filters → Claimed profiles only, plus one marketplace → apply. 2. Sort → Most reviews. | Only claimed stores of that marketplace, most reviews first. Rows read "N reviews · N questions answered · Marketplace", with an initials tile (stores have no logo). | Mobile and desktop | Yes (candidate build) |
| QA-053 | `/search` (Reviews) | None | Reviews older and newer than a month | 1. All filters → Time: Past month → Filter Reviews. 2. Sort → Oldest. | Older reviews drop out and a Time chip appears. Oldest reverses the order. Round 4 (2026-09-28): Review score (Hidden Gems / Controversial / Trending), Trust rating and Budget are now offered too; definitions in `docs/INDEPENDENT_QA_ROUND4_REMEDIATION.md`. | Mobile and desktop | Yes (candidate build) |
| QA-057 | `/sellers/<id>` | None. A member to add the precondition | The store has 3 or more reviews, including one at a half star (for example 4.5). Add one via `/sellers/rate` if needed. | 1. All filters → untick one star, Past month → apply. 2. Sort → Lowest, then Oldest, then With photos first. | The list follows each choice. A 4.5★ review appears under the 4★ tick, and the rating card's ticks mirror the sheet. An applied Time chip is shown. No Top mentions. | Mobile and desktop | Yes (writes, for the precondition) |

### 4b. The other Round 2 items still awaiting a human retest

| QA ID | Route | Account | Precondition | Steps | Expected | Device | Preview/TEST |
|---|---|---|---|---|---|---|---|
| QA-001 | `/search`; `/moderate/products` | None; a moderator for the picture | — | Search "ma", "Man", "ankr", "jisulfe". As a moderator, on Products, press Add image on a product with "None" and choose a photo; search for it again | Close matches only; typos still find Anker and Jisulife. After the upload the product's picture replaces the placeholder in search and on its cards | Both | Yes (writes) |
| QA-003 | `/reviews/new` | Same member on two devices | TEST at 0053 (§3) | Fill the first steps on desktop; open Write a review on a phone | "Pick up" is offered for the desktop draft; another account never sees it | Desktop, then mobile | **Yes (needs 0052)** |
| QA-006 | Any review | None | — | Compare a "No shop link" review with a "Buy it here" one | "Buy it here" appears only when there is an approved link, and opens the exact listing | Both | Production OK (no change) |
| QA-016 | `/dashboard` → Reviews, History, Transfer, Insights | Member | — | Use "← Dashboard"; also open `/dashboard/reviews` directly | The link returns to the Dashboard | Desktop (and mobile) | Yes (candidate build) |
| QA-022 / 033 | `/search` | None | — | Type "ma", then "Man" | Only our suggestion list, with no dark browser list; "Man" no longer suggests MacBook or Mattress | Both | Yes (candidate build) |
| QA-023 | `/questions` | None | — | Hover over a row, tap it, and use Tab + Enter | The row darkens with an orange title; the whole row opens the question | Both | Yes (candidate build) |
| QA-027 / 028 | `/feed` | Member | — | Downvote a card, then Share and Comment; reload | The vote persists and the card doesn't navigate; the sheet opens; Comment jumps to comments | Both | Yes (writes) |
| QA-029 | `/reviews/<id>` | Member | A reply exists | Reply to a reply and post | The composer opens with "@name"; the reply appears in the same thread | Both | Yes (writes) |
| QA-030 | `/reviews/<id>` | None | — | Look at the vote counts | The up and down numbers are the same size | Both | Yes (candidate build) |
| QA-038 | `/reviews/new` (Pros/Cons) | Member | — | Add a custom Pro with Add or Enter, and a Con by tapping elsewhere; Continue, then Back; publish | Both stay as chips and appear in the review | Both | Yes (writes) |
| QA-039 | `/reviews/<id>` | Comment author | Your own comment | ⋯ → Delete → Yes, delete; reload | Gone at once, and stays gone | Both | Yes (writes) |
| QA-043 | `/sellers/<id>` | None; store owner | An approved claim, for the owner part | Share a review; as the owner, open the page | The sheet opens. The owner sees Respond (editable) and Flag as suspected fake. No votes, threads or viewer report (§5). | Both | Yes (writes) |
| QA-054 | `/notifications` | Review author, plus a moderator | A moderator rejects one of the author's reviews on TEST | Open the "Your review was rejected" notice | It opens the review, with "Won't earn" and the reason. The **legacy** notice from 2026-09-22 is in production and is repaired by 0053: retest it in the production smoke (§6, step 9). | Both | Yes (writes) |
| QA-055 | `/notifications` | Member | One read and one unread notice | Open one; reload | Unread rows show "New" and a tint; a row stays read after the reload | Both | Yes (writes) |
| QA-058 | `/questions/<id>` | Three members (A asks, B answers, C tries) | — | A asks, B answers, C tries to pick, A picks; reload | No badge before A picks; C cannot pick; then "Best Answer · picked by the person who asked", and B is notified | Both | Yes (writes) |
| QA-059 | `/reviews/<id>` | None | — | Open ⋯ on desktop and on a small phone; press Escape | The menu opens beside its button, inside the page; Escape closes it | Both | Yes (candidate build) |
| QA-061 | `/login` | Two members | Two separate browser profiles | Sign in as a different account in each; reload both | Each profile keeps its own account | Desktop | Production OK (no change) |

## 5. Owner decisions (not resolved here)

| Item | Current behaviour | Decision needed | Safe while unresolved | Implementation impact |
|---|---|---|---|---|
| Trust thresholds after the distinct-voter fix | Stages 3/4/5 need 20/60/200 **people** of voter evidence and 5/15/50 verified reviews. A cohort present on at least half of a member's reviews (and at least 3 of them) that supplies more than 60% of eligible votes holds promotion for a moderator. Nobody is at Stage 3+ in production. | Keep these values, or tune them (people counts, cohort share, whether Stage 1 voters count in full) | Keep the current, stricter values. Nobody is demoted by them. | Constants in `services/trust.py` and their tests; no migration |
| Honesty Fund formula | Pool accrues its 30%; `distribute()` refuses (`honesty_fund_formula_pending`, 409); `honesty_fund_distribution_enabled = False` | The distribution formula (§14) | Keep distribution **off** | New scoring in `honesty_fund_service`, tests, and an ADR; the config flag is flipped only at release |
| Honesty Fund holding period | None coded. A 14-day review window is only a proposal (`TRUST_DISTINCT_VOTER_SECURITY_FIX.md`). | Whether to hold before crediting, and for how long | Keep distribution off; nothing is paid | A cycle-close snapshot plus a delayed credit; likely a migration |
| QA-043 seller-review voting | Not offered | Should seller reviews have votes, and what would they affect? | Keep them absent (no decorative control) | API, model and UI for votes on seller reviews; likely a migration |
| QA-043 threaded replies | The owner has one public, editable response; there are no public threads | Should there be public threads on seller reviews, and how are they moderated? | Keep the single owner response | Comments model, moderation queue and UI |
| QA-043 viewer reporting | Only the store owner can flag a review as a suspected fake. Viewers have no report and no ⋯. | Should viewers be able to report, and what does a report trigger? | No viewer ⋯ (never an empty menu) | Report route, queue wiring and UI |
| QA-053 Hidden Gems | Built (round 4) | Defined in `review_lenses.py` | Offered | — |
| QA-053 Controversial | Built (round 4) | Defined in `review_lenses.py` | Offered | — |
| QA-053 Trending | Built (round 4) | 7 days of helpful votes and comments | Offered | — |
| QA-053 Budget | Built (round 4) | Price paid, at most a chosen stop | Offered | — |
| Trust naming (§21, QA-049) | Existing labels unchanged. There is no Trust rating filter and no Reviewer credibility sort. | The names, and whether people may be ranked by the trust number | Keep the labels; offer no such filter or sort | UI copy, plus the filter and sort if approved |
| 2.5★ "it depends" track | `PRODUCT_RULE_PENDING_2_5 = True`. Such a review gets `pending_owner_rule`, and moderator routing refuses it. | Does it go to Commission or the Honesty Fund? | Refuse to route it (current behaviour) | One line in `earning_track._tie_break`, plus the flag and tests |
| QA-005 social accounts | Footer social icons removed; none invented | Official account URLs, or keep them removed | Keep them removed | Footer links only |

## 6. Release sequence

Engineering executes none of steps 4–10 without the owner's explicit authorisation.

1. **Prove Preview uses TEST** (§2). Then migrate TEST (§3).
2. **Independent QA** on the Preview (§4).
3. **Owner resolves the required product decisions** (§5). The safe defaults above ship if a decision is deferred.
4. **Owner authorises the release**, naming the approved SHA.
5. **Production backup**: a Supabase backup or dump of `byobedbhodhvocgrkrse`, confirmed restorable.
6. **Apply migration 0052** (`review_drafts`: additive, RLS on).
7. **Apply migration 0053** (idempotent repair of legacy rejection links).
8. **Deploy the approved SHA**. Merging PR #1 to `main` is the deploy.
9. **Production smoke test**:
   - `/health`;
   - the boot log shows `PRODUCTION | … | supabase project: byobedbhodhvocgrkrse`;
   - sign in, the feed and a review page;
   - a draft saves;
   - the legacy QA-054 notice opens its review.
10. **Honesty Fund distribution stays OFF** (`honesty_fund_distribution_enabled = false`).

**After release (operations, not engineering):** production has 38 of 43 products without a picture. A moderator adds them from Products → Add image (QA-001). Every "Buy it here" on production is an official Shopee or Lazada affiliate short link (18 of 18, read-only check on 2026-09-25). If one opens Shopee's "This shop failed to load" (QA-006), the link needs replacing in the affiliate dashboard; it is not a site defect.

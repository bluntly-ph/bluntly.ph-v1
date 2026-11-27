# Defense runbook

How to prepare, present and reset the system for the capstone defense. The
system is the live product, running on the **defense dataset**: a believable,
fully connected community of reviewers, stores, questions, prices and money,
seeded through the application's own API into the **TEST** project
(`bluntly-ph-test`). Production is never touched.

Related: [coverage matrix](DEFENSE_SYSTEM_COVERAGE.md) ·
[dataset manifest](DEFENSE_DATA_MANIFEST.md) ·
[cleanup report](DEFENSE_DATA_CLEANUP_REPORT.md) ·
[diagram alignment](DEFENSE_DIAGRAM_ALIGNMENT.md)

## 1. The tools

All three are in `backend/scripts/defense/` and refuse to run anywhere but
bluntly-ph-test or a local Postgres (`guard.py`: production signals, a missing
`BLUNTLY_TEST_ENV` marker, or an unrecognised database all exit 2 before
anything is written).

| Command | What it does |
|---|---|
| `python -m scripts.defense.reset` | Dry run: lists every table and row count it would clear, and the accounts it would keep. |
| `python -m scripts.defense.reset --apply` | Clears content, deletes fixture/defense accounts (`@example.com`, `@demo.bluntly.ph`, ...), keeps real accounts content-free, and on TEST empties the photo buckets. Reference tables (badges, tiers, cron) are kept. |
| `python -m scripts.defense.seed [--reset] --out seed.json` | Seeds the dataset through the API, back-dates history, recomputes trust, dates the audit trail. Deterministic. Refuses a database that already holds it unless `--reset`. |
| `python -m scripts.defense.verify [--site URL] [--json out.json]` | The readiness check: 95 checks across environment, personas, catalogue, content, moderation, money, prices, integrity, a gibberish sweep and the API routes (and, with `--site`, the pages). **Exits 1 if anything essential is missing.** |

## 2. Preparing TEST (GitHub Actions, no local credentials)

The TEST credentials live only in repository secrets, so TEST is filled from
GitHub Actions:

1. **Actions → Defense environment → Run workflow**, tick **populate_test**.
2. The `populate-test` job migrates TEST to head, prints the reset plan, resets,
   seeds, and runs `verify`. It fails loudly if any check fails; the
   `defense-test-readiness` artifact holds every check's result.
3. **Allow about an hour and a half.** From a GitHub runner every query
   crosses to ap-southeast-1: the first complete run took 60 minutes for the
   reset, seed and check (an earlier one spent 22 minutes on the votes alone
   and reached the traffic step at the hour). If CI's isolated-database job is
   running, the seed waits for it first (about 2.5 hours). Run it the evening
   before, not the hour before.

CI's isolated-database job also runs against TEST after every push to `main`
and leaves test fixtures behind. Both jobs share the `bluntly-ph-test`
concurrency group, so they never write at the same time, but a CI run *after*
seeding puts fixtures back. Either:

- set the repository variable **`DEFENSE_AUTOSEED=true`**: the defense
  workflow then re-seeds TEST automatically after every successful CI run on
  `main`; or
- freeze merges to `main` from the final seed until the defense ends.

## 3. The site the panel sees

The seeded data is on TEST, so the site must be one whose API reads TEST:

- **Recommended: the Vercel Preview deployment**, if its backend environment
  points at TEST. Confirm once: the API's startup log line
  `"production readiness"` carries a `database` field; it must name
  `supabase project: miysywhcdqkoniaibglx`. *(Not verifiable from here: the
  Vercel connector cannot read Preview environment values - an owner action.)*
- **Fallback: a local production build against TEST** on the presenting
  laptop (`npm run build && npx next start`, backend with the TEST session
  pooler string). Requires the TEST credentials on that laptop only.

Then run `python -m scripts.defense.verify --site <that URL>` once: it also
loads the public pages from the site itself.

## 4. Signing in as the personas (no passwords anywhere)

Every sign-in is the site's own email one-time code. Persona addresses are
**"+" aliases of the team inbox** (`DEFENSE_EMAIL_BASE` secret, else the root
owner's address), so every code arrives in one mailbox the team already has:

| Persona | Username | Address (alias of the team inbox) | Shows |
|---|---|---|---|
| Visitor | — | (signed out) | browse, search, read, compare |
| New reviewer | `paolo_mendoza` | `<inbox>+paolo@…` | Stage 1, joined 6 days ago, writes a review |
| Established reviewer | `mariareyes` | `<inbox>+maria@…` | Stage 2, earnings, cashout, asks questions |
| Advanced reviewer | `kristinev` | `<inbox>+kristine@…` | Stage 3 on real evidence, Best Answers |
| Store owner | `rico_powerhub` | `<inbox>+rico@…` | claimed PowerHub PH, answers buyers |
| Moderator | `mod_joanna` | `<inbox>+moderator@…` | every queue |
| Under investigation | `jomar_deals` | `<inbox>+jomar@…` | the voting-ring case |

Nothing to memorise and nothing in Git: open the login page, type the alias,
read the code from the inbox. The seed never sets a usable password (each
account gets a random one nobody records).

## 5. The walkthrough (about 20 minutes)

`e2e/defense-walkthrough.spec.ts` is this script, executed: every stop below
passed in rehearsal and was photographed at 390 and 1440 px (CI artifact
`defense-walkthrough`).

1. **Visitor** (3 min) — home, feed, search `powercore` (an alias of the
   Anker 737), Maria's Anker 737 review and its five-month update, the iPhone
   17 review with Shopee and Lazada price history, Q&A, PowerHub PH's store
   page, review requests, Kristine's public profile.
2. **New reviewer — Paolo** (4 min) — sign in by code; vote a review
   helpful; write a review of the Soundcore Liberty 4 NC through all seven
   steps (experience, verdict, stars, pros/cons, who it is not for, photo or
   skip, title, price paid). It publishes at once, unverified without a photo.
3. **Established reviewer — Maria** (3 min) — wallet (₱814.80: ₱368.40 ready,
   ₱446.40 still clearing), request a withdrawal of the cleared part, earnings
   history, notifications; on her own question, pick the Best Answer.
4. **Advanced reviewer — Kristine** (1 min) — Stage 3 profile.
5. **Store owner — Rico** (2 min) — seller dashboard; respond publicly to a
   buyer's store review.
6. **Moderator — Joanna** (7 min) — overview (queue, pending affiliate links,
   Honesty Fund, ledger); approve earnings on the review that passed the
   helpfulness gate; name the Xiaomi submission as a new product and attach
   the duplicate Anker Nano submission; reject the ₱24,999 iPhone outlier;
   take down the review containing a phone number (urgent report); attach the
   affiliate link to the review just approved; approve Cebu Gadget Hub's DTI
   claim; show Jomar under investigation, the Honesty Fund, analytics and the
   activity log.

**Presenter notes**
- Search sorts matches by helpfulness, not by closeness to the words typed:
  `anker 737` lists Anker Nano reviews too. Search the alias `powercore`, or
  open the product from its review.
- The walkthrough changes state. Re-run **populate_test** after a rehearsal on
  TEST so the panel sees the starting state.
- Real product photos: review photos on TEST are the manufacturer's product
  image uploaded under each reviewer (the dataset records the source page).
  Photos taken by the team would be more convincing - an owner action.

## 5b. Additions from the dev/QA sync of 2026-09-29

These need the code of PR #7 (migration 0067). Shared TEST stays at 0061 by the
owner's instruction, so today they run on a local or an authorized isolated
database. `python -m scripts.defense.verify --scenarios` says whether every
scenario below is present. The ledger is
[MEETING_2026_09_29_DECISIONS.md](MEETING_2026_09_29_DECISIONS.md).

1. **Why was it reported? (Administrator, 3 min).**
   - Open **Admin → Review queue → Report**, and on any card press **Why was this reported?**.
   - The panel beside the list gives the reason from stored facts, with the
     reported content under it:
     - **Jomar's "Great first console, sulit!"** has two system-detected reports:
       - *Copied text:* "Possible copied review … 88% similar", linking Carla's
         original.
       - *Vote collusion:* "5 of this review's 8 up-voters are members whose own
         reviews its author up-votes … no IP address or location is collected".
     - **The phone-number report** shows the member's category, their note, and
       why it escalated (an urgent reason).
2. **Escalate (Administrator, 1 min).**
   - Escalate an open report: it leaves the Report tab and appears as
     **Escalated** in the Overview's recent activity.
   - The team confirmed this behaviour on 2026-09-29.
3. **Voting evidence (Administrator, 1 min).**
   - In the Reviews tab, a queued review's **Voting Distribution** shows its
     reciprocal up-voters and its fastest hour, against the rules they are
     checked against.
4. **Bounty Board (3 min).**
   - `/requests` lists the open requests. *Is the base iPhone 17 enough …?*
     shows "2 answers · waiting for the asker to pick".
   - Sign in as **Joshua**. The notice "2 people answered your request" opens
     the request page; press **Pick as Best Answer** on one review.
   - The request leaves the board, stays on its page, and **Search → Questions**
     for "iPhone 17" still lists it.
   - The Anker Nano request shows the finished state: Best Answer picked by
     Hazel.

**Do not claim:**
- "IP detection" or "same-location voting". No voter IP or location is
  collected. Upvote farming is detected from the voting relationships
  themselves: reciprocity, bursts and repeated cohorts.
- Reverse-image search. No provider is configured, and the panel says so.

**Honesty Score:**
- It is `reputation_score`, a fixed formula (ADR-003 / ADR-014), not a
  percentile: 0.60 × the Wilson lower bound of helpful votes, plus review volume
  and Best Answers, minus strikes.
- Zient's calculation document is still owed.

## 6. Owner actions

| # | Action | Why |
|---|---|---|
| 1 | Run **Defense environment → populate_test** again after any rehearsal on TEST, and after any CI run on `main`. | TEST holds the dataset (95/95, 2026-09-26 01:58 UTC); both put changes on top of it. |
| 2 | Set **`DEFENSE_AUTOSEED=true`** or freeze merges before the defense. | CI writes fixtures into TEST. |
| 3 | Confirm the Preview deployment's API reads TEST (startup log `database` field). | Not readable through the connector. |
| 4 | Optionally set **`DEFENSE_EMAIL_BASE`** to a shared team inbox. | Otherwise codes go to aliases of the root owner's inbox. |
| 5 | Decide **Seeding vs Post-Seeding** earn-gate phase for the defense (currently Post-Seeding, per Zient 2026-09-22). | Open product decision; the dataset shows both a gate-queued review and moderator decisions. |
| 6 | Apply migration **0054** to production with the next `alembic upgrade head` (not a prerequisite for merging). | Checked read-only on 2026-09-25: production already has its 31 listings and no canonical product carries a `source_url`, so 0054 inserts nothing there; it only moves the version marker from 0053. The code does not check the version at runtime. The overview's "Pending Affiliate" becomes the affiliate queue's own count: 6 → 5 in production today. |
| 7 | Delete merged branches in GitHub (the git proxy refuses remote deletes from here) and enable *Automatically delete head branches*. | Clean repository. |
| 8 | Decide where the 2026-09-29 additions are demonstrated (§5b). | They need PR #7 at 0067. Production runs `main` at 0060. TEST is held at 0061. An isolated database needs authorization. |
| 9 | Zient: send the trust-score calculation document, and confirm the formula or a percentile rule. | The panel's "computational methods" question. |
| 10 | Decide whether an escalated report should stay listed until someone dismisses it, and keep comments limited while it does. | Today, escalation closes the report (§C of the meeting ledger). |

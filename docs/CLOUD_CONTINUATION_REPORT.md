# Cloud continuation report — Round 2, trust integrity, Figma parity

| | |
|---|---|
| Date | 2026-09-24 |
| Starting checkpoint | `fix/independent-qa-round-2` @ `0b93add` (verified equal to `origin` after `git fetch --all --prune`) |
| Working branch | `fix/cloud-round2-security-design`, created from `0b93add`; the checkpoint branch is untouched |
| `main` | `e0a4e93`, unchanged. Vercel production deployment `dpl_kGqbs3miCMYZv8p4zaZrW9s3gGMS` serves `e0a4e93` |
| Production | **Not mutated**: no migration, no write, no deploy, no setting, no money |

## 1. Connectors and tools in this session

| Integration | State | Notes |
|---|---|---|
| GitHub | Connected (`bluntly-ph`) | fetch and push, Actions read, PRs |
| Figma | Connected (official remote connector, account `Zienxt`, pro team, admin) | file `lso4Ri4hDaZxvCebhUqlY5` read |
| Supabase TEST (`miysywhcdqkoniaibglx`) | Connected (claude.ai Supabase connector) | only inspected (at `0051`); engineering ran on a local Postgres 17 instead |
| Supabase PROD (`byobedbhodhvocgrkrse`) | Connected; **read-only by discipline** | The connector itself is not scoped read-only. Every production query ran inside `BEGIN TRANSACTION READ ONLY`, and each result carries `transaction_read_only = on`. The repo's project-scoped `supabase` MCP server (in `.mcp.json`) needs OAuth that this non-interactive session cannot complete. |
| Vercel | Connected (team `bluntlyph`, project `prj_AeiZOUlUsyjVZSQjhhqF5vKERmFL`) | production and preview deployments read. Preview deployments of this branch build automatically; none were triggered or promoted. The preview URL could not be fetched (protection or scope). |
| Google Drive | Connected | `BLUNTLY_QA.xlsm` (`1rCyzx6TxfIa_EPGrkBYo0kWyjbScSr2Y`) downloaded and read. Tester statuses are not edited. |
| Apify | **Unavailable**: not installed in the claude.ai connector directory for this org | Not needed for this task. It can be added from claude.ai connectors. |
| google-sheets (repo `.mcp.json`) | Failed to connect: needs a service-account key file | Drive covered the workbook |
| Playwright | Local, with the pre-installed Chromium | used for all journeys |
| Local Postgres | 17.11 (PGDG), disposable cluster | backend suite, migrations, journeys |

**Authorization still useful (not blocking this work):**
- Supabase: authorize the repo's project-scoped `supabase` MCP server (`/mcp` in an interactive
  session) for a connector that is read-only by construction.
- Apify: connect it from claude.ai connectors if public-web research is wanted.
- Vercel: extend the connector's access to preview deployments if previews should be checked from the
  agent.

## 2. Inherited Round 2 work (not rewritten)

The 21 commits `e0a4e93..0b93add` are kept as they were. Two were adjusted as a direct consequence of
this continuation:
- QA-039's Delete now opens from the comment's ⋯, and its journey was updated.
- QA-024's sheet gained the Figma destinations, and its original journey still passes unchanged.

## 3. Trust-stage vulnerability — CONFIRMED and FIXED

Full write-up: `docs/TRUST_DISTINCT_VOTER_SECURITY_FIX.md`. Decision: `docs/adr/016-distinct-voter-evidence.md`.

- **Root cause.** `trust_service` passed `helpful + unhelpful`, summed over every counted review, to
  `evidence_capped_stage`. `uq_review_vote_once` is per (review, voter), so 4 accounts × 5 reviews =
  20 rows (Stage 3), and × 50 = 200 (Stage 5).
- **Reproduced.** `tests/test_trust_ring_exploit.py` runs against the unfixed code on Postgres 17:
  - the 4-ring reached Stage 3 and Stage 5;
  - every zero-weight voter kind still produced Stage 3;
  - the honest paths passed.
- **Fix.**
  - Stage evidence is the sum of `voter_evidence_weight` over DISTINCT voters: at most 1 per person,
    0 wherever §11 gives no weight (claimed seller, probation, Stage 0) or the account is suspended,
    halved if under 30 days at the vote, and halved if under investigation.
  - The thresholds are unchanged: 20 / 60 / 200, now counted in people.
  - The parameter was renamed, so an old row count cannot be passed silently.
- **Concentration.** Checked across a member's whole history, with no reciprocity required. When a
  repeating cohort supplies more than 60% of eligible rows:
  - promotion into Stages 3–5 is held for a moderator, through a system-detected report in the
    existing queue;
  - dismissal releases it, and escalation re-queues it;
  - nobody is demoted, struck or banned by the signal.
- **Honesty Fund** (distribution stays disabled; the formula stays open):
  - vote weight now honours claimed-seller and investigation status (this was a separate bug);
  - suspended voters weigh 0;
  - each review needs 4 people of distinct voter evidence;
  - claimed sellers and held authors are excluded.
  - The payout holding period is documented as a proposal only.
- **Production audit (read-only).** No member is at Stage 3+, and no Stage 3+ badge was ever
  awarded. No voter repeats on any author. The maximum evidence is 1.0 of the 20 required, so there
  are no suspicious accounts. See `docs/TRUST_STAGE_PRODUCTION_AUDIT.md`.

## 4. Figma-blocked QA — resolved against the live file

Full record, with node ids: `docs/FIGMA_ROUND2_VERIFICATION.md`.

| Item | Outcome |
|---|---|
| QA-020 | Spacing already matched the frame. Rows are now uniform, the author's Delete lives in the ⋯, and the Honesty Score is in the byline |
| QA-024 | "Share to…" with a preview and the Figma destinations (Facebook, Reddit, X, Telegram, WhatsApp; Messenger and Viber on phones), Copy link, More. Not drawn: Instagram / Add to Story (no web share address) and Bookmark (omitted by decision) |
| QA-025 | Several categories at once (sheet checkboxes, and toggles in the desktop rail) |
| QA-050 | Pills on Questions: Time, Latest/Oldest, and the product image tile |
| QA-052 | Pills on Sellers: Marketplace, Claimed only, Most reviews, and "N questions answered" |
| QA-053 | Time and Oldest built. Hidden Gems / Controversial / Trending / Budget have no definition, and Trust rating waits on §21: not drawn |
| QA-057 | Seller-review pills and sheets (rating shared with the card, Time, and five orders). **Defect fixed:** half-star seller reviews were missing from the list |
| QA-043 | Share for everyone; the claimed owner's editable response and flag-as-fake. Votes, threaded replies and a viewer report remain a **product decision** |

## 5. Migrations

- No new migration. The head stays **`0053_repair_rejection_links`**. The candidate still contains 0052
  (review_drafts) and 0053 (a data repair), and neither is in production.
- Verified locally on Postgres 17:
  - blank → head;
  - `downgrade -2` → `0051` → head;
  - the business-rules round trip with data: **OK**;
  - the migration safety report: advisory, unchanged.

## 6. Test evidence (local, Postgres 17.11, this branch)

| Gate | Result |
|---|---|
| ruff (app, scripts, sim, tests) | clean |
| Backend without a database (CI "no database" mode) | 1,742 passed, 541 skipped |
| Backend, full, Postgres-backed (CI deselects) | **2,281 passed**, 2 deselected (receipt storage needs the TEST project's key) |
| Milestone verifier | **59/59** |
| Trust security tests | ring exploit 12, holds 10 (incl. the real `/admin/reports` API), fund integrity 6, trust unit 22; Figma API filters 12 |
| Frontend typecheck / lint | clean / clean |
| Frontend unit | **372/372** |
| Production build | OK |
| Playwright on the real stack | **37/37**: 13 business-rule + 13 QA round 2 + 11 Figma parity (desktop 1280 and phone 390), also run serially in CI order |
| Hostile query input on the new parameters | parameterised; invalid enum → 422; unknown category → empty match |

**CI:**
- **DB fast feedback** run `36072513531` on `18e0595`: all green.
  - migrations blank → head, then `downgrade -2` and back;
  - pytest **2,281 passed** on Postgres 17;
  - milestones **59/59**;
  - business-rules round trip OK;
  - browser journeys **37 passed**.
- **CI** (pull request) run `36073000491` on `18e0595`: green (production guard, backend without a
  database, frontend typecheck, lint, unit and build).
- Earlier runs `36064822568` and `36071665979` failed on two things, both fixed:
  - the telemetry-isolation Fund test, which predated the evidence floor;
  - one run-order-dependent journey (QA-052).
- `36072305057` was cancelled by the next push.
- Commits after `18e0595` change this document only.

## 7. Deployment order (for a later, explicitly authorised release)

Superseded on 2026-09-25 by the ten-step sequence in `docs/RELEASE_READINESS.md` §6, which adds the Preview proof and the TEST migration.

1. Back up production.
2. Apply **0052** (additive `review_drafts` table, RLS on) and then **0053** (idempotent one-row repair)
   to production. Both have been exercised down and up locally.
3. Deploy the candidate. The trust fix needs no migration, and since no member is at Stage 3+, no stage
   changes on the first recompute.
4. Keep `honesty_fund_distribution_enabled = false` until the owner decides the formula and the payout
   holding period.
5. Before any tester uses a Vercel **preview** of this branch, confirm that the Preview environment's
   database variables point at TEST. `docs/ENVIRONMENTS.md` still says "Preview: none configured",
   while Preview-scoped variables exist. A preview on the production database would write to production
   with a schema that lacks 0052.

## 8. Remaining product decisions

- Honest-progression tuning after the distinct-voter fix (thresholds, cohort share, whether Stage 1
  voters count in full).
- Honesty Fund formula and payout holding period (§14).
- QA-043 seller-review votes, threaded replies and a viewer report.
- QA-053 Review-score lenses and Budget definitions; Trust rating (§21).
- §21 trust naming (QA-049); the 2.5-star "it depends" track.
- QA-005 social accounts (deferred).

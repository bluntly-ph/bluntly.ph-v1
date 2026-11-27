# Local CI equivalence (GitHub Actions blocked)

**Why this exists.** From 2026-09-28 14:33 UTC, GitHub Actions stopped
allocating runners for `bluntly-ph/bluntly.ph`: every job ends in 2–3 seconds
with no runner and no steps. That includes re-runs and main's own scheduled
job (production maintenance has since moved to Vercel Cron, see
`vercel.json`; the workflow is now a manual backup). The repository is private, so the likely cause is the `bluntly-ph` account's
Actions minutes or spending limit (github.com/settings/billing, signed in as
`bluntly-ph`). That is an external CI infrastructure blocker, not a code
failure.

Until runners return, each branch head is verified locally against the same
jobs, in the same order, with the same commands. **This is not GitHub CI.**
When Actions is available again, fresh exact-SHA CI must run on the current
branch heads. An older SHA's result does not carry over.

## Job-for-job mapping

| GitHub job (workflow) | Local step | Differences |
| --- | --- | --- |
| Production guard (`ci.yml`) | `pytest tests/test_env_guard.py`; then `pytest tests/test_health.py` with the production `SUPABASE_URL` must **fail** (refusal) | none |
| Backend (no database) (`ci.yml`) | `ruff check app/ scripts/ tests/`; `pytest -q` with `DATABASE_URL` pointing at a port nothing listens on (DB tests skip, as in CI); `scripts.check_migration_safety --all` | none |
| Backend (isolated database) (`ci.yml`) | **not reproducible locally**: it runs against the shared TEST Supabase project with repository secrets | covered by the next row on a fresh Postgres 17; TEST itself is not migrated (see below) |
| Backend (ephemeral Postgres 17) (`db-fast.yml`) | fresh database `lci` on local Postgres 17 → `alembic upgrade head` → `downgrade -2` and back → full `pytest` with the same two Storage deselects → `scripts.verify_milestones` → `scripts.check_rules_migration_roundtrip` | same Postgres major version; local socket instead of a service container |
| Frontend (`ci.yml`) | `tsc --noEmit`, `npm run lint`, `npm run test:frontend`, `npm run build` | dependencies already installed from the same `package-lock.json` (no fresh `npm ci`) |
| Browser journeys (`db-fast.yml`) | reseed the e2e database with `scripts.e2e_fixtures`, start the API and the built site, run the workflow's exact spec list with **one worker** (CI's order) and `CI=1` | Chromium from `/opt/pw-browsers`; retries as configured |

The runner script is `local_ci.sh` (kept outside the repository). Every stage
is PASS or FAIL, and any FAIL fails the run.

## Results

### PR #7 — `feat/admin-superadmin-architecture` @ `8a91b71` (2026-09-30, deployment readiness)

Run 2026-09-30, 00:31–00:42 UTC, on a clean worktree. `8a91b71` adds three things to
`cf184ba`: PR #8's startup guard (merged in `6b6103a`), the rate limiter's hashed keys
(`c1d2ea7`), and the Preview-readiness journeys and docs. The commit after it changes only
this file.

| Stage | Result |
| --- | --- |
| guard: env guard unit tests | PASS — 20 passed |
| guard: refuses a production target | PASS — refused |
| backend: ruff | PASS |
| backend: pytest (no database) | PASS — 2,093 passed, 748 skipped (need a database) |
| backend: migration safety report | PASS (report only) |
| db: migrate blank database to head (`0070`) | PASS |
| db: downgrade two steps and back | PASS |
| db: pytest (DB-backed included) | PASS — **2,839 passed**, 2 deselected (Storage key, as in CI) |
| db: milestone verification | PASS — **60/60** claims |
| db: business-rules migration round trip | PASS — "migration round trip: OK" |
| frontend: typecheck (clean `.next`) | PASS |
| frontend: lint | PASS |
| frontend: unit tests | PASS — 429 |
| frontend: production build | PASS — 59 static pages |
| journeys: seed, API, site | PASS |
| journeys: CI set (11 specs, one worker) | PASS — **105 passed**, 2 skipped by design (N and I need a signing site and real Storage), 0 failed, 0 flaky |

**Checked separately on this head:**
- Journey N passed in local Vercel mode: the site ran with `VERCEL=1` and a throwaway signing
  value, and the API trusted only signed addresses.
- The previous head (0061, seeded with PR #5's own defense seed) upgraded to head with every
  count identical. Invariants: 26/26. Defense verify: 12/12 and 109/109.
- On the real Preview for `8a91b71` the API refused to start on the production-pointing
  variables (`UnsafeEnvironmentError`).

The GitHub checks on `8a91b71` are red without running: no runner, as on every head since
2026-09-28. They were not re-run.

### PR #7 — `feat/admin-superadmin-architecture` @ `cf184ba` (2026-09-29, QA patch)

Run 2026-09-29, 21:51–22:00 UTC, on a clean worktree (`git status` empty).
`cf184ba` carries the QA patch: All Reviews, trust recalculation, copied
text, reused photos, shared-network votes, and the new browser journeys
(`174b46f` … `cf184ba`). The commit after it changes only this file.

| Stage | Result |
| --- | --- |
| guard: env guard unit tests | PASS — 20 passed |
| guard: refuses a production target | PASS — refused |
| backend: ruff | PASS |
| backend: pytest (no database) | PASS — 2,066 passed, 748 skipped (need a database) |
| backend: migration safety report | PASS (report only) |
| db: migrate blank database to head (`0070`) | PASS |
| db: downgrade two steps and back | PASS |
| db: pytest (DB-backed included) | PASS — **2,812 passed**, 2 deselected (Storage key, as in CI) |
| db: milestone verification | PASS — **60/60** claims |
| db: business-rules migration round trip | PASS — "migration round trip: OK" |
| frontend: typecheck (clean `.next`) | PASS |
| frontend: lint | PASS |
| frontend: unit tests | PASS — 429 |
| frontend: production build | PASS — 59 static pages |
| journeys: seed, API, site | PASS |
| journeys: CI set (11 specs, one worker) | PASS — **105 passed**, 0 failed, 0 flaky |

**Also checked on this head:**
- **Previous head to head.** The seeded defense database was taken down to
  `0067` (the previously pushed head) and back up to `0070`. Row counts of
  users, reviews, votes, moderation logs, products and commissions were
  identical at every step, and so were the summed Wilson and reputation
  scores. The seven new indexes exist after the upgrade, and both new tables
  have RLS on.
- **Defense scenarios.** `verify --scenarios` on a fresh local seed: 12/12.

**The GitHub checks on `cf184ba` are red without running.** Every job ended
2–3 s after it started, with no runner and no log (404). This is the same
account-level block as on the earlier heads. It was not re-run.

### PR #7 — `feat/admin-superadmin-architecture` @ `3c959bb` (2026-09-29)

Run 2026-09-29, 16:43–16:50 UTC, on a clean worktree (`git status` empty).
`3c959bb` is the 2026-09-29 dev/QA-sync work (`c3522af`) plus one fix found by
the first run on `c3522af`, described below. The commit after it changes only
this file.

| Stage | Result |
| --- | --- |
| guard: env guard unit tests | PASS — 20 passed |
| guard: refuses a production target | PASS — refused |
| backend: ruff | PASS |
| backend: pytest (no database) | PASS — 2,023 passed, 701 skipped (need a database) |
| backend: migration safety report | PASS (report only) |
| db: migrate blank database to head (`0067`) | PASS |
| db: downgrade two steps and back | PASS |
| db: pytest (DB-backed included) | PASS — **2,722 passed**, 2 deselected (Storage key, as in CI) |
| db: milestone verification | PASS — **60/60** claims |
| db: business-rules migration round trip | PASS — "migration round trip: OK" |
| frontend: typecheck (clean `.next`) | PASS |
| frontend: lint | PASS |
| frontend: unit tests | PASS — 423 |
| frontend: production build | PASS — 59 static pages |
| journeys: seed, API, site | PASS |
| journeys: CI set (10 specs, one worker) | PASS — **101 passed**, 0 failed, 0 flaky |

**The run on `c3522af` first** (16:27 UTC) passed every stage but one: journeys
98 passed, **1 failed**, 1 did not run. `br-journeys` "every signed-in page
holds from 320 to 1440 with no errors" recorded React error #418 (a hydration
text mismatch) on `/sellers/{id}` at 1440.
- **Root cause:** the seller review cards and the comment thread print ages
  ("now", "5m") from Client Components that read the clock during render. The
  server's HTML said "now" (59 s) and the browser's hydration said "1m"
  (60 s). This is pre-existing code, not the dev/QA-sync change; it fails only
  when an age crosses a unit in that second, which is why earlier runs passed.
- **Fix (`3c959bb`):** the page reads the clock once and hands it down, as the
  admin review queue already did.
- **Regression:** a new journey runs the browser clock two hours ahead, so any
  age read from the browser's clock disagrees for certain. Without the fix it
  failed 3 of 3 runs with two #418 errors (seller page and comment thread).
  With the fix it passed 3 of 3, and 101/101 in the full run above.

**Earlier runs.** Run 2026-09-28, 22:47–22:59 UTC, one stage after another, on clean
worktrees (`git status` empty at the SHA below).

### PR #7 — `feat/admin-superadmin-architecture` @ `e69c980`

| Stage | Result |
| --- | --- |
| guard: env guard unit tests | PASS — 20 passed |
| guard: refuses a production target | PASS — refused |
| backend: ruff | PASS |
| backend: pytest (no database) | PASS — 2,013 passed, 689 skipped (need a database) |
| backend: migration safety report | PASS — 18 migrations flagged for rollout order (report only) |
| db: migrate blank database to head (`0067`) | PASS |
| db: downgrade two steps and back | PASS |
| db: pytest (DB-backed included) | PASS — **2,700 passed**, 2 deselected (Storage key, as in CI) |
| db: milestone verification | PASS — **59/59** claims |
| db: business-rules migration round trip | PASS — "migration round trip: OK"¹ |
| frontend: typecheck | PASS |
| frontend: lint | PASS |
| frontend: unit tests | PASS — 418 |
| frontend: production build | PASS — 59 static pages |
| journeys: seed, API, site | PASS |
| journeys: CI set (9 specs, one worker) | PASS — **96 passed**, 0 failed, 0 flaky |

### PR #5 — `feat/reporting-module` @ `746e291`

| Stage | Result |
| --- | --- |
| guard: env guard unit tests | PASS — 20 passed |
| guard: refuses a production target | PASS — refused |
| backend: ruff | PASS |
| backend: pytest (no database) | PASS — 1,976 passed, 648 skipped |
| backend: migration safety report | PASS |
| db: migrate blank database to head (`0061`) | PASS |
| db: downgrade two steps and back | PASS |
| db: pytest (DB-backed included) | PASS — **2,622 passed**, 2 deselected |
| db: milestone verification | PASS — **59/59** claims |
| db: business-rules migration round trip | PASS — "migration round trip: OK" |
| frontend: typecheck | PASS² |
| frontend: lint | PASS |
| frontend: unit tests | PASS — 409 |
| frontend: production build | PASS — 57 static pages |
| journeys: seed, API, site | PASS |
| journeys: CI set (7 specs, one worker) | PASS — **68 passed**, 0 failed, 0 flaky |

¹ The first attempt was refused by the script's own safety check. It runs only
on a database it can prove is local, and the socket URL (`host=/tmp`) did not
say so. Re-run over `localhost` TCP, as CI connects: OK. The runner now uses
TCP.
² The first attempt read a `.next/types` file left in the worktree by PR #7's
build (`app/admin/...`, which PR #5 does not have). A fresh CI checkout has no
`.next`. Re-run with `.next` removed: clean. The runner now removes it first.

**Local engineering tests: PASS on both heads.**

## What local verification cannot show

- **TEST (Supabase) migration and the canonical isolated-database job.**
  TEST is at `0061` (PR #5's index, from its verification run on 2026-09-28).
  PR #7's `0064`–`0067` stay off TEST until the coordinated merge; see
  [ADMIN_SUPERADMIN_MIGRATION.md](ADMIN_SUPERADMIN_MIGRATION.md) §3.
- **The Vercel Preview.** See "Vercel Preview" below.

## Vercel Preview

The Vercel project (`bluntlyph` / `bluntly-ph`, services `frontend` and
`backend` per `vercel.json`) builds every pushed head through its Git
integration. Those builds run on Vercel, not GitHub Actions, so they are
unaffected by the Actions block. Each result is reported to GitHub as the
`Vercel` commit status on the exact SHA:

| Branch | SHA | Vercel status |
| --- | --- | --- |
| `feat/reporting-module` (PR #5) | `746e291` | success — "Deployment has completed" |
| `feat/admin-superadmin-architecture` (PR #7) | `3e8249e` | success — "Deployment has completed" |
| `feat/admin-superadmin-architecture` (PR #7) | `e69c980` | success — "Deployment has completed" (22:55 UTC) |

That proves the Preview **build** only. Smoke-testing the Preview was not done,
for two reasons:

1. **The Vercel connector lost access to the project.** On 2026-09-28 at
   ~22:50 UTC it could list the team and project but not read them: get
   project → 404, list deployments → 403 or empty. It also could not fetch the
   protected Preview URL ("your Vercel connection may not have access").
   Earlier the same day it read deployments and environment-variable names.
   Without that access nothing can confirm which Supabase project Preview
   points at (TEST, as required), and no deployment can be created or
   inspected. **Owner action:** extend the Vercel authorization to the
   `bluntlyph` team's `bluntly-ph` project.
2. **PR #7's backend needs TEST at `0067`; TEST is at `0061`.** A Preview of
   PR #7 on TEST would fail on every role read until TEST is migrated, and
   migrating TEST now would break main's code, and PR #5's Preview, on the
   same database. That is a coordinated step for the merge, not a CI
   workaround.

No manual deployment was made, and nothing was promoted. **Production: not
deployed.**

## Status (2026-09-28, 23:00 UTC)

| | PR #5 `feat/reporting-module` | PR #7 `feat/admin-superadmin-architecture` |
| --- | --- | --- |
| Exact SHA verified | `746e291` | `e69c980` (this file is added on top, docs only) |
| GitHub push | SUCCESS | SUCCESS |
| Local engineering tests | PASS | PASS |
| Vercel Preview build | PASS (`Vercel` commit status) | PASS (`Vercel` commit status) |
| Vercel Preview smoke | NOT RUN: connector has no project access, Preview database unconfirmed | NOT RUN: same, plus TEST is not at `0067` |
| GitHub CI | BLOCKED: external account billing/usage limit | BLOCKED: external account billing/usage limit |
| Production | NOT DEPLOYED | NOT DEPLOYED |

"CI passed" is never claimed from this record. When runners return, run fresh
exact-SHA CI on each branch's current head.

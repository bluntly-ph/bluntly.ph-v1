# PR #7 QA environment: Preview → isolated QA database

Written 2026-09-30. Goal: PR #7's Vercel Preview runs on an **isolated QA database**
migrated to the current head (0070) with the deterministic defense seed, so the QA patch can
be retested on a real deployment. Production stays read-only. Shared TEST stays at 0061,
which `main` and PR #5 run on.

## 1. Where things stand

| Item | State (verified 2026-09-30) |
|---|---|
| PR #7 migration head | `0070_vote_network_fingerprints` |
| Shared TEST (`miysywhcdqkoniaibglx`) | 0061, untouched |
| Production (`byobedbhodhvocgrkrse`) | untouched |
| Supabase organisation `bluntly-ph` | **Free plan**, two projects (production and TEST), no branches. Branching and a third project need a paid plan. |
| Vercel team | no Postgres or Neon integration installed |
| Vercel project `bluntly-ph` | web and API are two services of **one** project, so one project variable reaches both |
| Preview-scoped variables | still name **production**; no branch-scoped overrides exist |
| PR #7 Preview safety | PR #7 now contains PR #8's startup guard: while its variables name production, its API **refuses to start** instead of reaching production data |
| Credentials in the agent's session | none for Vercel, Supabase or any database |

**Why the agent stopped short of wiring it.** Every remaining step needs a secret (a database
password, a JWT secret, the client-IP signing secret, the Preview bypass secret). A secret the
agent generated would pass through its tool calls into the conversation record, which is
printing it. So the owner enters secrets. The agent needs only the ones it uses itself, given
through the environment settings (section 4), never in chat.

## 2. Choose the QA database (owner decision)

| Option | Cost | Touches | Notes |
|---|---|---|---|
| **A. Supabase Pro** → a branch of TEST, or a third project `bluntly-ph-qa` | paid plan | nothing shared | Cleanest. The defense and fixture seeds accept only TEST or a local database today. A new project ref needs its ref added in `backend/scripts/defense/guard.py` (one line, reviewable). |
| **B. A separate database inside the TEST project** (`bluntly_pr7_qa`, with its own login role) | free | adds a database to the shared TEST project and shares its free-plan quota. TEST's `postgres` database (0061; `main` and PR #5) is **not** touched. | Fastest. Needs your explicit authorisation, because it is a change inside shared TEST. Connect through the session pooler with the database name, and confirm the first connection works. |
| **C. Neon Postgres from the Vercel Marketplace**, scoped to this branch's Preview | free tier | nothing in Supabase | Storage (review photos) stays on TEST. Check that Storage still reads `SUPABASE_URL` when the database is not Supabase before relying on it. |

**Recommendation:** B, if a database inside the TEST project is acceptable; otherwise A.

## 3. Branch-scoped Preview variables

Vercel supports variables for one git branch of the Preview environment. Go to Project
`bluntly-ph` → Settings → Environment Variables → Add. Set **Environment: Preview**, then
**Branch: `feat/admin-superadmin-architecture`**, and **type: Sensitive**. These override
the shared Preview values for this branch only. PR #5, `main` and production are not affected.

| Variable | Value (enter in Vercel; never paste in chat) | Why |
|---|---|---|
| `SUPABASE_CONNECTION_STRING_SESSION_POOLER` | the QA database, session pooler | migrations; the runtime derives the transaction port from it |
| `SUPABASE_CONNECTION_STRING` | the QA database, direct | fallback |
| `SUPABASE_URL` | `https://miysywhcdqkoniaibglx.supabase.co` (TEST) | Storage for review photos |
| `SUPABASE_SECRET_KEY` | TEST's secret key | Storage uploads |
| `SUPABASE_PUBLISHABLE_KEY` | TEST's publishable key | |
| `SUPABASE_JWKS_URL` | TEST's JWKS URL | the guard checks that every target names the same, non-production project |
| `JWT_SECRET` | a new random value, 32+ characters, **not production's** | a session minted on QA must never open production |
| `PII_HASH_SALT` | a new random value | keys the network, rate-limit and click hashes |
| `CLIENT_IP_SIGNING_SECRET` | a new random value (`openssl rand -hex 32`, typed straight into Vercel) | the site signs the voter's address for the vote-farming signal. **One project variable reaches both the web and the API service**, so both use the same value. |
| `PAYOUT_PROVIDER` | `paypal_sandbox` | the shared Preview values cannot be read back to confirm they are sandbox |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` | same |
| `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` | the **sandbox** app's | same |

`APP_ENV` stays `staging` (the shared Preview value).

Then redeploy the branch's latest Preview. Its startup log line `production readiness` must name
the QA or TEST project, never production. If anything still names production, the guard stops
the API, and the log says which variable.

## 4. What the agent needs to continue

Add these in the Claude Code cloud environment (the environment menu in the session's title
bar → Edit → environment variables). A new session picks them up. Never paste them into chat.

| Variable the agent reads | What it is |
|---|---|
| `QA_DATABASE_URL` | the QA database's session-pooler connection string: to migrate and seed |
| `QA_JWT_SECRET` | the same value as the branch's `JWT_SECRET`: the journeys' fixture sessions are minted with it |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | Vercel → Settings → Deployment Protection → Protection Bypass for Automation: Previews are behind Vercel SSO |

## 5. Migrate and seed the QA database

Run from `backend/` with the QA target. Every script prints its target first and refuses
production.

```bash
export BLUNTLY_TEST_ENV=1 APP_ENV=staging USE_SUPABASE=true \
  SUPABASE_CONNECTION_STRING_SESSION_POOLER="$QA_DATABASE_URL" \
  SUPABASE_URL=https://miysywhcdqkoniaibglx.supabase.co JWT_SECRET="$QA_JWT_SECRET"
python -m scripts.print_env_target                      # must name TEST/QA, never PRODUCTION
python -m alembic upgrade 0061_commission_reviewer_index  # where TEST is today
#   seed TEST-like data at 0061 with PR #5's code (a git worktree at 746e291):
#   python -m scripts.defense.seed
python -m alembic upgrade head                          # previous head -> 0070
python -m scripts.check_invariants --strict
python -m scripts.defense.seed --reset --out defense-seed.json   # the deterministic dataset
python -m scripts.defense.verify --scenarios && python -m scripts.defense.verify
python -m scripts.e2e_fixtures e2e-fixtures.json        # the journeys' own accounts
```

Then check the database itself, with the SQL used in the rehearsal (section 7):
- RLS is on for `image_fingerprints` and `vote_network_fingerprints`.
- `anon` and `authenticated` have no privilege on any table.
- No default privileges are left for them.
- The seven new indexes and two unique constraints exist.

## 6. Preview retest

```bash
E2E_FIXTURES=e2e-fixtures.json E2E_API_URL=<preview origin> PLAYWRIGHT_BASE_URL=<preview origin> \
E2E_EXPECT_NETWORK_SIGNAL=1 E2E_STORAGE=1 \
npx playwright test e2e/review-queue-wilson-journeys.spec.ts e2e/admin-journeys.spec.ts \
  --project=chromium --workers=1
# VERCEL_AUTOMATION_BYPASS_SECRET comes from the environment; traces are off while it is set.
```

This covers:
- **Review Queue and All Reviews:** A and B each with its own Wilson (Q); a new review in All
  Reviews, Wilson sorting both ways, and Refresh (R).
- **Trust:** the Honesty Score shown, then recalculated after an approval (T).
- **Integrity evidence:** copied text (D); a site vote through the BFF producing the network
  signal, with no address in any staff response (N); a reused photo (I).
- **Access:** Administrator and Super Admin (`admin-journeys`).

Afterwards, read the deployment's runtime errors in Vercel.

## 7. Rehearsed locally (2026-09-30)

- **Previous head → head on seeded data.** A database at 0061 was seeded with PR #5's own
  defense seed, then upgraded to 0070 with the current code.
  - Users, reviews, votes, moderation logs, products, commissions and questions are identical,
    and so are the summed Wilson and reputation.
  - The one moderator became an administrator.
  - Invariants: 26 of 26.
  - The current seed with `--reset` then gave `verify --scenarios` 12 of 12 and the full
    `verify` 109 of 109.
- **Supabase's default grants, simulated.** Migrating a fresh database under Supabase-style
  default privileges left no table readable by `anon` or `authenticated`, and no default
  privilege for them. Twelve tables created before the QA patch have no RLS; the revocation is
  what protects them there.
- **The site-vote path in Vercel mode.** The site ran with `VERCEL=1` and a throwaway local
  signing value; the API trusted only signed addresses.
  - Three accounts under 30 days old up-voted through the browser (browser → BFF → API) and
    produced the shared-network report.
  - The network rows are 32-hex keyed hashes.
  - After the rate-limit fix, the whole database holds no raw address.
  - Journeys Q, R, T, D and N passed; I skipped for want of Storage.

## 8. Raw IP addresses: what the platform stores

| Where | Before 2026-09-30 | Now |
|---|---|---|
| Vote-farming signal (`vote_network_fingerprints`) | — | keyed hash of the network only, 30 days |
| Rate limiter (`rate_limit_counters`, used because Redis is not configured) | **the raw address as the key** (`rl:vote:<address>`), pruned only after an hour | keyed hash of the address (`app/core/rate_limit.py`) |
| Affiliate click sessions (`/r/...` redirect) | raw address kept 30 days, then hashed, deleted at 90 (Architecture §4 retention) | unchanged: a documented retention policy, so any change is the owner's decision |

The rate limiter keys on the first `X-Forwarded-For` hop, as before. On Vercel the edge writes
that header. Behind the BFF, every site user may therefore share one key; this was not changed.

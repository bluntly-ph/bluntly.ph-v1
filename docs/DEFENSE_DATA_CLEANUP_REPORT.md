# Defense data cleanup report

What was found, what was cleaned, and what is left for the owner, on each
environment. Date: 2026-09-25.

## TEST (`bluntly-ph-test`) — cleaned by the tooling

**State before.** TEST is shared with CI's isolated-database job, which
accumulates every run's fixtures (see `ci.yml`). Read-only count on
2026-09-25, schema at `0053_repair_rejection_links`: **29,817 accounts, of
which 29,719 are `@example.com` fixtures**, 15,546 products and 12,746
reviews. A panel cannot be shown that.

**Why a full content reset, not a prune.** `reviews.author_id` is
`ON DELETE SET NULL`: deleting fixture users alone would leave their reviews
behind as "deleted account" posts. So `scripts.defense.reset --apply`:

- `TRUNCATE`s every public table except `alembic_version`, `badges`,
  `membership_tiers`, `cron_credentials`, `cron_runs` and `users` (and refuses
  to run if a kept table references a truncated one);
- deletes fixture and demo accounts only (`@example.com`, `@bluntly.local`,
  `@example.ph`, `@showcase.bluntly.ph`, `@demo.bluntly.ph`) and keeps every
  other account, content-free, with wallet, trust and flags reset — so the
  owner's real test logins and the personas' sessions survive;
- empties the `review-photos`, `product-images` and `avatars` buckets.

It prints the full plan (tables, row counts, accounts kept) as a dry run
first; the workflow runs the dry run, then `--apply`, then the seed, then
`verify`. The plan and result are in the `populate-test` job log.

**Status.** TEST is populated by **Actions → Defense environment →
populate_test** (the TEST credentials exist only as repository secrets, so
this environment cannot reach TEST directly).

**State after** (run 36206750933, 2026-09-26 00:58–01:58 UTC, schema
`0054_record_source_listings`): `verify` **95/95 READY**. Read back from TEST:
34 accounts, **0** `@example.com`; the six personas at their stages
(`kristinev` 3, `mariareyes` 2, `paolo_mendoza` 1, `jomar_deals` 2 under
investigation, `rico_powerhub` seller, `mod_joanna` moderator); 15 canonical
products, all with images, and 2 pending submissions; 48 reviews dated
2026-03-10 to 2026-09-24, 276 votes, 37 comments, 11 questions, 17
commissions, 2 payouts; 569 view buckets; moderation history on 78 distinct
days. A CI run on `main` after this puts fixtures back (runbook §2).

## The dataset — gibberish sweep

`verify` sweeps every visible field (review titles, bodies, verdict
explanations, audiences, pros and cons; comments; questions and answers;
store reviews and responses; product and store names; display names and
usernames; review requests) for placeholder and debug text (`lorem`,
`asdf…`, `test123`, "test review", `foo`, `TODO`, `undefined`, `null`, `NaN`,
six repeated characters, `@example.com`, …). Result on the seeded database:
**0 hits**. `tests/test_defense_scripts.py` runs the same sweep over the
dataset source in CI.

## Production — read-only audit (nothing changed)

Read through the site's public API (`www.bluntly.ph/api/bff`), GET only:

| Area | Found |
|---|---|
| Products | 43 listed: 33 canonical, 10 pending submissions |
| Product images | 38 of 43 have none (placeholder shown) |
| Reviews | 25 public, by 7 authors; sweep: 0 hits |
| Questions | 10; sweep: 0 hits |
| Stores | 3; sweep: 0 hits |
| Review requests | 8; **1 hit**: `req_2f7ae3b8ce` "test product" / "test details test details…" (expired) |

Product names a moderator should look at (not caught by the sweep, found by
reading the list):

| Name | Problem |
|---|---|
| `ModLoopProbe 1786340188` (canonical) | a QA probe left in the catalogue |
| `What type of material used in Simwood pants?` (canonical) | a question typed as a product name |
| `https://s.shopee.ph/9AOhbTdlhg`, `https://s.lazada.com.ph/s.Z7XQ1V?c=w` (pending) | submissions named by their link |
| one pending submission with no name | nothing to canonicalize from |
| `Jisulife`, `Iphone 15`, `Molten` (canonical) | incomplete names (brand only, or no key spec) |

**Owner actions (production, deliberately not done here).** Remove the "test
product" request and the probe product from the moderator console; name or
attach the link-named submissions with the new *Name as a new product* control
once this release is deployed; rename the incomplete canonical names; add
images for the 38 products (the *Add image* control from QA-001). None of this
is bulk or automatic, by design.

## Local rehearsal databases

`defense` (the dataset), `e2e` (the journeys' fixtures) and `ci` (the pytest
database) on a local Postgres 17, all disposable, none reachable from outside
this container.

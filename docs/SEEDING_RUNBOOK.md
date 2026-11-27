# Seeding runbook: removing old test reviews and reseeding

Owner decision 2026-09-28: the team seeds proper data and removes old test
reviews. This page covers the order to work in, which tool to use at each step,
and what each tool will never do.

**The flow is always:** dry run, then list, then the owner/team verifies the
list, then cleanup, then seed, then verification. No step runs against
production without an explicit, separate owner authorization (§4).

## 1. Choose the path

| Situation | Path | Tooling |
|---|---|---|
| TEST should hold **only** the clean dataset | **A. Full reset** | `scripts.defense.reset`, `seed`, `verify` (already used for the defense; see [DEFENSE_RUNBOOK](DEFENSE_RUNBOOK.md)) |
| TEST keeps most of what it has, and only specific old test reviews go | **B. Selective purge** | `scripts.purge_test_reviews` (new) |
| Test content is visible on **production** | **C. Production takedown** | A separate reviewed procedure, never automatic (§4) |

All commands run from `backend/` with the TEST environment loaded
(`backend/.env.test` with `BLUNTLY_TEST_ENV=1`; see [ENVIRONMENTS](ENVIRONMENTS.md)).
Every writing script prints its target on the first line (`[env] … -> test | …`).
If that line does not say `test`, stop.

## 2. Path A: full reset of TEST

```bash
python -m scripts.defense.reset                 # DRY RUN: every table + row count, the accounts kept
python -m scripts.defense.reset --apply         # after the team has read the dry run
python -m scripts.defense.seed --out seed.json  # deterministic; refuses a DB that already holds it
python -m scripts.defense.verify --json verify.json   # exits 1 if anything essential is missing
python -m scripts.check_invariants --strict     # read-only: wallets, shares, orphans, FKs
```

`defense.reset` keeps real accounts (content-free) and the reference tables. Its
guard refuses production, a target without the test marker, and an
unrecognised database. From GitHub Actions, use **Defense environment → Run
workflow → populate_test** (about 1.5 hours from a runner).

## 3. Path B: selective purge on TEST

`scripts/purge_test_reviews.py` deletes **only the review IDs written into a
reviewed selection file**, and only after the file's digest is typed back.
It has no "delete all" mode. Its API has no endpoint and its UI has no button.

```bash
# 1. LIST (read-only, safe anywhere): whole threads together, one line each
python -m scripts.purge_test_reviews --out selection.tsv

# 2. VERIFY: the owner/team edits selection.tsv
#    - a line starting with '#' is NOT selected
#    - only the test-suite class is pre-selected; showcase/local-seed lines
#      start commented out and must be uncommented on purpose
#    - lines marked [BLOCKED: …] carry money evidence or an open report and
#      cannot be purged

# 3. CHECK (read-only): re-validates every selected line against the database
python -m scripts.purge_test_reviews --select selection.tsv
#    prints counts per class, any REFUSED / BLOCKED / PARTIAL THREAD line,
#    and the selection's digest

# 4. PURGE (TEST only; all or nothing, one transaction, audited)
python -m scripts.purge_test_reviews --select selection.tsv \
    --actor USR-000001 --confirm <digest> --apply

# 5. SEED, then VERIFY
python -m scripts.defense.seed --out seed.json        # or the team's chosen seeder
python -m scripts.defense.verify --json verify.json
python -m scripts.check_invariants --strict
```

**What counts as a candidate.** Only these author email markers are used.
Nothing is inferred from a review's text, age or activity.

| Class | Author email | Pre-selected |
|---|---|---|
| `test_suite` | `@example.com` (pytest, Playwright fixtures, milestone verifier) | yes |
| `local_seed` | `@example.ph` (`scripts/seed.py`'s sample shopper) | no |
| `showcase` | `@showcase.bluntly.ph` (`scripts/seed_showcase.py` demo authors) | no |

A review by any other account is never listed. If someone types its ID into
the file anyway, it is refused at check time and at apply time.

**What refuses the whole run.** Nothing is deleted if any of these apply:

- A selected review has a `commissions`, `honesty_fund_distributions`,
  `affiliate_postbacks` or `token_transactions` row pointing at it. That is
  payout/accounting evidence, so it is never erased. Take such a review down
  instead (§4); a takedown hides it and can be undone.
- A selected review, or a comment under it, has an **open** report. That is
  someone's complaint still waiting on a decision; resolve it in the console
  first. Closed reports are history and do not block.
- Only part of a thread is selected. Threads are purged whole.
- `--confirm` does not match the digest of exactly this selection.
- `--actor` is not a Super Admin.
- The target is production. `--apply` is refused there, and so is
  `--allow-production`.

**What goes with a purged review:** its votes, comments, versions, affiliate
link and reading telemetry (their foreign keys cascade), and the price reports
made from it. Those are test data too, and left behind they would stay in the
public price history with no source. Each affected product's review count,
median rating and trust rating is then recomputed.

**What is kept:** accounts, products, every review that was not selected, and
moderation history (closed reports and decisions). Click sessions and support
requests stay, with their link to the review cleared. Commissions and similar
rows are never involved, because such reviews are refused. Photo and receipt
objects in storage are left alone; the check step counts them.

**Audit:** each purged review leaves a `moderation_logs` row with action
`remove` and context `event=test_data_purge`. The row carries the class, the
public review ID, the title, the author handle and the selection digest. The
table has no foreign key to `reviews`, so the audit row survives the deletion.
Test coverage: `backend/tests/test_purge_test_reviews.py`.

## 4. Path C: production takedown (a separate, reviewed procedure)

Nothing in this runbook runs against production by default, and nothing runs
there automatically. If test content must come off the live site:

1. **Owner authorization in writing** for this specific production mutation.
2. **Read-only listing first.** `python -m scripts.purge_test_reviews --out prod-selection.tsv`
   is read-only and prints the target. Run it with production credentials only
   on the owner's machine, and share the file for review.
3. **Hide, don't delete.** An Administrator takes each review down from the
   review page or the console: **Take down (staff)**, which requires a reason
   and is audited. For a reviewed batch of test-suite content,
   `python -m scripts.hide_test_content` (dry run) followed by
   `--apply --allow-production` flips `is_removed` on test-account reviews
   only. `--revert --apply --allow-production` restores them. Hiding keeps
   every financial row intact.
4. **Never purge on production.** `purge_test_reviews --apply` refuses
   production outright. There is no override, by design.
5. Run `python -m scripts.check_invariants` (read-only) afterwards and keep
   its output with the authorization.

## 5. Checklist for seeding day

- [ ] `[env]` line names TEST on every command
- [ ] Dry run / listing produced and read by the team
- [ ] Selection file reviewed (Path B) or reset plan read (Path A)
- [ ] Cleanup applied; digest recorded
- [ ] Seed ran; `seed.json` kept
- [ ] `defense.verify` passed; `check_invariants --strict` passed
- [ ] Production untouched (unless §4 was authorized separately)

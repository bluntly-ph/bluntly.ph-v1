# Admin priority tiers

Source: the owner's dev note of 2026-09-26 ("Updated Dev Note"). Code:
`backend/app/services/priority_tiers.py` (the pure rule),
`priority_triage.py` (facts, aging, the hourly job), `priority_settings.py`
(thresholds). Tests: `backend/tests/test_priority_tiers.py` (46 pure cases),
`backend/tests/test_priority_triage_api.py` (6 on a real database).

## What a tier is, and is not

A tier is a **triage label** on an item that is **already** in a queue — the
earnings (earn_eligible) queue or the content-report queue. It sorts, filters
and explains. It does **not** decide membership:

* a review still reaches the earnings queue only through the gate
  (`earn_gate.maybe_queue`); content still reaches the report queue only by
  reports;
* computing tiers, and the hourly job, never change `earn_eligible_status`,
  never file or resolve a report, never add or remove an item;
* any item can be opened and decided in any order.

`test_priority_never_puts_an_item_into_a_queue_or_changes_its_state` runs the
whole job over a seeded queue and asserts membership and every earning state
are unchanged.

## The rule

Three risk signals can converge:

| Signal | Meaning | Default |
|---|---|---|
| A | The gate's weighted Wilson lower bound sits in the band around 0.65 | 0.60–0.70, inclusive |
| B | At least one upvoter is High or Critical risk (below) | — |
| C | Fraud reports on the item (`fake_proof`, `seller_posing_as_buyer`, `counterfeit`) | 2 or more |

| Tier | When |
|---|---|
| **Highest** | Two or more of A, B, C at once. One signal alone never reaches it. |
| **High** | Exactly one of A, B, C; **or** exactly one fraud report (a signal of its own, which never converges); **or** the first submission ever from a Stage 0 account (can make an item High, never Highest on its own). |
| **Low** | Author at Stage 3+, zero reports of any kind, no High/Critical voter anywhere in the author's received votes, and a Wilson trend that is stable or rising. |
| **Lowest** | The same, with the author at Stage 4 or 5. Shown as "Lowest · routine spot-check" — a label, not a different check. |
| **Neutral** | Everything else. |

Every tier carries its reasons (codes and plain-language labels), shown on the
queue row's badge, in the detail panel, and on each report.

## Voter risk — PROVISIONAL MAPPING, for the owner to confirm

The dev note reads voter risk (Baseline / Elevated / High / Critical) from "the
existing voter risk table". No such table or score exists in the codebase
(`docs/FULL_FEATURE_MATRIX.md` row 8.10). Rather than invent a scoring, the
four levels are mapped, deterministically, onto enforcement state that already
exists:

| Level | Mapped from |
|---|---|
| Critical | suspended, under investigation, or a vote-concentration finding upheld by a moderator (ADR-016) |
| High | on probation, or a vote-concentration hold awaiting a moderator |
| Elevated | account younger than the 30-day maturation window, or carrying a strike |
| Baseline | none of the above |

Only High and Critical count for signal B and for losing Low/Lowest.

## Wilson and its trend

The tiers read the same number the 0.65 gate reads: the trust-weighted Wilson
lower bound over votes snapshotted at vote time (`earn_gate.gate_state`). The
**trend** compares that bound now with the same bound over only the votes cast
before the trend window (7 days by default). A change within ±0.02 is
"stable"; no earlier votes is "unknown", which does not block Low.

## Aging (anti-starvation)

An item left **undecided** past the aging window (72 hours by default) moves up
**exactly one tier, once**: Lowest → Low → Neutral → High → Highest. It never
skips a tier.

* The clock starts when the item entered the queue (recorded in
  `queue_triage.entered_at`; for items queued before this shipped, the review's
  creation time or its unpublish time stands in — so on first deploy, items
  already older than the window age immediately, which is the intended
  catch-up).
* **Opening or previewing an item is not a decision** and writes nothing.
  (`test_aging_moves_one_tier_after_the_window_and_viewing_does_not_reset_it`.)
* A decision (approve, reject, resolve, dismiss) restarts the clock
  (`test_a_decision_restarts_the_clock_and_voids_the_aging`).
* The hourly job `priority_tiers` (Vercel Cron: `GET /api/v1/internal/cron/tick` every five minutes, from `vercel.json`; due from :15)
  stamps `aged_at`; reads only apply it.

## Thresholds

Stored in `platform_settings` (key `priority_tiers`), validated whole — an
invalid combination (band low > high, convergence below the single-report
minimum, Lowest stage below Low, an unknown reason) is refused and nothing is
saved.

| Key | Default |
|---|---|
| `wilson_band_low` / `wilson_band_high` | 0.60 / 0.70 |
| `fraud_high_min` / `fraud_convergence_min` | 1 / 2 |
| `aging_hours` | 72 |
| `low_min_stage` / `lowest_min_stage` | 3 / 4 |
| `trend_window_days` / `trend_tolerance` | 7 / 0.02 |
| `fraud_reasons` | fake_proof, seller_posing_as_buyer, counterfeit |

`GET /api/v1/admin/priority-settings` — moderators (the queue explains tiers in
these numbers). `PUT` — the site owner only (`require_root_owner`): a change
reorders every moderator's queue at once. There is no settings screen yet;
the owner changes them through the API.

## In the console

* **Earnings queue** — default order is by tier (Highest first, then oldest
  clock). A tier select filters; sort options: priority tier, policy order,
  oldest. Tier chips show counts over the filtered queue.
* **Report queue** — default order stays **escalation order** (Business Rules
  §12: urgent reasons — safety, personal information — on top). Every report
  shows its item's tier and "Why …" reasons; tier filter and tier sort are
  available. A tier sort there is the moderator's choice, never the default,
  so a tier can never bury an urgent report.

## Scheduler fix shipped alongside

`.github/workflows/scheduled-maintenance.yml` mapped its 21:00 UTC entry to
`sweep_contracts`, a task name the internal cron endpoint does not have — so
the daily integrity sweep never ran from the schedule. It now maps to
`integrity_sweep`.
This takes effect only when the branch is merged.

Since then the workflow has lost its schedule: Vercel Cron's tick runs every
task (`internal_cron.SCHEDULE`), and the workflow is a manual, one-task backup.
`test_the_workflow_is_a_manual_backup_that_names_only_known_tasks` keeps its
dispatch options inside the endpoint's allow-list.

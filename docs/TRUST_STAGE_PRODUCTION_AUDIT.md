# Trust-stage production audit (read-only)

**Question:** has the "evidence counts vote rows, not voters" exploit
(`docs/TRUST_DISTINCT_VOTER_SECURITY_FIX.md`) already been used in production?

**Answer: no.** Production has no member at Stage 3 or above, and it has never
awarded a Stage 3+ badge. No author has any voter who voted on more than one of
their reviews. The largest distinct-voter evidence any author has is **1.0**,
against the **20** Stage 3 requires. Deploying the fix therefore changes no
current production stage.

## Method

| | |
|---|---|
| Project | `byobedbhodhvocgrkrse` (production), via the Supabase connector |
| Schema at audit | Alembic `0051_product_median_column`: the candidate's 0052/0053 are not applied |
| When | 2026-09-24, during the cloud continuation session |
| Access | Every query ran inside `BEGIN TRANSACTION READ ONLY … COMMIT`, and every result row carries `current_setting('transaction_read_only') = on`. SELECT only; no DDL, DML, settings, functions or storage touched. |
| Identities | Pseudonymous: `left(md5(uuid), 8)`. No names, emails, handles, staff refs or IP data were read into this document. |

The per-author measures use the post-fix definitions (ADR-016):

- **Counted reviews**: public, not removed, earn status `approved`, `monetized`
  or `honesty_fund`, as trust counts them.
- **Voter evidence**: one per distinct voter. It is 0 for Stage 0, claimed-seller,
  probation or suspended voters; halved if the account was under 30 days old at
  the vote; halved if under investigation.
- **Repeated cohort**: eligible voters present on at least half of an author's
  counted reviews, and on at least three of them.

## Aggregate findings

| Measure | Value |
|---|---|
| Users | 20 |
| Trust stage distribution | Stage 0: 13 · Stage 1: 3 · Stage 2: 4 · **Stage 3+: 0** |
| Stage 3+ badges ever awarded (`established_reviewer`, `trusted_reviewer`, `community_expert`) | **0** |
| Public reviews | 25 |
| Vote rows (all reviews) | 10, cast 2026-08-21 … 2026-09-24 |
| Distinct voters | 7 |
| Vote rows from Stage 0 voters (zero weight under §11) | 7 of 10 |
| Vote rows from claimed-seller / probation / suspended voters | 0 |
| Votes cast before the 0050 weight snapshot (`vote_weight IS NULL`) | 8 |
| Users claimed-seller / probation / suspended / under investigation | 0 / 0 / 0 / 0 |
| Open system-detected reports | 0 |

### Per author (every author who has received a vote)

| Author (pseudo) | Stage | Verified counted reviews | Up / down rows | Distinct voters | Eligible voters | Voter evidence | Most reviews by one voter | Cohort share |
|---|---|---|---|---|---|---|---|---|
| `77793b75` | 2 | 2 | 3 / 2 | 5 | 1 | 1.0 | 1 | 0 |
| `b967c888` | 2 | 2 | 1 / 1 | 2 | 1 | 1.0 | 1 | 0 |
| `59f985ed` | 1 | 0 | 1 / 1 | 2 | 1 | 1.0 | 1 | 0 |
| `5b31a6c6` | 2 | 1 | 0 / 1 | 1 | 0 | 0 | 1 | 0 |

Concentration ratio (the largest repeated cohort's share of the eligible
evidence) is **0** for every author. No voter appears on two reviews by the same
author, so no cohort exists at all.

### Voters recurring across authors

The report asks whether one small voter set recurs across several authors'
histories. It does not:

| Voter (pseudo) | Stage | Votes | Distinct authors | Up |
|---|---|---|---|---|
| `5b31a6c6` | 2 | 3 | 3 | 1 |
| `b5c174b7` | 0 | 2 | 2 | 2 |
| five others | 0 | 1 each | 1 each | — |

The one Stage 2 voter spread three votes over three authors and two of them were
down-votes. That is ordinary participation, not a boosting pattern. Voter
`5b31a6c6` is itself author `5b31a6c6` above, which is expected: people who
write reviews also read and vote on others.

### Honesty Fund state

| Measure | Value |
|---|---|
| Reviews routed to the fund | 1 |
| Fund pool accrued (`commissions.honesty_fund_share`) | ₱0.00 |
| Distribution rows | 0 |
| `honesty_fund_distribution` audit entries | 10, all for synthetic cycles 1900-01 … 1901-07, written 2026-07-26 … 2026-08-19 |

The ten audit entries name cycle months in 1900–1901 and a ₱30.00 pool, which is
the fund test fixture's shape. They match the documented 2026-08-19 incident, in
which the test suite ran against the live database; no corresponding
distribution rows remain. No real money has moved through the fund. They are
recorded here for completeness and need no action from this task.

## Suspicious accounts for admin follow-up

**None.** No account meets any part of the exploit's fingerprint: no Stage 3+
member, no repeat voter on any author, no cohort, no cross-author ring.

## What changes at deployment

- `recompute_user_trust` will compute the same stages it does today for all 20
  members. Nobody is on the score ladder at Stage 3, so the new per-voter read is
  never reached.
- Honest progression is harder from now on. Stage 3 needs 20 distinct eligible
  people. Seven of the ten existing votes came from Stage 0 readers, who are not
  evidence. `docs/TRUST_DISTINCT_VOTER_SECURITY_FIX.md` §Product impact covers
  this.
- The fund stays disabled (`honesty_fund_distribution_enabled = False`).

## Production mutated

**No.** No stage, vote, account, report, setting or money was changed.

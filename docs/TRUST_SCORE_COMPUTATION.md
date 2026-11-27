# Trust Score computation

QA item (2026-09-29): *"The system should document and implement the defined computational
method for calculating and updating the user Trust Score, including how votes, trust stages,
and trust-score percentages contribute to the calculation."*

This document describes what the code computes today, formula by formula, with the file each
formula lives in. It defines nothing new: every number below is from an accepted decision
record or the Business Rules, and is pinned by a test (§10).

**Sources of authority, in order:**
- **Business Rules (Full Record, 2026-09-23):** §8 (Stage 1 to comment), §9 (claimed sellers),
  §11 (vote weights), §12 (reports and system signals).
- **ADR-003 (Accepted, M0):** the "trust score percentage". The PRD left it undefined (PRD A1);
  ADR-003 defined it as `reputation_score`.
- **ADR-014 (Accepted, 2026-08-04):** the Wilson-based helpfulness, the re-derived stage
  thresholds and the evidence gate.
- **ADR-016 (Accepted, 2026-09-24):** evidence counted in distinct eligible people, and the
  concentration hold. See `docs/TRUST_DISTINCT_VOTER_SECURITY_FIX.md`.
- **ADR-004:** Wilson, 45-day decay, velocity and reciprocity parameters.

**Open dependency:** Zient's own calculation document is still owed (dev/QA sync 2026-09-29,
ENG-0929-H). If it differs from ADR-003, the owner decides which one stands. Until then the
formula below is the implemented and accepted one. **PRODUCT DEFINITION REQUIRED** applies only
to the specific points in §9, not to the formula.

## Owner review block — OWNER VALIDATION REQUIRED — ZIENT

Written 2026-09-30 for Zient to confirm or correct. The formula has not been changed; this block
only restates it. The status stays **OWNER VALIDATION REQUIRED — ZIENT** until Zient confirms it
in writing.

**CURRENT IMPLEMENTED FORMULA** (the public Honesty Score, 0–100, shown rounded to a whole number):

```
helpfulness = 100 × WilsonLB(helpful votes, helpful + unhelpful votes)   over counted reviews, z = 1.96
Honesty Score = clamp( 0.60 × helpfulness
                     + min(25, 10 × log10(1 + verified reviews))
                     + min(15, 3 × Best Answers)
                     − 15 × strikes,  0, 100 )
```

- *Counted reviews* are those with an earnings decision (approved, monetized or Honesty Fund).
- The Honesty Score feeds the vote weight. At Stage 2+, a vote weighs
  `{2: 1.0, 3: 1.5, 4: 2.0, 5: 3.0}[stage] × score / 100`. Stage 1 weighs 0.25. Stage 0, a
  claimed seller or an account on probation weighs 0. The weight is halved under 30 days and
  halved again under investigation.
- Stages 3 / 4 / 5 also need 20 / 60 / 200 distinct eligible people (the evidence gate, §6).
  A concentration hold applies when one cohort casts more than 60% of the votes.

**SOURCE:**
- ADR-003 (Accepted, M0): the score formula.
- ADR-014 (Accepted 2026-08-04): Wilson helpfulness and the stage thresholds.
- ADR-016 (Accepted 2026-09-24): distinct people and the concentration hold.
- ADR-004: Wilson and the 45-day decay of the public ordering.
- Business Rules Full Record 2026-09-23: §8 (Stage 1 may comment), §9 (claimed sellers), §11
  (vote weights), §12 (system signals).

**PERCENTILE BEHAVIOR:** none. It is a fixed formula of the member's own record. No other
member's figures are an input, so the same record always gives the same score, and one member's
score never moves because others improve. It is a "percentage" only in that it runs from 0
to 100.

**COMMENTS DIRECT EFFECT:** NO. Comments are not an input, directly or through votes on them
(`test_trust_meeting_scenario.py`). Reaching Stage 1 is what allows commenting (§8); commenting
does not raise the score.

**OPEN PRODUCT QUESTIONS** (details in §9):
1. Does Zient's calculation document define the same formula? If not, which one stands?
2. Should helpfulness count only eligible votes? Today it counts the visible counters, which
   include up-votes by later-claimed sellers, probation accounts and Stage 0 readers. Changing
   this moves every member's score.
3. Who confirms probation and strikes, on what evidence, and through which tool? Nothing in the
   application sets them today.
4. When is "under investigation" set, beyond an Administrator's explicit, audited action?
5. Should undecided public reviews (published, no earnings decision) count toward Stage 2 and
   above? Today they count for Stage 1 only.
6. The numbers themselves: the 0.60 / 25 / 15 split, the 15-point strike penalty, the
   20 / 60 / 200 evidence thresholds, and the 0.60 concentration share.

**STATUS: OWNER VALIDATION REQUIRED — ZIENT.**

## 1. Five different things, often all called "trust"

| Name | What it is | Range | Where |
|---|---|---|---|
| **Trust Stage** | The member's rung on the ladder: 0 Newcomer, 1 Contributor, 2 Verified Buyer, 3 Established Reviewer, 4 Trusted Reviewer, 5 Community Expert | 0–5 | `users.trust_stage`; names from `users.trust_level_name` (a generated column) |
| **Honesty Score** (the "trust score percentage", `reputation_score`) | A deterministic blend of the member's helpfulness, verified volume, Best Answers and strikes | 0–100 (two decimals stored; the site shows it rounded) | `users.reputation_score`; `trust.reputation_score` |
| **Helpfulness ratio** | How helpful readers found the member's counted reviews: the Wilson lower bound of their up-votes | 0–100 | `users.helpfulness_ratio`; `trust.helpfulness_score` |
| **Vote weight** | What one of the member's votes is worth in the earnings gate on *other people's* reviews | 0–3.0 | snapshotted per vote in `review_votes.vote_weight`; `trust.gate_vote_weight` |
| **Stage evidence** | How many distinct eligible people voted on the member's counted reviews | 0–∞ | computed at recompute, not stored; `trust_service.voter_records` |

A score percentage and a stage are **not** blended into one number anywhere in this product.
No "70% votes + 30% stage" style formula exists, and none is invented here.

## 2. Inputs

| Input | Source | Notes |
|---|---|---|
| **Counted reviews** | the member's reviews that are public (`published_at` set, not removed) **and** have an Administrator's earnings decision: `approved`, `monetized` or `honesty_fund` (`TRUST_COUNTED_STATUSES`) | a 2.5★ review waiting on a Super Admin (`pending_superadmin_routing`) is not counted until it is routed |
| **Verified reviews** | counted reviews with `verification_status = verified` (an ownership photo) | |
| **Any public review** | for Stage 1 only (§8: "posted at least one review"); no decision needed | |
| **Vote counters** | `reviews.helpful_votes` / `unhelpful_votes` on the counted reviews: the **visible** counts, one per person per review | recounted from `review_votes` on every vote write |
| **Distinct voters** | every person with a vote on any counted review, grouped by `voter_id` | one grouped query |
| **Voter standing** | each voter's **current** stage, probation, investigation, claimed-seller and suspension flags | read now: a later claim or probation withdraws past evidence (§9) |
| **Voter age at the vote** | days between the voter's account creation and their **latest** vote on the member | age is taken at the vote, as §11's weight is; a fresh-account farm cannot wait 30 days and then count in full |
| **Best Answers** | `users.best_answer_count` | |
| **Strikes** | `users.strikes` | no application path writes strikes today (§9) |
| **Months active** | `(now − account created) / 30 days` | |
| **Deleted votes** | a vote taken back is deleted; a deleted account's votes cascade away | neither counts |
| **Concentration holds** | `vote_concentration` system reports on the member, and how each was resolved | |

## 3. Computation order

`trust_service.recompute_user_trust(member)`, one database transaction, deterministic:

```
1  counted     = member's public, Administrator-decided reviews
2  helpful,
   unhelpful   = Σ visible up / down counters over the counted reviews
3  helpfulness = 100 × WilsonLB(helpful, helpful + unhelpful), 2 dp        (§4)
4  reputation  = ADR-003 blend(helpfulness, verified, best answers, strikes)  (§4)
5  stage       = score ladder(reviews, verified, helpfulness,
                              best answers, strikes, months active)        (§5)
6  if stage ≥ 3:
     voters    = one record per DISTINCT voter on the counted reviews
     evidence  = Σ voter_evidence_weight(voter)                            (§6)
     stage     = highest stage ≤ stage whose evidence requirement is met
     if stage ≥ 3 and one cohort supplies > 60% of eligible vote rows:
       stage   = concentration hold                                        (§6)
7  write helpfulness_ratio, reputation_score, verified_review_count,
   trust_stage; award the badge for each stage newly reached
```

## 4. Helpfulness and the Honesty Score (the "trust score percentage")

**Helpfulness (ADR-014)**, `trust.helpfulness_score`:

```
helpfulness = 100 × WilsonLB(positive = helpful, total = helpful + unhelpful), rounded to 2 dp
WilsonLB(p, n) = (p̂ + z²/2n − z·√(p̂(1−p̂)/n + z²/4n²)) / (1 + z²/n),   p̂ = p/n,  z = 1.95996
```

A small perfect record is not scored as a large one: 1 up-vote of 1 gives 20.65, not 100.
With no votes, helpfulness is 0.

**Honesty Score (ADR-003)**, `trust.reputation_score`:

```
reputation = clamp( 0.60 × helpfulness                           (up to 60)
                  + min(25, 10 × log10(1 + verified reviews))     (up to 25)
                  + min(15, 3 × Best Answers)                     (up to 15)
                  − 15 × strikes,
                  0, 100 )
```

It is a fixed formula, not a percentile. No other member's figures are an input, so the same
record always scores the same (`test_trust_meeting_scenario.py`).

**Worked example (the meeting's own numbers):** one verified review, no Best Answers, no strikes.

| Votes on it | Helpfulness | Volume | Honesty Score | Shown |
|---|---|---|---|---|
| 3 up, 1 down | 100 × WilsonLB(3, 4) = 30.06 → 0.60 × 30.06 = 18.04 | 10 × log10(2) = 3.01 | 21.05 | **21** |
| 2 up, 2 down | 100 × WilsonLB(2, 4) = 15.00 → 9.00 | 3.01 | 12.01 | **12** |
| 2 up, 1 down | 100 × WilsonLB(2, 3) = 20.77 → 12.46 | 3.01 | 15.47 | **15** |

A comment moves none of these.

**How votes reach the Honesty Score:** only through helpfulness, and helpfulness reads the
**visible** counters, in which every person's vote counts once (ADR-004: "community visibility
votes are equal-weight"). The zero-weight and half-weight rules of §11 apply to the vote weight
(§5) and to stage evidence (§6), not to these counters. See §9, point 4.

## 5. The stage ladder, and what a vote weighs

**Score ladder (FR-7, ADR-014)**, `trust.determine_stage`; the first matching row wins:

| Stage | Name | Requires |
|---|---|---|
| 5 | Community Expert | ≥ 50 verified counted reviews, helpfulness ≥ 90.6, ≥ 6 months active |
| 4 | Trusted Reviewer | ≥ 15 verified, no strikes, ≥ 3 Best Answers, helpfulness ≥ 72.9 |
| 3 | Established Reviewer | ≥ 5 verified, helpfulness ≥ 49.5 |
| 2 | Verified Buyer | ≥ 1 verified counted review |
| 1 | Contributor | ≥ 1 public review of any kind (§8) |
| 0 | Newcomer | otherwise |

Stages 3–5 then also need **stage evidence** (§6): 20 / 60 / 200 distinct eligible people.

**Vote weight (Business Rules §11, ADR-003)**, `trust.gate_vote_weight`. This is what one vote
by this member is worth in the **earnings gate** on someone else's review:

```
if claimed seller or on probation or stage 0:  weight = 0
elif stage 1:                                   weight = 0.25
else:                                           weight = multiplier[stage] × reputation / 100
                                                multiplier = {2: 1.0, 3: 1.5, 4: 2.0, 5: 3.0}
if account younger than 30 days:  weight × 0.5
if under investigation:           weight × 0.5
```

This is where the **trust-score percentage** contributes: a Stage 3 voter with an Honesty Score
of 60 weighs 1.5 × 0.60 = 0.90. The weight is taken when the vote is cast and **snapshotted** on
the vote row (`review_votes.vote_weight`, with the voter's stage), so an earnings decision stays
auditable when trust later moves. Two later events overwrite snapshots:
- a store claim sets every earlier vote by that account to 0 (§9, `seller_service.bar_claimed_seller`);
- a vote cast before migration 0050 carries no weight and is left out of the gate.

**The earnings gate (§2)** sums these weights per review: Wilson lower bound on effective n
≥ 0.65, from ≥ 3 voters at Stage 2+ with non-zero weight (`earn_gate.gate_states`). Separately,
the **public** Wilson that orders "Most helpful" counts every vote equally with a 45-day decay
(ADR-004, `vote_service.recompute_review_vote_aggregates`). The Administrator's All Reviews list
shows both figures side by side.

## 6. Stage evidence and the concentration hold (ADR-016)

**Evidence per distinct voter**, `trust.voter_evidence_weight`, at most one person:

| Voter | Evidence |
|---|---|
| claimed seller, on probation, suspended, or Stage 0 | 0 |
| under 30 days old at their latest vote on the member | × 0.5 |
| under investigation | × 0.5 |
| anyone else, any stage 1–5 | 1 |

There is no stage multiplier: a few high-stage accounts cannot stand in for a crowd. Evidence
is 0 exactly where the vote weight is 0 (`test_trust.py` checks every combination).

```
evidence       = Σ over DISTINCT voters of voter_evidence_weight
required(3/4/5) = 4 × {5, 15, 50} = 20 / 60 / 200
stage          = highest stage ≤ score-ladder stage with evidence ≥ required(stage)
```

The same person voting on all fifty of a member's reviews is still one person of evidence.

**Concentration (no reciprocity needed)**, `trust.vote_concentration`:

```
cohort       = eligible voters present on ≥ max(3, ⌈50% × verified counted reviews⌉) of them
cohort share = cohort's vote rows ÷ all eligible vote rows
hold         = cohort not empty and cohort share > 0.60
```

When a recompute would **promote** a member into Stage 3–5 and the cohort holds:
- the member stays at their current stage (never below Stage 2);
- one SYSTEM_DETECTED `vote_concentration` report is filed on them, with aggregates only (no
  voter identities);
- an Administrator's **dismiss** releases promotion up to the stage that report covered;
- an **escalate** re-files the hold as a fresh report at the next recompute.

A member already at the stage keeps it and is reported. Nothing is demoted, struck, frozen or
banned by the signal.

## 7. Outputs

| Output | Who sees it |
|---|---|
| **Stage name and number** | everyone: profile, review bylines, comments, the admin console |
| **Honesty Score**, `Math.round(reputation_score)` (`lib/trust.ts:trustScore`; 49.49 → 49, 49.50 → 50) | everyone, as the shield badge |
| helpfulness ratio, verified review count | the member's own dashboard; staff |
| vote weight, stage evidence, concentration facts | staff only: gate progress, the report queue. Never public. |
| stage badges | awarded on reaching Stage 2–5; never removed by a later drop |

## 8. When a member is recalculated

Verified in the code (`grep recompute_user_trust`), not assumed:

| Event | Recalculates | Where |
|---|---|---|
| a vote cast, changed or taken back | the review's author, in the same transaction | `vote_service._finish_vote_write` |
| a review submitted | its author | `review_service.create_review` |
| a dated update added to a thread (§4) | nobody, correctly: an update never gets an earnings decision, so it is not a counted review, and the thread's first review already met Stage 1 | `review_service.add_thread_update` |
| a review deleted by its author | its author | `review_service.delete_entry` |
| an earnings decision: approve / link / Honesty Fund | its author | `referral_service` |
| earnings rejected | its author ("a rejected review stops counting") | `referral_service.reject` |
| taken down / restored by an Administrator | its author | `referral_service.unpublish` / `restore` |
| **a store claim approved** | **every member the seller had voted on** (their votes are now 0 evidence) | `seller_service.bar_claimed_seller` → `trust_service.recompute_authors_voted_on_by` |
| **an investigation set or cleared** | **every member the account had voted on** (their evidence halves, or is restored) | `PUT /admin/users/{id}/investigation` → same helper |
| **a concentration hold dismissed** | **the held member, at once** | `report_service.resolve_report` |
| nightly | every member active in the last 90 days (profile, review or vote) | `recompute_recently_active_users`, via the internal cron |
| nightly | every review's counters and public Wilson re-decayed, including a review whose votes all vanished | `vote_service.recompute_all_wilson_scores` |

**Changed on 2026-09-29 (bold rows).** Before, a store claim, an investigation and a hold
dismissal recalculated nobody. The members concerned kept a stage the evidence no longer
supported, or stayed held after release, until their own next vote. The nightly sweep does not
help there: it skips anyone inactive for 90 days. Each gap has a test that fails without its fix.

**Concurrency.** A vote write now locks its review's row before recounting. Twelve people
voting at the same moment used to leave 12 vote rows and a counter of 11: each writer recounted
without seeing the others' uncommitted votes. One person voting twice at once is one vote
(`uq_review_vote_once`; the loser gets a 409).

**Not a trigger, by design:**
- reading a profile or the queue;
- a comment (not an input);
- a report on a review (reports feed priority, §18, never trust).

## 9. What is not defined: PRODUCT DEFINITION REQUIRED

1. **Zient's calculation document** is owed. The formula in §4 is ADR-003's, accepted at M0; if
   Zient's document defines something else, the owner decides.
2. **Probation has no trigger.** §11 says confirmed probation zeroes a vote, and the math does.
   But nothing in the application sets `is_on_probation`: no route, no service, no rule for what
   "confirmed" means. It is set only directly in the database today. Strikes are the same.
   Building a probation tool means deciding who confirms it and on what evidence; that is not an
   engineering call. `recompute_authors_voted_on_by` is ready for it.
3. **"Under investigation"** is set by an Administrator's explicit, audited action only, until
   the rule is written (Business Rules implementation record, §11).
4. **Helpfulness counts visible votes.** A claimed seller's earlier up-votes, a probation
   account's and a Stage 0 reader's all stay in the visible counters (§9: "the visible counts
   stay: they record what happened"), so they still move helpfulness and the Honesty Score.
   They carry no weight in the gate and no stage evidence. Whether helpfulness should count only
   eligible votes is an owner decision; changing it would move every member's score.
5. **Undecided public reviews** (published, no earnings decision yet) count for Stage 1 only.
   Whether they should count toward Stage 2+ is a pending business rule (`trust_service.py`).

## 10. Tests that pin this document

| Test file | What it pins |
|---|---|
| `tests/test_trust.py` | the pure ladder, helpfulness, evidence weights (0 exactly where the gate weight is 0), concentration, gate weights |
| `tests/test_trust_ring_exploit.py` | a fixed ring cannot manufacture Stage 3 or 5; 20 distinct people still reach Stage 3; every ineligible voter kind; halvings |
| `tests/test_trust_integrity_holds.py` | hold on promotion, no reciprocity needed, filed once, dismissal releases, escalation re-queues, probation on the ring ends the hold |
| `tests/test_trust_meeting_scenario.py` | the meeting's 21 / 12 / 15, fixed formula, comments are not an input |
| `tests/test_trust_computation_qa.py` (new) | exact boundaries at 20 / 60 / 200 people and one short; half-weight voters; the claim, investigation, dismissal and vote-removal triggers; no self-set trust; concurrent votes; determinism; ADR-003 caps; §11 weights |
| `tests/test_all_reviews_and_queue_wilson.py` (new) | public vs gate Wilson on the same review; counters re-counted after votes vanish |
| `tests/frontend/trust-score-display.test.mjs` (new) | the shown Honesty Score is the stored one rounded half up; nothing shown without a score |
| `e2e/review-queue-wilson-journeys.spec.ts` T (new, browser) | on a real stack, the Honesty Score on a review page is the API's `reputation_score` rounded, before and after an earnings approval recalculates it. A signed-out page may show the previous score for up to 60 seconds (the public page cache) |

Independent QA retest is required for every row above. None of this is "QA passed".

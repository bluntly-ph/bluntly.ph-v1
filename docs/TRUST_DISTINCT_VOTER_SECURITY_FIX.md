# Security fix: trust-stage evidence counted vote rows, not voters

| | |
|---|---|
| Report | "trust-stage evidence check counts vote volume, not voter identity", Bluntly Research, 2026-09-24 |
| Severity | Critical for business integrity and future Honesty Fund money. Not RCE, not a data breach, not an availability issue. |
| Status | **Confirmed, fixed, regression-tested** on `fix/cloud-round2-security-design` |
| Decision record | `docs/adr/016-distinct-voter-evidence.md` (amends ADR-014) |
| Production exposure | None found (`docs/TRUST_STAGE_PRODUCTION_AUDIT.md`) |

## 1. Confirmed root cause

`backend/app/services/trust_service.py`, as of `0b93add`:

```python
helpful, unhelpful = db.execute(
    select(func.coalesce(func.sum(Review.helpful_votes), 0),
           func.coalesce(func.sum(Review.unhelpful_votes), 0))
    .where(Review.author_id == user_id, published)).one()
total_votes = helpful + unhelpful
...
new_stage = evidence_capped_stage(determine_stage(...), total_votes=total_votes)
```

`backend/app/services/trust.py`:

```python
MIN_VOTES_PER_VERIFIED_REVIEW = 4
STAGE_MIN_VERIFIED_REVIEWS = {3: 5, 4: 15, 5: 50}     # -> 20 / 60 / 200
def evidence_capped_stage(stage, total_votes): ...    # compares a ROW count
```

`review_votes` has `UniqueConstraint("review_id", "voter_id", name="uq_review_vote_once")`.
That makes a vote unique per review and voter, not per voter, so the same accounts
can vote once on every review a member writes. Every part of the report checked
out against the code:

- `evidence_capped_stage` compared a row total and never saw a voter id.
- 4 accounts × 5 reviews = 20 rows gave Stage 3; 4 × 50 = 200 rows gave Stage 5.
- `gate_vote_weight` reads `trust_stage`, so a manufactured stage gained real
  earnings-gate weight (up to 3.0×) on every other review it voted on.
- Honesty Fund scoring (`honesty_fund_service._review_scores`) sums the same
  gate weights. It also called `gate_vote_weight` with only four arguments,
  dropping `is_under_investigation` and `is_claimed_seller`. A claimed seller's
  earlier up-votes therefore still carried weight in fund scoring, and an
  investigated voter's were not halved. This was a separate defect, found and
  fixed here.
- The comment gate, badges and the Stage 2+ features all read `trust_stage`.

ADR-014 had already conceded that "an attacker with enough distinct qualified
voters still climbs". The gate was designed as if rows meant people, and nothing
enforced that.

### Existing collusion signal, verified and why it was not the fix

`ranking.RECIPROCITY_THRESHOLD = 0.60` and `COLLUSION_MIN_VOTERS = 5` are real.
`fraud_service.compute_signals_by_review` flags a review when at least 5
distinct up-voters exist and more than 60% of them were up-voted back by the
author. It:

1. is advisory: it adds priority and files a report, and blocks nothing;
2. requires reciprocity, which one-way sockpuppets never show;
3. is evaluated per review, while the exploit accumulates across a member's
   whole history.

It stays in place as one advisory layer. The trust calculation itself was fixed.

## 2. Exploit regression, reproduced before the fix

`backend/tests/test_trust_ring_exploit.py` drives the real `recompute_user_trust`
against Postgres 17, with every uniqueness constraint satisfied. Each ring
account votes at most once per review. The run against the unfixed code
(`0b93add`, local Postgres 17.11):

```
test_a_four_account_ring_cannot_manufacture_stage_3          assert 3 == 2   FAILED
test_the_same_ring_cannot_reach_stage_5_by_reusing_itself    assert 5 == 2   FAILED
test_an_already_inflated_stage_falls_back_on_recompute       assert 5 == 2   FAILED
test_zero_weight_voters_are_not_evidence[claimed seller]     assert 3 == 2   FAILED
test_zero_weight_voters_are_not_evidence[probation]          assert 3 == 2   FAILED
test_zero_weight_voters_are_not_evidence[suspended]          assert 3 == 2   FAILED
test_zero_weight_voters_are_not_evidence[stage 0]            assert 3 == 2   FAILED
test_a_claimed_sellers_earlier_votes_stop_counting           assert 3 == 2   FAILED
test_accounts_under_30_days_at_vote_time_count_half          assert 3 == 2   FAILED
test_under_investigation_voters_count_half                   assert 3 == 2   FAILED
test_twenty_distinct_voters_still_reach_stage_3              PASSED (honest path)
test_repeat_readers_count_once_each_but_do_not_block_progress PASSED (honest path)
```

After the fix, all 12 pass.

## 3. The fix

### 3.1 Distinct-voter rule

No approved distinct-voter threshold existed. Neither the Business Rules (Full
Record, 2026-09-23) nor the ADRs contain one; §14 explicitly defers the Honesty
Fund's anti-collusion safeguards. So the fix keeps the existing numeric evidence
model and changes only its unit:

> **Stage 3 / 4 / 5 require 20 / 60 / 200 of voter evidence, counted in DISTINCT
> ELIGIBLE PEOPLE who voted on the member's counted reviews.** A person
> contributes at most 1, however many of the member's reviews they voted on.

This is the report's recommended interpretation. It deliberately does not add a
flat constant such as "5 distinct voters for every stage", which would leave
Stages 4 and 5 open to the same fixed ring. Ring size must now grow with the
stage the ring wants: a 4-account ring stays at Stage 2 at every target.

`evidence_capped_stage(stage, voter_evidence)` takes the sum. Its parameter was
renamed from `total_votes` so that a caller still passing a row count fails with
a `TypeError` rather than silently reopening the hole. There is a test for that.

### 3.2 Eligible voters: model A, weighted distinct evidence

`trust.voter_evidence_weight` returns 0, 0.25, 0.5 or 1 per distinct voter:

| Voter state | Evidence | Source |
|---|---|---|
| Claimed seller | 0 | §9, §11: zero, permanently, "regardless of any voting history" |
| Confirmed probation | 0 | §11 |
| Stage 0 (never posted a review) | 0 | `gate_vote_weight` is 0 at Stage 0 |
| Suspended | 0 | not a participating account |
| Deleted | n/a | `review_votes.voter_id` is `ON DELETE CASCADE`, so the votes disappear |
| Under 30 days old **at the vote** | × 0.5 | §11; age is taken at the voter's latest vote, as §11's weight is |
| Under investigation | × 0.5 | §11 |
| Anyone else, any stage 1–5 | 1 | one person; no stage multiplier |

This is the simplest model that preserves the policy:

- **Zero exactly where §11 gives zero.** A test enumerates every combination of
  stage, age, probation, investigation and claim, and asserts that evidence is 0
  exactly when `gate_vote_weight` is 0. The two readings of §11 cannot drift apart.
- **No stage multiplier.** Using the gate weight itself (up to 3.0 at Stage 5)
  would let a few high-stage accounts stand in for a crowd, which is the same
  attack in a different form.
- **Standing is read now; age at the vote.** A later claim, probation or
  suspension withdraws past evidence. That is §9's wording, and it is how a
  moderator neutralises a confirmed ring (see 3.3). Age is taken when the vote
  was cast, so a fresh-account farm cannot wait 30 days and be counted in full.

### 3.3 Cumulative concentration: hold, never punish

`trust.vote_concentration` runs over a member's whole history and requires no
reciprocity:

- **Cohort**: eligible voters present on ≥ 50% of the member's counted reviews
  and on ≥ 3 of them.
- **Cohort share**: the cohort's vote rows ÷ all eligible vote rows.
- **Hold** when the cohort share is > 0.60, the same threshold as the existing
  ADR-004 collusion signal.

When a recompute would promote a member into Stages 3–5 with a holding cohort:

- the member stays at their current stage (never below Stage 2, which is based
  on posting);
- a SYSTEM_DETECTED `vote_concentration` report is filed against the member in
  the existing admin queue (§12: labelled by origin). It carries aggregates only
  (`candidate_stage`, `held_at_stage`, voter and row counts, cohort size and
  share) and no voter identities. A moderator who needs the cohort can see it on
  the member's public profile, which by §17 already shows who votes on them most;
- a moderator's **dismiss** releases promotion up to the stage that report
  covered;
- for a member target the queue offers only **escalate** besides dismiss.
  Escalation has no later decision step, so the hold re-enters the queue as a
  fresh report instead of stranding the member. The super admin reads the same
  queue;
- a member already at the stage keeps it and is reported for review. Nothing is
  demoted, struck, frozen or banned by the signal;
- to act on a confirmed ring, a moderator uses the existing probation tool on
  the ring accounts. Their evidence goes to 0, and the member's candidate stage
  falls with it. There is a test for this.

The nightly `recompute_recently_active_users` sweep re-evaluates every active
member, so detection is periodic and retrospective, not only on vote writes.

### 3.4 Honesty Fund eligibility (distribution still disabled)

The payout formula remains an open owner decision (§14), and
`honesty_fund_distribution_enabled` stays `False`. These changes only decide what
may take part in a cycle:

1. **§11 in full**: the vote weight now passes `is_under_investigation` and
   `is_claimed_seller`, and a suspended voter weighs 0.
2. **Minimum evidence floor**: a review scores 0 unless its up-voters add up to
   `FUND_MIN_REVIEW_EVIDENCE = MIN_VOTES_PER_VERIFIED_REVIEW = 4` people of
   distinct voter evidence. That is ADR-014's per-review evidence, reused rather
   than invented.
3. **Concentration hold**: `eligible_reviews` passes over any author whose
   concentration report is pending or escalated and not dismissed.
4. **§9**: a claimed seller's review is never scored.

**Payout holding period: proposed, not built.** The formula and the payout
mechanism are both undecided, so no holding logic is coded. Recommendation for
when they are decided: compute a cycle's fund scores at cycle close, publish them
to the admin console, and credit wallets only after a fixed review window (for
example 14 days). Any concentration report filed during the window removes that
author from the cycle. This composes with §15 (only reconciled money is paid)
and §13 (the super admin performs every transfer).

## 4. Product impact (honest progression)

This is a real change to the progression curve, and it is stated explicitly
rather than hidden:

- Stage 3 now needs 20 different eligible people, not 20 votes. A reviewer with a
  small loyal readership who vote on everything will climb more slowly.
- Pure readers (Stage 0) are not evidence, because §11 gives their votes no
  weight. In production today 7 of 10 votes come from Stage 0 readers.
- A strongly concentrated but genuine following (for example friends, family or
  a class) will trigger a hold and need one moderator dismissal per stage.

None of this is a reason to leave the exploit open. If the owner wants a gentler
curve, the levers are `MIN_VOTES_PER_VERIFIED_REVIEW`, the per-stage
requirement, `COHORT_COVERAGE` and `CONCENTRATION_HOLD_SHARE`, all in
`backend/app/services/trust.py`. Changing them must never turn evidence back
into a row count.

## 5. Tests

| File | What it pins |
|---|---|
| `tests/test_trust.py` | pure gate in people; renamed keyword refused; evidence is 0 exactly where gate weight is 0; halvings; the ring is its own size at every stage; concentration flags a cohort, ignores ineligible padding, leaves broad support alone |
| `tests/test_trust_ring_exploit.py` | the report's attack end to end (above) plus honest progression and every ineligible voter kind |
| `tests/test_trust_integrity_holds.py` | hold on promotion; no reciprocity needed; filed once; dismissal releases; escalation re-queues; existing stage kept and reported; broad support never held; probation on the ring ends the hold; a moderator finds and dismisses it through the real `/admin/reports` API, where a remove decision is refused (422) |
| `tests/test_honesty_fund_integrity.py` | evidence floor; claimed seller up-vote weighs 0; investigated half and suspended 0; claimed-seller author never scored; held author passed over; end-to-end `distribute` pays the free author and not the held one |
| `tests/test_retention_and_fund.py` | existing distribution tests updated to four voters per review; 2:1 proportionality unchanged |

## 6. Deployment order

The fix needs no migration: it adds no schema and reuses `moderation_logs` for
holds. It deploys with the candidate after 0052 and 0053 (see
`docs/CLOUD_CONTINUATION_REPORT.md`). Nobody in production is at Stage 3+, so
the first recompute changes no one's stage.

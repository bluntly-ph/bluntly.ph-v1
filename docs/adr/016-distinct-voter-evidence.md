# ADR-016: Stage evidence counts distinct eligible voters

- **Status:** **Accepted / implemented** (2026-09-24). Amends ADR-014's
  minimum-evidence gate. Security fix; full write-up in
  `docs/TRUST_DISTINCT_VOTER_SECURITY_FIX.md`.
- **Context:** ADR-014 required 20 / 60 / 200 community votes for Stages 3 / 4 / 5
  and passed `helpful + unhelpful` — the denormalized counters summed over every
  counted review — to `evidence_capped_stage`. `uq_review_vote_once` makes a vote
  unique per *(review, voter)*, not per voter, so four accounts voting once on each
  of five reviews produced 20 rows (Stage 3) and the same four across fifty reviews
  produced 200 (Stage 5). ADR-014 itself notes "an attacker with enough distinct
  qualified voters still climbs": the gate was designed as if rows meant people.
  Reproduced by `tests/test_trust_ring_exploit.py` against the pre-fix code
  (Stage 3 and Stage 5 reached by a 4-account ring).

## Decision
1. **Unit of evidence is a person.** `evidence_capped_stage(stage, voter_evidence)`
   takes the sum of `voter_evidence_weight` over the DISTINCT voters on the member's
   counted reviews (`trust_service.voter_records`, one grouped query). The numeric
   thresholds are unchanged — 20 / 60 / 200 — so ring size now has to grow with the
   stage it wants. The parameter was renamed from `total_votes` so no caller can
   keep passing a row count silently.
2. **Eligibility follows Business Rules §11, capped at one person.**
   `voter_evidence_weight` is 0 wherever `gate_vote_weight` is 0 (claimed seller,
   confirmed probation, Stage 0) and for a suspended account; halved under 30 days
   old (age at the voter's latest vote, as §11's own weight is taken); halved under
   investigation. No stage multiplier: a Stage 5 voter is one person, like a Stage 1.
   Standing is read now, so a later claim/probation/suspension withdraws evidence
   (§9: "regardless of any voting history"). A deleted account's votes are removed
   by `ON DELETE CASCADE`.
3. **Repeated-cohort concentration holds promotion.** `trust.vote_concentration`
   measures how much of the member's eligible vote rows come from voters present on
   at least half of their counted reviews (and at least three). Above 0.60 — the
   ADR-004 collusion threshold, reused — a promotion into Stages 3–5 is held at the
   current stage (never below Stage 2) and a SYSTEM_DETECTED `vote_concentration`
   report is filed against the member in the existing admin queue. A moderator's
   **dismiss** releases the promotion up to the stage it covered. The queue's
   only other answer for a member, **escalate**, has no later decision step, so
   the hold re-enters the queue as a fresh report rather than stranding the
   member. No reciprocity is required. Nothing is demoted, struck, frozen or
   banned by the signal; a confirmed ring is handled by putting the ring accounts
   on probation, which zeroes their evidence.
4. **Honesty Fund eligibility** (distribution still disabled; formula still open,
   §14) inherits the same evidence: vote weight honours claimed-seller, investigation
   and suspension; a fund-routed review needs `MIN_VOTES_PER_VERIFIED_REVIEW` (4)
   of distinct voter evidence among its up-voters; an author under an active
   concentration hold is excluded from the cycle.

## Consequences
- The 4-account ring stays at Stage 2 at every stage target; its rows are no
  longer evidence.
- Honest progression is harder: Stage 3 now needs 20 different eligible people, not
  20 votes. Pure readers (Stage 0) are not evidence, because their votes carry no
  weight anywhere under §11. This is a real change to the product's progression
  curve and is flagged for owner tuning; the exploit is not left open meanwhile.
- Production on 2026-09-24 (read-only): no member is at Stage 3+, so deploying this
  changes nobody's current stage (`docs/TRUST_STAGE_PRODUCTION_AUDIT.md`).
- `recompute_user_trust` reads per-voter rows only when the score ladder reaches
  Stage 3, so the vote-write path is unchanged for everyone below it.

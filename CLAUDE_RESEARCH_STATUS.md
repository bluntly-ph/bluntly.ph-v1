# CLAUDE RESEARCH STATUS (backend / data / QA worker)

PIM owns Figma and visual work; read CLAUDE_PIM_STATUS.md. Coordination file for
review media: docs/REVIEW_MEDIA_CONTRACT.md.

## Checkpoint R1 — review media (2026-10-05)
- START SHA: dfd41b5 (origin/defense-build-oct6 = same; no PIM commits yet, no CLAUDE_PIM_STATUS.md)
- TASK: several photos per product review; NO PHOTO = NO DEFAULT PHOTO
- AUDIT: reviews had ONE `photo_url`; store reviews and answers already used an ordered
  `photo_urls text[]` (≤4) - reused that shape, no media table. No backend path wrote the
  product image into a review photo; frontend `lib/review-media.ts` already refuses to borrow it.
- MIGRATION: 0094_review_photos (additive: reviews.photo_urls text[] NOT NULL DEFAULT '{}',
  CHECK cardinality ≤ 4, backfill {photo_url}). Up/down/up clean locally; 1,449 local rows backfilled, 0 mismatches.
- API: ReviewEntryIn/ReviewUpdate/ReviewOut gain `photo_urls`; `photo_url` = first photo
  (kept in step by models/review._sync_photos). Ownership per photo (403 photo_not_owned).
  Swap (§4) replaces the whole ordered set. Contract: docs/REVIEW_MEDIA_CONTRACT.md.
- FILES: backend/alembic/versions/0094_review_photos.py, app/models/review.py, app/schemas/review.py,
  app/services/review_service.py, app/api/v1/routes/reviews.py, tests/test_review_photos.py (8),
  tests/test_scheduler_migrations.py (head 0094), lib/review-media.ts (+reviewPhotos), tests/frontend/review-media.test.mjs,
  docs/openapi.json, lib/api-types.d.ts, docs/REVIEW_MEDIA_CONTRACT.md
- TESTS: test_review_photos 8 passed; every photo-touching suite 858 passed; no-DB full suite 2255 passed;
  frontend 586 passed; tsc clean.
- SUPABASE (read-only): production at 0085_email_outbox; 156/204 reviews have a photo, all the author's own
  in review-photos, 0 equal a product image. Nothing written.
- PIM DEPENDENCY: composer should send `photo_urls` (ordered, ≤4; [] for Skip); review page/cards read
  `review.photo_urls` (helper `reviewPhotos`). Single `photo_url` still works.
- BLOCKER: none. Orphan sweep for removed-before-submit uploads not built (documented gap).
- NEXT TASK: transaction QA seed (non-production), then Price History data/API.

## Checkpoint R2 — transaction QA seed + Price History (2026-10-05)
- START SHA: cd581be (origin same; no PIM commits)
- SEED (existing framework, not a new one): scripts/defense (guarded: TEST project or local only,
  refuses production). It already writes money through the real API (clicks → Shopee/Lazada report
  imports → commissions → remittances → cashouts/payouts). Gap found: this week held only a ₱0
  cancelled order and the 30–59-day window that "30d vs previous" compares against was EMPTY.
  Added 9 orders (dataset.ORDERS → 29): this week, last week, 30–59 days; none before its review;
  persona stories unchanged. REPORT_WINDOWS + money_in() give the deterministic expected totals.
- VERIFY: scripts.defense.verify now proves Overview 1M verified (₱4,871) and previous (₱2,914) equal the
  dataset, and commissions == completed orders (24) — a duplicate import would fail it. 112/112 READY.
- IDEMPOTENT: a second `seed` run refuses ("already present", exit 3); `--reset` rebuilds.
- REPORTS (fresh local defense DB): 1M ₱4,871 vs ₱2,914 (+67%); 6M/1Y ₱14,585 (May–Oct buckets; Nov–Apr
  zero — the community is 8 months old, nothing invented before it); payouts: 1 paid ₱369.60, 1 scheduled ₱690.
- TESTS: test_defense_scripts (+2: windows covered, totals fixed); walkthrough 7/7 on the reseeded DB.
- PRICE HISTORY: existing GET /products/{id}/prices is sufficient — docs/PRICE_HISTORY_CONTRACT.md.
  Production: 2 approved / 176 pending observations → real data needs moderators to work the Prices queue.
- PIM DEPENDENCY: Price History visual reads `series` per marketplace; must render no-data/one-point.
- NEXT TASK: non-Figma QA items from BLUNTLY_QA.xlsm.

## Checkpoint R3 — resume after interruption + payout below-minimum count (2026-10-05)
- START: local HEAD 71b32da (R2 seed commit, rebased onto PIM 040ab1c, NOT pushed); tree clean.
  origin/defense-build-oct6 = f528c1e (11 PIM commits). No file overlap; rebased → 64d8fa9, pushed.
- SURVIVED: everything. test_review_photos.py + docs/REVIEW_MEDIA_CONTRACT.md were already in cd581be;
  the seed + Price History work was the unpushed 71b32da (now 64d8fa9).
- REVIEW MEDIA vs PIM (f528c1e): matches — composer sends ordered photo_urls (≤4, MAX_REVIEW_PHOTOS)
  + photo_url = first; Skip sends []; the one swap PATCHes the whole ordered set; zero photos render no
  media area; no product-image fallback. test_review_photos 8 passed.
- SEED: fresh defense DB → verify 113/113 READY; Overview 1M ₱4,871 / previous ₱2,914 / commissions = 24
  completed orders; a second seed run refuses (no duplicates). (A verify run AFTER the walkthrough shows 7
  queue/claim "failures" — the walkthrough consumes those states; verify is for a fresh seed.)
- PAYOUT (PIM dependency closed): GET /admin/payouts/summary now returns
  `below_minimum_count` (members, claimed sellers aside, with 0 < withdrawable < settings.payout_min_php
  — same withdrawable_from rule and same minimum request_cashout refuses below; exactly the minimum is NOT
  below) and `payout_minimum` ("300.00"). PayoutCycleCard already reads the field — no frontend change.
  Seeded dataset: 3 (Ivan ₱252, Kristine ₱186, Rina ₱174). verify proves service == its own SQL.
- TESTS: test_payout_summary (+2: below / exactly-at / above / zero / claimed seller / partly and fully
  uncleared; route carries count + minimum); payout-related suites 137 passed; no-DB 2257 passed;
  frontend 606 passed; tsc clean. OpenAPI + lib/api-types.d.ts regenerated (+2 fields only).
- SUPABASE: not re-queried this checkpoint (production last read: alembic 0085; 0086–0094 pending;
  no production writes).
- NEXT TASK: non-Figma QA items.

## STRUCTURED Q&A — release blocker, RESEARCH owns (2026-10-05)
- OPTIONS (the four existing Ask chips, Figma Screen/Ask/Step 2 7573:10506; no new taxonomy):
  Experience · Pros & Cons · Do you recommend this? · Is this right for me?
  Rating is NOT a chip: every answer to a product question carries one. Answer flow keeps all 7 steps
  and "Step N out of 7" (words, experience, pros_cons, verdict, fit, rating, photo).
- STORAGE (unchanged): the request is the question's last line "Looking for: X, Y"
  (answer_parts.requirements_of / splitQuestionBody); answer parts in the answer's labelled block,
  parsed into AnswerOut.parts. MIGRATION: NONE.
- VALIDATION (server, POST /questions/{id}/answers; qa_service._require_structure). This applies to a
  member's answer to a PRODUCT question:
  - no rating → 422 answer_rating_required {parts:["rating"]} (0.5–5, half steps; 0 refused)
  - a requested part empty → 422 answer_part_required {parts:[…] in step order}.
    Experience→experience, Pros & Cons→good AND bad, recommend→verdict, right for me→right_for_you.
  - unrequested parts stay optional and are kept when sent. Words: the server requires "has words";
    the flow requires 30 characters.
  - Exempt: a store's own answer (a store does not rate its own product) and questions about a store.
  - Legacy: a free-form question → only the rating is required. A "…, Rating" line still parses.
    Unknown items → no demands.
- FRONTEND:
  - the counter says "· Required" / "· Required: they asked about this" / "· Optional".
  - a server 422 jumps the flow to the step it names.
  - a product question has no one-line answer box (only the flow; store questions keep the box).
  - "Looking for:" chips on the question page, Questions list, search best match and similar/related
    rows (LookingFor; Rating never shown; legacy shows none). FOR PIM: the list cards' chip row is not
    in Figma — verify.
  - Not touched: answer media (single photo, per PIM), review media, Best Answer, votes, replies,
    notifications, seller answers.
- TESTS:
  - backend test_structured_answers (9) + 11 older Q&A fixtures now send a rating; Q&A suites 132
    passed; no-DB 2260.
  - frontend structured-question-model (13); frontend 619 passed; tsc / eslint / next build clean.
  - e2e owner-patch 12 drives the 7 steps (the rating gate holds Continue) and reads the answer back.
  - full CI journey list on a fresh fixture stack: 109 passed / 0 failed. Four stale journeys were
    fixed (move-to-support MQA-021, DTI label f62b445, integrity rows MQA-003, mark-paid race).
- COMMITS: 4284300 (backend), a79b502 (ask/answer flow), 7994f67 + ec8f490 (journeys), f46edbf (chips).
- AMBIGUITY (left to owner/PIM, not built):
  - Answer Step 2b "Where's this from?"; a photo on the question; whether "It depends" needs an
    explanation; answer photos >1.
  - Defense seed answers carry ratings (ANSWER_RATINGS), fresh seed 113/113.
- RELEASE: code ready on defense-build-oct6. Production DB untouched. Production is at alembic 0085;
  0086–0094 are pending and need Supabase re-authorisation plus owner approval. 0089/0092 run outside a
  transaction. Structured Q&A itself needs no migration.

## BACKEND-ONLY MODE (2026-10-05) — handoff to PIM
Frontend and Figma work belongs to PIM from now on. RESEARCH's Figma search commit `7665a3c`
(Reviews/Questions tabs; 109 browser journeys passed against it) is parked on
`claude/vibrant-newton-msudxr` and was NOT pushed to defense-build-oct6. PIM may cherry-pick it or ignore it.

### A. Structured Q&A — API contract (pushed 4284300; no migration)
- POST /api/v1/questions/{id}/answers, for a member's answer to a PRODUCT question:
  - `rating` is required: a string "0.5".."5" in half steps.
    - Missing → 422 `{code:"answer_rating_required", parts:["rating"]}`.
    - Invalid (0, 4.3, 6, -1) → 422.
  - Every requested specific is required. Missing ones → 422
    `{code:"answer_part_required", parts:[…]}`, listed in step order. The part names are:

    | Requested on the question | Part name in `parts` | Answer field(s) |
    |---|---|---|
    | Experience | experience | experience |
    | Pros & Cons | pros_cons | good AND bad |
    | Do you recommend this? | verdict | verdict |
    | Is this right for me? | fit | right_for_you |

  - Unrequested fields are optional and kept. Words (`body`) are always required.
  - Exempt: a store's own answer, and questions about a store.
- The request is read from the question's last line, "Looking for: X, Y". `QuestionOut.requirements` is that list.
  - A legacy "…, Rating" item is parsed but demands nothing extra.
  - Unknown items → no demands.
  - A free-form question requires only the rating.
- AnswerOut.parts: text, experience, good, bad, recommend, verdict, verdict_reason, right_for_you,
  rating, photo_urls.
- VERDICT "Why? (optional)" (Answer Step 4.1). API field: **`verdict_reason`**.
  - POST /answers takes `verdict_reason: string | null` (≤ 1000, no links). It is ALWAYS optional:
    omitting it is valid, and it is never in `parts` of a 422.
  - Stored as a "Verdict reason: …" line in the answer's labelled block. NO migration.
  - Returned as `parts.verdict_reason` (null when absent, including on every legacy answer).
  - lib/api-types.d.ts regenerated.

### B. Admin Honesty Score override — API contract (migration 0095_trust_score_override)
- Model:
  - `effective = override if set else computed`.
  - `users.reputation_score` IS the effective score, so every reader follows it: vote weight,
    review lenses, Honesty Fund, profiles, cards.
  - The algorithm keeps writing `computed_reputation_score`.
- Scale: 0..100, two decimals (ADR-003). DB CHECK on the override.
- PUT /api/v1/admin/people/{person_id}/trust-score — administrator or super admin.
  - Body `{score: number|null, reason: string(3..1000)}`. A number sets or changes the override; null clears it.
  - 200 response:

    ```
    {user_id, computed_score, score_override|null, effective_score, is_score_overridden,
     score_override_reason|null, score_overridden_at|null, score_overridden_by|null}
    ```

    Decimals are strings with 2 places ("80.00").
  - Errors:
    - 403 for a member
    - 404 `person_not_found`
    - 422 `score_out_of_range`
    - 422 `reason_required`
    - 422 `self_decision` (your own score)
  - The same value again is a no-op, with no audit row.
- Audit: each set, change or clear writes one moderation_logs row:
  - `action="override"`, target = the member, `notes="Honesty Score override <set|change|clear>: <reason>"`.
  - `context = {kind:"trust_score_override", change, computed, override_before, override_after,
    effective_before, effective_after}`. It appears in the Activity log.
- The members that person voted for are re-evaluated immediately, because vote weight reads the score.
- TRUST STAGE is not derived from the score. trust.determine_stage uses review counts, verified reviews,
  helpfulness, best answers, strikes, tenure and voter evidence. The level names come from the stage:
  0 Newcomer, 1 Contributor, 2 Verified Buyer, 3 Established Reviewer, 4 Trusted Reviewer,
  5 Community Expert. So an override moves the Honesty Score and never the stage name. No contradiction:
  the two were already independent numbers.
- Admin People API fields. Both payloads below also keep `reputation_score`, which is the effective score:
  - GET /api/v1/admin/people/{id} → `person.computed_score`, `person.score_override`,
    `person.is_score_overridden`, `person.score_override_reason`, `person.score_overridden_at`,
    `person.avatar_url`.
  - GET /api/v1/admin/reviewers (People list) rows → `computed_score`, `score_override`,
    `is_score_overridden`, `avatar_url`.
- Profile photo: `avatar_url` is users.avatar_url, the member's own uploaded photo, with no second copy.
  It is null when there's none, and PIM draws initials.
- lib/api-types.d.ts was regenerated.
- TESTS: test_trust_override (5) covers:
  - set, change and clear, with audit rows and the no-op
  - range, reason, self, 404 and roles
  - recompute under an override
  - the stage unaffected
  - People API fields and the photo, present and absent

  Also: related DB suites 716 passed; no-DB 2265; migration up → down → up OK.
- MIGRATION REQUIRED: YES, 0095 (additive). Production is at 0085, so 0086–0095 are pending.

# QA reconciliation, 2026-09-29

## QA WORKBOOK WRITEBACK BLOCKED

- **Workbook:** `BLUNTLY_QA.xlsm`, Drive id `1rCyzx6TxfIa_EPGrkBYo0kWyjbScSr2Y`
  (the link given as `…/spreadsheets/d/1rCyzx6TxfIa_EPGrkBYo0kWyjbScSr2Y/edit?gid=1916511535`).
- **Read attempted live on 2026-09-29.** The Google Drive connector is signed in as
  `bluntly.ph@gmail.com`:
  - `get_file_metadata` and `download_file_content` both returned **"Requested entity was not
    found."**;
  - a title search for `BLUNTLY_QA` / "QA Issues" found nothing;
  - the tester's shared folder "Bluntly bugs" lists as empty.

  The file is not shared with the connected account, or is shared with a different one. The
  2026-09-26 and 2026-09-28 reads were made through a connection that could see it.
- **Google Sheets connector:** failed to connect ("Connection closed").
- **Write:** not possible even with access. The Drive connector only creates files or renames
  and moves them. It cannot write a cell in an `.xlsm`, and replacing the whole file would
  overwrite the tester's own cells, which is not allowed.
- **Owner action:** share the workbook with `bluntly.ph@gmail.com` (Viewer is enough to read),
  or reconnect Google Sheets. An engineering-owned column can then be filled from the table
  below.

Nothing in the workbook was read today or changed. **Tester-owned cells modified: 0.**

## What would have been written

The workbook's *QA Issues(Main)* sheet has the tester's own columns and an engineering column
(*Engineering QA → QA Comment*, per the round-3 record). The table below is everything
engineering would put in its own column, one line per QA ID.

Map each column to the workbook like this:
- **Latest tester result read** is quoted, not changed. It is the tester's status as read on
  2026-09-26 (round 3) and 2026-09-28 (round 4): items the tester marked Resolved, and the
  Fail / Partially Fixed / Open items listed in
  [INDEPENDENT_QA_ROUND4_REMEDIATION.md](INDEPENDENT_QA_ROUND4_REMEDIATION.md).
- **Engineering status** uses the owner's vocabulary. No row says "QA passed": only the tester
  can.

Every other field of every row is the tester's.

**Evidence and branches:**
- **Local automated evidence** is the local CI equivalent of 2026-09-29 on PR #7 (GitHub
  Actions is not allocating runners). See [LOCAL_CI_EQUIVALENCE.md](LOCAL_CI_EQUIVALENCE.md) and
  the PR description.
- **Preview evidence:** none. Every Preview still points at the production database (the
  2026-09-29 safety incident; PR #8 makes such a Preview refuse to start). PR #7 also needs
  migration 0067, which shared TEST does not have by instruction.
- **Today's code** is PR #7 `c3522af`. Earlier rounds are on `main`.

Figma node IDs for these items are in [FIGMA_ROUND2_VERIFICATION.md](FIGMA_ROUND2_VERIFICATION.md)
and the round-3 record. Figma could not be re-read today: the connector needs re-authorization.

| QA | Original issue (short) | Latest tester result read | Engineering status | Implementation | Local automated evidence | Preview evidence | Independent retest | Engineering note |
|---|---|---|---|---|---|---|---|---|
| QA-001 | Search: partial and misspelled product names; product images | Partially Fixed | FIXED — NEEDS INDEPENDENT RETEST | round 4 (on `main`) | test_product_search_ranking.py | none (Preview unsafe) | Yes | Suggestion order fixed. 42 of 47 production products have no image: a content gap for Admin → Products, not code. Meeting 2026-09-29 (A): see QA-022/033. |
| QA-002 | Suggested pros/cons | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-003 | Drafts (one per product; follow the account) | Partially Fixed | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-004 | Review public right after submit | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-005 | Footer social links | Deferred | DEFERRED — PRODUCT DECISION | — | — | none (Preview unsafe) | After decision | Needs the owner's social accounts. |
| QA-006 | Shop link on a review without an affiliate link | Partially Fixed | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-007 | Contrast | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-008 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-009 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-010 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-011 | Voting on a review that has votes | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-012 | "Post a request" not clickable (button inside a link) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-013 | Dark Mode control | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-014 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-015 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-016 | Back to Dashboard control | Partially Fixed | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-017 | Figma parity | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-018 | Profile → Dashboard → Back | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-019 | Avatar upload from a phone | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-020 | Comment actions (Share on comments) | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-021 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-022 | Search suggestions: relevance; double clear button | Fail | FIXED — NEEDS INDEPENDENT RETEST (round 4); "MA" relevance: EXPECTED BEHAVIOR — NO ENGINEERING DEFECT; intent/trend search: DEFERRED / LONG-TERM | round 4 (on `main`) | test_product_search_ranking.py; production read-only 2026-09-29: "ma" → Mandaue Foam, Apple MacBook, Uratex Mattress | none (Preview unsafe) | Yes | Meeting 2026-09-29 (A): "MA" matching Mattress is the §6 word-start rule (the same tier as MacBook); no threshold separates them, only intent can. No Eurotex product exists on production today. Long-term: common-search/trend intent from real query volume. |
| QA-023 | Whole question row clickable | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-024 | Share sheet | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-025 | Search category filter (several at once) | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-026 | (see workbook) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-027 | Feed card actions | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-028 | Vote without navigating; Share | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-029 | Reply on every comment | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-030 | Downvote counts visible | Partially Fixed | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-031 | Shop-link wording on mobile | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-032 | Figma parity | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-033 | Search "ma" suggestions | Fail | FIXED — NEEDS INDEPENDENT RETEST (round 4); "MA" relevance: EXPECTED BEHAVIOR — NO ENGINEERING DEFECT; intent/trend search: DEFERRED / LONG-TERM | round 4 (on `main`) | test_product_search_ranking.py; production read-only 2026-09-29: "ma" → Mandaue Foam, Apple MacBook, Uratex Mattress | none (Preview unsafe) | Yes | Same as QA-022 (meeting item A). |
| QA-034 | Question recipient must be clear | Resolved | SUPERSEDED BY OWNER DECISION | PR #7 (owner patch, 2026-09-28) | test_qa_no_audience.py; owner-patch journeys 11–14 | none (Preview unsafe) | Yes | The audience choice was removed (owner 2026-09-28); the pill now reads "About a product / About a store". |
| QA-035 | Price reports | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-036 | iOS zoom on inputs | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-037 | Verdict decides the earning track (follow-up explanation) | Resolved | IMPLEMENTED — NEEDS INDEPENDENT RETEST | PR #7 (2.5★ Super Admin routing) | test_special_routing_api.py; admin journeys 6, 11–13 | none (Preview unsafe) | Yes | 2.5★ "It depends" now routes to a Super Admin (Decision A). |
| QA-038 | Custom pros/cons from a phone keyboard | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-039 | Comment delete confirmation | Partially Fixed | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-040 | Avatar crop | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-041 | Large photo upload (1 MB limit) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-042 | Username save after a large photo | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-043 | Seller-review actions (votes, replies, report) | Fail | FIXED — NEEDS INDEPENDENT RETEST | round 4 (on `main`); wording PR #7 | test_owner_round4_api.py; owner-round4 journeys | none (Preview unsafe) | Yes | Seller-review votes, replies and report into the ordinary queue; copy now says "administrator". |
| QA-044 | Answer appears on submit | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-045 | Notify me on a question | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-046 | (not in the Full Record) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-047 | Seller page long-URL overflow | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-048 | (owner: stays omitted) | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-049 | Honesty Score filter | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-050 | Questions tab filters and sort | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-051 | Timestamp is publication time | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-052 | Sellers tab filters | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-053 | Search All filters groups | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-054 | Rejection/take-down reason shown to the author | Fail | FIXED — NEEDS INDEPENDENT RETEST | round 4 (on `main`); wording PR #7 | test_round3_catalogue_api.py::test_the_author_sees_why… | none (Preview unsafe) | Yes | The administrator's reason is shown to the author. |
| QA-055 | Unread notification styling | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-056 | Header avatar after a photo change | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-057 | Seller page sort and filters | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-058 | Best Answer by the asker only | Open | FIXED — NEEDS INDEPENDENT RETEST | round 2 (on `main`) | test_best_answer_attribution.py; owner-patch journey 14 | none (Preview unsafe) | Yes | Unchanged for Q&A. The same asker-only rule now also closes review requests (see QA-074). |
| QA-059 | Review ⋯ menu overlaps the title | Fail | FIXED — NEEDS INDEPENDENT RETEST | rounds 2–4 (on `main`) | see INDEPENDENT_QA_ROUND3/4_REMEDIATION.md | none (Preview unsafe) | Yes |  |
| QA-060 | Hero image fallback | Resolved | EXPECTED BEHAVIOR — NO ENGINEERING DEFECT | — | suites green on PR #7 | none (Preview unsafe) | No | Resolved by the tester; no engineering change since. |
| QA-061 | Session isolation across tabs | Fail | NOT REPRODUCED (separate profiles stay separate); cross-tab notice: FIXED — NEEDS INDEPENDENT RETEST | round 4 (on `main`) | qa-round2 journeys QA-061 A/B/E | none (Preview unsafe) | Yes | Retest with two browser profiles. |
| QA-062 | Photo crop step | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-063 | Skip photo kept the upload | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-064 | Notification read state and badge | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-065 | Per-notification controls | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-066 | Verdict chip vs the reviewer's quote | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-067 | Interaction notifications | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`); link PR #7 `c3522af` | B-r3; test_round3_catalogue_api.py::test_a_request_upvote_tells_the_requester_once | none (Preview unsafe) | Yes | Request up-vote notices now open the request's own page `/requests/{id}` (2026-09-29). |
| QA-068 | Comment order jumps on a vote | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-069 | Report another member's comment | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-070 | Share image / OpenGraph | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-071 | Product category from a pasted link | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-072 | Pasted URL became the product name | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |
| QA-073 | Requester told when a request is answered | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`); PR #7 `c3522af` | test_round3_catalogue_api.py (request tests); meeting-0929 journey I+J | none (Preview unsafe) | Yes | Meeting 2026-09-29 (J): every answer tells the asker "Someone answered your request", which opens `/requests/{id}` with every answer and the Best Answer control. Before, the notice opened the review alone. |
| QA-074 | A request was only fulfilled by a manual claim | Not yet retested (added in round 3) | SUPERSEDED BY OWNER DECISION | PR #7 `c3522af` | test_round3_catalogue_api.py; test_requests_api.py; meeting-0929 journeys I | none (Preview unsafe) | Yes | Meeting 2026-09-29 (I, final model ≈41:30): the first review no longer closes a request. Every later review of the product is an answer; the ASKER picks the Best Answer; the request then leaves the board, never deleted or archived. Requests must name a product. |
| QA-075 | DTI/SEC registration format | Not yet retested (added in round 3) | FIXED — NEEDS INDEPENDENT RETEST | round 3 (on `main`) | B-r3, F-r3, E-r3 (INDEPENDENT_QA_ROUND3_REMEDIATION.md) | none (Preview unsafe) | Yes |  |

## New engineering findings from the 2026-09-29 meeting (no tester QA ID)

These have no row in the tester's numbering, and none was invented. They belong in an
engineering-owned "New engineering findings" or "Defense readiness" area if the workbook has
one. Otherwise this document is their record. Full detail is in
[MEETING_2026_09_29_DECISIONS.md](MEETING_2026_09_29_DECISIONS.md).

| ID | Finding | Classification | Engineering status | Implementation | Local automated evidence | Independent retest |
|---|---|---|---|---|---|---|
| ENG-0929-B | Admin Reports did not say why an item was reported | OBSERVED BUG + AGREED DECISION | FIXED — NEEDS INDEPENDENT RETEST | PR #7 `c3522af`: a report detail panel beside the list (`ReportDetailPanel`), a deterministic explanation from stored fields (`report_explainer.py`), and evidence stored by the integrity sweep | `test_report_explanations.py` (7), meeting-0929 journey B | Yes: Admin → Review queue → Report → **Why was this reported?** |
| ENG-0929-C | Escalation: leaves Reports, shows on Overview, content stays live, comments limited while a report is open | CONFIRMED CURRENT BEHAVIOR | EXPECTED BEHAVIOR CONFIRMED BY TEAM 2026-09-29. Two gaps (not a standing list; the limit lifts on escalation): DEFERRED — PRODUCT DECISION | none (pinned as is) | `test_escalation_behaviour.py` (4) | Optional |
| ENG-0929-D | "IP detection" shown under Voting Distribution | DOCUMENTATION NEEDED | IMPLEMENTED — NEEDS INDEPENDENT RETEST (the panel shows the real reciprocal-voting numbers). **Network-based vote-farming signal: IMPLEMENTED — NEEDS INDEPENDENT RETEST** in the QA patch below (a keyed network hash; no IP address stored or shown) | PR #7 `c3522af`: `QueueVotingEvidence`, Voting Distribution panel; QA patch `315d86d`: `vote_network.py` | `test_report_explanations.py::…collusion…`, `test_fraud_signals.py`, `test_vote_network.py` (10) | Yes: a queued review with up-voters |
| ENG-0929-E | Seeded defense scenarios (report, copied text, collusion, escalation, dismissal, Bounty Board states, sandbox payout) | DEMO DATA REQUIREMENT | Scenario data ready on a local 0067 database: `verify --scenarios` 12/12, full `verify` 109/109. **Not applied to TEST or production.** This is demo data, not QA evidence | PR #7 `c3522af`: `scripts/defense/{dataset,seed,verify}.py` | `test_defense_scripts.py` (9) | n/a |
| ENG-0929-F | Review-queue tier chips dropped to 0 after choosing a tier | OBSERVED BUG | FIXED — NEEDS INDEPENDENT RETEST | PR #7 `c3522af`: tier facet counts (`referral_service._paginate_cards`) | `test_queue_facet_counts.py` (2; fails without the fix), meeting-0929 journey F (fails without the fix) | Yes: choose a tier chip; the other chips keep their numbers |
| ENG-0929-H | Honesty Score computation (21 → 12 → 15) | DOCUMENTATION NEEDED | COMPUTATION IMPLEMENTED (ADR-003/014: a fixed formula, not a percentile). Engineering documentation written: [TRUST_SCORE_COMPUTATION.md](TRUST_SCORE_COMPUTATION.md) (QA patch below). Zient's own document: still BLOCKED — ZIENT | scoring formula unchanged; recalculation triggers fixed in `272b7dc` | `test_trust_meeting_scenario.py` (5), `test_trust_computation_qa.py` (15) | After Zient's document |
| ENG-0929-I | Bounty Board final model (product-linked; many answers; the asker's Best Answer; off the board, never deleted) | AGREED DECISION | IMPLEMENTED — NEEDS INDEPENDENT RETEST | PR #7 `c3522af`: `request_service`, `/requests/[id]`, the request form's product field, search | `test_round3_catalogue_api.py`, `test_requests_api.py`, `test_qa_authz.py`, meeting-0929 journeys I (2) | Yes (QA-073/074) |
| ENG-0929-K | New answer flow (Figma) | PROPOSED IDEA | DEFERRED — POST DEFENSE | — | — | — |
| ENG-0929-L | New admin, user and seller dashboards and sidebar (Figma) | PROPOSED IDEA | DEFERRED — POST DEFENSE; Figma BLOCKED — EXTERNAL AUTHORIZATION | — | — | — |
| ENG-0929-M | Seller page and review comments threw React error #418 (hydration text mismatch) when an age crossed a unit between the server render and hydration ("now" on the server, "1m" in the browser) | OBSERVED BUG (found by the local CI run on `c3522af`, not in the meeting) | FIXED — NEEDS INDEPENDENT RETEST | PR #7, the commit after `c3522af`: the page reads the clock once and hands it down (`shortAge`, `CommentThread`'s `ageLabel`), the pattern the admin queue already used | br-journeys "a review's age reads the same on the server and in the browser" (browser clock two hours ahead: 2 × #418 without the fix, 3 of 3 runs; passes 3 of 3 with it) | Optional: a seller page or comment thread with a recent item shows no console error |

## QA patch 2026-09-29: Trust Score, anti-farming and plagiarism, Review Queue / Wilson

Three QA items from the priority patch of 2026-09-29. None has a QA ID in the tester's
numbering yet, and none was invented: the IDs below are engineering-owned. The workbook is
still not visible (see the top of this document), so this is their record.

**Branch and evidence (all three):**
- **Code:** PR #7 branch `feat/admin-superadmin-architecture`:
  - `174b46f` All Reviews;
  - `272b7dc` trust recalculation;
  - `a1cd30b` copied text and reused photos;
  - `315d86d` shared-network votes;
  - then the commit carrying the browser journeys and these docs.
- **Migrations:** 0068 (All Reviews indexes), 0069 (image fingerprints), 0070 (vote network
  hashes). All are additive. Shared TEST stays at 0061 by instruction, and nothing here was
  applied to TEST or production.
- **Automated evidence:** the local CI equivalent (GitHub Actions is still not allocating
  runners, so no CI run is claimed).
- **Browser evidence:** Playwright on a local real stack (production Next build, FastAPI,
  Postgres 17). No Preview can be used: every Preview still points at the production database.

### QA — Trust Score Computation (ENG-0929-TRUST)

- **REQUIREMENT:**
  - Document how trust is computed: the inputs, the computation order, the formulas and the
    recalculation triggers, verified against the code.
  - Keep every rule already decided:
    - distinct eligible people;
    - a claimed seller counts 0, probation counts 0;
    - under 30 days and under investigation count half;
    - deleted votes do not count;
    - the concentration hold;
    - the 20 / 60 / 200 thresholds.
  - Invent no formula.
- **ROOT CAUSE:**
  - The formulas were correct: ADR-003 for the score, ADR-016 for the stage evidence, and
    Business Rules §11 for vote weights.
  - Four recalculation triggers were missing, so a member's trust stayed stale until an
    unrelated event:
    - a voter's store claim (their votes drop to 0);
    - an investigation set or cleared on a voter (their votes halve or recover);
    - an Administrator dismissing a concentration hold (the member stayed held until their
      next vote);
    - two votes on one review at the same moment (a race lost one counter increment).
  - Probation and strikes have no application writer: PRODUCT DEFINITION REQUIRED.
- **IMPLEMENTATION:**
  - `272b7dc`:
    - `trust_service.recompute_authors_voted_on_by`, called from `bar_claimed_seller` and the
      investigation endpoint;
    - a recompute on dismissing a `vote_concentration` report;
    - a row lock on the review in `cast_vote` and `remove_vote`.
  - [TRUST_SCORE_COMPUTATION.md](TRUST_SCORE_COMPUTATION.md) covers:
    - the glossary and inputs;
    - the order of computation and the formulas with their sources;
    - the worked 21 / 12 / 15 example;
    - the ladder, weights, evidence and hold;
    - outputs and triggers;
    - the PRODUCT DEFINITION REQUIRED list.
  - The scoring formula itself is unchanged.
- **AUTOMATED EVIDENCE:**
  - `test_trust_computation_qa.py` (15): exact boundaries at 20 / 60 / 200 people and one short;
    half-weight voters; each new trigger; vote removal; no self-set trust; concurrent votes;
    determinism; ADR-003 caps; §11 weights. The concurrency test failed before the row lock:
    12 votes, counter 11.
  - Also run: `test_trust_meeting_scenario.py` (5) and `tests/frontend/trust-score-display.test.mjs` (3).
- **BROWSER EVIDENCE:** `e2e/review-queue-wilson-journeys.spec.ts` T:
  - the Honesty Score on a review page equals the API's `reputation_score` rounded;
  - after an earnings approval recalculates it, the page shows the new figure.
  - A signed-out page can show the previous score for up to 60 seconds (the public page cache
    of `getReviewFull`). This is not changed: caching was not disabled.
- **EXTERNAL BLOCKER:**
  - Zient's trust document is still pending, so ENG-0929-H documentation is BLOCKED — ZIENT.
  - Probation and strike writers: PRODUCT DEFINITION REQUIRED.
- **INDEPENDENT RETEST NEEDED:** Yes. Suggested checks:
  - a reviewer's score before and after an Administrator approves one of their reviews;
  - a voter who claims a store: the authors they voted for are recalculated.

### QA — Anti-Farming / Plagiarism Detection (ENG-0929-INTEGRITY)

- **REQUIREMENT:**
  - Detect possible vote farming by IP.
  - Detect copied text in reviews, updates, answers and comments.
  - Detect reused photos:
    - layer 1, a perceptual hash that needs no provider;
    - layer 2, an external reverse image search, only through an authorised provider.
  - All of these are moderation signals only:
    - no automatic deletion, ban or confiscation;
    - no public accusation;
    - no public IP.
- **ROOT CAUSE:**
  - Copied text was checked only in the nightly sweep, and only for reviews, by a raw
    `pg_trgm` similarity that punctuation or case could defeat.
  - Photos and voter networks were not checked at all.
  - No reverse-image provider is procured.
- **IMPLEMENTATION:** four signals, each filing a SYSTEM_DETECTED report with stored evidence
  and an explanation. See [ANTI_FARMING_AND_PLAGIARISM.md](ANTI_FARMING_AND_PLAGIARISM.md).
  - **Copied text** (`a1cd30b`, `duplicate_content`):
    - normalised text (NFKC, accents, invisible characters, case, punctuation);
    - never flagged under 12 words or 60 characters;
    - flagged when near-identical (character-trigram Jaccard ≥ 0.85, configurable) or when a
      passage is copied (≥ 70% of one side's 3-word phrases, at least 8);
    - checked at submission against the same product and the same author (about 10 ms), and
      platform-wide by the daily sweep for the last two days' reviews;
    - answers and comments are checked as well;
    - product search is not reused.
  - **Reused photos** (`a1cd30b`, `duplicate_image`):
    - SHA-256 plus a 64-bit dHash at upload;
    - near means within 12 bits (measured: a resized, q30, PNG or brightened copy is 0 bits
      away; a 10% crop is 11; unrelated photos are 23–41);
    - corrupt files and decompression bombs are refused;
    - photos uploaded before 0069 have no fingerprint and are not compared.
    - costs about 12.5 ms at 50,000 photos (two queries and a partial index on `reviews.photo_url`,
      which EXPLAIN justified: a single join cost 141 ms).
  - **Reverse image search** (external): `not_configured`. Nothing is scraped or faked.
    EXTERNAL REVERSE IMAGE SEARCH: BLOCKED — PROVIDER/API CREDENTIAL REQUIRED.
  - **Shared-network votes** (`315d86d`, `shared_network_votes`):
    - uses the trusted client IP only (Vercel's edge header, or the BFF's signed address);
    - stored as a keyed HMAC of the network, where IPv6 counts by its /64; RAW IP STORED: NO;
    - kept 30 days;
    - flagged per author over 72 h when 3+ accounts on one network include 2+ under 30 days
      old, or when 5+ accounts cast 10+ up-votes (configurable, flagging only).
    - the check is one index scan: 0.08 ms at 200,259 rows.
  - Reports and panels show counts, account ids and links. They never show an address, a
    hash or a reporter.
- **AUTOMATED EVIDENCE:**
  - `test_duplicate_text.py` (16), `test_duplicate_images.py` (20), `test_vote_network.py` (10);
  - `tests/frontend/client-ip-signature.test.mjs` (4);
  - `test_fraud_signals.py` and `test_report_explanations.py` (the queue and the sweep share
    one detector);
  - the defense scenario of a copied review still flags. `verify --scenarios` gives 12 of 12 on a
    fresh local seed, which also flags one persona's boilerplate paragraph reused across two of
    their own reviews (73% of phrases; see the anti-farming document).
- **BROWSER EVIDENCE:** `e2e/review-queue-wilson-journeys.spec.ts` D:
  - a copied review, with case and punctuation changed, is published at once;
  - its public page shows no finding;
  - an Administrator's **Why was this reported?** reads "Possible copied review" and links the
    original;
  - nothing shaped like an IP appears on the panel.
- **EXTERNAL BLOCKER:**
  - Reverse image search: provider or API credential required.
  - Owner action: set `CLIENT_IP_SIGNING_SECRET` to the same value on the API and the web
    project. Until then, votes cast through the site's BFF record no network, and the signal
    sees only direct API calls.
  - Found while auditing, not changed: the existing first-vote geography reads Vercel geo
    headers on the API. For votes cast through the BFF, that is the BFF's location.
- **INDEPENDENT RETEST NEEDED:** Yes:
  - post a lightly edited copy of another review on the same product: it publishes, and staff
    see a system report with the match;
  - upload the same photo on two reviews: the second is reported.

### QA — Review Queue / Wilson Score (ENG-0929-QUEUE)

- **REQUIREMENT:** "The Review Queue displays the Wilson Score from an older review record and
  does not appear to fetch the newly submitted review."
  - Reproduce first and find the root cause.
  - Use one canonical Wilson, and document raw vs weighted.
  - Keep the queue fresh without disabling caching globally.
  - Add an ALL REVIEWS view:
    - Administrator and Super Admin only;
    - search, filters, the four sorts, pagination;
    - no financial data.
- **ROOT CAUSE:** reproduced on a real database before any change.
  - Under Post-Seeding, the deployed default, a new review's earning state is `none` until its
    trust-weighted votes pass the Business Rules §2 gate (weighted Wilson ≥ 0.65 from ≥ 3
    Stage 2+ voters). So a review written a minute ago is correctly not in the queue.
  - The rows the queue does show are older reviews, each with its own Wilson. No value leaks
    between rows.
  - The engineering suites never showed this because they run the Seeding phase.
  - Found on the way: a review whose votes vanished (a voter's account deleted) was never
    re-counted by the nightly sweep.
- **IMPLEMENTATION:** `174b46f`:
  - `GET /admin/reviews` (staff only) and an **All reviews** tab beside the queue:
    - search; state, earning, product and date filters;
    - newest, oldest, Wilson high to low, Wilson low to high;
    - pages of up to 100;
    - both Wilson figures per row (public: equal votes, 45-day decay; gate: trust-weighted);
    - "why not queued";
    - no money or private fields; author columns only.
  - The queue now:
    - says which phase it runs and why a new review may not be in it;
    - has a Refresh control;
    - shows when it was loaded.
  - One gate implementation (`earn_gate.gate_states`), and orphaned counters re-counted.
  - Indexes 0068, justified by EXPLAIN on 50,472 reviews:
    - page 1 by newest went from 54.9 ms to 0.35 ms;
    - by Wilson, from 72.3 ms to 0.28 ms;
    - page 200, from 127 ms to 17.3 ms.
  - Five queries per page, with no N+1.
- **AUTOMATED EVIDENCE:**
  - `test_all_reviews_and_queue_wilson.py` (12): a new review is in All Reviews but not yet
    queued; every queue row has its own Wilson; Wilson at the edges and after votes vanish;
    public vs gate; sort both ways and paging; filters; staff-only; no money fields.
  - `tests/frontend/all-reviews-model.test.mjs` (7).
- **BROWSER EVIDENCE:** `e2e/review-queue-wilson-journeys.spec.ts`:
  - **Q:** reviews A and B are published and not queued; three trust-weighted up-votes put
    both in the queue, and each row shows its own Wilson, equal to the API's.
  - **R:** All Reviews shows both, with public and gate Wilson equal to the API's. Wilson high
    to low puts A first; low to high puts B first, matching the API. After a voter changes
    their vote, **Refresh** shows A's new Wilson and "2 / 1", and A stays queued.
  - Local run: 4 of 4 passed on a fresh seed, alongside the full CI journey set.
- **EXTERNAL BLOCKER:**
  - Figma re-check of 6922:837 and 5017:2225: BLOCKED — the Figma connector needs
    re-authorization (see [ADMIN_FIGMA_PARITY.md](ADMIN_FIGMA_PARITY.md)).
  - No Preview is safe to test on.
- **INDEPENDENT RETEST NEEDED:** Yes:
  - write a review: it appears at once under **All reviews**, with "Not queued yet" and its
    gate figure;
  - after three trusted up-votes it appears in the queue;
  - change a vote, press **Refresh**, and see the new Wilson.

## Summary

- **Workbook:** BLOCKED (not visible to the connected Drive account; no cell-write capability).
- **Rows reconciled here:** 75 (QA-001 … QA-075).
- **Rows whose engineering entry changes because of today's work:**
  - QA-022 and QA-033 (meeting A);
  - QA-058 (the same rule now applies to requests);
  - QA-067 and QA-073 (the notice link);
  - QA-074 (superseded by the 2026-09-29 decision).

  QA-034, QA-037, QA-043 and QA-054 carry the 2026-09-28 owner-patch changes.
- **New engineering findings:** ENG-0929-B, C, D, E, F, H, I, K, L, and M (found by local CI, not the meeting).
- **QA patch 2026-09-29:** ENG-0929-TRUST, ENG-0929-INTEGRITY and ENG-0929-QUEUE, each FIXED or IMPLEMENTED — NEEDS INDEPENDENT RETEST. External reverse image search: BLOCKED — PROVIDER/API CREDENTIAL REQUIRED. ENG-0929-D and H updated.
- **Tester-owned cells modified:** 0.

# Dev/QA sync of 2026-09-29: decision ledger

**Sources:**
- `2026-09-29 18-06-45 - transcript.md`, the readable summary;
- `2026-09-29 18-06-45 - transcript (raw timestamps).txt`, used to check wording and order.

The recording is auto-transcribed Taglish with no speaker labels. A sentence becomes a
decision here only when the call explicitly agreed it. When a later explicit agreement
contradicts an earlier brainstorm, the later one wins; section I is the main case.

**What was checked against what:**
- Branch: `feat/admin-superadmin-architecture` (PR #7), on top of PR #5.
- Production, read-only: `main` @ `087a45b`, database migration 0060. The only reads were
  public API GETs.
- Nothing in production was changed.

**Classifications:**
- AGREED DECISION
- CONFIRMED CURRENT BEHAVIOR
- OBSERVED BUG
- PROPOSED IDEA
- DEFERRED / LONG-TERM
- DEMO DATA REQUIREMENT
- DOCUMENTATION / EXPLANATION NEEDED

**QA IDs** are the tester's, from the repository's engineering copy of the workbook:
- [FULL_SYSTEM_QA_MATRIX.md](FULL_SYSTEM_QA_MATRIX.md);
- [INDEPENDENT_QA_ROUND3_REMEDIATION.md](INDEPENDENT_QA_ROUND3_REMEDIATION.md);
- [INDEPENDENT_QA_ROUND4_REMEDIATION.md](INDEPENDENT_QA_ROUND4_REMEDIATION.md).

The live workbook could not be opened today; see
[QA_CURRENT_RECONCILIATION.md](QA_CURRENT_RECONCILIATION.md).

A topic with no tester row gets an engineering ID (`ENG-0929-x`), never a new QA number.

## Summary

| # | Topic | Time | Classification | Outcome |
|---|---|---|---|---|
| 0 | Preview refuses the production database | 01:30–02:00 | CONFIRMED CURRENT BEHAVIOR | The PR #8 guard fired on a Preview the team opened: *"A non-production app … refuses to start on the production database. Anyway, okay naman yun."* Working as intended. |
| A | Search: "MA" suggestions | 02:00–07:15 | OBSERVED (tester) → KNOWN SEARCH QUALITY ISSUE / LONG-TERM RELEVANCE TUNING | Matches the §6 word-start rule; no defect. Intent prediction deferred. |
| B | Admin report does not say *why* it was reported | 07:24–10:40 | OBSERVED BUG + AGREED DECISION (side-by-side panel) | Built: report detail panel with grounded evidence. |
| C | Escalation | 10:38–13:30 | CONFIRMED CURRENT BEHAVIOR (with two recorded gaps) | Pinned by regression tests. The gaps go to the owner. |
| D | "IP detection" / voting anomaly | 13:41–17:40, 21:30 | DOCUMENTATION NEEDED: **the meeting's conclusion is wrong** | No IP-based vote detection exists. The panel the team read is a static "no data" note. |
| E | Seed demo anomaly and report data | 17:40–19:15, 43:30–44:30 | DEMO DATA REQUIREMENT | Defense seed extended; scenario check added. |
| F | Review-queue filter counts drop to 0 | 19:40–20:40 | OBSERVED BUG (general UI polish deferred) | Reproduced and fixed. |
| G | Payout | 19:15–21:20 | CONFIRMED CURRENT BEHAVIOR | No change. |
| H | Trust (Honesty) Score computation | 21:52–26:50 | DOCUMENTATION NEEDED | Code path documented. The meeting's "percentile" description does not match the code. Zient's document pending. |
| I | Review Requests / Bounty Board logic | 26:57–42:55 | AGREED DECISION (final clarification ≈41:30) | Implemented: Best Answer by the asker, request kept permanently. |
| J | "Someone answered your request" goes nowhere useful | 27:50–34:40 | OBSERVED BUG | Notices deep-link to the request's own page. |
| K | New answer flow (Figma) | 45:00–46:45 | PROPOSED IDEA, explicitly lower priority | DEFERRED — POST DEFENSE. |
| L | New admin / user / seller dashboards and sidebar (Figma) | 46:46–47:05 | PROPOSED IDEA | DEFERRED — POST DEFENSE. Figma unreadable today. |

## A. Search: fuzzy matching

- **Timestamp:** 02:00–07:15.
- **Classification:** OBSERVED (tester) → KNOWN SEARCH QUALITY ISSUE / LONG-TERM RELEVANCE TUNING.
- **Observed:**
  - "Pag tinry mo yung MA sa Macbook … may lumalabas na Eurotex, may lumalabas na Apple Macbook."
  - The tester expected only names that start with "MA".
- **Proposed:**
  - Category tagging while searching ("electronics or food and beverage").
  - Later, "common search terms / search trends" the way Google does it, so "Apple" leans to the
    iPhone.
- **Final:**
  - "I think that will take a while since kailangan ng maraming search … ongoing progress even
    sa Google."
  - The trend/intent idea is long-term work that needs real search volume. It is not for
    tomorrow.
- **Current implementation:** `backend/app/services/product_search.py`, explicit tiers:
  1. exact name;
  2. alias;
  3. the name starts with the query;
  4. a word of the name starts with the query;
  5. an alias word starts with the query;
  6. trigram typo match (≥ 0.55, queries of 3+ characters only);
  7. substring (queries of 4+ characters only).

  Two-letter queries match word starts only.
- **Checked on production, read-only (`GET /api/v1/products?q=ma&browse=true`,
  2026-09-29 ~12:15 UTC):**
  1. Mandaue Foam Waterproof Mattress Protector (the name starts with "Ma");
  2. Apple MacBook Air M2 (a word starts with "Ma");
  3. Uratex Classic Mattress (a word starts with "Ma").

  No product named Eurotex exists on production today. If one did, its "Mattress" word would
  place it in the same word-start tier as MacBook. The Reviews tab (`/reviews/feed?q=ma`)
  lists those products' reviews in the reader's chosen sort (Most helpful / Latest), not by
  match tier. That is by design.
- **Assessment:**
  - With two letters, "MA" is equally a prefix of *MacBook* and *Mattress*. No threshold
    separates them; only intent can, which is the long-term item.
  - The threshold was already tightened for this exact complaint in round 4 (QA-022/033:
    "man" no longer matches MacBook as a typo).
  - No low-risk ranking defect was found.
- **Action required:** none today. The long-term item goes to the backlog: search-trend and
  synonym intent from real query volume, curated with canonicalization (§6).
- **QA items:** QA-022, QA-033 (and QA-001 for suggestion order).
- **Figma node:** none. **Demo requirement:** none.
- **Status:** EXPECTED BEHAVIOR — NO ENGINEERING DEFECT (word-start rule). Intent prediction:
  DEFERRED / LONG-TERM.

## B. Admin report detail: why was it reported?

- **Timestamp:** 07:24–10:40.
- **Classification:** OBSERVED BUG + AGREED DECISION.
- **Observed:** "Open the reported item" (for example "fake photo or receipt") opens the
  review, "but it doesn't tell na bakit siya nireport". The administrator has to reconstruct
  the reason by hand.
- **Proposed and agreed:**
  - Open a side page or panel instead, with the report's details beside the reported item's
    details, "side by side", like the Reviews tab.
  - Include a summary of why it was reported, for example "a matching review already exists
    in our database".
- **Current implementation (before):** `components/admin/ReviewQueueScreen.tsx` → `ReportsTab`.
  - Each card shows the reason label, origin, the escalation badge, age, priority tier and
    the reporter's note, plus a link to the item.
  - There is no evidence panel.
  - System-detected reports stored only the signal's name (`context.signal`), not its
    evidence.
- **Built:**
  - Every report card opens a **report detail panel** beside the list. On narrow screens it
    stacks under the card.
  - Summary: a deterministic "Why this was reported" sentence, assembled from stored fields
    only. No generative text.
  - Report facts:
    - reason category;
    - origin (User-reported / System-detected);
    - reporter note;
    - filed time;
    - reports on this item and the weighted escalation state;
    - the report's own resolution.
  - The reported content: title, author, body excerpt, rating, whether it is published or
    taken down, and a link to it.
  - Evidence, where stored:
    - **Copied text:** "Possible copied review: its text closely matches another review in
      the database", with the matching review linked and the similarity shown. Only when
      the duplicate check actually matched.
    - **Collusion:** the reciprocal up-voter numbers and the threshold.
    - **Vote velocity:** the burst.
    - **Verdict/star mismatch.**
    - **Vote concentration** (a user target): the cohort facts already stored.
  - The integrity sweep now stores each signal's evidence on the report when it files it.
    Reports filed earlier show the signal and say that no evidence was stored.
  - Found and fixed while building this: the copied-text check was symmetric, so it flagged
    the **original** review as well as the copy, naming an honest author a copier. It now
    flags only the later review (`fraud_service`, `created_at` of the match must be earlier).
    Pinned in `test_report_explanations.py`.
  - Reverse-image search is **not** claimed anywhere: no provider is configured (ADR-007),
    and the panel says so.
- **QA items:** NO EXISTING TESTER QA ID → **ENG-0929-B**. QA-069 (reporting a comment) and
  QA-043 (reporting a store review) land in the same queue and benefit.
- **Figma node:** the Reviews tab's detail column, as in [ADMIN_FIGMA_PARITY.md](ADMIN_FIGMA_PARITY.md).
  Figma could not be re-read today.
- **Demo requirement:** the defense seed now carries a user report, a system-detected
  copied-text report, a collusion report and an escalated one (section E).
- **Status:** FIXED — NEEDS INDEPENDENT RETEST.

## C. Escalation

- **Timestamp:** 10:38–13:30.
- **Classification:** CONFIRMED CURRENT BEHAVIOR.
- **Observed:** "may in-escalate ako and then nandun lang siya sa overview". After escalating,
  the report left Reports and showed only on the Overview. The escalated post stayed live,
  but a tester could not comment ("nire-review pa ito ng moderator").
- **Agreed:**
  - "Tama lang ganun … tama lang naman yun."
  - Leaving Reports on escalation is right.
  - Content staying live while comments are limited is right.
  - It "only goes away when removed or dismissed".
- **Current implementation, verified in code and now pinned by
  `backend/tests/test_escalation_behaviour.py`:**
  1. **Escalate** (`POST /admin/reports/{id}/decision`, `resolution=escalated`) closes the
     report, so it leaves the open Reports queue. ✔ matches.
  2. The escalation is written to the audit log as `escalate`, which the Overview's recent
     activity lists as "Escalated". ✔ matches: "doon lang siya sa overview lumalabas".
  3. Nothing is done to the content: it stays published. ✔ matches.
  4. Comments on a review with an **open** report are limited to established members
     (`comment_thread_reported`: "This thread is under review by our administrators …").
     ✔ matches for the open-report state.
- **Two gaps between that description and the current model:**
  - **(a) Not a standing list.** Overview shows escalation as a row in *recent activity*
    (the last five actions). Five later actions push it off Overview; it stays in
    `/admin/activity`. No list keeps escalated items at the top until someone dismisses
    them, and an escalated report has no later "dismiss" step in the current model.
  - **(b) The comment limit follows open reports, not escalation.** Escalation closes the
    report, so the limit lifts when it is escalated, unless the review has another open
    report. Most reported reviews carry both a member's report and a system one, which is
    likely what the team saw.
- **Action required:** none before the defense; the team explicitly accepted today's
  behaviour. If the owner wants (a) and (b) exactly as described ("stays on top for every
  administrator until dismissed; comments stay limited while escalated"), that changes the
  report model: escalation becomes a state with a later decision. That is a post-defense
  change. It is recorded here and not built.
- **Terminology:** user-facing copy already says "administrators" on this branch (for
  example the comment limit). The transcript's "moderator" is the older name.
- **QA items:** NO EXISTING TESTER QA ID → **ENG-0929-C**.
- **Demo requirement:** an escalated report is seeded (section E).
- **Status:** EXPECTED BEHAVIOR CONFIRMED BY TEAM 2026-09-29. Gaps (a) and (b): DEFERRED —
  PRODUCT DECISION.

## D. "IP detection" and the voting anomaly

- **Timestamp:** 13:41–17:40, and again at 21:28 ("IP detection pala, mahanap dito sa
  bandang voting distribution … nag-vote sa same location").
- **Classification:** DOCUMENTATION / EXPLANATION NEEDED. **The meeting's conclusion does not
  match the code, and the team should know before the panel.**
- **What the meeting concluded:** IP / same-location upvote farming shows in **Voting
  Distribution → "no flagged voter / per-voter risk data"**, which read "0-0" for that post.
- **What the code does:**
  - That panel (`ReviewQueueScreen.tsx`, "Voting Distribution") is a **static note**: "No
    flagged-voter or per-voter risk data exists." It is not a zero count. It says there is
    no per-voter risk model and no per-review voter geography to show.
  - **No IP is recorded for votes.** IP addresses are recorded only on affiliate-link click
    sessions (`/r/{id}`), for attribution, hashed after 30 days and deleted after 90
    (`retention_service.py`). Vote IP capture was deferred pending a privacy assessment
    (`fraud_service.py` docstring).
  - The voting anomalies the system actually detects, all advisory:
    - **Collusion (reciprocal voting):** a review with ≥ 5 up-voters, more than 60% of whom
      the author up-votes back (`ranking.COLLUSION_MIN_VOTERS`, `COLLUSION_THRESHOLD`).
      Shown in the review's Signals panel. The integrity sweep files it as a
      SYSTEM_DETECTED report.
    - **Vote velocity:** a burst of up-votes inside the velocity window. Shown and filed the
      same way.
    - **Vote concentration:** a member whose counted votes come mostly from a small
      repeated cohort (ADR-016). Their promotion into the evidence-gated stages is held,
      and a SYSTEM_DETECTED report is filed on the member with the cohort facts.
  - The post ranked Highest with 0 flags: the queue's tier comes from the integrity tier and
    from being untouched past the 72-hour aging window, not from anomaly flags. That
    reading at 17:05 was correct.
- **What to say at the defense:** "Upvote farming is detected from the voting relationships
  themselves (reciprocity, bursts, repeated cohorts), not from IP addresses. We do not
  collect voter IPs." Do not demo an "IP issue detected" screen; none exists.
- **Built:**
  - The Voting Distribution panel now shows this review's real reciprocal-voting numbers
    (up-voters, how many are up-voted back, the 60% line) in place of the "no data"
    sentence, whenever there are up-voters.
  - It says in words that no IP is used.
  - The report detail panel (B) shows the same facts for a collusion report.
- **QA items:** NO EXISTING TESTER QA ID → **ENG-0929-D**.
- **Demo requirement:** a collusion case and the existing vote-concentration case are seeded
  (section E).
- **Status:** IMPLEMENTED — NEEDS INDEPENDENT RETEST (display). The "IP detection" claim is
  **NOT IMPLEMENTED**; the objectives paper and the defense script must not claim it.

## E. Defense demo data

- **Timestamp:** 17:40–19:15 ("mag-seed na ngayon … author for demo") and 43:30–44:30 ("demo
  test lang sa report tapos yung may mga anomaly voting").
- **Classification:** DEMO DATA REQUIREMENT.
- **Current:** `backend/scripts/defense/` (seed, reset, verify) already writes a deterministic
  32-account dataset through the real API ([DEFENSE_DATA_MANIFEST.md](DEFENSE_DATA_MANIFEST.md)).
  It refuses anything but bluntly-ph-test or a local database.
- **Added:**
  - an **escalated** report;
  - a **system-detected copied-text** report, produced by the real integrity sweep over a
    review that copies another;
  - a **system-detected collusion** report, from the existing five-account ring and its
    reciprocal votes;
  - Bounty Board requests:
    - one unanswered;
    - one with several answers, waiting on the asker;
    - one with a Best Answer, still visible on its page and in search.

  `python -m scripts.defense.verify --scenarios` reports each scenario present or missing.
- **Names:** every account and store is fictional and named like a real one, as the dataset
  already does. No "test123" data.
- **Scenario data is not QA evidence:** it proves each scenario can be shown, not that it
  passed independent QA.
- **Where it can run:**
  - This branch needs migration 0067. Shared TEST stays at 0061 by instruction.
  - So today the seed can run on a local Postgres, or on an isolated database once one is
    authorized. It does not run on shared TEST or on production.
  - See "Where the demo runs" below.
- **Seed run on a fresh local Postgres at 0067 (2026-09-29, 31 s, all through the real API):**
  - 48 reviews and 4 member reports: 1 escalated, 1 dismissed.
  - The live integrity sweep checked 46 reviews and filed 7 system reports: copied text on
    Jomar's PS5 review (0.875 similar, linked to Carla's), and collusion on each of Jomar's six
    reviews (5 of 8 up-voters up-voted back). No honest member's review was flagged.
  - The vote-concentration hold on Jomar.
  - 3 requests: 1 with a Best Answer, 1 with two answers waiting, 1 unanswered.
  - `verify --scenarios` 12/12; the full `verify` 109/109 (one warning: no image storage
    locally).
- **Status:** READY on a local database. Not applied to any shared environment.

## F. Review-queue filter counts

- **Timestamp:** 19:40–20:40 ("when you click yung mga filter dito, matching filter, nagiging
  zero yung iba, tapos bumabalik lang pag-clinic mo ulit").
- **Classification:** OBSERVED BUG. Only general UI polish was deferred to finals ("hindi naman
  siya bleeding … kung sa finals na lang"); a wrong number is not polish.
- **Reproduced (backend):**
  - `referral_service._paginate_cards` computed `counts` over the cards the current filter
    kept.
  - The tier chips ("Matching this filter: Highest 3 · High 0 …") are also the tier filter's
    toggles.
  - So selecting one tier set every *other* tier chip to 0 until the tier was cleared.
- **Root cause:** counts calculated from the filtered subset instead of per facet. Not stale
  client state, not a cache, not a race.
- **Fixed:**
  - Each tier chip now counts what selecting it would show: every other filter applied, the
    tier filter left out.
  - The band and SLA chips, which are not toggles, still describe the current filter, as
    their label says.
  - The Reports tab already counted this way.
- **Regression:** `tests/test_queue_facet_counts.py`.
- **QA items:** NO EXISTING TESTER QA ID → **ENG-0929-F**.
- **Status:** FIXED — NEEDS INDEPENDENT RETEST.

## G. Payout

- **Timestamp:** 19:15–21:20.
- **Classification:** CONFIRMED CURRENT BEHAVIOR.
- **Said:** "Inayos na yung payouts dito. Ay, meron na pala." Asked "ba't hindi mo nilagyan ng
  pera (300)?", the answer was: fake money, sandbox only, "naka-clearly indicate naman. So,
  safe naman kami."
- **Current:** unchanged.
  - PayPal sandbox only.
  - ₱300 minimum.
  - Only cleared, reconciled money is withdrawable.
  - The demo account simply had no cleared balance at or above ₱300.
- **Action:** none. No defect identified. **QA items:** none changed.
- **Status:** EXPECTED BEHAVIOR — NO ENGINEERING DEFECT.

## H. Trust (Honesty) Score computation

- **Timestamp:** 21:52–26:50.
- **Classification:** DOCUMENTATION / EXPLANATION NEEDED.
- **Observed:** on the tester's review (3 up, 1 down) the score read 21.
  - A comment did not change it.
  - After the tester's downvote ("2-2") it read 12.
  - After removing the downvote it read 15.
- **Said in the meeting:**
  - The score is percentile-based with no fixed formula.
  - Zient owns it and will provide a document covering every calculation, for the panel's
    "computational methods" question.
- **Current implementation (read from code, not inferred from the numbers):**
  - The profile's Honesty Score is `users.reputation_score`, computed by
    `app/services/trust.py::reputation_score` (ADR-003, estimator from ADR-014):

    ```
    score = clamp(0, 100,
        0.60 × helpfulness                      # up to 60
      + min(25, 10 × log10(1 + verified reviews))
      + min(15, 3 × Best Answers)
      − 15 × strikes)
    helpfulness = 100 × Wilson lower bound (95%) of helpful / (helpful + not helpful)
                  over the member's review votes
    ```

  - It is recomputed on every vote (`trust_service.recompute_user_trust`). Inputs are review
    votes, verified-review count, Best Answers and strikes. **Comments are not an input**;
    `tests/test_trust_meeting_scenario.py` pins that.
  - It is a fixed, deterministic formula, **not a percentile**. The Wilson bound is why one
    vote moves it so much on a small record: 3/1 and 2/2 are very different lower bounds on
    four votes.
  - The observed 21 → 12 → 15 is consistent with this formula for a member with one verified
    review whose votes went 3 up/1 down → 2 up/2 down → 2 up/1 down. The test pins those
    three points of the *implemented* formula. It does not define a new one.
- **Action required:**
  - Engineering: none. Scoring is unchanged.
  - Zient: confirm whether the business rule is this formula or a percentile rank. If it is a
    percentile, the code does not implement it yet, and that is a product decision.
- **QA items:** none cover the computation. QA-049 (the Honesty Score *filter*, open rule
  §21) and QA-053 (trust-rating filter bands) are adjacent → **ENG-0929-H**.
- **Zient document:** not found in the repository or the connected Drive → **OWNER
  DOCUMENTATION PENDING — ZIENT**. ADR-003 and ADR-014 are engineering's record of what is
  built.
- **Status:** COMPUTATION IMPLEMENTED. DOCUMENTATION BLOCKED — ZIENT.

## I. Review Requests / Bounty Board

- **Timestamp:** 26:57–42:55. Final clarification about 41:30–42:55.
- **Classification:** AGREED DECISION. The earlier proposals were superseded.

### Chronology (what is *not* the decision)

1. **27:50–34:40 (observed):**
   - The tester answered "Is Tefal wok pan durable?" and the asker was notified.
   - The Requests page did not change ("two waiting pa din"), and nobody could tell where the
     answer lived.
   - Not in Figma.
2. **33:50–34:40 (proposed):**
   - The notification opens the review, then a modal asks the asker to confirm it answered
     the question.
   - "we can agree with that one": provisional.
3. **34:40–37:40 (proposed):** once confirmed, the request is archived and leaves the list.
4. **38:30–40:10 (proposed, viole):**
   - Pending / Recently answered sub-tabs.
   - An answered request stays in "Recently answered" for 24 hours.
   - The Figma draft shows these tabs.
   - Counterpoint: "hindi siya nadidelete … bakit tayo magdidelete ng data".
5. **40:40–41:30 (converging):** "kahit wala nga tayong recently answered … mapunta na lang
   siya sa thread na ito … searchable pa rin siya".

### Final agreed model (41:37–42:55)

> "Kapag nag-post ka ng question, you will have to link a product … yung question mo ay
> mapupunta sa thread na to. If ikaw yung asker … nag-award ka ng best answer, andito pa rin
> yun sa thread na to. Ang purpose ng bounty board is for the most recently or anticipated
> question to be recognized kagad … Hindi siya para sa mga nagtatanong. Para siya sa mga
> tagasagot … It will just disappear. Hindi siya may remove, hindi siya mag-archive. It will
> just go to the thread na it belonged to originally."
> "Yep, yep. That's clarified. Okay na din yung logics for me."

1. Every request names a product.
2. It belongs permanently to that product's thread.
3. The Bounty Board surfaces open, most-wanted requests **for answerers**; it is not where the
   request is stored.
4. Many people may answer.
5. The **asker** awards the Best Answer.
6. Then the request leaves the board. It is **not deleted and not archived**; it stays
   viewable and searchable.

**Superseded:**
- the confirm-modal flow (step 2);
- archiving (step 3);
- Pending / Recently answered tabs with 24-hour expiry (step 4, including the Figma draft).

### Current implementation (before)

`review_requests`, `request_service.py`, `/requests`:
- A request's product was optional (a free-text title, or a pasted listing).
- **The first published review of the product closed the request automatically** (QA-074),
  so only one person could answer and the asker picked nothing.
- A fulfilled request had no page of its own, so once closed it could not be seen anywhere.
- "Answer with a review" opened an empty composer.

### Built

**Backend:**
- **Product required:** a new request must name a product (`request_product_required`,
  422), directly or through a listing the catalogue already knows.
- **Answers:** every published review of that product, written after the request by someone
  other than the asker. Many answers per request.
- **Board:** a request stays on the board (`status=open`) until the asker picks. Each new
  answer tells the asker "Someone answered your request". Up-voters are told once, at the
  first answer.
- **Best Answer:** `POST /requests/{id}/best-answer` (asker only; the review must be one of
  its answers) marks it `fulfilled`, records the review and the time, and tells the review's
  author.
  - The request leaves the board, because the board lists `open` only.
  - Nothing is deleted or archived.
  - The old reviewer self-claim `POST /requests/{id}/fulfill` now carries the same asker-only
    rule, so no one else can close a request.
- **Search:** `GET /requests?q=` searches requests in any state except removed.

**Frontend:**
- **Request page `/requests/{id}`:** the canonical, permanent page.
  - The question, the product, the status and the up-votes.
  - Every answer (review), with **Pick as Best Answer** for the asker while it is open.
  - The Best Answer is pinned on top once picked.
- **Board rows** open the request page, show the answer count, and "Answer with a review"
  opens the composer with the product already chosen (`/reviews/new?product=`).
- **Posting a request** starts by picking the product.
- **Search → Questions** also lists matching review requests, answered or not.
- **Product thread:** the request page links to the product's reviews and Q&A through search
  (`/search?q=<product>`). This build has no standalone product page, so the request page
  is the permanent home the meeting called "the thread".

### QA and status

- **QA items:**
  - **QA-074:** auto-fulfil on first review → **SUPERSEDED BY OWNER DECISION 2026-09-29**
    (asker's Best Answer).
  - **QA-073:** requester told when answered → still true; the link moves (see J).
  - **QA-058:** Best Answer by the asker (Q&A) → the same rule now applies to requests.
- **Figma node:** the Requests page draft with *Pending / Recently answered* (shown at ≈39:00)
  is superseded by the final model. Node IDs could not be read; Figma needs
  re-authorization.
- **Demo requirement:** the three request states are seeded (section E).
- **Status:** IMPLEMENTED — NEEDS INDEPENDENT RETEST.

## J. Answer notification deep link

- **Timestamp:** 27:50–34:40.
- **Classification:** OBSERVED BUG.
- **Observed:**
  - The asker's notice existed, but "dito pa rin ako nararoute sa review request". It sent
    the asker back to the board, and "walang nangyari dun sa mismo review request".
  - "Once click kasi dapat mapunta siya dun sa request na yun": the notice should land on
    the request.
- **Before:**
  - "Your review request was answered" linked to the review alone.
  - Up-vote notices linked to `/requests#request-<id>`, an anchor on a board the request
    could already have left.
- **Built:** every request notice links to the request's own page `/requests/{id}`:
  - "Someone answered your request";
  - "A review you were waiting for is up";
  - "Your review was picked as the Best Answer";
  - up-vote notices.

  The page shows the question and all its answers, with the Best Answer control for the
  asker.
- **QA items:** QA-073 (link target), QA-067 (up-vote notices).
- **Status:** FIXED — NEEDS INDEPENDENT RETEST.

## K. New answer flow (Figma)

- **Timestamp:** 45:00–46:45.
- **Classification:** PROPOSED IDEA; lower priority by explicit instruction.
- **Shown:** an answer page with the main question, usage expectation, "where is this from",
  the good, the bad, a rating, an optional image, then the posted result.
- **Said:** "yung flow muna … if … it will mess up the flow and the sequence, siguro wag muna
  kasi bukas na to … mahirap mag-debug … same day". Priority is the logic agreed with Gab and
  the reviewer flow; this only "if time".
- **Current:**
  - Answering a request means writing an ordinary review of its product, which already has
    the full composer (rating, verdict, pros/cons, photo).
  - Answering a Q&A question is a text answer.
- **Figma:** not readable today (the connector needs re-authorization), so no node IDs are
  recorded and nothing was built from memory.
- **Status:** DEFERRED — POST DEFENSE.

## L. New admin, user and seller dashboards and sidebar (Figma)

- **Timestamp:** 46:46–47:05.
- **Classification:** PROPOSED IDEA.
- **Current:**
  - PR #7 carries the Administrator/Super Admin console ([ADMIN_FIGMA_PARITY.md](ADMIN_FIGMA_PARITY.md)).
  - PR #7 also carries the seller dashboard ([SELLER_DASHBOARD_FIGMA_PARITY.md](SELLER_DASHBOARD_FIGMA_PARITY.md)),
    built from the frames available then.
  - The new frames shown today could not be read.
- **Status:** DEFERRED — POST DEFENSE. Figma: BLOCKED — EXTERNAL AUTHORIZATION.

## Where the demo runs (owner decision)

None of today's changes reaches the defense unless the environment that serves the demo runs
this branch:

| Environment | Code | Database | Has today's changes |
|---|---|---|---|
| Production `bluntly.ph` | `main` `087a45b` | PROD at 0060 | No. Needs PR #5 and PR #7 merged, and PROD migrated through 0067. Both are production changes not authorized here. |
| Previews | per branch | still the **production** project (Preview variables not yet moved to TEST) | Unsafe for interactive demo. PR #8 makes them refuse to start. |
| Shared TEST | — | 0061 | Cannot run PR #7 (needs 0067; TEST stays at 0061 by instruction) |
| Local | this branch | local Postgres at 0067 | Yes. The defense seed and the scenario check run here. |

The owner decides whether the defense uses production as it stands (without today's changes)
or an authorized isolated environment running PR #7.

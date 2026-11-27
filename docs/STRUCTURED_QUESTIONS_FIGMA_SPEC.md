# Structured questions & answers — Figma spec and frontend contract

Owner: PIM (Figma). Implementer: RESEARCH (backend, API, validation, persistence, remaining UI).
Status: 2026-10-05. Figma file `lso4Ri4hDaZxvCebhUqlY5` ("Page 1", `0:1`).

> **Source fidelity — VERIFIED AGAINST LIVE FIGMA (2026-10-05, afternoon).** The first draft was
> written from Page 1 metadata cached at 10:22. PIM then re-pulled the live Page 1 metadata and
> diffed every frame: **all Ask (7573:10506…11005) and Answer (7573:8215…9158) frames are
> unchanged**. Since the cache, Figma has only added the floating `QuickActions/Button` (56 × 56 at
> x318 y764) to Screen/Search, Screen/Question, Screen/Product and the reviewer screens, plus
> `Overlay/QuickActions` (8502:40871) and `Overlay/QuickActions/SignedOut` (8511:41142). Styles
> were then read live with `get_design_context` (Ask Step 2.1 7573:10601, Answer Step 4.1
> 7573:8678, Answer Step 5.1 7573:8753) and screenshots (Ask Step 2.3 7573:10791, Answer Step 2b
> 7573:8591, Step 7 7573:9133, Done 7573:9158). Every text string is verbatim from Figma.

The document has three kinds of content, each marked:

- **FIGMA**: what the current frames draw. This is canon.
- **OWNER RULE**: behaviour the owner set, which overrides Figma.
- **PROPOSED**: engineering choices where Figma is silent. RESEARCH may change these, but should
  record the change here.

---

## 1. Frames (current, read 2026-10-05)

Frames are listed left to right on the canvas, which is the flow order. Every frame is 390px wide
(mobile). **No desktop frames exist for Ask, Answer or Question** (searched the whole page).

### Ask a question

| Order | Frame | Node | Height | What it is |
|---|---|---|---|---|
| 1 | `Screen/Ask/Step 4` | 7573:10886 | 844 | Find the product (empty search) |
| 2 | `Screen/Ask/Step 1` | 7573:10945 | 844 | Find the product (with results) |
| 3 | `Screen/Ask/Step 2` | 7573:10506 | 1101 | Write the question + request specifics (empty) |
| 3a | `Screen/Ask/Step 2.1` / `2.2` / `2.3` | 7573:10601 / 10696 / 10791 | 1101 | Same, filled; the variants differ only in fills (chip states), not in text or layers |
| 4 | `Screen/Ask/Step 3` | 7573:11005 | 844 | Done: "Now, we wait.." |

The frame names are not in flow order (the empty search is "Step 4"). Use the order above.

### Answer a question

| Step | Frame | Node | Height | Title |
|---|---|---|---|---|
| 1 | `Screen/Answer/Step 1`, `1.1` (filled) | 7573:8215, 7573:8403 | 844 | "Straight to the point" |
| 2 | `Screen/Answer/Step 2a`, `2a.1` (selected) | 7573:8936, 7573:8983 | 844 | "Been there, used that" |
| 2 (alt) | `Screen/Answer/Step 2b` | 7573:8591 | 844 | "Where's this from?" (see §11, open question 1) |
| 3 | `Screen/Answer/Step 3`, `3.1` | 7573:8792, 7573:8864 | 1130 | "The good, the bad" |
| 4 | `Screen/Answer/Step 4`, `4.1` (chosen) | 7573:8635, 7573:8678 | 844 | "Your verdict" / "Your verdict!" |
| 5 | `Screen/Answer/Step 5`, `5.1` (It depends) | 7573:8714, 7573:8753 | 844 | "Is it for them?" |
| 6 | `Screen/Answer/Step 6`, `6.1` (low), `6.2` (high) | 7573:9030, 7573:9062, 7573:9098 | 844 | "Rating time" |
| 7 | `Screen/Answer/Step 7` | 7573:9133 | 844 | "Show, don't tell" |
| Done | `Screen/Answer/Done` | 7573:9158 | 844 | "Answer posted!" |

Every Answer step frame carries "Step N out of 7" (`Step 1 out of 7` … `Step 7 out of 7`) at
(16,130), whatever the question asked.

### Question detail, threads, components

| Frame | Node | Notes |
|---|---|---|
| `Screen/Question` | 7731:15601 | Question detail (390 × 2507): ProductStrip, Verdict Summary, the question, the best answer, "N more answers", answer rows, threads |
| `Screen/Question/Thread` | 7735:8020 | Focused thread. **Already built** (`?thread=<reply id>`, PIM commit f528c1e). Do not rebuild it |
| `Question Page Components` (section) | 7761:7856 | `ThreadCard` 7761:7892, `Switcher` 7761:7896, `Menu/Option` 7761:7914, `Menu` 7761:7939, `SearchField/Inline` 7761:7998, `AskCard` 7761:8010, `VerdictSummary` 7761:8030, **`AnswerVerdict` 7761:8037** (326 × 21) |
| `Sheet/Question/More` | 8455:36543 | Question overflow sheet (Oct 2026 section) |
| `Sheet/Answer/OwnMore` | 8455:36584 | Own answer overflow sheet |
| `Confirm/Answer/Delete` | 8455:36985 | Delete own answer confirm |
| `Toast/Post/AnswerDeleted` | 8456:37030 | Toast after delete |

---

## 2. The request model: what Reviewer A can ask for

**FIGMA: `Screen/Ask/Step 2` (7573:10506).**

There are three sections, each a title in a 20px line plus a hint in a 16px line, at x=28.

1. **"What's your main question?"** (y300). Hint: **"Ask your main question"** (y321).
   - It's a free-text box (Group 872, 334 × 174 at y351) with placeholder **"Write it bluntly here.."**.
     The counter at the bottom right reads **"15 characters remaining"** when empty and
     **"Good question!"** once satisfied (Step 2.1, 7573:10657).
   - This field is **required, minimum 15 characters**. That's in the code today as
     `MIN_QUESTION_CHARS = 15`, with a max of 1800 characters of text (`MAX_QUESTION_TEXT`; the API
     caps the body at 2000 and the rest leaves room for the "Looking for" line).
   - The first line is the question's title. Any further lines are the asker's situation, which the
     Answer flow quotes under its Step 1 title.
2. **"Are there any specifics you'd like to know?"** (y557). Hint: **"Help other buyers answer your question"** (y578).
   - There are exactly **four chips**, each 52px tall with a 20px **Plus** glyph at (16,16) and its
     label at (44,16). Layout and order:
     - Row 1 (y608): **"Experience"** (136w) · **"Pros & Cons"** (144w)
     - Row 2 (y672): **"Do you recommend this?"** (236w)
     - Row 3 (y736): **"Is this right for me?"** (192w)
   - They're **multi-select** toggles, and choosing none is allowed (FIGMA: no error state is drawn,
     and the Continue pill is the same in every variant).
   - **There is no "Rating" chip.** The code still offers a fifth "Rating" chip; PIM removed it
     this commit (§9).
   - **FIGMA (live, 2.1 + 2.3):** unselected chip = `rgba(255,255,255,0.3)` fill, radius 12,
     height 52, padding 16/8, gap 8, shadow `0 4px 4px rgba(0,0,0,0.1)`, grey Plus 20, label
     Poppins Regular 14/20 `#202020`. Selected (2.3: "Experience", "Is this right for me?") = the
     same chip with an orange (`rgba(239,88,33,0.8)`) 1px border and the Plus in success green. The
     code already draws exactly this (`AskQuestionForm.tsx`). No "required" or "optional" marker
     exists on the chips — a chip is simply on or off.
3. **"Would you like to share a photo?"** (y812). Hint: **"A photo might help other buyers answer your question"**.
   - A 120 × 120 upload tile with an "Image" glyph and **"Tap to upload"**.
   - **Not built today** (a question has no photo in the API). See §11, open question 2.

Above the sections (Group 807 at y130) sits **"Product in question:"** (12px), the product name
(16px), and a **"Change"** link at the right.

The pill **"Button/Pill — Continue"** is 358 × 56 at y757. The code posts from this step and labels
the pill "Submit", an intentional difference recorded in `AskQuestionForm.tsx`.

**OWNER RULE.** Rating is **always** required in an answer, so it is never a request option.

---

## 3. The Answer flow, step by step (FIGMA)

All steps share the review composer's header: the back arrow, the avatar, the 1px progress line,
"Step N out of 7" at (16,130), the title in 20px Medium brand orange at (16,152), the blurb at
(16,182), and the pill "Continue" at (16,756), 358 × 56. These are already implemented in
`components/qa/AnswerFlow.tsx`.

| Step | Title · blurb | Controls (verbatim) |
|---|---|---|
| 1 | **"Straight to the point"** · the blurb is the asker's situation in quotes (e.g. "“I'm out almost the whole day (10 hours)…”") | A text box with placeholder **"Write it bluntly here..."** and counter **"30 characters remaining"** (y712). In Step 1.1 the counter is hidden once satisfied |
| 2 | **"Been there, used that"** · "Tell them what it's actually like to own it." | Card **"Usage"**, prompt **"How long have you used it?"**, chips: "Less than a week", "1–4 weeks", "1–6 months", "6 months–1 year", "1 year+", "I returned it" (single select; 2a.1 shows `Chip/Selected`). Card **"Expectations"**, prompt **"Compared to what you expected?"**, chips: "Better", "About the same", "Worse" (single select), plus a text field **"Anything they should know? (optional)"** |
| 2 (alt) | **"Where's this from?"** · "Buyers trust answers more when they know the source" | Four choice rows (icon + title + 12px sub-line): **"I own it"** / "I'm using it right now"; **"I used to own it"** / "Had it before, but not anymore"; **"I returned it"** / "Tried it, then sent it back"; **"I researched it"** / "Reviews, specs, or someone else's unit". Live screenshot: Continue is **disabled** until one is chosen. **Not built** — no API field for the source. See §11, open question 1 |
| 3 | **"The good, the bad"** · "Tap what applies. It helps them see the full picture." | **"Pros"**, prompt "What's so great about this product?", suggestion chips: "Worth it!", "As described", "Feels premium", "Easy to use", "Affordable", "Good build quality", plus **"Add a pro..."**. **"Cons"**, prompt "What are the downsides worth mentioning?", suggestion chips: "Not worth it", "Hard to use", "Feels cheap", "Not as advertised", "Looks better in the photos", "Too expensive", "Flimsy", plus **"Add a con..."** (multi select) |
| 4 | **"Your verdict"** (4.1: "Your verdict!") · "Your unfiltered words. Make it count." | Choice rows: **"Yes, get it"**, **"Only on sale"**, **"Get a different variant"**, **"No, skip it"** (single select). Step 4.1 (live): the list collapses to the chosen row (white, 1px orange border, radius 16, 53 high) with **"Change"** (14px, 30% black) at the right, then a 358 × 231 white card with placeholder **"Why? (optional)"** and no counter; **Continue stays enabled** with it empty. **The "Why?" field is not built: there is no API field to store it** (§8, §10) |
| 5 | **"Is it for them?"** · "Read their situation. Does this product fit it?" | Choice rows: **"Yes, it fits what you need"**, **"It depends"**, **"No, look elsewhere"** (single select). Step 5.1 (live, It depends): the chosen row plus "Change", then a text card **"Tell them what it depends on..."** with a visible **"15 characters remaining"** counter, and **Continue disabled** — the explanation is REQUIRED (≥ 15 characters) once "It depends" is chosen. Stored in the existing `right_for_you` as "It depends: <text>" (free text, max 1000) |
| 6 | **"Rating time"** · "Last one! How would you rate it overall?" | Five 52px stars on an arc at x 49/109/169/229/289, y 370/359/354/359/370. Feedback text under them: Step 6.1 **"That bad, huh?"** (low), Step 6.2 **"Amazing product!"** (high). Already built (`StarRatingInput`, half steps) |
| 7 | **"Show, don't tell"** · "A photo of your own unit backs up your answer. Optional, but buyers trust it more." | **ONE** photo card (358 × 390): **"Tap to upload your product photo"** / "Use your own photo of the product". Link **"Skip – post without a photo"** under it; pill **"Post answer"** (disabled until a photo is added; Skip posts without one). **FIGMA draws a single slot: answers take ONE photo.** The API accepts up to 4, but the frontend follows Figma (`max={1}`, already built). Do not copy the review composer's four |
| Done | **"All done!"** · **"Answer posted!"** · "Thanks for being blunt. The asker gets notified right away." | **"You answered this question:"** (blue 12px) over a white card: the *asker's* Author row (avatar, name, age, trust stage, Honesty Score, overflow), the **question** in italic quotes, and votes + comments. **"Your latest stats:"** over the three figures (real data, `LatestStats`). Pill **"View the question"** |

---

## 4. Validation contract

Answer steps map onto request types like this:

| Requested chip (Ask Step 2) | Answer step | API field (today) |
|---|---|---|
| *(always)* | 1 "Straight to the point" | `body` |
| Experience | 2 "Been there, used that" | `experience` (one line built by `experienceLine()`) |
| Pros & Cons | 3 "The good, the bad" | `good`, `bad` |
| Do you recommend this? | 4 "Your verdict" | `verdict` (`yes` / `on_sale` / `other_variant` / `no`; `recommend` is derived) |
| Is this right for me? | 5 "Is it for them?" | `right_for_you` |
| *(always, OWNER RULE)* | 6 "Rating time" | `rating` |
| *(never required)* | 7 "Show, don't tell" | `photo_urls` |

**FIGMA.** All seven steps are always in the flow ("Step N out of 7" in every frame). Steps that
weren't requested are **shown and skippable**. They are not hidden.

**OWNER (2026-10-06).** The asker's "Looking for" chips ARE the question's requirements, exactly;
nothing else becomes required because of the question. The step counter says so beside
"Step N out of 7": **"Required: they asked about this"** on a picked specific, **"Required"** on
the words and the rating (every answer), and **"Added information"** on every other step, which
never blocks Continue or posting. Example, "How long does a single bottle of this cleanser
lasts?" (Looking for: Experience, Pros & Cons, Do you recommend this?): steps 2, 3 and 4 are
required by the question; 5 (Is it for them?) and 7 (Photo) are Added information.

### The matrix

| Field | Control | Required? | Satisfied when (PROPOSED where Figma is silent) | Error copy (PROPOSED) |
|---|---|---|---|---|
| Words | text box | **ALWAYS** | ≥ 30 characters (FIGMA counter "30 characters remaining") | "Write at least 30 characters first." |
| Rating | 5 stars, half steps | **ALWAYS (OWNER RULE)** | 0.5–5 in 0.5 steps | "Give it a star rating. Every answer needs one." |
| Experience | Usage chip + Expectations chip + note | **if requested** | Usage chosen **and** Expectations chosen. The note is optional (FIGMA "(optional)") | "They asked about your experience. Say how long you've used it." / "… Say how it compared to what you expected." |
| Pros & Cons | phrase pickers | **if requested** | ≥ 1 pro **and** ≥ 1 con, ignoring blank lines (same rule as the review composer) | "They asked for pros and cons. Add at least one of each." |
| Do you recommend this? | verdict rows | **if requested** | one verdict chosen. "Why? (optional)" stays optional (FIGMA) | "They asked whether you recommend it. Pick a verdict." |
| Is this right for me? | fit rows | **if requested** | one fit chosen | "They asked whether it's right for them. Pick an answer." |
| Photo | photo card | **never** | — | — |

**FIGMA (live, resolved):** when the fit is **"It depends"**, Step 5.1 shows "15 characters
remaining" on "Tell them what it depends on..." with Continue **disabled**, so the explanation is
**required, ≥ 15 characters, whether or not the asker requested the fit**. Step 4.1's "Why?" says
"(optional)", has no counter and leaves Continue enabled: it stays optional.

| Field | Control | Required? | Satisfied when | Error copy |
|---|---|---|---|---|
| It depends — explanation | text card under the chosen fit | **when "It depends" is chosen** (FIGMA 5.1) | ≥ 15 characters | "Tell them what it depends on (15 characters at least)." |

### Where it's enforced

- **Frontend (PIM, this commit):** `components/qa/structured-question-model.ts` implements the
  matrix (`requiredSteps`, `answerStepBlocker`, `firstUnmetStep`). `AnswerFlow` takes `requested`,
  so Continue is blocked with the reason in the existing `ComposerActions` hint. Posting, including
  Skip on the photo step, re-checks every step and jumps back to the first unmet one.
- **Backend (RESEARCH, DONE in 4284300):** `POST /questions/{id}/answers` enforces rating
  (`answer_rating_required`) and each requested part (`answer_part_required` with `parts`). The
  "It depends" 15-character rule is enforced in the frontend only (the server accepts any
  non-empty `right_for_you`).

---

## 5. Drafts, editing, reload (current behaviour; FIGMA draws none of it)

- **Ask:** the composer holds state in memory only. Leaving the page loses it. There's no Ask
  draft in Figma, so don't build one.
- **Answer:** `AnswerFlow` holds the draft in memory only (`useState(EMPTY_DRAFT)`). There's no
  answer draft in Figma either, so don't build one. A reload starts over.
- **Editing a posted answer:** members can't (only a store edits its own answer: `Overlay/Store/EditAnswer`
  8202:22530, shown as "· Edited"). `Sheet/Answer/OwnMore` (8455:36584) and `Confirm/Answer/Delete`
  (8455:36985) cover deleting your own answer, which is existing behaviour.
- **Success:** `Screen/Answer/Done` (§3). FIGMA's card quotes the **question** (with the asker's
  Author row), not the answer. Use `ReviewQuoteCard` (`components/reviews/ReviewQuoteCard.tsx`,
  Figma 7702:7587) with the question's text and asker. No product image.

---

## 6. Question detail and answer cards (FIGMA `Screen/Question` 7731:15601)

- **The question:** a 20px avatar, the handle and "asked 3d ago" (y20). The title is 20px over 54px
  at y54; the situation sits at y122; Reactions are at y178.
- **Requested specifics on the question:** **the current frames draw none** (re-checked live: the
  question block 7731:15647 is avatar/handle/age, title, situation and Reactions only; no "Looking
  for" or request tag exists anywhere on Page 1 — the only "Requirements" frames are the trust-stage
  tiles). RESEARCH's `LookingFor` (f46edbf: "Looking for:" 12px Light + 10px `#d9d9d9` chips,
  radius 4, Rating never shown, nothing for a legacy question) is the smallest compatible
  treatment and is kept. It is an implementation choice, **not** a Figma frame (§11, open question 3).
- **Answer card** (best answer `BestAnswer` 7731:15656, 358 wide, 16px in; other answers `AnswerRow` 7731:15718):
  1. `Author` (the shared `AuthorHeader`, already used by the question page). It shows trust stage
     and Honesty Score, "Seller · ✓ Claimed" for a store, and "· Edited".
  2. **`AnswerVerdict` row** (7761:8037, 326 × 21): the left label is a 16px icon plus the verdict
     text ("Yes, get it" / "No, skip it" …), a flexible spacer, and the right is **Stars** 88 × 16.
     **The rating sits here, at the right end of the verdict row.** If there's a rating but no
     verdict, show the stars alone at the right. If there's neither (legacy answer), leave the row out.
  3. The answer text: 14px, starting 35px under the verdict row.
  4. `Details` (best answer expanded, others behind "Toggle/ShowFull" / "Toggle/ShowLess"), with
     sections in this order, each a 12px label over its values:
     - **"Experience"**: lines like "Used 6 months–1 year", "Better than expected"
     - **"Pros & Cons"**: pro lines with a check, con lines with an X ("Worth it!", "Easy to use", "As described", "Too expensive")
     - **"Is it for them?"**: the fit with its icon ("It depends"), then the explanation text under it
     - **Photos**: 64 × 64 tiles, 8px apart. **The answer's own uploads only. Never the product image.**
  5. The `ActionBar` (vote, Reply, Share) with **"Best"** (Medal 16 plus "Best") at the right of the best answer.
- **Missing parts:** an unrequested, unanswered part is **left out**, with no "Not answered"
  placeholder (FIGMA draws none).
- **Thread view** (`?thread=`): its "Thread started from" card shows the answer's author and text.
  Structured parts aren't drawn there (FIGMA 7735:8031 has text only).

Already implemented: `components/qa/QuestionThread.tsx` (`AnswerCard`, `Details`) reads
`answer.parts` from the API. Check that it follows the order above and puts the stars in the
verdict row.

---

## 7. Legacy questions and answers

- **A legacy question (free-form, no "Looking for:" line)** displays exactly as written.
  `splitQuestionBody()` returns `requirements: []`, so the Answer flow requires only words and
  rating. **Don't migrate or rewrite old bodies.**
- **A legacy "Looking for: …, Rating" line** still parses (`QUESTION_REQUIREMENTS` keeps "Rating").
  It maps to the rating step, which is required anyway.
- **A legacy answer (no structured block)** comes back from `answer_parts.parse` as text only.
  Show its text with no verdict row and no Details. Never invent a rating for it.
- **The Verdict Summary** (`AnswerSummary` 7731:15613, "Verdict Summary" · "from N answers") must
  count only answers that have a verdict / rating. That's the backend aggregate's job (RESEARCH).

---

## 8. ENGINEERING CONTRACT (proposed by PIM; the rating/parts half is IMPLEMENTED by RESEARCH in 4284300)

**Verdict "Why?" — IMPLEMENTED by RESEARCH (36492f7):** `AnswerCreate.verdict_reason: str | None`
(≤ 1000, no links), stored as a `Verdict reason:` line after `Recommends it:`, returned as
`parts.verdict_reason`. Never required.

Keep the current storage (no migration needed). The question's specifics stay on its last
"Looking for:" line, and an answer's parts stay as its labelled trailing block
(`backend/app/services/answer_parts.py`). Add explicit fields on the API surface:

```text
QuestionOut / QuestionDetailOut
  requested_parts: ("experience" | "pros_cons" | "verdict" | "fit")[]   # derived from requirements_of(body);
                                                                      # "Rating" in a legacy line is dropped
                                                                      # here (always required anyway)
QuestionCreate
  body: str                                  # unchanged
  requested_parts?: same enum[]              # optional; if sent, the server writes the "Looking for:" line
                                             # itself (the client may keep composing it — both must agree)

AnswerCreate   (POST /questions/{id}/answers)
  body: str                                  # ≥ 30 chars after trim (today: "has words")
  rating: Decimal                            # REQUIRED (0.5–5, half steps)  ← change: was optional
  experience, good, bad, verdict, right_for_you, photo_urls   # unchanged shapes
  # Server validation against requested_parts:
  #   experience → experience non-empty
  #   pros_cons  → good non-empty AND bad non-empty
  #   verdict    → verdict non-null
  #   fit        → right_for_you non-empty
  # 422 { code: "answer_part_required", parts: ["experience", ...] }   # names every missing part
  # 422 { code: "answer_rating_required" }                             # rating missing

AnswerOut.parts   (exists)  — keep; the UI reads experience/good/bad/verdict/right_for_you/rating/photo_urls
```

Naming follows the repo's existing keys (`experience`, `good`, `bad`, `verdict`, `right_for_you`,
`rating`, `photo_urls`). The requested-part enum uses the answer step ids from
`structured-question-model.ts` (`experience`, `pros_cons`, `verdict`, `fit`).

The frontend maps request chips to parts with `STEP_FOR_REQUIREMENT`. When the API sends
`requested_parts`, `AnswerFlow` should take it in place of parsing the body. That's a one-line
change in `app/questions/[id]/answer/page.tsx`.

Error copy: the client already blocks per step. For a server 422, show `detail` in the
`ComposerActions` error slot (existing) and jump to the first missing part's step
(`ANSWER_STEPS.indexOf(...)`).

---

## 9. What PIM implemented in this commit (frontend only)

- `components/qa/structured-question-model.ts` (new): `ASKABLE_REQUIREMENTS` (Figma's four),
  `ANSWER_STEPS` (Figma's seven), `STEP_FOR_REQUIREMENT`, `requiredSteps`, `answerStepBlocker`,
  `firstUnmetStep`. Tests are in `tests/frontend/structured-question-model.test.mjs` (9), covering
  the owner example (Experience + Verdict asked means rating + experience + verdict are required),
  rating always being required, unrequested steps never blocking, and legacy bodies.
- `components/qa/AnswerFlow.tsx`: a new `requested` prop. Continue is blocked by the model with the
  reason in the existing hint. Submit and Skip are guarded and jump to the first unmet step. The
  error clears on the next edit.
- `app/questions/[id]/answer/page.tsx`: passes `requirements` from `splitQuestionBody`.
- `components/qa/AskQuestionForm.tsx`: the chips are now `ASKABLE_REQUIREMENTS` (the "Rating" chip
  is gone), and the hint copy is Figma's "Help other buyers answer your question".

The UI stays honest even before the backend change: a client that skips the UI (the API directly)
can still post an answer without a rating until §8 lands.

---

## 10. Remaining frontend work (PIM owns the frontend from 2026-10-05 afternoon)

1. ~~Answer Step 4.1 "Why? (optional)"~~ **DONE:** RESEARCH added `verdict_reason` (36492f7);
   PIM draws the field under the folded verdict (optional, no counter) and the answer card shows
   it as a "Why?" section leading the Details (no Figma slot exists for it there).
2. ~~Answer Step 5.1 "Tell them what it depends on..."~~ **DONE (PIM push 2):** required ≥ 15
   characters whenever "It depends" is chosen; `right_for_you` = "It depends: <text>"
   (`fitValue` / `splitFit` in `answer-flow-model.ts`); the answer card shows the fit, then the
   reason under it.
3. ~~Steps 4.1 / 5.1 folded row~~ **DONE (PIM push 2):** the chosen choice folds to one row with
   "Change"; Step 4's title becomes "Your verdict!" once chosen.
4. Answer Step 7: **one photo** (FIGMA single slot) — already `max={1}`. Do NOT raise it to 4.
5. ~~Done card~~ **DONE (PIM push 2):** `ReviewQuoteCard` quoting the question with the asker's
   Author row (initial avatar: the API sends no asker avatar), the question's real up-votes and
   reply count.
5. The answer card: check the stars-in-the-verdict-row and section order (§6) against `QuestionThread.tsx`.
6. The step rail: optionally mark requested steps. **There's no Figma design for a marker, so don't
   add one** unless the owner asks.

Reuse: `AuthorHeader`, `ReviewQuoteCard`, `ComposerActions` (hint/error), `StarRatingInput`,
`ReviewPhotosField`, the shared field states (`components/ui/field-styles.ts`), and `BluntlyTextarea`.

Files likely affected: `backend/app/schemas/qa.py`, `backend/app/services/qa_service.py`,
`backend/app/services/answer_parts.py`, `docs/openapi.json`, `lib/api-types.d.ts`, `lib/qa.ts`,
`components/qa/AnswerFlow.tsx`, `components/qa/answer-flow-model.ts`,
`components/qa/QuestionThread.tsx`, `app/questions/[id]/answer/page.tsx`,
`app/questions/[id]/page.tsx`, `tests/frontend/answer-flow-model.test.mjs`, and backend Q&A tests.

---

## 11. Open questions (genuine Figma ambiguities: ask PIM or the owner, don't guess)

1. **Step 2a vs 2b.** (Still open after the live check.) Both are "Step 2 out of 7". 2a ("Been there, used that": usage +
   expectations) and 2b ("Where's this from?": I own it / I used to own it / I returned it /
   I researched it) are drawn side by side with no connector in the metadata. The likely reading is
   that 2b is a source question that precedes or replaces 2a (2a only makes sense for an owner), but
   Figma doesn't say. The current build has 2a only. **Keep 2a only** until the owner answers.
2. **The question photo** ("Would you like to share a photo?" on Ask Step 2). Figma draws it, but
   the API has no question photo. That's a RESEARCH/owner decision. It needs storage, and the same
   rule applies: a question photo is the asker's own upload, never a product image.
3. **Showing the requested specifics** on the question and list cards. The current frames draw
   none. Keep RESEARCH's `LookingFor` row (f46edbf) unless the owner removes it.
4. ~~The "It depends" explanation~~ — **resolved live**: required, ≥ 15 characters (Continue is
   disabled in 5.1).

## 12. Responsive

FIGMA: mobile only (390). Desktop and tablet keep the current composer layout
(`ComposerLayout`: a centred column with the step rail at `md+`), which applies to Ask and Answer
alike. Don't invent desktop-specific structure. Long text wraps (`overflow-wrap:anywhere` on
user text, never `break-all`). Chips wrap onto new lines; rows never scroll sideways.

## 13. Loading / empty / error

- Ask Step 1: "N result found" (sic: "2 result found" in the frame) over the results, and
  **"Can't find product? Paste Shopee link here"** under them. Already built.
- Answer submit errors: the existing `ComposerActions` error slot. Network: "Couldn't reach the
  server. Try again."
- Question detail, no answers: the existing "No answers yet" / "No other answers yet". FIGMA has
  no dedicated frame.
- Skeletons: use the existing shared skeleton (`components/ui/Skeleton.tsx`) and don't add new shapes.

## 14. Owner rules that still apply

- **No product image as user media.** No question or answer surface ever shows the product's
  canonical image as an asker's or answerer's photo. The product image appears only as product
  context (the ProductStrip / ProductPanel thumbnail).
- **Seller sign-up and 3D:** deferred. Don't build them.

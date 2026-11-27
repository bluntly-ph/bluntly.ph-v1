/**
 * Structured questions and answers — what an asker can request, and what an
 * answer must then contain. Pure; tested in
 * tests/frontend/structured-question-model.test.mjs. The full contract is
 * docs/STRUCTURED_QUESTIONS_FIGMA_SPEC.md.
 *
 * FIGMA (read 2026-10-05, file lso4Ri4hDaZxvCebhUqlY5):
 *  - "Screen/Ask/Step 2" (7573:10506, variants 2.1–2.3) — "Are there any
 *    specifics you'd like to know?" offers exactly four chips, in this order:
 *    Experience · Pros & Cons · Do you recommend this? · Is this right for me?
 *  - "Screen/Answer/Step 1…7" (7573:8215 … 7573:9133) — seven steps, every one
 *    numbered "Step N out of 7" whatever was asked: the words, Experience
 *    ("Been there, used that"), Pros & Cons ("The good, the bad"), the verdict
 *    ("Your verdict"), the fit ("Is it for them?"), the rating ("Rating
 *    time") and the photo ("Show, don't tell").
 *
 * OWNER RULES (2026-10-05): a requested specific is REQUIRED in the answer;
 * the RATING is ALWAYS required; the photo stays optional (the frame's "Skip –
 * post without a photo"). A specific that was not requested keeps its step and
 * stays optional ("Added information") — the frames never drop a step.
 *
 * Legacy: questions store their request as a last "Looking for: …" line
 * (ask-question-model). "Rating" may appear there on older questions; it is
 * read, but no longer offered, because a rating is required regardless.
 */
import { counterIsSatisfied } from "../reviews/composer-gate-model.ts";
import { FIT_DEPENDS, fitDetailRemaining, type AnswerDraft } from "./answer-flow-model.ts";
import type { QuestionRequirement } from "./ask-question-model.ts";

/** The chips "Screen/Ask/Step 2" offers, in its order. */
export const ASKABLE_REQUIREMENTS = [
  "Experience",
  "Pros & Cons",
  "Do you recommend this?",
  "Is this right for me?",
] as const satisfies readonly QuestionRequirement[];

/** The answer flow's steps, in the frames' order (Step 1…7). */
export const ANSWER_STEPS = ["words", "experience", "pros_cons", "verdict", "fit", "rating", "photo"] as const;
export type AnswerStep = (typeof ANSWER_STEPS)[number];

/** Which answer step carries each requestable specific. */
export const STEP_FOR_REQUIREMENT: Record<QuestionRequirement, AnswerStep> = {
  Experience: "experience",
  "Pros & Cons": "pros_cons",
  "Do you recommend this?": "verdict",
  "Is this right for me?": "fit",
  Rating: "rating",
};

/** Steps an answer must complete for these requested specifics. */
export function requiredSteps(requested: readonly QuestionRequirement[]): Set<AnswerStep> {
  const out = new Set<AnswerStep>(["words", "rating"]);
  for (const r of requested) out.add(STEP_FOR_REQUIREMENT[r]);
  return out;
}

function hasLine(value: string): boolean {
  return value.split("\n").some((l) => l.trim().length > 0);
}

/**
 * Why `step` cannot be left yet, or null. Only required steps can block; an
 * optional step can always be passed with Continue, as today.
 *
 * Satisfaction rules (PROPOSED where the frames are silent — see the spec §4):
 *  words       30 characters ("30 characters remaining", Answer Step 1)
 *  experience  a "How long have you used it?" chip and a "Compared to what
 *              you expected?" chip; the note is "(optional)" in the frame
 *  pros_cons   at least one pro and one con (the review composer's rule)
 *  verdict     one "Your verdict" choice; "Why? (optional)" stays optional
 *  fit         one "Is it for them?" choice; and, whether or not it was
 *              requested, "It depends" needs its 15-character reason
 *              (FIGMA Step 5.1 greys Continue until then)
 *  rating      a star rating, half steps, 0.5–5
 *  photo       never required
 */
export function answerStepBlocker(
  step: AnswerStep,
  draft: Pick<AnswerDraft, "text" | "usage" | "expectation" | "pros" | "cons" | "verdict" | "fit" | "rating"> &
    Partial<Pick<AnswerDraft, "fitDetail">>,
  requested: readonly QuestionRequirement[],
): string | null {
  if (step === "fit" && draft.fit === FIT_DEPENDS && fitDetailRemaining(draft.fitDetail ?? "") > 0) {
    return "Tell them what it depends on (15 characters at least).";
  }
  if (!requiredSteps(requested).has(step)) return null;
  switch (step) {
    case "words":
      return counterIsSatisfied(draft.text) ? null : "Write at least 30 characters first.";
    case "experience":
      if (!draft.usage) return "They asked about your experience. Say how long you've used it.";
      return draft.expectation ? null : "They asked about your experience. Say how it compared to what you expected.";
    case "pros_cons":
      return hasLine(draft.pros) && hasLine(draft.cons)
        ? null
        : "They asked for pros and cons. Add at least one of each.";
    case "verdict":
      return draft.verdict ? null : "They asked whether you recommend it. Pick a verdict.";
    case "fit":
      return draft.fit ? null : "They asked whether it's right for them. Pick an answer.";
    case "rating":
      return draft.rating !== null && draft.rating > 0 ? null : "Give it a star rating. Every answer needs one.";
    case "photo":
      return null;
  }
}

/** The first required step still unmet, for a submit guard; null when ready. */
export function firstUnmetStep(
  draft: Parameters<typeof answerStepBlocker>[1],
  requested: readonly QuestionRequirement[],
): { step: AnswerStep; index: number; reason: string } | null {
  for (let i = 0; i < ANSWER_STEPS.length; i++) {
    const reason = answerStepBlocker(ANSWER_STEPS[i], draft, requested);
    if (reason) return { step: ANSWER_STEPS[i], index: i, reason };
  }
  return null;
}

/** What the counter calls a step the asker did not pick (owner 2026-10-06). */
export const ADDED_INFORMATION = "Added information";

/**
 * What the step counter says beside "Step N out of 7" (the step's required
 * state, in words - no new marker, the frames draw none): "Required" for the
 * words and the rating, "Required: they asked about this" for a specific the
 * asker picked under "Looking for", and "Added information" for every other
 * step - it stays in the flow, can be skipped and never blocks posting.
 */
export function stepRequirementNote(step: AnswerStep, requested: readonly QuestionRequirement[]): string {
  if (step === "words" || step === "rating") return "Required";
  const asked = requested.some((r) => STEP_FOR_REQUIREMENT[r] === step);
  return asked ? "Required: they asked about this" : ADDED_INFORMATION;
}

/** The answer parts the API names in a 422 (answer_rating_required / answer_part_required). */
const STEP_FOR_PART: Record<string, AnswerStep> = {
  rating: "rating",
  experience: "experience",
  pros_cons: "pros_cons",
  verdict: "verdict",
  fit: "fit",
};

/** The step to return to for the first part a server refusal names, or null. */
export function stepForServerParts(parts: unknown): number | null {
  if (!Array.isArray(parts)) return null;
  for (const p of parts) {
    const step = typeof p === "string" ? STEP_FOR_PART[p] : undefined;
    if (step) return ANSWER_STEPS.indexOf(step);
  }
  return null;
}

/**
 * The requested specifics a question shows as "Looking for:" chips: the
 * askable ones only, in the Ask picker's order. A legacy "Rating" request is
 * left out (every answer carries a rating anyway); a legacy free-form
 * question shows none.
 */
export function shownRequests(requested: readonly QuestionRequirement[]): QuestionRequirement[] {
  return ASKABLE_REQUIREMENTS.filter((r) => requested.includes(r));
}

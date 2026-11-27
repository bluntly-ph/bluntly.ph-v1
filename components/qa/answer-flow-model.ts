/**
 * The answer flow's choices and how they become an answer's parts (Figma
 * "Answer Page - Step 1..7", 7573:8215-7573:9133). Pure; tested in
 * tests/frontend/answer-flow-model.test.mjs.
 */

export const USAGE = ["Less than a week", "1–4 weeks", "1–6 months", "6 months–1 year", "1 year+", "I returned it"] as const;
export const EXPECTATIONS = ["Better", "About the same", "Worse"] as const;

/** Step 4 "Your verdict", in the frame's order; values are the API's. */
export const VERDICT_CHOICES = [
  { value: "yes", label: "Yes, get it" },
  { value: "on_sale", label: "Only on sale" },
  { value: "other_variant", label: "Get a different variant" },
  { value: "no", label: "No, skip it" },
] as const;
export type VerdictValue = (typeof VERDICT_CHOICES)[number]["value"];

/** Step 5 "Is it for them?". */
export const FIT_CHOICES = ["Yes, it fits what you need", "It depends", "No, look elsewhere"] as const;

/**
 * Step 5.1 (7573:8753): choosing "It depends" opens "Tell them what it depends
 * on..." with "15 characters remaining" and Continue greyed, so the reason is
 * required. It is stored in the existing free-text `right_for_you` as
 * "It depends: <reason>" and read back by `splitFit`.
 */
export const FIT_DEPENDS = "It depends";
export const MIN_FIT_DETAIL = 15;
const FIT_DEPENDS_PREFIX = `${FIT_DEPENDS}: `;

/** "It depends: if you commute" → the choice and the reason under it. */
export function splitFit(value: string | null | undefined): { choice: string | null; detail: string | null } {
  const v = (value ?? "").trim();
  if (!v) return { choice: null, detail: null };
  if (v.startsWith(FIT_DEPENDS_PREFIX)) {
    const detail = v.slice(FIT_DEPENDS_PREFIX.length).trim();
    return { choice: FIT_DEPENDS, detail: detail || null };
  }
  return { choice: v, detail: null };
}

/** Characters still needed in the "It depends" reason (0 once enough). */
export function fitDetailRemaining(detail: string): number {
  return Math.max(0, MIN_FIT_DETAIL - detail.trim().length);
}

export type AnswerDraft = {
  text: string;
  usage: string | null;
  expectation: string | null;
  note: string;
  pros: string;
  cons: string;
  verdict: VerdictValue | null;
  /** Step 4.1 "Why? (optional)" (verdict_reason); sent only with a verdict. */
  verdictReason: string;
  fit: string | null;
  /** The reason under "It depends" (Step 5.1); ignored for any other fit. */
  fitDetail: string;
  rating: number | null;
  photoUrl: string | null;
};

export const EMPTY_DRAFT: AnswerDraft = {
  text: "",
  usage: null,
  expectation: null,
  note: "",
  pros: "",
  cons: "",
  verdict: null,
  verdictReason: "",
  fit: null,
  fitDetail: "",
  rating: null,
  photoUrl: null,
};

function lines(value: string): string[] {
  return value
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

/** "Used it 1–6 months · About the same as expected · The clip is loose." */
export function experienceLine(d: Pick<AnswerDraft, "usage" | "expectation" | "note">): string | null {
  const parts = [
    d.usage ? (d.usage === "I returned it" ? "Returned it" : `Used it ${d.usage.toLowerCase()}`) : null,
    d.expectation ? (d.expectation === "About the same" ? "About as expected" : `${d.expectation} than expected`) : null,
    d.note.trim() || null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/** What `right_for_you` stores: the fit, with the reason after "It depends". */
export function fitValue(d: Pick<AnswerDraft, "fit" | "fitDetail">): string | null {
  if (!d.fit) return null;
  const detail = d.fitDetail.split(/\s+/).filter(Boolean).join(" ");
  return d.fit === FIT_DEPENDS && detail ? `${FIT_DEPENDS_PREFIX}${detail}` : d.fit;
}

/** The POST /questions/{id}/answers body. */
export function answerPayload(d: AnswerDraft): Record<string, unknown> {
  const good = lines(d.pros).join("; ");
  const bad = lines(d.cons).join("; ");
  return {
    body: d.text.trim(),
    experience: experienceLine(d),
    good: good || null,
    bad: bad || null,
    verdict: d.verdict,
    verdict_reason: d.verdict ? d.verdictReason.trim() || null : null,
    right_for_you: fitValue(d),
    rating: d.rating === null || d.rating <= 0 ? null : String(d.rating),
    photo_urls: d.photoUrl ? [d.photoUrl] : [],
  };
}

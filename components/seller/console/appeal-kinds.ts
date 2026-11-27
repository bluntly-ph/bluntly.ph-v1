/**
 * What a store says is wrong with a review (MQA-041, backend 0090). The admin's
 * check follows from it, so each kind names its own next step. Pure, so
 * tests/frontend can run it.
 */

export type AppealKind = "never_ordered" | "untrue" | "breaks_rules";

export const APPEAL_KINDS: { kind: AppealKind; label: string; hint: string; prompt: string; placeholder: string; check: string }[] = [
  {
    kind: "never_ordered",
    label: "The buyer never ordered",
    hint: "No order from this account in your shop.",
    prompt: "Why do you think they never ordered?",
    placeholder: "e.g. No order from this account in our shop that week.",
    check: "If it looks fake, the reviewer is asked to prove the purchase.",
  },
  {
    kind: "untrue",
    label: "The details are untrue",
    hint: "A real buyer, but what they wrote didn't happen.",
    prompt: "What is untrue, and how do you know?",
    placeholder: "e.g. They say it arrived late, but the courier delivered it in 2 days.",
    check: "The reviewer is asked for evidence of what they wrote.",
  },
  {
    kind: "breaks_rules",
    label: "It breaks the rules",
    hint: "Insults, personal details, spam or off-topic.",
    prompt: "Which rule does it break?",
    placeholder: "e.g. It posts our staff member's phone number.",
    check: "An admin checks it against the Community Guidelines.",
  },
];

/** The short label an admin sees for a flag ("Never ordered"). */
export function appealKindLabel(kind: string | null | undefined): string {
  return { never_ordered: "Never ordered", untrue: "Untrue details", breaks_rules: "Breaks the rules" }[kind ?? "never_ordered"] ?? "Never ordered";
}

export function appealKind(kind: AppealKind) {
  return APPEAL_KINDS.find((k) => k.kind === kind) ?? APPEAL_KINDS[0];
}

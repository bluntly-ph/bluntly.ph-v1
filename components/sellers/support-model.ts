/**
 * Seller support requests: the labels the UI shows for the API's values.
 * Pure (tested in tests/frontend/support-model.test.mjs).
 */

export const SUPPORT_CATEGORIES = [
  { value: "report_review", label: "Report a review" },
  { value: "takedown_investigation", label: "Ask for a takedown investigation" },
  { value: "fake_review_dispute", label: "Dispute a review I believe is fake" },
  { value: "account_claim", label: "My account or store claim" },
  { value: "listing_product", label: "A listing or product" },
  { value: "general", label: "General support" },
] as const;

export const SUPPORT_STATUS_LABEL: Record<string, string> = {
  open: "Open",
  in_review: "In review",
  // MQA-022/024: the seller's next move, in the words their Messages thread uses.
  waiting_for_seller: "Waiting on you",
  resolved: "Resolved",
  rejected: "Rejected",
};

/** The team's word for the same status: whose turn it is, from their side. */
const STAFF_WORDS: Record<string, string> = { waiting_for_seller: "Waiting for seller" };

/** Categories the team files, not offered in the seller's form: a store change
 *  is asked for with "Request a change" (MQA-026). */
const FILED_BY_TEAM: Record<string, string> = { store_change: "A store change" };

export function categoryLabel(value: string): string {
  return SUPPORT_CATEGORIES.find((c) => c.value === value)?.label ?? FILED_BY_TEAM[value] ?? value.replace(/_/g, " ");
}

export function statusLabel(value: string, side: "seller" | "staff" = "seller"): string {
  return (side === "staff" ? STAFF_WORDS[value] : undefined) ?? SUPPORT_STATUS_LABEL[value] ?? value.replace(/_/g, " ");
}

/** A request still being handled (not resolved or rejected). */
export function isOpen(value: string): boolean {
  return value === "open" || value === "in_review" || value === "waiting_for_seller";
}

/** A request waiting on the team, not on the seller (the Support queue's work). */
export function waitingOnTeam(value: string): boolean {
  return value === "open" || value === "in_review";
}

/** Client-side mirror of the API's length rules, for an early, specific hint. */
export function validateSupportDraft(d: { subject: string; message: string }): string | null {
  if (d.subject.trim().length < 3) return "Give the request a short subject.";
  if (d.message.trim().length < 10) return "Describe the issue in at least 10 characters.";
  if (d.message.trim().length > 4000) return "Keep the message under 4,000 characters.";
  return null;
}

const APPEAL_LABEL: Record<string, string> = {
  open: "open",
  substantiation_requested: "reviewer asked for proof",
  upheld: "upheld",
  dismissed: "dismissed",
};

/** The store's "suspected fake" flag, as the dashboard names its state. */
export function appealLabel(value: string): string {
  return APPEAL_LABEL[value] ?? value.replace(/_/g, " ");
}

/**
 * What an audit row DID, when its action alone would mislead (MQA-006, MQA-008).
 * A report dismissal is audited as `approve` (the content stood), so the row read
 * "Approved a review"; a price decision is audited as approve / reject too. The
 * row's `outcome` (from its context) names the real event. Pure, for tests.
 */
export const OUTCOME_LABEL: Record<string, string> = {
  dismissed: "Dismissed a report",
  content_removed: "Removed reported content",
  content_restored: "Restored reported content",
  escalated: "Escalated a report",
  price_approved: "Approved a price",
  price_rejected: "Rejected a price",
};

/** The Activity log's sentence verb for the same events. */
export const OUTCOME_VERB: Record<string, string> = {
  dismissed: "dismissed a report on",
  content_removed: "removed, on a report,",
  content_restored: "restored, on a report,",
  escalated: "escalated to a Super Admin a report on",
  price_approved: "approved a price for",
  price_rejected: "rejected a price for",
};

export function outcomeLabel(outcome: string | null | undefined): string | null {
  return outcome ? (OUTCOME_LABEL[outcome] ?? null) : null;
}

/**
 * How an Activity log entry reads, shared by the Activity log and the
 * Overview's "Recent team activity" card (Screen/Admin/Overview v4, 8444:38818)
 * so the two never word the same action differently.
 */
import { conversationVerb } from "./activity-model.ts";
import { OUTCOME_VERB } from "./activity-outcome.ts";

/** What each action reads as, after the actor's name. */
export const VERB: Record<string, string> = {
  approve: "approved earnings on",
  reject: "rejected earnings on",
  remove: "removed",
  publish: "published",
  unpublish: "took down",
  penalize: "penalized",
  override: "overrode the decision on",
  escalate: "escalated",
  report: "reported",
  restore: "restored",
  suspend: "suspended",
  receipt_view: "viewed the proof of purchase for",
  investigation_set: "opened an investigation into",
  investigation_clear: "cleared the investigation of",
  role_grant: "gave a staff role to",
  role_revoke: "removed the staff role of",
  affiliate_link_attach: "attached an affiliate link to",
  affiliate_link_revoke: "revoked the affiliate link on",
  csv_import: "imported an affiliate report",
  payout: "marked a payout as sent",
  remittance_record: "recorded a marketplace remittance",
  honesty_fund_distribution: "distributed the Honesty Fund",
  special_routing: "routed",
  cold_start_substitution: "substituted a cold-start vote on",
  best_answer_pick: "picked a Best Answer on",
  author_delete: "deleted their own",
  alias_add: "added an alias to",
  alias_remove: "removed an alias from",
  listing_attach: "attached a listing to",
  photo_replace: "replaced the photo on",
  appeal_decision: "decided the appeal on",
  substantiation_request: "asked the reviewer to back up",
  seller_appeal: "appealed",
  track_flip: "moved the track of",
  support_request: "answered a support request on",
  store_product: "decided a product link for",
  store_release: "gave up the store",
  data_export: "exported data:",
  cashout_request: "requested a cash-out",
  qa_tester_add: "added a QA tester",
  qa_tester_remove: "removed a QA tester",
  qa_test_credit: "credited a QA test",
  product_import: "imported products from a file",
};

export const words = (s: string) => s.replaceAll("_", " ");

/**
 * "Zient approved earnings on Aula F75 Keyboard" as plain text: the actor (or
 * System), the verb for the action or its outcome, and the target's label.
 */
export function activitySentence(e: {
  actor?: string | null;
  action: string;
  outcome?: string | null;
  target_label?: string | null;
  notes?: string | null;
}): string {
  const conv = e.action === "conversation" ? conversationVerb(e.notes) : null;
  const verb = conv
    ? conv.before
    : ((e.outcome ? OUTCOME_VERB[e.outcome] : undefined) ?? VERB[e.action] ?? words(e.action));
  const target = e.target_label ?? (conv ? "a conversation" : null);
  return [e.actor ?? "System", verb, target, conv?.after || null].filter(Boolean).join(" ");
}

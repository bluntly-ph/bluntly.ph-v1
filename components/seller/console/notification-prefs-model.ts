/**
 * Screen/Seller/Settings → Notifications (Figma 8218:24151): the rows in the
 * frame's order and what each switch covers (backend notification_service.STORE_PREFS).
 * Pure, so tests/frontend can run it.
 */

export type Prefs = {
  store_reviews: boolean;
  store_reviews_low_only: boolean;
  store_questions: boolean;
  appeal_updates: boolean;
  product_links: boolean;
  /** Channels (backend 0085): every notice above also by email, and the Monday summary. */
  email: boolean;
  weekly_summary: boolean;
};

export type PrefRow = { key: keyof Prefs; title: string; sub: string };

export const PREF_ROWS: PrefRow[] = [
  { key: "store_reviews", title: "New reviews of your store", sub: "Every new review, as it's posted" },
  { key: "store_reviews_low_only", title: "Only low reviews", sub: "Just reviews of 3 stars or less" },
  { key: "store_questions", title: "New questions", sub: "Questions about your store" },
  { key: "appeal_updates", title: "Appeal updates", sub: "When an admin decides on a review you flagged" },
  { key: "product_links", title: "Product link decisions", sub: "When a moderator approves or declines a link" },
  { key: "email", title: "Also by email", sub: "Each of the notifications above, sent to your email too" },
  { key: "weekly_summary", title: "Weekly summary", sub: "Mondays by email: your rating, new reviews and what's waiting" },
];

/** A switch's state after a change. "Only low reviews" means nothing with new reviews off. */
export function withPref(prefs: Prefs, key: keyof Prefs, on: boolean): Prefs {
  const next = { ...prefs, [key]: on };
  if (key === "store_reviews" && !on) next.store_reviews_low_only = false;
  return next;
}

/** Whether a row's switch can be used. */
export function prefEnabled(prefs: Prefs, key: PrefRow["key"]): boolean {
  if (key === "store_reviews_low_only") return prefs.store_reviews;
  return true;
}

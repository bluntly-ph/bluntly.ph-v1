/**
 * The Seller Overview's pure pieces (Figma Screen/Seller/Overview 8190:20643):
 * the greeting, the "Waiting on you" list and the small formatters. Kept free
 * of React and server imports so tests/frontend can run them.
 */

type Waiting = { id: string; body: string; created_at: string; asker?: string | null };
type Row = {
  id: string;
  created_at: string;
  title?: string | null;
  excerpt?: string | null;
  overall_rating: number;
  has_store_response: boolean;
  reviewer_name?: string | null;
  reviewer?: string | null;
};
type Appeal = {
  id: string;
  status: string;
  created_at: string;
  seller_review_id: string;
  substantiation_requested_at?: string | null;
  reviewer?: { display_name?: string | null; username?: string | null } | null;
};

export type WaitingItem = {
  kind: "question" | "review" | "appeal";
  id: string;
  title: string;
  note: string;
  action: "Answer" | "Respond" | "View";
  href: string;
  at: number;
  /** A low rating still waiting for the store: drawn red, as in the frame. */
  urgent: boolean;
};

const HOUR = 3600_000;

/** "2 days ago", "20 h ago", "5 min ago". */
export function agoShort(iso: string, now: number): string {
  const ms = Math.max(0, now - new Date(iso).getTime());
  if (ms < HOUR) return `${Math.max(1, Math.round(ms / 60_000))} min ago`;
  if (ms < 24 * HOUR) return `${Math.round(ms / HOUR)} h ago`;
  const d = Math.round(ms / (24 * HOUR));
  if (d < 7) return d === 1 ? "1 day ago" : `${d} days ago`;
  const w = Math.round(d / 7);
  return w === 1 ? "1 week ago" : `${w} weeks ago`;
}

/** Good morning / afternoon / evening, in Manila. */
export function greeting(now: number): string {
  const hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone: "Asia/Manila" }).format(now));
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/** 0.86 -> "86%"; nothing to measure -> "—". */
export function pct(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "—" : `${Math.round(v * 100)}%`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09" -> "Sep". */
export function monthLabel(key: string): string {
  const m = Number(key.split("-")[1]);
  return MONTHS[m - 1] ?? key;
}

const OPEN_APPEALS = new Set(["open", "substantiation_requested"]);

/**
 * Everything waiting on the owner, oldest first: store questions without the
 * store's answer, reviews without its response, and its flags still open.
 * Respond and Answer go where the forms already live (store page, question page).
 */
export function waitingItems(
  d: { waiting_questions: Waiting[]; reviews?: Row[] | null; waiting_reviews?: Row[] | null; seller: { id: string } },
  appeals: Appeal[],
  now: number,
): WaitingItem[] {
  const items: WaitingItem[] = [];
  for (const q of d.waiting_questions) {
    items.push({
      kind: "question", id: q.id, title: q.body, action: "Answer", href: `/seller/${d.seller.id}/questions`,
      note: `Question · asked${q.asker ? ` by ${q.asker}` : ""} · ${agoShort(q.created_at, now)}`,
      at: new Date(q.created_at).getTime(), urgent: false,
    });
  }
  // waiting_reviews is oldest first over ALL reviews; `reviews` is only the newest 30
  // (an API from before it existed still gets the old behaviour).
  for (const r of d.waiting_reviews ?? d.reviews ?? []) {
    if (r.has_store_response) continue;
    const who = r.reviewer_name ?? r.reviewer ?? "a buyer";
    items.push({
      kind: "review", id: r.id, title: r.title ? `“${r.title}”` : (r.excerpt ?? "A review of your store"),
      action: "Respond", href: `/seller/${d.seller.id}/reviews?respond=${r.id}`,
      note: `${formatStars(r.overall_rating)} review by ${who} · ${agoShort(r.created_at, now)} · no response`,
      at: new Date(r.created_at).getTime(), urgent: r.overall_rating <= 2,
    });
  }
  for (const a of appeals) {
    if (!OPEN_APPEALS.has(a.status)) continue;
    const who = a.reviewer?.display_name ?? (a.reviewer?.username ? `@${a.reviewer.username}` : "a buyer");
    const asked = a.status === "substantiation_requested" && a.substantiation_requested_at;
    items.push({
      kind: "appeal", id: a.id, title: `Your appeal on ${who}’s review`, action: "View",
      href: `/seller/${d.seller.id}/appeals`,
      note: asked
        ? `${who} was asked for proof of purchase · ${agoShort(a.substantiation_requested_at as string, now)}`
        : `Waiting for an administrator · ${agoShort(a.created_at, now)}`,
      at: new Date(a.created_at).getTime(), urgent: false,
    });
  }
  return items.sort((x, y) => x.at - y.at);
}

/**
 * How many things wait on the store in all ("See all N" in the frame), from the
 * API's totals rather than the length of the capped lists drawn.
 */
export function waitingTotal(
  d: { unanswered_questions: number; analytics?: { reviews_awaiting_response?: number | null } | null },
  appeals: Appeal[],
  shown: number,
): number {
  const open = appeals.filter((a) => OPEN_APPEALS.has(a.status)).length;
  const reviews = d.analytics?.reviews_awaiting_response;
  return reviews == null ? shown : Math.max(shown, d.unanswered_questions + reviews + open);
}

function formatStars(v: number): string {
  return `${Number.isInteger(v) ? v : v.toFixed(1)}★`;
}

export type NoteTab = "all" | "reviews" | "questions" | "appeals";

/**
 * Overlay/Store/Notifications' tabs: the notification kinds each one shows.
 * The panel asks the API for exactly these (GET /notifications?kind=…), so a
 * tab is never just the matching part of the latest page.
 */
export const TAB_KINDS: Record<Exclude<NoteTab, "all">, string[]> = {
  reviews: ["store_review_new", "seller_responded"],
  questions: ["store_question_new", "question_answered"],
  appeals: ["case_message", "seller_appeal_decided"],
};

/** Which tab a notification kind belongs to (null = All only). */
export function tabOf(kind: string): NoteTab | null {
  for (const [tab, kinds] of Object.entries(TAB_KINDS) as [Exclude<NoteTab, "all">, string[]][]) {
    if (kinds.includes(kind)) return tab;
  }
  return null;
}

/** The API query for a tab. */
export function notificationsQuery(tab: NoteTab, limit = 30): string {
  const params = new URLSearchParams({ limit: String(limit) });
  if (tab !== "all") for (const k of TAB_KINDS[tab]) params.append("kind", k);
  return `/api/bff/api/v1/notifications?${params}`;
}

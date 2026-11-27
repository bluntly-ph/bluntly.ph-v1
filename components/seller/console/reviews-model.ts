/**
 * Screen/Seller/Reviews (Figma 8196:20870) and its menus (Menu/Seller/Reviews/
 * Sort 8198:21465, Filter 8198:21475): which reviews a tab shows, in what
 * order, after the filters and the search. Pure, so tests/frontend run it.
 */

export type StoreReview = {
  id: string;
  title: string | null;
  comment: string | null;
  overall_rating: number;
  accuracy: boolean;
  order_completeness: boolean;
  would_recommend: boolean;
  customer_service?: number;
  packaging_quality?: number;
  created_at: string;
  seller_response?: string | null;
  seller_response_at?: string | null;
  /** Set when the store edited its response (0082): buyers see "Edited". */
  seller_response_edited_at?: string | null;
  reviewer: { display_name?: string | null; username?: string | null; trust_stage?: number | null } | null;
};

export type ReviewTab = "needs" | "responded" | "all";
export type ReviewSort = "oldest" | "newest" | "lowest";
export type OrderState = "as_listed" | "not_as_listed" | "missing";
export type ReviewFilters = { stars: number[]; order: OrderState[]; recommend: ("yes" | "no")[]; q: string };

export const TABS: { key: ReviewTab; label: string }[] = [
  { key: "needs", label: "Needs response" },
  { key: "responded", label: "Responded" },
  { key: "all", label: "All" },
];
/**
 * Columns per tab, as the frames draw them: Needs response 8196:20870 (the order's
 * state helps decide the reply), Responded 8201:21535 (your response and when),
 * All 8201:22036 (whether you responded).
 */
export const REVIEW_COLUMNS: Record<ReviewTab, readonly string[]> = {
  needs: ["Buyer", "Rating", "Review", "Order", "Posted", "Action"],
  responded: ["Buyer", "Rating", "Review", "Your response", "Responded", "Action"],
  all: ["Buyer", "Rating", "Review", "Your response", "Posted", "Action"],
};

export const SORTS: { key: ReviewSort; label: string }[] = [
  { key: "oldest", label: "Oldest first" },
  { key: "newest", label: "Newest first" },
  { key: "lowest", label: "Lowest rating first" },
];

/** The Order column: what the buyer said about the listing and the parcel. */
export function orderState(r: Pick<StoreReview, "accuracy" | "order_completeness">): OrderState {
  if (!r.accuracy) return "not_as_listed";
  if (!r.order_completeness) return "missing";
  return "as_listed";
}

export const ORDER_LABEL: Record<OrderState, string> = {
  as_listed: "As listed · complete",
  not_as_listed: "Not as listed",
  missing: "Items missing",
};

export function inTab(r: StoreReview, tab: ReviewTab): boolean {
  if (tab === "needs") return !r.seller_response;
  if (tab === "responded") return Boolean(r.seller_response);
  return true;
}

export function reviewerName(r: StoreReview): string {
  return r.reviewer?.display_name || (r.reviewer?.username ? `@${r.reviewer.username}` : "A buyer");
}

/** Whole stars for the filter (a 4.5 counts as 4★, as the breakdown bins it). */
export function starBin(rating: number): number {
  return Math.max(1, Math.min(5, Math.floor(rating)));
}

export function applyFilters(rows: StoreReview[], f: ReviewFilters): StoreReview[] {
  const q = f.q.trim().toLowerCase();
  return rows.filter((r) =>
    (f.stars.length === 0 || f.stars.includes(starBin(r.overall_rating))) &&
    (f.order.length === 0 || f.order.includes(orderState(r))) &&
    (f.recommend.length === 0 || f.recommend.includes(r.would_recommend ? "yes" : "no")) &&
    (!q || [r.title, r.comment, reviewerName(r)].some((t) => (t ?? "").toLowerCase().includes(q))),
  );
}

export function sortReviews(rows: StoreReview[], sort: ReviewSort): StoreReview[] {
  const t = (r: StoreReview) => new Date(r.created_at).getTime();
  return [...rows].sort((a, b) =>
    sort === "newest" ? t(b) - t(a) : sort === "lowest" ? a.overall_rating - b.overall_rating || t(a) - t(b) : t(a) - t(b),
  );
}

/** Facet counts for the Filter menu, over the tab's rows before filtering. */
export function facets(rows: StoreReview[]) {
  const stars: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  const order: Record<OrderState, number> = { as_listed: 0, not_as_listed: 0, missing: 0 };
  const recommend = { yes: 0, no: 0 };
  for (const r of rows) {
    stars[starBin(r.overall_rating)] += 1;
    order[orderState(r)] += 1;
    recommend[r.would_recommend ? "yes" : "no"] += 1;
  }
  return { stars, order, recommend };
}

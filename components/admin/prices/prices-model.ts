/**
 * The admin Prices screen's URL and API vocabulary (MQA-043 paging and total,
 * MQA-007 order, MQA-042 filters). Pure, so tests/frontend can check it.
 *
 * The URL holds every choice — `sort`, `platform`, `source`, `held`, `q`,
 * `mine`, `product`, `page`, `size` — so a filtered view survives a reload,
 * can be shared, and the back button walks the pages.
 */

import type { FilterGroup } from "../../console/list-query";

export const PRICE_KEYS = ["sort", "platform", "source", "held", "q", "mine", "product", "page", "size"];

/** Rows a page. 50 by default; 100 was the old fixed cap, kept as a choice. */
export const PRICE_PAGE_SIZES = [50, 100] as const;

export const PRICE_SORTS: [string, string][] = [
  ["oldest", "Oldest first"],
  ["newest", "Newest first"],
  ["product", "By product"],
];
/** Oldest first stays the default: a price reported earlier is checked earlier. */
export const PRICE_DEFAULT_SORT = "oldest";

export const PRICE_FILTERS: FilterGroup[] = [
  { key: "platform", title: "Marketplace", options: [["shopee", "Shopee"], ["lazada", "Lazada"], ["amazon", "Amazon"], ["other", "Other"]] },
  { key: "source", title: "Source", options: [["review", "From a review"], ["manual", "Price report"]] },
  { key: "held", title: "Why it waits", options: [["outlier", "Far outside the usual range"], ["no_baseline", "No usual range yet"]] },
  { key: "mine", title: "Your reports", options: [["hide", "Hide prices I reported"]] },
];

const ALLOWED: Record<string, readonly string[]> = {
  sort: PRICE_SORTS.map(([k]) => k),
  platform: ["shopee", "lazada", "amazon", "other"],
  source: ["review", "manual"],
  held: ["outlier", "no_baseline"],
  mine: ["hide"],
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * The API query for the list's filters (no paging): only values the API
 * accepts are forwarded, so a hand-edited URL narrows instead of a 422.
 */
export function priceFilterQuery(params: Record<string, string>): URLSearchParams {
  const out = new URLSearchParams();
  for (const [key, allowed] of Object.entries(ALLOWED)) {
    const v = params[key];
    if (v && allowed.includes(v) && !(key === "sort" && v === PRICE_DEFAULT_SORT)) out.set(key, v);
  }
  const q = (params.q ?? "").trim().slice(0, 120);
  if (q) out.set("q", q);
  if (params.product && UUID.test(params.product)) out.set("product_id", params.product);
  return out;
}

/** True when anything narrows the list (the order does not). */
export function isFiltered(params: Record<string, string>): boolean {
  const q = priceFilterQuery(params);
  q.delete("sort");
  return q.toString() !== "";
}

/** "164 prices waiting" — and, while filtered, how many of them match. */
export function waitingLine(total: number, waiting: number | null, filtered: boolean): string {
  const n = (v: number) => v.toLocaleString("en-PH");
  const all = waiting ?? total;
  const waitingText = `${n(all)} price${all === 1 ? "" : "s"} waiting`;
  if (!filtered) return `${waitingText}.`;
  return `${n(total)} of ${waitingText} match${total === 1 ? "es" : ""}.`;
}

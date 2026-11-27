/**
 * All Reviews (QA, 2026-09-29): every review that still exists, beside the
 * Review Queue, with its current votes and both Wilson figures.
 *
 * Why it exists: the Review Queue is the earnings-decision queue. Under
 * Post-Seeding, the deployed default, a review joins it only once its
 * trust-weighted votes pass the Business Rules §2 gate, so a review written a
 * minute ago is correctly absent. QA read that as "the queue does not fetch the
 * new review" and "shows an older record's Wilson". This list is the inventory
 * next to the work list.
 *
 * Pure and client-safe: types, URL parsing and labels, covered by
 * tests/frontend/all-reviews-model.test.mjs. The server fetch lives in
 * lib/moderation.ts.
 */

import { QUEUE_ROUTE } from "./review-queue-model.ts";
import { pageSize } from "../console/pagination-model.ts";

export type AllReviewsState = "published" | "taken_down" | "removed" | "deleted_by_author";
export type AllReviewsSort = "newest" | "oldest" | "wilson_desc" | "wilson_asc";
export type EarnState =
  | "none"
  | "pending"
  | "approved"
  | "rejected"
  | "monetized"
  | "honesty_fund"
  | "pending_superadmin_routing";

export type AllReviewRow = {
  id: string;
  reference: string | null;
  title: string;
  star_rating: string | number;
  verdict: "yes_absolutely" | "it_depends" | "hard_pass";
  state: AllReviewsState;
  earn_eligible_status: EarnState;
  in_review_queue: boolean;
  is_thread_root: boolean;
  helpful_votes: number;
  unhelpful_votes: number;
  /** Public Wilson: every vote equal, 45-day decay (ADR-004). */
  wilson_score: string;
  /** The §2 earnings gate: trust-weighted votes on effective n. */
  gate: {
    wilson_lower_bound: number;
    effective_total: number;
    stage2_plus_voters: number;
    passes: boolean;
  };
  open_reports: number;
  author: { id: string; username: string | null; display_name: string | null; trust_stage: number } | null;
  /** image_url: the product thumbnail (product context, never the review's photo). */
  product: { id: string; canonical_name: string | null; image_url?: string | null };
  created_at: string;
  published_at: string | null;
};

export type AllReviewsPage = {
  items: AllReviewRow[];
  total: number;
  limit: number;
  offset: number;
  earn_gate_phase: "seeding" | "post_seeding";
  /** The gate's rule, as the server applies it. */
  gate_threshold: number;
  gate_min_stage2_voters: number;
};

/** Like the queue's result: an outage never renders as "no reviews". */
export type AllReviewsResult =
  | { available: true; page: AllReviewsPage; fetchedAt: number }
  | { available: false; reason: "unauthenticated" | "unavailable"; fetchedAt: number };

export type AllReviewsFilters = {
  q: string;
  state: AllReviewsState | "";
  earn: EarnState | "";
  from: string;
  to: string;
  sort: AllReviewsSort;
  /** 1-based, and the page size the shared console Pagination offers (10 by default). */
  page: number;
  size: number;
};

export const DEFAULT_ALL_SORT: AllReviewsSort = "newest";
export const DEFAULT_ALL_SIZE = pageSize(undefined);

export const STATE_LABELS: Record<AllReviewsState, string> = {
  published: "Published",
  taken_down: "Taken down",
  removed: "Removed",
  deleted_by_author: "Deleted by author",
};

export const EARN_LABELS: Record<EarnState, string> = {
  none: "Not queued yet",
  pending: "Awaiting decision",
  approved: "Approved",
  rejected: "Rejected",
  monetized: "Link attached",
  honesty_fund: "Honesty Fund",
  pending_superadmin_routing: "Awaiting Super Admin routing",
};

export const SORT_LABELS: Record<AllReviewsSort, string> = {
  newest: "Newest",
  oldest: "Oldest",
  wilson_desc: "Wilson: high to low",
  wilson_asc: "Wilson: low to high",
};

const DAY = /^\d{4}-\d{2}-\d{2}$/;

function isKey<T extends string>(value: string, keys: Record<T, string>): value is T {
  return Object.prototype.hasOwnProperty.call(keys, value);
}

/**
 * The tab's filters from the page URL. Prefixed (`aq`, `astate`…) so they
 * never collide with the Review Queue's own `q`, `sort` and `offset`. Anything
 * outside the vocabulary is dropped, as the queue does, rather than put a 422
 * on an administrator's screen.
 */
export function parseAllReviewsFilters(params: URLSearchParams): AllReviewsFilters {
  const get = (key: string) => (params.get(key) ?? "").trim();
  const state = get("astate");
  const earn = get("aearn");
  const sort = get("asort");
  const from = get("afrom");
  const to = get("ato");
  const page = Number.parseInt(get("apage"), 10);
  return {
    q: get("aq").slice(0, 200),
    state: isKey(state, STATE_LABELS) ? state : "",
    earn: isKey(earn, EARN_LABELS) ? earn : "",
    from: DAY.test(from) ? from : "",
    to: DAY.test(to) ? to : "",
    sort: isKey(sort, SORT_LABELS) ? sort : DEFAULT_ALL_SORT,
    page: Number.isFinite(page) && page > 1 ? page : 1,
    size: pageSize(get("asize")),
  };
}

/** The API query for `GET /admin/reviews`. */
export function allReviewsApiQuery(filters: AllReviewsFilters): string {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.state) params.set("state", filters.state);
  if (filters.earn) params.set("earn", filters.earn);
  if (filters.from) params.set("created_from", filters.from);
  if (filters.to) params.set("created_to", filters.to);
  params.set("sort", filters.sort);
  params.set("limit", String(filters.size));
  params.set("offset", String((filters.page - 1) * filters.size));
  return params.toString();
}

/** A link to the tab with some filters changed; any change but paging starts at page one. */
export function allReviewsHref(
  filters: AllReviewsFilters,
  changes: Partial<AllReviewsFilters> = {},
): string {
  const next = { ...filters, ...changes, page: "page" in changes ? (changes.page ?? 1) : 1 };
  const params = new URLSearchParams({ tab: "all" });
  if (next.q) params.set("aq", next.q);
  if (next.state) params.set("astate", next.state);
  if (next.earn) params.set("aearn", next.earn);
  if (next.from) params.set("afrom", next.from);
  if (next.to) params.set("ato", next.to);
  if (next.sort !== DEFAULT_ALL_SORT) params.set("asort", next.sort);
  if (next.size !== DEFAULT_ALL_SIZE) params.set("asize", String(next.size));
  if (next.page > 1) params.set("apage", String(next.page));
  return `${QUEUE_ROUTE}?${params.toString()}`;
}

/** The URL parameters the pager keeps (everything but the page and its size). */
export function allReviewsQuery(filters: AllReviewsFilters): Record<string, string> {
  const params = new URL(allReviewsHref(filters, { page: 1 }), "http://x").searchParams;
  params.delete("asize");
  return Object.fromEntries(params.entries());
}

/** How many filter-menu settings are on: the dot on the Filter button. */
export function activeFilterCount(filters: AllReviewsFilters): number {
  return [filters.state, filters.earn, filters.from || filters.to].filter(Boolean).length;
}

/** Wilson as the queue prints it: two places, the full figure in the tooltip. */
export function wilsonText(value: string | number): string {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : "—";
}

/**
 * Why a review is, or is not, in the Review Queue — the question QA asked.
 * Never "missing": the queue has a rule, and this says which part applies.
 */
export function queueStatusText(
  row: AllReviewRow,
  page: Pick<AllReviewsPage, "earn_gate_phase" | "gate_threshold" | "gate_min_stage2_voters">,
): string {
  if (row.in_review_queue) return "In the Review Queue";
  if (!row.is_thread_root) return "An update: earning stays with the thread's first review";
  if (row.state !== "published") return "Not queued: not on the site";
  if (row.earn_eligible_status === "none") {
    return page.earn_gate_phase === "post_seeding"
      ? `Not queued yet: the earnings gate needs Wilson ≥ ${page.gate_threshold.toFixed(2)} from ` +
          `${page.gate_min_stage2_voters} Stage 2+ voters (now ${row.gate.wilson_lower_bound.toFixed(2)}, ` +
          `${row.gate.stage2_plus_voters} ${row.gate.stage2_plus_voters === 1 ? "voter" : "voters"})`
      : "Not queued";
  }
  return `Decided: ${EARN_LABELS[row.earn_eligible_status] ?? row.earn_eligible_status}`;
}

/** "Updated 14:05:09" in Manila time: fixed zone, so server and browser agree. */
const UPDATED = new Intl.DateTimeFormat("en-PH", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "Asia/Manila",
});

export function updatedAtText(fetchedAt: number): string {
  return `Updated ${UPDATED.format(new Date(fetchedAt))}`;
}

const WRITTEN = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeZone: "Asia/Manila" });

export function writtenText(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : WRITTEN.format(d);
}

const MANILA_DAY = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "numeric", day: "numeric", timeZone: "Asia/Manila" });
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function manilaParts(d: Date): { y: number; m: number; day: number } {
  const parts = Object.fromEntries(MANILA_DAY.formatToParts(d).map((p) => [p.type, p.value]));
  return { y: Number(parts.year), m: Number(parts.month), day: Number(parts.day) };
}

/**
 * The Posted column, as drawn: "28 Sep"; the year only when it is not this one
 * (Manila). Month names are fixed, not the locale's ("Sept" in some ICU builds),
 * so server and browser print the same.
 */
export function postedText(iso: string, now: number): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const { y, m, day } = manilaParts(d);
  const text = `${day} ${MONTHS[m - 1]}`;
  return y === manilaParts(new Date(now)).y ? text : `${text} ${y}`;
}

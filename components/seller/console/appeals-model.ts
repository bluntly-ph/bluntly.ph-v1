/**
 * Screen/Seller/Appeals (Figma 8196:21910) and Overlay/Store/Appeal
 * (8197:21606): the store's flags, by where they stand. Pure.
 */

import type { FilterGroup } from "@/components/console/list-query";

export type StoreAppeal = {
  id: string;
  seller_review_id: string;
  reason: string;
  status: string;
  created_at: string;
  substantiation_requested_at?: string | null;
  substantiated_at?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  review_title?: string | null;
  review_comment?: string | null;
  review_rating?: number | null;
  review_created_at?: string | null;
  reviewer?: { display_name?: string | null; username?: string | null; trust_stage?: number | null } | null;
};

export type AppealTab = "progress" | "decided" | "all";
export const APPEAL_TABS: { key: AppealTab; label: string }[] = [
  { key: "progress", label: "In progress" },
  { key: "decided", label: "Decided" },
  { key: "all", label: "All" },
];

const OPEN = new Set(["open", "substantiation_requested"]);
export const isOpen = (a: StoreAppeal) => OPEN.has(a.status);

export function inAppealTab(a: StoreAppeal, tab: AppealTab): boolean {
  return tab === "all" || (tab === "progress") === isOpen(a);
}

export const STATUS: Record<string, { label: string; tone: "neutral" | "warning" | "success" | "muted" }> = {
  open: { label: "Open", tone: "neutral" },
  substantiation_requested: { label: "Proof requested", tone: "warning" },
  upheld: { label: "Upheld · removed", tone: "success" },
  dismissed: { label: "Dismissed · stays up", tone: "muted" },
};

export function reviewerOf(a: StoreAppeal): string {
  return a.reviewer?.display_name || (a.reviewer?.username ? `@${a.reviewer.username}` : "A buyer");
}

/** The cards: open (and how many wait on the reviewer), upheld of decided, median days to a decision. */
export function appealSummary(rows: StoreAppeal[]) {
  const open = rows.filter(isOpen);
  const decided = rows.filter((a) => !isOpen(a) && a.decided_at);
  const days = decided
    .map((a) => (new Date(a.decided_at as string).getTime() - new Date(a.created_at).getTime()) / 86_400_000)
    .sort((x, y) => x - y);
  const mid = days.length ? (days.length % 2 ? days[(days.length - 1) / 2] : (days[days.length / 2 - 1] + days[days.length / 2]) / 2) : null;
  return {
    open: open.length,
    waitingOnReviewer: open.filter((a) => a.status === "substantiation_requested").length,
    upheld: decided.filter((a) => a.status === "upheld").length,
    decided: decided.length,
    medianDays: mid,
  };
}

/** Menu/Seller/Appeals/Sort (Figma 8198:21632). */
export const APPEAL_SORTS: [string, string][] = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["updated", "Recently updated"],
];
export const APPEAL_DEFAULT_SORT = "newest";

const STATUS_FILTER: [string, string][] = [
  ["open", "Open"],
  ["substantiation_requested", "Proof requested"],
  ["upheld", "Upheld"],
  ["dismissed", "Dismissed"],
];

/** The last thing that happened on a flag: decided, proof given, proof asked, or the flag itself. */
export function lastUpdate(a: StoreAppeal): number {
  return Math.max(
    ...[a.created_at, a.substantiation_requested_at, a.substantiated_at, a.decided_at]
      .filter((v): v is string => Boolean(v))
      .map((v) => new Date(v).getTime()),
  );
}

const stars = (a: StoreAppeal) => (a.review_rating == null ? null : Math.max(1, Math.floor(a.review_rating)));

/** Menu/Seller/Appeals/Filter (Figma 8198:21642): Status and Rating, each with its count; ratings present only. */
export function appealFilters(rows: StoreAppeal[]): FilterGroup[] {
  const status = STATUS_FILTER.map(([v, l]) => [v, l, rows.filter((a) => a.status === v).length] as [string, string, number]).filter(
    ([, , n]) => n > 0,
  );
  const ratings = [1, 2, 3, 4, 5]
    .map((r) => [String(r), `${r}★`, rows.filter((a) => stars(a) === r).length] as [string, string, number])
    .filter(([, , n]) => n > 0);
  return [
    ...(status.length ? [{ key: "status", title: "Status", options: status }] : []),
    ...(ratings.length ? [{ key: "rating", title: "Rating", options: ratings }] : []),
  ];
}

/** Filter, search (reviewer, review title, your reason) and sort, as the URL asks. */
export function applyAppeals(rows: StoreAppeal[], q: { sort?: string; status?: string; rating?: string; q?: string }): StoreAppeal[] {
  const words = (q.q ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  const out = rows.filter(
    (a) =>
      (!q.status || a.status === q.status) &&
      (!q.rating || stars(a) === Number(q.rating)) &&
      words.every((w) => `${reviewerOf(a)} ${a.review_title ?? ""} ${a.reason}`.toLowerCase().includes(w)),
  );
  const at = (a: StoreAppeal) => new Date(a.created_at).getTime();
  const by =
    q.sort === "oldest"
      ? (x: StoreAppeal, y: StoreAppeal) => at(x) - at(y)
      : q.sort === "updated"
        ? (x: StoreAppeal, y: StoreAppeal) => lastUpdate(y) - lastUpdate(x)
        : (x: StoreAppeal, y: StoreAppeal) => at(y) - at(x);
  return [...out].sort(by);
}

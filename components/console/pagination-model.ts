/**
 * The console pager's arithmetic (Figma component Pagination, as drawn under
 * Screen/Admin/People 7998:11931): "Showing 1–10 of 1,284", ← 1 2 3 … 129 →,
 * "10 per page". Pure, so the window rule is testable without a browser.
 */

/** The page sizes a console table offers; the first is the default (Figma: 10). */
export const PAGE_SIZES = [10, 25, 50] as const;

export type PageItem = number | "gap";

export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(Math.max(0, total) / Math.max(1, size)));
}

/** A requested page clamped to the pages that exist (a stale ?page= past the end). */
export function clampPage(page: number, total: number, size: number): number {
  const n = Number.isFinite(page) ? Math.floor(page) : 1;
  return Math.min(Math.max(1, n), pageCount(total, size));
}

/** A ?size= value the table offers, else the default. */
export function pageSize(raw: string | number | null | undefined, sizes: readonly number[] = PAGE_SIZES): number {
  const n = typeof raw === "number" ? raw : Number.parseInt(raw ?? "", 10);
  return sizes.includes(n) ? n : sizes[0];
}

/** "Showing first–last of total" — 0–0 for an empty result. */
export function shownRange(page: number, size: number, total: number): { first: number; last: number } {
  if (total <= 0) return { first: 0, last: 0 };
  const first = (page - 1) * size + 1;
  return { first, last: Math.min(total, page * size) };
}

/**
 * The page buttons: always the first and the last, the current page and its
 * neighbours, and three at either end (the frame shows 1 2 3 … 129 on page 1).
 * A gap stands for the pages left out; a single left-out page is shown instead.
 */
export function pageWindow(page: number, pages: number): PageItem[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
  const keep = new Set<number>([1, pages, page - 1, page, page + 1]);
  if (page <= 3) [2, 3].forEach((p) => keep.add(p));
  if (page >= pages - 2) [pages - 2, pages - 1].forEach((p) => keep.add(p));
  const sorted = [...keep].filter((p) => p >= 1 && p <= pages).sort((a, b) => a - b);
  const out: PageItem[] = [];
  for (const p of sorted) {
    const prev = out.at(-1);
    if (typeof prev === "number" && p - prev === 2) out.push(prev + 1);
    else if (typeof prev === "number" && p - prev > 2) out.push("gap");
    out.push(p);
  }
  return out;
}

/**
 * Screen/Seller/Products (Figma 8204:22648, Waiting 8214:23301, All 8214:23647)
 * and Menu/Seller/Products/Sort + Filter (8213:23168, 8213:23178): tabs, sort,
 * filter and the row labels. Pure, so tests/frontend can check it.
 */

export type ProductTab = "linked" | "waiting" | "all";

export type Figures = {
  reviews: number;
  median?: number | null;
  change_30d?: number | null;
  worth_it?: number | null;
  complicated?: number | null;
  not_worth?: number | null;
  questions: number;
  open_questions: number;
};

export type Row = {
  id: string;
  product_id: string;
  name: string;
  category?: string | null;
  image_url?: string | null;
  status: "pending" | "approved" | "rejected" | "cancelled";
  requested_at: string;
  figures: Figures;
};

export const PRODUCT_TABS: { key: ProductTab; label: string }[] = [
  { key: "linked", label: "Linked" },
  { key: "waiting", label: "Waiting for approval" },
  { key: "all", label: "All" },
];

export const PRODUCT_SORTS: [string, string][] = [
  ["reviews", "Most reviews"],
  ["rating", "Lowest rating first"],
  ["change", "Biggest change"],
];

export function inTab(r: Row, tab: ProductTab): boolean {
  if (tab === "linked") return r.status === "approved";
  if (tab === "waiting") return r.status === "pending";
  return r.status === "approved" || r.status === "pending";
}

export function ratingBand(f: Figures): "low" | "high" | "few" {
  if (f.median == null) return "few";
  return f.median < 4 ? "low" : "high";
}

export function applyProducts(rows: Row[], tab: ProductTab, q: Record<string, string>): Row[] {
  const needle = (q.q ?? "").trim().toLowerCase();
  const out = rows.filter(
    (r) =>
      inTab(r, tab) &&
      (!q.category || r.category === q.category) &&
      (!q.rating || ratingBand(r.figures) === q.rating) &&
      (!q.open || r.figures.open_questions > 0) &&
      (!needle || r.name.toLowerCase().includes(needle)),
  );
  const sort = q.sort || "reviews";
  return out.sort((a, b) => {
    if (sort === "rating") return (a.figures.median ?? 99) - (b.figures.median ?? 99) || b.figures.reviews - a.figures.reviews;
    if (sort === "change") return Math.abs(b.figures.change_30d ?? 0) - Math.abs(a.figures.change_30d ?? 0) || b.figures.reviews - a.figures.reviews;
    return b.figures.reviews - a.figures.reviews || a.name.localeCompare(b.name);
  });
}

/** "+0.2 rating", "No change", "−0.3 rating", or "Needs 5+" (too few reviews). */
export function changeLabel(f: Figures): { text: string; tone: "up" | "down" | "flat" | "muted" } {
  if (f.median == null) return { text: "Needs 5+", tone: "muted" };
  const c = f.change_30d;
  if (c == null || Math.abs(c) < 0.05) return { text: "No change", tone: "flat" };
  return c > 0 ? { text: `+${c.toFixed(1)} rating`, tone: "up" } : { text: `−${Math.abs(c).toFixed(1)} rating`, tone: "down" };
}

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

/** Bar widths for the verdict split (green / yellow / red), summing to 100. */
export function verdictBar(f: Figures): [number, number, number] | null {
  if (f.worth_it == null || f.complicated == null || f.not_worth == null) return null;
  const total = f.worth_it + f.complicated + f.not_worth || 1;
  return [(f.worth_it / total) * 100, (f.complicated / total) * 100, (f.not_worth / total) * 100];
}

/** "up from 55% in Jul", "down from 20% in Jul", "steady". */
export function verdictTrend(now: number | null | undefined, then: number | null | undefined, monthName: string): string {
  if (now == null || then == null) return "";
  const d = Math.round(now * 100) - Math.round(then * 100);
  if (Math.abs(d) < 1) return "steady";
  return `${d > 0 ? "up" : "down"} from ${Math.round(then * 100)}% in ${monthName}`;
}

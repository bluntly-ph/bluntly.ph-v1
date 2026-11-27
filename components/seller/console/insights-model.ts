/**
 * Screen/Seller/Insights (Figma 8208:22905) and Overlay/Store/Export
 * (8213:23286): the labels under each figure, the sparklines' points and the
 * export's file list. Pure, so tests/frontend can check it.
 *
 * "Since <month>" compares the period's figure with the first month of the
 * period that has reviews (the frame's "86%, up from 79% in April"). It needs
 * two months with reviews; a month without reviews has no figure and is
 * skipped, never drawn as a zero.
 */

export type InsightsMonth = {
  month: string;
  reviews: number;
  rating?: number | null;
  recommend?: number | null;
  responded?: number | null;
  matched?: number | null;
  complete?: number | null;
  service?: number | null;
  packaging?: number | null;
};

export type MonthKey = Exclude<keyof InsightsMonth, "month" | "reviews">;

const SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export const monthShort = (key: string) => SHORT[Number(key.slice(5, 7)) - 1] ?? key;
export const monthLong = (key: string) => LONG[Number(key.slice(5, 7)) - 1] ?? key;

export const INSIGHT_PERIODS = [
  { key: "30d", label: "Last 30 days", before: "the 30 days before" },
  { key: "3m", label: "Last 3 months", before: "the 3 months before" },
  { key: "6m", label: "Last 6 months", before: "the 6 months before" },
  { key: "12m", label: "Last 12 months", before: "the 12 months before" },
  { key: "all", label: "All time", before: "" },
] as const;

export function periodLabel(period: string): string {
  return (INSIGHT_PERIODS.find((p) => p.key === period) ?? INSIGHT_PERIODS[2]).label;
}

/** The months that have a figure for `key`, oldest first. */
function withValue(months: InsightsMonth[], key: MonthKey): { month: string; value: number }[] {
  return months.flatMap((m) => (m[key] != null ? [{ month: m.month, value: m[key] as number }] : []));
}

/** "+46% vs the 6 months before", "No reviews in the 6 months before", "All time". */
export function reviewsNote(reviews: number, before: number, period: string): string {
  const p = INSIGHT_PERIODS.find((x) => x.key === period) ?? INSIGHT_PERIODS[2];
  if (!p.before) return "Since your first review";
  if (before === 0) return reviews === 0 ? `None in ${p.before} either` : `None in ${p.before}`;
  const change = Math.round(((reviews - before) / before) * 100);
  if (change === 0) return `Same as ${p.before}`;
  return `${change > 0 ? "+" : "−"}${Math.abs(change)}% vs ${p.before}`;
}

/** A rating out of 5: "+0.1 since April", "No change since April", or "" with one month. */
export function scoreSince(months: InsightsMonth[], key: MonthKey, now: number | null | undefined): string {
  const pts = withValue(months, key);
  if (pts.length < 2 || now == null) return "";
  const first = pts[0];
  const d = now - first.value;
  if (Math.abs(d) < 0.05) return `No change since ${monthLong(first.month)}`;
  return `${d > 0 ? "+" : "−"}${fmtScore(Math.abs(d))} since ${monthLong(first.month)}`;
}

/** A share: "Up from 79% in April", "Down from …", "Same as in April". */
export function shareSince(months: InsightsMonth[], key: MonthKey, value: number | null | undefined): string {
  const pts = withValue(months, key);
  if (pts.length < 2 || value == null) return "";
  const first = pts[0];
  const now = Math.round(value * 100);
  const then = Math.round(first.value * 100);
  if (now === then) return `Same as in ${monthLong(first.month)}`;
  return `${now > then ? "Up" : "Down"} from ${then}% in ${monthLong(first.month)}`;
}

/** The small tiles' change against the first month: "+3 pts" / "−1 since May" / "No change". */
export function tileChange(
  months: InsightsMonth[],
  key: MonthKey,
  kind: "share" | "score",
  now: number | null | undefined,
): { text: string; tone: "up" | "down" | "flat" } | null {
  const pts = withValue(months, key);
  if (pts.length < 2 || now == null) return null;
  const first = pts[0];
  if (kind === "share") {
    const d = Math.round(now * 100) - Math.round(first.value * 100);
    if (d === 0) return { text: "No change", tone: "flat" };
    return { text: `${d > 0 ? "+" : "−"}${Math.abs(d)} pts`, tone: d > 0 ? "up" : "down" };
  }
  const d = now - first.value;
  if (Math.abs(d) < 0.05) return { text: "No change", tone: "flat" };
  return { text: `${d > 0 ? "+" : "−"}${fmtScore(Math.abs(d))} since ${monthShort(first.month)}`, tone: d > 0 ? "up" : "down" };
}

/** 4 → "4", 4.25 → "4.3", 0.1 → "0.1". */
export function fmtScore(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

/** Polyline points for a sparkline in a `w` × `h` box; months without a figure are skipped. */
export function sparkPoints(months: InsightsMonth[], key: MonthKey, w: number, h: number, kind: "share" | "score"): { x: number; y: number }[] {
  const lo = kind === "share" ? 0 : 1;
  const hi = kind === "share" ? 1 : 5;
  const n = Math.max(1, months.length - 1);
  return months.flatMap((m, i) => {
    const v = m[key];
    if (v == null) return [];
    const t = (Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo);
    return [{ x: (i * w) / n, y: h - 4 - t * (h - 8) }];
  });
}

/** "9 h", "2 d", "35 min". */
export function hoursLabel(h: number | null | undefined): string {
  if (h == null) return "—";
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} d`;
}

/** "down from 31 h in April" (faster is better), or "" when there is nothing to compare. */
export function replyTrend(now: number | null | undefined, first: number | null | undefined, firstMonth: string | null): { text: string; tone: "up" | "down" | "flat" } | null {
  if (now == null || first == null || !firstMonth) return null;
  if (hoursLabel(now) === hoursLabel(first)) return { text: `same as ${monthLong(firstMonth)}`, tone: "flat" };
  return now < first
    ? { text: `down from ${hoursLabel(first)} in ${monthLong(firstMonth)}`, tone: "up" }
    : { text: `up from ${hoursLabel(first)} in ${monthLong(firstMonth)}`, tone: "down" };
}

/** Bars of "Your replies over time": the last `max` months (All time can be long). */
export function replyBars(months: InsightsMonth[], max = 12): { month: string; share: number | null; current: boolean }[] {
  const shown = months.slice(-max);
  return shown.map((m, i) => ({ month: m.month, share: m.responded ?? null, current: i === shown.length - 1 }));
}

// ------------------------------------------------------------------ export

export type ExportKey = "reviews" | "products" | "questions" | "appeals";

export const EXPORT_FILES: { key: ExportKey; label: string; what: string; unit: "rows" | "products" }[] = [
  { key: "reviews", label: "Store reviews", what: "ratings, order facts, your responses", unit: "rows" },
  { key: "products", label: "Product analytics", what: "ratings and verdicts", unit: "products" },
  { key: "questions", label: "Questions", what: "status and your answers", unit: "rows" },
  { key: "appeals", label: "Appeals", what: "reason, status, decision", unit: "rows" },
];

/** Rough bytes per CSV row, measured on local data; only for the "about 60 KB" hint. */
const ROW_BYTES: Record<ExportKey, number> = { reviews: 420, products: 160, questions: 200, appeals: 180 };

export function exportSummary(chosen: ExportKey[], sizes: Record<ExportKey, number> | null): string {
  const files = `${chosen.length} file${chosen.length === 1 ? "" : "s"}`;
  if (!sizes || chosen.length === 0) return files;
  const bytes = chosen.reduce((sum, k) => sum + 120 + sizes[k] * ROW_BYTES[k], 0);
  const kb = Math.max(1, Math.round(bytes / 1024));
  return `${files} · about ${kb} KB`;
}

export function exportHref(storeId: string, chosen: ExportKey[], period: string): string {
  const order = EXPORT_FILES.map((f) => f.key).filter((k) => chosen.includes(k));
  return `/api/bff/api/v1/sellers/${encodeURIComponent(storeId)}/export?include=${order.join(",")}&period=${encodeURIComponent(period)}`;
}

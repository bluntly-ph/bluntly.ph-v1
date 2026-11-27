/**
 * Price history, as the sheet and window draw it (Figma "Sheet/Product/
 * PriceHistory" 8375:32412 and "Overlay/Product/PriceHistory" 8372:32116, read
 * 2026-10-05), from the real series of GET /products/{id}/prices — the
 * administrator-checked prices buyers reported, one line per marketplace
 * (Business Rules §16). Nothing here invents a price: every figure is a point
 * in the series, or the median of points in the range.
 */
import type { PricePoint, PriceSeries } from "./price-chart-model.ts";

export type PriceRange = "30D" | "90D" | "1Y" | "All";
export const PRICE_RANGES: PriceRange[] = ["30D", "90D", "1Y", "All"];
const DAYS: Record<PriceRange, number | null> = { "30D": 30, "90D": 90, "1Y": 365, All: null };

/** "Middle of 90 days", "Middle of the last year", "Middle of every report". */
export const RANGE_WORDS: Record<PriceRange, string> = {
  "30D": "Middle of 30 days",
  "90D": "Middle of 90 days",
  "1Y": "Middle of the year",
  All: "Middle of every report",
};

const dayMs = (iso: string) => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);

/** The points observed within the range, ending today; empty marketplaces dropped. */
export function inRange(series: PriceSeries, range: PriceRange, now: number): PriceSeries {
  const days = DAYS[range];
  const today = Date.parse(`${new Date(now).toISOString().slice(0, 10)}T00:00:00Z`);
  const from = days === null ? -Infinity : today - (days - 1) * 86_400_000;
  const out: PriceSeries = {};
  for (const [platform, points] of Object.entries(series)) {
    const kept = points
      .filter((p) => dayMs(p.observed_at) >= from && Number.isFinite(Number(p.price)))
      .sort((a, b) => dayMs(a.observed_at) - dayMs(b.observed_at));
    if (kept.length) out[platform] = kept;
  }
  return out;
}

export type PriceFact = { price: number; platform: string; date: string };

export type PriceStats = {
  count: number;
  /** The most recent report; the cheapest marketplace when two share the day. */
  latest: PriceFact | null;
  lowest: PriceFact | null;
  highest: PriceFact | null;
  /** The median of every report in the range. */
  usual: number | null;
};

export function priceStats(series: PriceSeries): PriceStats {
  const all: PriceFact[] = Object.entries(series).flatMap(([platform, points]) =>
    points.map((p: PricePoint) => ({ price: Number(p.price), platform, date: p.observed_at.slice(0, 10) })),
  );
  if (!all.length) return { count: 0, latest: null, lowest: null, highest: null, usual: null };
  const byDateThenPrice = [...all].sort((a, b) => (a.date === b.date ? a.price - b.price : a.date < b.date ? 1 : -1));
  // Ties on price go to the earliest date: "lowest since".
  const lowest = [...all].sort((a, b) => a.price - b.price || (a.date < b.date ? -1 : 1))[0];
  const highest = [...all].sort((a, b) => b.price - a.price || (a.date < b.date ? -1 : 1))[0];
  const sorted = all.map((f) => f.price).sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const usual = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  return { count: all.length, latest: byDateThenPrice[0], lowest, highest, usual: Math.round(usual * 100) / 100 };
}

/**
 * "Shopee is ₱50 under its usual price today." — said of the latest report
 * against the range's median, and only when they differ. Worded as a report,
 * not a live price: these are what buyers paid, not a listing.
 */
export function comparisonLine(stats: PriceStats, label: (platform: string) => string, money: (n: number) => string): string | null {
  if (!stats.latest || stats.usual === null || stats.count < 2) return null;
  const diff = Math.round((stats.latest.price - stats.usual) * 100) / 100;
  if (diff === 0) return `The latest ${label(stats.latest.platform)} report matches the usual price.`;
  return `The latest ${label(stats.latest.platform)} report is ${money(Math.abs(diff))} ${diff < 0 ? "under" : "over"} the usual price.`;
}

/** Three round gridline values spanning [min, max], as the frame's ₱1000 / ₱1250 / ₱1500. */
export function priceTicks(min: number, max: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (max === min) {
    const step = niceStep(Math.max(1, Math.abs(min) * 0.1));
    return [min - step, min, min + step].map((v) => Math.round(v));
  }
  // The smallest round step whose three ticks still cover the data.
  let step = niceStep((max - min) / 2);
  for (let i = 0; i < 8; i++) {
    const lo = Math.floor(min / step) * step;
    if (lo + 2 * step >= max) return [lo, lo + step, lo + 2 * step];
    step = niceStep(step * 1.01);
  }
  const lo = Math.floor(min / step) * step;
  return [lo, lo + step, lo + 2 * step];
}

function niceStep(raw: number): number {
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * power) return m * power;
  return 10 * power;
}

/** Up to four dates evenly across [first, last], as the frame's x labels. */
export function dateTicks(first: string, last: string, count = 4): string[] {
  const a = dayMs(first);
  const b = dayMs(last);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return [];
  if (a === b) return [first.slice(0, 10)];
  const n = Math.max(2, Math.min(count, Math.round((b - a) / 86_400_000) + 1));
  return Array.from({ length: n }, (_, i) => new Date(a + ((b - a) * i) / (n - 1)).toISOString().slice(0, 10));
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "11 Sep" — a fixed month list: ICU writes September as "Sept" in en-GB. */
export function dayMonth(iso: string): string {
  const [, m, d] = iso.slice(0, 10).split("-").map(Number);
  return m && d ? `${d} ${MONTHS[m - 1]}` : "";
}

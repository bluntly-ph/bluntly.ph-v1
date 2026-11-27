/**
 * Pure helpers for the contributor dashboard (Figma Screen/Dashboard 7833:9534).
 * No React, no fetch — tested in tests/frontend/contributor-dashboard-model.test.mjs.
 *
 * Money stays the API's decimal string for display; bar heights and rings are
 * proportions, where a number is fine.
 */

/** "1790.04" -> ["₱1,790", ".04"]; the design draws the cents smaller and paler. */
export function pesoSplit(value: string | null | undefined): [string, string] {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return ["₱0", ".00"];
  const [whole, cents] = Math.abs(n)
    .toFixed(2)
    .split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return [`${n < 0 ? "−" : ""}₱${grouped}`, `.${cents}`];
}

/** "47k", "1.3k", "758": the design's compact counts. */
export function compact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) {
    const k = n / 1000;
    return `${k < 10 ? k.toFixed(1).replace(/\.0$/, "") : Math.round(k)}k`;
  }
  const m = n / 1_000_000;
  return `${m < 10 ? m.toFixed(1).replace(/\.0$/, "") : Math.round(m)}m`;
}

/** Bar heights in px on ONE scale (pesos per px), earned up to 95, returned
 *  capped at the 32px band below the axis; any money at all gets 4px. */
export function barHeights(
  buckets: { earned: string; returned: string }[],
  maxUp = 95,
  maxDown = 32,
): { up: number; down: number }[] {
  const earned = buckets.map((b) => Math.max(0, Number(b.earned) || 0));
  const returned = buckets.map((b) => Math.max(0, Number(b.returned) || 0));
  const top = Math.max(...earned, ...returned, 0);
  if (top <= 0) return buckets.map(() => ({ up: 0, down: 0 }));
  const px = (v: number, cap: number) => (v <= 0 ? 0 : Math.min(cap, Math.max(4, Math.round((v / top) * maxUp))));
  return buckets.map((_, i) => ({ up: px(earned[i], maxUp), down: px(returned[i], maxDown) }));
}

export type StepState = "done" | "next" | "upcoming";

/** The 1..5 stepper: stages reached are filled, the next one is ringed. */
export function stepStates(stage: number): StepState[] {
  return [1, 2, 3, 4, 5].map((n) => (n <= stage ? "done" : n === stage + 1 ? "next" : "upcoming"));
}

/** How full a requirement's ring is, 0..1. A "no strikes" style requirement
 *  (needed 0) is full when met and empty when not. */
export function ringFraction(have: number, needed: number, done: boolean): number {
  if (done) return 1;
  if (needed <= 0) return 0;
  return Math.max(0, Math.min(1, have / needed));
}

/** What a requirement ring says: "2/3" for counts of things, the score itself otherwise. */
export function requirementValue(key: string, have: number, needed: number): string {
  if (key === "receipt_reviews" || key === "best_answers" || key === "reviews") return `${Math.floor(have)}/${needed}`;
  if (key === "months_active") return `${have}`;
  return `${Math.round(have)}`;
}

/** "2 of 3 steps to Verified Buyer". */
export function stepsLine(requirements: { done: boolean }[], next: string | null): string {
  if (!next) return "The top of the ladder";
  const met = requirements.filter((r) => r.done).length;
  return `${met} of ${requirements.length} ${requirements.length === 1 ? "step" : "steps"} to ${next}`;
}

/** "1.4%" of the stage above in the funnel; null when there is nothing to
 *  divide, or when the part is larger (people can vote on a review they read
 *  last month, so "helped" can exceed this month's views — not a funnel). */
export function share(part: number, whole: number): string | null {
  if (whole <= 0 || part > whole) return null;
  const pct = (part / whole) * 100;
  return `${pct < 10 && pct > 0 ? pct.toFixed(1).replace(/\.0$/, "") : Math.round(pct)}%`;
}

/** "+12%" / "−2%" against the month before; null when last month was zero. */
export function change(now: number, before: number): string | null {
  if (before <= 0) return null;
  const pct = Math.round(((now - before) / before) * 100);
  return `${pct > 0 ? "+" : pct < 0 ? "−" : ""}${Math.abs(pct)}%`;
}

/**
 * The Payout ring (Figma Chart/Threshold ring 7842:9432): commission then
 * Honesty Fund, clockwise from the top. Below the minimum the arcs are each
 * part's share OF THE MINIMUM, so the grey track left over is what is still
 * to go; at or above it they split the whole ring.
 */
export function payoutRing(
  commission: string | number,
  honestyFund: string | number,
  minimum: string | number,
): { commission: number; honestyFund: number; met: boolean } {
  const c = Math.max(Number(commission) || 0, 0);
  const h = Math.max(Number(honestyFund) || 0, 0);
  const min = Math.max(Number(minimum) || 0, 0);
  const total = c + h;
  const met = total >= min && total > 0;
  const scale = met ? total : min;
  if (scale <= 0) return { commission: 0, honestyFund: 0, met };
  return { commission: c / scale, honestyFund: h / scale, met };
}

export type ArcLabel = { key: string; d: string; text: string; show: boolean };

/**
 * "Where the commission went": each share's amount written along its own arc.
 *
 * The arcs are drawn clockwise from the top, each `gap` px shorter than its
 * share of the circumference (the chart's own dash geometry). A label runs
 * along the band's centre line over that same span; in the lower half the path
 * runs the other way so the text reads upright. `show` is false when the arc is
 * too short for the text (an approximate width: `charWidth` px per character).
 */
export function commissionArcLabels(
  parts: { key: string; value: number }[],
  size: number,
  band: number,
  gap: number,
  charWidth = 6.6,
): ArcLabel[] {
  const r = (size - band) / 2;
  const c = 2 * Math.PI * r;
  const mid = size / 2;
  const total = parts.reduce((a, p) => a + Math.max(p.value, 0), 0);
  const at = (turn: number) => {
    const a = turn * 2 * Math.PI;
    return `${(mid + r * Math.sin(a)).toFixed(2)} ${(mid - r * Math.cos(a)).toFixed(2)}`;
  };
  let start = 0;
  return parts.map((p) => {
    const len = total > 0 ? Math.max(p.value, 0) / total : 0;
    const from = start + gap / 2 / c;
    const to = start + len - gap / 2 / c;
    start += len;
    const text = pesoSplit(String(p.value)).join("");
    const arc = (to - from) * c;
    if (len <= 0 || arc <= 0) return { key: p.key, d: "", text, show: false };
    const centre = (from + to) / 2;
    const lower = Math.cos(centre * 2 * Math.PI) < 0;
    const large = to - from > 0.5 ? 1 : 0;
    const d = lower
      ? `M ${at(to)} A ${r} ${r} 0 ${large} 0 ${at(from)}`
      : `M ${at(from)} A ${r} ${r} 0 ${large} 1 ${at(to)}`;
    return { key: p.key, d, text, show: arc >= text.length * charWidth + 8 };
  });
}

/**
 * Chart/Earnings line (Figma 7831:21345): a polyline over the plot box with a
 * "nice" top (the scale's three labels are top, half, 0). Returns the SVG
 * points string and the top in pesos.
 */
export function earningsLine(
  values: (string | number)[],
  width: number,
  height: number,
): { points: string; top: number } {
  const v = values.map((x) => Math.max(0, Number(x) || 0));
  const max = Math.max(...v, 0);
  const step = max <= 0 ? 1 : 10 ** Math.floor(Math.log10(max));
  const top = max <= 0 ? 30 : Math.ceil(max / step) * step;
  const dx = v.length > 1 ? width / (v.length - 1) : 0;
  const points = v.map((x, i) => `${(i * dx).toFixed(1)},${(height - (x / top) * height).toFixed(1)}`).join(" ");
  return { points, top };
}

/** Card/Votes bars: helpful up to 80px, not helpful down to 20px, one scale. */
export function voteBars(buckets: { up: number; down: number }[], maxUp = 80, maxDown = 20): { up: number; down: number }[] {
  const top = Math.max(...buckets.map((b) => Math.max(b.up, b.down)), 0);
  if (top <= 0) return buckets.map(() => ({ up: 0, down: 0 }));
  const px = (n: number, cap: number) => (n <= 0 ? 0 : Math.min(cap, Math.max(2, Math.round((n / top) * maxUp))));
  return buckets.map((b) => ({ up: px(b.up, maxUp), down: px(b.down, maxDown) }));
}

/** "₱65,969.00": a breakdown amount, cents always shown. "−₱0.00" with `negative`. */
export function peso(value: string | number | null | undefined, negative = false): string {
  const [whole, cents] = pesoSplit(value === null || value === undefined ? null : String(value));
  return `${negative && !whole.startsWith("−") ? "−" : ""}${whole}${cents}`;
}

/** "₱3,873": a sales figure in a row's meta line, whole pesos. */
export function pesoWhole(value: string | number): string {
  return pesoSplit(String(Math.round(Number(value) || 0)))[0];
}

/** "1 order" / "91 orders"; "1 item" / "123 items". */
export function counted(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}

/**
 * The sheet's subtitle: "Apr 5 – Oct 2, 2026 · completed orders", in Manila
 * time; both years when the span crosses one; one day alone; null with none.
 */
export function completedSpan(first: string | null, last: string | null): string | null {
  if (!first || !last) return null;
  const part = (iso: string, opts: Intl.DateTimeFormatOptions) =>
    new Date(iso).toLocaleDateString("en-US", { timeZone: "Asia/Manila", ...opts });
  const year = (iso: string) => part(iso, { year: "numeric" });
  const day = { month: "short", day: "numeric" } as const;
  const end = `${part(last, day)}, ${year(last)}`;
  const start = year(first) === year(last) ? part(first, day) : `${part(first, day)}, ${year(first)}`;
  return `${start === part(last, day) && year(first) === year(last) ? end : `${start} – ${end}`} · completed orders`;
}

/**
 * The price-history chart's geometry, kept out of the component so the test
 * runner can check it (Business Rules §16: one line per marketplace, never
 * blended into one average).
 */

export type PricePoint = { observed_at: string; price: string };
export type PriceSeries = Record<string, PricePoint[]>;

export type ChartLine = {
  platform: string;
  /** SVG path data, or "" when the marketplace has no points. */
  d: string;
  /** Each point in chart coordinates, for markers and their labels. */
  dots: { x: number; y: number; price: number; date: string }[];
};

export type Chart = {
  lines: ChartLine[];
  minPrice: number;
  maxPrice: number;
  firstDate: string | null;
  lastDate: string | null;
};

const day = (iso: string): number => Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);

/**
 * Lay out the visible marketplaces' series in a `width` × `height` box with
 * `pad` on every side. Both axes are scaled to the VISIBLE lines only, so
 * hiding a marketplace re-fits the others rather than leaving them squashed.
 * A single point sits in the middle; equal prices draw a flat line mid-height.
 */
export function layoutChart(
  series: PriceSeries,
  visible: readonly string[],
  width: number,
  height: number,
  pad = 8,
): Chart {
  const shown = visible.filter((p) => (series[p] ?? []).length > 0);
  const all = shown.flatMap((p) => series[p]);
  if (all.length === 0) {
    return { lines: [], minPrice: 0, maxPrice: 0, firstDate: null, lastDate: null };
  }
  const prices = all.map((p) => Number(p.price));
  const times = all.map((p) => day(p.observed_at));
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const x = (t: number) => (t1 === t0 ? width / 2 : pad + ((t - t0) / (t1 - t0)) * innerW);
  const y = (v: number) =>
    maxPrice === minPrice ? height / 2 : pad + (1 - (v - minPrice) / (maxPrice - minPrice)) * innerH;

  const lines = shown.map((platform) => {
    const points = [...series[platform]].sort((a, b) => day(a.observed_at) - day(b.observed_at));
    const dots = points.map((p) => ({
      x: round(x(day(p.observed_at))),
      y: round(y(Number(p.price))),
      price: Number(p.price),
      date: p.observed_at.slice(0, 10),
    }));
    const d = dots.map((pt, i) => `${i === 0 ? "M" : "L"}${pt.x} ${pt.y}`).join(" ");
    return { platform, d, dots };
  });

  const sortedDates = all.map((p) => p.observed_at.slice(0, 10)).sort();
  return {
    lines,
    minPrice,
    maxPrice,
    firstDate: sortedDates[0],
    lastDate: sortedDates[sortedDates.length - 1],
  };
}

function round(n: number): number {
  return Math.round(n * 10) / 10;
}

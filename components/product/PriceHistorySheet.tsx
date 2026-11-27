"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChartLine, Package, X } from "@phosphor-icons/react/dist/ssr";

import { Block, Pill, SkeletonRegion } from "@/components/ui/Skeleton";
import type { PricePanel } from "@/lib/products";

import {
  PRICE_RANGES,
  RANGE_WORDS,
  comparisonLine,
  dateTicks,
  dayMonth,
  inRange,
  priceStats,
  priceTicks,
  type PriceRange,
} from "./price-history-model";
import type { PriceSeries } from "./price-chart-model";

/**
 * Price history — Figma "Sheet/Product/PriceHistory" (8375:32412; 30D / 1Y /
 * All 8460:36440/36484/36528; Loading 8375:32513; Empty 8375:32583; Error
 * 8375:32647) on phones and "Overlay/Product/PriceHistory" (8372:32116 and its
 * states) from `md`, read 2026-10-05, "opened from 'Price history' on product
 * tools". A native <dialog>: Escape and the backdrop close it, focus is held
 * inside while it is open.
 *
 *   sheet    white, top radius 24, 16px in, a 40x4 #d9d9d9 handle; title 20px
 *            SemiBold over "Product · marketplaces" in 12px at 70%; the range
 *            as FilterChips (30D 90D 1Y All); the chart 200px tall; the legend;
 *            four PriceStat tiles 2x2; the comparison; "Report what you paid";
 *            the full-width Open pill
 *   window   760px at radius 24, 24px in, a close X; the product row; the range
 *            as a segmented control, the legend beside it; the tiles in a row;
 *            a hairline footer with the note and Open pills
 *   chart    three gridlines at #E6E6E6 with 10px labels in a 44px gutter;
 *            Shopee #EF5821 solid 2px, Lazada #3771C8 dashed 5/4; the lowest
 *            point a 10px white dot ringed in its line's colour under a dark
 *            "Lowest ₱1,099 · 11 Sep" tip; four 10px dates beneath
 *
 * REAL DATA ONLY (GET /products/{id}/prices, Business Rules §16): the series
 * is the administrator-checked prices buyers reported, one line per
 * marketplace, never blended. The range filters those points; every tile is a
 * real point or their median. Nothing is drawn below the publication
 * threshold (`sufficient` false → the empty state, with the pending count).
 *
 * INTENTIONAL PRODUCT DIFFERENCES — the frames' copy describes a scraper this
 * product does not have ("Checked daily from public listings", "We start
 * tracking once a listing is linked"; "Now … lowest today"). Prices here are
 * buyers' reports, so the tile is "Latest report", the note says where the
 * figures come from, and the empty state says how history starts. "Open on …"
 * is drawn only when the review carries that marketplace's listing link.
 */

const LABEL: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", amazon: "Amazon", other: "Other" };
const STROKE: Record<string, { color: string; dash?: string }> = {
  shopee: { color: "#EF5821" },
  lazada: { color: "#3771C8", dash: "5 4" },
  amazon: { color: "#202020", dash: "2 3" },
  other: { color: "#8c8c8c", dash: "1 3" },
};
const label = (p: string) => LABEL[p] ?? p;
const peso = (n: number) => `₱${n.toLocaleString("en-PH", { maximumFractionDigits: 2, minimumFractionDigits: n % 1 ? 2 : 0 })}`;

type Load = { state: "ready"; panel: PricePanel } | { state: "loading" } | { state: "error" };

export function PriceHistorySheet({
  productId,
  productName,
  initial,
  listing,
  reportHref,
  triggerClassName,
  triggerContent,
}: {
  productId: string;
  productName: string | null;
  /** The panel the page already read; null when that read failed;
   *  undefined when the page did not read it — the sheet loads it on open. */
  initial?: PricePanel | null;
  listing?: { href: string; platform: string | null } | null;
  /** Where "Report what you paid" goes (the page's report form). */
  reportHref?: string;
  triggerClassName: string;
  /** What the trigger shows; the pill's glyph and label by default. */
  triggerContent?: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [load, setLoad] = useState<Load>(
    initial ? { state: "ready", panel: initial } : initial === null ? { state: "error" } : { state: "loading" },
  );
  const lazy = initial === undefined;
  const [range, setRange] = useState<PriceRange>("90D");

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    const onClose = () => setIsOpen(false);
    el.addEventListener("close", onClose);
    return () => el.removeEventListener("close", onClose);
  }, []);

  useEffect(() => {
    const el = dialogRef.current;
    if (isOpen && el && !el.open) el.showModal();
  }, [isOpen]);

  const opened = useRef(false);

  async function retry() {
    setLoad({ state: "loading" });
    try {
      const res = await fetch(`/api/bff/api/v1/products/${encodeURIComponent(productId)}/prices`);
      if (!res.ok) throw new Error(String(res.status));
      setLoad({ state: "ready", panel: (await res.json()) as PricePanel });
    } catch {
      setLoad({ state: "error" });
    }
  }

  const panel = load.state === "ready" ? load.panel : null;
  const series: PriceSeries = panel?.sufficient ? (panel.series ?? {}) : {};
  const platforms = Object.keys(series).filter((p) => series[p].length);
  const subtitle = [productName, platforms.length ? platforms.map(label).join(" and ") : null].filter(Boolean).join(" · ");

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setIsOpen(true);
          // Read on first open when the page did not (search cards).
          if (lazy && !opened.current) {
            opened.current = true;
            void retry();
          }
        }}
        aria-haspopup="dialog"
        className={triggerClassName}
      >
        {triggerContent ?? (
          <>
            <ChartLine size={20} aria-hidden="true" /> Price History
          </>
        )}
      </button>
      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        onClick={(e) => {
          if (e.target === dialogRef.current) dialogRef.current?.close();
        }}
        className="mb-0 mt-auto max-h-[92dvh] w-full max-w-full overflow-y-auto rounded-t-[24px] bg-[var(--surface-card)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-sheet)] backdrop:bg-[var(--overlay-scrim-25)] md:m-auto md:w-[min(760px,calc(100vw-2rem))] md:rounded-[24px]"
      >
        {isOpen ? (
          <div className="flex flex-col gap-4 px-4 pb-[34px] pt-3 md:gap-5 md:p-6">
            <div className="flex justify-center pb-1 md:hidden" aria-hidden="true">
              <span className="h-1 w-10 rounded-[2px] bg-[#d9d9d9]" />
            </div>

            <div className="flex items-start gap-3">
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <h2 id={titleId} className="text-[20px] font-semibold leading-7">
                  Price history
                </h2>
                <p className="break-words text-[12px] leading-4 text-[var(--text-secondary)] md:hidden">{subtitle || productName}</p>
              </div>
              <button
                type="button"
                onClick={() => dialogRef.current?.close()}
                aria-label="Close price history"
                className="grid size-8 shrink-0 cursor-pointer place-items-center rounded-full hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
              >
                <X size={20} aria-hidden="true" />
              </button>
            </div>

            <div className="hidden min-w-0 items-center gap-3 md:flex">
              <span className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-[var(--surface-app)]">
                <Package size={20} aria-hidden="true" />
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="break-words text-[14px] font-medium leading-5">{productName}</span>
                {platforms.length ? (
                  <span className="text-[12px] leading-4 text-[var(--text-secondary)]">
                    Reported on {platforms.map(label).join(" and ")} since {dayMonth(firstDate(series)).replace(/^\d+ /, "")}{" "}
                    {firstDate(series).slice(0, 4)}
                  </span>
                ) : null}
              </span>
            </div>

            {load.state === "loading" ? (
              <Loading />
            ) : load.state === "error" ? (
              <div className="flex flex-col items-center gap-2 rounded-[12px] bg-[var(--status-critical-bg)] px-6 py-10 text-center">
                <p className="text-[16px] font-semibold leading-6">Couldn&rsquo;t load price history</p>
                <p className="text-[14px] leading-5 text-[var(--text-secondary)]">Something went wrong on our side. Try again in a moment.</p>
                <button
                  type="button"
                  onClick={() => void retry()}
                  className="mt-1 h-7 cursor-pointer rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] font-medium leading-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                >
                  Try again
                </button>
              </div>
            ) : !platforms.length ? (
              <div className="flex flex-col items-center gap-2 rounded-[12px] bg-[var(--surface-app)] px-6 py-10 text-center">
                <p className="text-[16px] font-semibold leading-6">No price history yet</p>
                <p className="text-[14px] leading-5 text-[var(--text-secondary)]">
                  History starts with the first price a buyer reports and an administrator checks.
                  {panel && panel.pending_count > 0
                    ? ` ${panel.pending_count} ${panel.pending_count === 1 ? "report is" : "reports are"} waiting to be checked.`
                    : ""}
                </p>
              </div>
            ) : (
              <Ready series={series} range={range} onRange={setRange} />
            )}

            {load.state === "ready" && platforms.length ? (
              <div className="flex flex-col gap-4 md:-mx-6 md:flex-row md:items-center md:gap-3 md:border-t md:border-[var(--border-subtle)] md:px-6 md:pt-4">
                <p className="text-[12px] leading-4 text-[var(--text-secondary)] md:flex-1">
                  What buyers here reported paying, checked by an administrator. Not a listing price.
                </p>
                {reportHref ? (
                  <a
                    href={reportHref}
                    onClick={() => dialogRef.current?.close()}
                    className="text-[14px] font-semibold leading-5 text-[var(--accent-primary)] hover:underline md:hidden"
                  >
                    Paid a different price? Report what you paid
                  </a>
                ) : null}
                {listing ? (
                  <a
                    href={listing.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex h-14 w-full items-center justify-center rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-6 text-[16px] font-semibold leading-6 text-[var(--text-on-brand)] hover:bg-[var(--accent-primary-strong)] md:h-8 md:w-auto md:px-3 md:text-[12px] md:font-normal"
                  >
                    Open on {listing.platform ? label(listing.platform) : "the listing"}
                  </a>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
      </dialog>
    </>
  );
}

function firstDate(series: PriceSeries): string {
  return Object.values(series).flat().map((p) => p.observed_at.slice(0, 10)).sort()[0] ?? "";
}

function Ready({ series, range, onRange }: { series: PriceSeries; range: PriceRange; onRange: (r: PriceRange) => void }) {
  const [now] = useState(() => Date.now());
  const shown = inRange(series, range, now);
  const stats = priceStats(shown);
  const platforms = Object.keys(shown);
  const allPlatforms = Object.keys(series).filter((p) => series[p].length);
  const line = comparisonLine(stats, label, peso);

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <div
          role="radiogroup"
          aria-label="Range"
          onKeyDown={(e) => {
            const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
            if (!step) return;
            e.preventDefault();
            const next = PRICE_RANGES[(PRICE_RANGES.indexOf(range) + step + PRICE_RANGES.length) % PRICE_RANGES.length];
            onRange(next);
            (e.currentTarget.querySelector(`[data-range="${next}"]`) as HTMLButtonElement | null)?.focus();
          }}
          className="flex gap-2 md:gap-0 md:rounded-[12px] md:bg-[var(--surface-app)] md:p-1">
          {PRICE_RANGES.map((r) => {
            const on = r === range;
            return (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={on}
                tabIndex={on ? 0 : -1}
                data-range={r}
                onClick={() => onRange(r)}
                className={`h-8 cursor-pointer rounded-[16px] border px-[14px] text-[12px] leading-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--accent-primary)] md:rounded-[8px] md:border-0 md:text-[14px] ${
                  on
                    ? "border-[#e94f1d] bg-[#fbede3] font-medium text-[#e94f1d] md:bg-[var(--surface-card)] md:text-[var(--text-primary)] md:shadow-[var(--shadow-hairline-inset)]"
                    : "border-[#d1d1d1] bg-white text-[var(--text-primary)] md:bg-transparent md:text-[var(--text-secondary)]"
                }`}
              >
                {r}
              </button>
            );
          })}
        </div>
        <span className="hidden flex-1 md:block" />
        <Legend platforms={allPlatforms} className="hidden md:flex" />
      </div>

      {platforms.length ? (
        <Chart series={shown} lowest={stats.lowest} />
      ) : (
        <div className="grid h-[200px] place-items-center rounded-[12px] bg-[var(--surface-app)] px-6 text-center text-[14px] leading-5 text-[var(--text-secondary)]">
          No checked reports in this range. Try a longer one.
        </div>
      )}

      <Legend platforms={allPlatforms} className="md:hidden" />

      {stats.count ? (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          <Stat label="Latest report" value={stats.latest} />
          <Stat label="Lowest" value={stats.lowest} good />
          <Stat label="Highest" value={stats.highest} />
          <div className="flex min-w-0 flex-col gap-0.5 rounded-[12px] border border-[var(--border-subtle)] px-[14px] py-3">
            <span className="text-[12px] leading-4 text-[var(--text-secondary)]">Usual price</span>
            <span className="text-[16px] font-semibold leading-6">{stats.usual === null ? "—" : peso(stats.usual)}</span>
            <span className="text-[12px] leading-4 text-[var(--text-secondary)]">{RANGE_WORDS[range]}</span>
          </div>
        </div>
      ) : null}
      {stats.count === 1 ? (
        <p className="text-[12px] leading-4 text-[var(--text-secondary)]">One checked report in this range so far.</p>
      ) : line ? (
        <p className="text-[12px] leading-4 text-[var(--text-secondary)]">{line}</p>
      ) : null}
    </>
  );
}

function Stat({ label: name, value, good = false }: { label: string; value: { price: number; platform: string; date: string } | null; good?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-[12px] border border-[var(--border-subtle)] px-[14px] py-3">
      <span className="text-[12px] leading-4 text-[var(--text-secondary)]">{name}</span>
      <span className={`text-[16px] font-semibold leading-6 ${good ? "text-[var(--semantic-success-500)]" : ""}`}>
        {value ? peso(value.price) : "—"}
      </span>
      <span className="break-words text-[12px] leading-4 text-[var(--text-secondary)]">
        {value ? `${label(value.platform)} · ${dayMonth(value.date)}` : ""}
      </span>
    </div>
  );
}

function Legend({ platforms, className = "" }: { platforms: string[]; className?: string }) {
  return (
    <ul className={`flex flex-wrap items-center gap-4 ${className}`} aria-label="Marketplaces">
      {platforms.map((p) => {
        const s = STROKE[p] ?? STROKE.other;
        return (
          <li key={p} className="flex items-center gap-1.5 text-[12px] leading-4 text-[var(--text-secondary)]">
            <svg width="16" height="2" aria-hidden="true">
              <line x1="0" y1="1" x2="16" y2="1" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
            </svg>
            {label(p)}
          </li>
        );
      })}
    </ul>
  );
}

const H = 200;
const GUTTER = 44;
const TOP = 16;
const BOTTOM = 176;

function Chart({ series, lowest }: { series: PriceSeries; lowest: { price: number; platform: string; date: string } | null }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(358);
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const all = Object.values(series).flat();
  const prices = all.map((p) => Number(p.price));
  const ticks = priceTicks(Math.min(...prices), Math.max(...prices));
  const dates = all.map((p) => p.observed_at.slice(0, 10)).sort();
  const t0 = Date.parse(`${dates[0]}T00:00:00Z`);
  const t1 = Date.parse(`${dates[dates.length - 1]}T00:00:00Z`);
  const left = GUTTER + 4;
  const right = w - 4;
  const x = (iso: string) => {
    const t = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
    return t1 === t0 ? (left + right) / 2 : left + ((t - t0) / (t1 - t0)) * (right - left);
  };
  const lo = ticks[0];
  const hi = ticks[ticks.length - 1];
  const y = (v: number) => (hi === lo ? (TOP + BOTTOM) / 2 : TOP + (1 - (v - lo) / (hi - lo)) * (BOTTOM - TOP));
  const dots = Object.entries(series).flatMap(([platform, points]) =>
    points.map((p) => ({ platform, x: x(p.observed_at), y: y(Number(p.price)), price: Number(p.price), date: p.observed_at.slice(0, 10) })),
  );
  const low = lowest ? { x: x(lowest.date), y: y(lowest.price), text: `Lowest ${peso(lowest.price)} · ${dayMonth(lowest.date)}` } : null;
  const tip = hover ?? low;
  const xTicks = dateTicks(dates[0], dates[dates.length - 1]);

  return (
    <div ref={box} className="relative w-full">
      <svg
        width={w}
        height={H}
        role="img"
        aria-label={`Prices from ${dayMonth(dates[0])} to ${dayMonth(dates[dates.length - 1])}, between ${peso(Math.min(...prices))} and ${peso(Math.max(...prices))}.`}
        onPointerMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = e.clientX - r.left;
          const near = dots.reduce((a, b) => (Math.abs(b.x - px) < Math.abs(a.x - px) ? b : a), dots[0]);
          if (near) setHover({ x: near.x, y: near.y, text: `${label(near.platform)} ${peso(near.price)} · ${dayMonth(near.date)}` });
        }}
        onPointerLeave={() => setHover(null)}
        className="block touch-pan-y"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={GUTTER} x2={w} y1={y(t)} y2={y(t)} stroke="#E6E6E6" />
            <text x={0} y={y(t) + 3} fontSize="10" fill="rgba(32,32,32,0.7)">
              ₱{t.toLocaleString("en-PH", { maximumFractionDigits: 0, useGrouping: false })}
            </text>
          </g>
        ))}
        {Object.entries(series).map(([platform, points]) => {
          const s = STROKE[platform] ?? STROKE.other;
          const d = points.map((p, i) => `${i ? "L" : "M"}${x(p.observed_at).toFixed(1)} ${y(Number(p.price)).toFixed(1)}`).join(" ");
          return (
            <g key={platform}>
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} strokeLinejoin="round" />
              {points.length === 1 ? <circle cx={x(points[0].observed_at)} cy={y(Number(points[0].price))} r="3" fill={s.color} /> : null}
            </g>
          );
        })}
        {low && lowest ? (
          <circle cx={low.x} cy={low.y} r="4" fill="white" stroke={(STROKE[lowest.platform] ?? STROKE.other).color} strokeWidth="2" />
        ) : null}
        {hover ? <circle cx={hover.x} cy={hover.y} r="4" fill="white" stroke="#202020" strokeWidth="2" /> : null}
        {xTicks.map((d, i) => (
          <text
            key={d}
            x={x(d)}
            y={196}
            fontSize="10"
            fill="rgba(32,32,32,0.7)"
            textAnchor={xTicks.length === 1 ? "middle" : i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
          >
            {dayMonth(d)}
          </text>
        ))}
      </svg>
      {tip ? (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute whitespace-nowrap rounded-[8px] bg-[var(--text-primary)] px-2 py-1 text-[12px] font-medium leading-4 text-white"
          style={{
            left: Math.min(Math.max(tip.x - 80, GUTTER), w - 170),
            // Under the dot, as the frame draws it, unless that would cover
            // the date labels; then above.
            top: tip.y + 10 + 24 <= 186 ? tip.y + 10 : tip.y - 34,
          }}
        >
          {tip.text}
        </span>
      ) : null}
      <table className="sr-only">
        <caption>Checked prices by date</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Marketplace</th>
            <th scope="col">Price</th>
          </tr>
        </thead>
        <tbody>
          {dots
            .slice()
            .sort((a, b) => (a.date < b.date ? -1 : 1))
            .map((d) => (
              <tr key={`${d.platform}-${d.date}-${d.price}`}>
                <td>{dayMonth(d.date)}</td>
                <td>{label(d.platform)}</td>
                <td>{peso(d.price)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

/** Sheet/Product/PriceHistory/Loading (8375:32513), from the shared skeleton. */
function Loading() {
  return (
    <SkeletonRegion label="Loading price history" className="flex flex-col gap-4">
      <div className="flex gap-2">
        {[0, 1, 2, 3].map((i) => (
          <Pill key={i} className="h-8 w-14" />
        ))}
      </div>
      <Block className="h-[200px] w-full" />
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Block key={i} className="h-[76px] w-full" />
        ))}
      </div>
    </SkeletonRegion>
  );
}

export default PriceHistorySheet;

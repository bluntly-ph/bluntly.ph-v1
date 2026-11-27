"use client";

import { useState } from "react";

import { layoutChart, type PriceSeries } from "./price-chart-model";

const W = 320;
const H = 140;

/** One colour per marketplace; unknown ones fall back to ink. */
const COLOUR: Record<string, string> = {
  shopee: "#ee4d2d",
  lazada: "#0f146d",
  amazon: "#ff9900",
  other: "var(--base-gray-400)",
};

const LABEL: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", amazon: "Amazon", other: "Other" };

function peso(n: number): string {
  return `₱${n.toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;
}

/**
 * Price history, one line per marketplace (Business Rules §16). Never blended:
 * a Shopee price and a Lazada price are different offers, and an average of
 * the two is a price nobody paid. Each marketplace can be switched off; the
 * chart re-fits to what is left. A table of the same points follows for
 * screen readers, since a line chart is not something they can read.
 */
export function PriceHistoryChart({ series }: { series: PriceSeries }) {
  const platforms = Object.keys(series).filter((p) => series[p].length > 0);
  const [visible, setVisible] = useState<string[]>(platforms);
  if (platforms.length === 0) return null;

  const chart = layoutChart(series, visible, W, H, 10);

  function toggle(p: string) {
    setVisible((v) => (v.includes(p) ? v.filter((x) => x !== p) : [...v, p]));
  }

  return (
    <div className="mt-4">
      <div role="group" aria-label="Marketplaces shown" className="flex flex-wrap gap-2">
        {platforms.map((p) => {
          const on = visible.includes(p);
          return (
            <button
              key={p}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(p)}
              className={`inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-pill)] px-2.5 py-1 text-[12px] shadow-[var(--shadow-hairline-inset)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] ${
                on ? "text-[var(--text-primary)]" : "text-[var(--text-muted)] line-through"
              }`}
            >
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: COLOUR[p] ?? "var(--text-primary)" }} />
              {LABEL[p] ?? p}
            </button>
          );
        })}
      </div>

      {chart.lines.length === 0 ? (
        <p className="mt-3 text-[12px] text-[var(--text-secondary)]">Choose a marketplace to see its prices.</p>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="mt-3 h-auto w-full"
            role="img"
            aria-label={`Price history from ${chart.firstDate} to ${chart.lastDate}, between ${peso(chart.minPrice)} and ${peso(chart.maxPrice)}.`}
          >
            <line x1="0" y1={H - 1} x2={W} y2={H - 1} stroke="var(--line-hairline-30)" />
            {chart.lines.map((line) => (
              <g key={line.platform} stroke={COLOUR[line.platform] ?? "var(--text-primary)"} fill={COLOUR[line.platform] ?? "var(--text-primary)"}>
                {line.dots.length > 1 ? <path d={line.d} fill="none" strokeWidth={2} strokeLinejoin="round" /> : null}
                {line.dots.map((dot) => (
                  <circle key={`${dot.date}-${dot.price}`} cx={dot.x} cy={dot.y} r={3}>
                    <title>{`${LABEL[line.platform] ?? line.platform} · ${dot.date} · ${peso(dot.price)}`}</title>
                  </circle>
                ))}
              </g>
            ))}
          </svg>
          <div className="mt-1 flex justify-between text-[11px] text-[var(--text-muted)]">
            <span>{chart.firstDate}</span>
            <span>
              {peso(chart.minPrice)} – {peso(chart.maxPrice)}
            </span>
            <span>{chart.lastDate}</span>
          </div>
          <table className="sr-only">
            <caption>Reported prices by marketplace</caption>
            <thead>
              <tr>
                <th scope="col">Marketplace</th>
                <th scope="col">Date</th>
                <th scope="col">Price</th>
              </tr>
            </thead>
            <tbody>
              {chart.lines.flatMap((line) =>
                line.dots.map((dot) => (
                  <tr key={`${line.platform}-${dot.date}-${dot.price}`}>
                    <td>{LABEL[line.platform] ?? line.platform}</td>
                    <td>{dot.date}</td>
                    <td>{peso(dot.price)}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

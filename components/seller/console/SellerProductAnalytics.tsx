import Link from "next/link";

import { CATEGORIES } from "@/lib/landing-data";
import { CompareRow } from "@/components/console/CompareRow";

import { pct, verdictBar, verdictTrend } from "./products-model";

/**
 * Screen/Seller/Products/Analytics (Figma 8205:22802): one linked product's
 * figures for the store that sells it — product reviews from buyers of any
 * store, never the store's own reviews. Built from what the data holds:
 *
 * - the trend is the median of the reviews written each month, beside the
 *   category's;
 * - "What reviewers keep mentioning" groups identical pros and cons, shown once
 *   5 or more reviews share one (the frame's rule);
 * - the frame's "Mention durability problems" row and its topic grouping of
 *   questions have nothing behind them yet: the questions are listed as asked.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type Analytics = Schemas["StoreProductAnalyticsOut"];

const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.slug, c.label]));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monthName = (key: string) => MONTHS[Number(key.slice(5, 7)) - 1] ?? key;

export function SellerProductAnalytics({ storeId, a }: { storeId: string; a: Analytics }) {
  const f = a.figures;
  const category = CATEGORY_LABEL[a.category ?? ""] ?? "its category";
  const lastMonth = a.months.length >= 2 ? monthName(a.months[a.months.length - 2].month) : "";
  const diff = f.median != null && a.category_median != null ? f.median - a.category_median : null;
  const bar = verdictBar(f);
  const worthCount = f.worth_it != null ? Math.round(f.worth_it * f.reviews) : null;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h1 className="min-w-0 flex-1 truncate text-[24px] font-semibold leading-none">{a.name}</h1>
        <span className="rounded-full border border-[var(--border-subtle)] px-3 py-[7px] text-[12px] text-[var(--text-secondary)]">Last 6 months</span>
      </div>

      <section aria-label="At a glance" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Card
          label="Median rating"
          value={f.median != null ? `${f.median.toFixed(1)} / 5` : "—"}
          note={`${f.reviews} review${f.reviews === 1 ? "" : "s"}${f.change_30d != null ? ` · ${f.change_30d >= 0 ? "+" : "−"}${Math.abs(f.change_30d).toFixed(1)} in 30 days` : ""}`}
        />
        <Card label="Worth it" value={pct(f.worth_it)} note={worthCount != null ? `${worthCount} of ${f.reviews} reviewers` : "Needs 5 reviews"} />
        <Card label="Open questions" value={String(f.open_questions)} note={`Of ${f.questions} asked about it`} />
        <Card
          label={`Compared to ${category.toLowerCase()}`}
          value={diff != null ? `${diff >= 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)}` : "—"}
          note={a.category_median != null ? `Category median ${a.category_median.toFixed(1)} · ${a.category_products} products` : "No category figures yet"}
        />
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <section className="rounded-[16px] border border-[var(--border-subtle)] p-5" aria-label="Rating trend">
          <div className="flex flex-wrap items-start gap-3">
            <span className="flex flex-1 flex-col gap-1">
              <h2 className="text-[16px] font-semibold leading-none">Rating trend</h2>
              <span className="text-[12px] text-[var(--text-secondary)]">Median rating of the reviews written each month</span>
            </span>
            <span className="flex items-center gap-3 text-[12px] text-[var(--text-secondary)]">
              <span className="flex items-center gap-1">
                <span className="size-2 rounded-full bg-[var(--accent-primary)]" aria-hidden /> This product
              </span>
              <span className="flex items-center gap-1">
                <span className="h-[2px] w-3 bg-[var(--text-secondary)]" aria-hidden /> {category} median
              </span>
            </span>
          </div>
          <TrendChart months={a.months} />
        </section>

        <section className="rounded-[16px] border border-[var(--border-subtle)] p-5" aria-label="Verdicts">
          <h2 className="text-[16px] font-semibold leading-none">Verdicts</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">What reviewers concluded</p>
          {bar ? (
            <>
              <div className="mt-4 flex h-3 gap-[2px] overflow-hidden rounded-[4px]" aria-hidden>
                <span className="bg-[var(--semantic-success-500)]" style={{ width: `${bar[0]}%` }} />
                <span className="bg-[var(--accent-star)]" style={{ width: `${bar[1]}%` }} />
                <span className="bg-[var(--semantic-danger)]" style={{ width: `${bar[2]}%` }} />
              </div>
              <ul className="mt-2 flex flex-col">
                {(
                  [
                    ["Worth it", f.worth_it, "bg-[var(--semantic-success-500)]", verdictTrend(f.worth_it, a.worth_it_last_month, lastMonth)],
                    ["It’s complicated", f.complicated, "bg-[var(--accent-star)]", ""],
                    ["Not worth it", f.not_worth, "bg-[var(--semantic-danger)]", ""],
                  ] as const
                ).map(([label, share, dot, trend]) => (
                  <li key={label} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0">
                    <span className={`size-2 shrink-0 rounded-full ${dot}`} aria-hidden />
                    <span className="flex flex-1 flex-col gap-1 leading-none">
                      <span className="text-[14px]">{label}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">
                        {Math.round((share ?? 0) * f.reviews)} reviews{trend ? ` · ${trend}` : ""}
                      </span>
                    </span>
                    <span className="text-[14px] font-medium [font-variant-numeric:tabular-nums]">{pct(share)}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-4 text-[14px] text-[var(--text-secondary)]">Not enough reviews yet. Verdicts show from 5 reviews.</p>
          )}
        </section>
      </div>

      <section className="rounded-[16px] border border-[var(--border-subtle)] p-5" aria-label="What reviewers keep mentioning">
        <h2 className="text-[16px] font-semibold leading-none">What reviewers keep mentioning</h2>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">From {f.reviews} reviews. A theme shows once 5 or more reviews mention it.</p>
        {a.complaints.length === 0 && a.praise.length === 0 ? (
          <p className="mt-4 text-[14px] text-[var(--text-secondary)]">No pro or con is shared by 5 reviews yet.</p>
        ) : (
          <div className="mt-4 grid gap-6 md:grid-cols-2">
            <Themes title="Complaints" items={a.complaints} tone="bg-[var(--semantic-danger)]" />
            <Themes title="Praise" items={a.praise} tone="bg-[var(--semantic-success-500)]" />
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-[16px] border border-[var(--border-subtle)] p-5" aria-label={`Compared to ${category}`}>
          <h2 className="text-[16px] font-semibold leading-none">Compared to {category.toLowerCase()}</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{a.category_products} products on Bluntly</p>
          <ul className="mt-2 flex flex-col">
            <CompareRow dense label="Median rating" mine={f.median} theirs={a.category_median} hi={5} format={(v) => v.toFixed(1)} />
            <CompareRow dense label="Worth it" mine={f.worth_it} theirs={a.category_worth_it} hi={1} format={(v) => pct(v)} />
            <CompareRow dense label="Questions answered by a store" mine={a.store_answered} theirs={a.category_store_answered} hi={1} format={(v) => pct(v)} />
          </ul>
        </section>
        <section className="rounded-[16px] border border-[var(--border-subtle)] p-5" aria-label="What buyers ask">
          <div className="flex items-start gap-3">
            <span className="flex flex-1 flex-col gap-1">
              <h2 className="text-[16px] font-semibold leading-none">What buyers ask before buying</h2>
              <span className="text-[12px] text-[var(--text-secondary)]">The latest questions about it. Worth covering on your listing.</span>
            </span>
            <Link href={`/seller/${storeId}/questions`} className="shrink-0 text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
              See questions
            </Link>
          </div>
          {a.recent_questions.length === 0 ? (
            <p className="mt-4 text-[14px] text-[var(--text-secondary)]">No one has asked about it yet.</p>
          ) : (
            <ul className="mt-2 flex flex-col">
              {a.recent_questions.map((q) => (
                <li key={q.id} className="flex items-start gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0">
                  <Link href={`/questions/${q.id}`} className="min-w-0 flex-1 text-[14px] hover:underline">
                    {q.body}
                  </Link>
                  {q.answers ? (
                    <span className="shrink-0 text-[12px] text-[var(--text-secondary)]">
                      {q.answers} answer{q.answers === 1 ? "" : "s"}
                    </span>
                  ) : (
                    <span className="shrink-0 rounded-full bg-[var(--status-high-bg)] px-2 py-[2px] text-[12px] text-[var(--status-high-fg)]">Unanswered</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <p className="text-[12px] text-[var(--text-secondary)]">These are product reviews from buyers of any store that sells it. Reviews of your store are under Reviews.</p>
    </div>
  );
}

function Card({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <span className="truncate text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
      <span className="text-[12px] text-[var(--text-secondary)]">{note}</span>
    </div>
  );
}

function Themes({ title, items, tone }: { title: string; items: { text: string; reviews: number; share: number }[]; tone: string }) {
  return (
    <div>
      <p className="pb-2 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]">{title}</p>
      {items.length === 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">None shared by 5 reviews yet.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((t) => (
            <li key={t.text} className="flex flex-col gap-1">
              <span className="flex items-center gap-3">
                <span className="flex-1 text-[14px]">{t.text}</span>
                <span className="text-[12px] text-[var(--text-secondary)]">
                  {t.reviews} reviews · {pct(t.share)}
                </span>
              </span>
              <span className="h-[5px] overflow-hidden rounded-full bg-[var(--surface-app)]" aria-hidden>
                <span className={`block h-full ${tone}`} style={{ width: `${Math.min(100, t.share * 100)}%` }} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The rating trend: this product's monthly median (dots) over the category's (line). */
function TrendChart({ months }: { months: { month: string; median?: number | null; category_median?: number | null }[] }) {
  const W = 560;
  const H = 190;
  const top = 22;
  const left = 32;
  // The axis starts at 3 unless a month sits lower; a point is never drawn
  // off its own value.
  const values = months.flatMap((m) => [m.median, m.category_median]).filter((v): v is number => v != null);
  const lo = Math.min(3, Math.floor(Math.min(...values, 3) * 2) / 2);
  const hi = 5;
  const ticks = Array.from({ length: Math.round((hi - lo) / 0.5) + 1 }, (_, i) => lo + i * 0.5);
  const x = (i: number) => left + (i * (W - left - 16)) / Math.max(1, months.length - 1);
  const y = (v: number) => top + ((hi - Math.max(lo, Math.min(hi, v))) / (hi - lo)) * (H - top - 24);
  const path = (key: "median" | "category_median") =>
    months
      .map((m, i) => [i, m[key]] as const)
      .filter(([, v]) => v != null)
      .map(([i, v], k) => `${k === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v as number).toFixed(1)}`)
      .join(" ");
  const has = months.some((m) => m.median != null);
  return (
    <figure className="mt-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Median rating per month, this product and its category">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={left} x2={W - 8} y1={y(v)} y2={y(v)} stroke="var(--border-subtle)" strokeWidth={1} />
            <text x={0} y={y(v) + 4} fontSize={11} fill="var(--text-secondary)">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        <path d={path("category_median")} fill="none" stroke="var(--text-secondary)" strokeWidth={2} />
        <path d={path("median")} fill="none" stroke="var(--accent-primary)" strokeWidth={2} />
        {months.map((m, i) =>
          m.median != null ? (
            <g key={m.month}>
              <circle cx={x(i)} cy={y(m.median)} r={4} fill="var(--surface-card)" stroke="var(--accent-primary)" strokeWidth={2} />
              <text x={x(i)} y={y(m.median) - 9} fontSize={11} textAnchor="middle" fill="var(--text-secondary)">
                {m.median.toFixed(1)}
              </text>
            </g>
          ) : null,
        )}
        {months.map((m, i) => (
          <text key={`l-${m.month}`} x={x(i)} y={H - 4} fontSize={12} textAnchor="middle" fill="var(--text-secondary)">
            {monthName(m.month)}
          </text>
        ))}
      </svg>
      {!has ? <figcaption className="text-[12px] text-[var(--text-secondary)]">No reviews were written in the last 6 months.</figcaption> : null}
    </figure>
  );
}

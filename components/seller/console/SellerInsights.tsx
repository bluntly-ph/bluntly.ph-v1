import Link from "next/link";

import { PLATFORM_LABEL, type SellerPlatform } from "@/components/sellers/seller-model";
import { CompareRow } from "@/components/console/CompareRow";

import { ExportButton } from "./ExportDialog";
import {
  fmtScore,
  hoursLabel,
  monthShort,
  pct,
  replyBars,
  replyTrend,
  reviewsNote,
  scoreSince,
  shareSince,
  sparkPoints,
  tileChange,
  type InsightsMonth,
  type MonthKey,
} from "./insights-model";
import { PeriodMenu } from "./PeriodMenu";

/**
 * Screen/Seller/Insights (Figma 8208:22905): the store's own reviews over the
 * chosen period. Store reviews only; product figures are under Products.
 *
 * Every rating is a median, every share a plain proportion of the period's
 * reviews. "Compared to similar stores" is the median store on the same
 * marketplace with 5 or more reviews in the period: stores carry no category,
 * so the frame's "electronics stores" cannot be drawn.
 *
 * NOT DRAWN, because nothing holds it: "What buyers say about your store". A
 * store review is free text with no pros, cons or tags to count, so the card
 * says that instead of inventing themes.
 */

type Insights = import("@/lib/api-types").components["schemas"]["StoreInsightsOut"];

const UP = "text-[var(--accent-success)]";
const DOWN = "text-[var(--accent-danger)]";
const CARD = "rounded-[16px] border border-[var(--border-subtle)] p-5";
const platformLabel = (p: string) => PLATFORM_LABEL[p as SellerPlatform] ?? p;

export function SellerInsights({ storeId, data }: { storeId: string; data: Insights }) {
  const months = data.months as InsightsMonth[];
  const empty = data.reviews === 0;
  const firstMonth = months.find((m) => m.reviews > 0)?.month ?? null;
  const peers = data.peers && data.peers.stores >= 3 ? data.peers : null;
  const reply = replyTrend(data.reply_hours, data.reply_hours_first, firstMonth);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex-1 text-[24px] font-semibold leading-none">Insights</h1>
        <Link
          href={`/sellers/${storeId}/reports`}
          className="flex h-9 items-center rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]"
        >
          Rating summary report
        </Link>
        <ExportButton storeId={storeId} period={data.period} />
        <PeriodMenu storeId={storeId} period={data.period} base={`/seller/${storeId}/insights`} />
      </div>

      <section aria-label="At a glance" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Store rating" value={data.rating != null ? `${fmtScore(data.rating)} / 5` : "—"} note={empty ? "No reviews in this period" : scoreSince(months, "rating", data.rating)} />
        <Tile label="Reviews of your store" value={String(data.reviews)} note={reviewsNote(data.reviews, data.reviews_before, data.period)} />
        <Tile label="Would recommend" value={pct(data.recommend)} note={empty ? "No reviews in this period" : shareSince(months, "recommend", data.recommend)} />
        <Tile label="Response rate" value={pct(data.responded)} note={empty ? "No reviews in this period" : shareSince(months, "responded", data.responded)} />
      </section>

      <section aria-label="Order facts" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SparkTile label="Matched the listing" value={pct(data.matched)} now={data.matched} months={months} k="matched" kind="share" />
        <SparkTile label="Complete orders" value={pct(data.complete)} now={data.complete} months={months} k="complete" kind="share" />
        <SparkTile label="Customer service" value={data.service != null ? `${fmtScore(data.service)} / 5` : "—"} now={data.service} months={months} k="service" kind="score" />
        <SparkTile label="Packaging" value={data.packaging != null ? `${fmtScore(data.packaging)} / 5` : "—"} now={data.packaging} months={months} k="packaging" kind="score" />
      </section>

      <section className={CARD} aria-label="What buyers say about your store">
        <h2 className="text-[16px] font-semibold leading-none">What buyers say about your store</h2>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
          From {data.reviews} store review{data.reviews === 1 ? "" : "s"}.
        </p>
        <p className="mt-4 rounded-[12px] bg-[var(--surface-app)] px-4 py-3 text-[14px] text-[var(--text-secondary)]">
          Store reviews are written in buyers’ own words, without tags, so there are no themes to count yet.{" "}
          <Link href={`/seller/${storeId}/reviews`} className="text-[var(--chart-honesty-fund)] hover:underline">
            Read them under Reviews
          </Link>
          .
        </p>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className={CARD} aria-label="Your replies over time">
          <h2 className="text-[16px] font-semibold leading-none">Your replies over time</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">Share of reviews you responded to, by month</p>
          <ReplyBars months={months} />
          <div className="mt-4 flex flex-wrap items-baseline gap-2 border-t border-[var(--border-subtle)] pt-4">
            <span className="flex-1 text-[14px]">Median time to reply</span>
            <span className="text-[14px] font-medium [font-variant-numeric:tabular-nums]">{hoursLabel(data.reply_hours)}</span>
            {reply ? <span className={`text-[12px] ${reply.tone === "up" ? UP : reply.tone === "down" ? DOWN : "text-[var(--text-secondary)]"}`}>{reply.text}</span> : null}
          </div>
        </section>

        <section className={CARD} aria-label="Compared to similar stores">
          <div className="flex flex-wrap items-start gap-3">
            <span className="flex flex-1 flex-col gap-1">
              <h2 className="text-[16px] font-semibold leading-none">Compared to similar stores</h2>
              <span className="text-[12px] text-[var(--text-secondary)]">
                {peers
                  ? `${peers.stores} ${platformLabel(data.platform)} stores on Bluntly with 5 or more reviews in this period`
                  : `${platformLabel(data.platform)} stores on Bluntly`}
              </span>
            </span>
            <span className="flex items-center gap-3 text-[12px] text-[var(--text-secondary)]">
              <span className="flex items-center gap-1">
                <span className="size-2 rounded-full bg-[var(--accent-primary)]" aria-hidden /> You
              </span>
              <span className="flex items-center gap-1">
                <span className="h-3 w-[2px] bg-[var(--text-primary)]" aria-hidden /> Median store
              </span>
            </span>
          </div>
          {peers ? (
            <ul className="mt-2 flex flex-col">
              <CompareRow toned label="Store rating" mine={data.rating} theirs={peers.rating} lo={1} hi={5} format={(v) => fmtScore(v)} />
              <CompareRow toned label="Would recommend" mine={data.recommend} theirs={peers.recommend} lo={0} hi={1} format={pct} />
              <CompareRow toned label="Packaging" mine={data.packaging} theirs={peers.packaging} lo={1} hi={5} format={(v) => `${fmtScore(v)} / 5`} />
              <CompareRow toned label="Response rate" mine={data.responded} theirs={peers.responded} lo={0} hi={1} format={pct} />
            </ul>
          ) : (
            <p className="mt-4 text-[14px] text-[var(--text-secondary)]">
              Not enough {platformLabel(data.platform)} stores have 5 or more reviews in this period to compare with yet.
            </p>
          )}
        </section>
      </div>
      <p className="text-[12px] text-[var(--text-secondary)]">Store reviews only. Product analytics are under Products.</p>
    </div>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className={`${CARD} flex flex-col gap-2`}>
      <span className="truncate text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
      <span className="min-h-[18px] text-[12px] text-[var(--text-secondary)]">{note}</span>
    </div>
  );
}

function SparkTile({
  label,
  value,
  now,
  months,
  k,
  kind,
}: {
  label: string;
  value: string;
  now?: number | null;
  months: InsightsMonth[];
  k: MonthKey;
  kind: "share" | "score";
}) {
  const W = 200;
  const H = 40;
  const change = tileChange(months, k, kind, now);
  const pts = sparkPoints(months, k, W, H, kind);
  const stroke = change?.tone === "down" ? "var(--accent-danger)" : "var(--accent-success)";
  const last = pts[pts.length - 1];
  return (
    <div className={`${CARD} flex flex-col gap-2`}>
      <span className="truncate text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="flex items-baseline gap-2">
        <span className="text-[20px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
        {change ? <span className={`text-[12px] ${change.tone === "up" ? UP : change.tone === "down" ? DOWN : "text-[var(--text-secondary)]"}`}>{change.text}</span> : null}
      </span>
      <svg viewBox={`-4 0 ${W + 8} ${H}`} className="mt-2 h-10 w-full" role="img" aria-label={`${label} by month`} preserveAspectRatio="none">
        {pts.length > 1 ? (
          <polyline points={pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")} fill="none" stroke={stroke} strokeWidth={2} vectorEffect="non-scaling-stroke" />
        ) : null}
        {last ? <circle cx={last.x} cy={last.y} r={3} fill={stroke} /> : null}
      </svg>
      <span className="flex justify-between text-[11px] text-[var(--text-secondary)]">
        <span>{months.length ? monthShort(months[0].month) : ""}</span>
        <span>{months.length ? monthShort(months[months.length - 1].month) : ""}</span>
      </span>
    </div>
  );
}

function ReplyBars({ months }: { months: InsightsMonth[] }) {
  const bars = replyBars(months);
  return (
    <div className="mt-6 flex h-[180px] items-end gap-2" role="img" aria-label="Share of reviews you responded to, by month">
      {bars.map((b) => (
        <div key={b.month} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
          <span className="text-[12px] text-[var(--text-secondary)] [font-variant-numeric:tabular-nums]">{b.share != null ? pct(b.share) : "—"}</span>
          <span
            className={`w-full rounded-t-[6px] ${b.current ? "bg-[var(--accent-success)]" : "bg-[color-mix(in_srgb,var(--accent-success)_35%,transparent)]"}`}
            style={{ height: `${b.share != null ? Math.max(2, b.share * 120) : 0}px` }}
          />
          <span className="text-[12px] text-[var(--text-secondary)]">{monthShort(b.month)}</span>
        </div>
      ))}
    </div>
  );
}


import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowFatUp, CaretRight, ChatCircle, Info } from "@phosphor-icons/react/dist/ssr";

import { DashboardBar } from "@/components/dashboard/DashboardBar";
import { DashboardSelect } from "@/components/dashboard/DashboardSelect";
import { Money, ParentLink, ReachRings } from "@/components/dashboard/DashboardParts";
import { ReviewChooser } from "@/components/dashboard/ReviewChooser";
import { CommissionBreakdownSheet } from "@/components/dashboard/CommissionBreakdownSheet";
import { commissionArcLabels, compact, earningsLine, pesoSplit, voteBars } from "@/components/dashboard/contributor-model";
import { StarRow } from "@/components/sellers/SellerIdentity";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getPerformance, type Performance } from "@/lib/dashboard";
import { trustLevel } from "@/lib/trust";
import { QuickActions } from "@/components/site/QuickActions";

export const metadata: Metadata = { title: "Performance — bluntly" };

/**
 * Performance, built to Figma Screen/Performance 7848:9542 (meeting
 * 2026-10-02, 4:58): all reviews or one product (the Switcher), then the
 * review card, earnings over the last 30 days, helpful / not-helpful votes,
 * the view-to-buy rings, where the commission went, where buyers bought, and
 * the reviews ranked by what they earned.
 *
 * Every figure is GET /users/me/performance: views from the view counters,
 * votes, link clicks, and the commission breakdown (`commission`: every sale
 * the marketplaces reported for the member, gross to net). "Earned", "Where
 * the commission went" and its ⓘ sheet (Figma 9057:47088), and "Where they
 * bought" all read that one breakdown, so they can never disagree.
 * Not drawn, because nothing records them per review: bookmarks (no server
 * record exists) and shares (only in reading telemetry, which never feeds
 * money screens); the frame's title sort icon has no behaviour in the file.
 */

const PERIODS = [
  { value: "week", label: "Weekly" },
  { value: "month", label: "Monthly" },
];
const PLATFORM: Record<string, { label: string; colour: string }> = {
  shopee: { label: "Shopee", colour: "#ee4d2d" },
  lazada: { label: "Lazada", colour: "#0f146d" },
};
const PLOT_W = 292;
const PLOT_H = 112;

function Card({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={label} className={`w-full rounded-[32px] bg-[var(--surface-app)] ${className}`}>
      {children}
    </section>
  );
}

function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`w-full rounded-[32px] bg-[var(--surface-card)] ${className}`}>{children}</div>;
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <span className="text-[12px] leading-none text-[var(--base-gray-400)]">{label}</span>
      <span className="text-[20px] font-semibold leading-none text-[var(--text-primary)]">{children}</span>
    </div>
  );
}

function ReviewCard({ p, title }: { p: Performance; title: string }) {
  const rating = p.rating === null ? null : Number(p.rating);
  return (
    <Card label={title} className="p-[3px]">
      <div className="flex flex-col gap-[6px] px-[14px] pb-[14px] pt-[14px]">
        <h2 className="text-[16px] font-semibold leading-none text-[var(--text-primary)]">{title}</h2>
        <div className="flex items-center gap-2">
          <StarRow value={rating} size={16} gap={2} />
          <span className="text-[12px] leading-none text-[var(--base-gray-400)]">
            {rating === null ? "No rating yet" : `${p.rating} average`} · {p.review_count} {p.review_count === 1 ? "review" : "reviews"}
          </span>
        </div>
      </div>
      <Panel className="flex gap-3 p-5">
        {/* Net earnings: the breakdown's "You", so this, the donut and the sheet agree. */}
        <Stat label="Earned">
          <Money value={p.commission?.you ?? p.earned} whole="text-[20px]" cents="text-[12px]" />
        </Stat>
        <Stat label="Views">{compact(p.totals.views)}</Stat>
        <Stat label="Helped">{compact(p.totals.helped)}</Stat>
      </Panel>
      <ul className="flex px-[14px] pb-4 pt-[14px]" aria-label="Community, all time">
        <li className="flex flex-1 items-center justify-center gap-[6px] text-[14px] font-semibold leading-none">
          <ArrowFatUp size={18} weight="fill" aria-hidden />
          <span>{compact(p.upvotes)}</span>
          <span className="sr-only">helpful votes</span>
        </li>
        <li className="flex flex-1 items-center justify-center gap-[6px] text-[14px] font-semibold leading-none">
          <ChatCircle size={18} aria-hidden />
          <span>{compact(p.comments)}</span>
          <span className="sr-only">comments</span>
        </li>
      </ul>
    </Card>
  );
}

function EarningsCard({ p }: { p: Performance }) {
  const { points, top } = earningsLine(p.daily.map((d) => d.earned), PLOT_W, PLOT_H - 22);
  const first = p.daily[0]?.day;
  // The frame's x labels: the first day as "Sep 1", then every 7th day's date.
  const ticks = p.daily
    .map((d, i) => ({ i, day: new Date(`${d.day}T00:00:00+08:00`) }))
    .filter(({ i }) => i % 7 === 0)
    .map(({ i, day }) => ({
      x: (i / Math.max(p.daily.length - 1, 1)) * PLOT_W,
      label: i === 0 ? `${day.toLocaleString("en-US", { month: "short", timeZone: "Asia/Manila" })} ${day.getDate()}` : String(day.getDate()),
    }));
  const week = Number(p.earned_7d);
  return (
    <Card label="Earnings" className="p-[3px]">
      <div className="flex items-start px-[14px] pb-[14px] pt-[14px]">
        <div className="flex flex-1 flex-col gap-[2px] leading-none">
          <h2 className="text-[16px] font-semibold text-[var(--text-primary)]">Earnings</h2>
          <span className="text-[12px] text-[var(--base-gray-400)]">Last 30 days</span>
        </div>
        <div className="flex flex-col items-end gap-[2px]">
          <Money value={p.earned_30d} whole="text-[24px]" cents="text-[16px]" />
          {week > 0 ? (
            <span className="text-[12px] font-medium leading-none text-[var(--semantic-success-500)]">
              +{pesoSplit(p.earned_7d)[0]} this week
            </span>
          ) : null}
        </div>
      </div>
      <Panel className="flex flex-col gap-3 px-4 py-5">
        <div className="flex justify-end">
          <span className="inline-flex h-[30px] items-center rounded-[32px] border border-[var(--border-subtle)] px-[14px] text-[12px] font-medium leading-none">
            30 days
          </span>
        </div>
        <figure className="relative h-[150px] w-full" aria-label={`Earned per day since ${first ?? "30 days ago"}`}>
          <svg viewBox={`-24 -7 ${PLOT_W + 28} 150`} className="h-full w-full overflow-visible" preserveAspectRatio="none" aria-hidden>
            {[0, 0.5, 1].map((f) => (
              <g key={f}>
                <line x1={0} x2={PLOT_W} y1={f * (PLOT_H - 22)} y2={f * (PLOT_H - 22)} stroke="rgba(0,0,0,0.15)" strokeWidth={0.5} />
                <text x={-24} y={f * (PLOT_H - 22) + 3} fontSize={10} fill="rgba(0,0,0,0.5)">
                  {pesoSplit(String(top * (1 - f)))[0]}
                </text>
              </g>
            ))}
            <polyline points={points} fill="none" stroke="var(--semantic-success-500)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
            {ticks.map((t) => (
              <text key={t.x} x={t.x} y={PLOT_H + 18} fontSize={10} fill="rgba(0,0,0,0.5)">
                {t.label}
              </text>
            ))}
          </svg>
        </figure>
      </Panel>
    </Card>
  );
}

function VotesCard({ p }: { p: Performance }) {
  const bars = voteBars(p.buckets);
  return (
    <Card label="Votes" className="p-[3px]">
      <Panel className="flex flex-col gap-4 p-5">
        <div className="flex items-center">
          <h2 className="flex-1 text-[16px] font-semibold leading-none">Votes</h2>
          <DashboardSelect param="period" value={p.period} label="Period" options={PERIODS} />
        </div>
        <div className="flex gap-6 leading-none">
          <div className="flex flex-1 flex-col gap-1">
            <span className="text-[12px] text-[var(--base-gray-400)]">Helpful</span>
            <span className="text-[24px] font-semibold">{p.helpful.toLocaleString("en-US")}</span>
          </div>
          <div className="flex flex-1 flex-col gap-1 text-[var(--base-gray-400)]">
            <span className="text-[12px]">Not helpful</span>
            <span className="text-[24px] font-semibold">{p.not_helpful.toLocaleString("en-US")}</span>
          </div>
        </div>
      </Panel>
      <ol className="flex gap-3 px-5 pb-4 pt-5" aria-label="Helpful and not helpful votes per period">
        {p.buckets.map((b, i) => (
          <li key={b.start} className="flex min-w-0 flex-1 flex-col items-center" aria-label={`${b.label}: ${b.up} helpful, ${b.down} not helpful`}>
            <span className="flex h-20 w-full flex-col justify-end">
              {bars[i].up > 0 ? <span className="w-full rounded-[8px] bg-[var(--semantic-success-500)]" style={{ height: bars[i].up }} /> : null}
            </span>
            <span className="h-[6px]" />
            <span className="flex h-5 w-full flex-col">
              {bars[i].down > 0 ? <span className="w-full rounded-[8px] bg-[var(--base-gray-200)]" style={{ height: bars[i].down }} /> : null}
            </span>
            <span className={`text-[10px] leading-none ${b.current ? "text-[var(--text-primary)]" : "text-[var(--base-gray-400)]"}`}>{b.label}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function CommissionCard({ p }: { p: Performance }) {
  const parts = [
    { key: "you", label: "You", value: Number(p.share_you), colour: "var(--accent-primary)", ink: "#fff" },
    { key: "fund", label: "Honesty Fund", value: Number(p.share_honesty_fund), colour: "var(--chart-honesty-fund)", ink: "#fff" },
    { key: "bluntly", label: "Bluntly", value: Number(p.share_platform), colour: "var(--base-gray-200)", ink: "var(--text-primary)" },
  ];
  const total = parts.reduce((a, b) => a + Math.max(b.value, 0), 0);
  const size = 196;
  const band = 26;
  const r = (size - band) / 2;
  const c = 2 * Math.PI * r;
  const gap = band + 6;
  // Each share's amount on its own arc (owner request 2026-10-06), not in the legend.
  const labels = total > 0 ? commissionArcLabels(parts, size, band, gap) : [];
  let start = 0;
  return (
    <Card label="Where the commission went" className="p-[3px]">
      <Panel className="flex flex-col items-center gap-4 p-5">
        <div className="flex w-full items-center">
          <h2 className="flex-1 text-[16px] font-semibold leading-none">Where the commission went</h2>
          {p.commission ? (
            <CommissionBreakdownSheet breakdown={p.commission} />
          ) : (
            <Link href="/how-it-works" aria-label="How commission is split" className="grid size-8 place-items-center rounded-full bg-[var(--surface-app)]">
              <Info size={16} aria-hidden />
            </Link>
          )}
        </div>
        <div className="relative grid size-[196px] place-items-center">
          <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 -rotate-90" aria-hidden>
            {total <= 0 ? (
              <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-app)" strokeWidth={band} />
            ) : (
              parts.map((part) => {
                const len = Math.max(part.value, 0) / total;
                const arc = len > 0 ? (
                  <circle
                    key={part.label}
                    cx={size / 2}
                    cy={size / 2}
                    r={r}
                    fill="none"
                    stroke={part.colour}
                    strokeWidth={band}
                    strokeLinecap="round"
                    strokeDasharray={`${Math.max(len * c - gap, 0.01)} ${c}`}
                    strokeDashoffset={-(start * c + gap / 2)}
                  />
                ) : null;
                start += len;
                return arc;
              })
            )}
          </svg>
          {labels.some((l) => l.show) ? (
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="absolute inset-0" aria-hidden>
              {labels.map((l, i) =>
                l.show ? (
                  <g key={l.key}>
                    <path id={`commission-arc-${l.key}`} d={l.d} fill="none" />
                    <text fontSize={11} fontWeight={600} fill={parts[i].ink} dominantBaseline="central" textAnchor="middle">
                      <textPath href={`#commission-arc-${l.key}`} startOffset="50%">
                        {l.text}
                      </textPath>
                    </text>
                  </g>
                ) : null,
              )}
            </svg>
          ) : null}
          {total > 0 ? (
            <ul className="sr-only">
              {parts.map((part) => (
                <li key={part.key}>{`${part.label}: ${pesoSplit(String(part.value)).join("")}`}</li>
              ))}
            </ul>
          ) : null}
          <div className="relative flex flex-col items-center gap-[2px]">
            <span className="text-[12px] leading-none text-[var(--base-gray-400)]">Your share</span>
            <Money value={p.share_you} whole="text-[24px]" cents="text-[16px]" />
          </div>
        </div>
        <ul className="flex flex-wrap justify-center gap-[14px] pt-1">
          {parts.map((part) => (
            <li key={part.label} className="flex items-center gap-[6px] text-[12px] leading-none">
              <span aria-hidden className="size-2 rounded-full" style={{ background: part.colour }} />
              <span className="text-[var(--base-gray-400)]">{part.label}</span>
              <span className="font-medium">{total > 0 ? `${Math.round((Math.max(part.value, 0) / total) * 100)}%` : "—"}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </Card>
  );
}

function BuyersCard({ p }: { p: Performance }) {
  const total = p.orders.reduce((a, o) => a + o.orders, 0);
  return (
    <Card label="Where they bought" className="p-[3px]">
      <Panel className="flex flex-col gap-3 p-5">
        <h2 className="text-[16px] font-semibold leading-none">Where they bought</h2>
        {total > 0 ? (
          <>
            <div className="flex w-full gap-[3px]" aria-hidden>
              {p.orders.map((o) => (
                <span key={o.platform} className="h-3 min-w-px rounded-[6px]" style={{ flex: `${o.orders} 0 0`, background: PLATFORM[o.platform]?.colour ?? "var(--base-gray-400)" }} />
              ))}
            </div>
            <ul className="flex flex-wrap gap-4">
              {p.orders.map((o) => (
                <li key={o.platform} className="flex items-center gap-[6px] text-[12px] leading-none">
                  <span aria-hidden className="size-2 rounded-full" style={{ background: PLATFORM[o.platform]?.colour ?? "var(--base-gray-400)" }} />
                  <span className="font-medium">{PLATFORM[o.platform]?.label ?? o.platform}</span>
                  <span className="text-[var(--base-gray-400)]">
                    {o.orders} {o.orders === 1 ? "order" : "orders"}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-[12px] leading-[1.5] text-[var(--base-gray-400)]">No orders through your links in this period yet.</p>
        )}
      </Panel>
    </Card>
  );
}

function YourReviews({ p }: { p: Performance }) {
  const rows = [...p.products].sort((a, b) => Number(b.earned) - Number(a.earned) || b.views - a.views).slice(0, 5);
  const count = p.products.reduce((a, x) => a + x.reviews, 0);
  return (
    <Card label="Your reviews" className="p-[3px]">
      <Panel className="flex flex-col gap-4 p-5">
        <div className="flex items-center">
          <h2 className="flex-1 text-[12px] font-normal leading-normal text-[var(--chart-honesty-fund)]">Your reviews</h2>
          <span className="text-[12px] font-medium leading-none">Most earned</span>
        </div>
        {rows.length === 0 ? (
          <p className="text-[12px] text-[var(--base-gray-400)]">Publish a review to see how it does.</p>
        ) : (
          <ul className="flex flex-col">
            {rows.map((r, i) => (
              <li key={r.product_id} className={i > 0 ? "border-t border-[var(--border-subtle)] pt-4 mt-4" : ""}>
                <Link href={`/dashboard/insights?product=${r.product_id}`} className="flex items-center gap-3">
                  {r.image_url ? (
                    <Image src={r.image_url} alt="" width={44} height={44} unoptimized className="size-11 shrink-0 rounded-[12px] object-cover" />
                  ) : (
                    <span aria-hidden className="size-11 shrink-0 rounded-[12px] bg-[var(--surface-app)]" />
                  )}
                  <span className="flex min-w-0 flex-1 flex-col gap-[2px] leading-none">
                    {/* Two lines, as the frame wraps "Jisulife Handheld Fan / Life9". */}
                    <span className="line-clamp-2 text-[14px] font-medium leading-[20px] text-[var(--text-primary)]">{r.name}</span>
                    <span className="text-[12px] text-[var(--base-gray-400)]">
                      {compact(r.views)} views · {compact(r.helped)} helped
                    </span>
                  </span>
                  <span className="flex flex-col items-end leading-none">
                    <Money value={r.earned} whole="text-[16px]" cents="text-[12px]" />
                    <span className="text-[10px] text-[var(--base-gray-400)]">earned</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <Link href="/dashboard/reviews" className="flex items-center justify-center gap-1 px-5 pb-4 pt-[14px] text-[12px] font-medium leading-none">
        See all {count} {count === 1 ? "review" : "reviews"}
        <CaretRight size={12} aria-hidden />
      </Link>
    </Card>
  );
}

export default async function PerformancePage({
  searchParams,
}: {
  searchParams: Promise<{ product?: string; period?: string }>;
}) {
  const me = await requireOnboardedUser();
  const params = await searchParams;
  const period = params.period === "month" ? "month" : "week";
  let p = await getPerformance(params.product ?? null, period);
  // A product link that is no longer yours (or a typo) falls back to all reviews.
  if (p === null && params.product) p = await getPerformance(null, period);
  const product = p?.products.find((x) => x.product_id === p?.product_id) ?? null;
  const title = product ? product.name : "All reviews";
  const count = p?.products.reduce((a, x) => a + x.reviews, 0) ?? 0;

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <DashboardBar backHref="/dashboard" trustLevel={trustLevel(me.trust_level_name, me.trust_stage)} />
      </div>
      <main className="mx-auto flex w-full max-w-[390px] flex-col gap-4 px-4 pb-10 md:max-w-[480px] md:pt-8">
        <div className="flex flex-col">
          <ParentLink href="/dashboard" label="Dashboard" />
          <h1 className="px-1 text-[24px] font-semibold leading-none text-[var(--text-primary)]">Performance</h1>
        </div>
        {p === null ? (
          <p role="alert" className="rounded-[32px] bg-[var(--surface-app)] p-6 text-center text-[14px] text-[var(--text-secondary)]">
            Your performance could not be loaded. Nothing here is a zero; try again in a moment.
          </p>
        ) : (
          <>
            <div className="flex items-center gap-2 px-1">
              <ReviewChooser
                value={p.product_id ?? ""}
                products={p.products}
                totalReviews={count}
                totalEarned={p.products.reduce((a, x) => a + Number(x.earned), 0).toFixed(2)}
                periodLabel={period === "month" ? "this month" : "this week"}
              />
              <span className="shrink-0 text-[12px] leading-none text-[var(--base-gray-400)]">
                {product ? `${product.reviews} of ${count}` : count} {count === 1 ? "review" : "reviews"}
              </span>
            </div>
            <ReviewCard p={p} title={title} />
            <EarningsCard p={p} />
            <VotesCard p={p} />
            {p.reach_week && p.reach_prev_week ? (
              <Card label="From view to buy" className="flex flex-col gap-3 overflow-hidden px-5 pt-5">
                <h2 className="text-[16px] font-semibold leading-none">From view to buy</h2>
                <ReachRings now={p.reach_week} before={p.reach_prev_week} suffix="this week" label="The last 7 days: views, people helped, link clicks and purchases" />
              </Card>
            ) : null}
            <CommissionCard p={p} />
            <BuyersCard p={p} />
            <YourReviews p={p} />
          </>
        )}
      </main>
      {/* Screen/Performance draws QuickActions/Button. */}
      <QuickActions />
    </div>
  );
}

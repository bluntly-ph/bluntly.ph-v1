import Link from "next/link";
import { CaretDown, CaretUp } from "@phosphor-icons/react/dist/ssr";

import { AdminExportButton } from "@/components/admin/export/AdminExport";

import { hoursMinutes, oldestWaiting } from "./analytics-model";

type Summary = import("@/lib/api-types").components["schemas"]["AnalyticsSummaryOut"];

const RANGES: [string, string][] = [
  ["7d", "7D"],
  ["30d", "30D"],
  ["90d", "90D"],
  ["12m", "12M"],
];
const LABEL: Record<string, string> = {
  reviews_published: "Reviews published",
  votes_cast: "Votes cast",
  affiliate_clicks: "Affiliate clicks",
  orders: "Orders",
  commission: "Commission",
  review_views: "Review views",
};
const STAGE = ["Newcomer", "Contributor", "Verified Buyer", "Established", "Trusted", "Community Expert"];
/** Reviewers by stage: light grey for Newcomer to ink for Community Expert, as drawn. */
const STAGE_TONE = [
  "bg-[var(--base-gray-200)]",
  "bg-[var(--base-gray-300)]",
  "bg-[var(--base-gray-400)]",
  "bg-[var(--base-gray-500)]",
  "bg-[var(--base-gray-600)]",
  "bg-[var(--text-primary)]",
];
const n = (v: number | string) => Number(v).toLocaleString("en-PH", { maximumFractionDigits: 0 });
const CARD = "rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4";

function Peso({ value }: { value: number | string }) {
  const [whole, cents] = Number(value).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).split(".");
  return (
    <span className="[font-variant-numeric:tabular-nums]">
      ₱{whole}
      <span className="text-[var(--text-secondary)]">.{cents}</span>
    </span>
  );
}

function Delta({ current, previous }: { current: number; previous: number }) {
  if (!previous) return <span className="text-[12px] text-[var(--text-secondary)]">{current ? "new vs previous" : "none in either period"}</span>;
  const pct = ((current - previous) / previous) * 100;
  const up = pct >= 0;
  return (
    <span className={`flex items-center gap-1 text-[12px] ${up ? "text-[var(--accent-success)]" : "text-[var(--accent-danger)]"}`}>
      {up ? <CaretUp size={10} weight="fill" aria-hidden /> : <CaretDown size={10} weight="fill" aria-hidden />}
      {Math.abs(pct).toFixed(1)}%<span className="text-[var(--text-secondary)]">vs previous</span>
    </span>
  );
}

function Bar({ label, value, max, right }: { label: string; value: number; max: number; right: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="flex justify-between text-[14px]">
        <span>{label}</span>
        <span className="[font-variant-numeric:tabular-nums]">{right}</span>
      </p>
      <span className="block h-[6px] rounded-full bg-[var(--surface-app)]">
        <span className="block h-full rounded-full bg-[var(--accent-primary)]" style={{ width: `${max ? Math.min(100, Math.max(1, Math.round((value / max) * 100))) : 0}%` }} />
      </span>
    </div>
  );
}

function Chart({ data, unit }: { data: Summary["series"]; unit: string }) {
  const W = 640;
  const H = 180;
  const max = Math.max(1, ...data.map((d) => Math.max(d.current, d.previous)));
  const step = W / Math.max(1, data.length);
  const bw = Math.max(2, step - 4);
  const y = (v: number) => H - (v / max) * H;
  const line = data.map((d, i) => `${i ? "L" : "M"}${(i * step + step / 2).toFixed(1)},${y(d.previous).toFixed(1)}`).join(" ");
  const fmt = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Asia/Manila" });
  const ticks = [0, Math.floor(data.length / 3), Math.floor((2 * data.length) / 3), data.length - 1].filter((v, i, a) => v >= 0 && a.indexOf(v) === i);
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H + 18}`} className="h-auto w-full" role="img" aria-label={`Reviews published per ${unit}, with the previous period`}>
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <line key={f} x1={0} x2={W} y1={y(max * f)} y2={y(max * f)} stroke="var(--border-subtle)" strokeWidth={1} />
        ))}
        {data.map((d, i) => (
          <g key={d.start}>
            <rect x={i * step + 2} y={y(d.current)} width={bw} height={Math.max(0, H - y(d.current))} rx={Math.min(4, bw / 2)} fill="var(--accent-primary)">
              <title>{`${fmt(d.start)}: ${d.current} published (previous period ${d.previous})`}</title>
            </rect>
          </g>
        ))}
        <path d={line} fill="none" stroke="var(--text-primary)" strokeWidth={2} strokeDasharray="4 4" />
        {ticks.map((i) => (
          <text key={i} x={i === 0 ? 0 : i === data.length - 1 ? W : i * step + step / 2} y={H + 14} textAnchor={i === 0 ? "start" : i === data.length - 1 ? "end" : "middle"} fontSize={11} fill="var(--text-secondary)">
            {fmt(data[i].start)}
          </text>
        ))}
      </svg>
      <figcaption className="sr-only">
        <table>
          <caption>Reviews published per {unit}</caption>
          <thead>
            <tr><th>Starting</th><th>This period</th><th>Previous period</th></tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.start}><td>{fmt(d.start)}</td><td>{d.current}</td><td>{d.previous}</td></tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}

/**
 * Admin Analytics (Figma Screen/Admin/Analytics 8071:16115) over
 * GET /admin/analytics/summary: every figure counts recorded rows, and each
 * sits beside the same figure for the period before.
 */
export function AnalyticsScreen({ data, range, now, children }: { data: Summary | null; range: string; now: number; children?: React.ReactNode }) {
  const days = { "7d": 7, "30d": 30, "90d": 90, "12m": 365 }[range] ?? 30;
  if (!data) return <p role="alert" className="text-[14px] text-[var(--text-secondary)]">Analytics could not be loaded. Try again in a moment.</p>;
  const k = Object.fromEntries(data.kpis.map((x) => [x.key, x]));
  const total = data.series.reduce((a, d) => a + d.current, 0);
  const prevTotal = data.series.reduce((a, d) => a + d.previous, 0);
  const f = data.funnel as Record<string, string>;
  // The widest stage sets the scale: orders are marketplace-reported and can
  // outnumber the clicks recorded here.
  const fmax = Math.max(1, Number(f.review_views), Number(f.affiliate_clicks), Number(f.orders));
  const m = data.moderation as Record<string, number | string | null>;
  const oldest = oldestWaiting(m.oldest_waiting_at as string | null, now);
  const c = data.community as { new_members: number; previous_new_members: number; active_reviewers: number; returning_voters_pct: number | null; reviewers_by_stage: Record<string, number> };
  const stageTotal = Object.values(c.reviewers_by_stage).reduce((a, b) => a + b, 0);
  const decisions = Number(m.decisions) || 0;
  const look = data.needs_a_look;
  return (
    <div className="flex flex-col gap-4">
      {/* Screen/Admin/Analytics (8071:16115): the period sits just under the
          title, the range switch and then Export CSV at its right. */}
      <div className="-mt-3 flex flex-wrap items-center gap-3">
        <p className="flex-1 text-[14px] text-[var(--text-secondary)]">
          Last {range === "12m" ? "12 months" : `${days} days`}, compared with the {range === "12m" ? "12 months" : `${days} days`} before.
        </p>
        <nav aria-label="Range" className="flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {RANGES.map(([key, label]) => (
            <Link key={key} href={`/admin/analytics?range=${key}`} aria-current={range === key ? "page" : undefined} className={`rounded-[8px] px-3 py-[5px] text-[13px] ${range === key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)]"}`}>
              {label}
            </Link>
          ))}
        </nav>
        <AdminExportButton initial={["analytics"]} period={range} />
      </div>

      <section aria-label="Key figures" className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {(["reviews_published", "votes_cast", "affiliate_clicks", "orders", "commission"] as const).map((key) => {
          const x = k[key];
          return (
            <div key={key} data-testid="kpi" className={CARD}>
              <p className="text-[12px] text-[var(--text-secondary)]">{LABEL[key]}</p>
              <p className="mt-1 text-[22px] font-semibold leading-tight">{key === "commission" ? <Peso value={x?.current ?? 0} /> : n(x?.current ?? 0)}</p>
              <Delta current={Number(x?.current ?? 0)} previous={Number(x?.previous ?? 0)} />
            </div>
          );
        })}
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section aria-label="Reviews published" className={CARD}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-[16px] font-semibold">Reviews published per {data.series_unit}</h2>
              <p className="text-[12px] text-[var(--text-secondary)]">
                {(total / Math.max(1, data.series.length)).toFixed(1)} a {data.series_unit} on average, {total >= prevTotal ? "up" : "down"} from {(prevTotal / Math.max(1, data.series.length)).toFixed(1)}
              </p>
            </div>
            <p className="flex items-center gap-3 text-[12px] text-[var(--text-secondary)]">
              <span className="flex items-center gap-1"><span className="size-[10px] rounded-[2px] bg-[var(--accent-primary)]" aria-hidden /> Reviews published</span>
              <span className="flex items-center gap-1"><span className="w-[14px] border-t-2 border-dashed border-[var(--text-primary)]" aria-hidden /> Previous period</span>
            </p>
          </div>
          <div className="mt-3"><Chart data={data.series} unit={data.series_unit} /></div>
        </section>

        <section aria-label="From review to commission" className={CARD}>
          <h2 className="text-[16px] font-semibold">From review to commission</h2>
          <p className="text-[12px] text-[var(--text-secondary)]">Where readers drop off</p>
          <div className="mt-3 flex flex-col gap-3">
            <Bar label="Review views" value={Number(f.review_views)} max={fmax} right={n(f.review_views)} />
            <Bar label="Affiliate clicks" value={Number(f.affiliate_clicks)} max={fmax} right={n(f.affiliate_clicks)} />
            {Number(f.review_views) ? <p className="-mt-2 text-[12px] text-[var(--text-secondary)]">{((Number(f.affiliate_clicks) / Number(f.review_views)) * 100).toFixed(1)}% of views</p> : null}
            <Bar label="Orders" value={Number(f.orders)} max={fmax} right={n(f.orders)} />
            <Bar label="Commission" value={Number(f.orders)} max={fmax} right={<Peso value={f.commission} />} />
            {Number(f.orders) ? <p className="-mt-2 text-[12px] text-[var(--text-secondary)]">₱{(Number(f.commission) / Number(f.orders)).toFixed(2)} per order</p> : null}
          </div>
          <p className="mt-3 text-[11px] text-[var(--text-secondary)]">Orders are marketplace-reported; not every order follows a click recorded here.</p>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-label="Moderation" className={CARD}>
          <div className="flex justify-between"><h2 className="text-[16px] font-semibold">Moderation</h2><Link href="/admin/review-queue" className="text-[12px] text-[var(--chart-honesty-fund)]">Open queue</Link></div>
          <p className="text-[12px] text-[var(--text-secondary)]">How fast the queue moves</p>
          <div className="mt-3 grid grid-cols-3 gap-3 text-[13px]">
            <div><p className="text-[12px] text-[var(--text-secondary)]">Median decision time</p><p className="text-[18px] font-semibold">{hoursMinutes(m.median_decision_hours as number | null)}</p>{m.previous_median_decision_hours !== null ? <p className="text-[12px] text-[var(--text-secondary)]">Was {hoursMinutes(m.previous_median_decision_hours as number)}</p> : null}</div>
            <div><p className="text-[12px] text-[var(--text-secondary)]">In queue now</p><p className="text-[18px] font-semibold">{n(Number(m.in_queue))}</p>{oldest ? <p className="text-[12px] text-[var(--text-secondary)]">{oldest}</p> : null}</div>
            <div><p className="text-[12px] text-[var(--text-secondary)]">Decisions</p><p className="text-[18px] font-semibold">{n(decisions)}</p><p className="text-[12px] text-[var(--text-secondary)]">By {n(Number(m.deciders))} staff</p></div>
          </div>
          {decisions ? (
            <>
              <div className="mt-4 flex h-[8px] gap-[2px] overflow-hidden rounded-full" aria-hidden>
                <span className="bg-[var(--text-primary)]" style={{ width: `${(Number(m.approved) / decisions) * 100}%` }} />
                <span className="bg-[var(--text-secondary)]" style={{ width: `${(Number(m.rejected) / decisions) * 100}%` }} />
                <span className="bg-[var(--border-subtle)]" style={{ width: `${(Number(m.taken_down) / decisions) * 100}%` }} />
              </div>
              <p className="mt-2 flex flex-wrap gap-4 text-[12px] text-[var(--text-secondary)]">
                {(
                  [
                    ["Approved", m.approved, "bg-[var(--text-primary)]"],
                    ["Rejected", m.rejected, "bg-[var(--text-secondary)]"],
                    ["Taken down", m.taken_down, "bg-[var(--border-subtle)]"],
                  ] as const
                ).map(([label, v, swatch]) => (
                  <span key={label} className="flex items-center gap-[6px]">
                    <span aria-hidden className={`size-2 rounded-[2px] ${swatch}`} />
                    {label} {Math.round((Number(v) / decisions) * 100)}%
                  </span>
                ))}
              </p>
            </>
          ) : null}
          <p className="mt-3 border-t border-[var(--border-subtle)] pt-3 text-[13px]">
            Reports: {n(Number(m.reports_opened))} opened, {n(Number(m.reports_closed))} closed{m.median_report_close_hours !== null ? `, median ${m.median_report_close_hours}h to close` : ""}
          </p>
        </section>

        <section aria-label="Community" className={CARD}>
          <div className="flex justify-between"><h2 className="text-[16px] font-semibold">Community</h2><Link href="/admin/reviewers" className="text-[12px] text-[var(--chart-honesty-fund)]">Open people</Link></div>
          <p className="text-[12px] text-[var(--text-secondary)]">Who is writing and voting</p>
          <div className="mt-3 grid grid-cols-3 gap-3">
            <div><p className="text-[12px] text-[var(--text-secondary)]">New members</p><p className="text-[18px] font-semibold">{n(c.new_members)}</p><Delta current={c.new_members} previous={c.previous_new_members} /></div>
            <div><p className="text-[12px] text-[var(--text-secondary)]">Active reviewers</p><p className="text-[18px] font-semibold">{n(c.active_reviewers)}</p><p className="text-[12px] text-[var(--text-secondary)]">Posted at least once</p></div>
            <div><p className="text-[12px] text-[var(--text-secondary)]">Returning voters</p><p className="text-[18px] font-semibold">{c.returning_voters_pct === null ? "—" : `${c.returning_voters_pct}%`}</p><p className="text-[12px] text-[var(--text-secondary)]">Voted in both periods</p></div>
          </div>
          <p className="mt-4 text-[12px] text-[var(--text-secondary)]">Reviewers by stage</p>
          {/* Figma Community card: one bar split by stage, lightest (Newcomer)
              to ink (Community Expert), and a legend with each share. */}
          {stageTotal ? (
            <div className="mt-2 flex h-[8px] gap-[2px] overflow-hidden rounded-full" aria-hidden>
              {STAGE.map((label, i) => {
                const v = c.reviewers_by_stage[String(i)] ?? 0;
                return v ? <span key={label} className={STAGE_TONE[i]} style={{ width: `${(v / stageTotal) * 100}%` }} /> : null;
              })}
            </div>
          ) : null}
          <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--text-secondary)]">
            {STAGE.map((label, i) => {
              const v = c.reviewers_by_stage[String(i)] ?? 0;
              return (
                <li key={label} className="flex items-center gap-[6px]" title={`${n(v)} ${v === 1 ? "reviewer" : "reviewers"}`}>
                  <span aria-hidden className={`size-2 rounded-full ${STAGE_TONE[i]}`} />
                  {label} {stageTotal ? Math.round((v / stageTotal) * 100) : 0}%
                  <span className="sr-only">, {n(v)} {v === 1 ? "reviewer" : "reviewers"}</span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section aria-label="Top products by commission" className={CARD}>
          <div className="flex justify-between"><h2 className="text-[16px] font-semibold">Top products by commission</h2><Link href="/admin/affiliate-links" className="text-[12px] text-[var(--chart-honesty-fund)]">Open affiliate</Link></div>
          <p className="text-[12px] text-[var(--text-secondary)]">What readers buy after reading</p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[480px] text-left text-[14px]">
              <thead className="text-[12px] text-[var(--text-secondary)]">
                <tr>{["Product", "Reviews", "Clicks", "Orders", "Commission"].map((h, i) => <th key={h} scope="col" className={`py-2 font-normal ${i ? "text-right" : ""}`}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.top_products.length === 0 ? (
                  <tr><td colSpan={5} className="py-6 text-center text-[var(--text-secondary)]">No commission recorded in this period.</td></tr>
                ) : (
                  data.top_products.map((p) => (
                    <tr key={p.id} className="border-t border-[var(--border-subtle)]">
                      <td className="max-w-[240px] truncate py-2">{p.name ?? "Unnamed product"}</td>
                      <td className="text-right">{n(p.reviews)}</td>
                      <td className="text-right">{n(p.clicks)}</td>
                      <td className="text-right">{n(p.orders)}</td>
                      <td className="text-right"><Peso value={p.commission} /></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section aria-label="Where readers are" className={CARD}>
          <h2 className="text-[16px] font-semibold">Where readers are</h2>
          <p className="text-[12px] text-[var(--text-secondary)]">{n(data.places_total)} page requests</p>
          <div className="mt-3 flex flex-col gap-3">
            {data.places.length === 0 ? <p className="text-[13px] text-[var(--text-secondary)]">No located requests in this period.</p> : data.places.map((p) => (
              <Bar key={`${p.city}-${p.country}`} label={p.city} value={p.requests} max={data.places[0].requests} right={n(p.requests)} />
            ))}
          </div>
          <p className="mt-3 text-[11px] text-[var(--text-secondary)]">City as the edge resolved it; no IP addresses are stored, and buckets are kept 90 days.</p>
        </section>
      </div>

      <section aria-label="Needs a look" className={CARD}>
        <h2 className="text-[16px] font-semibold">Needs a look</h2>
        <p className="text-[12px] text-[var(--text-secondary)]">Signals the integrity sweep and the ledgers raised</p>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          {(
            [
              ["Possible voting rings", look.voting_rings, "/admin/review-queue?tab=report", "Open in queue"],
              ["Reused photos", look.reused_photos, "/admin/review-queue", "Open in queue"],
              ["Under investigation", look.under_investigation, "/admin/reviewers?status=investigating", "Open people"],
              ["Failed payouts", look.failed_payouts, "/admin/payouts?view=failed", "Open payouts"],
            ] as const
          ).map(([label, value, href, cta]) => (
            <div key={label} className="rounded-[12px] bg-[var(--surface-app)] p-3">
              <p className="text-[12px] text-[var(--text-secondary)]">{label}</p>
              <p className="text-[20px] font-semibold">{n(value ?? 0)}</p>
              <Link href={href} className="text-[12px] text-[var(--chart-honesty-fund)]">{cta}</Link>
            </div>
          ))}
        </div>
      </section>
      {children}
    </div>
  );
}

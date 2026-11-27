import Link from "next/link";

import { PersonCell, RatingCell } from "@/components/admin/queue/QueueCells";
import { Chip } from "@/components/console/Chip";
import { StarRow } from "@/components/sellers/SellerIdentity";
import { formatRating } from "@/components/ui/star-ladder";
import { PERIODS, type ConsoleAppeal, type ConsoleDashboard, type ConsolePeriod } from "@/lib/seller-console";

import { PeriodMenu } from "./PeriodMenu";
import { WaitingList } from "./WaitingList";
import { agoShort, greeting, monthLabel, pct, waitingItems, waitingTotal } from "./overview-model";

/**
 * Screen/Seller/Overview (Figma 8190:20643), every figure from the owner's
 * dashboard (GET /sellers/{id}/dashboard?period=…) and appeals:
 *
 * - tiles and Rating breakdown: the period's visible reviews (period_summary);
 * - Waiting on you: unanswered store questions, reviews without a response and
 *   flags the store raised that are still open — oldest first;
 * - Reviews per month: the last six Manila months (analytics.months);
 * - Your replies: responses ÷ reviews, store answers ÷ store questions, and the
 *   median hours to reply, beside every store's median;
 * - Recent reviews: the newest five.
 *
 * Respond opens the console's Reviews screen; Answer opens the question page,
 * where the store's answer form lives; nothing here posts.
 */
export function SellerOverview({
  storeId,
  dashboard,
  appeals,
  period,
  now,
}: {
  storeId: string;
  dashboard: ConsoleDashboard;
  appeals: ConsoleAppeal[] | null;
  period: ConsolePeriod;
  now: number;
}) {
  const s = dashboard.period_summary ?? dashboard.seller.summary;
  const a = dashboard.analytics;
  const n = s.review_count ?? 0;
  const name = dashboard.seller.display_name;
  const waiting = waitingItems(dashboard, appeals ?? [], now);
  const months = a?.months ?? [];
  const last = months.at(-1);
  const prev = months.at(-2);
  const maxMonth = Math.max(1, ...months.map((m) => m.reviews));
  const dist = s.rating_distribution ?? {};
  const maxDist = Math.max(1, ...Object.values(dist).map(Number));
  const periodLabel = PERIODS.find((p) => p.key === period)?.label ?? "";
  const reviews = (dashboard.reviews ?? []).slice(0, 5);

  const tiles: { label: string; value: string; note: string }[] = [
    {
      label: "Overall rating",
      value: s.overall_average != null ? `${formatRating(Number(s.overall_average))} / 5` : "—",
      note: n ? `Median of ${n} review${n === 1 ? "" : "s"}` : "No reviews in this period",
    },
    { label: "Would recommend", value: pct(s.recommend_rate), note: n ? `${Math.round((s.recommend_rate ?? 0) * n)} of ${n} buyers` : "—" },
    { label: "Matched the listing", value: pct(s.accuracy_rate), note: "Item was as described" },
    { label: "Complete orders", value: pct(s.order_completeness_rate), note: "Nothing was missing" },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="flex-1 text-[24px] font-semibold leading-none">
          {greeting(now)}, {name}
        </h1>
        <PeriodMenu storeId={storeId} period={period} />
      </div>

      <section aria-label={`The store in the ${periodLabel.toLowerCase()}`} className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
            <span className="text-[12px] text-[var(--text-secondary)]">{t.label}</span>
            <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{t.value}</span>
            <span className="text-[12px] text-[var(--text-secondary)]">{t.note}</span>
          </div>
        ))}
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <WaitingList storeId={storeId} items={waiting} total={waitingTotal(dashboard, appeals ?? [], waiting.length)} />

        <section aria-labelledby="breakdown-h" className="rounded-[16px] border border-[var(--border-subtle)] p-5">
          <h2 id="breakdown-h" className="text-[16px] font-semibold leading-none">Rating breakdown</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
            Overall rating across {n} review{n === 1 ? "" : "s"}
          </p>
          <div className="mt-4 flex items-center gap-3">
            <span className="text-[32px] font-semibold leading-none">{s.overall_average != null ? formatRating(Number(s.overall_average)) : "—"}</span>
            <span className="flex flex-col gap-1">
              <StarRow value={s.overall_average != null ? Number(s.overall_average) : null} size={18} />
              <span className="text-[12px] text-[var(--text-secondary)]">Median, same method as product ratings</span>
            </span>
          </div>
          <ul className="mt-4 flex flex-col gap-2" aria-label="Reviews by stars">
            {[5, 4, 3, 2, 1].map((star) => {
              const c = Number(dist[String(star)] ?? 0);
              const tone = star >= 4 ? "bg-[var(--semantic-success-500)]" : star === 3 ? "bg-[var(--accent-star)]" : star === 2 ? "bg-[var(--brand-coral)]" : "bg-[var(--semantic-danger)]";
              return (
                <li key={star} className="flex items-center gap-2 text-[12px]">
                  <span className="w-6 text-[var(--text-secondary)]">{star}★</span>
                  <span className="h-[6px] flex-1 rounded-full bg-[var(--surface-app)]">
                    <span className={`block h-full rounded-full ${tone}`} style={{ width: `${(c / maxDist) * 100}%` }} />
                  </span>
                  <span className="w-8 text-right [font-variant-numeric:tabular-nums]">{c}</span>
                </li>
              );
            })}
          </ul>
          <div className="mt-5 flex flex-col gap-2 border-t border-[var(--border-subtle)] pt-4">
            {[
              ["Customer service", s.customer_service_average],
              ["Packaging", s.packaging_quality_average],
            ].map(([label, v]) => (
              <div key={label as string} className="flex items-center gap-3 text-[14px]">
                <span className="flex-1">{label}</span>
                <span className="flex gap-1" aria-hidden>
                  {[1, 2, 3, 4, 5].map((i) => (
                    <span key={i} className={`h-[5px] w-5 rounded-full ${v != null && i <= Math.round(Number(v)) ? "bg-[var(--accent-primary)]" : "bg-[var(--surface-app)]"}`} />
                  ))}
                </span>
                <span className="w-10 text-right text-[12px] [font-variant-numeric:tabular-nums]">{v != null ? `${formatRating(Number(v))} / 5` : "—"}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <section aria-labelledby="months-h" className="rounded-[16px] border border-[var(--border-subtle)] p-5">
          <div className="flex items-start gap-3">
            <div className="flex-1">
              <h2 id="months-h" className="text-[16px] font-semibold leading-none">Reviews per month</h2>
              <p className="mt-1 text-[12px] text-[var(--text-secondary)]">Visible reviews only. Removed ones don&rsquo;t count.</p>
            </div>
            {last ? (
              <Chip tone="neutral">
                {last.reviews} in {monthLabel(last.month)}
                {prev ? ` · ${last.reviews >= prev.reviews ? "up" : "down"} from ${prev.reviews}` : ""}
              </Chip>
            ) : null}
          </div>
          <ol className="mt-6 flex h-[170px] items-end gap-3" aria-label="Reviews per month">
            {months.map((m, i) => (
              <li key={m.month} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
                <span className="text-[12px] [font-variant-numeric:tabular-nums]">{m.reviews}</span>
                <span
                  className={`w-full rounded-t-[4px] ${i === months.length - 1 ? "bg-[var(--accent-primary)]" : "bg-[var(--status-high-bg)]"}`}
                  style={{ height: `${Math.max(2, (m.reviews / maxMonth) * 120)}px` }}
                  aria-hidden
                />
                <span className="text-[12px] text-[var(--text-secondary)]">{monthLabel(m.month)}</span>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="replies-h" className="rounded-[16px] border border-[var(--border-subtle)] p-5">
          <h2 id="replies-h" className="text-[16px] font-semibold leading-none">Your replies</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">Buyers see your response under their review</p>
          <div className="mt-4 flex flex-col gap-4">
            <Meter label="Reviews you responded to" value={a?.response_rate ?? null} note={`${a?.responses_total ?? 0} of ${a?.review_count ?? 0}`} />
            <Meter
              label="Questions you answered"
              value={a && a.questions_total ? a.questions_answered_by_store / a.questions_total : null}
              note={`${a?.questions_answered_by_store ?? 0} of ${a?.questions_total ?? 0}`}
            />
            <div className="flex flex-col gap-1">
              <span className="flex items-center text-[14px]">
                <span className="flex-1">Median time to reply</span>
                <span className="[font-variant-numeric:tabular-nums]">{a?.median_reply_hours != null ? `${hours(a.median_reply_hours)}` : "—"}</span>
              </span>
              <span className="text-[12px] text-[var(--text-secondary)]">
                {a?.platform_median_reply_hours != null ? `Most stores reply within ${hours(a.platform_median_reply_hours)}` : "No store has replied yet"}
              </span>
            </div>
          </div>
        </section>
      </div>

      <section aria-labelledby="recent-h" className="flex flex-col gap-3">
        <div className="flex items-center">
          <h2 id="recent-h" className="flex-1 text-[16px] font-semibold leading-none">Recent reviews</h2>
          <Link href={`/seller/${storeId}/reviews`} className="-my-1.5 py-1.5 text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
            See all reviews
          </Link>
        </div>
        <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
          <table className="w-full min-w-[860px] border-collapse text-left text-[14px]">
            <caption className="sr-only">Recent reviews</caption>
            <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
              <tr>
                {["Buyer", "Rating", "Review", "Posted", "Your response", "Action"].map((h) => (
                  <th key={h} scope="col" className="h-10 px-3 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {reviews.length === 0 ? (
                <tr>
                  <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                    No reviews of your store yet.
                  </td>
                </tr>
              ) : (
                reviews.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--border-subtle)]">
                    <td className="px-3 py-[10px]">
                      <PersonCell name={r.reviewer_name ?? r.reviewer ?? "Buyer"} stage={r.reviewer_trust_stage ?? null} />
                    </td>
                    <td className="px-3">
                      {/* Figma Recent reviews: one star in the rating's colour, then the number. */}
                      <span className="sr-only">{formatRating(r.overall_rating)} stars</span>
                      <span aria-hidden="true"><RatingCell rating={r.overall_rating} /></span>
                    </td>
                    <td className="max-w-[320px] truncate px-3">{r.title || r.excerpt || "—"}</td>
                    <td className="whitespace-nowrap px-3 text-[var(--text-secondary)]" suppressHydrationWarning>
                      {agoShort(r.created_at, now)}
                    </td>
                    <td className="px-3">
                      {r.has_store_response ? <Chip tone="success">Responded</Chip> : <Chip tone="warning">No response</Chip>}
                    </td>
                    <td className="px-3">
                      <Link
                        href={`/seller/${storeId}/reviews?respond=${r.id}`}
                        className="inline-flex h-8 items-center rounded-full border border-[var(--border-subtle)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        {r.has_store_response ? "Edit" : "Respond"}
                      </Link>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function hours(h: number): string {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} days`;
}

/** Figma component Meter: label and value, a bar, a note under it. */
function Meter({ label, value, note }: { label: string; value: number | null; note: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="flex items-center text-[14px]">
        <span className="flex-1">{label}</span>
        <span className="[font-variant-numeric:tabular-nums]">{pct(value)}</span>
      </span>
      <span className="h-[5px] rounded-full bg-[var(--surface-app)]" aria-hidden>
        <span className="block h-full rounded-full bg-[var(--semantic-success-500)]" style={{ width: `${Math.round((value ?? 0) * 100)}%` }} />
      </span>
      <span className="text-[12px] text-[var(--text-secondary)]">{note}</span>
    </div>
  );
}

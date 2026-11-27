import { OVERVIEW_CARD, OverviewCardHeader } from "@/components/admin/overview/OverviewCardHeader";
import { manilaToday, nextMonthlyDate, shortDate } from "@/components/admin/overview/overview-model";
import { peso, pesoWhole } from "@/lib/dashboard";

/**
 * "This payout cycle" (Card/PayoutCycle 8444:38954, Screen/Admin/Overview v4,
 * read 2026-10-05): when payouts send, the amount queued to send in 28px Bold,
 * three 14px lines (label at 70%, figure in SemiBold — Failed in critical red),
 * a hairline, and the Honesty Fund pool with its distribution date.
 *
 * Real figures only: the amount, "Ready to send" and "Failed" are
 * GET /admin/payouts/summary; the send day is SettingsOut.payout_day (a day of
 * the month, Manila); the pool and its date are GET /admin/payouts/honesty-fund.
 * The frame's "Below ₱300 threshold" count is drawn only when the API sends
 * `below_minimum_count` — it does not yet (RESEARCH dependency) — rather than
 * shown as a guess. A part that could not be read is left out.
 */
export function PayoutCycleCard({
  summary,
  payoutDay,
  payoutMinimum,
  fund,
  now,
}: {
  summary: { to_send_total: string; to_send_count: number; failed_count: number; below_minimum_count?: number } | null;
  payoutDay: number | null;
  payoutMinimum: string | null;
  fund: { pool: string; distributes_on: string } | null;
  now: number;
}) {
  const sends = payoutDay ? shortDate(nextMonthlyDate(payoutDay, manilaToday(now))) : null;
  const distributes = fund?.distributes_on
    ? (() => {
        const [y, m, d] = fund.distributes_on.slice(0, 10).split("-").map(Number);
        return y && m && d ? shortDate({ y, m: m - 1, d }, false) : null;
      })()
    : null;
  const line = "flex items-center gap-2 text-[14px] leading-5";

  return (
    <section aria-labelledby="payout-card-heading" className={`${OVERVIEW_CARD} gap-3`}>
      <OverviewCardHeader id="payout-card-heading" title="This payout cycle" href="/admin/payouts" />
      {summary === null ? (
        <p role="status" className="text-[13px] text-[var(--text-secondary)]">
          The payout figures could not be loaded.
        </p>
      ) : (
        <>
          {sends ? <p className="text-[12px] leading-4 text-[var(--text-muted)]">Sends {sends}</p> : null}
          <p className="text-[28px] font-bold leading-9">{peso(summary.to_send_total)}</p>
          <p className={line}>
            <span className="min-w-0 flex-1 text-[var(--text-secondary)]">Ready to send</span>
            <span className="font-semibold">{summary.to_send_count}</span>
          </p>
          <p className={line}>
            <span className="min-w-0 flex-1 text-[var(--text-secondary)]">Failed</span>
            <span className={`font-semibold ${summary.failed_count > 0 ? "text-[var(--status-critical-fg)]" : ""}`}>
              {summary.failed_count}
            </span>
          </p>
          {typeof summary.below_minimum_count === "number" ? (
            <p className={line}>
              <span className="min-w-0 flex-1 text-[var(--text-secondary)]">
                Below {payoutMinimum ? pesoWhole(payoutMinimum) : "the"} threshold
              </span>
              <span className="font-semibold">{summary.below_minimum_count}</span>
            </p>
          ) : null}
        </>
      )}
      {fund ? (
        <>
          <hr className="border-0 border-t border-[var(--border-subtle)]" />
          <p className="flex items-center gap-2">
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-[14px] leading-5 text-[var(--text-secondary)]">Honesty Fund pool</span>
              {distributes ? (
                <span className="text-[12px] leading-4 text-[var(--text-muted)]">Distributes {distributes}</span>
              ) : null}
            </span>
            <span className="text-[14px] font-semibold leading-5">{peso(fund.pool)}</span>
          </p>
        </>
      ) : null}
    </section>
  );
}

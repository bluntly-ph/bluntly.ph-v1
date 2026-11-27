import type { Metadata } from "next";
import { ArrowsClockwise, CalendarBlank, CheckCircle, MinusCircle } from "@phosphor-icons/react/dist/ssr";

import { PayoutTabs } from "@/components/admin/payouts/PayoutTabs";
import { FUND_FILTERS, FUND_SORTS, applyCycles } from "@/components/admin/list-models";
import { ListControls } from "@/components/console/ListControls";
import { flatParams } from "@/components/console/list-query";
import { getHonestyFundCycles, getPayoutSummary, type FundCycle } from "@/lib/moderation";

export const metadata: Metadata = { title: "Honesty Fund — bluntly admin" };

const TZ = "Asia/Manila";

function Money({ amount, size = 14 }: { amount: string | null | undefined; size?: number }) {
  if (amount == null) return <span>—</span>;
  const [whole, cents] = Number(amount).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).split(".");
  return (
    <span className="whitespace-nowrap font-medium [font-variant-numeric:tabular-nums]" style={{ fontSize: size }}>
      ₱{whole}
      <span className="text-[var(--text-secondary)]">.{cents}</span>
    </span>
  );
}

const monthName = (iso: string, opts: Intl.DateTimeFormatOptions = { month: "long", year: "numeric" }) =>
  new Date(`${iso}T12:00:00+08:00`).toLocaleDateString("en-GB", { ...opts, timeZone: TZ });
const dayMonth = (iso: string) => new Date(iso.length === 10 ? `${iso}T12:00:00+08:00` : iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: TZ });

function lastDay(month: string): string {
  const d = new Date(`${month}T12:00:00+08:00`);
  return new Date(d.getFullYear(), d.getMonth() + 1, 0, 12).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function Status({ c }: { c: FundCycle }) {
  if (c.status === "collecting") {
    return (
      <span className="flex items-center gap-1.5">
        <ArrowsClockwise size={16} aria-hidden className="text-[var(--accent-trust)]" /> Collecting
      </span>
    );
  }
  if (c.status === "distributed") {
    return (
      <span className="flex items-center gap-1.5">
        <CheckCircle size={16} weight="fill" aria-hidden className="text-[var(--accent-success)]" /> Distributed
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1.5 text-[var(--text-secondary)]">
      <MinusCircle size={16} aria-hidden /> Not distributed
    </span>
  );
}

/**
 * Payouts → Honesty Fund (Figma 8024:13286): the pool being collected this
 * cycle (30% of every real commission), when the cycle closes and is shared
 * out, the last distribution, and one row per recent cycle — read from the
 * commissions and the distribution rows the monthly run wrote.
 *
 * Distribution is a scheduled operation, not a button: there is no
 * "distribute now" control, because an administrator triggering a payout run
 * by hand is not how the product works.
 */
export default async function HonestyFundPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  // Menu/Payouts/HonestyFund/Sort + Filter (8288:30028, 8288:30047).
  const query = flatParams(await searchParams, ["sort", "status"]);
  const [fund, summary] = await Promise.all([getHonestyFundCycles(), getPayoutSummary()]);
  const cycles = fund ? applyCycles([...fund.cycles], query) : [];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-2">
      <div className="flex flex-wrap items-center gap-2">
        <PayoutTabs current="honesty_fund" counts={summary} />
        <span className="flex-1" />
        <ListControls basePath="/admin/honesty-fund" params={query} sorts={FUND_SORTS} defaultSort="newest" filters={FUND_FILTERS} />
      </div>
      {!fund ? (
        <p role="alert" className="rounded-[16px] border border-[var(--border-subtle)] p-6 text-[13px] text-[var(--text-secondary)]">
          The Honesty Fund could not be loaded. This is not an empty fund: nothing is known right now.
        </p>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-1.5 rounded-[16px] border border-[var(--border-subtle)] p-5">
              <span className="text-[12px] text-[var(--text-secondary)]">{monthName(fund.current.month, { month: "long" })} pool</span>
              <Money amount={fund.current.pool} size={24} />
              <span className="text-[12px] text-[var(--text-secondary)]">30% of every commission this cycle</span>
            </div>
            <div className="flex flex-col gap-1.5 rounded-[16px] border border-[var(--border-subtle)] p-5">
              <span className="text-[12px] text-[var(--text-secondary)]">Cycle closes</span>
              <span className="text-[24px] font-medium leading-none">{dayMonth(fund.closes_on)}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">Distributes automatically on {dayMonth(fund.distributes_on)}</span>
            </div>
            <div className="flex flex-col gap-1.5 rounded-[16px] border border-[var(--border-subtle)] p-5">
              <span className="text-[12px] text-[var(--text-secondary)]">Last distributed</span>
              {fund.last ? (
                <>
                  <Money amount={fund.last.distributed} size={24} />
                  <span className="text-[12px] text-[var(--text-secondary)]">
                    {monthName(fund.last.month, { month: "long" })} · {fund.last.contributors} {fund.last.contributors === 1 ? "contributor" : "contributors"}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-[24px] font-medium leading-none">—</span>
                  <span className="text-[12px] text-[var(--text-secondary)]">No cycle has been distributed in the last year</span>
                </>
              )}
            </div>
          </div>

          <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
            <table className="w-full min-w-[720px] text-left text-[14px]">
              <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
                <tr>
                  {["Cycle", "Pool", "Contributors", "Largest share", "Distributed", "Status"].map((h) => (
                    <th key={h} scope="col" className="h-10 px-3 font-normal">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cycles.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-8 text-center text-[var(--text-secondary)]">
                      No cycle matches this filter.
                    </td>
                  </tr>
                ) : null}
                {cycles.map((c) => (
                  <tr key={c.month} data-testid="fund-cycle" className="border-t border-[var(--border-subtle)]">
                    <td className="px-3 py-[10px]">
                      <span className="flex items-center gap-3">
                        <span aria-hidden className="grid size-8 place-items-center rounded-[8px] bg-[var(--surface-app)] text-[var(--text-secondary)]">
                          <CalendarBlank size={16} />
                        </span>
                        <span className="flex flex-col gap-[2px] leading-4 [&>:first-child]:leading-5">
                          <span>{monthName(c.month)}</span>
                          <span className="text-[12px] text-[var(--text-secondary)]">
                            {c.status === "collecting" ? `Open until ${lastDay(c.month)}` : `Closed ${lastDay(c.month)}`}
                          </span>
                        </span>
                      </span>
                    </td>
                    <td className="px-3"><Money amount={c.pool} /></td>
                    <td className="px-3 [font-variant-numeric:tabular-nums]">{c.status === "distributed" ? c.contributors : "—"}</td>
                    <td className="px-3">{c.largest_share ? <Money amount={c.largest_share} /> : "—"}</td>
                    <td className="px-3 text-[var(--text-secondary)]">
                      {c.distributed_at ? dayMonth(c.distributed_at) : c.status === "collecting" ? dayMonth(fund.distributes_on) : "—"}
                    </td>
                    <td className="px-3"><Status c={c} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[12px] text-[var(--text-secondary)]">
            The last 12 cycles with any activity. A cycle is a Manila calendar month: a commission belongs to the month it
            was recognised in. A closed cycle shows &ldquo;Not distributed&rdquo; until the monthly run shares it out, or
            when no review was eligible.
          </p>
        </>
      )}
    </div>
  );
}

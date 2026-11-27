import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUUpLeft, CaretDown, Check, Coins, HandCoins, PaperPlaneTilt, XCircle } from "@phosphor-icons/react/dist/ssr";

import { DashboardBar } from "@/components/dashboard/DashboardBar";
import { Money, ParentLink } from "@/components/dashboard/DashboardParts";
import { groupByMonth, ledgerRows, monthKey, monthTotals, TYPE_FILTERS, type LedgerRow } from "@/components/dashboard/history-model";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getEarningsStatement } from "@/lib/reports";
import { trustLevel } from "@/lib/trust";
import { QuickActions } from "@/components/site/QuickActions";

export const metadata: Metadata = { title: "History — bluntly" };

const MANILA = "Asia/Manila";

function Icon({ row }: { row: LedgerRow }) {
  const I = row.kind === "fund" ? HandCoins : row.kind === "return" ? ArrowUUpLeft : row.kind === "payout" ? (row.status === "Refunded" ? XCircle : PaperPlaneTilt) : Coins;
  const tone = row.kind === "return" ? "text-[var(--accent-danger)]" : row.kind === "fund" ? "text-[var(--accent-primary)]" : "text-[var(--text-secondary)]";
  return (
    <span className="grid size-[44px] shrink-0 place-items-center rounded-[12px] bg-[var(--surface-app)]">
      <I size={20} className={tone} aria-hidden />
    </span>
  );
}

function amount(v: number): string {
  const s = Math.abs(v).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${v < 0 ? "−" : "+"}₱${s}`;
}

/**
 * History (Figma Screen/History 8098:17238): the wallet's ledger for the last
 * two months, grouped by month — commissions (pending until the marketplace
 * pays, then cleared), returns, Honesty Fund credits and payouts — read from
 * the earnings statement. "Request reward" and "Adjustment by Bluntly" rows
 * in the frame have no record behind them here, so none are shown.
 */
export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ type?: string }> }) {
  const me = await requireOnboardedUser();
  const sp = await searchParams;
  const type = TYPE_FILTERS.some(([k]) => k === sp.type) ? (sp.type as string) : "all";
  // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
  const now = new Date(Date.now());
  const today = now.toLocaleDateString("en-CA", { timeZone: MANILA });
  const [y, m] = today.split("-").map(Number);
  const start = `${m === 1 ? y - 1 : y}-${String(m === 1 ? 12 : m - 1).padStart(2, "0")}-01`;
  const result = await getEarningsStatement({ start_date: start, end_date: today });
  const statement = result.ok ? result.report : null;
  const rows = statement ? ledgerRows(statement.entries, statement.fund_distributions, statement.payouts) : [];
  const months = groupByMonth(rows, type);
  const thisMonth = monthKey(now.toISOString());
  const totals = monthTotals(rows, thisMonth);
  const monthName = now.toLocaleDateString("en-GB", { month: "long", timeZone: MANILA });
  const pending = statement ? Number(statement.summary.clearing) : 0;
  const current = TYPE_FILTERS.find(([k]) => k === type)?.[1] ?? "All types";

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <DashboardBar backHref="/dashboard" trustLevel={trustLevel(me.trust_level_name, me.trust_stage)} />
      </div>

      <main className="mx-auto flex w-full max-w-[390px] flex-1 flex-col md:max-w-[480px] md:pt-8">
        <div className="flex flex-col gap-3 px-4 pb-8">
          <ParentLink href="/dashboard" label="Dashboard" />
          <h1 className="px-1 text-[24px] font-semibold leading-none text-[var(--text-primary)]">History</h1>

          {!statement ? (
            <p role="alert" className="rounded-[16px] bg-[var(--surface-app)] px-4 py-6 text-[13px] text-[var(--text-secondary)]">Your history could not be loaded right now.</p>
          ) : (
            <>
              <section aria-label={`${monthName} so far`} className="rounded-[32px] bg-[var(--surface-app)] p-[3px]">
                <div className="rounded-[32px] bg-[var(--surface-card)] px-5 py-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-[12px] text-[var(--text-secondary)]">Earned in {monthName}</p>
                      <Money value={totals.earned.toFixed(2)} whole="text-[20px]" cents="text-[14px]" />
                    </div>
                    <div>
                      <p className="text-[12px] text-[var(--text-secondary)]">Paid out</p>
                      <Money value={totals.paid.toFixed(2)} whole="text-[20px]" cents="text-[14px]" />
                    </div>
                  </div>
                  {pending > 0 ? (
                    <p className="mt-3 text-[12px] leading-[1.5] text-[var(--text-secondary)]">
                      ₱{pending.toLocaleString("en-PH", { minimumFractionDigits: 2 })} is still pending. Commission clears once the shop confirms the order and the return window ends.
                    </p>
                  ) : null}
                </div>
              </section>

              <div className="flex items-center justify-between px-1">
                <h2 className="text-[13px] text-[var(--text-primary)]">Transactions</h2>
                <details className="relative">
                  <summary className="flex h-8 cursor-pointer list-none items-center gap-2 rounded-full border border-[var(--border-subtle)] px-3 text-[12px] [&::-webkit-details-marker]:hidden">
                    {current} <CaretDown size={12} aria-hidden />
                  </summary>
                  <ul role="menu" className="absolute right-0 top-[calc(100%+6px)] z-20 w-[180px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-[6px] shadow-[var(--shadow-modal)]">
                    {TYPE_FILTERS.map(([key, label]) => (
                      <li key={key}>
                        <Link role="menuitemradio" aria-checked={type === key} href={key === "all" ? "/dashboard/history" : `/dashboard/history?type=${key}`} scroll={false} className="flex items-center justify-between gap-2 rounded-[10px] px-3 py-2 text-[13px] hover:bg-[var(--overlay-hover)] active:bg-[var(--overlay-pressed)] aria-checked:font-medium aria-checked:text-[var(--accent-primary)]">
                          {/* Menu/Option (7761:7914): the current one in brand Medium with a Check, never a fill. */}
                          {label}
                          {type === key ? <Check size={16} aria-hidden /> : null}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </details>
              </div>

              {months.length === 0 ? (
                <div className="rounded-[24px] bg-[var(--surface-app)] px-5 py-10 text-center">
                  <p className="text-[14px] text-[var(--text-primary)]">{type === "all" ? "Nothing in the last two months." : `No ${current.toLowerCase()} in the last two months.`}</p>
                  <p className="mt-1 text-[12px] text-[var(--text-secondary)]">When a review you wrote leads to a sale, the commission appears here, then clears once the marketplace pays.</p>
                </div>
              ) : (
                months.map((month) => (
                  // Figma Card/October 2026 (8098:17307): a 3px grey frame around one
                  // white panel; the month and its net 20px in, then the rows,
                  // with no rules between them.
                  <section key={month.key} aria-label={month.label} className="rounded-[32px] bg-[var(--surface-app)] p-[3px]">
                    <div className="rounded-[30px] bg-[var(--surface-card)] px-5 pb-2 pt-5">
                    <div className="flex items-center justify-between text-[13px]">
                      <span>{month.label}</span>
                      <span className="text-[var(--text-secondary)] [font-variant-numeric:tabular-nums]">{amount(month.net)} net</span>
                    </div>
                    <ul>
                      {month.rows.map((r, i) => (
                        <li key={`${r.at}-${i}`} data-testid="ledger-row" className="flex items-center gap-3 py-3">
                          <Icon row={r} />
                          <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                            <span className="truncate text-[14px] font-medium">{r.title}</span>
                            <span className="line-clamp-2 text-[12px] text-[var(--text-secondary)]">{r.detail}</span>
                          </span>
                          <span className="flex shrink-0 flex-col items-end gap-[2px]">
                            <span className={`text-[14px] font-medium [font-variant-numeric:tabular-nums] ${r.tone === "negative" ? "text-[var(--text-primary)]" : r.tone === "muted" ? "text-[var(--text-secondary)]" : "text-[var(--accent-success)]"} ${r.kind === "return" ? "!text-[var(--accent-danger)]" : ""}`}>
                              {amount(r.amount)}
                            </span>
                            <span className={`text-[11px] ${r.status === "Reversed" ? "text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"}`}>{r.status}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                    </div>
                  </section>
                ))
              )}
              <p className="text-center text-[12px] text-[var(--text-secondary)]">
                Showing the last 2 months ·{" "}
                <Link href="/dashboard/statement" className="underline hover:text-[var(--accent-primary)]">Full statement</Link>
              </p>
            </>
          )}
        </div>
      </main>
      {/* Screen/History draws QuickActions/Button. */}
      <QuickActions />
    </div>
  );
}

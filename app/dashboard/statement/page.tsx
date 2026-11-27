import type { Metadata } from "next";
import Link from "next/link";
import { CaretLeft } from "@phosphor-icons/react/dist/ssr";

import { Figure, ReportFrame, ReportTable, ReportUnavailable } from "@/components/reports/ReportFrame";
import {
  csvHref,
  cycleLabel,
  formatPeso,
  periodFromSearch,
  statusLabel,
  verdictLabel,
} from "@/components/reports/report-model";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { EARNINGS_STATEMENT_PATH, getEarningsStatement, type EarningsStatement } from "@/lib/reports";

export const metadata: Metadata = { title: "Earnings statement — bluntly" };

const DATE = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeZone: "Asia/Manila" });
const when = (iso: string | null) => (iso ? DATE.format(new Date(iso)) : "—");

/**
 * Report 4 — the reviewer's own Earnings Statement (docs/REPORTING_MODULE.md).
 *
 * Always the signed-in reviewer's: the API derives whose statement it is from
 * the session, and this page passes no user id at all. No Figma frame draws a
 * statement; it is built from the dashboard's own cards and the console's
 * table, and every number on it is computed by the API from the ledger.
 */
export default async function StatementPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const me = await requireOnboardedUser();
  const period = periodFromSearch(await searchParams);
  const result = await getEarningsStatement(period);

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      <main className="mx-auto w-full min-w-0 max-w-[72rem] flex-1 px-4 py-6 md:px-8 md:py-8">
        <Link
          href="/dashboard"
          className="report-no-print inline-flex items-center gap-1 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <CaretLeft size={16} /> Dashboard
        </Link>
        <div className="mt-4">
          {result.ok ? (
            <Statement report={result.report} period={period} />
          ) : (
            <ReportUnavailable reason={result.reason} detail={result.detail} />
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

function Statement({ report, period }: { report: EarningsStatement; period: ReturnType<typeof periodFromSearch> }) {
  const s = report.summary;
  const who = report.reviewer.username ? `@${report.reviewer.username}` : report.reviewer.display_name ?? "You";
  return (
    <ReportFrame
      meta={report.meta}
      entity={who}
      action="/dashboard/statement"
      downloads={[
        { label: "Export CSV", href: csvHref(EARNINGS_STATEMENT_PATH, period) },
        { label: "Payouts CSV", href: csvHref(EARNINGS_STATEMENT_PATH, period, "payouts") },
      ]}
    >
      <section aria-label="Summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Figure label="Earned this period" value={formatPeso(s.earned_in_period)} testId="earned-in-period" />
        <Figure label="Earned, all time" value={formatPeso(s.lifetime_earned)} testId="lifetime-earned" />
        <Figure
          label="Clearing"
          value={formatPeso(s.clearing)}
          hint="Waiting for the marketplace to pay Bluntly"
          tone="muted"
          testId="clearing"
        />
        <Figure
          label="Cleared, withdrawable"
          value={formatPeso(s.withdrawable)}
          hint={s.can_cash_out ? "Ready to cash out" : `Minimum cashout ${formatPeso(s.minimum_cashout)}`}
          tone={s.can_cash_out ? "good" : undefined}
          testId="withdrawable"
        />
        <Figure label="Paid this period" value={formatPeso(s.paid_in_period)} testId="paid-in-period" />
        <Figure label="Paid, all time" value={formatPeso(s.paid_lifetime)} />
        <Figure label="Requested, not paid yet" value={formatPeso(s.in_flight)} />
        <Figure label="Wallet balance" value={formatPeso(s.wallet_balance)} />
      </section>

      <ReportTable
        caption="Earnings per review"
        rows={report.reviews}
        rowKey={(r, i) => r.review_id ?? `r${i}`}
        empty="No earnings in this period."
        columns={[
          { header: "Review", cell: (r) => <span className="line-clamp-2 max-w-[18rem]">{r.title ?? "Removed review"}</span> },
          { header: "Product", cell: (r) => r.product ?? "—" },
          { header: "Verdict", cell: (r) => verdictLabel(r.verdict) },
          { header: "Status", cell: (r) => statusLabel(r.earning_status) },
          { header: "Marketplace", cell: (r) => r.marketplaces.join(", ") || "—" },
          { header: "Sales", cell: (r) => r.sales, align: "right" },
          { header: "Commission", cell: (r) => formatPeso(r.commission_gross), align: "right" },
          { header: "Your earning", cell: (r) => formatPeso(r.reviewer_earning), align: "right" },
          { header: "Cleared", cell: (r) => formatPeso(r.cleared), align: "right" },
          { header: "Clearing", cell: (r) => formatPeso(r.clearing), align: "right" },
        ]}
      />

      <ReportTable
        caption="Line items"
        rows={report.entries}
        rowKey={(e, i) => e.commission_id ?? `e${i}`}
        empty="No sales were recognised in this period."
        footer={
          report.entries_truncated ? (
            <p className="text-[12px] text-[var(--text-muted)]">
              Showing the first line items only; the totals above cover the whole period. Export the CSV for all of them.
            </p>
          ) : undefined
        }
        columns={[
          { header: "Recognised", cell: (e) => when(e.recognised_at) },
          { header: "Cycle", cell: (e) => cycleLabel(e.cycle_month) },
          { header: "Review", cell: (e) => <span className="line-clamp-2 max-w-[16rem]">{e.review_title ?? "—"}</span> },
          { header: "Marketplace", cell: (e) => e.marketplace ?? "—" },
          { header: "Commission", cell: (e) => formatPeso(e.commission_gross), align: "right" },
          { header: "Your earning", cell: (e) => formatPeso(e.reviewer_earning), align: "right" },
          { header: "Status", cell: (e) => statusLabel(e.status) },
          { header: "Cleared on", cell: (e) => when(e.cleared_at) },
        ]}
      />

      {report.fund_distributions.length ? (
        <ReportTable
          caption="Honesty Fund payouts"
          rows={report.fund_distributions}
          rowKey={(d, i) => d.distribution_id ?? `d${i}`}
          empty=""
          columns={[
            { header: "Cycle", cell: (d) => cycleLabel(d.cycle_month) },
            { header: "Amount", cell: (d) => formatPeso(d.amount), align: "right" },
          ]}
        />
      ) : null}

      <ReportTable
        caption="Cashouts and payouts"
        rows={report.payouts}
        rowKey={(p, i) => p.payout_id ?? `p${i}`}
        empty="No cashout was requested in this period."
        columns={[
          { header: "Requested", cell: (p) => when(p.requested_at) },
          { header: "Amount", cell: (p) => formatPeso(p.amount), align: "right" },
          { header: "Method", cell: (p) => p.method },
          { header: "Sent to", cell: (p) => p.destination ?? "—" },
          { header: "Batch", cell: (p) => p.batch_id ?? "—" },
          { header: "Reference", cell: (p) => p.reference ?? "—" },
          { header: "Status", cell: (p) => statusLabel(p.status) },
          { header: "Processed", cell: (p) => when(p.processed_at) },
        ]}
      />
    </ReportFrame>
  );
}

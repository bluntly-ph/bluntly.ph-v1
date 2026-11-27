import type { Metadata } from "next";
import Link from "next/link";

import { Figure, ReportFrame, ReportTable, ReportUnavailable } from "@/components/reports/ReportFrame";
import {
  csvHref,
  cycleLabel,
  formatPeso,
  periodFromSearch,
  periodQuery,
  statusLabel,
} from "@/components/reports/report-model";
import { COMMISSIONS_PATH, getCommissionPayoutReport, type CommissionPayoutReport } from "@/lib/reports";

export const metadata: Metadata = { title: "Commissions & payouts report — bluntly admin" };

const PAGE = 100;
const DATE = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeZone: "Asia/Manila" });
const when = (iso: string | null) => (iso ? DATE.format(new Date(iso)) : "—");

/**
 * Report 2 — Commissions and Payouts.
 *
 * Imported Shopee/Lazada commissions for the period's cycle months with the
 * split each carried, whether the marketplace has paid Bluntly for that cycle,
 * and every reviewer against the ₱300 cashout minimum. Totals always cover the
 * whole period; the commission table is paged.
 */
export default async function CommissionsReportPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const period = periodFromSearch(sp);
  const offset = Math.max(0, Number(typeof sp.offset === "string" ? sp.offset : 0) || 0);
  const result = await getCommissionPayoutReport(period, { limit: PAGE, offset });
  return result.ok ? (
    <CommissionReport report={result.report} period={period} />
  ) : (
    <ReportUnavailable reason={result.reason} detail={result.detail} />
  );
}

function CommissionReport({
  report,
  period,
}: {
  report: CommissionPayoutReport;
  period: ReturnType<typeof periodFromSearch>;
}) {
  const t = report.totals;
  const { total, limit, offset } = report.page;
  const pageHref = (o: number) => `/admin/reports/commissions?${periodQuery(period, { offset: String(o) })}`;
  return (
    <ReportFrame
      meta={report.meta}
      action="/admin/reports/commissions"
      downloads={[
        { label: "Commissions CSV", href: csvHref(COMMISSIONS_PATH, period) },
        { label: "Payout summary CSV", href: csvHref(COMMISSIONS_PATH, period, "payout-summary") },
        { label: "Remittances CSV", href: csvHref(COMMISSIONS_PATH, period, "remittances") },
      ]}
    >
      <section aria-label="Totals" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Figure label="Imported commissions" value={formatPeso(t.gross)} hint={`${t.commissions} entries`} testId="gross-total" />
        <Figure label="Platform (40%)" value={formatPeso(t.platform_share)} />
        <Figure label="Reviewers (30%)" value={formatPeso(t.reviewer_share)} />
        <Figure label="Honesty Fund (30% + fund-track)" value={formatPeso(t.honesty_fund_share)} />
        <Figure label="Cleared (marketplace paid)" value={formatPeso(t.cleared_gross)} tone="good" />
        <Figure label="Awaiting marketplace payout" value={formatPeso(t.clearing_gross)} tone="muted" />
        <Figure label="Reversals" value={String(t.reversals)} />
        <Figure label="QA test entries" value={String(t.qa_test_entries)} />
      </section>

      <ReportTable
        caption="By marketplace"
        rows={t.by_marketplace}
        rowKey={(p) => p.marketplace}
        empty="No commissions in this period."
        columns={[
          { header: "Marketplace", cell: (p) => p.marketplace },
          { header: "Entries", cell: (p) => p.commissions, align: "right" },
          { header: "Gross", cell: (p) => formatPeso(p.gross), align: "right" },
          { header: "Platform", cell: (p) => formatPeso(p.platform_share), align: "right" },
          { header: "Reviewers", cell: (p) => formatPeso(p.reviewer_share), align: "right" },
          { header: "Honesty Fund", cell: (p) => formatPeso(p.honesty_fund_share), align: "right" },
          { header: "Cleared", cell: (p) => formatPeso(p.cleared_gross), align: "right" },
          { header: "Clearing", cell: (p) => formatPeso(p.clearing_gross), align: "right" },
        ]}
      />

      <ReportTable
        caption="Reviewer payout readiness"
        rows={report.payout_summary}
        rowKey={(r) => r.reviewer_id}
        empty="No reviewer earned or requested a payout in this period."
        columns={[
          { header: "Reviewer", cell: (r) => r.reviewer ?? "—" },
          { header: "Cleared / withdrawable", cell: (r) => formatPeso(r.withdrawable), align: "right" },
          { header: "Clearing", cell: (r) => formatPeso(r.clearing), align: "right" },
          { header: "Threshold", cell: (r) => formatPeso(r.threshold), align: "right" },
          {
            header: "Eligible",
            cell: (r) => (
              <span
                data-testid="cashout-eligible"
                className={r.eligible_for_cashout ? "font-semibold text-[var(--accent-success)]" : "text-[var(--text-secondary)]"}
              >
                {r.eligible_for_cashout ? "Yes" : "No"}
              </span>
            ),
          },
          { header: "Payout account", cell: (r) => (r.payout_account_on_file ? "On file" : "Missing") },
          { header: "Requested", cell: (r) => formatPeso(r.requested_amount), align: "right" },
          { header: "Paid in period", cell: (r) => formatPeso(r.paid_in_period), align: "right" },
          { header: "Latest payout", cell: (r) => statusLabel(r.latest_payout_status) },
          { header: "Batch", cell: (r) => r.latest_payout_batch ?? "—" },
        ]}
      />

      <ReportTable
        caption="Marketplace remittances"
        rows={report.remittances}
        rowKey={(r) => `${r.marketplace}-${r.cycle_month}`}
        empty="No marketplace cycles in this period."
        columns={[
          { header: "Marketplace", cell: (r) => r.marketplace },
          { header: "Cycle", cell: (r) => cycleLabel(r.cycle_month) },
          { header: "Attributed gross", cell: (r) => formatPeso(r.attributed_gross), align: "right" },
          { header: "Received", cell: (r) => formatPeso(r.amount_received), align: "right" },
          { header: "Difference", cell: (r) => formatPeso(r.difference), align: "right" },
          { header: "Received on", cell: (r) => (r.received_on ? DATE.format(new Date(r.received_on)) : "—") },
          { header: "Status", cell: (r) => statusLabel(r.status) },
        ]}
      />

      <ReportTable
        caption={`Commissions (${total})`}
        rows={report.commissions}
        rowKey={(c, i) => c.commission_id ?? `c${i}`}
        empty="No commissions were imported for this period."
        footer={
          total > limit ? (
            <div className="report-no-print flex items-center justify-between text-[12px] text-[var(--text-secondary)]">
              <span>
                {offset + 1}–{Math.min(offset + limit, total)} of {total}
              </span>
              <span className="flex gap-3">
                {offset > 0 ? <Link href={pageHref(Math.max(0, offset - limit))}>Previous</Link> : null}
                {offset + limit < total ? <Link href={pageHref(offset + limit)}>Next</Link> : null}
              </span>
            </div>
          ) : undefined
        }
        columns={[
          { header: "Cycle", cell: (c) => cycleLabel(c.cycle_month) },
          { header: "Marketplace", cell: (c) => c.marketplace ?? "—" },
          { header: "Sub ID", cell: (c) => <code className="text-[12px]">{c.sub_id ?? "—"}</code> },
          { header: "Review", cell: (c) => <span className="line-clamp-2 max-w-[14rem]">{c.review_title ?? "—"}</span> },
          { header: "Reviewer", cell: (c) => c.reviewer ?? "—" },
          { header: "Imported", cell: (c) => formatPeso(c.imported_commission), align: "right" },
          { header: "Reconciled", cell: (c) => formatPeso(c.reconciled_amount), align: "right" },
          { header: "Status", cell: (c) => statusLabel(c.reconciliation_status) },
          { header: "Reconciled on", cell: (c) => when(c.reconciled_at) },
          { header: "Reviewer share to", cell: (c) => statusLabel(c.allocation) },
          { header: "Platform share", cell: (c) => formatPeso(c.platform_share), align: "right" },
          { header: "Reviewer share", cell: (c) => formatPeso(c.reviewer_share), align: "right" },
          { header: "Fund share", cell: (c) => formatPeso(c.honesty_fund_share), align: "right" },
        ]}
      />
    </ReportFrame>
  );
}

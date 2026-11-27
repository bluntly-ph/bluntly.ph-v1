import type { Metadata } from "next";

import { Figure, ReportFrame, ReportTable, ReportUnavailable } from "@/components/reports/ReportFrame";
import {
  csvHref,
  cycleLabel,
  formatPeso,
  periodFromSearch,
  statusLabel,
  verdictLabel,
} from "@/components/reports/report-model";
import { getHonestyFundReport, HONESTY_FUND_PATH, type HonestyFundReport } from "@/lib/reports";

export const metadata: Metadata = { title: "Honesty Fund report — bluntly admin" };

/**
 * Report 1 — the Honesty Fund Distribution Report.
 *
 * Layer A (fund inputs) is complete; layer B (the computed distribution) is
 * NOT computed, because the formula and holding period are an open owner
 * decision (Business Rules §14). The page says so first, before any number.
 */
export default async function HonestyFundReportPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const period = periodFromSearch(await searchParams);
  const result = await getHonestyFundReport(period);
  return result.ok ? (
    <FundReport report={result.report} period={period} />
  ) : (
    <ReportUnavailable reason={result.reason} detail={result.detail} />
  );
}

function FundReport({ report, period }: { report: HonestyFundReport; period: ReturnType<typeof periodFromSearch> }) {
  return (
    <ReportFrame
      meta={report.meta}
      action="/admin/reports/honesty-fund"
      downloads={[
        { label: "Export CSV", href: csvHref(HONESTY_FUND_PATH, period) },
        { label: "Cycles CSV", href: csvHref(HONESTY_FUND_PATH, period, "cycles") },
      ]}
    >
      <div
        role="note"
        data-testid="fund-formula-status"
        className="rounded-[var(--radius-md)] border border-[var(--accent-star)] bg-[var(--surface-card)] px-4 py-3 text-[13px] text-[var(--text-primary)]"
      >
        <p className="font-semibold">Distribution formula: not yet defined</p>
        <p className="mt-1 text-[var(--text-secondary)]">{report.formula.note}</p>
      </div>

      <section aria-label="Fund totals" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Figure label="Fund inflow (ledger)" value={formatPeso(report.fund_total)} testId="fund-total" />
        <Figure label="Of which cleared" value={formatPeso(report.fund_total_cleared)} />
        <Figure label="Distributed" value={formatPeso(report.distributed_total)} />
        <Figure
          label="Fund-track reviews"
          value={`${report.eligible_count} eligible`}
          hint={`${report.excluded_count} excluded · ${report.pending_routing_count} awaiting 2.5★ routing`}
        />
      </section>

      <ReportTable
        caption="Pool by cycle"
        rows={report.cycles}
        rowKey={(c) => c.cycle_month}
        empty="No cycles in this period."
        columns={[
          { header: "Cycle", cell: (c) => cycleLabel(c.cycle_month) },
          { header: "Commissions", cell: (c) => c.commissions, align: "right" },
          { header: "Fund inflow", cell: (c) => formatPeso(c.fund_inflow), align: "right" },
          { header: "Cleared", cell: (c) => formatPeso(c.fund_inflow_cleared), align: "right" },
          { header: "Distributed", cell: (c) => formatPeso(c.distributed), align: "right" },
          { header: "Status", cell: (c) => statusLabel(c.distribution_status) },
        ]}
      />

      <ReportTable
        caption="Reviews on the Honesty Fund track"
        rows={report.reviews}
        rowKey={(r) => r.review_id}
        empty="No reviews were on the Honesty Fund track in this period."
        columns={[
          { header: "Review", cell: (r) => <span className="line-clamp-2 max-w-[16rem]">{r.title}</span> },
          { header: "Reviewer", cell: (r) => r.reviewer ?? "—" },
          { header: "Verdict", cell: (r) => `${verdictLabel(r.verdict)} · ${r.star_rating}★` },
          {
            header: "Eligibility",
            cell: (r) => (r.exclusion_reason ? `Excluded: ${statusLabel(r.exclusion_reason)}` : "Eligible"),
          },
          { header: "Photo", cell: (r) => (r.photo_provided ? "Photo provided" : "—") },
          { header: "Weighted votes", cell: (r) => r.weighted_helpful_votes, align: "right" },
          {
            header: "Voter evidence",
            cell: (r) => `${r.voter_evidence} / ${r.evidence_floor}`,
            align: "right",
          },
          { header: "Honesty Score", cell: (r) => r.honesty_score, align: "right" },
          { header: "Commission base", cell: (r) => formatPeso(r.commission_base), align: "right" },
          { header: "Fund attributable", cell: (r) => formatPeso(r.fund_attributable), align: "right" },
          {
            header: "Computed share",
            cell: (r) => (r.computed_share === null ? statusLabel(r.computed_share_status) : formatPeso(r.computed_share)),
          },
          { header: "Distributed", cell: (r) => formatPeso(r.distributed_amount), align: "right" },
        ]}
      />
    </ReportFrame>
  );
}

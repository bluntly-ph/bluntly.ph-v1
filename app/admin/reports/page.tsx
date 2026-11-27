import type { Metadata } from "next";

import { ReportsScreen } from "@/components/admin/reports/ReportsScreen";
import { monthFromSearch } from "@/components/admin/reports/financial-model";
import { getFinancialReport, getFinancialReportHistory } from "@/lib/moderation";

export const metadata: Metadata = { title: "Reports — bluntly admin" };

/**
 * Reports, built to Figma Screen/Admin/Reports (8028:12886; meeting 2026-10-02,
 * 18:06): the chosen month's money (net commission and its split, money in,
 * money out, still owed) and the branded PDFs generated so far. The Generate
 * report dialog (8028:13346) picks a month, quarter, year or dates and the
 * sections to print.
 *
 * The CSV exports that were Reports before (Honesty Fund, Commissions &
 * Payouts, Seller Ratings) are the tabs beside this one, unchanged.
 */
export default async function ReportsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
  const now = Date.now();
  const month = monthFromSearch(sp.month, now);
  const [report, history] = await Promise.all([getFinancialReport(month), getFinancialReportHistory()]);
  return <ReportsScreen month={month} report={report} history={history} now={now} />;
}

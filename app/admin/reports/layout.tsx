/**
 * Reports (Money → Reports). The screens are tabs of the console shell
 * (AdminNav SECTION_TABS): Reports (the financial report and its PDFs),
 * Honesty Fund, Commissions & Payouts and Seller Ratings (the CSV exports).
 *
 * Staff access is inherited from the console layout AND enforced by the API on
 * every report (`require_report_staff`); the tabs hide nothing on their own.
 * See docs/REPORTING_MODULE.md.
 */
export default function ReportsLayout({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 pb-4">{children}</div>;
}

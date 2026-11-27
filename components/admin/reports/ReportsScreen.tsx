"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CaretDown, FileText, WarningCircle } from "@phosphor-icons/react/dist/ssr";

import { GenerateReportDialog } from "@/components/admin/reports/GenerateReportDialog";
import {
  manilaDay,
  monthLabel,
  monthOptions,
  peso,
  pesoParts,
  sectionsLabel,
  shareWidths,
} from "@/components/admin/reports/financial-model";
import type { FinancialReport, FinancialReportEntry } from "@/lib/moderation";
import { DROPDOWN_PILL_STATES } from "@/components/ui/search-styles";

/**
 * Reports (Figma Screen/Admin/Reports 8028:12886; meeting 2026-10-02, 18:06):
 * the month's money at a glance — net commission and how it split, money in,
 * money out, what is still owed — and the PDFs generated so far, each one a
 * download of the same document. "Generate report" opens the dialog.
 *
 * Every figure comes from GET /admin/reports/financial, read from the ledger
 * the other reports read; the screen formats, it does not add up. The CSV
 * exports stay on the tabs beside this one.
 */

const SHARE_COLOUR: Record<string, string> = {
  bluntly: "var(--accent-primary)",
  reviewers: "var(--semantic-success-500)",
  honesty_fund: "var(--semantic-info-blue)",
};

function Money({ amount, size = 14, weight = "font-medium" }: { amount: string | null | undefined; size?: number; weight?: string }) {
  const [whole, cents] = pesoParts(amount);
  return (
    <span className={`whitespace-nowrap leading-none ${weight}`} style={{ fontSize: size }}>
      {whole}
      {cents ? <span className="text-[var(--base-gray-400)]">.{cents}</span> : null}
    </span>
  );
}

function FlowCard({
  label,
  amount,
  note,
  footLabel,
  footAmount,
  warn = false,
}: {
  label: string;
  amount: string | undefined;
  note: string;
  footLabel: string;
  footAmount: string | undefined;
  warn?: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-[6px] rounded-[16px] border border-[var(--border-subtle)] px-5 py-4">
      {/* Figma Card/Money in (8028:12886): 16px label and note lines around a 26px amount. */}
      <span className="text-[12px] leading-4 text-[var(--text-secondary)]">{label}</span>
      {amount !== undefined ? <Money amount={amount} size={26} weight="font-semibold" /> : <span className="text-[26px] leading-none">—</span>}
      <span className="text-[12px] leading-4 text-[var(--text-secondary)]">{note}</span>
      <div className="flex items-center gap-[6px] border-t border-[var(--border-subtle)] pt-2 text-[14px] leading-none">
        {warn ? <WarningCircle size={14} weight="fill" aria-hidden className="shrink-0 text-[var(--accent-primary)]" /> : null}
        <span className="flex-1">{footLabel}</span>
        {footAmount !== undefined ? <Money amount={footAmount} /> : <span>—</span>}
      </div>
    </div>
  );
}

export function ReportsScreen({
  month,
  report,
  history,
  now,
}: {
  month: string;
  report: FinancialReport | null;
  history: FinancialReportEntry[] | null;
  now: number;
}) {
  const router = useRouter();
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const months = monthOptions(now);
  if (!months.some((m) => m.value === month)) months.push({ value: month, label: monthLabel(month) });

  const r = report?.revenue;
  const shares = r?.shares ?? [];
  const widths = shareWidths(shares.map((s) => s.amount));
  const out = report?.money_out;
  const sentCount = out?.sent.count ?? 0;
  // PayPal sandbox payouts move no real money (QA test money): left out of the
  // total and said beside it, so the card never hides them silently.
  const sandboxCount = out?.sandbox_excluded?.count ?? 0;
  const monthName = monthLabel(month).split(" ")[0];

  function download(entry: FinancialReportEntry) {
    // The BFF attaches the session; the API answers with the PDF as an attachment.
    const a = document.createElement("a");
    a.href = `/api/bff${entry.download_path}`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative flex items-center">
          <span className="sr-only">Month</span>
          <select
            value={month}
            onChange={(e) => router.push(`/admin/reports?month=${e.target.value}`)}
            className={`h-8 appearance-none rounded-[32px] py-2 pl-[14px] pr-8 leading-none ${DROPDOWN_PILL_STATES}`}
          >
            {months.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
          <CaretDown size={12} aria-hidden className="pointer-events-none absolute right-[14px]" />
        </label>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => {
            setNotice(null);
            setGenerating(true);
          }}
          className="h-8 rounded-[20px] bg-[var(--accent-primary)] px-3 text-[12px] font-light leading-none text-[var(--text-on-brand)]"
        >
          Generate report
        </button>
      </div>
      {notice ? (
        <p role="status" className="text-[12px] text-[var(--text-secondary)]">
          {notice}
        </p>
      ) : null}

      {report === null ? (
        <div role="alert" className="rounded-[16px] border border-[var(--border-subtle)] px-5 py-8 text-center text-[14px] text-[var(--text-secondary)]">
          The figures for {monthLabel(month)} could not be loaded. Nothing below is a zero; try again in a moment.
        </div>
      ) : (
        <>
          <section aria-label="Net commission and split" className="flex flex-col gap-4 rounded-[16px] border border-[var(--border-subtle)] p-5">
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex flex-col gap-[6px]">
                <span className="text-[12px] leading-4 text-[var(--text-secondary)]">Net commission</span>
                <Money amount={r?.net} size={26} weight="font-semibold" />
              </div>
              <span className="flex-1" />
              <span className="text-[12px] leading-none text-[var(--text-secondary)]">
                {peso(r?.earned)} earned · {peso(r?.reversed)} reversed · {peso(r?.absorbed)} absorbed
              </span>
            </div>
            {widths.some((w) => w > 0) ? (
              <div className="flex gap-[3px]" aria-hidden>
                {shares.map((s, i) =>
                  widths[i] > 0 ? (
                    <span key={s.key} className="h-3 rounded-[6px]" style={{ width: `${widths[i]}%`, background: SHARE_COLOUR[s.key] }} />
                  ) : null,
                )}
              </div>
            ) : (
              <div className="h-3 rounded-[6px] bg-[var(--border-subtle)]" aria-hidden />
            )}
            <ul className="flex flex-wrap gap-x-8 gap-y-2">
              {shares.map((s) => (
                <li key={s.key} className="flex items-center gap-2 text-[14px] leading-none">
                  <span className="size-2 rounded-[2px]" style={{ background: SHARE_COLOUR[s.key] }} aria-hidden />
                  <span>{s.label}</span>
                  <Money amount={s.amount} />
                  <span className="text-[12px] text-[var(--text-secondary)]">{s.rate === null ? "—" : `${Math.round(s.rate)}%`}</span>
                </li>
              ))}
            </ul>
            {r && r.earned === "0.00" && r.reversed === "0.00" ? (
              <p className="text-[12px] leading-snug text-[var(--text-secondary)]">
                No marketplace commission was recognised for {monthLabel(month)} yet. Commissions arrive when a Shopee or Lazada report is imported on Affiliate.
              </p>
            ) : null}
          </section>

          <div className="flex flex-col gap-4 md:flex-row">
            <FlowCard
              label="Money in"
              amount={report.money_in.received_total}
              note={`Remitted in ${monthName}`}
              footLabel="Shortfall"
              footAmount={report.money_in.shortfall_total}
              warn={report.money_in.shortfall_total !== "0.00"}
            />
            <FlowCard
              label="Money out"
              amount={out?.paid_out_total}
              note={`${sentCount} ${sentCount === 1 ? "payout" : "payouts"} sent${
                sandboxCount ? ` · ${sandboxCount} sandbox not counted` : ""
              }`}
              footLabel="To send"
              footAmount={out?.to_send.amount}
            />
            <FlowCard
              label="Still owed"
              amount={report.liabilities.cleared_in_wallets}
              note="Cleared, in wallets"
              footLabel="Clearing"
              footAmount={report.liabilities.still_clearing}
            />
          </div>
        </>
      )}

      <div className="overflow-x-auto rounded-[12px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[860px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Generated reports</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {[
                ["Report", "w-[380px]"],
                ["Period", "w-[180px]"],
                ["Sections", "w-[160px]"],
                ["Generated", "w-[140px]"],
                ["Action", "w-[130px]"],
              ].map(([h, w]) => (
                <th key={h} scope="col" className={`${w} px-3 py-[14px] font-medium leading-none`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {history === null ? (
              <tr>
                <td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  The list of generated reports could not be loaded.
                </td>
              </tr>
            ) : history.length === 0 ? (
              <tr>
                <td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  No report generated yet. Generate one for a month, a quarter, a year or any dates.
                </td>
              </tr>
            ) : (
              history.map((entry) => (
                <tr key={entry.id} data-testid="report-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)] focus-within:bg-[var(--surface-app)]">
                  <td className="px-3 py-[10px]">
                    <span className="flex items-center gap-[10px]">
                      <span className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)] group-hover:bg-[var(--surface-card)]">
                        <FileText size={16} aria-hidden />
                      </span>
                      <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                        <span className="truncate">{entry.title}</span>
                        <span className="truncate text-[12px] text-[var(--text-secondary)]">
                          PDF · {entry.pages} {entry.pages === 1 ? "page" : "pages"}
                          {entry.generated_by ? ` · by ${entry.generated_by}` : ""}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className="px-3 leading-none">{entry.span_short}</td>
                  <td className="px-3 leading-none">{sectionsLabel(entry.sections)}</td>
                  <td className="px-3 leading-none text-[var(--text-secondary)]">{manilaDay(entry.generated_at)}</td>
                  <td className="px-3">
                    <button
                      type="button"
                      onClick={() => download(entry)}
                      aria-label={`Download ${entry.title}`}
                      className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] font-medium leading-none md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100"
                    >
                      Download
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <GenerateReportDialog
        key={generating ? "open" : "closed"}
        open={generating}
        now={now}
        initialMonth={month}
        onClose={() => setGenerating(false)}
        onGenerated={(entry) => {
          setGenerating(false);
          setNotice(`${entry.title} is ready (${entry.pages} ${entry.pages === 1 ? "page" : "pages"}). The download has started.`);
          download(entry);
          router.refresh();
        }}
      />
    </div>
  );
}

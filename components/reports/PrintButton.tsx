"use client";

import { Printer } from "@phosphor-icons/react";

/**
 * Print, or "Save as PDF" from the same dialog. The report pages carry a print
 * stylesheet (globals.css, `.report-*`), so no PDF library is needed.
 */
export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="report-no-print inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3.5 py-2 text-[13px] font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-input)]"
    >
      <Printer size={16} aria-hidden /> Print / PDF
    </button>
  );
}

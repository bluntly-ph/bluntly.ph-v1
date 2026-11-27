import { DownloadSimple } from "@phosphor-icons/react/dist/ssr";

import { PrintButton } from "./PrintButton";
import { MONTHS, yearOptions } from "./report-model";
import { FIELD_STATES } from "@/components/console/fields";

/**
 * The frame every report shares: what it is, which period, when it was
 * generated, and for whom — then the period picker, the downloads and the
 * notes that say how its numbers were computed.
 *
 * The period picker is a plain GET form, so it works before (and without)
 * JavaScript and a report URL is always shareable and bookmarkable. The server
 * re-renders the report for the new period; nothing is calculated here.
 */

export type ReportMetaLike = {
  title: string;
  period: { kind: string; label: string; start: string; end: string; timezone: string };
  generated_at: string;
  notes: string[];
};

const GENERATED = new Intl.DateTimeFormat("en-PH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Manila",
});

export function ReportFrame({
  meta,
  entity,
  downloads,
  action,
  children,
}: {
  meta: ReportMetaLike;
  entity?: string;
  downloads: { label: string; href: string }[];
  action: string;
  children: React.ReactNode;
}) {
  const [year, month] = meta.period.start.split("-").map(Number);
  const years = yearOptions(new Date().getFullYear(), 2026, year);
  const isRange = meta.period.kind === "range";

  return (
    <article className="report-root flex flex-col gap-4" aria-label={meta.title}>
      <header className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="text-[20px] font-bold leading-tight text-[var(--text-primary)]">{meta.title}</h1>
          <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
            <span data-testid="report-period">{meta.period.label}</span>
            {entity ? <> · <span className="font-semibold text-[var(--text-primary)]">{entity}</span></> : null}
          </p>
          <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
            Generated {GENERATED.format(new Date(meta.generated_at))} (Manila time)
          </p>
        </div>
        <div className="report-no-print flex flex-wrap items-center gap-2">
          {downloads.map((d) => (
            <a
              key={d.href}
              href={d.href}
              download
              className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent-primary)] px-3.5 py-2 text-[13px] font-semibold text-[var(--text-on-brand)] hover:opacity-90"
            >
              <DownloadSimple size={16} aria-hidden /> {d.label}
            </a>
          ))}
          <PrintButton />
        </div>
      </header>

      <form
        method="get"
        action={action}
        className="report-no-print flex flex-wrap items-end gap-2 rounded-[var(--radius-md)] bg-[var(--surface-card)] p-3 shadow-[var(--shadow-hairline-inset)]"
        aria-label="Reporting period"
      >
        <label className="flex flex-col text-[12px] text-[var(--text-secondary)]">
          Month
          <select
            name="month"
            defaultValue={isRange || meta.period.kind === "year" ? "" : String(month)}
            className={`mt-1 rounded-[var(--radius-sm)] px-2 py-1.5 text-[14px] ${FIELD_STATES}`}
          >
            <option value="">Whole year</option>
            {MONTHS.map((m, i) => (
              <option key={m} value={String(i + 1)}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-[12px] text-[var(--text-secondary)]">
          Year
          <select
            name="year"
            defaultValue={String(year)}
            className={`mt-1 rounded-[var(--radius-sm)] px-2 py-1.5 text-[14px] ${FIELD_STATES}`}
          >
            {years.map((y) => (
              <option key={y} value={String(y)}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <details className="text-[12px] text-[var(--text-secondary)]" open={isRange}>
          <summary className="cursor-pointer py-1.5">Custom range</summary>
          <div className="mt-1 flex flex-wrap gap-2">
            <label className="flex flex-col">
              From
              <input
                type="date"
                name="start_date"
                defaultValue={isRange ? meta.period.start : ""}
                className={`mt-1 rounded-[var(--radius-sm)] px-2 py-1 text-[14px] ${FIELD_STATES}`}
              />
            </label>
            <label className="flex flex-col">
              To
              <input
                type="date"
                name="end_date"
                defaultValue={isRange ? meta.period.end : ""}
                className={`mt-1 rounded-[var(--radius-sm)] px-2 py-1 text-[14px] ${FIELD_STATES}`}
              />
            </label>
          </div>
        </details>
        <button
          type="submit"
          className="rounded-full border border-[var(--border-subtle)] px-4 py-2 text-[13px] font-semibold text-[var(--text-primary)] hover:bg-[var(--surface-input)]"
        >
          Show
        </button>
      </form>

      {children}

      {meta.notes.length ? (
        <section aria-label="How this report is calculated" className="text-[12px] leading-relaxed text-[var(--text-muted)]">
          <ul className="list-disc space-y-1 pl-5">
            {meta.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}

/** A figure tile: label, value, optional hint. */
export function Figure({
  label,
  value,
  hint,
  tone,
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "warn" | "muted";
  testId?: string;
}) {
  const color =
    tone === "good"
      ? "text-[var(--accent-success)]"
      : tone === "warn"
        ? "text-[var(--accent-danger)]"
        : tone === "muted"
          ? "text-[var(--text-muted)]"
          : "text-[var(--text-primary)]";
  return (
    <div className="min-w-0 rounded-[var(--radius-md)] bg-[var(--surface-card)] px-4 py-3 shadow-[var(--shadow-card)]">
      <p className="text-[12px] text-[var(--text-secondary)]">{label}</p>
      <p
        data-testid={testId}
        className={`mt-1 break-words text-[20px] font-bold leading-tight [font-variant-numeric:tabular-nums] ${color}`}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-[11px] text-[var(--text-muted)]">{hint}</p> : null}
    </div>
  );
}

export type ReportColumn<T> = {
  header: string;
  cell: (row: T) => React.ReactNode;
  align?: "left" | "right";
};

/**
 * A report table. It scrolls sideways INSIDE its card on a narrow screen, so
 * the page itself never overflows; the header stays readable in print.
 */
export function ReportTable<T>({
  caption,
  columns,
  rows,
  empty,
  rowKey,
  footer,
}: {
  caption: string;
  columns: ReportColumn<T>[];
  rows: T[];
  empty: string;
  rowKey: (row: T, index: number) => string;
  footer?: React.ReactNode;
}) {
  return (
    <section aria-label={caption} className="report-section min-w-0 rounded-[var(--radius-md)] bg-[var(--surface-card)] shadow-[var(--shadow-card)]">
      <h2 className="px-4 pt-3 text-[14px] font-semibold text-[var(--text-primary)]">{caption}</h2>
      {rows.length === 0 ? (
        <p className="px-4 pb-4 pt-2 text-[13px] text-[var(--text-secondary)]" role="status">
          {empty}
        </p>
      ) : (
        <div className="report-scroll mt-2 overflow-x-auto pb-2">
          <table className="w-full min-w-max border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border-subtle)] text-[12px] text-[var(--text-secondary)]">
                {columns.map((c) => (
                  <th
                    key={c.header}
                    scope="col"
                    className={`whitespace-nowrap px-4 py-2 font-medium ${c.align === "right" ? "text-right" : "text-left"}`}
                  >
                    {c.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={rowKey(row, i)} className="border-b border-[var(--border-subtle)] last:border-0">
                  {columns.map((c) => (
                    <td
                      key={c.header}
                      className={`px-4 py-2 align-top text-[var(--text-primary)] ${c.align === "right" ? "whitespace-nowrap text-right [font-variant-numeric:tabular-nums]" : ""}`}
                    >
                      {c.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {footer ? <div className="border-t border-[var(--border-subtle)] px-4 py-2">{footer}</div> : null}
    </section>
  );
}

/** What a page shows instead of a report when it cannot show one. */
export function ReportUnavailable({ reason, detail }: { reason: string; detail?: string }) {
  const text =
    reason === "forbidden"
      ? "You don't have access to this report."
      : reason === "not_found"
        ? "There is nothing to report on here."
        : reason === "invalid"
          ? `That period can't be reported on. ${detail ?? ""}`
          : "We couldn't reach the server just now. Refresh in a moment and it should come back.";
  return (
    <div role="status" data-testid="report-unavailable" className="rounded-[var(--radius-md)] bg-[var(--surface-card)] p-8 text-center shadow-[var(--shadow-hairline-inset)]">
      <p className="text-[15px] font-semibold text-[var(--text-primary)]">
        {reason === "forbidden" ? "Not available" : reason === "invalid" ? "Invalid period" : "Report unavailable"}
      </p>
      <p className="mt-1 text-[13px] text-[var(--text-secondary)]">{text}</p>
    </div>
  );
}

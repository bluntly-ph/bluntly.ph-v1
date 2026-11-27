"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CaretDown, X } from "@phosphor-icons/react/dist/ssr";

import {
  SECTIONS,
  generateBody,
  monthOptions,
  quarterOptions,
  yearOptions,
  type PeriodKind,
  type SectionKey,
} from "@/components/admin/reports/financial-model";
import type { FinancialReportEntry } from "@/lib/moderation";
import { FIELD_STATES } from "@/components/console/fields";

/**
 * Generate report (Figma Overlay/Report/Generate 8028:13346; meeting
 * 2026-10-02, 18:06: "options for what to include, which month, which period").
 *
 * 560px, radius 16: the period as Month / Quarter / Year / Custom chips, the
 * month (quarter, year, or two dates) in a select field, the four sections as
 * switches, then Cancel and Generate PDF. The PDF is drawn on the server from
 * the ledger, logged in the Reports table, and downloaded straight away.
 */

const KINDS: { key: PeriodKind; label: string }[] = [
  { key: "month", label: "Month" },
  { key: "quarter", label: "Quarter" },
  { key: "year", label: "Year" },
  { key: "custom", label: "Custom" },
];

function Switch({ on, onToggle, labelledBy }: { on: boolean; onToggle: () => void; labelledBy: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-labelledby={labelledBy}
      onClick={onToggle}
      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] ${
        on ? "bg-[var(--accent-primary)]" : "bg-[var(--base-gray-200)]"
      }`}
    >
      <span
        aria-hidden
        className={`absolute top-[2px] size-4 rounded-full bg-white shadow-[0_1px_2px_rgba(0,0,0,0.2)] transition-[left] ${
          on ? "left-[18px]" : "left-[2px]"
        }`}
      />
    </button>
  );
}

export function GenerateReportDialog({
  open,
  now,
  initialMonth,
  onClose,
  onGenerated,
}: {
  open: boolean;
  now: number;
  initialMonth: string;
  onClose: () => void;
  onGenerated: (entry: FinancialReportEntry) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const fieldId = useId();
  const [kind, setKind] = useState<PeriodKind>("month");
  const [month, setMonth] = useState(initialMonth);
  const [quarter, setQuarter] = useState(() => quarterOptions(now)[0].value);
  const [year, setYear] = useState(() => yearOptions(now)[0].value);
  const [range, setRange] = useState({ start: "", end: "" });
  const [sections, setSections] = useState<SectionKey[]>(SECTIONS.map((s) => s.key));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  function toggle(key: SectionKey) {
    setSections((current) => (current.includes(key) ? current.filter((k) => k !== key) : [...current, key]));
  }

  async function generate() {
    const value = kind === "month" ? month : kind === "quarter" ? quarter : year;
    const body = generateBody(kind, value, range, sections);
    if (typeof body === "string") {
      setError(body);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/admin/reports/financial/generate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = (await res.json().catch(() => ({}))) as FinancialReportEntry & { detail?: string; title?: string };
      if (!res.ok) {
        setError(payload.detail ?? payload.title ?? "The report could not be generated.");
        return;
      }
      onGenerated(payload);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const fieldLabel = kind === "custom" ? "Dates" : KINDS.find((k) => k.key === kind)?.label;
  const options = kind === "month" ? monthOptions(now) : kind === "quarter" ? quarterOptions(now) : yearOptions(now);
  const selected = kind === "month" ? month : kind === "quarter" ? quarter : year;
  const select = (v: string) => (kind === "month" ? setMonth(v) : kind === "quarter" ? setQuarter(v) : setYear(v));
  const field = `${FIELD_STATES} h-[52px] w-full rounded-[12px] px-4 text-[16px] tracking-[0.05em]`;

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      className="m-auto w-[560px] max-w-[calc(100vw-32px)] overflow-hidden rounded-[16px] bg-[var(--surface-card)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-modal)] backdrop:bg-black/30 [&:not([open])]:hidden"
    >
      <div className="flex items-center pb-4 pl-6 pr-5 pt-5">
        <h2 id={titleId} className="flex-1 text-[20px] font-semibold leading-none">
          Generate report
        </h2>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close"
          className="grid size-8 place-items-center rounded-full hover:bg-[var(--surface-app)]"
        >
          <X size={18} />
        </button>
      </div>

      <div className="flex flex-col gap-5 px-6 pb-6 pt-1">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-[12px] leading-none text-[var(--text-secondary)]">Period</legend>
          <div className="flex flex-wrap gap-[6px]">
            {KINDS.map((k) => (
              <button
                key={k.key}
                type="button"
                aria-pressed={kind === k.key}
                onClick={() => {
                  setKind(k.key);
                  setError(null);
                }}
                className={`rounded-full px-3 py-[6px] text-[14px] leading-none ${
                  kind === k.key
                    ? "bg-[var(--text-primary)] text-[var(--text-on-brand)]"
                    : "border border-[var(--border-subtle)] bg-[var(--surface-card)] text-[var(--text-primary)] hover:bg-[var(--surface-app)]"
                }`}
              >
                {k.label}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="flex flex-col gap-[6px]">
          <label htmlFor={fieldId} className="text-[12px] leading-none text-[var(--base-gray-400)]">
            {fieldLabel}
          </label>
          {kind === "custom" ? (
            <div className="grid grid-cols-2 gap-2">
              <input
                id={fieldId}
                type="date"
                aria-label="Start date"
                value={range.start}
                onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))}
                className={field}
              />
              <input
                type="date"
                aria-label="End date"
                value={range.end}
                onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))}
                className={field}
              />
            </div>
          ) : (
            <div className="relative">
              <select id={fieldId} value={selected} onChange={(e) => select(e.target.value)} className={`${field} appearance-none pr-10`}>
                {options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <CaretDown size={16} aria-hidden className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2" />
            </div>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <p className="text-[12px] leading-none text-[var(--text-secondary)]">Sections</p>
          {SECTIONS.map((s, i) => {
            const id = `${fieldId}-${s.key}`;
            return (
              <div key={s.key} className={`flex items-center gap-3 py-[10px] ${i > 0 ? "border-t border-[var(--border-subtle)]" : ""}`}>
                <div className="flex min-w-0 flex-1 flex-col gap-[2px] leading-none">
                  <span id={id} className="text-[14px]">
                    {s.label}
                  </span>
                  <span className="text-[12px] text-[var(--text-secondary)]">{s.detail}</span>
                </div>
                <Switch on={sections.includes(s.key)} onToggle={() => toggle(s.key)} labelledBy={id} />
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-6 pb-5 pt-4">
        {error ? (
          <p role="alert" className="min-w-0 flex-1 text-[12px] leading-snug text-[var(--accent-danger)]">
            {error}
          </p>
        ) : (
          <p className="min-w-0 flex-1 text-[12px] leading-none text-[var(--text-secondary)]">Figures as of now, Manila time.</p>
        )}
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="h-8 rounded-[20px] border border-[var(--border-default)] px-3 text-[12px] font-light leading-none disabled:opacity-60"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void generate()}
          disabled={busy || sections.length === 0}
          className="h-8 rounded-[20px] bg-[var(--accent-primary)] px-3 text-[12px] font-light leading-none text-[var(--text-on-brand)] disabled:opacity-60"
        >
          {busy ? "Generating…" : "Generate PDF"}
        </button>
      </div>
    </dialog>
  );
}

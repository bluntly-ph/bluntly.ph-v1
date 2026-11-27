/**
 * Pure helpers for the Reports screen and its Generate report dialog (Figma
 * Screen/Admin/Reports 8028:12886, Overlay/Report/Generate 8028:13346). No
 * React, no fetch — unit-tested in tests/frontend/financial-report-model.test.mjs.
 *
 * Money stays a decimal string: `formatPeso` only inserts separators and the
 * sign. The bar's segment widths are proportions, not money, so a number is
 * fine there.
 */

import { formatPeso } from "../../reports/report-model.ts";

export const SECTIONS = [
  { key: "revenue", label: "Revenue & split", detail: "Earned, reversed, absorbed; Bluntly, reviewer and Honesty Fund shares" },
  { key: "money_in", label: "Money in", detail: "Marketplace remittances and shortfalls" },
  { key: "money_out", label: "Money out", detail: "Payouts sent, to send, failed, cancelled; Honesty Fund" },
  { key: "liabilities", label: "Liabilities", detail: "Cleared in wallets, still clearing, unattributed" },
] as const;

export type SectionKey = (typeof SECTIONS)[number]["key"];
export type PeriodKind = "month" | "quarter" | "year" | "custom";

const TZ = "Asia/Manila";

/** "1234.5" -> "₱1,234.50" (the reports' one formatter). */
export const peso = formatPeso;

/** "30132.5" -> ["₱30,132", "50"]: the whole part and the grey cents. */
export function pesoParts(value: string | null | undefined): [string, string] {
  const text = formatPeso(value);
  const dot = text.lastIndexOf(".");
  return dot < 0 ? [text, ""] : [text.slice(0, dot), text.slice(dot + 1)];
}

/** The Manila calendar month of an instant, as "YYYY-MM". */
export function manilaMonth(now: number): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit" }).formatToParts(new Date(now));
  const y = parts.find((p) => p.type === "year")?.value ?? "1970";
  const m = parts.find((p) => p.type === "month")?.value ?? "01";
  return `${y}-${m}`;
}

function shift(month: string, back: number): string {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + (m - 1) - back;
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, "0")}`;
}

/** "2026-09" -> "September 2026". */
export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 15)).toLocaleDateString("en-PH", { month: "long", year: "numeric", timeZone: "UTC" });
}

/** The current Manila month and the eleven before it, newest first. */
export function monthOptions(now: number, count = 12): { value: string; label: string }[] {
  const current = manilaMonth(now);
  return Array.from({ length: count }, (_, i) => {
    const value = shift(current, i);
    return { value, label: monthLabel(value) };
  });
}

/** This quarter and the seven before it: { value: "2026-3", label: "Q3 2026" }. */
export function quarterOptions(now: number, count = 8): { value: string; label: string }[] {
  const [y, m] = manilaMonth(now).split("-").map(Number);
  let index = y * 4 + Math.floor((m - 1) / 3);
  return Array.from({ length: count }, () => {
    const year = Math.floor(index / 4);
    const q = (index % 4) + 1;
    index -= 1;
    return { value: `${year}-${q}`, label: `Q${q} ${year}` };
  });
}

/** This year and the two before it. */
export function yearOptions(now: number, count = 3): { value: string; label: string }[] {
  const year = Number(manilaMonth(now).slice(0, 4));
  return Array.from({ length: count }, (_, i) => ({ value: String(year - i), label: String(year - i) }));
}

/** ?month=2026-09 when well formed, otherwise the current Manila month. */
export function monthFromSearch(value: string | string[] | undefined, now: number): string {
  const v = Array.isArray(value) ? value[0] : value;
  return v && /^\d{4}-(0[1-9]|1[0-2])$/.test(v) ? v : manilaMonth(now);
}

/** The table's Sections cell: "All 4" or "Money in, Money out". */
export function sectionsLabel(sections: string[]): string {
  if (SECTIONS.every((s) => sections.includes(s.key))) return `All ${SECTIONS.length}`;
  return SECTIONS.filter((s) => sections.includes(s.key))
    .map((s) => s.label)
    .join(", ");
}

const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "1 Sep 2026", in Manila (ICU's en-GB says "Sept"; the design says "Sep"). */
export function manilaDay(iso: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "numeric", day: "numeric" }).formatToParts(new Date(iso));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return `${get("day")} ${SHORT_MONTHS[get("month") - 1] ?? ""} ${get("year")}`;
}

/** Segment widths (percent of the bar) for the positive shares, in order. */
export function shareWidths(amounts: string[]): number[] {
  const values = amounts.map((a) => Math.max(0, Number(a) || 0));
  const total = values.reduce((sum, v) => sum + v, 0);
  return total > 0 ? values.map((v) => (v / total) * 100) : values.map(() => 0);
}

export type GenerateBody = {
  kind: PeriodKind;
  year?: number;
  month?: number;
  quarter?: number;
  start_date?: string;
  end_date?: string;
  sections: SectionKey[];
};

/**
 * The POST body for a choice in the dialog, or an error message the dialog
 * shows instead of sending something the API would refuse.
 */
export function generateBody(
  kind: PeriodKind,
  value: string,
  range: { start: string; end: string },
  sections: SectionKey[],
): GenerateBody | string {
  if (sections.length === 0) return "Choose at least one section.";
  const ordered = SECTIONS.map((s) => s.key).filter((k) => sections.includes(k));
  if (kind === "month") {
    const [y, m] = value.split("-").map(Number);
    return { kind, year: y, month: m, sections: ordered };
  }
  if (kind === "quarter") {
    const [y, q] = value.split("-").map(Number);
    return { kind, year: y, quarter: q, sections: ordered };
  }
  if (kind === "year") return { kind, year: Number(value), sections: ordered };
  const isDate = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s);
  if (!isDate(range.start) || !isDate(range.end)) return "Choose a start and an end date.";
  if (range.end < range.start) return "The end date is before the start date.";
  return { kind, start_date: range.start, end_date: range.end, sections: ordered };
}

/**
 * Pure helpers for the four system reports. No React, no fetch — unit-tested
 * in tests/frontend/report-model.test.mjs.
 *
 * MONEY IS NEVER A FLOAT HERE. The API sends every amount as a decimal string
 * ("1234.50"); these helpers only insert separators and a sign into that
 * string. Every figure is calculated on the server, from the ledger — the UI
 * formats, it does not add up.
 */

export type PeriodParams = {
  month?: string;
  year?: string;
  start_date?: string;
  end_date?: string;
};

const DECIMAL = /^(-)?(\d+)(?:\.(\d+))?$/;

/** "1234.5" -> "₱1,234.50"; "-12.5" -> "−₱12.50"; null/garbage -> "—". */
export function formatPeso(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const match = DECIMAL.exec(String(value).trim());
  if (!match) return "—";
  const [, minus, whole, fraction = ""] = match;
  const cents = (fraction + "00").slice(0, 2);
  const grouped = whole.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const isZero = /^0*$/.test(whole) && /^0*$/.test(cents);
  return `${minus && !isZero ? "−" : ""}₱${grouped}.${cents}`;
}

/** 0.6667 -> "66.7%"; null -> "—". Rates are not money, so a number is fine. */
export function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return "—";
  return `${(Math.round(rate * 1000) / 10).toFixed(1)}%`;
}

/** A 0-5 rating to one decimal place, or "—". */
export function formatRating(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(n % 1 === 0 ? 0 : 2).replace(/0$/, "") : "—";
}

/**
 * The period a page was asked for, reduced to the parameters the API accepts.
 * A custom range wins only when BOTH ends are present; otherwise month/year.
 * Anything malformed is dropped rather than forwarded — the API would refuse
 * it anyway, and a report that errors on a typo is worse than the default.
 */
export function periodFromSearch(sp: Record<string, string | string[] | undefined>): PeriodParams {
  const one = (k: string) => {
    const v = sp[k];
    return typeof v === "string" ? v.trim() : undefined;
  };
  const start = one("start_date");
  const end = one("end_date");
  const isDate = (s?: string) => !!s && /^\d{4}-\d{2}-\d{2}$/.test(s);
  if (isDate(start) && isDate(end)) return { start_date: start, end_date: end };
  const year = one("year");
  const month = one("month");
  const out: PeriodParams = {};
  if (year && /^\d{4}$/.test(year)) {
    out.year = year;
    if (month && /^(0?[1-9]|1[0-2])$/.test(month)) out.month = String(Number(month));
  }
  return out;
}

/** Query string for a period (no leading "?"), stable key order. */
export function periodQuery(p: PeriodParams, extra: Record<string, string> = {}): string {
  const params = new URLSearchParams();
  for (const key of ["month", "year", "start_date", "end_date"] as const) {
    const v = p[key];
    if (v) params.set(key, v);
  }
  for (const [k, v] of Object.entries(extra)) params.set(k, v);
  return params.toString();
}

/**
 * The browser's download link for a report's CSV. It goes through the BFF,
 * which attaches the session server-side — the browser never holds a token.
 */
export function csvHref(apiPath: string, p: PeriodParams, section?: string): string {
  const extra: Record<string, string> = { format: "csv" };
  if (section) extra.section = section;
  return `/api/bff${apiPath}?${periodQuery(p, extra)}`;
}

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/**
 * Years offered in the picker: this year back to 2026 (the platform's first),
 * plus the year being shown if it lies outside that — a report opened from a
 * link for another year must still show that year as selected.
 */
export function yearOptions(currentYear: number, first = 2026, selected?: number): number[] {
  const out: number[] = [];
  for (let y = Math.max(currentYear, first); y >= first; y -= 1) out.push(y);
  if (selected && Number.isInteger(selected) && !out.includes(selected)) {
    out.push(selected);
    out.sort((a, b) => b - a);
  }
  return out;
}

/** "2026-09-01" -> "Sep 2026" regardless of the browser's locale. */
export function cycleLabel(isoDate: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(isoDate);
  if (!m) return isoDate;
  return `${MONTHS[Number(m[2]) - 1]?.slice(0, 3) ?? m[2]} ${m[1]}`;
}

/** Reviewer-facing wording for the canonical statuses the API returns. */
export const STATUS_LABEL: Record<string, string> = {
  clearing: "Clearing",
  cleared: "Cleared",
  returned: "Returned",
  reversal: "Reversal",
  qa_test: "QA test earning",
  awaiting_remittance: "Awaiting marketplace payout",
  reconciled: "Reconciled",
  scheduled: "Requested",
  processing: "Processing",
  paid: "Paid",
  failed: "Failed",
  cancelled: "Cancelled",
  eligible: "Eligible",
  excluded: "Excluded",
  distributed: "Distributed",
  not_distributed: "Not distributed",
  pending_formula: "Pending distribution formula",
  reviewer: "Reviewer",
  honesty_fund: "Honesty Fund",
  removed: "Removed",
  not_public: "Not public",
  claimed_seller: "Claimed seller",
  concentration_hold: "Concentration hold",
  not_eligible: "Not eligible",
};

export function statusLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return STATUS_LABEL[value] ?? value.replace(/_/g, " ");
}

const VERDICT_LABEL: Record<string, string> = {
  yes_absolutely: "Yes, absolutely",
  it_depends: "It depends",
  hard_pass: "Hard pass",
};

export function verdictLabel(value: string | null | undefined): string {
  return value ? VERDICT_LABEL[value] ?? value : "—";
}

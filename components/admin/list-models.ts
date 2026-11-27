/**
 * Sort / filter / search for the console lists the Figma gave menus to
 * (Menu/Sellers/Claims/*, Menu/Sellers/Appeals/*, Menu/Payouts/*,
 * Menu/Payouts/HonestyFund/*, Menu/Affiliate/Months/*, Menu/Affiliate/Imports/*,
 * 8288:*). Pure functions over rows the screens already hold, so the menus
 * never ask the API for anything new and tests/frontend can check them.
 */

import type { FilterGroup } from "../console/list-query";

function includesText(haystack: (string | null | undefined)[], q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  return haystack.some((h) => (h ?? "").toLowerCase().includes(needle));
}

type Q = Record<string, string>;
const time = (iso: string | null | undefined) => (iso ? new Date(iso).getTime() : 0);
const num = (v: string | number | null | undefined) => Number(v ?? 0) || 0;

// ---------------------------------------------------------------- claims

export const CLAIM_SORTS: [string, string][] = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["store", "Store A–Z"],
];
export const CLAIM_FILTERS: FilterGroup[] = [
  { key: "reg", title: "Registration", options: [["dti", "DTI"], ["sec", "SEC"], ["none", "Not registered"]] },
  { key: "market", title: "Marketplace", options: [["shopee", "Shopee"], ["lazada", "Lazada"]] },
];
type ClaimRow = {
  created_at: string;
  seller_display_name?: string | null;
  seller_platform?: string | null;
  registration_kind?: string | null;
  registration_number?: string | null;
  marketplace_shop_name?: string | null;
  claimant?: { display_name?: string | null; username?: string | null } | null;
};
/** Queues stay first in, first out by default (the order the API always used). */
export const CLAIM_DEFAULT_SORT = "oldest";
export const APPEAL_DEFAULT_SORT = "oldest";

export function applyClaims<T extends ClaimRow>(rows: T[], q: Q): T[] {
  const out = rows.filter(
    (c) =>
      (!q.reg || (q.reg === "none" ? !c.registration_kind || !c.registration_number : c.registration_kind === q.reg)) &&
      (!q.market || c.seller_platform === q.market) &&
      includesText([c.seller_display_name, c.marketplace_shop_name, c.claimant?.display_name, c.claimant?.username], q.q ?? ""),
  );
  const sort = q.sort || CLAIM_DEFAULT_SORT;
  return out.sort((a, b) =>
    sort === "store"
      ? (a.seller_display_name ?? "").localeCompare(b.seller_display_name ?? "")
      : (sort === "oldest" ? 1 : -1) * (time(a.created_at) - time(b.created_at)),
  );
}

// ---------------------------------------------------------------- appeals

export const APPEAL_SORTS: [string, string][] = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["rating", "Lowest rating first"],
];
export const APPEAL_FILTERS: FilterGroup[] = [
  { key: "status", title: "Status", options: [["open", "Open"], ["proof", "Proof requested"], ["upheld", "Upheld"], ["dismissed", "Dismissed"]] },
  { key: "rating", title: "Rating", options: [["1", "1★"], ["2", "2★"], ["3", "3★"]] },
];
/** The decided statuses live outside the open queue; the page asks for them only when filtered. */
export function wantsDecidedAppeals(q: Q): boolean {
  return q.status === "upheld" || q.status === "dismissed";
}
type AppealRow = {
  created_at: string;
  status: string;
  review_rating?: number | string | null;
  seller_name?: string | null;
  reason: string;
  reviewer?: { display_name?: string | null; username?: string | null } | null;
};
export function applyAppeals<T extends AppealRow>(rows: T[], q: Q): T[] {
  const status = q.status === "proof" ? "substantiation_requested" : q.status;
  const out = rows.filter(
    (a) =>
      (!status || a.status === status) &&
      (!q.rating || Math.floor(num(a.review_rating)) === Number(q.rating)) &&
      includesText([a.seller_name, a.reviewer?.display_name, a.reviewer?.username, a.reason], q.q ?? ""),
  );
  const sort = q.sort || APPEAL_DEFAULT_SORT;
  return out.sort((a, b) =>
    sort === "rating" ? num(a.review_rating) - num(b.review_rating) || time(a.created_at) - time(b.created_at)
    : (sort === "oldest" ? 1 : -1) * (time(a.created_at) - time(b.created_at)),
  );
}

// ---------------------------------------------------------------- payouts

export const PAYOUT_SORTS: [string, string][] = [
  ["oldest", "Oldest request first"],
  ["highest", "Highest amount"],
  ["lowest", "Lowest amount"],
];
/** Figma also draws "Send to: PayPal / GCash / Maya / Bank"; every payout goes by PayPal today
 *  (GCash and Maya are a simulation), so that group would only ever empty the list. */
export const PAYOUT_FILTERS: FilterGroup[] = [
  { key: "amount", title: "Amount", options: [["under500", "Under ₱500"], ["500to2000", "₱500–2,000"], ["over2000", "Over ₱2,000"]] },
];
type PayoutRow = { amount: string | number; created_at: string; payout_id?: string | null; display_name?: string | null; username?: string | null };
export function applyPayouts<T extends PayoutRow>(rows: T[], q: Q): T[] {
  const band = (v: number) => (v < 500 ? "under500" : v <= 2000 ? "500to2000" : "over2000");
  const out = rows.filter(
    (p) => (!q.amount || band(num(p.amount)) === q.amount) && includesText([p.display_name, p.username, p.payout_id], q.q ?? ""),
  );
  const sort = q.sort || "oldest";
  return out.sort((a, b) =>
    sort === "highest" ? num(b.amount) - num(a.amount) : sort === "lowest" ? num(a.amount) - num(b.amount) : time(a.created_at) - time(b.created_at),
  );
}

// ---------------------------------------------------------------- Honesty Fund cycles

export const FUND_SORTS: [string, string][] = [
  ["newest", "Newest cycle"],
  ["oldest", "Oldest cycle"],
  ["pool", "Largest pool"],
];
/** collecting = "Scheduled" (it distributes at month end); not_distributed = "Held". */
export const FUND_FILTERS: FilterGroup[] = [
  { key: "status", title: "Status", options: [["distributed", "Distributed"], ["collecting", "Scheduled"], ["not_distributed", "Held"]] },
];
type CycleRow = { month: string; status: string; pool?: string | number | null };
export function applyCycles<T extends CycleRow>(rows: T[], q: Q): T[] {
  const out = rows.filter((c) => !q.status || c.status === q.status);
  const sort = q.sort || "newest";
  return out.sort((a, b) =>
    sort === "pool" ? num(b.pool) - num(a.pool) : (sort === "oldest" ? 1 : -1) * a.month.localeCompare(b.month),
  );
}

// ---------------------------------------------------------------- Affiliate months / imports

export const MONTH_SORTS: [string, string][] = [
  ["newest", "Newest month"],
  ["oldest", "Oldest month"],
  ["shortfall", "Largest shortfall"],
];
export const MONTH_FILTERS: FilterGroup[] = [
  { key: "status", title: "Status", options: [["settled", "Settled"], ["waiting", "Waiting on remittance"], ["short", "Short"]] },
];
type MonthRow = { cycle_month: string; net: string | number; remitted?: string | number | null; status: string };
/** What the marketplace still owes on a month: its net less what it remitted. */
export function shortfall(m: MonthRow): number {
  return Math.max(0, num(m.net) - num(m.remitted));
}
export function monthState(m: MonthRow): "settled" | "waiting" | "short" {
  if (m.status !== "remitted") return "waiting";
  return shortfall(m) > 0.004 ? "short" : "settled";
}
export function applyMonths<T extends MonthRow>(rows: T[], q: Q): T[] {
  const out = rows.filter((m) => !q.status || monthState(m) === q.status);
  const sort = q.sort || "newest";
  return out.sort((a, b) =>
    sort === "shortfall" ? shortfall(b) - shortfall(a) : (sort === "oldest" ? 1 : -1) * a.cycle_month.localeCompare(b.cycle_month),
  );
}

export const IMPORT_SORTS: [string, string][] = [
  ["newest", "Newest first"],
  ["oldest", "Oldest first"],
  ["unattributed", "Most unattributed"],
];
type ImportRow = { imported_at: string; filename?: string | null; unattributed?: number | null };
export function applyImports<T extends ImportRow>(rows: T[], q: Q): T[] {
  const out = rows.filter((i) => includesText([i.filename], q.q ?? ""));
  const sort = q.sort || "newest";
  return out.sort((a, b) =>
    sort === "unattributed" ? num(b.unattributed) - num(a.unattributed) : (sort === "oldest" ? 1 : -1) * (time(a.imported_at) - time(b.imported_at)),
  );
}

/** "DTI 3482917" (Figma 7992:11327): the kind once, even when the number was typed with it ("DTI-3482917"). */
export function registrationNumber(kind: string | null | undefined, number: string | null | undefined): string {
  if (!number) return "—";
  const k = (kind ?? "dti").toUpperCase();
  return number.trim().replace(new RegExp(`^${k}[\\s#:-]*`, "i"), "") || number;
}

export function registrationLabel(kind: string | null | undefined, number: string | null | undefined): string {
  return `${(kind ?? "dti").toUpperCase()} ${registrationNumber(kind, number)}`;
}

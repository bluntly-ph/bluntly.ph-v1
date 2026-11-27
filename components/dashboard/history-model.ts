/**
 * The contributor History ledger (Figma Screen/History 8098:17238), built from
 * the earnings statement (GET /reports/earnings-statement): commissions, their
 * returns, Honesty Fund credits and payouts, one row each, grouped by month.
 * Pure; tested in tests/frontend/history-model.test.mjs.
 *
 * Nothing is invented: the frame's "Request reward" and "Adjustment by
 * Bluntly" rows have no record behind them in this product, so they never
 * appear.
 */

export type StatementEntry = {
  recognised_at: string;
  /** The accounting cycle the commission belongs to (YYYY-MM-01): its month here. */
  cycle_month: string;
  product: string | null;
  marketplace: string | null;
  reviewer_earning: string;
  status: string;
  review_title: string | null;
};
export type StatementFund = { cycle_month: string; amount: string };
export type StatementPayout = {
  requested_at: string;
  processed_at: string | null;
  amount: string;
  method: string;
  destination: string | null;
  reference: string | null;
  status: string;
};

export type LedgerKind = "commission" | "return" | "fund" | "payout";
export type LedgerTone = "positive" | "negative" | "muted";
export type LedgerRow = {
  kind: LedgerKind;
  /** The month it belongs to: a commission's or credit's cycle, a payout's date. */
  month: string;
  at: string;
  title: string;
  detail: string;
  amount: number;
  status: string;
  tone: LedgerTone;
};
export type LedgerMonth = { key: string; label: string; net: number; rows: LedgerRow[] };

export const TYPE_FILTERS: [string, string][] = [
  ["all", "All types"],
  ["commission", "Commissions"],
  ["fund", "Honesty Fund"],
  ["payout", "Payouts"],
  ["return", "Returns"],
];

const MARKET: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", amazon: "Amazon", other: "Marketplace" };
const METHOD: Record<string, string> = { paypal: "PayPal", gcash: "GCash", maya: "Maya", bank: "bank" };
const monthKey = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { timeZone: "Asia/Manila" }).slice(0, 7);
const monthLabel = (key: string) =>
  new Date(`${key}-15T00:00:00+08:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric", timeZone: "Asia/Manila" });

export function ledgerRows(entries: StatementEntry[], funds: StatementFund[], payouts: StatementPayout[]): LedgerRow[] {
  const rows: LedgerRow[] = [];
  for (const e of entries) {
    const amount = Number(e.reviewer_earning);
    const where = [e.product ?? e.review_title, e.marketplace ? `${MARKET[e.marketplace] ?? e.marketplace} order` : null].filter(Boolean).join(" · ");
    if (e.status === "returned" || e.status === "reversal" || amount < 0) {
      rows.push({ kind: "return", month: e.cycle_month.slice(0, 7), at: e.recognised_at, title: "Order returned", detail: `${where || "An order"} · commission reversed`, amount: -Math.abs(amount), status: "Reversed", tone: "negative" });
    } else {
      rows.push({
        kind: "commission",
        month: e.cycle_month.slice(0, 7),
        at: e.recognised_at,
        title: "Commission",
        detail: e.status === "qa_test" ? "QA test earning · not real money" : where || "Affiliate sale",
        amount,
        status: e.status === "cleared" ? "Cleared" : e.status === "qa_test" ? "Sandbox test" : "Pending",
        tone: "positive",
      });
    }
  }
  for (const f of funds) {
    rows.push({ kind: "fund", month: f.cycle_month.slice(0, 7), at: `${f.cycle_month}T00:00:00+08:00`, title: "Honesty Fund share", detail: `${monthLabel(f.cycle_month.slice(0, 7)).split(" ")[0]} cycle`, amount: Number(f.amount), status: "Cleared", tone: "positive" });
  }
  for (const p of payouts) {
    const to = `${METHOD[p.method] ?? p.method}${p.destination ? ` ${p.destination}` : ""}`;
    const amount = Number(p.amount);
    if (p.status === "cancelled" || p.status === "failed") {
      rows.push({
        kind: "payout",
        month: monthKey(p.processed_at ?? p.requested_at),
        at: p.processed_at ?? p.requested_at,
        title: p.status === "cancelled" ? "Payout cancelled" : "Payout failed",
        detail: `₱${amount.toLocaleString("en-PH", { minimumFractionDigits: 2 })} returned to your wallet`,
        amount,
        status: "Refunded",
        tone: "positive",
      });
    } else {
      const at = p.status === "paid" ? (p.processed_at ?? p.requested_at) : p.requested_at;
      rows.push({
        kind: "payout",
        month: monthKey(at),
        at,
        title: `Payout to ${to}`,
        detail: p.reference ? `Reference ${p.reference}` : p.status === "paid" ? "Sent" : "Requested",
        amount: -amount,
        status: p.status === "paid" ? "Sent" : p.status === "processing" ? "Processing" : "Requested",
        tone: p.status === "paid" ? "negative" : "muted",
      });
    }
  }
  return rows.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

export function groupByMonth(rows: LedgerRow[], type = "all"): LedgerMonth[] {
  const months: LedgerMonth[] = [];
  for (const r of rows) {
    if (type !== "all" && r.kind !== type) continue;
    const key = r.month;
    let m = months.find((x) => x.key === key);
    if (!m) {
      m = { key, label: monthLabel(key), net: 0, rows: [] };
      months.push(m);
    }
    m.rows.push(r);
    m.net += r.amount;
  }
  for (const m of months) m.net = Math.round(m.net * 100) / 100;
  return months.sort((a, b) => b.key.localeCompare(a.key));
}

/** The header: what was earned and what was paid out in `monthKey`. */
export function monthTotals(rows: LedgerRow[], key: string): { earned: number; paid: number } {
  let earned = 0;
  let paid = 0;
  for (const r of rows) {
    if (r.month !== key) continue;
    if (r.kind === "commission" || r.kind === "fund") earned += r.amount;
    if (r.kind === "return") earned += r.amount;
    if (r.kind === "payout" && r.status === "Sent") paid += -r.amount;
  }
  return { earned: Math.round(earned * 100) / 100, paid: Math.round(paid * 100) / 100 };
}

export { monthKey };

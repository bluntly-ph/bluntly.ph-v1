import assert from "node:assert/strict";
import test from "node:test";

import { groupByMonth, ledgerRows, monthTotals } from "../../components/dashboard/history-model.ts";

const entries = [
  { recognised_at: "2026-10-02T03:00:00Z", product: "Jisulife Fan", marketplace: "shopee", cycle_month: "2026-10-01", reviewer_earning: "86.40", status: "clearing", review_title: null },
  { recognised_at: "2026-09-20T03:00:00Z", product: "Aula F75", marketplace: "lazada", cycle_month: "2026-09-01", reviewer_earning: "-42.00", status: "reversal", review_title: null },
  { recognised_at: "2026-09-10T03:00:00Z", product: "Xiaomi Band", marketplace: "shopee", cycle_month: "2026-09-01", reviewer_earning: "118.25", status: "cleared", review_title: null },
];
const funds = [{ cycle_month: "2026-10-01", amount: "41.20" }];
const payouts = [
  { requested_at: "2026-10-01T05:00:00Z", processed_at: "2026-10-02T05:00:00Z", amount: "1240.00", method: "paypal", destination: "j***@gmail.com", reference: "7X44A2", status: "paid" },
  { requested_at: "2026-09-05T05:00:00Z", processed_at: "2026-09-06T05:00:00Z", amount: "300.00", method: "paypal", destination: null, reference: null, status: "cancelled" },
];

test("rows: commissions, returns, fund credits and payouts, newest first", () => {
  const rows = ledgerRows(entries, funds, payouts);
  assert.deepEqual(rows.map((r) => [r.title, r.amount, r.status]), [
    ["Payout to PayPal j***@gmail.com", -1240, "Sent"],
    ["Commission", 86.4, "Pending"],
    ["Honesty Fund share", 41.2, "Cleared"],
    ["Order returned", -42, "Reversed"],
    ["Commission", 118.25, "Cleared"],
    ["Payout cancelled", 300, "Refunded"],
  ]);
});

test("a commission sits in its cycle month, not the day its row was written", () => {
  const rows = ledgerRows([{ ...entries[2], recognised_at: "2026-10-03T00:00:00Z", cycle_month: "2026-07-01" }], [], []);
  assert.equal(groupByMonth(rows)[0].key, "2026-07");
});

test("months group, net and filter by type; the header totals one month", () => {
  const rows = ledgerRows(entries, funds, payouts);
  const months = groupByMonth(rows);
  assert.deepEqual(months.map((m) => [m.key, m.net, m.rows.length]), [["2026-10", -1112.4, 3], ["2026-09", 376.25, 3]]);
  assert.deepEqual(groupByMonth(rows, "payout").map((m) => m.rows.length), [1, 1]);
  assert.deepEqual(groupByMonth(rows, "return").map((m) => m.key), ["2026-09"]);
  assert.deepEqual(monthTotals(rows, "2026-10"), { earned: 127.6, paid: 1240 });
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  csvHref,
  cycleLabel,
  formatPeso,
  formatRate,
  formatRating,
  periodFromSearch,
  periodQuery,
  statusLabel,
  yearOptions,
} from "../../components/reports/report-model.ts";

/**
 * The reports' presentation helpers. Money arrives as decimal strings and must
 * leave as exactly the same value — a float anywhere in between is how
 * 0.1 + 0.2 ends up on a financial statement.
 */

test("pesos keep their exact value, grouped and signed", () => {
  assert.equal(formatPeso("1234.5"), "₱1,234.50");
  assert.equal(formatPeso("2169.97"), "₱2,169.97");
  assert.equal(formatPeso("300.00"), "₱300.00");
  assert.equal(formatPeso("299.99"), "₱299.99");
  assert.equal(formatPeso("-12.50"), "−₱12.50");
  assert.equal(formatPeso("0.00"), "₱0.00");
  assert.equal(formatPeso("-0.00"), "₱0.00");
  assert.equal(formatPeso("1000000"), "₱1,000,000.00");
  assert.equal(formatPeso("9007199254740993.01"), "₱9,007,199,254,740,993.01");
});

test("anything that is not a decimal renders as a dash, never NaN", () => {
  for (const v of [null, undefined, "", "abc", "1e5", "NaN"]) assert.equal(formatPeso(v), "—");
});

test("rates and ratings", () => {
  assert.equal(formatRate(0.6667), "66.7%");
  assert.equal(formatRate(1), "100.0%");
  assert.equal(formatRate(null), "—");
  assert.equal(formatRating(4.5), "4.5");
  assert.equal(formatRating(4), "4");
  assert.equal(formatRating(4.17), "4.17");
  assert.equal(formatRating(null), "—");
});

test("a custom range wins only when both ends are real dates", () => {
  assert.deepEqual(periodFromSearch({ start_date: "2026-09-01", end_date: "2026-09-15", month: "3", year: "2026" }),
    { start_date: "2026-09-01", end_date: "2026-09-15" });
  assert.deepEqual(periodFromSearch({ start_date: "2026-09-01", month: "3", year: "2026" }),
    { month: "3", year: "2026" });
  assert.deepEqual(periodFromSearch({ month: "03", year: "2026" }), { month: "3", year: "2026" });
  assert.deepEqual(periodFromSearch({ month: "13", year: "2026" }), { year: "2026" });
  assert.deepEqual(periodFromSearch({ month: "3" }), {});
  assert.deepEqual(periodFromSearch({ year: "20x6" }), {});
});

test("query strings and CSV links are stable and go through the BFF", () => {
  assert.equal(periodQuery({ year: "2026", month: "9" }), "month=9&year=2026");
  assert.equal(csvHref("/api/v1/reports/earnings-statement", { year: "2026", month: "9" }),
    "/api/bff/api/v1/reports/earnings-statement?month=9&year=2026&format=csv");
  assert.equal(csvHref("/api/v1/admin/reports/commissions-payouts", {}, "payout-summary"),
    "/api/bff/api/v1/admin/reports/commissions-payouts?format=csv&section=payout-summary");
});

test("labels", () => {
  assert.equal(cycleLabel("2026-09-01"), "Sep 2026");
  assert.equal(statusLabel("awaiting_remittance"), "Awaiting marketplace payout");
  assert.equal(statusLabel("pending_formula"), "Pending distribution formula");
  assert.equal(statusLabel("something_new"), "something new");
  assert.deepEqual(yearOptions(2028), [2028, 2027, 2026]);
  assert.deepEqual(yearOptions(2025), [2026]);
  assert.deepEqual(yearOptions(2026, 2026, 1997), [2026, 1997]);
  assert.deepEqual(yearOptions(2027, 2026, 2026), [2027, 2026]);
});

import assert from "node:assert/strict";
import test from "node:test";

import { completedSpan, counted, peso, pesoWhole } from "../../components/dashboard/contributor-model.ts";

test("breakdown amounts always show cents; reversals carry a minus", () => {
  assert.equal(peso("65969.00"), "₱65,969.00");
  assert.equal(peso("1962.7"), "₱1,962.70");
  assert.equal(peso("0.00", true), "−₱0.00");
  assert.equal(peso("12.50", true), "−₱12.50");
  assert.equal(peso(null), "₱0.00");
});

test("a row's sales are whole pesos", () => {
  assert.equal(pesoWhole("3873.00"), "₱3,873");
  assert.equal(pesoWhole("1665.6"), "₱1,666");
});

test("counts agree with their noun", () => {
  assert.equal(counted(1, "order"), "1 order");
  assert.equal(counted(91, "order"), "91 orders");
  assert.equal(counted(1234, "item"), "1,234 items");
});

test("the subtitle names the span of completed orders in Manila time", () => {
  // 17:00 Manila on Apr 5 is 09:00 UTC; 12:54 Manila on Oct 2 is 04:54 UTC.
  assert.equal(completedSpan("2026-04-05T09:00:05Z", "2026-10-02T04:54:36Z"), "Apr 5 – Oct 2, 2026 · completed orders");
  assert.equal(completedSpan("2025-12-30T02:00:00Z", "2026-01-03T02:00:00Z"), "Dec 30, 2025 – Jan 3, 2026 · completed orders");
  assert.equal(completedSpan("2026-10-02T01:00:00Z", "2026-10-02T04:00:00Z"), "Oct 2, 2026 · completed orders");
  // 23:30 UTC on Oct 1 is already Oct 2 in Manila.
  assert.equal(completedSpan("2026-10-01T23:30:00Z", "2026-10-01T23:30:00Z"), "Oct 2, 2026 · completed orders");
  assert.equal(completedSpan(null, null), null);
});

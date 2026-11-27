import assert from "node:assert/strict";
import test from "node:test";

import {
  comparisonLine,
  dateTicks,
  dayMonth,
  inRange,
  priceStats,
  priceTicks,
} from "../../components/product/price-history-model.ts";

const NOW = Date.parse("2026-10-05T10:00:00Z");
const SERIES = {
  shopee: [
    { observed_at: "2026-07-07", price: "1399.00" },
    { observed_at: "2026-09-11", price: "1099.00" },
    { observed_at: "2026-10-04", price: "1249.00" },
  ],
  lazada: [
    { observed_at: "2026-07-07", price: "1449.00" },
    { observed_at: "2026-10-04", price: "1299.00" },
  ],
  amazon: [{ observed_at: "2025-01-01", price: "999.00" }],
};

test("ranges keep only the points observed inside them", () => {
  assert.deepEqual(Object.keys(inRange(SERIES, "30D", NOW)), ["shopee", "lazada"]);
  assert.equal(inRange(SERIES, "30D", NOW).shopee.length, 2); // 11 Sep and 4 Oct
  // 90 days ending 5 Oct start on 8 Jul, so 7 Jul is out.
  assert.equal(inRange(SERIES, "90D", NOW).shopee.length, 2);
  assert.equal(inRange(SERIES, "1Y", NOW).shopee.length, 3);
  assert.deepEqual(Object.keys(inRange(SERIES, "1Y", NOW)), ["shopee", "lazada"]);
  assert.deepEqual(Object.keys(inRange(SERIES, "All", NOW)), ["shopee", "lazada", "amazon"]);
  assert.deepEqual(inRange({}, "All", NOW), {});
});

test("stats are real points or their median, never invented", () => {
  const s = priceStats(inRange(SERIES, "1Y", NOW));
  assert.equal(s.count, 5);
  assert.deepEqual(s.lowest, { price: 1099, platform: "shopee", date: "2026-09-11" });
  assert.deepEqual(s.highest, { price: 1449, platform: "lazada", date: "2026-07-07" });
  assert.deepEqual(s.latest, { price: 1249, platform: "shopee", date: "2026-10-04" }); // cheaper of the two on 4 Oct
  assert.equal(s.usual, 1299);
  assert.deepEqual(priceStats({}), { count: 0, latest: null, lowest: null, highest: null, usual: null });
});

test("the comparison says what the latest report is against the usual price", () => {
  const label = (p) => ({ shopee: "Shopee", lazada: "Lazada" })[p] ?? p;
  const money = (n) => `₱${n}`;
  const s = priceStats(inRange(SERIES, "1Y", NOW));
  assert.equal(comparisonLine(s, label, money), "The latest Shopee report is ₱50 under the usual price.");
  assert.equal(comparisonLine(priceStats({ shopee: [{ observed_at: "2026-10-01", price: "100" }] }), label, money), null);
});

test("axis ticks are round and span the data", () => {
  assert.deepEqual(priceTicks(1099, 1449), [1000, 1250, 1500]);
  const flat = priceTicks(500, 500);
  assert.equal(flat.length, 3);
  assert.ok(flat[0] < 500 && flat[2] > 500);
  assert.deepEqual(dateTicks("2026-07-07", "2026-10-05"), ["2026-07-07", "2026-08-06", "2026-09-05", "2026-10-05"]);
  assert.deepEqual(dateTicks("2026-10-05", "2026-10-05"), ["2026-10-05"]);
  assert.equal(dayMonth("2026-09-11"), "11 Sep");
});

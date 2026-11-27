import assert from "node:assert/strict";
import test from "node:test";

import { layoutChart } from "../../components/product/price-chart-model.ts";

const series = {
  shopee: [
    { observed_at: "2026-09-01", price: "1000.00" },
    { observed_at: "2026-09-21", price: "800.00" },
  ],
  lazada: [{ observed_at: "2026-09-11", price: "1200.00" }],
};

test("one line per marketplace, never blended (Business Rules §16)", () => {
  const chart = layoutChart(series, ["shopee", "lazada"], 100, 50, 0);
  assert.deepEqual(chart.lines.map((l) => l.platform), ["shopee", "lazada"]);
  assert.equal(chart.minPrice, 800);
  assert.equal(chart.maxPrice, 1200);
  assert.equal(chart.firstDate, "2026-09-01");
  assert.equal(chart.lastDate, "2026-09-21");
  // Oldest point at the left edge, newest at the right; the cheapest lowest.
  const shopee = chart.lines[0].dots;
  assert.equal(shopee[0].x, 0);
  assert.equal(shopee[1].x, 100);
  assert.equal(shopee[1].y, 50);
  // Lazada's single point is mid-timeline and at the top (the dearest).
  assert.deepEqual(chart.lines[1].dots[0], { x: 50, y: 0, price: 1200, date: "2026-09-11" });
});

test("hiding a marketplace re-fits the axes to what is left", () => {
  const chart = layoutChart(series, ["shopee"], 100, 50, 0);
  assert.equal(chart.lines.length, 1);
  assert.equal(chart.maxPrice, 1000);
  assert.equal(chart.lines[0].dots[0].y, 0);
});

test("a single point or flat prices sit in the middle; nothing shown is empty", () => {
  const one = layoutChart({ shopee: [{ observed_at: "2026-09-01", price: "5" }] }, ["shopee"], 100, 50);
  assert.deepEqual([one.lines[0].dots[0].x, one.lines[0].dots[0].y], [50, 25]);
  assert.equal(layoutChart(series, [], 100, 50).lines.length, 0);
});

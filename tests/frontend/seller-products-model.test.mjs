import assert from "node:assert/strict";
import test from "node:test";

import { applyProducts, changeLabel, inTab, verdictBar, verdictTrend } from "../../components/seller/console/products-model.ts";

const f = (over = {}) => ({ reviews: 10, median: 4.2, change_30d: 0.2, worth_it: 0.6, complicated: 0.3, not_worth: 0.1, questions: 2, open_questions: 1, ...over });
const rows = [
  { id: "a", product_id: "pa", name: "Fan Life10", category: "home-living", status: "approved", requested_at: "2026-09-01T00:00:00Z", figures: f({ reviews: 86, median: 4.0 }) },
  { id: "b", product_id: "pb", name: "Neck Fan Pro1", category: "home-living", status: "approved", requested_at: "2026-09-02T00:00:00Z", figures: f({ reviews: 38, median: 3.6, change_30d: -0.3, open_questions: 0 }) },
  { id: "c", product_id: "pc", name: "Mini Fan", category: "audio", status: "approved", requested_at: "2026-09-03T00:00:00Z", figures: f({ reviews: 3, median: null, change_30d: null, worth_it: null }) },
  { id: "d", product_id: "pd", name: "Neck Fan Pro2", category: "home-living", status: "pending", requested_at: "2026-10-01T00:00:00Z", figures: f({ reviews: 17 }) },
];

test("tabs: linked, waiting, all (live links only)", () => {
  assert.deepEqual(rows.filter((r) => inTab(r, "linked")).map((r) => r.id), ["a", "b", "c"]);
  assert.deepEqual(rows.filter((r) => inTab(r, "waiting")).map((r) => r.id), ["d"]);
  assert.equal(rows.filter((r) => inTab(r, "all")).length, 4);
  assert.equal(inTab({ ...rows[0], status: "rejected" }, "all"), false);
});

test("sort, filter and search", () => {
  assert.deepEqual(applyProducts(rows, "linked", {}).map((r) => r.id), ["a", "b", "c"]);
  assert.deepEqual(applyProducts(rows, "linked", { sort: "rating" }).map((r) => r.id), ["b", "a", "c"]);
  assert.deepEqual(applyProducts(rows, "linked", { sort: "change" }).map((r) => r.id), ["b", "a", "c"]);
  assert.deepEqual(applyProducts(rows, "linked", { rating: "low" }).map((r) => r.id), ["b"]);
  assert.deepEqual(applyProducts(rows, "linked", { rating: "few" }).map((r) => r.id), ["c"]);
  assert.deepEqual(applyProducts(rows, "linked", { open: "1", category: "home-living" }).map((r) => r.id), ["a"]);
  assert.deepEqual(applyProducts(rows, "all", { q: "neck" }).map((r) => r.id), ["b", "d"]);
});

test("labels: change, verdict bar and trend", () => {
  assert.deepEqual(changeLabel(f({ change_30d: 0.2 })), { text: "+0.2 rating", tone: "up" });
  assert.deepEqual(changeLabel(f({ change_30d: -0.34 })), { text: "−0.3 rating", tone: "down" });
  assert.deepEqual(changeLabel(f({ change_30d: 0.01 })), { text: "No change", tone: "flat" });
  assert.deepEqual(changeLabel(f({ median: null })), { text: "Needs 5+", tone: "muted" });
  assert.deepEqual(verdictBar(f()).map((n) => Math.round(n)), [60, 30, 10]);
  assert.equal(verdictBar(f({ worth_it: null })), null);
  assert.equal(verdictTrend(0.62, 0.55, "Jul"), "up from 55% in Jul");
  assert.equal(verdictTrend(0.14, 0.2, "Jul"), "down from 20% in Jul");
  assert.equal(verdictTrend(0.24, 0.24, "Jul"), "steady");
});

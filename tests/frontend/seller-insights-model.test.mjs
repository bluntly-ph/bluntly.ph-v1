import assert from "node:assert/strict";
import test from "node:test";

import {
  exportHref,
  exportSummary,
  hoursLabel,
  replyBars,
  replyTrend,
  reviewsNote,
  scoreSince,
  shareSince,
  sparkPoints,
  tileChange,
} from "../../components/seller/console/insights-model.ts";
import { changeReady, changesPayload, changesReady, changesTitle, linkLabel, registrationLabel } from "../../components/seller/console/profile-model.ts";

const m = (month, over = {}) => ({ month, reviews: 4, rating: null, recommend: null, responded: null, matched: null, complete: null, service: null, packaging: null, ...over });
const months = [
  m("2026-04", { rating: 4.2, recommend: 0.79, responded: 0.41, matched: 0.89, service: 3, packaging: 4 }),
  m("2026-05", { reviews: 0 }),
  m("2026-06", { rating: 4.3, recommend: 0.8, responded: 0.52, matched: 0.9, service: 4, packaging: 3 }),
  m("2026-09", { rating: 4.3, recommend: 0.86, responded: 0.64, matched: 0.92, service: 4, packaging: 3 }),
];

test("since-notes compare the period's figure with the first month that has reviews", () => {
  assert.equal(scoreSince(months, "rating", 4.3), "+0.1 since April");
  assert.equal(scoreSince(months, "rating", 4.2), "No change since April");
  assert.equal(shareSince(months, "recommend", 0.86), "Up from 79% in April");
  assert.equal(shareSince(months, "responded", 0.64), "Up from 41% in April");
  assert.equal(shareSince([m("2026-04", { recommend: 0.8 }), m("2026-05", { recommend: 0.6 })], "recommend", 0.7), "Down from 80% in April");
  // One month (or none) with a figure, or no period figure: nothing to compare.
  assert.equal(scoreSince([m("2026-09", { rating: 4 })], "rating", 4), "");
  assert.equal(shareSince([], "recommend", 0.5), "");
  assert.equal(shareSince(months, "recommend", null), "");
});

test("tile changes: points for shares, score steps for ratings", () => {
  assert.deepEqual(tileChange(months, "matched", "share", 0.92), { text: "+3 pts", tone: "up" });
  assert.deepEqual(tileChange(months, "service", "score", 4), { text: "+1 since Apr", tone: "up" });
  assert.deepEqual(tileChange(months, "packaging", "score", 3), { text: "−1 since Apr", tone: "down" });
  assert.deepEqual(tileChange([m("2026-04", { complete: 0.95 }), m("2026-05", { complete: 0.951 })], "complete", "share", 0.951), { text: "No change", tone: "flat" });
  assert.equal(tileChange(months, "complete", "share", 0.9), null);
});

test("reviews compared with the period before", () => {
  assert.equal(reviewsNote(128, 88, "6m"), "+45% vs the 6 months before");
  assert.equal(reviewsNote(40, 50, "3m"), "−20% vs the 3 months before");
  assert.equal(reviewsNote(5, 0, "6m"), "None in the 6 months before");
  assert.equal(reviewsNote(5, 5, "12m"), "Same as the 12 months before");
  assert.equal(reviewsNote(5, 0, "all"), "Since your first review");
});

test("sparklines skip months without a figure", () => {
  const pts = sparkPoints(months, "matched", 300, 40, "share");
  assert.equal(pts.length, 3);
  assert.equal(pts[0].x, 0);
  assert.equal(pts[2].x, 300);
  assert.ok(pts[2].y < pts[0].y, "a higher share is drawn higher");
});

test("reply time and its trend (faster is better)", () => {
  assert.equal(hoursLabel(0.5), "30 min");
  assert.equal(hoursLabel(9.2), "9 h");
  assert.equal(hoursLabel(72), "3 d");
  assert.equal(hoursLabel(null), "—");
  assert.deepEqual(replyTrend(9, 31, "2026-04"), { text: "down from 31 h in April", tone: "up" });
  assert.deepEqual(replyTrend(31, 9, "2026-04"), { text: "up from 9 h in April", tone: "down" });
  assert.equal(replyTrend(9, null, "2026-04"), null);
  const bars = replyBars(months);
  assert.equal(bars.length, 4);
  assert.equal(bars[1].share, null);
  assert.equal(bars[3].current, true);
  assert.equal(replyBars(Array.from({ length: 20 }, (_, i) => m(`2025-${String((i % 12) + 1).padStart(2, "0")}`))).length, 12);
});

test("export: summary and the download URL", () => {
  const sizes = { reviews: 128, products: 6, questions: 36, appeals: 6 };
  assert.equal(exportSummary(["reviews", "products"], sizes), "2 files · about 54 KB");
  assert.equal(exportSummary(["appeals"], null), "1 file");
  assert.equal(exportSummary([], sizes), "0 files");
  assert.equal(
    exportHref("s1", ["appeals", "reviews"], "all"),
    "/api/bff/api/v1/sellers/s1/export?include=reviews,appeals&period=all",
  );
});

test("store profile: change requests and labels", () => {
  assert.equal(changeReady("name", " "), false);
  assert.equal(changeReady("name", "Jisulife PH"), true);
  assert.equal(changeReady("registration", "12"), false);
  assert.equal(changeReady("give_up", ""), true);
  // MQA-017: several changes in one request, each with its own field.
  const drafts = [
    { kind: "name", value: " Jisulife PH " },
    { kind: "link", value: "https://shopee.ph/x" },
    { kind: "registration", value: "3318207", regKind: "dti" },
  ];
  assert.deepEqual(changesPayload(drafts), [
    { field: "display_name", value: "Jisulife PH" },
    { field: "store_url", value: "https://shopee.ph/x" },
    { field: "registration", value: "3318207", kind: "dti" },
  ]);
  assert.equal(changesReady(drafts), true);
  assert.equal(changesReady([]), false);
  assert.equal(changesReady([{ kind: "link", value: " " }]), false);
  assert.equal(changesTitle(drafts.slice(0, 1)), "Store name change");
  assert.equal(changesTitle(drafts.slice(0, 2)), "Store name and store link change");
  assert.equal(changesTitle(drafts), "Store name, store link and registration details change");
  assert.equal(linkLabel("https://www.shopee.ph/jisulife.official/"), "shopee.ph/jisulife.official");
  assert.equal(linkLabel("not a url"), "not a url");
  assert.equal(linkLabel(null), null);
  assert.equal(registrationLabel("dti", "4821"), "DTI · ending 4821");
  assert.equal(registrationLabel(null, null), null);
});

import assert from "node:assert/strict";
import test from "node:test";

import { REVIEW_COLUMNS, applyFilters, facets, inTab, orderState, sortReviews } from "../../components/seller/console/reviews-model.ts";

const r = (id, rating, days, extra = {}) => ({
  id, title: `T${id}`, comment: "c", overall_rating: rating, accuracy: true, order_completeness: true,
  would_recommend: rating >= 3, created_at: new Date(Date.UTC(2026, 9, 1) - days * 86_400_000).toISOString(),
  reviewer: { display_name: `Buyer ${id}` }, ...extra,
});
const rows = [r("a", 2, 2), r("b", 5, 5, { seller_response: "Thanks!" }), r("c", 1, 1, { accuracy: false }), r("d", 4.5, 9, { order_completeness: false })];

test("tabs split by the store's response", () => {
  assert.deepEqual(rows.filter((x) => inTab(x, "needs")).map((x) => x.id), ["a", "c", "d"]);
  assert.deepEqual(rows.filter((x) => inTab(x, "responded")).map((x) => x.id), ["b"]);
});

test("the Order column reads the buyer's listing and parcel answers", () => {
  assert.equal(orderState(rows[0]), "as_listed");
  assert.equal(orderState(rows[2]), "not_as_listed");
  assert.equal(orderState(rows[3]), "missing");
});

test("sorts: oldest first by default, newest, lowest rating", () => {
  assert.deepEqual(sortReviews(rows, "oldest").map((x) => x.id), ["d", "b", "a", "c"]);
  assert.deepEqual(sortReviews(rows, "newest").map((x) => x.id), ["c", "a", "b", "d"]);
  assert.deepEqual(sortReviews(rows, "lowest").map((x) => x.id), ["c", "a", "d", "b"]);
});

test("filters combine; a half star bins down; search reads title, text and buyer", () => {
  const none = { stars: [], order: [], recommend: [], q: "" };
  assert.deepEqual(applyFilters(rows, { ...none, stars: [4] }).map((x) => x.id), ["d"]);
  assert.deepEqual(applyFilters(rows, { ...none, stars: [1, 2], recommend: ["no"] }).map((x) => x.id), ["a", "c"]);
  assert.deepEqual(applyFilters(rows, { ...none, order: ["missing"] }).map((x) => x.id), ["d"]);
  assert.deepEqual(applyFilters(rows, { ...none, q: "buyer c" }).map((x) => x.id), ["c"]);
  assert.deepEqual(facets(rows).stars, { 1: 1, 2: 1, 3: 0, 4: 1, 5: 1 });
});

import { appealSummary, inAppealTab } from "../../components/seller/console/appeals-model.ts";

test("appeals: tabs and the cards' figures", () => {
  const day = 86_400_000;
  const t0 = Date.UTC(2026, 8, 1);
  const a = (id, status, decidedDays) => ({
    id, status, reason: "r", seller_review_id: "x", created_at: new Date(t0).toISOString(),
    decided_at: decidedDays == null ? null : new Date(t0 + decidedDays * day).toISOString(),
  });
  const rows = [a("1", "open"), a("2", "substantiation_requested"), a("3", "upheld", 4), a("4", "dismissed", 6), a("5", "dismissed", 10)];
  assert.deepEqual(rows.filter((x) => inAppealTab(x, "progress")).map((x) => x.id), ["1", "2"]);
  assert.deepEqual(rows.filter((x) => inAppealTab(x, "decided")).map((x) => x.id), ["3", "4", "5"]);
  assert.deepEqual(appealSummary(rows), { open: 2, waitingOnReviewer: 1, upheld: 1, decided: 3, medianDays: 6 });
});

import { inQuestionTab, questionSummary } from "../../components/seller/console/questions-model.ts";

test("questions: tabs by the store's answer; rate and median hours to answer", () => {
  const h = 3_600_000;
  const t0 = Date.UTC(2026, 8, 1);
  const q = (id, answeredAfterH) => ({
    id, body: id, answer_count: 0, asker: null, created_at: new Date(t0).toISOString(),
    store_answer: answeredAfterH == null ? null : { id: `a${id}`, body: "x", created_at: new Date(t0 + answeredAfterH * h).toISOString() },
  });
  const rows = [q("1", null), q("2", 4), q("3", 10), q("4", 30)];
  assert.deepEqual(rows.filter((x) => inQuestionTab(x, "unanswered")).map((x) => x.id), ["1"]);
  assert.deepEqual(rows.filter((x) => inQuestionTab(x, "answered")).map((x) => x.id), ["2", "3", "4"]);
  const s = questionSummary(rows);
  assert.equal(s.unanswered, 1);
  assert.equal(s.rate, 0.75);
  assert.equal(s.medianHours, 10);
});

test("columns per tab follow the frames (8196:20870, 8201:21535, 8201:22036)", () => {
  assert.deepEqual(REVIEW_COLUMNS.needs, ["Buyer", "Rating", "Review", "Order", "Posted", "Action"]);
  assert.deepEqual(REVIEW_COLUMNS.responded, ["Buyer", "Rating", "Review", "Your response", "Responded", "Action"]);
  assert.deepEqual(REVIEW_COLUMNS.all, ["Buyer", "Rating", "Review", "Your response", "Posted", "Action"]);
});

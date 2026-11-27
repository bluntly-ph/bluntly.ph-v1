import assert from "node:assert/strict";
import test from "node:test";

import { filterActions, oldestAwaiting, oldestUnanswered, quickActions } from "../../components/seller/console/quick-actions-model.ts";

test("each waiting count opens its own screen", () => {
  const items = quickActions("s1", { reviews: 2, questions: 1, appeals: 0 });
  const by = Object.fromEntries(items.map((i) => [i.key, i]));
  assert.equal(by.reviews.href, "/seller/s1/reviews");
  assert.equal(by.questions.href, "/seller/s1/questions");
  assert.equal(by.appeals.href, "/seller/s1/appeals");
  assert.equal(by.reviews.count, 2);
  assert.equal(by["respond-oldest"].href, "/seller/s1/reviews?respond=oldest");
  assert.equal(by.export.opens, "export");
  assert.equal(by["answer-oldest"].href, "/seller/s1/questions?answer=oldest");
  assert.equal(by.link.href, "/seller/s1/products?link=1");
  // The frame's actions, in its order.
  assert.deepEqual(items.filter((i) => i.group === "Actions").map((i) => i.label), [
    "Respond to the oldest review",
    "Answer the oldest question",
    "Link a product",
    "Download CSV",
  ]);
});

test("nothing waiting: no 'oldest' actions", () => {
  const items = quickActions("s1", { reviews: 0, questions: 0, appeals: 0 });
  assert.equal(items.some((i) => i.key === "respond-oldest" || i.key === "answer-oldest"), false);
});

test("search matches the label or its extra words, every word", () => {
  const items = quickActions("s1", { reviews: 1, questions: 0, appeals: 0 });
  assert.deepEqual(filterActions(items, "csv").map((i) => i.key), ["export"]);
  assert.deepEqual(filterActions(items, "CATALOGUE").map((i) => i.key), ["link"]);
  assert.deepEqual(filterActions(items, "oldest review").map((i) => i.key), ["respond-oldest"]);
  assert.equal(filterActions(items, "  ").length, items.length);
  assert.equal(filterActions(items, "zzz").length, 0);
});

test("the oldest review without a response", () => {
  const rows = [
    { id: "a", created_at: "2026-10-01T00:00:00Z", seller_response: null },
    { id: "b", created_at: "2026-09-01T00:00:00Z", seller_response: "thanks" },
    { id: "c", created_at: "2026-09-15T00:00:00Z", seller_response: null },
    { id: "d", created_at: "2026-09-10T00:00:00Z", seller_response: null },
  ];
  assert.equal(oldestAwaiting(rows)?.id, "d");
  assert.equal(oldestAwaiting([{ id: "x", created_at: "2026-01-01T00:00:00Z", seller_response: "ok" }]), null);
  const qs = [
    { id: "q1", created_at: "2026-09-01T00:00:00Z", store_answer: { id: "a" } },
    { id: "q2", created_at: "2026-09-05T00:00:00Z", store_answer: null },
    { id: "q3", created_at: "2026-09-03T00:00:00Z" },
  ];
  assert.equal(oldestUnanswered(qs)?.id, "q3");
});

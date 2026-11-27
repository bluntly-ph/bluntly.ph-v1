import assert from "node:assert/strict";
import test from "node:test";

import { isNewReport, parseQueueFilters, reportsApiQuery } from "../../components/admin/review-queue-model.ts";

/** MQA-001: a just-filed report is easy to find - an order and a marker. */

test("Newest first is an order the URL carries to the API", () => {
  const f = parseQueueFilters(new URLSearchParams("tab=report&rsort=newest"));
  assert.equal(f.rsort, "newest");
  assert.match(reportsApiQuery(f), /sort=newest/);
  assert.equal(parseQueueFilters(new URLSearchParams("rsort=latest")).rsort, "escalation");
});

test("a report reads New for its first day only", () => {
  const now = Date.parse("2026-10-05T12:00:00Z");
  assert.equal(isNewReport("2026-10-05T11:00:00Z", now), true);
  assert.equal(isNewReport("2026-10-04T12:00:01Z", now), true);
  assert.equal(isNewReport("2026-10-04T11:59:59Z", now), false);
  assert.equal(isNewReport("2026-10-06T12:00:00Z", now), false);
});

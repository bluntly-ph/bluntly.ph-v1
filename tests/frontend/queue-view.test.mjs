import assert from "node:assert/strict";
import test from "node:test";

import { parseQueueFilters, queueApiQuery, queueHref } from "../../components/admin/review-queue-model.ts";

/**
 * MQA-015: a review a moderator took down is decided, so it leaves the list of
 * work - but stays one switch away (?view=taken_down) with its Restore.
 */

test("the work is the default view; taken_down is asked for by name", () => {
  assert.equal(parseQueueFilters(new URLSearchParams("")).view, "waiting");
  assert.equal(parseQueueFilters(new URLSearchParams("view=taken_down")).view, "taken_down");
  assert.equal(parseQueueFilters(new URLSearchParams("view=decided")).view, "waiting");
  assert.equal(new URLSearchParams(queueApiQuery(parseQueueFilters(new URLSearchParams("")))).get("view"), null);
  assert.equal(new URLSearchParams(queueApiQuery(parseQueueFilters(new URLSearchParams("view=taken_down")))).get("view"), "taken_down");
});

test("the view survives other choices and paging, and switching it starts at page 1", () => {
  const f = parseQueueFilters(new URLSearchParams("view=taken_down&tier=high&offset=50"));
  assert.match(queueHref(f, { sort: "oldest" }), /view=taken_down/);
  assert.match(queueHref(f, { offset: 100 }), /offset=100/);
  const back = queueHref(f, { view: "waiting" });
  assert.doesNotMatch(back, /view=|offset=/);
  assert.match(back, /tier=high/);
});

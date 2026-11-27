import assert from "node:assert/strict";
import test from "node:test";

import {
  parseQueueFilters,
  queueHref,
  REPORT_PAGE_SIZE,
  reportsApiQuery,
  reportTotalsLine,
} from "../../components/admin/review-queue-model.ts";

/**
 * MQA-045: the Overview said "Open reports 4" while the Reports tab said 6.
 * One counted reported items, the other report rows from a 50-row page. Both
 * now show the API's total of reports, and the items figure under its name.
 */

test("both figures are named, so 6 and 4 can never be read as the same thing", () => {
  assert.equal(reportTotalsLine({ reports: 6, items: 4 }), "6 open reports on 4 items");
  assert.equal(reportTotalsLine({ reports: 1, items: 1 }), "1 open report on 1 item");
  assert.equal(reportTotalsLine({ reports: 3, items: 1 }, "escalated"), "3 escalated reports on 1 item");
  assert.equal(reportTotalsLine({ reports: 1284, items: 900 }, "all"), "1,284 reports on 900 items");
});

test("an outage is not zero", () => {
  assert.equal(reportTotalsLine(null), null);
  assert.equal(reportTotalsLine({ reports: null, items: null }), null);
  assert.equal(reportTotalsLine({ reports: 0, items: 0 }), "0 open reports");
});

test("the Report tab pages through every report, keeping status, tier and order", () => {
  const first = parseQueueFilters(new URLSearchParams("tab=report&rstatus=resolved&tier=high&rsort=oldest"));
  assert.equal(first.rpage, 1);
  assert.equal(new URLSearchParams(reportsApiQuery(first)).get("offset"), null);

  const third = parseQueueFilters(new URLSearchParams("tab=report&rstatus=resolved&tier=high&rsort=oldest&rpage=3"));
  const q = new URLSearchParams(reportsApiQuery(third));
  assert.equal(q.get("offset"), String(2 * REPORT_PAGE_SIZE));
  assert.equal(q.get("limit"), String(REPORT_PAGE_SIZE));
  assert.equal(q.get("status"), "resolved");
  assert.equal(q.get("tier"), "high");
  assert.equal(q.get("sort"), "oldest");
});

test("a bad page is page 1, and changing a filter starts again from page 1", () => {
  for (const raw of ["0", "-2", "abc", ""]) {
    assert.equal(parseQueueFilters(new URLSearchParams(`rpage=${raw}`)).rpage, 1);
  }
  const deep = parseQueueFilters(new URLSearchParams("tab=report&rpage=4"));
  assert.doesNotMatch(queueHref(deep, { tab: "report", rstatus: "escalated" }), /rpage=/);
});

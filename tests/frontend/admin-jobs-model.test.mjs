import assert from "node:assert/strict";
import test from "node:test";

import { agoText, jobLine, needsRun, nextIn, sortJobs } from "../../components/admin/activity/jobs-model.ts";

// 2026-10-04 12:00 Manila.
const now = Date.parse("2026-10-04T04:00:00Z");
const t = (over) => ({ task: "x", cadence: "daily", state: "healthy", due_at: "2026-10-03T21:00:00Z", next_at: "2026-10-05T00:00:00Z", last_success_at: "2026-10-03T21:05:00Z", last_run: null, ...over });

test("a failed job says when it failed and when it last worked", () => {
  const line = jobLine(t({ state: "failed", last_run: { status: "failed", failure: "OperationalError", started_at: "2026-10-03T21:00:00Z" }, last_success_at: "2026-10-03T04:00:00Z" }), now);
  assert.deepEqual(line, { text: "Failed at 5:00 AM · last success 1 day ago", tone: "danger" });
  assert.equal(jobLine(t({ state: "overdue" }), now).tone, "danger");
});

test("healthy jobs say when they next run", () => {
  assert.equal(jobLine(t({}), now).text, "Next in 20h");
  assert.equal(jobLine(t({ cadence: "monthly", next_at: "2026-10-04T18:30:00Z" }), now).text, "5 Oct, 2:30 AM");
  assert.equal(jobLine(t({ cadence: "hourly", last_run: { status: "ok", failure: null, started_at: "2026-10-04T03:48:00Z" } }), now).text, "Every hour · last run 12 min ago");
  assert.equal(jobLine(t({ state: "never_run" }), now).text, "Never run · due since 5:00 AM");
  assert.equal(jobLine(t({ state: "never_run", cadence: "monthly", due_at: "2026-09-30T18:00:00Z" }), now).text, "Never run · due since 1 Oct, 2:00 AM");
  assert.equal(jobLine(t({ state: "never_run", due_at: "2026-10-04T21:00:00Z", next_at: null }), now).text, "Never run");
});

test("helpers", () => {
  assert.equal(nextIn("2026-10-04T04:45:00Z", now), "Next in 45 min");
  assert.equal(agoText(null, now), "never");
  assert.equal(agoText("2026-10-04T01:00:00Z", now), "3h ago");
  assert.deepEqual(sortJobs([t({ task: "b" }), t({ task: "a", state: "failed" }), t({ task: "c", state: "never_run" })]).map((x) => x.task), ["a", "c", "b"]);
  assert.equal(needsRun(t({})), false);
  assert.equal(needsRun(t({ state: "due" })), true);
});

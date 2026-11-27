import assert from "node:assert/strict";
import test from "node:test";

import { hoursMinutes, oldestWaiting } from "../../components/admin/analytics/analytics-model.ts";

/** Admin Analytics → Moderation (Figma 8071:16115: "5h 20m", "Was 7h 05m", "Oldest waiting 3 days"). */

test("decision time reads in hours and minutes, never a bare 0h", () => {
  assert.equal(hoursMinutes(5 + 20 / 60), "5h 20m");
  assert.equal(hoursMinutes(7 + 5 / 60), "7h 05m");
  assert.equal(hoursMinutes(0.75), "45m");
  assert.equal(hoursMinutes(0.004), "under 1m");
  assert.equal(hoursMinutes(null), "—");
});

test("oldest waiting", () => {
  const now = Date.parse("2026-10-04T10:00:00Z");
  assert.equal(oldestWaiting("2026-10-01T09:00:00Z", now), "Oldest waiting 3 days");
  assert.equal(oldestWaiting("2026-10-04T05:00:00Z", now), "Oldest waiting 5 h");
  assert.equal(oldestWaiting("2026-10-04T09:30:00Z", now), "Oldest waiting under an hour");
  assert.equal(oldestWaiting(null, now), null);
});

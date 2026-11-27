import assert from "node:assert/strict";
import test from "node:test";

import { DESTINATIONS, oldest, routedThisMonth, waiting } from "../../components/admin/routing/routing-model.ts";

/** Special routing (Figma 8178:20045, Overlay/Routing/Track 8178:20344). */

const now = Date.parse("2026-10-04T08:00:00Z");

test("splits follow the rules (owner decision A), each summing to 100", () => {
  assert.deepEqual(DESTINATIONS.map((d) => d.key), ["honesty_fund", "platform"]);
  for (const d of DESTINATIONS) assert.equal(d.split.reduce((a, [, v]) => a + v, 0), 100);
});

test("waiting reads hours, then days, late from a day", () => {
  assert.deepEqual(waiting("2026-09-30T08:00:00Z", now), { label: "4 days", late: true });
  assert.deepEqual(waiting("2026-10-03T12:00:00Z", now), { label: "20 h", late: false });
  assert.deepEqual(waiting("2026-10-04T07:30:00Z", now), { label: "under 1 h", late: false });
  assert.deepEqual(waiting(null, now), { label: "—", late: false });
});

test("oldest uses the escalation time first", () => {
  const items = [
    { title: "A", created_at: "2026-09-01T00:00:00Z", escalated_at: "2026-10-03T00:00:00Z" },
    { title: "B", created_at: "2026-09-20T00:00:00Z", escalated_at: "2026-09-28T00:00:00Z" },
  ];
  assert.equal(oldest(items).title, "B");
  assert.equal(oldest([]), null);
});

test("routed this month counts this Manila month only", () => {
  const h = [
    { at: "2026-10-02T00:00:00Z", actor_name: "Zient P." },
    { at: "2026-10-03T00:00:00Z", actor_name: "Zient P." },
    { at: "2026-09-29T00:00:00Z", actor_name: "Mara L." },
  ];
  assert.deepEqual(routedThisMonth(h, now), { count: 2, by: "By Zient P." });
  assert.deepEqual(routedThisMonth([], now), { count: 0, by: null });
});

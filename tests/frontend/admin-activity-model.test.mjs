import assert from "node:assert/strict";
import test from "node:test";

import { conversationVerb, dayCount } from "../../components/admin/activity/activity-model.ts";

/** Admin Activity log rows (Figma 8074:16245). */

test("Inbox events read as verbs, not raw notes", () => {
  assert.deepEqual(conversationVerb("conversation moved_to_support"), { before: "moved", after: "to Support" });
  assert.deepEqual(conversationVerb("conversation assigned"), { before: "assigned", after: "" });
  assert.deepEqual(conversationVerb("conversation status:resolved"), { before: "marked", after: "as resolved" });
  assert.deepEqual(conversationVerb(null), { before: "updated", after: "" });
});

test("a day's count is never the page size passed off as the day's total", () => {
  assert.equal(dayCount(50, { today: 176 }), "176 actions");
  assert.equal(dayCount(50, { today: null, cut: true }), "50+ actions");
  assert.equal(dayCount(1, {}), "1 action");
  assert.equal(dayCount(12, { today: null, cut: false }), "12 actions");
});

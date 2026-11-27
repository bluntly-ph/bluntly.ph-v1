import assert from "node:assert/strict";
import test from "node:test";

import {
  attentionColumns,
  attentionOpen,
  initials,
  manilaToday,
  nextMonthlyDate,
  shortDate,
} from "../../components/admin/overview/overview-model.ts";
import { activitySentence } from "../../components/admin/activity/activity-words.ts";

test("initials as the v4 avatars draw them", () => {
  assert.equal(initials("Jisulife Official"), "JO");
  assert.equal(initials("maricel.d"), "MD");
  assert.equal(initials("@zienxt"), "ZI");
  assert.equal(initials(""), "?");
  assert.equal(initials(null), "?");
});

test("the next send date on a monthly payout day", () => {
  assert.deepEqual(nextMonthlyDate(10, { y: 2026, m: 9, d: 5 }), { y: 2026, m: 9, d: 10 });
  assert.deepEqual(nextMonthlyDate(10, { y: 2026, m: 9, d: 10 }), { y: 2026, m: 9, d: 10 });
  assert.deepEqual(nextMonthlyDate(10, { y: 2026, m: 9, d: 11 }), { y: 2026, m: 10, d: 10 });
  assert.deepEqual(nextMonthlyDate(10, { y: 2026, m: 11, d: 20 }), { y: 2027, m: 0, d: 10 });
  // A day past the month's end lands on its last day.
  assert.deepEqual(nextMonthlyDate(31, { y: 2026, m: 1, d: 3 }), { y: 2026, m: 1, d: 28 });
  assert.equal(shortDate({ y: 2026, m: 9, d: 10 }), "Sat, 10 Oct");
  assert.equal(shortDate({ y: 2026, m: 9, d: 31 }, false), "31 Oct");
  assert.equal(shortDate({ y: 2026, m: 8, d: 10 }), "Thu, 10 Sep");
  const t = manilaToday(Date.UTC(2026, 9, 5, 18)); // 02:00 on the 6th in Manila
  assert.deepEqual(t, { y: 2026, m: 9, d: 6 });
});

const GROUPS = [
  { key: "moderation", label: "Moderation", items: [{ key: "reviews_past_due", label: "Reviews past due", count: 16 }, { key: "support_requests", label: "Support requests", count: 2 }] },
  { key: "integrity", label: "Integrity", items: [{ key: "under_investigation", label: "Under investigation", count: 2 }] },
  { key: "catalog", label: "Catalog", items: [{ key: "price_submissions", label: "Price submissions", count: 6 }, { key: "seller_claims_appeals", label: "Seller claims & appeals", count: 1 }] },
  { key: "money", label: "Money", items: [{ key: "failed_payouts", label: "Failed payouts", count: null }] },
];

test("Needs attention in v4's columns, every API row kept", () => {
  const [left, right] = attentionColumns(GROUPS);
  assert.deepEqual(left.map((g) => g.key), ["moderation", "integrity", "money"]);
  assert.deepEqual(right.map((g) => g.key), ["catalog", "sellers"]);
  assert.deepEqual(right[0].items.map((i) => i.key), ["price_submissions"]);
  assert.equal(right[1].items[0].label, "Claims & appeals");
  assert.equal(right[1].items[0].count, 1);
  const drawn = [...left, ...right];
  assert.equal(attentionOpen(drawn), attentionOpen(GROUPS)); // 27: the total is what is drawn
  assert.equal(attentionOpen(GROUPS), 27);
  // The input is not mutated.
  assert.equal(GROUPS[2].items.length, 2);
});

test("an activity entry reads as one sentence", () => {
  assert.equal(activitySentence({ actor: "Zient", action: "unpublish", target_label: "Generic Neck Fan" }), "Zient took down Generic Neck Fan");
  assert.equal(activitySentence({ actor: null, action: "integrity_sweep" }), "System integrity sweep");
  assert.equal(activitySentence({ actor: "Mika", action: "payout" }), "Mika marked a payout as sent");
});

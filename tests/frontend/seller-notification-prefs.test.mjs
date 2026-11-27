import assert from "node:assert/strict";
import test from "node:test";

import { PREF_ROWS, prefEnabled, withPref } from "../../components/seller/console/notification-prefs-model.ts";

/** Screen/Seller/Settings → Notifications (Figma 8218:24151). */

const all = { store_reviews: true, store_reviews_low_only: false, store_questions: true, appeal_updates: true, product_links: true, email: true, weekly_summary: true };

test("rows follow the frame's order", () => {
  assert.deepEqual(
    PREF_ROWS.map((r) => r.title),
    ["New reviews of your store", "Only low reviews", "New questions", "Appeal updates", "Product link decisions", "Also by email", "Weekly summary"],
  );
});

test("turning new reviews off also clears Only low reviews, and disables it", () => {
  const off = withPref({ ...all, store_reviews_low_only: true }, "store_reviews", false);
  assert.equal(off.store_reviews, false);
  assert.equal(off.store_reviews_low_only, false);
  assert.equal(prefEnabled(off, "store_reviews_low_only"), false);
  assert.equal(prefEnabled(all, "store_reviews_low_only"), true);
});

test("the email channels are usable on their own (backend 0085)", () => {
  assert.equal(prefEnabled(all, "email"), true);
  assert.equal(prefEnabled(all, "weekly_summary"), true);
  const off = withPref(all, "email", false);
  assert.equal(off.email, false);
  assert.equal(off.weekly_summary, true);
  assert.equal(off.store_reviews, true);
});

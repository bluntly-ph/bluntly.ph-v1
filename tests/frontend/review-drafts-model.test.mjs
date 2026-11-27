import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_DRAFTS,
  draftUrl,
  localDraftsKey,
  mergeDrafts,
} from "../../components/reviews/review-drafts-model.ts";

/**
 * QA-003: drafts saved on desktop were missing on mobile because they lived only
 * in one browser. The account copy and the local copy are merged by these rules.
 */

test("a draft that exists only on the account appears on this device", () => {
  const merged = mergeDrafts({}, [{ slot: "p1", draft: { title: "Tefal pan" }, saved_at: 5 }]);
  assert.deepEqual(merged, [{ slot: "p1", draft: { title: "Tefal pan", savedAt: 5 } }]);
});

test("for the same slot the newer save wins, from either side", () => {
  const local = { p1: { title: "local newer", savedAt: 9 }, p2: { title: "local older", savedAt: 1 } };
  const server = [
    { slot: "p1", draft: { title: "server older" }, saved_at: 3 },
    { slot: "p2", draft: { title: "server newer" }, saved_at: 7 },
  ];
  const bySlot = Object.fromEntries(mergeDrafts(local, server).map((e) => [e.slot, e.draft.title]));
  assert.deepEqual(bySlot, { p1: "local newer", p2: "server newer" });
});

test("two products keep two drafts, newest first (the original Tefal report)", () => {
  const merged = mergeDrafts({ a: { title: "pan", savedAt: 1 } }, [
    { slot: "b", draft: { title: "kettle" }, saved_at: 2 },
  ]);
  assert.deepEqual(merged.map((e) => e.slot), ["b", "a"]);
});

test("the merged list keeps the ten newest", () => {
  const server = Array.from({ length: 12 }, (_, i) => ({ slot: `s${i}`, draft: {}, saved_at: i }));
  const merged = mergeDrafts({}, server);
  assert.equal(merged.length, MAX_DRAFTS);
  assert.equal(merged[0].slot, "s11");
});

test("the local key belongs to one account, so a shared device keeps drafts apart", () => {
  assert.notEqual(localDraftsKey("alice"), localDraftsKey("bob"));
  assert.match(localDraftsKey("alice"), /alice$/);
});

test("slot URLs are encoded", () => {
  assert.equal(draftUrl(), "/api/bff/api/v1/review-drafts");
  assert.equal(draftUrl("__no-product__"), "/api/bff/api/v1/review-drafts/__no-product__");
  assert.equal(draftUrl("a/b"), "/api/bff/api/v1/review-drafts/a%2Fb");
});

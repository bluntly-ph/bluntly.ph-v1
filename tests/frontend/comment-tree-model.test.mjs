import assert from "node:assert/strict";
import test from "node:test";

import {
  removeFromThread,
  replyOpening,
  visibleThread,
} from "../../components/review/comment-tree-model.ts";

/** QA-039: a confirmed delete must not leave the comment on screen. QA-029: every comment can be answered. */

const t = (id, replies = [], is_removed = false) => ({ id, is_removed, replies });

test("deleting a comment without replies removes it from the thread", () => {
  assert.deepEqual(removeFromThread([t("a"), t("b")], "a").map((c) => c.id), ["b"]);
});

test("deleting a reply removes the reply and keeps its thread", () => {
  const out = removeFromThread([t("a", [t("r1"), t("r2")])], "r1");
  assert.deepEqual(out.map((c) => c.id), ["a"]);
  assert.deepEqual(out[0].replies.map((r) => r.id), ["r2"]);
});

test("a deleted top comment with live replies stays as a tombstone for them", () => {
  const out = removeFromThread([t("a", [t("r1")])], "a");
  assert.equal(out.length, 1);
  assert.equal(out[0].is_removed, true);
  assert.deepEqual(out[0].replies.map((r) => r.id), ["r1"]);
});

test("the tombstone goes when its last reply goes", () => {
  const out = removeFromThread([t("a", [t("r1")], true)], "r1");
  assert.deepEqual(out, []);
});

test("a thread as listed never shows removed replies or empty tombstones", () => {
  const out = visibleThread([t("a", [], true), t("b", [t("x", [], true)]), t("c", [t("y")], true)]);
  assert.deepEqual(out.map((c) => [c.id, c.replies.map((r) => r.id)]), [["b", []], ["c", ["y"]]]);
});

test("a reply to a reply opens addressed to that person, as plain text", () => {
  assert.equal(replyOpening("maria.c"), "@maria.c ");
  assert.equal(replyOpening("<img src=x>"), "@imgsrcx ");
  assert.equal(replyOpening(null), "");
});

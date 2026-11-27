import assert from "node:assert/strict";
import test from "node:test";

import { THREAD_MAX_DEPTH, descendantCount, focusThread, replyTree } from "../../components/qa/question-thread-model.ts";

// a ─ b ─ c ─ d ─ e      (a 5-deep chain)
//   └ f
const ROWS = [
  { id: "a", parent_id: null },
  { id: "b", parent_id: "a" },
  { id: "c", parent_id: "b" },
  { id: "d", parent_id: "c" },
  { id: "e", parent_id: "d" },
  { id: "f", parent_id: "a" },
  { id: "g", parent_id: null },
];

test("a thread shows three levels before 'Continue this thread'", () => {
  assert.equal(THREAD_MAX_DEPTH, 3);
});

test("descendants are counted at every depth", () => {
  const [a, g] = replyTree(ROWS);
  assert.equal(descendantCount(a), 5);
  assert.equal(descendantCount(g), 0);
});

test("the thread view focuses one reply with the replies above it", () => {
  const t = focusThread(ROWS, "d");
  assert.equal(t.node.id, "d");
  assert.deepEqual(t.node.children.map((c) => c.id), ["e"]);
  assert.deepEqual(t.ancestors.map((r) => r.id), ["a", "b", "c"]);
  assert.deepEqual(focusThread(ROWS, "a").ancestors, []);
  assert.equal(focusThread(ROWS, "nope"), null);
  // A cycle in bad data cannot loop forever.
  const loop = [{ id: "x", parent_id: "y" }, { id: "y", parent_id: "x" }];
  assert.equal(focusThread(loop, "x"), null);
});

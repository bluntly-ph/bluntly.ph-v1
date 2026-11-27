import assert from "node:assert/strict";
import test from "node:test";

import {
  experienceLines,
  fitTone,
  pointLines,
  replyTree,
  sortAnswers,
  verdictSummary,
} from "../../components/qa/question-thread-model.ts";

test("verdict summary counts only real verdicts", () => {
  const s = verdictSummary([
    { parts: { verdict: "yes" } },
    { parts: { verdict: "yes" } },
    { parts: { verdict: "on_sale" } },
    { parts: null },
    { parts: { verdict: null } },
  ]);
  assert.deepEqual(s.counts, { yes: 2, on_sale: 1, other_variant: 0, no: 0 });
  assert.equal(s.total, 3);
});

test("parts become lines", () => {
  assert.deepEqual(experienceLines("Used it 1–6 months · About as expected"), ["Used it 1–6 months", "About as expected"]);
  assert.deepEqual(experienceLines(null), []);
  assert.deepEqual(pointLines("Worth it!; Easy to use"), ["Worth it!", "Easy to use"]);
  assert.equal(fitTone("Yes, it fits what you need"), "yes");
  assert.equal(fitTone("No, look elsewhere"), "no");
  assert.equal(fitTone("It depends"), "depends");
});

test("replies nest under their parents, in order", () => {
  const tree = replyTree([
    { id: "a", parent_id: null },
    { id: "b", parent_id: "a" },
    { id: "c", parent_id: null },
    { id: "d", parent_id: "b" },
    { id: "e", parent_id: "gone" },
  ]);
  assert.deepEqual(tree.map((n) => n.id), ["a", "c", "e"]);
  assert.equal(tree[0].children[0].children[0].id, "d");
});

test("most helpful puts net votes first, oldest breaking ties", () => {
  const rows = [
    { id: 1, helpful_votes: 1, unhelpful_votes: 0, created_at: "2026-10-01" },
    { id: 2, helpful_votes: 5, unhelpful_votes: 1, created_at: "2026-10-02" },
    { id: 3, helpful_votes: 1, unhelpful_votes: 0, created_at: "2026-09-30" },
  ];
  assert.deepEqual(sortAnswers(rows, "helpful").map((r) => r.id), [2, 3, 1]);
  assert.deepEqual(sortAnswers(rows, "newest").map((r) => r.id), [2, 1, 3]);
});

import assert from "node:assert/strict";
import test from "node:test";

import { countProblem, countState } from "../../components/console/counted-model.ts";

test("within the limit: no error, plain counter", () => {
  const s = countState("hello", 1000);
  assert.equal(s.over, false);
  assert.equal(s.excess, 0);
  assert.equal(s.label, "5 / 1,000");
  assert.equal(countProblem(s), null);
});

test("exactly at the limit is still valid", () => {
  assert.equal(countState("x".repeat(500), 500).over, false);
});

test("past the limit: the over state is reachable and says by how much", () => {
  const s = countState("x".repeat(1020), 1000);
  assert.equal(s.over, true);
  assert.equal(s.excess, 20);
  assert.equal(s.label, "1,020 / 1,000");
  assert.equal(countProblem(s), "20 characters over the limit. Shorten it to send.");
  assert.equal(countProblem(countState("xx", 1)), "1 character over the limit. Shorten it to send.");
});

test("counts code points like the API, so an emoji is one character", () => {
  assert.equal(countState("👍👍", 2).over, false);
  assert.equal(countState("👍👍", 2).count, 2);
});

test("a minimum is flagged only after typing, and ignores surrounding blanks", () => {
  assert.equal(countState("", 1000, 10).short, false);
  assert.equal(countState("   short   ", 1000, 10).short, true);
  assert.equal(countProblem(countState("short", 1000, 10), 10), "At least 10 characters.");
  assert.equal(countState("long enough now", 1000, 10).short, false);
});

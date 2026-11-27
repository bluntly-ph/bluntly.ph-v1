import assert from "node:assert/strict";
import test from "node:test";

import { formatScore, parseScore } from "../../components/admin/people/trust-score-model.ts";

test("formatScore shows the API's decimals without trailing zeros", () => {
  assert.equal(formatScore("80.00"), "80");
  assert.equal(formatScore("72.50"), "72.5");
  assert.equal(formatScore("63.25"), "63.25");
  assert.equal(formatScore(null), "—");
  assert.equal(formatScore(""), "—");
  assert.equal(formatScore("x"), "—");
});

test("parseScore accepts 0-100 with up to two places, like the API's CHECK", () => {
  assert.equal(parseScore("0"), 0);
  assert.equal(parseScore("100"), 100);
  assert.equal(parseScore(" 72.5 "), 72.5);
  assert.equal(parseScore("63.25"), 63.25);
  for (const bad of ["", "-1", "100.01", "101", "72.555", "abc", "7e1", "1,5"]) assert.equal(parseScore(bad), null, bad);
});

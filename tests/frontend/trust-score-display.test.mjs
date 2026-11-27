import assert from "node:assert/strict";
import { test } from "node:test";

import { trustDescription, trustScore } from "../../lib/trust.ts";

/**
 * The public Honesty Score (QA, 2026-09-29, Trust Score computation). The
 * number shown is `reputation_score` (ADR-003, 0 to 100, two decimals in the
 * database) rounded to a whole number: docs/TRUST_SCORE_COMPUTATION.md, §7.
 */

test("the displayed score is the stored score rounded half up", () => {
  assert.equal(trustScore("49.49"), 49);
  assert.equal(trustScore("49.50"), 50);
  assert.equal(trustScore("62.00"), 62);
  assert.equal(trustScore(0), 0);
  assert.equal(trustScore("100.00"), 100);
});

test("no score is shown rather than an invented one", () => {
  assert.equal(trustScore(null), null);
  assert.equal(trustScore(undefined), null);
  assert.equal(trustScore(""), null);
  assert.equal(trustScore("not a number"), null);
});

test("the accessible name says what the number is", () => {
  assert.equal(trustDescription("Verified Buyer", 62), "Verified Buyer, trust score 62 out of 100");
  assert.equal(trustDescription("Newcomer", null), "Newcomer");
});

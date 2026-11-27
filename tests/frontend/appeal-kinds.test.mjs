import assert from "node:assert/strict";
import test from "node:test";

import { APPEAL_KINDS, appealKind, appealKindLabel } from "../../components/seller/console/appeal-kinds.ts";

/** MQA-041 (backend 0090): a store says what is wrong; the admin's check follows from it. */

test("the three kinds the API accepts, never-ordered first", () => {
  assert.deepEqual(APPEAL_KINDS.map((k) => k.kind), ["never_ordered", "untrue", "breaks_rules"]);
});

test("each kind asks its own question and names its own check", () => {
  assert.match(appealKind("never_ordered").check, /prove the purchase/);
  assert.match(appealKind("untrue").check, /evidence/);
  assert.match(appealKind("breaks_rules").check, /Guidelines/);
  assert.equal(new Set(APPEAL_KINDS.map((k) => k.prompt)).size, 3);
});

test("labels for the admin; old flags without a kind read as never ordered", () => {
  assert.equal(appealKindLabel("untrue"), "Untrue details");
  assert.equal(appealKindLabel(null), "Never ordered");
  assert.equal(appealKindLabel("something-else"), "Never ordered");
});

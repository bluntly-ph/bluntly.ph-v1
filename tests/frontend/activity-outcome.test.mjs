import assert from "node:assert/strict";
import test from "node:test";

import { OUTCOME_LABEL, OUTCOME_VERB, outcomeLabel } from "../../components/admin/activity/activity-outcome.ts";

/** MQA-006/008: a row says what happened, not the audit action it was stored as. */
test("a dismissal reads as a dismissal, not an approval", () => {
  assert.equal(outcomeLabel("dismissed"), "Dismissed a report");
  assert.equal(outcomeLabel("escalated"), "Escalated a report");
  assert.equal(outcomeLabel("price_approved"), "Approved a price");
  assert.equal(outcomeLabel(null), null);
  assert.equal(outcomeLabel("unknown"), null);
});

test("every outcome has a label and a verb", () => {
  assert.deepEqual(Object.keys(OUTCOME_LABEL).sort(), Object.keys(OUTCOME_VERB).sort());
});

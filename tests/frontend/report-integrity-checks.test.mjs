import assert from "node:assert/strict";
import test from "node:test";

import { reviewIntegrityChecks } from "../../components/admin/review-queue-model.ts";

/**
 * MQA-003: the Reports view shows a reported review's integrity checks - the
 * ones its Review Queue card runs - flagged first, and a check that could not
 * run (no provider, no photo) never reads as a pass.
 */

const quiet = {
  signals: { velocity: false, collusion: false, duplicate_content: false },
  voting: { upvoters: 0, reciprocal_upvoters: 0, min_upvoters: 5, threshold: 0.6,
            max_upvotes_in_velocity_window: 0, velocity_threshold: 10 },
  integrity: { plagiarism_status: "not_configured", reverse_image_status: "not_configured" },
  edited_since_monetized: false,
  has_photo: true,
  reused_photo: false,
};

test("no facts, no checks: a report on a comment shows none", () => {
  assert.deepEqual(reviewIntegrityChecks(null), []);
  assert.deepEqual(reviewIntegrityChecks(undefined), []);
});

test("every queue check is listed, and the external ones say they did not run", () => {
  const checks = reviewIntegrityChecks(quiet);
  assert.deepEqual(checks.map((c) => c.key), ["spike", "ring", "copy", "photo", "edited", "ris", "plagiarism"]);
  assert.equal(checks.filter((c) => c.state === "flagged").length, 0);
  const ris = checks.find((c) => c.key === "ris");
  assert.equal(ris.state, "not_run");
  assert.match(ris.detail, /No provider/);
  assert.equal(checks.find((c) => c.key === "ring").detail, "No up-votes yet");
});

test("what fired comes first, with the numbers the check used", () => {
  const checks = reviewIntegrityChecks({
    ...quiet,
    signals: { velocity: true, collusion: false, duplicate_content: true },
    voting: { ...quiet.voting, upvoters: 14, max_upvotes_in_velocity_window: 14 },
    reused_photo: true,
  });
  assert.deepEqual(checks.filter((c) => c.state === "flagged").map((c) => c.label),
                   ["Vote spike", "Copied text", "Reused photo"]);
  assert.match(checks[0].detail, /14 up-votes within one hour; the check fires above 10/);
});

test("a review with no photo does not pass the photo check, it skips it", () => {
  const photo = reviewIntegrityChecks({ ...quiet, has_photo: false }).find((c) => c.key === "photo");
  assert.equal(photo.state, "not_run");
});

import assert from "node:assert/strict";
import test from "node:test";

import { passwordCheck } from "../../components/seller/console/account-model.ts";

test("untouched password fields mean no change", () => {
  assert.deepEqual(passwordCheck("", "", ""), { wanted: false, problem: null });
});

test("the frame's rules, in the order a person fixes them", () => {
  assert.equal(passwordCheck("", "longenough1", "longenough1").problem, "Enter your current password.");
  assert.equal(passwordCheck("old", "short", "short").problem, "The new password needs at least 10 characters.");
  assert.equal(passwordCheck("old", "longenough1", "longenough2").problem, "The two new passwords don't match.");
  assert.equal(passwordCheck("longenough1", "longenough1", "longenough1").problem, "Choose a password different from the current one.");
  assert.deepEqual(passwordCheck("old", "longenough1", "longenough1"), { wanted: true, problem: null });
});

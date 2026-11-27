import assert from "node:assert/strict";
import test from "node:test";

import { accountSwitchMessage } from "../../components/site/account-switch-model.ts";

/**
 * QA-061: tabs of one browser share one sign-in. When another tab signs in as
 * someone else, this tab is told who it now acts as; nothing else speaks up.
 */

test("another account signing in is announced by name", () => {
  const message = accountSwitchMessage("alice", "bob");
  assert.match(message, /@bob/);
  assert.match(message, /reload/i);
});

test("the same account signing in again says nothing", () => {
  assert.equal(accountSwitchMessage("alice", "alice"), null);
  assert.equal(accountSwitchMessage(" alice ", "alice"), null);
});

test("a cleared or empty value is never read as a sign-out", () => {
  assert.equal(accountSwitchMessage("alice", null), null);
  assert.equal(accountSwitchMessage("alice", ""), null);
});

test("a signed-out tab hears that the browser is now signed in", () => {
  assert.match(accountSwitchMessage(null, "bob"), /@bob/);
});

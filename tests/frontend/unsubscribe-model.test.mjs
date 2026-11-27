import assert from "node:assert/strict";
import test from "node:test";

import { SCOPE_COPY, scopeOf } from "../../components/account/unsubscribe-model.ts";

/** /unsubscribe (backend 0085): only the two channels a signed link can turn off. */

test("only the two email channels are recognised", () => {
  assert.equal(scopeOf("email"), "email");
  assert.equal(scopeOf("weekly_summary"), "weekly_summary");
  for (const other of ["store_reviews", "", null, undefined, 1, "EMAIL"]) assert.equal(scopeOf(other), null);
});

test("each channel says what it stops, and that the app keeps the notices", () => {
  assert.match(SCOPE_COPY.email.done, /still show up in the app/);
  assert.match(SCOPE_COPY.weekly_summary.what, /weekly summary/);
});

import assert from "node:assert/strict";
import test from "node:test";

import { unreadBadge } from "../../components/ui/unread.ts";

/** MQA-032: a number, not a dot; capped at 9+; nothing when there is nothing. */

test("the badge says how many, up to 9+", () => {
  assert.equal(unreadBadge(0), null);
  assert.equal(unreadBadge(-2), null);
  assert.equal(unreadBadge(Number.NaN), null);
  assert.equal(unreadBadge(1), "1");
  assert.equal(unreadBadge(4), "4");
  assert.equal(unreadBadge(9), "9");
  assert.equal(unreadBadge(10), "9+");
  assert.equal(unreadBadge(240), "9+");
});

import assert from "node:assert/strict";
import test from "node:test";

import { messageActions, threadSignature } from "../../components/messages/messages-model.ts";

/** MQA-011: edit and unsend for the sender within the window; delete-for-me for anyone. */

const NOW = Date.parse("2026-10-05T10:00:00Z");
const open = "2026-10-05T10:10:00Z";
const shut = "2026-10-05T09:59:00Z";
const member = { id: "m1", side: "member" };
const staff = { id: "s1", side: "staff" };

test("the sender may edit and unsend while the window is open", () => {
  const m = { kind: "message", author_id: "m1", from_staff: false, change_until: open };
  assert.deepEqual(messageActions(m, member, NOW), { edit: true, unsend: true, hide: true });
  assert.deepEqual(messageActions({ ...m, change_until: shut }, member, NOW), { edit: false, unsend: false, hide: true });
  assert.deepEqual(messageActions({ ...m, change_until: null }, member, NOW), { edit: false, unsend: false, hide: true });
});

test("nobody changes someone else's message, but anyone may delete it for themselves", () => {
  const theirs = { kind: "message", author_id: "s2", from_staff: true, change_until: open };
  assert.deepEqual(messageActions(theirs, staff, NOW), { edit: false, unsend: false, hide: true });
  assert.deepEqual(messageActions(theirs, member, NOW), { edit: false, unsend: false, hide: true });
  // A staff member who is also the member of the thread acts from the side they sent it.
  const asMember = { kind: "message", author_id: "s1", from_staff: false, change_until: open };
  assert.equal(messageActions(asMember, staff, NOW).edit, false);
});

test("an unsent message and an event line offer no edit", () => {
  const unsent = { kind: "message", author_id: "m1", from_staff: false, unsent: true, change_until: open };
  assert.deepEqual(messageActions(unsent, member, NOW), { edit: false, unsend: false, hide: true });
  assert.deepEqual(messageActions({ kind: "event", author_id: "m1", from_staff: false }, member, NOW),
                   { edit: false, unsend: false, hide: false });
});

test("the live thread notices edits and unsends, not only new messages", () => {
  const a = [{ id: "1" }, { id: "2" }];
  assert.notEqual(threadSignature(a), threadSignature([{ id: "1" }, { id: "2", edited_at: "t" }]));
  assert.notEqual(threadSignature(a), threadSignature([{ id: "1", unsent: true }, { id: "2" }]));
  assert.equal(threadSignature(a), threadSignature([{ id: "1" }, { id: "2" }]));
});

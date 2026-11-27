import assert from "node:assert/strict";
import test from "node:test";

import {
  activeInboxFilters,
  agoCompact,
  closedNote,
  dayLabel,
  eventText,
  fileKind,
  fileSize,
  firstName,
  inboxHref,
  memberTitle,
  previewLine,
  staffTitle,
} from "../../components/messages/messages-model.ts";

const NOW = Date.UTC(2026, 9, 3, 12, 0, 0);
const at = (minutes) => new Date(NOW - minutes * 60_000).toISOString();

test("ages read like the inbox list: just now, 12m, 5h, 2d, 1w, then a date", () => {
  assert.equal(agoCompact(at(0.5), NOW), "just now");
  assert.equal(agoCompact(at(12), NOW), "12m");
  assert.equal(agoCompact(at(5 * 60), NOW), "5h");
  assert.equal(agoCompact(at(2 * 1440), NOW), "2d");
  assert.equal(agoCompact(at(8 * 1440), NOW), "1w");
  assert.equal(agoCompact("2026-08-01T00:00:00Z", NOW), "1 Aug");
  // Manila, not UTC: 16:30 UTC on 2 Oct is already 3 Oct there.
  assert.equal(dayLabel("2026-10-02T16:30:00Z"), "3 Oct");
});

test("event lines say who from the viewer's side", () => {
  const staffViewer = { id: "admin-1", side: "staff" };
  const memberViewer = { id: "member-1", side: "member" };
  const when = "2026-10-04T02:00:00Z";
  assert.equal(eventText("closed", { id: "admin-1", name: "Zient P." }, true, staffViewer, when), "Closed by you · 4 Oct");
  assert.equal(eventText("closed", { id: "admin-2", name: "Mara" }, true, staffViewer, when), "Closed by Mara · 4 Oct");
  assert.equal(eventText("closed", { id: "admin-2", name: "Mara" }, true, memberViewer, when), "Closed by Bluntly · 4 Oct");
  assert.equal(eventText("reopened", { id: "member-1", name: "Jun" }, false, memberViewer, when), "Opened again by you · 4 Oct");
  assert.equal(eventText("support:SUP-1A2B3C4D", { id: "admin-1" }, true, staffViewer, when), "Moved to Queue → Support (SUP-1A2B3C4D) · 4 Oct");
  // MQA-030: the member never sees the team's queue names or ticket codes.
  assert.equal(eventText("support:SUP-1A2B3C4D", { id: "admin-1" }, true, memberViewer, when), "Your request was passed to our support team · 4 Oct");
  // A member resolving their own conversation (Screen/Messages/Thread/Closed).
  assert.equal(eventText("closed", { id: "member-1" }, false, memberViewer, at(0.2), NOW), "Marked as resolved by you · just now");
  assert.equal(eventText("closed", { id: "member-1", name: "Jun R." }, false, staffViewer, when), "Marked as resolved by Jun R. · 4 Oct");
});

test("the closed footer matches the frames", () => {
  const closedAt = "2026-10-04T02:00:00Z";
  assert.equal(
    closedNote({ id: "admin-1" }, closedAt, { id: "admin-1", side: "staff" }, "Jun R."),
    "Closed by you on 4 Oct. If Jun replies, it opens again.",
  );
  assert.equal(closedNote({ id: "admin-2" }, closedAt, { id: "m", side: "member" }, null), "Closed by Bluntly on 4 Oct. Reply to open it again.");
});

test("titles and previews: staff read the party, members read the topic", () => {
  const seller = { audience: "seller", seller_name: "Jisulife Official", member: { name: "Zient P." }, topic: "appeal" };
  const reviewer = { audience: "reviewer", seller_name: null, member: { name: "Kuya Renz" }, topic: "payout" };
  assert.equal(staffTitle(seller), "Jisulife Official · Appeal");
  assert.equal(staffTitle(reviewer), "Kuya Renz · Payout");
  assert.equal(memberTitle({ topic: "appeal", subject: "Rico T.’s review" }), "Appeal · Rico T.’s review");
  assert.equal(memberTitle({ topic: "other", subject: "Adding a second store owner" }), "General · Adding a second store owner");
  const row = { preview: "Thank you.", preview_from_staff: false, member: { name: "Zient P." } };
  assert.equal(previewLine(row, "staff"), "Zient: Thank you.");
  assert.equal(previewLine(row, "member"), "You: Thank you.");
  assert.equal(previewLine({ ...row, preview_from_staff: true }, "member"), "Bluntly: Thank you.");
  assert.equal(previewLine({ ...row, preview: null }, "staff"), "");
  assert.equal(firstName("@kuya_renz"), "kuya_renz");
});

test("inbox URLs drop defaults and reset the page", () => {
  const q = { tab: "all", topic: "", status: "", handled: "", q: "", sort: "latest", page: 3, size: 25 };
  assert.equal(inboxHref(q), "/admin/inbox");
  assert.equal(inboxHref(q, { tab: "sellers" }), "/admin/inbox?tab=sellers");
  assert.equal(inboxHref({ ...q, topic: "appeal" }, { sort: "waiting", c: "abc" }), "/admin/inbox?topic=appeal&sort=waiting&c=abc");
  assert.equal(inboxHref(q, { page: 3 }), "/admin/inbox?page=3");
  assert.equal(activeInboxFilters({ topic: "appeal", status: "", handled: "me" }), 2);
});

test("attachments are described by kind and size", () => {
  assert.equal(fileKind("image/png"), "PNG");
  assert.equal(fileKind("image/jpeg"), "JPG");
  assert.equal(fileKind("application/pdf"), "PDF");
  assert.equal(fileSize(421_888), "412 KB");
  assert.equal(fileSize(1_258_291), "1.2 MB");
  assert.equal(fileSize(null), "");
});

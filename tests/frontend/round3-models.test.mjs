import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { arrangeByOrder, sortComments } from "../../components/review/comment-sort-model.ts";
import { OWN_PROFILE_TABS, PROFILE_TABS, readProfileTab } from "../../components/profile/profile-tabs-model.ts";
import { skipPhotoStep } from "../../components/reviews/review-media-model.ts";
import {
  initialProposedName,
  linkedProductProblem,
  looksLikeUrl,
} from "../../components/reviews/product-link-model.ts";
import {
  applyNotificationAction,
  notificationActionRequest,
} from "../../components/site/notification-model.ts";
import {
  centred,
  clampOffset,
  coverScale,
  outputSide,
  sourceSquare,
  zoomAround,
} from "../../lib/crop-geometry.ts";
import { registrationFormatError } from "../../lib/registration-format.ts";
import { FALLBACK_SHARE_IMAGE, shareImageFor } from "../../lib/share-image.ts";

/**
 * Round 3 (QA-062..075): the pure parts of each fix, so what they decide is
 * pinned without a browser. The browser journeys are in the QA record.
 */

// --- QA-075: one rule, both sides --------------------------------------------

const CASES = JSON.parse(readFileSync(new URL("../../shared/registration-numbers.json", import.meta.url)))
  .cases;

test("the claim form's registration rule matches the server's case table exactly", () => {
  assert.ok(CASES.length >= 30);
  for (const c of CASES) {
    assert.equal(registrationFormatError(c.kind, c.value) === null, c.ok, `${c.kind} ${JSON.stringify(c.value)}`);
  }
});

test("a format message never claims verification", () => {
  for (const c of CASES) {
    const message = registrationFormatError(c.kind, c.value);
    if (message) assert.doesNotMatch(message, /verif/i);
  }
});

// --- QA-064/065: notification actions -----------------------------------------

const NOW = "2026-09-26T12:00:00Z";
const list = () => [
  { id: "a", kind: "k", title: "A", body: null, link: null, read_at: null, created_at: NOW },
  { id: "b", kind: "k", title: "B", body: null, link: null, read_at: NOW, created_at: NOW },
];

test("reading an unread notice moves the count by one, and only once", () => {
  const first = applyNotificationAction(list(), "a", "read", NOW);
  assert.equal(first.unreadDelta, -1);
  assert.equal(first.items[0].read_at, NOW);
  assert.equal(applyNotificationAction(first.items, "a", "read", NOW).unreadDelta, 0);
});

test("mark unread and dismiss move the count the right way", () => {
  assert.equal(applyNotificationAction(list(), "b", "unread", NOW).unreadDelta, 1);
  assert.equal(applyNotificationAction(list(), "a", "unread", NOW).unreadDelta, 0);
  const gone = applyNotificationAction(list(), "a", "dismiss", NOW);
  assert.deepEqual(gone.items.map((n) => n.id), ["b"]);
  assert.equal(gone.unreadDelta, -1);
  assert.equal(applyNotificationAction(list(), "b", "dismiss", NOW).unreadDelta, 0);
  assert.equal(applyNotificationAction(list(), "zzz", "dismiss", NOW).unreadDelta, 0);
});

test("each action is the matching API call, and dismiss is not a POST to read", () => {
  assert.deepEqual(notificationActionRequest("a", "read"), { path: "/api/bff/api/v1/notifications/a/read", method: "POST" });
  assert.deepEqual(notificationActionRequest("a", "unread"), { path: "/api/bff/api/v1/notifications/a/unread", method: "POST" });
  assert.deepEqual(notificationActionRequest("a", "dismiss"), { path: "/api/bff/api/v1/notifications/a", method: "DELETE" });
});

// --- QA-068: a vote does not move a comment ------------------------------------

const comment = (id, up, down, at) => ({ id, helpful_votes: up, unhelpful_votes: down, created_at: at });

test("the thread keeps its order when a vote changes the counts", () => {
  const thread = [comment("x", 5, 0, "2026-09-01"), comment("y", 3, 0, "2026-09-02"), comment("z", 1, 0, "2026-09-03")];
  const order = sortComments(thread).map((c) => c.id);
  assert.deepEqual(order, ["x", "y", "z"]);
  const voted = thread.map((c) => (c.id === "z" ? { ...c, helpful_votes: 9 } : c));
  assert.deepEqual(arrangeByOrder(voted, order).map((c) => c.id), ["x", "y", "z"]);
  // A fresh sort (the reader choosing one) does reorder.
  assert.deepEqual(sortComments(voted).map((c) => c.id)[0], "z");
});

test("a new comment comes first and a removed one drops out", () => {
  const thread = [comment("x", 5, 0, "2026-09-01"), comment("new", 0, 0, "2026-09-05")];
  assert.deepEqual(arrangeByOrder(thread, ["gone", "x"]).map((c) => c.id), ["new", "x"]);
});

// --- QA-069: the Saved tab is the owner's only ---------------------------------

test("saved is a tab on your own profile and nowhere else", () => {
  assert.deepEqual(PROFILE_TABS, ["reviews", "comments", "stats"]);
  assert.deepEqual(OWN_PROFILE_TABS, ["reviews", "comments", "stats", "saved"]);
  assert.equal(readProfileTab("saved", { own: true }), "saved");
  assert.equal(readProfileTab("saved"), "reviews");
});

// --- QA-063: Skip means no photo -------------------------------------------------

test("skipping the photo step clears every photo and moves on", () => {
  const draft = {
    step: 5,
    photoUrls: [
      "https://x.supabase.co/storage/v1/object/public/review-photos/u/p.jpg",
      "https://x.supabase.co/storage/v1/object/public/review-photos/u/q.jpg",
    ],
    receiptKey: "r",
  };
  const next = { ...draft, ...skipPhotoStep(draft.step) };
  assert.deepEqual(next.photoUrls, []);
  assert.equal(next.step, 6);
  assert.equal(next.receiptKey, "r"); // the private receipt has its own control
});

// --- QA-062: the crop geometry ---------------------------------------------------

test("a crop always covers the window and saves what it shows", () => {
  const natural = { w: 4000, h: 3000 }; // landscape phone photo
  const view = 300;
  const s = coverScale(view, natural);
  assert.equal(s, 0.1);
  const o = centred(natural, s, view);
  assert.deepEqual(o, { x: -50, y: 0 });
  // Dragging past an edge is held at the edge: no empty band is ever saved.
  assert.deepEqual(clampOffset({ x: 40, y: 40 }, natural, s, view), { x: 0, y: 0 });
  assert.deepEqual(clampOffset({ x: -999, y: -999 }, natural, s, view), { x: -100, y: 0 });
  const sq = sourceSquare(o, s, view);
  assert.deepEqual(sq, { sx: 500, sy: -0, side: 3000 });
  // Zooming around the centre keeps the centre still.
  const z = zoomAround(o, s, s * 2, { x: 150, y: 150 }, natural, view);
  const before = { x: (150 - o.x) / s, y: (150 - o.y) / s };
  const after = { x: (150 - z.x) / (s * 2), y: (150 - z.y) / (s * 2) };
  assert.deepEqual(after, before);
  // Portrait works the same way round.
  const portrait = { w: 3000, h: 4000 };
  assert.deepEqual(centred(portrait, coverScale(view, portrait), view), { x: 0, y: -50 });
});

test("the saved side is capped and never upscaled, unless fixed", () => {
  assert.equal(outputSide(3000, 1600), 1600);
  assert.equal(outputSide(640, 1600), 640);
  assert.equal(outputSide(640, 512, true), 512);
});

// --- QA-072: a link is not a name --------------------------------------------------

test("the proposed name comes from the link, else the search, never a URL", () => {
  assert.equal(initialProposedName("Anker Soundcore Q20i", "anker"), "Anker Soundcore Q20i");
  assert.equal(initialProposedName(null, "jisulife fan"), "jisulife fan");
  assert.equal(initialProposedName(null, "https://shopee.ph/x-i.1.2"), "");
  assert.equal(initialProposedName(null, ""), "");
});

test("a product needs a real name and a category before it is sent", () => {
  assert.equal(linkedProductProblem("", "audio"), "Give the product a name.");
  assert.match(linkedProductProblem("https://shopee.ph/x", "audio"), /not the link/);
  assert.match(linkedProductProblem("shopee.ph/abc", "audio"), /not the link/);
  assert.equal(linkedProductProblem("Anker Q20i", ""), "Choose a category.");
  assert.equal(linkedProductProblem("Anker Q20i", "audio"), null);
  assert.equal(looksLikeUrl("Model 2.0 fan"), false);
});

// --- QA-070: the share image ----------------------------------------------------------

test("a share uses the review photo, then the product image, then the site card", () => {
  const photo = "https://abc.supabase.co/storage/v1/object/public/review-photos/u/1.jpg";
  const product = "https://abc.supabase.co/storage/v1/object/public/product-images/p.jpg";
  assert.equal(shareImageFor(photo, product), photo);
  assert.equal(shareImageFor(null, product), product);
  assert.equal(shareImageFor(null, null), FALLBACK_SHARE_IMAGE);
  assert.equal(shareImageFor("https://example.com/fixture.jpg", null), FALLBACK_SHARE_IMAGE);
});

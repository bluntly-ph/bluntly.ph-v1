import assert from "node:assert/strict";
import test from "node:test";

import { reviewPhoto } from "../../lib/review-media.ts";

/**
 * Owner bug report, 2026-10-03: a review without an uploaded photo showed the
 * product's canonical image as if the reviewer had uploaded it. A review's
 * media is only its own upload; the product image is product context.
 */

const UPLOADED = "https://x.supabase.co/storage/v1/object/public/review-photos/u1/abc.jpg";
const PRODUCT_IMAGE = "https://x.supabase.co/storage/v1/object/public/product-images/p1.jpg";

test("a review with an uploaded photo shows that photo", () => {
  assert.equal(reviewPhoto({ photo_url: UPLOADED }), UPLOADED);
});

test("a review without an uploaded photo shows none, even when its product has an image", () => {
  const item = { review: { photo_url: null }, product: { image_url: PRODUCT_IMAGE } };
  assert.equal(reviewPhoto(item.review), null);
  // The product keeps its image for product context.
  assert.equal(item.product.image_url, PRODUCT_IMAGE);
});

test("a missing review or an unusable value is no photo", () => {
  assert.equal(reviewPhoto(null), null);
  assert.equal(reviewPhoto(undefined), null);
  assert.equal(reviewPhoto({}), null);
  assert.equal(reviewPhoto({ photo_url: "" }), null);
});

// 0094: several photos, in order; none is none.
test("reviewPhotos lists the review's own photos in order, and never the product's", async () => {
  const { reviewPhotos } = await import("../../lib/review-media.ts");
  const a = "https://x.supabase.co/storage/v1/object/public/review-photos/u/a.jpg";
  const b = "https://x.supabase.co/storage/v1/object/public/review-photos/u/b.jpg";
  assert.deepEqual(reviewPhotos({ photo_urls: [b, a], photo_url: b }), [b, a]);
  assert.deepEqual(reviewPhotos({ photo_url: a }), [a]);
  assert.deepEqual(reviewPhotos({ photo_urls: [], photo_url: null }), []);
  assert.deepEqual(reviewPhotos(null), []);
});

// --- Multiple review photos (owner, 2026-10-05) --------------------------------

import {
  MAX_REVIEW_PHOTOS,
  addPhoto,
  cleanPhotos,
  draftPhotos,
  removePhoto,
  replacePhoto,
  reviewMediaPayload,
  skipPhotoStep,
} from "../../components/reviews/review-media-model.ts";

const A = "https://x.supabase.co/storage/v1/object/public/review-photos/u1/a.jpg";
const B = "https://x.supabase.co/storage/v1/object/public/review-photos/u1/b.jpg";
const C = "https://x.supabase.co/storage/v1/object/public/review-photos/u1/c.jpg";

test("no photos sends no photo — null and an empty list, never a fallback", () => {
  assert.deepEqual(reviewMediaPayload([]), { photo_url: null, photo_urls: [] });
});

test("one photo is both photo_url and the whole list", () => {
  assert.deepEqual(reviewMediaPayload([A]), { photo_url: A, photo_urls: [A] });
});

test("several photos keep the reviewer's order; the first is photo_url", () => {
  assert.deepEqual(reviewMediaPayload([B, A, C]), { photo_url: B, photo_urls: [B, A, C] });
});

test("the list is capped, de-duplicated and holds only real strings", () => {
  assert.equal(MAX_REVIEW_PHOTOS, 4);
  assert.deepEqual(cleanPhotos([A, A, "", null, 3, B]), [A, B]);
  assert.equal(cleanPhotos(["1", "2", "3", "4", "5"].map((n) => `${A}?${n}`)).length, MAX_REVIEW_PHOTOS);
  assert.deepEqual(cleanPhotos("not a list"), []);
});

test("add, remove and replace one photo", () => {
  assert.deepEqual(addPhoto([A], B), [A, B]);
  assert.deepEqual(addPhoto([A, B, C, `${A}?4`], `${A}?5`), [A, B, C, `${A}?4`]);
  assert.deepEqual(removePhoto([A, B, C], 1), [A, C]);
  assert.deepEqual(replacePhoto([A, B, C], 1, `${B}?new`), [A, `${B}?new`, C]);
  assert.deepEqual(replacePhoto([A], 5, B), [A]);
});

test("an old draft's single photo is adopted; nothing is invented", () => {
  assert.deepEqual(draftPhotos({ photoUrl: A }), [A]);
  assert.deepEqual(draftPhotos({ photoUrl: null }), []);
  assert.deepEqual(draftPhotos({}), []);
  assert.deepEqual(draftPhotos({ photoUrls: [A, B], photoUrl: C }), [A, B]);
  assert.deepEqual(draftPhotos(null), []);
});

test("skip after selecting clears the selection", () => {
  assert.deepEqual({ photoUrls: [A, B], ...skipPhotoStep(5) }, { photoUrls: [], step: 6 });
});

import { reviewPhotos } from "../../lib/review-media.ts";

test("reviewPhotos: an empty list falls back to the one photo; unusable values are none", () => {
  assert.deepEqual(reviewPhotos({ photo_url: A, photo_urls: [A, B] }), [A, B]);
  assert.deepEqual(reviewPhotos({ photo_url: A }), [A]);
  assert.deepEqual(reviewPhotos({ photo_url: A, photo_urls: [] }), [A]);
  assert.deepEqual(reviewPhotos({ photo_url: null, photo_urls: [] }), []);
  assert.deepEqual(reviewPhotos({ photo_url: null, photo_urls: ["", null, "https://example.com/x.jpg"] }), []);
  assert.deepEqual(reviewPhotos(null), []);
});

test("a review without uploads has no photos even when its product has an image", () => {
  const item = { review: { photo_url: null, photo_urls: [] }, product: { image_url: PRODUCT_IMAGE } };
  assert.deepEqual(reviewPhotos(item.review), []);
});

import assert from "node:assert/strict";
import test from "node:test";

import { filterSellerReviews, sharePercent, shortAge } from "../../components/sellers/seller-model.ts";

const NOW = Date.UTC(2026, 8, 14, 12, 0, 0);
const ago = (seconds) => new Date(NOW - seconds * 1000).toISOString();

test("a review's age is written the way the frame writes it: 5h, 12d", () => {
  assert.equal(shortAge(ago(30), NOW), "now");
  assert.equal(shortAge(ago(5 * 60), NOW), "5m");
  assert.equal(shortAge(ago(5 * 3600), NOW), "5h");
  assert.equal(shortAge(ago(12 * 86400), NOW), "12d");
  assert.equal(shortAge(ago(21 * 86400), NOW), "3w");
  assert.equal(shortAge(ago(800 * 86400), NOW), "2y");
});

test("an unreadable or future date is not given an age", () => {
  assert.equal(shortAge("not a date", NOW), "");
  assert.equal(shortAge(ago(-3600), NOW), "now");
});

/**
 * The seller page's "All reviews" block, as "Seller Page - Review.png" draws it:
 * a star breakdown written as "88%", "2.3%", and a star filter plus a keyword
 * search over the store's reviews.
 */

test("shares of ten percent and more are whole numbers", () => {
  assert.equal(sharePercent(0.88), "88%");
  assert.equal(sharePercent(0.1), "10%");
  assert.equal(sharePercent(1), "100%");
});

test("shares under ten percent keep one decimal, as the frame writes them", () => {
  assert.equal(sharePercent(0.023), "2.3%");
  assert.equal(sharePercent(0.073), "7.3%");
});

test("a share that rounds up to ten is written as ten, not 10.0", () => {
  assert.equal(sharePercent(0.0999), "10%");
});

test("no reviews at a star is 0%, not 0.0%", () => {
  assert.equal(sharePercent(0), "0%");
});

const review = (id, rating, title, comment) => ({
  id,
  overall_rating: rating,
  title,
  comment,
});

const REVIEWS = [
  review("a", 5, "Walang bubble wrap sa packaging!!!", "Box arrived crushed."),
  review("b", 1, "tipid na tipid sa packaging much?", null),
  review("c", 4, null, "Fast shipping, good seller."),
];

test("every star ticked and no keyword keeps every review, in order", () => {
  const out = filterSellerReviews(REVIEWS, { stars: [1, 2, 3, 4, 5], keyword: "" });
  assert.deepEqual(out.map((r) => r.id), ["a", "b", "c"]);
});

test("unticking a star hides that star's reviews", () => {
  const out = filterSellerReviews(REVIEWS, { stars: [4, 5], keyword: "" });
  assert.deepEqual(out.map((r) => r.id), ["a", "c"]);
});

test("with no star ticked nothing matches", () => {
  assert.deepEqual(filterSellerReviews(REVIEWS, { stars: [], keyword: "" }), []);
});

test("the keyword matches title or comment, ignoring case and surrounding space", () => {
  assert.deepEqual(
    filterSellerReviews(REVIEWS, { stars: [1, 2, 3, 4, 5], keyword: "  PACKAGING " }).map((r) => r.id),
    ["a", "b"],
  );
  assert.deepEqual(
    filterSellerReviews(REVIEWS, { stars: [1, 2, 3, 4, 5], keyword: "shipping" }).map((r) => r.id),
    ["c"],
  );
});

test("stars and keyword narrow together", () => {
  assert.deepEqual(
    filterSellerReviews(REVIEWS, { stars: [5], keyword: "packaging" }).map((r) => r.id),
    ["a"],
  );
});

// 2026-09-24. Seller ratings are half steps (0048). The list filter matched
// the exact value against the ticked whole stars, so a 4.5 matched nothing and
// was missing from the list with every box ticked — while the bars counted it.
test("a half-star review is in the list, under the bar the summary counts it in", async () => {
  const { filterSellerReviews, starBucket } = await import("../../components/sellers/seller-model.ts");
  const halves = [
    { id: "a", overall_rating: 4.5, title: null, comment: null },
    { id: "b", overall_rating: 0.5, title: null, comment: null },
    { id: "c", overall_rating: 0, title: null, comment: null },
    { id: "d", overall_rating: 5, title: null, comment: null },
  ];
  assert.deepEqual(halves.map((r) => starBucket(r.overall_rating)), [4, 1, 1, 5]);
  const every = filterSellerReviews(halves, { stars: [1, 2, 3, 4, 5], keyword: "" });
  assert.deepEqual(every.map((r) => r.id), ["a", "b", "c", "d"]);
  assert.deepEqual(filterSellerReviews(halves, { stars: [4], keyword: "" }).map((r) => r.id), ["a"]);
  assert.deepEqual(filterSellerReviews(halves, { stars: [1], keyword: "" }).map((r) => r.id), ["b", "c"]);
});

test("Time keeps only the reviews posted within the period (QA-057)", async () => {
  const { filterSellerReviews } = await import("../../components/sellers/seller-model.ts");
  const now = Date.parse("2026-09-24T00:00:00Z");
  const day = 86_400_000;
  const rows = [
    { id: "new", overall_rating: 4, title: null, comment: null, created_at: new Date(now - 5 * day).toISOString() },
    { id: "mid", overall_rating: 4, title: null, comment: null, created_at: new Date(now - 60 * day).toISOString() },
    { id: "old", overall_rating: 4, title: null, comment: null, created_at: new Date(now - 500 * day).toISOString() },
  ];
  const ids = (period) => filterSellerReviews(rows, { stars: [4], keyword: "", period, now }).map((r) => r.id);
  assert.deepEqual(ids("month"), ["new"]);
  assert.deepEqual(ids("year"), ["new", "mid"]);
  assert.deepEqual(ids("all"), ["new", "mid", "old"]);
});

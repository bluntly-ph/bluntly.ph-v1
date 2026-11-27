import assert from "node:assert/strict";
import test from "node:test";

import {
  parseAnswerWindow,
  parseClaimed,
  parseFlag,
  parseReviewSort,
  parseSellerRating,
  parseStars,
  searchTabHref,
} from "../../components/search/search-tabs-model.ts";
import { feedFilterParams, sellerFilterParams } from "../../lib/search-filter-params.ts";

/**
 * Search filters, step 2 (owner 2026-10-07): the frames' Rating, Show only,
 * Variant and "Lowest rated" on reviews; Unclaimed, Rating and Answers buyers
 * on sellers. The URL carries them so a filtered search can be shared, and the
 * sheet's live count asks the API with the same query the list will.
 */

test("Rating groups: whole stars 1-5, highest first, no repeats, nonsense dropped", () => {
  assert.deepEqual(parseStars("2,5,5,9,x,4"), [5, 4, 2]);
  assert.deepEqual(parseStars(undefined), []);
});

test("Lowest rated is a review order the URL keeps", () => {
  assert.equal(parseReviewSort("lowest"), "lowest");
  assert.equal(searchTabHref("reviews", { q: "fan", sort: "lowest" }), "/search?q=fan&sort=lowest");
});

test("the reviews URL carries Rating, Show only and Variant; all five stars is All", () => {
  assert.equal(
    searchTabHref("reviews", { q: "fan", stars: [5, 4], photos: true, verified: true, recommends: true, variant: "4000 mAh" }),
    "/search?q=fan&stars=5%2C4&photos=1&verified=1&recommends=1&variant=4000+mAh",
  );
  assert.equal(searchTabHref("reviews", { q: "fan", stars: [1, 2, 3, 4, 5] }), "/search?q=fan");
  assert.equal(parseFlag("1"), true);
  assert.equal(parseFlag("yes"), false);
});

test("Profile is three-way: claimed, unclaimed, or both", () => {
  assert.equal(parseClaimed("1"), true);
  assert.equal(parseClaimed("0"), false);
  assert.equal(parseClaimed(undefined), undefined);
  assert.equal(searchTabHref("sellers", { claimed: false }), "/search?tab=sellers&claimed=0");
  assert.equal(searchTabHref("sellers", { claimed: undefined }), "/search?tab=sellers");
});

test("the sellers URL carries Rating and Answers buyers", () => {
  assert.equal(
    searchTabHref("sellers", { q: "jisu", minRating: 4, answers: "day" }),
    "/search?q=jisu&tab=sellers&rating=4&answers=day",
  );
  assert.equal(parseSellerRating("4"), 4);
  assert.equal(parseSellerRating("5"), undefined);
  assert.equal(parseAnswerWindow("week"), "week");
  assert.equal(parseAnswerWindow("month"), undefined);
});

test("the API query: what the list and the live count both send", () => {
  assert.equal(
    feedFilterParams({ product_id: "p1", stars: [5, 4], photos: true, verified: false, variant: "Blue" }).toString(),
    // Stars in one order (2026-10-22): the query string is the cache key.
    "product_id=p1&stars=4&stars=5&photos=true&variant=Blue",
  );
  assert.equal(
    sellerFilterParams({ q: " jisu ", claimed: false, minRating: 3, answers: "week" }).toString(),
    "q=jisu&claimed=false&min_rating=3&answers_within=week",
  );
  // Both profiles: no claimed parameter at all.
  assert.equal(sellerFilterParams({ claimed: undefined }).toString(), "");
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { MAX_QUERY_LENGTH, feedQuery } from "../../lib/search-filter-params.ts";

/**
 * One builder for every review feed and count query string (2026-10-22).
 *
 * The query string is the Data Cache key. Crawlers and readers rarely spell a
 * search the same way twice, so every spelling of the same question has to
 * collapse to one key, or each is a miss and a backend call.
 */

test("keys come out sorted, whatever order the caller set them in", () => {
  const a = feedQuery({ q: "fan", categories: ["beauty"], stars: [5] }, { sort: "newest", limit: 24 });
  const b = feedQuery({ stars: [5], categories: ["beauty"], q: "fan" }, { limit: 24, sort: "newest" });
  assert.equal(a, b);
  const keys = [...new URLSearchParams(a).keys()];
  assert.deepEqual(keys, [...keys].sort());
});

test("UI-only parameters never reach the API", () => {
  const withUi = feedQuery({ q: "fan", from: "categories", tab: "reviews", page: "3", sheet: "filters" });
  assert.equal(withUi, feedQuery({ q: "fan" }));
  assert.equal(withUi, "q=fan");
});

test("the search text is trimmed and capped at the API's 200 characters", () => {
  assert.equal(feedQuery({ q: "  fan  " }), "q=fan");
  const long = feedQuery({ q: `${"x".repeat(250)}` });
  assert.equal(new URLSearchParams(long).get("q").length, MAX_QUERY_LENGTH);
  assert.equal(MAX_QUERY_LENGTH, 200);
  assert.equal(feedQuery({ q: "   " }), "");
});

test("category slugs are lowercased, de-duplicated and ordered", () => {
  assert.equal(
    feedQuery({ category: "Beauty", categories: ["electronics", "BEAUTY", " pets "] }),
    "category=beauty&category=electronics&category=pets",
  );
});

test("star groups are de-duplicated and ordered", () => {
  assert.equal(feedQuery({ stars: [5, 3, 5] }), "stars=3&stars=5");
});

test("page controls ride beside the filters, and a first page has no offset", () => {
  assert.equal(
    feedQuery({}, { mode: "for-you", sort: "wilson", limit: 12, offset: 0, view: "card" }),
    "limit=12&mode=for-you&sort=wilson&view=card",
  );
  assert.equal(feedQuery({}, { offset: 24 }), "offset=24");
});

test("lib/reviews.ts builds every feed and count URL with feedQuery", () => {
  // Imported as text: lib/reviews.ts is server-only and imports through `@/`.
  const src = readFileSync(new URL("../../lib/reviews.ts", import.meta.url), "utf8");
  const urls = [...src.matchAll(/apiFetch<[^(]*\(\s*`(\/api\/v1\/reviews\/feed[^`]*)`/g)].map((m) => m[1]);
  assert.ok(urls.length >= 6, `expected the feed reads, found ${urls.length}`);
  for (const url of urls) {
    if (url.startsWith("/api/v1/reviews/feed/variants")) continue;
    assert.match(url, /\?\$\{(?:query|feedQuery\()/, `${url} is not built by feedQuery`);
  }
  assert.doesNotMatch(src, /new URLSearchParams\(\{/, "a hand-built feed query string");
});

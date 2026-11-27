import assert from "node:assert/strict";
import test from "node:test";

import {
  budgetLabel,
  clearCategoryHref,
  parseBudget,
  parseCategories,
  parseLens,
  parseTrust,
  parsePeriod,
  parsePlatform,
  parseQuestionSort,
  parseReviewSort,
  parseSellerSort,
  searchTabHref,
  toggleCategory,
} from "../../components/search/search-tabs-model.ts";

/**
 * The tabs are links to real URLs, so what they carry across is the contract:
 * the reader's query follows them, and a filter that means nothing on the other
 * side does not.
 */

test("the query follows the reader to the other tab", () => {
  assert.equal(searchTabHref("questions", { q: "jisulife" }), "/search?q=jisulife&tab=questions");
  assert.equal(searchTabHref("reviews", { q: "jisulife" }), "/search?q=jisulife");
});

test("reviews is the default tab and carries no tab parameter", () => {
  assert.equal(searchTabHref("reviews", {}), "/search");
  assert.equal(searchTabHref("questions", {}), "/search?tab=questions");
});

test("a category narrows reviews and is not carried to questions", () => {
  assert.equal(
    searchTabHref("reviews", { q: "fan", category: "audio" }),
    "/search?q=fan&category=audio",
  );
  // Categories do not apply to questions; carrying one would put a filter in the
  // URL that silently does nothing.
  assert.equal(searchTabHref("questions", { q: "fan", category: "audio" }), "/search?q=fan&tab=questions");
});

test("the sellers tab carries the query and not the category", () => {
  assert.equal(
    searchTabHref("sellers", { q: "jisulife", category: "audio" }),
    "/search?q=jisulife&tab=sellers",
  );
});

test("the categories back-link context survives both tabs", () => {
  assert.equal(
    searchTabHref("questions", { q: "fan", from: "categories" }),
    "/search?q=fan&tab=questions&from=categories",
  );
});

test("a blank query is not carried as an empty parameter", () => {
  assert.equal(searchTabHref("questions", { q: "   " }), "/search?tab=questions");
  assert.equal(searchTabHref("reviews", { q: "" }), "/search");
});

test("a query with spaces and symbols is encoded", () => {
  assert.equal(
    searchTabHref("questions", { q: "jisulife fan & noise" }),
    "/search?q=jisulife+fan+%26+noise&tab=questions",
  );
});

// The "Sort" pill (Figma 1591:5408) writes the review order into the URL. The
// feed serves two orders, most helpful (`wilson`, the default) and latest.

test("a chosen review order is carried with the reviews", () => {
  assert.equal(
    searchTabHref("reviews", { q: "fan", category: "audio", sort: "newest" }),
    "/search?q=fan&category=audio&sort=newest",
  );
});

test("the default order is not written into the URL", () => {
  assert.equal(searchTabHref("reviews", { q: "fan", sort: "wilson" }), "/search?q=fan");
});

test("the order is not carried to questions or sellers, which serve none", () => {
  assert.equal(searchTabHref("questions", { q: "fan", sort: "newest" }), "/search?q=fan&tab=questions");
  assert.equal(searchTabHref("sellers", { sort: "newest" }), "/search?tab=sellers");
});

test("an order the feed does not serve falls back to most helpful", () => {
  assert.equal(parseReviewSort("newest"), "newest");
  assert.equal(parseReviewSort("wilson"), "wilson");
  // The Sort frame's "Oldest" is served since 2026-09-24 (QA-053).
  assert.equal(parseReviewSort("oldest"), "oldest");
  assert.equal(parseReviewSort("credibility"), "wilson");
  assert.equal(parseReviewSort(undefined), "wilson");
});

test("resetting the category sends a categories visitor back to /categories", () => {
  // BUG-011: clearing the filter must not strand them on /search.
  assert.equal(clearCategoryHref({ q: "fan", sort: "newest", from: "categories" }), "/categories");
  assert.equal(clearCategoryHref({ q: "fan", sort: "newest" }), "/search?q=fan&sort=newest");
});

// ---- 2026-09-24: the controls the Figma frames draw, now served (QA-025/050/052/053)

test("several categories travel together, in order, without repeats (QA-025)", () => {
  assert.equal(
    searchTabHref("reviews", { q: "fan", categories: ["electronics", "beauty", "electronics"] }),
    "/search?q=fan&category=electronics%2Cbeauty",
  );
  assert.deepEqual(parseCategories("electronics,beauty"), ["electronics", "beauty"]);
  assert.deepEqual(parseCategories(["electronics", "beauty,pets"]), ["electronics", "beauty", "pets"]);
  // A hand-edited URL cannot put an unknown, inert category on the page.
  assert.deepEqual(parseCategories("electronics,nope", ["electronics", "beauty"]), ["electronics"]);
  assert.deepEqual(toggleCategory(["electronics"], "beauty"), ["electronics", "beauty"]);
  assert.deepEqual(toggleCategory(["electronics", "beauty"], "electronics"), ["beauty"]);
});

test("Time narrows reviews and questions, and the default is not written (QA-053)", () => {
  assert.equal(searchTabHref("reviews", { period: "month" }), "/search?period=month");
  assert.equal(searchTabHref("reviews", { period: "all" }), "/search");
  assert.equal(searchTabHref("questions", { q: "fan", period: "year" }), "/search?q=fan&tab=questions&period=year");
  assert.equal(searchTabHref("sellers", { period: "year" }), "/search?tab=sellers");
  assert.equal(parsePeriod("month"), "month");
  assert.equal(parsePeriod("decade"), "all");
});

test("questions order by date; stores filter by marketplace and claim, and order by reviews", () => {
  assert.equal(searchTabHref("questions", { questionSort: "oldest" }), "/search?tab=questions&sort=oldest");
  assert.equal(searchTabHref("questions", { questionSort: "newest" }), "/search?tab=questions");
  assert.equal(
    searchTabHref("sellers", { q: "jisu", platform: "lazada", claimed: true, sellerSort: "reviews" }),
    "/search?q=jisu&tab=sellers&platform=lazada&claimed=1&sort=reviews",
  );
  assert.equal(parseQuestionSort("oldest"), "oldest");
  assert.equal(parseQuestionSort("best"), "newest");
  assert.equal(parseSellerSort("reviews"), "reviews");
  assert.equal(parseSellerSort("name"), "name");
  assert.equal(parseSellerSort("rating"), "ranked");
  assert.equal(parseSellerSort(undefined), "ranked");
  assert.equal(parsePlatform("shopee"), "shopee");
  assert.equal(parsePlatform("amazon"), undefined);
});

// MQA-033: the Sellers tab is ranked by default, so the plain URL is the ranked one.
test("the ranked store order is the default and carries no sort", () => {
  assert.equal(searchTabHref("sellers", { sellerSort: "ranked" }), "/search?tab=sellers");
  assert.equal(searchTabHref("sellers", { sellerSort: "name" }), "/search?tab=sellers&sort=name");
  assert.equal(searchTabHref("sellers", {}), "/search?tab=sellers");
});

test("each tab's filters stay with that tab", () => {
  const all = { q: "x", categories: ["beauty"], sort: "newest", period: "month", questionSort: "oldest",
                platform: "shopee", claimed: true, sellerSort: "reviews" };
  assert.equal(searchTabHref("reviews", all), "/search?q=x&category=beauty&sort=newest&period=month");
  assert.equal(searchTabHref("questions", all), "/search?q=x&tab=questions&sort=oldest&period=month");
  assert.equal(searchTabHref("sellers", all), "/search?q=x&tab=sellers&platform=shopee&claimed=1&sort=reviews");
});

// QA-053: the sheet's Review score, Trust rating and Budget travel in the URL
// with the reviews, and nowhere else.

test("a lens, a trust band and a budget are carried with the reviews", () => {
  assert.equal(
    searchTabHref("reviews", { q: "fan", lens: "hidden_gems", trust: "high", maxPrice: 2500 }),
    "/search?q=fan&lens=hidden_gems&trust=high&max_price=2500",
  );
});

test("the review-only filters are not carried to another tab", () => {
  const state = { q: "fan", lens: "trending", trust: "low", maxPrice: 500 };
  assert.equal(searchTabHref("questions", state), "/search?q=fan&tab=questions");
  assert.equal(searchTabHref("sellers", state), "/search?q=fan&tab=sellers");
  assert.equal(searchTabHref("people", state), "/search?q=fan&tab=people");
});

test("clearing the review filters drops the lens, trust band and budget", () => {
  assert.equal(clearCategoryHref({ q: "fan", sort: "newest" }), "/search?q=fan&sort=newest");
});

test("only known lenses, bands and budget stops survive a hand-edited URL", () => {
  assert.equal(parseLens("controversial"), "controversial");
  assert.equal(parseLens("viral"), undefined);
  assert.equal(parseTrust("high"), "high");
  assert.equal(parseTrust("medium"), undefined);
  assert.equal(parseBudget("1000"), 1000);
  assert.equal(parseBudget("1234"), undefined);
  assert.equal(parseBudget(undefined), undefined);
});

test("a budget chip reads as pesos", () => {
  assert.equal(budgetLabel(2500), "Up to ₱2,500");
});

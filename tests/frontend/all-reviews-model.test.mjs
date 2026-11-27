import assert from "node:assert/strict";
import { test } from "node:test";

import {
  activeFilterCount,
  allReviewsApiQuery,
  allReviewsHref,
  allReviewsQuery,
  parseAllReviewsFilters,
  postedText,
  queueStatusText,
  updatedAtText,
  wilsonText,
} from "../../components/admin/all-reviews-model.ts";
import { isTab } from "../../components/admin/review-queue-model.ts";

/**
 * All Reviews (QA, 2026-09-29): the Administrator's list of every review, beside
 * the Review Queue. The server filters, sorts and pages; these are the pure
 * pieces between the URL and that request.
 */

const params = (q) => new URLSearchParams(q);

test("All reviews is a Review Queue tab", () => {
  assert.equal(isTab("all"), true);
  assert.equal(isTab("everything"), false);
});

test("the tab's filters are prefixed, validated and never collide with the queue's", () => {
  const f = parseAllReviewsFilters(
    params("q=queue&sort=tier&page=4&aq=+wok+&astate=taken_down&aearn=pending&afrom=2026-09-01&ato=2026-09-29&asort=wilson_desc&apage=3&asize=25"),
  );
  assert.deepEqual(f, {
    q: "wok", state: "taken_down", earn: "pending", from: "2026-09-01", to: "2026-09-29",
    sort: "wilson_desc", page: 3, size: 25,
  });
  // Anything outside the vocabulary falls back instead of reaching the API.
  const bad = parseAllReviewsFilters(params("astate=gone&aearn=paid&afrom=yesterday&asort=random&apage=-5&asize=1000"));
  assert.deepEqual(bad, { q: "", state: "", earn: "", from: "", to: "", sort: "newest", page: 1, size: 10 });
});

test("the API query names the backend's own parameters; the page becomes limit/offset", () => {
  const f = parseAllReviewsFilters(params("aq=wok&astate=published&afrom=2026-09-01&asort=wilson_asc&apage=3&asize=25"));
  const q = new URLSearchParams(allReviewsApiQuery(f));
  assert.equal(q.get("q"), "wok");
  assert.equal(q.get("state"), "published");
  assert.equal(q.get("created_from"), "2026-09-01");
  assert.equal(q.get("created_to"), null);
  assert.equal(q.get("sort"), "wilson_asc");
  assert.equal(q.get("limit"), "25");
  assert.equal(q.get("offset"), "50");
});

test("a changed filter starts at page one; paging keeps everything else", () => {
  const f = parseAllReviewsFilters(params("aq=wok&asort=wilson_desc&apage=3"));
  assert.equal(allReviewsHref(f, { state: "published" }),
    "/admin/review-queue?tab=all&aq=wok&astate=published&asort=wilson_desc");
  assert.equal(allReviewsHref(f, { page: 4 }),
    "/admin/review-queue?tab=all&aq=wok&asort=wilson_desc&apage=4");
  assert.equal(allReviewsHref(parseAllReviewsFilters(params(""))), "/admin/review-queue?tab=all");
  // What the pager keeps: everything but the page and its size.
  assert.deepEqual(allReviewsQuery(parseAllReviewsFilters(params("aq=wok&apage=3&asize=25"))), { tab: "all", aq: "wok" });
});

test("the Filter dot counts state, earning and the posted range once", () => {
  assert.equal(activeFilterCount(parseAllReviewsFilters(params(""))), 0);
  assert.equal(activeFilterCount(parseAllReviewsFilters(params("astate=removed&aearn=pending&afrom=2026-09-01&ato=2026-09-02"))), 3);
});

test("Posted reads as the frame writes it, with the year only when it is not this one", () => {
  const now = Date.parse("2026-10-03T08:00:00Z");
  assert.equal(postedText("2026-09-28T03:00:00Z", now), "28 Sep");
  // 04:00 on 1 January in Manila: this year there, though still 2025 in UTC.
  assert.equal(postedText("2025-12-31T20:00:00Z", now), "1 Jan");
  assert.equal(postedText("2025-06-01T03:00:00Z", now), "1 Jun 2025");
  assert.equal(postedText("not a date", now), "");
});

test("Wilson prints to two places and never as NaN", () => {
  assert.equal(wilsonText("0.30064"), "0.30");
  assert.equal(wilsonText(0), "0.00");
  assert.equal(wilsonText("not a number"), "—");
});

const page = { earn_gate_phase: "post_seeding", gate_threshold: 0.65, gate_min_stage2_voters: 3 };
const row = (over = {}) => ({
  in_review_queue: false, is_thread_root: true, state: "published", earn_eligible_status: "none",
  gate: { wilson_lower_bound: 0.2, effective_total: 1, stage2_plus_voters: 1, passes: false },
  ...over,
});

test("a review not in the queue says why, in the gate's own numbers", () => {
  assert.equal(queueStatusText(row(), page),
    "Not queued yet: the earnings gate needs Wilson ≥ 0.65 from 3 Stage 2+ voters (now 0.20, 1 voter)");
  assert.equal(queueStatusText(row({ in_review_queue: true }), page), "In the Review Queue");
  assert.equal(queueStatusText(row({ is_thread_root: false }), page),
    "An update: earning stays with the thread's first review");
  assert.equal(queueStatusText(row({ state: "taken_down" }), page), "Not queued: not on the site");
  assert.equal(queueStatusText(row({ earn_eligible_status: "monetized" }), page), "Decided: Link attached");
  assert.equal(queueStatusText(row(), { ...page, earn_gate_phase: "seeding" }), "Not queued");
});

test("'Updated' is written in Manila time, so server and browser print the same", () => {
  // 2026-09-29 06:05:09 UTC is 14:05:09 in Manila.
  assert.equal(updatedAtText(Date.UTC(2026, 8, 29, 6, 5, 9)), "Updated 14:05:09");
});

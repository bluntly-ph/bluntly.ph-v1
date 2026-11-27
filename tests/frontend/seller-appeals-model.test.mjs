import assert from "node:assert/strict";
import test from "node:test";

test("Appeals Sort / Filter / Search (Figma Menu/Seller/Appeals 8198:21632, 8198:21642)", async () => {
  const { applyAppeals, appealFilters, lastUpdate } = await import("../../components/seller/console/appeals-model.ts");
  const rows = [
    { id: "a", seller_review_id: "r1", reason: "No order that week", status: "open", created_at: "2026-09-10T00:00:00Z", review_rating: 1, reviewer: { display_name: "Rico T." } },
    { id: "b", seller_review_id: "r2", reason: "Same text on 4 stores", status: "substantiation_requested", created_at: "2026-09-01T00:00:00Z", substantiation_requested_at: "2026-09-20T00:00:00Z", review_rating: 2, review_title: "Scammer" },
    { id: "c", seller_review_id: "r3", reason: "Courier signed", status: "upheld", created_at: "2026-08-01T00:00:00Z", decided_at: "2026-09-15T00:00:00Z", review_rating: 1.5 },
  ];
  assert.deepEqual(applyAppeals(rows, {}).map((a) => a.id), ["a", "b", "c"]);
  assert.deepEqual(applyAppeals(rows, { sort: "oldest" }).map((a) => a.id), ["c", "b", "a"]);
  assert.deepEqual(applyAppeals(rows, { sort: "updated" }).map((a) => a.id), ["b", "c", "a"]);
  assert.equal(lastUpdate(rows[2]), new Date("2026-09-15T00:00:00Z").getTime());
  assert.deepEqual(applyAppeals(rows, { status: "upheld" }).map((a) => a.id), ["c"]);
  assert.deepEqual(applyAppeals(rows, { rating: "1" }).map((a) => a.id), ["a", "c"]);
  assert.deepEqual(applyAppeals(rows, { q: "rico" }).map((a) => a.id), ["a"]);
  assert.deepEqual(applyAppeals(rows, { q: "scammer" }).map((a) => a.id), ["b"]);
  const [status, rating] = appealFilters(rows);
  assert.deepEqual(status.options, [["open", "Open", 1], ["substantiation_requested", "Proof requested", 1], ["upheld", "Upheld", 1]]);
  assert.deepEqual(rating.options, [["1", "1★", 2], ["2", "2★", 1]]);
});

test("Questions Sort / Filter / Search (Figma Menu/Seller/Questions 8198:21562, 8198:21572)", async () => {
  const { applyQuestions, questionFilters } = await import("../../components/seller/console/questions-model.ts");
  const rows = [
    { id: "a", body: "Do you ship to Davao?", created_at: "2026-09-10T00:00:00Z", answer_count: 1, community_answers: 0, followers: 2, asker: { display_name: "Mara L." } },
    { id: "b", body: "Is there a warranty?", created_at: "2026-09-01T00:00:00Z", answer_count: 2, community_answers: 2, followers: 9 },
    { id: "c", body: "Same-day shipping?", created_at: "2026-09-05T00:00:00Z", answer_count: 0, community_answers: 0, followers: 2 },
  ];
  assert.deepEqual(applyQuestions(rows, {}).map((q) => q.id), ["b", "c", "a"]);
  assert.deepEqual(applyQuestions(rows, { sort: "newest" }).map((q) => q.id), ["a", "c", "b"]);
  assert.deepEqual(applyQuestions(rows, { sort: "followed" }).map((q) => q.id), ["b", "c", "a"]);
  assert.deepEqual(applyQuestions(rows, { community: "none" }).map((q) => q.id), ["c", "a"]);
  assert.deepEqual(applyQuestions(rows, { community: "has" }).map((q) => q.id), ["b"]);
  assert.deepEqual(applyQuestions(rows, { q: "mara" }).map((q) => q.id), ["a"]);
  assert.deepEqual(questionFilters(rows)[0].options, [["none", "None yet", 2], ["has", "Has answers", 1]]);
});

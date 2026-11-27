import assert from "node:assert/strict";
import test from "node:test";

import { agoShort, greeting, monthLabel, notificationsQuery, pct, tabOf, waitingItems, waitingTotal } from "../../components/seller/console/overview-model.ts";

/** Seller console Overview (Figma Screen/Seller/Overview 8190:20643). */

const now = Date.parse("2026-10-03T02:00:00Z"); // 10:00 in Manila
const day = 86_400_000;
const iso = (msAgo) => new Date(now - msAgo).toISOString();

test("Waiting on you: questions, unanswered reviews and open flags, oldest first", () => {
  const items = waitingItems(
    {
      seller: { id: "s1" },
      waiting_questions: [{ id: "q1", body: "Does it clip onto a stroller?", created_at: iso(3 * day), asker: "Mara L." }],
      reviews: [
        { id: "r1", created_at: iso(2 * day), title: "Battery died after two weeks", overall_rating: 2, has_store_response: false, reviewer_name: "Paolo D." },
        { id: "r2", created_at: iso(5 * day), title: "Quiet", overall_rating: 5, has_store_response: true },
      ],
    },
    [
      { id: "a1", status: "substantiation_requested", created_at: iso(4 * day), substantiation_requested_at: iso(1 * day), seller_review_id: "r9", reviewer: { display_name: "Rico T." } },
      { id: "a2", status: "dismissed", created_at: iso(9 * day), seller_review_id: "r8" },
    ],
    now,
  );
  assert.deepEqual(items.map((i) => `${i.kind}:${i.id}`), ["appeal:a1", "question:q1", "review:r1"]);
  const [appeal, question, review] = items;
  assert.equal(appeal.note, "Rico T. was asked for proof of purchase · 1 day ago");
  assert.equal(question.note, "Question · asked by Mara L. · 3 days ago");
  assert.equal(question.href, "/seller/s1/questions");
  assert.equal(review.note, "2★ review by Paolo D. · 2 days ago · no response");
  assert.equal(review.urgent, true);
  assert.equal(review.href, `/seller/s1/reviews?respond=${review.id}`);
  assert.equal(appeal.href, "/seller/s1/appeals");
});

test("small formatters", () => {
  assert.equal(greeting(now), "Good morning");
  assert.equal(greeting(Date.parse("2026-10-03T08:00:00Z")), "Good afternoon");
  assert.equal(greeting(Date.parse("2026-10-03T12:00:00Z")), "Good evening");
  assert.equal(pct(0.864), "86%");
  assert.equal(pct(null), "—");
  assert.equal(monthLabel("2026-09"), "Sep");
  assert.equal(agoShort(iso(20 * 3600_000), now), "20 h ago");
  assert.equal(agoShort(iso(8 * day), now), "1 week ago");
});

test("notification kinds land in the panel's tabs", () => {
  assert.equal(tabOf("store_review_new"), "reviews");
  assert.equal(tabOf("store_question_new"), "questions");
  assert.equal(tabOf("case_message"), "appeals");
  assert.equal(tabOf("seller_appeal_decided"), "appeals");
  assert.equal(tabOf("seller_claim_approved"), null);
});

test("each tab asks the API for its own kinds", () => {
  assert.equal(notificationsQuery("all"), "/api/bff/api/v1/notifications?limit=30");
  assert.equal(notificationsQuery("appeals"), "/api/bff/api/v1/notifications?limit=30&kind=case_message&kind=seller_appeal_decided");
});

test("Waiting on you reads the oldest-first waiting_reviews, not the newest 30", () => {
  const newest = { id: "new", created_at: iso(1 * day), title: "New", overall_rating: 4, has_store_response: false };
  const oldest = { id: "old", created_at: iso(90 * day), title: "Old", overall_rating: 1, has_store_response: false };
  const items = waitingItems({ seller: { id: "s1" }, waiting_questions: [], reviews: [newest], waiting_reviews: [oldest] }, [], now);
  assert.deepEqual(items.map((i) => i.id), ["old"]);
  // An API from before waiting_reviews still fills the list from `reviews`.
  assert.deepEqual(waitingItems({ seller: { id: "s1" }, waiting_questions: [], reviews: [newest] }, [], now).map((i) => i.id), ["new"]);
});

test("See all N counts every waiting item from the API's totals", () => {
  const appeals = [
    { id: "a1", status: "open", created_at: iso(day), seller_review_id: "r1" },
    { id: "a2", status: "substantiation_requested", created_at: iso(day), seller_review_id: "r2" },
    { id: "a3", status: "upheld", created_at: iso(day), seller_review_id: "r3" },
  ];
  assert.equal(waitingTotal({ unanswered_questions: 25, analytics: { reviews_awaiting_response: 40 } }, appeals, 42), 67);
  // No totals from the API: fall back to what is drawn, never invent a number.
  assert.equal(waitingTotal({ unanswered_questions: 0, analytics: null }, appeals, 3), 3);
});

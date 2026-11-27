import assert from "node:assert/strict";
import { test } from "node:test";

import {
  appealLabel,
  categoryLabel,
  isOpen,
  statusLabel,
  waitingOnTeam,
  SUPPORT_CATEGORIES,
  validateSupportDraft,
} from "../../components/sellers/support-model.ts";

test("every API category has a label, and an unknown one still reads", () => {
  const values = SUPPORT_CATEGORIES.map((c) => c.value);
  assert.deepEqual(values, [
    "report_review",
    "takedown_investigation",
    "fake_review_dispute",
    "account_claim",
    "listing_product",
    "general",
  ]);
  assert.equal(categoryLabel("fake_review_dispute"), "Dispute a review I believe is fake");
  assert.equal(categoryLabel("brand_new_thing"), "brand new thing");
});

test("statuses read as words; only open and in-review keep the seller waiting", () => {
  assert.equal(statusLabel("in_review"), "In review");
  assert.equal(statusLabel("resolved"), "Resolved");
  assert.equal(isOpen("open"), true);
  assert.equal(isOpen("in_review"), true);
  assert.equal(isOpen("resolved"), false);
  assert.equal(isOpen("rejected"), false);
});

test("the draft check mirrors the API's length rules", () => {
  assert.match(validateSupportDraft({ subject: "Hi", message: "long enough message" }), /subject/);
  assert.match(validateSupportDraft({ subject: "A subject", message: "   short  " }), /10 characters/);
  assert.match(validateSupportDraft({ subject: "A subject", message: "x".repeat(4001) }), /4,000/);
  assert.equal(validateSupportDraft({ subject: "A subject", message: "Ten or more characters." }), null);
});

test("the store's flag states read plainly", () => {
  assert.equal(appealLabel("substantiation_requested"), "reviewer asked for proof");
  assert.equal(appealLabel("upheld"), "upheld");
  assert.equal(appealLabel("something_new"), "something new");
});

test("waiting for the seller: their turn, still active, not the team's work (MQA-022/024)", () => {
  assert.equal(statusLabel("waiting_for_seller"), "Waiting on you");
  assert.equal(statusLabel("waiting_for_seller", "staff"), "Waiting for seller");
  assert.equal(statusLabel("in_review", "staff"), "In review");
  assert.equal(isOpen("waiting_for_seller"), true);
  assert.equal(waitingOnTeam("waiting_for_seller"), false);
  assert.equal(waitingOnTeam("in_review"), true);
  assert.equal(categoryLabel("store_change"), "A store change");
});

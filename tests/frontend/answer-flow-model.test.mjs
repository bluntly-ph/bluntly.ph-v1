import assert from "node:assert/strict";
import test from "node:test";

import { EMPTY_DRAFT, answerPayload, experienceLine } from "../../components/qa/answer-flow-model.ts";

test("experience: usage, expectation and the optional note on one line", () => {
  assert.equal(experienceLine({ usage: "1–6 months", expectation: "About the same", note: "" }), "Used it 1–6 months · About as expected");
  assert.equal(experienceLine({ usage: "I returned it", expectation: "Worse", note: " Loud. " }), "Returned it · Worse than expected · Loud.");
  assert.equal(experienceLine({ usage: null, expectation: null, note: "" }), null);
});

test("payload: the parts the API takes, nothing invented", () => {
  const p = answerPayload({
    ...EMPTY_DRAFT,
    text: "  Nine hours on medium. ",
    pros: "Worth it!\nEasy to use",
    cons: "",
    verdict: "on_sale",
    fit: "It depends",
    rating: 4.5,
    photoUrl: "https://x/review-photos/u/1.jpg",
  });
  assert.deepEqual(p, {
    body: "Nine hours on medium.",
    experience: null,
    good: "Worth it!; Easy to use",
    bad: null,
    verdict: "on_sale",
    verdict_reason: null,
    right_for_you: "It depends",
    rating: "4.5",
    photo_urls: ["https://x/review-photos/u/1.jpg"],
  });
  assert.equal(answerPayload({ ...EMPTY_DRAFT, text: "x", rating: 0 }).rating, null);
});

test("It depends: the reason rides on right_for_you and reads back", async () => {
  const { fitValue, splitFit, fitDetailRemaining } = await import("../../components/qa/answer-flow-model.ts");
  assert.equal(fitValue({ fit: "It depends", fitDetail: "  if you commute\n daily " }), "It depends: if you commute daily");
  assert.equal(fitValue({ fit: "It depends", fitDetail: "" }), "It depends");
  // A reason typed before switching to another fit is not sent.
  assert.equal(fitValue({ fit: "No, look elsewhere", fitDetail: "left over" }), "No, look elsewhere");
  assert.equal(fitValue({ fit: null, fitDetail: "x" }), null);
  assert.deepEqual(splitFit("It depends: if you commute daily"), { choice: "It depends", detail: "if you commute daily" });
  assert.deepEqual(splitFit("It depends"), { choice: "It depends", detail: null });
  assert.deepEqual(splitFit("Yes, if you walk a lot."), { choice: "Yes, if you walk a lot.", detail: null });
  assert.deepEqual(splitFit(null), { choice: null, detail: null });
  assert.equal(fitDetailRemaining(""), 15);
  assert.equal(fitDetailRemaining("   twelve chars  "), 15 - "twelve chars".length);
  assert.equal(fitDetailRemaining("a".repeat(20)), 0);
  assert.equal(answerPayload({ ...EMPTY_DRAFT, text: "x", fit: "It depends", fitDetail: "only for short trips" }).right_for_you, "It depends: only for short trips");
});

test("Why? rides with a verdict only", () => {
  assert.equal(answerPayload({ ...EMPTY_DRAFT, text: "x", verdict: "yes", verdictReason: "  Lasts all day.  " }).verdict_reason, "Lasts all day.");
  assert.equal(answerPayload({ ...EMPTY_DRAFT, text: "x", verdict: "yes", verdictReason: "   " }).verdict_reason, null);
  assert.equal(answerPayload({ ...EMPTY_DRAFT, text: "x", verdict: null, verdictReason: "orphan" }).verdict_reason, null);
});

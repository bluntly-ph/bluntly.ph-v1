import assert from "node:assert/strict";
import test from "node:test";

import {
  ANSWER_STEPS,
  ASKABLE_REQUIREMENTS,
  answerStepBlocker,
  firstUnmetStep,
  requiredSteps,
  shownRequests,
  stepForServerParts,
  stepRequirementNote,
} from "../../components/qa/structured-question-model.ts";
import { splitQuestionBody } from "../../components/qa/ask-question-model.ts";

const WORDS = "Yes, but only with the 20,000 mAh one. It lasts all day.";
const EMPTY = { text: "", usage: null, expectation: null, pros: "", cons: "", verdict: null, fit: null, rating: null };
const MIN = { ...EMPTY, text: WORDS, rating: 4 };

test("the Ask picker offers Figma's four specifics, in order; Rating is not one", () => {
  assert.deepEqual(ASKABLE_REQUIREMENTS, ["Experience", "Pros & Cons", "Do you recommend this?", "Is this right for me?"]);
});

test("the answer steps are Figma's seven, in order", () => {
  assert.deepEqual(ANSWER_STEPS, ["words", "experience", "pros_cons", "verdict", "fit", "rating", "photo"]);
});

test("words and rating are always required; requested specifics add their steps", () => {
  assert.deepEqual([...requiredSteps([])].sort(), ["rating", "words"]);
  assert.deepEqual([...requiredSteps(["Experience", "Do you recommend this?"])].sort(), ["experience", "rating", "verdict", "words"]);
  // A legacy "Rating" request maps to the step that is required anyway.
  assert.deepEqual([...requiredSteps(["Rating"])].sort(), ["rating", "words"]);
});

test("Reviewer A asks for Experience and Verdict: B must give rating, experience and verdict", () => {
  const asked = ["Experience", "Do you recommend this?"];
  assert.equal(firstUnmetStep({ ...EMPTY, text: WORDS }, asked).step, "experience");
  assert.equal(firstUnmetStep({ ...MIN, usage: "1–6 months" }, asked).step, "experience"); // expectation missing
  assert.equal(firstUnmetStep({ ...MIN, usage: "1–6 months", expectation: "Better" }, asked).step, "verdict");
  assert.equal(firstUnmetStep({ ...MIN, usage: "1–6 months", expectation: "Better", verdict: "yes", rating: null }, asked).step, "rating");
  assert.equal(firstUnmetStep({ ...MIN, usage: "1–6 months", expectation: "Better", verdict: "yes" }, asked), null);
});

test("unrequested specifics never block", () => {
  for (const step of ["experience", "pros_cons", "verdict", "fit", "photo"]) {
    assert.equal(answerStepBlocker(step, EMPTY, []), null, step);
  }
  assert.equal(firstUnmetStep(MIN, []), null);
});

test("the rating is required even when nothing was requested", () => {
  assert.match(answerStepBlocker("rating", { ...MIN, rating: null }, []), /star rating/);
  assert.equal(firstUnmetStep({ ...MIN, rating: null }, []).index, 5);
});

test("pros & cons needs one of each; blank lines do not count", () => {
  const asked = ["Pros & Cons"];
  assert.ok(answerStepBlocker("pros_cons", { ...MIN, pros: "Light", cons: "" }, asked));
  assert.ok(answerStepBlocker("pros_cons", { ...MIN, pros: "\n \n", cons: "Loud" }, asked));
  assert.equal(answerStepBlocker("pros_cons", { ...MIN, pros: "Light", cons: "Loud" }, asked), null);
});

test("the fit and the words", () => {
  assert.ok(answerStepBlocker("fit", MIN, ["Is this right for me?"]));
  assert.equal(answerStepBlocker("fit", { ...MIN, fit: "Yes, it fits what you need" }, ["Is this right for me?"]), null);
  // "It depends" alone is not enough: Step 5.1 wants its reason (test below).
  assert.ok(answerStepBlocker("fit", { ...MIN, fit: "It depends" }, ["Is this right for me?"]));
  assert.ok(answerStepBlocker("words", { ...MIN, text: "too short" }, []));
});

test("a legacy free-form question requests nothing, and still answers", () => {
  const legacy = splitQuestionBody("Is it loud?\nI study in a library.");
  assert.deepEqual(legacy.requirements, []);
  assert.equal(firstUnmetStep(MIN, legacy.requirements), null);
  const old = splitQuestionBody("Is it loud?\n\nLooking for: Experience, Rating");
  assert.deepEqual(old.requirements, ["Experience", "Rating"]);
  assert.equal(firstUnmetStep(MIN, old.requirements).step, "experience");
});

test("a zero-star rating is not a rating", () => {
  assert.match(answerStepBlocker("rating", { ...MIN, rating: 0 }, []), /star rating/);
});

test("the counter says each step's required state, all seven steps kept", () => {
  const asked = ["Experience", "Do you recommend this?"];
  assert.deepEqual(
    ANSWER_STEPS.map((s) => stepRequirementNote(s, asked)),
    ["Required", "Required: they asked about this", "Added information", "Required: they asked about this", "Added information", "Required", "Added information"],
  );
  assert.deepEqual(
    ANSWER_STEPS.map((s) => stepRequirementNote(s, [])),
    ["Required", "Added information", "Added information", "Added information", "Added information", "Required", "Added information"],
  );
  // A legacy "Rating" request changes nothing: the rating is required anyway.
  assert.equal(stepRequirementNote("rating", ["Rating"]), "Required");
});

test("a server refusal returns to the first step it names", () => {
  assert.equal(stepForServerParts(["rating"]), 5);
  assert.equal(stepForServerParts(["experience", "verdict"]), 1);
  assert.equal(stepForServerParts(["pros_cons"]), 2);
  assert.equal(stepForServerParts(["fit"]), 4);
  assert.equal(stepForServerParts(["something_new", "verdict"]), 3);
  assert.equal(stepForServerParts(["something_new"]), null);
  assert.equal(stepForServerParts(undefined), null);
  assert.equal(stepForServerParts("rating"), null);
});

test("list and detail chips: requested specifics only, never Rating, none on legacy", () => {
  assert.deepEqual(shownRequests(splitQuestionBody("Q?\n\nLooking for: Experience, Do you recommend this?").requirements), [
    "Experience",
    "Do you recommend this?",
  ]);
  assert.deepEqual(shownRequests(splitQuestionBody("Q?\n\nLooking for: Experience, Rating").requirements), ["Experience"]);
  assert.deepEqual(shownRequests(splitQuestionBody("Q?\n\nLooking for: Rating").requirements), []);
  assert.deepEqual(shownRequests(splitQuestionBody("Is it loud?\nI study in a library.").requirements), []);
  // Shown in the Ask picker's order, whatever order the line had.
  assert.deepEqual(shownRequests(["Is this right for me?", "Experience"]), ["Experience", "Is this right for me?"]);
});

test("It depends needs its 15-character reason, requested or not (Figma Step 5.1)", async () => {
  const { answerStepBlocker } = await import("../../components/qa/structured-question-model.ts");
  const base = { text: "", usage: null, expectation: null, pros: "", cons: "", verdict: null, fit: "It depends", rating: null };
  assert.match(answerStepBlocker("fit", { ...base, fitDetail: "short" }, []), /what it depends on/);
  assert.match(answerStepBlocker("fit", { ...base, fitDetail: "short" }, ["Is this right for me?"]), /what it depends on/);
  assert.equal(answerStepBlocker("fit", { ...base, fitDetail: "only for day trips" }, ["Is this right for me?"]), null);
  // Another fit needs no reason; an unrequested, unchosen fit never blocks.
  assert.equal(answerStepBlocker("fit", { ...base, fit: "Yes, it fits what you need", fitDetail: "" }, ["Is this right for me?"]), null);
  assert.equal(answerStepBlocker("fit", { ...base, fit: null }, []), null);
});

// Owner correction 2026-10-06: the asker's "Looking for" chips ARE the
// question's requirements; nothing else becomes required because of the question.
const CERAVE = "How long does a single bottle of this cleanser lasts?\n\nLooking for: Experience, Pros & Cons, Do you recommend this?";
const BASE = new Set(["words", "rating"]); // every answer, whatever was asked
const questionSteps = (requested) => [...requiredSteps(requested)].filter((s) => !BASE.has(s)).sort();

test("the CeraVe question requires exactly Experience, Pros & Cons and Do you recommend this?", () => {
  const { text, requirements } = splitQuestionBody(CERAVE);
  assert.equal(text, "How long does a single bottle of this cleanser lasts?");
  assert.deepEqual(requirements, ["Experience", "Pros & Cons", "Do you recommend this?"]);
  // The chips the question page shows are the same three.
  assert.deepEqual(shownRequests(requirements), requirements);
  assert.deepEqual(questionSteps(requirements), ["experience", "pros_cons", "verdict"]);

  // Each requested section blocks until answered...
  const ready = { ...MIN, usage: "1–6 months", expectation: "About the same", pros: "Gentle", cons: "Runs out fast", verdict: "yes" };
  assert.equal(firstUnmetStep(ready, requirements), null);
  assert.match(answerStepBlocker("experience", { ...ready, usage: null }, requirements), /experience/);
  assert.match(answerStepBlocker("pros_cons", { ...ready, cons: "" }, requirements), /pros and cons/);
  assert.match(answerStepBlocker("verdict", { ...ready, verdict: null }, requirements), /recommend/);
  assert.equal(firstUnmetStep({ ...ready, usage: null }, requirements).step, "experience");
  assert.equal(firstUnmetStep({ ...ready, pros: "" }, requirements).step, "pros_cons");
  assert.equal(firstUnmetStep({ ...ready, verdict: null }, requirements).step, "verdict");

  // ...and the section the asker did not pick stays skippable.
  assert.equal(answerStepBlocker("fit", { ...ready, fit: null }, requirements), null);
  assert.equal(answerStepBlocker("photo", ready, requirements), null);
  assert.deepEqual(
    ANSWER_STEPS.map((s) => stepRequirementNote(s, requirements)),
    ["Required", "Required: they asked about this", "Required: they asked about this",
     "Required: they asked about this", "Added information", "Required", "Added information"],
  );
  for (const step of ["experience", "pros_cons", "verdict"]) {
    assert.equal(stepRequirementNote(step, requirements), "Required: they asked about this", step);
  }
});

test("only what the asker picked becomes a question requirement", () => {
  const cases = [
    [["Experience"], ["experience"]],
    [["Pros & Cons"], ["pros_cons"]],
    [["Experience", "Do you recommend this?"], ["experience", "verdict"]],
    [["Experience", "Pros & Cons", "Do you recommend this?"], ["experience", "pros_cons", "verdict"]],
    [[], []],
  ];
  for (const [picked, steps] of cases) {
    // Through the stored body and back, exactly as the pages read it.
    const body = picked.length ? `Is it any good for travel?\n\nLooking for: ${picked.join(", ")}` : "Is it any good for travel?";
    const { requirements } = splitQuestionBody(body);
    assert.deepEqual(requirements, picked, body);
    assert.deepEqual(questionSteps(requirements), steps, body);
    for (const step of ["experience", "pros_cons", "verdict", "fit"]) {
      const blocks = answerStepBlocker(step, MIN, requirements) !== null;
      assert.equal(blocks, steps.includes(step), `${step} for ${JSON.stringify(picked)}`);
    }
  }
});

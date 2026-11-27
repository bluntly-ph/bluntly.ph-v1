import assert from "node:assert/strict";
import test from "node:test";

import { countLine } from "../../components/site/page-numbers-model.ts";

/** MQA-036/037: the total first, then where the reader is. */
test("count line", () => {
  assert.equal(countLine(214, ["review", "reviews"], 3, 9), "214 reviews · page 3 of 9");
  assert.equal(countLine(1, ["review", "reviews"], 1, 1), "1 review");
  assert.equal(countLine(5000, ["review", "reviews"], 99, 42), "5,000 reviews · page 42 of 42");
});

import assert from "node:assert/strict";
import test from "node:test";

import { clampPage, pageCount, pageSize, pageWindow, shownRange } from "../../components/console/pagination-model.ts";

test("the frame's first page: 1 2 3 … 129", () => {
  assert.deepEqual(pageWindow(1, 129), [1, 2, 3, "gap", 129]);
});

test("a middle page keeps its neighbours and both ends", () => {
  assert.deepEqual(pageWindow(50, 129), [1, "gap", 49, 50, 51, "gap", 129]);
});

test("the last page mirrors the first", () => {
  assert.deepEqual(pageWindow(129, 129), [1, "gap", 127, 128, 129]);
});

test("a single left-out page is shown rather than a gap", () => {
  assert.deepEqual(pageWindow(4, 9), [1, 2, 3, 4, 5, "gap", 9]);
});

test("few pages show them all; an empty list is one page", () => {
  assert.deepEqual(pageWindow(2, 3), [1, 2, 3]);
  assert.equal(pageCount(0, 10), 1);
  assert.deepEqual(pageWindow(1, pageCount(0, 10)), [1]);
});

test("production's 23 members at 10 a page are three pages, not one long list", () => {
  assert.equal(pageCount(23, 10), 3);
  assert.deepEqual(shownRange(3, 10, 23), { first: 21, last: 23 });
  assert.deepEqual(shownRange(1, 10, 0), { first: 0, last: 0 });
});

test("a stale page past the end is clamped; only offered sizes are accepted", () => {
  assert.equal(clampPage(9, 23, 10), 3);
  assert.equal(clampPage(0, 23, 10), 1);
  assert.equal(clampPage(Number.NaN, 23, 10), 1);
  assert.equal(pageSize("25"), 25);
  assert.equal(pageSize("1000"), 10);
  assert.equal(pageSize(undefined), 10);
});

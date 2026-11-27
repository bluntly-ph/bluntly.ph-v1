import assert from "node:assert/strict";
import test from "node:test";

import {
  isFiltered,
  PRICE_DEFAULT_SORT,
  PRICE_FILTERS,
  priceFilterQuery,
  waitingLine,
} from "../../components/admin/prices/prices-model.ts";

/**
 * The admin Prices screen: MQA-043 (every waiting price reachable, the real
 * total in the header), MQA-007 (a sort control), MQA-042 (filters).
 */

test("the header says the real backlog, and what a filter matched of it", () => {
  assert.equal(waitingLine(164, 164, false), "164 prices waiting.");
  assert.equal(waitingLine(1, 1, false), "1 price waiting.");
  assert.equal(waitingLine(12, 164, true), "12 of 164 prices waiting match.");
  assert.equal(waitingLine(1, 164, true), "1 of 164 prices waiting matches.");
  assert.equal(waitingLine(1284, 1284, false), "1,284 prices waiting.");
});

test("only values the API accepts are forwarded; the default order is left out", () => {
  const q = priceFilterQuery({
    sort: "newest", platform: "lazada", source: "review", held: "outlier", mine: "hide",
    q: "  electric fan ", product: "6f1c2a1e-0d6b-4d7e-9a43-0c7f6b3e2a11",
  });
  assert.equal(q.get("sort"), "newest");
  assert.equal(q.get("platform"), "lazada");
  assert.equal(q.get("source"), "review");
  assert.equal(q.get("held"), "outlier");
  assert.equal(q.get("mine"), "hide");
  assert.equal(q.get("q"), "electric fan");
  assert.equal(q.get("product_id"), "6f1c2a1e-0d6b-4d7e-9a43-0c7f6b3e2a11");

  const junk = priceFilterQuery({ sort: "random", platform: "ebay", held: "maybe", mine: "only", product: "1 OR 1=1" });
  assert.equal(junk.toString(), "", "a hand-edited URL narrows to nothing rather than a 422");
  assert.equal(priceFilterQuery({ sort: PRICE_DEFAULT_SORT }).toString(), "");
});

test("an order is not a filter", () => {
  assert.equal(isFiltered({ sort: "newest" }), false);
  assert.equal(isFiltered({ platform: "shopee" }), true);
  assert.equal(isFiltered({ q: "   " }), false);
});

test("the filter menu offers marketplace, source, why it waits, and hiding my own", () => {
  assert.deepEqual(PRICE_FILTERS.map((f) => f.key), ["platform", "source", "held", "mine"]);
});

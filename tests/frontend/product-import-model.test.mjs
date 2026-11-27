import assert from "node:assert/strict";
import test from "node:test";

import {
  attachLines,
  canAttach,
  importLabel,
  rowNote,
  summaryChips,
} from "../../components/admin/products/product-import-model.ts";

const row = (over) => ({
  line: 2, outcome: "new", name: "Acme Fan", category: "audio", errors: [], product_id: null,
  existing_name: null, duplicate_of_line: null, matched_by: null, attach_adds: [], ...over,
});

test("only a matched row with something to add can be attached", () => {
  assert.equal(canAttach(row({ outcome: "exists", attach_adds: ["alias “x”"] })), true);
  assert.equal(canAttach(row({ outcome: "exists", attach_adds: [] })), false);
  assert.equal(canAttach(row({ outcome: "conflict", attach_adds: ["listing y"] })), false);
  assert.equal(canAttach(row({ outcome: "new" })), false);
});

test("a choice the new preview no longer allows is dropped", () => {
  const rows = [
    row({ line: 2, outcome: "exists", attach_adds: ["listing a"] }),
    row({ line: 3, outcome: "exists", attach_adds: [] }),
    row({ line: 4, outcome: "new" }),
  ];
  assert.deepEqual(attachLines(rows, new Set([2, 3, 4, 9])), [2]);
});

test("each row says why it is what it is", () => {
  assert.equal(rowNote(row({ outcome: "error", errors: ["Brand is required."] })), "Brand is required.");
  assert.equal(rowNote(row({ outcome: "exists", existing_name: "Base Fan", matched_by: "listing" })),
    "Matches “Base Fan” by listing");
  assert.equal(rowNote(row({ outcome: "duplicate", duplicate_of_line: 3 })), "Same as row 3");
  assert.equal(rowNote(row({ outcome: "new" })), null);
});

test("the Import button says what applying will do", () => {
  assert.equal(importLabel(0, 0), "Nothing to import");
  assert.equal(importLabel(3, 0), "Import 3 new");
  assert.equal(importLabel(0, 2), "Attach 2");
  assert.equal(importLabel(3, 2), "Import 3 new · attach 2");
});

test("the summary counts what happened and leaves out zeros", () => {
  const applied = summaryChips({ applied: true, counts: { total: 6, imported: 2, attached: 1, skipped: 2, invalid: 1, failed: 0 } });
  assert.deepEqual(applied.map((c) => c.label), ["6 rows", "2 added", "1 attached", "2 skipped", "1 can't import"]);
  const preview = summaryChips({ applied: false, counts: { total: 4, new: 1, exists: 1, duplicate: 1, conflict: 1, invalid: 0 } });
  assert.deepEqual(preview.map((c) => c.label), ["4 rows", "1 new", "1 match a product", "1 repeated", "1 conflict"]);
});

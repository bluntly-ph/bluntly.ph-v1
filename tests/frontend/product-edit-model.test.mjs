import assert from "node:assert/strict";
import test from "node:test";

import { blocker, partsFrom, partsPayload, savesAs, specsPayload } from "../../components/admin/products/product-edit-model.ts";

test("saves as: brand, line, variant, type, then in-name specs", () => {
  const parts = [
    { kind: "line", value: "Redmi Note 13 Pro" },
    { kind: "variant", value: "5G" },
  ];
  const specs = [
    { label: "RAM", value: "8GB", in_name: true },
    { label: "Storage", value: "256GB", in_name: true },
    { label: "Display", value: "6.67in", in_name: false },
  ];
  assert.equal(savesAs("Xiaomi", parts, specs), "Xiaomi Redmi Note 13 Pro 5G 8GB 256GB");
  assert.equal(savesAs(" Aula ", [{ kind: "type", value: "Keyboard" }, { kind: "line", value: "F75" }], []), "Aula F75 Keyboard");
});

test("parts round-trip to the API's fields", () => {
  assert.deepEqual(partsPayload([{ kind: "line", value: " F75 " }, { kind: "type", value: "Keyboard" }]), {
    product_line: "F75",
    key_spec: null,
    descriptor: "Keyboard",
  });
  assert.deepEqual(partsFrom({ line: "F75", key_spec: null, descriptor: "Keyboard" }), [
    { kind: "line", value: "F75" },
    { kind: "type", value: "Keyboard" },
  ]);
});

test("blank specs are dropped; what blocks a save is named", () => {
  assert.deepEqual(specsPayload([{ label: "Battery", value: "", in_name: false }, { label: " RAM ", value: "8GB", in_name: true }]), [
    { label: "RAM", value: "8GB", in_name: true },
  ]);
  assert.equal(blocker("", [], null), "Add the brand.");
  assert.equal(blocker("Aula", [{ kind: "line", value: "" }], null), "Add the product line.");
  assert.equal(blocker("Aula", [{ kind: "line", value: "F75" }], null), "Choose a category.");
  assert.equal(blocker("Aula", [{ kind: "line", value: "F75" }], "gaming"), null);
});

test("an older product's line falls back to its name without the brand", () => {
  assert.deepEqual(partsFrom({ canonical_name: "Aula F75 Keyboard", brand: "Aula" }), [{ kind: "line", value: "F75 Keyboard" }]);
  assert.deepEqual(partsFrom({ canonical_name: "Life9 Fan", brand: null }), [{ kind: "line", value: "Life9 Fan" }]);
});

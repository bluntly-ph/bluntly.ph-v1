import assert from "node:assert/strict";
import test from "node:test";

import { emailLooksValid, maskEmail } from "../../components/account/email-change-model.ts";

/** Verified email change (backend 0084). */

test("masking keeps the first letter and the domain", () => {
  assert.equal(maskEmail("jun.r@gmail.com"), "j••••@gmail.com");
  assert.equal(maskEmail("a@b.ph"), "a•••@b.ph");
  assert.equal(maskEmail("not-an-address"), "not-an-address");
});

test("a light address check before asking the API", () => {
  assert.equal(emailLooksValid("new@store.ph"), true);
  assert.equal(emailLooksValid("  new@store.ph "), true);
  for (const bad of ["", "new", "new@", "@store.ph", "new@store", "new @store.ph", "a@b@c.ph"]) {
    assert.equal(emailLooksValid(bad), false, bad);
  }
});

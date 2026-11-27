import assert from "node:assert/strict";
import test from "node:test";

import { LISTING_NOTE, listingLink } from "../../components/review/listing-link-model.ts";

/**
 * QA-006: a review with no affiliate link still leads to the product, through
 * its plain marketplace listing, labelled as a link that earns nobody.
 */

test("a marketplace listing is named for its marketplace", () => {
  assert.deepEqual(listingLink("https://shopee.ph/x-i.1.2", "shopee"), {
    href: "https://shopee.ph/x-i.1.2",
    label: "View on Shopee",
  });
  assert.equal(listingLink("https://www.lazada.com.ph/p/1", "lazada")?.label, "View on Lazada");
});

test("an unnamed marketplace gets a plain label", () => {
  assert.equal(listingLink("https://example.ph/item", "other")?.label, "View the listing");
});

test("nothing is linked without an https URL", () => {
  assert.equal(listingLink(null, "shopee"), null);
  assert.equal(listingLink("", "shopee"), null);
  assert.equal(listingLink("http://shopee.ph/x", "shopee"), null);
  assert.equal(listingLink("javascript:alert(1)", "shopee"), null);
});

test("the note says it is not an affiliate link", () => {
  assert.match(LISTING_NOTE, /not an affiliate link/i);
});

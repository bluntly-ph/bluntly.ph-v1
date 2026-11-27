import assert from "node:assert/strict";
import test from "node:test";

import {
  copyLabel,
  destinationHref,
  safeSharePath,
  SHARE_DESTINATIONS,
  shareDestinations,
  shareUrl,
} from "../../components/share/share-model.ts";

/**
 * QA-024: Share opens the app's own sheet (copy link first, the system sheet
 * only as "More options"). What it shares is always a page of this site.
 */

test("a review path becomes an absolute link on this site", () => {
  assert.equal(shareUrl("https://www.bluntly.ph", "/reviews/abc"), "https://www.bluntly.ph/reviews/abc");
  assert.equal(
    shareUrl("https://www.bluntly.ph", "/reviews/abc#comment-1"),
    "https://www.bluntly.ph/reviews/abc#comment-1",
  );
});

test("nothing can turn a share into a link off the site", () => {
  for (const bad of ["https://evil.example", "//evil.example/x", "/\\evil.example", "javascript:alert(1)",
                     "", null, undefined, "/ spaced", "/tab\there"]) {
    assert.equal(safeSharePath(bad), "/", String(bad));
    assert.equal(new URL(shareUrl("https://www.bluntly.ph", bad)).origin, "https://www.bluntly.ph");
  }
});

test("the copy button says what happened, including how to recover from a refusal", () => {
  assert.equal(copyLabel("idle"), "Copy link");
  assert.equal(copyLabel("copied"), "Link copied");
  assert.match(copyLabel("failed"), /select the link/);
});

test("Figma's destinations, less the ones the web cannot honestly offer (QA-024)", () => {
  const ids = SHARE_DESTINATIONS.map((d) => d.id);
  assert.deepEqual(ids, ["facebook", "messenger", "reddit", "x", "viber", "telegram", "whatsapp"]);
  // No Instagram (no web share address) and no Bookmark (feature omitted by decision).
  assert.ok(!ids.includes("instagram") && !ids.includes("bookmark"));
  // App links only where a touch device can answer them.
  assert.deepEqual(shareDestinations(false).map((d) => d.id), ["facebook", "reddit", "x", "telegram", "whatsapp"]);
  assert.equal(shareDestinations(true).length, 7);
});

test("every destination carries this site's link, encoded, to a fixed host", () => {
  const url = shareUrl("https://www.bluntly.ph", "/reviews/abc#comment-1");
  const title = 'A "fan" & more <script>';
  const hosts = {
    facebook: "https://www.facebook.com/sharer/sharer.php?",
    messenger: "fb-messenger://share/?",
    reddit: "https://www.reddit.com/submit?",
    x: "https://x.com/intent/post?",
    viber: "viber://forward?",
    telegram: "https://t.me/share/url?",
    whatsapp: "https://wa.me/?",
  };
  for (const d of SHARE_DESTINATIONS) {
    const href = destinationHref(d.id, url, title);
    assert.ok(href.startsWith(hosts[d.id]), d.id);
    assert.ok(href.includes(encodeURIComponent(url)) || href.includes(encodeURIComponent(`${title} ${url}`)), d.id);
    // Nothing raw that could end the query or open markup.
    const query = href.slice(hosts[d.id].length);
    assert.ok(!/[<>"# ]/.test(query), `${d.id}: ${query}`);
  }
});

test("a hostile path still shares only this site through every destination", () => {
  const url = shareUrl("https://www.bluntly.ph", "//evil.example/x");
  for (const d of SHARE_DESTINATIONS) {
    assert.ok(destinationHref(d.id, url, "t").includes(encodeURIComponent("https://www.bluntly.ph/")));
    assert.ok(!destinationHref(d.id, url, "t").includes("evil.example"));
  }
});

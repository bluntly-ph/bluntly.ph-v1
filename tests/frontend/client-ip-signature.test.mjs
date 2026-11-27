import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  BFF_ONLY_HEADERS,
  edgeClientIp,
  signClientIp,
  signedClientIpHeaders,
} from "../../lib/client-ip-signature.ts";

/**
 * The BFF's signed client IP (QA 2026-09-29). The API verifies the same
 * construction in backend/app/core/client_ip.py; this vector was produced by
 * that Python function, so the two cannot drift apart unnoticed.
 */

test("the signature matches the API's own construction", () => {
  assert.equal(
    signClientIp("203.0.113.7", 1790000000, "test-secret"),
    "1bac6f685f47734b8b27fe3ba664d4b5d08e7a22a771949f79c965998ffaabf8",
  );
});

test("the edge's address is read only on Vercel, where the edge writes it", () => {
  const h = new Headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" });
  assert.equal(edgeClientIp(h, true), "203.0.113.7");
  assert.equal(edgeClientIp(h, false), null);           // anywhere else a client wrote it
  const vercel = new Headers({ "x-vercel-forwarded-for": "2001:db8::1", "x-forwarded-for": "1.2.3.4" });
  assert.equal(edgeClientIp(vercel, true), "2001:db8::1");
});

test("anything that is not an address is dropped", () => {
  for (const bad of ["not-an-ip", "999.1.1.1", "", "<script>"]) {
    assert.equal(edgeClientIp(new Headers({ "x-forwarded-for": bad }), true), null);
  }
});

test("the browser cannot pre-set the headers only the BFF writes", () => {
  assert.deepEqual(
    [...BFF_ONLY_HEADERS].sort(),
    ["x-bluntly-bff", "x-bluntly-client-ip", "x-bluntly-client-ip-at", "x-bluntly-client-ip-signature"],
  );
});

test("the signed headers carry the address, the time and the API's signature", () => {
  assert.deepEqual(signedClientIpHeaders("203.0.113.7", "test-secret", 1790000000), {
    "x-bluntly-client-ip": "203.0.113.7",
    "x-bluntly-client-ip-at": "1790000000",
    "x-bluntly-client-ip-signature":
      "1bac6f685f47734b8b27fe3ba664d4b5d08e7a22a771949f79c965998ffaabf8",
  });
});

/**
 * Security review S1 (2026-10-22): server-side calls forward the visitor's
 * signed address so the API's rate limits count visitors, not the frontend.
 * A per-visitor header on a fetch that lands in the shared Data Cache would
 * split or poison that cache, so it must only ever ride uncached calls.
 */
test("the API client signs the visitor's address only on calls it cannot cache", () => {
  const src = readFileSync(new URL("../../lib/api/client.ts", import.meta.url), "utf8");
  const uses = src.match(/visitorHeaders\(\)/g) ?? [];
  assert.equal(uses.length, 2, "visitorHeaders is defined once and called once");
  assert.match(
    src,
    /if \(!isCacheableCall\(options\)\) \{\s*init\.headers = \{[^}]*\.\.\.\(await visitorHeaders\(\)\)/,
  );
  // The cacheable rule is the same one buildInit uses for `next.revalidate`.
  assert.match(src, /\(options\.method \?\? "GET"\) === "GET" &&\s*!options\.token &&\s*options\.revalidate !== undefined/);
  assert.match(src, /options\.revalidate !== undefined && !options\.token/);
});

test("the traffic beacon carries the proxy's secret and the visitor's signed address", () => {
  const src = readFileSync(new URL("../../lib/traffic-beacon.ts", import.meta.url), "utf8");
  assert.match(src, /process\.env\.TRAFFIC_BEACON_SECRET/);
  assert.match(src, /headers\["x-traffic-key"\] = key/);
  assert.match(src, /signedClientIpHeaders\(ip, signingSecret\)/);
});

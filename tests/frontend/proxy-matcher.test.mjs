import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

/**
 * Which requests the proxy (proxy.ts) runs on.
 *
 * Every request the matcher admits is a billed function invocation, so it
 * must admit page routes only. `/api/*` was admitted until 2026-10-22: each
 * client fetch through the BFF (including every tick of the live message and
 * count polls) paid for a proxy pass that could do nothing — no API path is
 * protected or auth-only, and the traffic beacon refuses to count them.
 *
 * Asserted at the source, the same way return-path.test.mjs pins the proxy's
 * `?next=`; the end-to-end half is e2e/route-guards.spec.ts.
 */

const PROXY = readFileSync(new URL("../../proxy.ts", import.meta.url), "utf8").replace(/\r/g, "");

function matcherSource() {
  const found = /source:\s*"((?:[^"\\]|\\.)*)"/.exec(PROXY);
  assert.ok(found, "proxy.ts has a matcher `source`");
  // Undo the TypeScript string escaping to get the pattern Next compiles.
  return JSON.parse(`"${found[1]}"`);
}

const matcher = new RegExp(`^${matcherSource()}$`);
const runs = (path) => matcher.test(path);

test("the proxy still runs on every page route, gated or not", () => {
  for (const path of [
    "/",
    "/feed",
    "/search",
    "/questions",
    "/profile",
    "/profile/edit",
    "/admin/review-queue",
    "/messages",
    "/login",
    "/welcome",
    "/reviews/new",
    "/reviews/0f8fad5b-d9cb-469f-a165-70867728950e",
    "/questions/abc/answer",
    "/sellers/acme/dashboard",
  ]) {
    assert.ok(runs(path), `${path} must meet the proxy`);
  }
});

test("the proxy never runs on API routes", () => {
  for (const path of [
    "/api/bff/api/v1/notifications/unread-count",
    "/api/bff/api/v1/cases/seller/123/messages",
    "/api/telemetry",
  ]) {
    assert.ok(!runs(path), `${path} must not meet the proxy`);
  }
});

test("the proxy never runs on static files or crawler files", () => {
  for (const path of [
    "/_next/static/chunks/main.js",
    "/_next/image",
    "/favicon.ico",
    "/robots.txt",
    "/sitemap.xml",
    "/bluntly-logo.svg",
    "/mascots/happy.png",
    "/figma/hero.webp",
  ]) {
    assert.ok(!runs(path), `${path} must not meet the proxy`);
  }
});

test("no gated or auth-only route lives under /api", () => {
  const access = readFileSync(new URL("../../lib/route-access.ts", import.meta.url), "utf8");
  assert.ok(!/["'`]\/api/.test(access), "lib/route-access.ts must not list an /api path");
});

const CONTENT_PAGES = [
  "/about",
  "/articles",
  "/contact",
  "/faqs",
  "/guidelines",
  "/how-it-works",
  "/legal",
  "/privacy",
  "/terms",
];

test("the static content pages no longer meet the proxy", () => {
  // 2026-10-22: nothing there is gated or counted as a view, so the proxy
  // was a second function call per hit for a beacon nobody reads per page.
  for (const path of CONTENT_PAGES) {
    assert.ok(!runs(path), `${path} must not meet the proxy`);
    assert.ok(!runs(`${path}/`), `${path}/ must not meet the proxy`);
  }
});

test("only those exact paths are skipped", () => {
  for (const path of ["/aboutus", "/terms-and-more", "/privacy/x", "/legalese", "/faq"]) {
    assert.ok(runs(path), `${path} must still meet the proxy`);
  }
});

test("every page whose views count, and every gated or auth-only path, still meets it", async () => {
  const { PROTECTED, AUTH_ONLY } = await import("../../lib/route-access.ts");
  for (const path of ["/", "/feed", "/reviews/0f8fad5b-d9cb-469f-a165-70867728950e"]) {
    assert.ok(runs(path), `${path} must meet the proxy`);
  }
  for (const prefix of [...PROTECTED, ...AUTH_ONLY]) {
    const path = prefix.endsWith("/") ? `${prefix}some-store` : prefix;
    assert.ok(runs(path), `${path} must meet the proxy`);
    assert.ok(!CONTENT_PAGES.includes(path), `${path} is both gated and skipped`);
  }
});

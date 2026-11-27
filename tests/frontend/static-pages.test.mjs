import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

/**
 * The content pages are static (built once, served from the CDN), and stay so.
 *
 * Until 2026-10-22 every page read the session through PageShell's getUser(),
 * so /terms ran a function on each of its ~70k hits in two weeks. One import of
 * lib/dal, lib/session or next/headers anywhere in a page's server tree turns
 * it back into a per-request render without any error, so this pins the tree
 * at the source. `npm run build` is the end-to-end check (the route table
 * marks them ○).
 */

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8").replace(/\r/g, "");
/** Code only: the files explain in comments what they must never call. */
const code = (path) =>
  read(path)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, "");

const CONTENT_PAGES = [
  "about",
  "articles",
  "contact",
  "faqs",
  "guidelines",
  "how-it-works",
  "legal",
  "privacy",
  "terms",
];

// What makes a page dynamic: the session, cookies, request headers.
const DYNAMIC = /from\s+["'](?:@\/lib\/dal|@\/lib\/session|next\/headers)["']|\bgetUser\(|\bcookies\(\)|\bheaders\(\)|searchParams/;

test("every content page uses the static shell, not PageShell", () => {
  for (const page of CONTENT_PAGES) {
    const source = code(`app/${page}/page.tsx`);
    assert.match(source, /from "@\/components\/site\/StaticPageShell"/, `${page} must use StaticPageShell`);
    assert.doesNotMatch(source, /from "@\/components\/site\/PageShell"/, `${page} must not use PageShell`);
    assert.doesNotMatch(source, DYNAMIC, `${page} must not read the session or the request`);
    // Build-time guard: prerender, and fail the build on any request-time API.
    assert.match(source, /^export const dynamic = "error";$/m, `${page} must declare dynamic = "error"`);
  }
});

test("the static shell and the browser-side account corner never read the session on the server", () => {
  for (const file of ["components/site/StaticPageShell.tsx", "components/site/SessionAccount.tsx", "lib/session-hint.ts"]) {
    assert.doesNotMatch(code(file), DYNAMIC, `${file} must stay static-safe`);
  }
  assert.match(read("components/site/StaticPageShell.tsx"), /account="session"/);
});

test("the signed-in hint is written and cleared with the session, and repaired by the proxy", () => {
  const session = read("lib/session.ts");
  assert.match(session, /cookieStore\.set\(SIGNED_IN_HINT/, "createSession sets the hint");
  assert.match(session, /cookieStore\.delete\(SIGNED_IN_HINT\)/, "destroySession clears the hint");
  assert.match(session, /httpOnly: true/, "the session cookie itself stays httpOnly");
  const proxy = read("proxy.ts");
  assert.match(proxy, /syncHint\(request, NextResponse\.next\(\), hasSession\)/);
  const hint = read("lib/session-hint.ts");
  assert.doesNotMatch(hint, /accessToken|getSessionToken/, "the hint never carries a credential");
  assert.match(hint, /randomUUID\(\)/, "the hint is a random value");
});

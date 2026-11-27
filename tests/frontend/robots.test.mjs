import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

/**
 * What robots.txt (app/robots.ts) tells crawlers.
 *
 * From Oct 3 to 19, 2026 AI crawlers made about 2.8M requests to /search, and
 * each one rendered the page and queried the database. The rules below are what
 * keep a refactor from silently reopening it.
 *
 * Asserted at the source, like proxy-matcher.test.mjs: app/robots.ts imports
 * through the `@/` alias, which plain Node cannot resolve.
 */

const ROBOTS = readFileSync(new URL("../../app/robots.ts", import.meta.url), "utf8").replace(/\r/g, "");
const SITEMAP_DOC = readFileSync(new URL("../../docs/SITEMAP.md", import.meta.url), "utf8");
const SITE_MAP = readFileSync(new URL("../../lib/site-map.ts", import.meta.url), "utf8");

/** The object literal of the rule whose userAgent starts with `agent`. */
function ruleFor(agent) {
  const start = ROBOTS.indexOf(`userAgent: ${agent}`);
  assert.ok(start >= 0, `a rule for ${agent} exists`);
  const open = ROBOTS.lastIndexOf("{", start);
  let depth = 0;
  for (let i = open; i < ROBOTS.length; i += 1) {
    if (ROBOTS[i] === "{") depth += 1;
    if (ROBOTS[i] === "}") depth -= 1;
    if (depth === 0) return ROBOTS.slice(open, i + 1);
  }
  throw new Error(`unterminated rule for ${agent}`);
}

function crawlerList() {
  const found = /const AI_TRAINING_CRAWLERS = \[([^\]]*)\]/.exec(ROBOTS);
  assert.ok(found, "app/robots.ts lists the AI training crawlers");
  return [...found[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

test("robots.ts uses the rules-array shape, one group per audience", () => {
  assert.match(ROBOTS, /rules:\s*\[/);
});

test("/search is disallowed for every crawler", () => {
  const star = ruleFor('"*"');
  assert.match(star, /disallow:\s*\[[^\]]*"\/search"/);
});

test("the existing disallows are all still there", () => {
  const star = ruleFor('"*"');
  for (const entry of ["...PROTECTED", "...AUTH_ONLY", '"/api/"', '"/r/"', '"/sellers/*/dashboard"']) {
    assert.ok(star.includes(entry), `"*" still disallows ${entry}`);
  }
  assert.match(star, /allow:\s*"\/"/);
});

test("every AI training crawler is disallowed site-wide", () => {
  const listed = crawlerList();
  for (const agent of [
    "GPTBot",
    "meta-externalagent",
    "CCBot",
    "ClaudeBot",
    "anthropic-ai",
    "Bytespider",
    "PerplexityBot",
    "Google-Extended",
  ]) {
    assert.ok(listed.includes(agent), `${agent} is listed`);
  }
  const group = ruleFor("AI_TRAINING_CRAWLERS");
  assert.match(group, /disallow:\s*"\/"/);
  assert.doesNotMatch(group, /(?<!dis)allow:/, "the group allows nothing");
});

test("search engines and ChatGPT search are not blocked site-wide", () => {
  // A crawler named in its own group ignores "*", so naming one in the AI
  // list would shut it out of the whole site.
  const listed = crawlerList().map((a) => a.toLowerCase());
  for (const agent of ["oai-searchbot", "googlebot", "bingbot"]) {
    assert.ok(!listed.includes(agent), `${agent} must stay under "*"`);
  }
});

test("the sitemap does not list /search", () => {
  const entry = /path: "\/search",[\s\S]*?inSitemap: (true|false)/.exec(SITE_MAP);
  assert.ok(entry, "lib/site-map.ts has a /search route");
  assert.equal(entry[1], "false");
  const row = SITEMAP_DOC.split("\n").find((line) => line.includes("| `/search` |"));
  assert.ok(row, "docs/SITEMAP.md lists /search");
  assert.match(row, /\| No \|$/);
});

test("the search page is marked noindex but still followed", () => {
  const page = readFileSync(new URL("../../app/search/page.tsx", import.meta.url), "utf8");
  assert.match(page, /robots:\s*\{\s*index:\s*false,\s*follow:\s*true\s*\}/);
});

import assert from "node:assert/strict";
import test from "node:test";

import { NON_HUMAN_AGENT } from "../../lib/traffic-beacon.ts";

/**
 * Review views feed the admin's momentum facts (2026-09-22), so an agent that
 * declares itself automated must not count as a reader.
 */

test("self-declared crawlers, unfurlers and lab tools are not readers", () => {
  for (const ua of [
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36 Chrome-Lighthouse",
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0) HeadlessChrome/140",
    "curl/8.5.0",
    "python-requests/2.32.3",
  ]) {
    assert.ok(NON_HUMAN_AGENT.test(ua), ua);
  }
});

test("ordinary browsers count", () => {
  for (const ua of [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36 Edg/140.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
    "",
  ]) {
    assert.equal(NON_HUMAN_AGENT.test(ua), false, ua);
  }
});

test("a phone model that ends in 'bot' is a reader, not a bot", () => {
  // CUBOT handsets are sold in the Philippines; their model is in the UA.
  for (const ua of [
    "Mozilla/5.0 (Linux; Android 13; CUBOT P80) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; Cubot_X30) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36",
  ]) {
    assert.equal(NON_HUMAN_AGENT.test(ua), false, ua);
  }
  for (const ua of ["Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)",
    "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", "Twitterbot/1.0"]) {
    assert.ok(NON_HUMAN_AGENT.test(ua), ua);
  }
});

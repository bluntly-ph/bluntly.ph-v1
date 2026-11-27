import type { MetadataRoute } from "next";

import { PROTECTED, AUTH_ONLY } from "@/lib/route-access";
import { SITE_URL } from "@/lib/site-map";

/**
 * AI training crawlers, kept off the whole site. They are not search engines:
 * nothing they fetch sends a reader back, and from Oct 3 to 19, 2026 GPTBot and
 * meta-externalagent alone made about 2.8M requests to /search, each one a
 * page render plus backend calls and database reads.
 *
 * Search engines and answer engines that link back (Googlebot, Bingbot,
 * OAI-SearchBot for ChatGPT search results) fall under the "*" rule instead.
 * A crawler obeys only the most specific group that names it, so listing one
 * here takes it out of "*" entirely.
 */
const AI_TRAINING_CRAWLERS = [
  "GPTBot",
  "meta-externalagent",
  "CCBot",
  "ClaudeBot",
  "anthropic-ai",
  "Bytespider",
  "PerplexityBot",
  "Google-Extended",
];

/**
 * /robots.txt: crawl everything public, skip what needs a session or only
 * makes sense signed out (the same lists the proxy enforces), the API, and the
 * affiliate redirects — a crawler following /r/ would count as a click.
 *
 * /search too: every filter and query combination is a new URL to a crawler,
 * so it is an endless space of pages that each cost a render and a database
 * query, and the reviews it lists are crawlable on their own pages anyway.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          ...PROTECTED,
          "/sellers/*/dashboard",
          ...AUTH_ONLY,
          "/api/",
          "/r/",
          "/search",
        ],
      },
      { userAgent: AI_TRAINING_CRAWLERS, disallow: "/" },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}

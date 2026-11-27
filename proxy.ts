import { NextResponse } from "next/server";
import type { NextProxy } from "next/server";

import { isAuthOnlyPath, isProtectedPath } from "@/lib/route-access";
import { SIGNED_IN_HINT, newHintValue } from "@/lib/session-hint";
import { trafficBeacon } from "@/lib/traffic-beacon";

/**
 * Next 16 renamed Middleware to Proxy
 * (node_modules/next/dist/docs/01-app/01-getting-started/16-proxy.md).
 *
 * This is an OPTIMISTIC check only. It looks at cookie presence and nothing
 * else — it does not decode or validate the JWT. The Next docs are explicit
 * that proxy "should not be used as a full session management or authorization
 * solution"; that job belongs to lib/dal.ts, which verifies against the backend
 * on every request pass.
 *
 * The value here is avoiding a pointless render-then-redirect for signed-out
 * users, not security.
 */

const SESSION_COOKIE = process.env.SESSION_COOKIE_NAME ?? "bluntly_session";

// Which routes need a session, and which make no sense with one: lib/route-access.ts.

/**
 * Keep the readable "signed in" hint (lib/session-hint.ts) in step with the
 * session: mint one for a session that predates it, drop one whose session is
 * gone. The static pages' header trusts it to decide whether to ask for the
 * account at all, and the proxy is the one place that sees both cookies on
 * almost every page.
 */
function syncHint(request: Parameters<NextProxy>[0], response: NextResponse, hasSession: boolean) {
  const hasHint = Boolean(request.cookies.get(SIGNED_IN_HINT)?.value);
  if (hasSession && !hasHint) {
    response.cookies.set(SIGNED_IN_HINT, newHintValue(), {
      httpOnly: false,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
    });
  } else if (!hasSession && hasHint) {
    response.cookies.delete(SIGNED_IN_HINT);
  }
  return response;
}

export const proxy: NextProxy = (request, event) => {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  // Traffic geography for the moderator panel. Handed to `waitUntil` so it
  // settles after the response is already on its way: analytics must never sit
  // on the critical path of a page load, and this one is allowed to fail
  // silently because a reader whose page rendered fine should never learn that
  // a counter did not increment.
  const beacon = trafficBeacon(request);
  if (beacon) event.waitUntil(beacon);

  if (!hasSession && isProtectedPath(pathname)) {
    const url = new URL("/login", request.url);
    // Path AND query. A route can carry its state in the query — the profile's
    // three sections are one route with a `?tab=` — and sending back only the
    // pathname lands the reader somewhere they did not ask for, quietly, after
    // they have done everything right. `safeNext` in app/actions/auth.ts
    // already resolves and revalidates whatever arrives here, keeping the
    // search and refusing anything that escapes the origin, so widening this
    // does not widen what a redirect can reach.
    url.searchParams.set("next", `${pathname}${request.nextUrl.search}`);
    return syncHint(request, NextResponse.redirect(url), hasSession);
  }

  if (hasSession && isAuthOnlyPath(pathname)) {
    return syncHint(request, NextResponse.redirect(new URL("/", request.url)), hasSession);
  }

  return syncHint(request, NextResponse.next(), hasSession);
};

export const config = {
  matcher: [
    {
      /*
       * Page routes only. Everything else is excluded:
       *
       * - Next internals and static assets: running the proxy on every image
       *   and font request is pure latency.
       * - `/api/*` (the BFF forwarder, telemetry): no API path is protected or
       *   auth-only (lib/route-access.ts), and the traffic beacon already
       *   refuses to count them (lib/traffic-beacon.ts `isCountable`), so the
       *   proxy did nothing for them except bill a second function invocation
       *   on every client fetch — including each tick of the live message and
       *   count polls. The route handlers authenticate themselves.
       * - robots.txt and sitemap.xml: crawler files, never gated, never counted.
       * - The content pages (About, Articles, Contact, FAQs, Guidelines, How it
       *   works, Legal, Privacy, Terms; 2026-10-22). None is gated or
       *   auth-only, and none has views that count, so the proxy's only work
       *   there was the traffic beacon, and a beacon is a second function call
       *   for every hit on pages that took about 70k hits each in two weeks.
       *   Exact paths only: nothing else lives under them.
       */
      source:
        "/((?!api/|_next/static|_next/image|favicon.ico|robots\\.txt|sitemap\\.xml|(?:about|articles|contact|faqs|guidelines|how-it-works|legal|privacy|terms)/?$|.*\\.(?:svg|png|jpg|jpeg|gif|webp|avif|ico|woff2?)$).*)",
      /*
       * ...and never on a PREFETCH — the router guessing where the reader might
       * go next, not a reader arriving. Measured on production (2026-09-17),
       * running the proxy on them did two kinds of damage:
       *
       * 1. The traffic beacon counted them. Next strips the Flight headers and
       *    `_rsc` from the request a proxy sees (node_modules/next/dist/server/
       *    web/adapter.js), so `isCountable` cannot tell a prefetch from a
       *    visit. Every review link that scrolled into view added a VIEW to that
       *    review: in one hour of lab runs that opened a single review, 24
       *    reviews gained 121 views, and the traffic panel counted 826 "page
       *    requests" for about 200 real page loads.
       *
       * 2. A signed-out reader's prefetch of a gated link (Write a review,
       *    Profile, Ask a question) was answered with a 307 to /login. The
       *    router replays a redirected prefetch with its cache-busting param and
       *    never cancels the first response ("TODO: We should abort the previous
       *    request", fetch-server-response.js), so those requests stayed open
       *    for the life of the page: Lighthouse's desktop runs of /feed and
       *    /search hit their 45 s load timeout waiting on them.
       *
       * Skipping prefetches here is the pattern the proxy docs give for exactly
       * this. It gives up nothing: every gated page guards itself on the server
       * (lib/dal.ts requireUser / requireOnboardedUser / requireRole), and the
       * real navigation — which has no prefetch header — still meets the proxy,
       * its redirect and its `?next=`.
       */
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};

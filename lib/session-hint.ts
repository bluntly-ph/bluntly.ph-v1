/**
 * The "signed in" hint: a readable companion to the httpOnly session cookie.
 *
 * WHY IT EXISTS. Static pages (Terms, FAQs, About, …) are served from the CDN,
 * so their header cannot read the session on the server. It asks the BFF for
 * the account instead — but asking on every static page view for every
 * signed-out visitor would cost a function call each time, which is the cost
 * static pages exist to remove. This cookie lets the browser know, for free,
 * whether there is anything to ask about.
 *
 * WHAT IT HOLDS. A random value minted at sign-in, and nothing else: no token,
 * no user id. Its only jobs are "present or absent" and "is this the same
 * session as the one I cached" (the value changes on every sign-in, so a cached
 * account never outlives the session it came from).
 *
 * Who writes it: `lib/session.ts` at sign-in and sign-out, and `proxy.ts`,
 * which repairs it on any page it sees (a session from before this cookie
 * existed, or a session that expired while the hint stayed).
 */
export const SIGNED_IN_HINT = "bluntly_signed_in";

export function newHintValue(): string {
  return crypto.randomUUID();
}

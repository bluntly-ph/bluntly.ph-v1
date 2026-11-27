/**
 * Which paths the proxy sends to /login when there is no session, and which it
 * sends home when there is one. Kept apart from proxy.ts so the site map's test
 * can check every page's declared access against the same rules the proxy runs.
 *
 * Every route guarded by `requireUser`/`requireRole` belongs in PROTECTED. Those
 * guards redirect to a bare `/login` because a Server Component cannot see its
 * own pathname — so a route missing from this list still ends up at the login
 * page, just without the `?next=` that brings the user back. Someone who clicks
 * "Write a review" while signed out should land on the review form after
 * signing in, not on the homepage.
 */
export const PROTECTED = [
  "/dashboard",
  "/profile",
  "/profile/edit",
  "/settings",
  "/admin",
  // The console's old address. next.config redirects it to /admin; listed so
  // it is guarded even if that redirect were ever removed.
  "/moderate",
  "/onboarding",
  "/reviews/new",
  "/questions/new",
  "/requests/new",
  // The seller composer, opened from the mobile action menu. Its page guards
  // with requireOnboardedUser, which alone would drop the return path.
  "/sellers/rate",
  // Reached from the avatar menu; its page guards with requireUser, which
  // alone sent a signed-out reader to a bare /login.
  "/notifications",
  // You and the Bluntly team (Screen/Messages); the pages guard with
  // requireOnboardedUser, which alone would drop the return path.
  "/messages",
  // Where a reviewer answers an admin's substantiation request (§10); the
  // notification links here and the page guards with requireUser.
  "/sellers/appeals",
  // The Seller console (/seller/dashboard is its way in; /seller/<store id>/…
  // the console itself, Figma Screen/Seller/*). The trailing slash keeps the
  // public store pages (/sellers/…) open.
  "/seller/",
] as const;

/**
 * Protected paths with a dynamic segment, which a prefix cannot express. The
 * store dashboard guards with requireUser and was missing here, so a signed-out
 * owner lost the way back to their store (found building the site map).
 */
const PROTECTED_PATTERNS = [
  // The answer flow (Figma "Answer Page"): signed in, and back here after login.
  /^\/questions\/[^/]+\/answer(?:\/|$)/,
  /^\/sellers\/[^/]+\/dashboard(?:\/|$)/,
  // Report 3, the store rating summary: owner or staff, never signed out.
  /^\/sellers\/[^/]+\/reports(?:\/|$)/,
  // Seller support requests: the approved owner only.
  /^\/sellers\/[^/]+\/support(?:\/|$)/,
];

/** Routes that make no sense while already signed in. */
export const AUTH_ONLY = ["/login", "/signup", "/welcome"] as const;

export function isProtectedPath(pathname: string): boolean {
  return (
    PROTECTED.some((prefix) => pathname.startsWith(prefix)) ||
    PROTECTED_PATTERNS.some((pattern) => pattern.test(pathname))
  );
}

export function isAuthOnlyPath(pathname: string): boolean {
  return AUTH_ONLY.some((prefix) => pathname.startsWith(prefix));
}

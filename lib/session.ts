import "server-only";

import { cookies } from "next/headers";
import { clearReaderId } from "./reader-id";
import { SIGNED_IN_HINT, newHintValue } from "./session-hint";

/**
 * Session cookie handling.
 *
 * The backend issues an HS256 JWT and has **no refresh token**
 * (docs/FRONTEND_INTEGRATION.md §2). So the cookie's lifetime is pinned to the
 * token's own `expires_in`: when the cookie dies the token was already dead.
 *
 * httpOnly is the point of the whole BFF design — XSS cannot read this.
 */

const COOKIE_NAME = process.env.SESSION_COOKIE_NAME ?? "bluntly_session";

export async function createSession(
  accessToken: string,
  expiresInSeconds: number,
): Promise<void> {
  const cookieStore = await cookies();
  clearReaderId(cookieStore);
  cookieStore.set(COOKIE_NAME, accessToken, {
    httpOnly: true,
    // Secure breaks plain-http localhost, where the dev server runs.
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: expiresInSeconds,
  });
  // Readable on purpose and holding no credential: lib/session-hint.ts. It lets
  // a static page's header skip asking for the account when nobody is signed in.
  cookieStore.set(SIGNED_IN_HINT, newHintValue(), {
    httpOnly: false,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: expiresInSeconds,
  });
}

export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(COOKIE_NAME)?.value ?? null;
}

export async function destroySession(): Promise<void> {
  const cookieStore = await cookies();
  clearReaderId(cookieStore);
  cookieStore.delete(COOKIE_NAME);
  cookieStore.delete(SIGNED_IN_HINT);
}


export { COOKIE_NAME as SESSION_COOKIE_NAME };

"use client";

import { useEffect, useState } from "react";

import { AccountSwitchNotice } from "@/components/site/AccountSwitchNotice";
import { ProfileNavPanel } from "@/components/site/ProfileNavPanel";
import type { HeaderUser } from "@/components/site/SiteHeader";
import { Circle } from "@/components/ui/Skeleton";
import { SIGNED_IN_HINT } from "@/lib/session-hint";

/**
 * The header's account corner on a STATIC page (components/site/StaticPageShell).
 *
 * A static page is built once and served from the CDN, so the server cannot
 * tell it who is reading. The browser finds out instead, as cheaply as it can:
 *
 *   1. No "signed in" hint cookie (lib/session-hint.ts): signed out. No request.
 *      This is every crawler and every signed-out reader, i.e. most traffic.
 *   2. A hint whose value matches the account cached for this tab
 *      (sessionStorage): that account. No request.
 *   3. Otherwise: one GET of /api/bff/api/v1/auth/me, cached against the hint.
 *      The hint changes on every sign-in, so a cached account never outlives
 *      the session it was read for.
 *
 * Until it knows, it draws the avatar's 40px placeholder, so nothing shifts and
 * nobody signed in sees a "Log in" flash.
 */

const CACHE_KEY = "bluntly:session-user:v1";

type Known = { state: "known"; user: HeaderUser };
type Status = { state: "loading" } | Known;

type MeBody = { username?: string | null; avatar_url?: string | null; role?: string | null };

function readHint(): string | null {
  try {
    for (const part of document.cookie.split(";")) {
      const [name, ...rest] = part.trim().split("=");
      if (name === SIGNED_IN_HINT) return decodeURIComponent(rest.join("=")) || null;
    }
  } catch {
    // No cookie access: treat as signed out.
  }
  return null;
}

function readCache(hint: string): HeaderUser | undefined {
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY);
    if (!raw) return undefined;
    const cached = JSON.parse(raw) as { hint?: string; user?: HeaderUser };
    return cached.hint === hint ? (cached.user ?? null) : undefined;
  } catch {
    return undefined;
  }
}

function writeCache(hint: string, user: HeaderUser) {
  try {
    window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({ hint, user }));
  } catch {
    // Storage blocked: the next static page asks again. Correct, just not free.
  }
}

// One request per page however many components ask.
let inflight: Promise<HeaderUser> | null = null;

function fetchUser(hint: string): Promise<HeaderUser> {
  inflight ??= fetch("/api/bff/api/v1/auth/me", { cache: "no-store", credentials: "same-origin" })
    .then(async (res) => {
      if (!res.ok) return null;
      const me = (await res.json().catch(() => null)) as MeBody | null;
      return me ? { username: me.username ?? null, avatarUrl: me.avatar_url ?? null, role: me.role ?? null } : null;
    })
    .catch(() => null)
    .then((user) => {
      writeCache(hint, user);
      return user;
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** Who is reading, by the cheapest route available (see the module comment). */
async function resolveUser(): Promise<HeaderUser> {
  const hint = readHint();
  if (!hint) return null;
  const cached = readCache(hint);
  if (cached !== undefined) return cached;
  return fetchUser(hint);
}

export function useSessionUser(): Status {
  const [status, setStatus] = useState<Status>({ state: "loading" });
  useEffect(() => {
    let live = true;
    // Read in an effect, never during render: the server rendered "loading",
    // and the first client render must match it.
    void resolveUser().then((user) => {
      if (live) setStatus({ state: "known", user });
    });
    return () => {
      live = false;
    };
  }, []);
  return status;
}

/** The avatar and its navigation panel, once the account is known. */
export function SessionProfileNav() {
  const status = useSessionUser();
  if (status.state === "loading") return <Circle size={40} />;
  return <ProfileNavPanel user={status.user} />;
}

/** QA-061's cross-tab account notice, fed the account once it is known. */
export function SessionAccountSwitchNotice() {
  const status = useSessionUser();
  if (status.state === "loading") return null;
  return <AccountSwitchNotice username={status.user?.username} />;
}

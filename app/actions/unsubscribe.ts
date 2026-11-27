"use server";

import { apiFetch } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

/** The /unsubscribe page's button (backend routes/email.py, RFC 8058). No session: the signed token is the proof. */
export async function unsubscribe(token: string): Promise<{ ok: boolean; error?: string }> {
  try {
    await apiFetch(`/api/v1/email/unsubscribe?token=${encodeURIComponent(token)}`, { method: "POST" });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return { ok: false, error: "This link isn't valid any more." };
    if (err instanceof ApiError && err.status === 429) return { ok: false, error: "Too many attempts. Try again in a few minutes." };
    return { ok: false, error: "Couldn't reach Bluntly. Try again." };
  }
}

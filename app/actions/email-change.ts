"use server";

import { apiFetch } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { createSession, getSessionToken } from "@/lib/session";

/**
 * Verified email change (backend 0084, owner decision 2026-10-04).
 *
 * Server Actions, not BFF calls, because the confirm step returns a NEW session
 * token: the change ends every session issued before it, this browser included,
 * so the fresh token has to go straight into the httpOnly cookie here.
 */

export type EmailChangeState = {
  ok?: boolean;
  error?: string;
  /** Stable problem code — branch on this, never on `error` prose. */
  code?: string;
  /** After a successful start: where the second code went. */
  newEmail?: string;
  /** After a successful confirm: the address now in use. */
  email?: string;
};

function failure(err: unknown): EmailChangeState {
  if (err instanceof ApiError) {
    if (err.code === "rate_limited" || err.status === 429) {
      return { error: err.problem.detail || "Too many attempts. Try again later.", code: err.code };
    }
    return { error: err.problem.detail || "That didn't work. Try again.", code: err.code };
  }
  return { error: "Couldn't reach Bluntly. Check your connection and try again." };
}

export async function startEmailChange(newEmail: string): Promise<EmailChangeState> {
  const token = await getSessionToken();
  if (!token) return { error: "Sign in again to change your email.", code: "unauthenticated" };
  try {
    const out = await apiFetch<{ new_email: string }>("/api/v1/users/me/email-change", {
      method: "POST",
      token,
      json: { new_email: newEmail.trim() },
    });
    return { ok: true, newEmail: out.new_email };
  } catch (err) {
    return failure(err);
  }
}

export async function confirmEmailChange(currentCode: string, newCode: string): Promise<EmailChangeState> {
  const token = await getSessionToken();
  if (!token) return { error: "Sign in again to change your email.", code: "unauthenticated" };
  try {
    const out = await apiFetch<{ email: string; access_token: string; expires_in: number }>("/api/v1/users/me/email-change/confirm", {
      method: "POST",
      token,
      json: { current_code: currentCode.trim(), new_code: newCode.trim() },
    });
    await createSession(out.access_token, out.expires_in);
    return { ok: true, email: out.email };
  } catch (err) {
    return failure(err);
  }
}

export async function cancelEmailChange(): Promise<EmailChangeState> {
  const token = await getSessionToken();
  if (!token) return { ok: true };
  try {
    await apiFetch<void>("/api/v1/users/me/email-change", { method: "DELETE", token });
    return { ok: true };
  } catch (err) {
    return failure(err);
  }
}

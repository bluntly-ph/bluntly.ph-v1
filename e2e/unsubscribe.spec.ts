import { createHmac } from "node:crypto";

import { expect, test } from "@playwright/test";

/**
 * One-click unsubscribe from the store emails (backend 0085, routes/email.py).
 *
 * The link in an email is signed with the API's JWT secret, so this spec signs one
 * the same way (email_outbox_service.unsubscribe_token) for a member it registers.
 *
 *   E2E_API_URL=http://localhost:8000 E2E_JWT_SECRET=<the API's JWT_SECRET> \
 *   npx playwright test e2e/unsubscribe.spec.ts
 */

const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const SECRET = process.env.E2E_JWT_SECRET;
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

test.skip(!SECRET, "needs E2E_JWT_SECRET (the API's JWT_SECRET)");

function link(userId: string, scope: "email" | "weekly_summary"): string {
  const sig = createHmac("sha256", SECRET as string).update(`unsubscribe:${userId}:${scope}`).digest("hex").slice(0, 32);
  return `${userId}.${scope}.${sig}`;
}

async function prefs(token: string) {
  const res = await fetch(`${API}/api/v1/users/me/notification-prefs`, { headers: { authorization: `Bearer ${token}` } });
  return (await res.json()) as Record<string, boolean>;
}

test("the email footer link turns the weekly summary off, and only after the click", async ({ page }) => {
  const tag = Math.random().toString(36).slice(2, 10);
  const reg = await fetch(`${API}/api/v1/auth/register`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: `unsub_${tag}@example.com`, password: "password123", display_name: "Unsub E2E" }),
  });
  expect(reg.status).toBe(201);
  const { access_token: token } = (await reg.json()) as { access_token: string };
  const me = (await (await fetch(`${API}/api/v1/auth/me`, { headers: { authorization: `Bearer ${token}` } })).json()) as { id: string };

  await page.goto(`${BASE}/unsubscribe?token=${link(me.id, "weekly_summary")}`);
  const box = page.getByTestId("unsubscribe");
  await expect(box).toContainText("Stop the Monday weekly summary?");
  // Opening the link changed nothing (mail scanners open links too).
  expect((await prefs(token)).weekly_summary).toBe(true);

  await box.getByRole("button", { name: "Unsubscribe" }).click();
  await expect(box.getByRole("status")).toContainText("You won't get the weekly summary any more.");
  const after = await prefs(token);
  expect(after.weekly_summary).toBe(false);
  expect(after.email).toBe(true);

  // Opened again: already off, nothing to click.
  await page.reload();
  await expect(box.getByRole("status")).toBeVisible();
  await expect(box.getByRole("button", { name: "Unsubscribe" })).toHaveCount(0);

  // A tampered link says so, and nothing about the account.
  await page.goto(`${BASE}/unsubscribe?token=${me.id}.email.${"0".repeat(32)}`);
  await expect(page.getByText("This unsubscribe link isn’t valid.")).toBeVisible();
});

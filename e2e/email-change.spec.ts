import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

/**
 * Verified email change (backend 0084; owner decision 2026-10-04), end to end in the
 * Seller console's Account window.
 *
 * A fresh store owner is made through the API (a change revokes the account's other
 * tokens, so a shared fixture user would break the journeys that follow). The two
 * codes are read from the API's log: with EMAIL_PROVIDER=console each email's subject
 * (which leads with its code) is logged.
 *
 *   E2E_FIXTURES=<e2e_fixtures json> E2E_API_URL=http://localhost:8000 \
 *   E2E_API_LOG=<uvicorn log> npx playwright test e2e/email-change.spec.ts
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const API_LOG = process.env.E2E_API_LOG;
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

test.skip(!FIXTURES || !API_LOG, "needs E2E_FIXTURES and E2E_API_LOG");

type Fx = { users: Record<string, { token: string }> };
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({ users: {} } as Fx);

async function api(path: string, init: { token?: string; json?: unknown; method?: string } = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (init.token) headers.authorization = `Bearer ${init.token}`;
  const res = await fetch(`${API}${path}`, {
    method: init.method ?? (init.json === undefined ? "GET" : "POST"),
    headers,
    body: init.json === undefined ? undefined : JSON.stringify(init.json),
  });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

/** The newest code sent to `to`, from the console provider's log line. */
function codeFor(to: string): string {
  const lines = readFileSync(API_LOG as string, "utf8").split("\n").filter((l) => l.includes("Email (console provider)") && l.includes(to));
  const subject = JSON.parse(lines.at(-1) as string).subject as string;
  return /^(\d{6})/.exec(subject)?.[1] as string;
}

test("a store owner changes their sign-in email with two codes", async ({ page, context }) => {
  const tag = Math.random().toString(36).slice(2, 10);
  const oldEmail = `owner_${tag}@example.com`;
  const newEmail = `owner_${tag}_new@example.com`;
  const reg = await api("/api/v1/auth/register", { json: { email: oldEmail, password: "password123", display_name: "Owner E2E" } });
  expect(reg.status).toBe(201);
  const token = reg.body.access_token as string;
  // Past the onboarding wizard (interests chosen), as a real store owner would be.
  expect((await api("/api/v1/users/me", { token, method: "PATCH", json: { interests: ["electronics"] } })).status).toBe(200);
  const store = await api("/api/v1/sellers", { token, json: { display_name: `Mail Store ${tag}`, platform: "shopee" } });
  const claim = await api(`/api/v1/sellers/${store.body.id}/claims`, {
    token,
    json: { registration_kind: "dti", registration_number: "DTI-3145678", registered_business_name: "Mail Trading", marketplace_shop_name: `Mail Store ${tag}`, evidence: "I run it." },
  });
  const approved = await api(`/api/v1/admin/seller-claims/${claim.body.id}/decision`, { token: fx.users.administrator.token, json: { decision: "approve" } });
  expect(approved.status).toBe(200);

  await context.addCookies([{ name: "bluntly_session", value: token, url: BASE }]);
  await page.goto(`${BASE}/seller/${store.body.id}/settings`);
  await page.getByRole("button", { name: "Profile and password" }).click();
  const box = page.getByTestId("email-change");
  await expect(box).toContainText("o••••");
  await box.getByRole("button", { name: "Change email" }).click();
  await expect(box.getByRole("button", { name: "Send codes" })).toBeDisabled();
  await box.getByLabel(/New email/).fill(newEmail);
  await box.getByRole("button", { name: "Send codes" }).click();

  const fromOld = box.getByLabel(/Code sent to o•+@example\.com/);
  await expect(fromOld).toBeVisible();
  await fromOld.fill(codeFor(oldEmail));
  // A wrong second code: refused, nothing changes.
  await box.getByLabel(`Code sent to ${newEmail}`).fill(codeFor(newEmail) === "000000" ? "111111" : "000000");
  await box.getByRole("button", { name: "Change email" }).click();
  await expect(box.getByRole("alert")).toContainText("don't match");
  expect((await api("/api/v1/auth/me", { token })).body.email).toBe(oldEmail);

  await box.getByLabel(`Code sent to ${newEmail}`).fill(codeFor(newEmail));
  await box.getByRole("button", { name: "Change email" }).click();
  await expect(box.getByRole("status")).toContainText(`You now sign in with ${newEmail}`);

  // The token this browser started with is ended; the page keeps working on the fresh one.
  expect((await api("/api/v1/auth/me", { token })).status).toBe(401);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  const cookie = (await context.cookies()).find((c) => c.name === "bluntly_session");
  expect((await api("/api/v1/auth/me", { token: cookie?.value })).body.email).toBe(newEmail);
});

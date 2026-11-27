import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext } from "@playwright/test";

/**
 * QA sandbox payments (owner decision, 2026-09-27) against the REAL stack: a
 * named QA tester is credited a sandbox test earning from the console, sees it
 * labelled, withdraws it from Transfer, and a moderator pays it from Payouts —
 * the path real QA testers will walk before the defense. Seeded by
 * backend/scripts/e2e_fixtures.py (the `qatester` account is already on the
 * owner's list). Skipped anywhere E2E_FIXTURES is unset.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  users: Record<string, { id: string; token: string; username: string }>;
  qa_review: string;
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function api(who: string, path: string, init: RequestInit = {}) {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "content-type": "application/json", authorization: `Bearer ${fx.users[who].token}` },
  });
  return { status: res.status, body: await res.json().catch(() => null) };
}

test("a QA tester is credited a sandbox test earning, withdraws it, and is paid", async ({ browser }) => {
  const mod = await browser.newContext();
  await as(mod, "administrator");
  const tester = await browser.newContext();
  await as(tester, "qatester");
  const mp = await mod.newPage();
  const tp = await tester.newPage();
  const name = `@${fx.users.qatester.username}`;

  // The moderator credits the tester's review from QA Payments.
  await mp.goto("/admin/qa-sandbox");
  const card = mp.getByRole("region", { name: `QA tester ${name}` });
  await expect(card).toBeVisible();
  await expect(mp.getByText("Only a Super Admin can add or remove QA testers.")).toBeVisible();
  await card.getByRole("button", { name: "Credit test earning" }).first().click();
  await expect(card.getByText(/Test earning ₱350\.00 credited/)).toBeVisible();
  // Once per review: the control is gone once it has its earning.
  await expect(card.getByRole("button", { name: "Credit test earning" })).toHaveCount(0);

  // The tester is told, sees it labelled, and it is ready to withdraw.
  const notices = await api("qatester", "/api/v1/notifications?limit=10");
  expect(notices.body.some((n: { kind: string }) => n.kind === "qa_test_earning")).toBe(true);
  expect((await api("qatester", "/api/v1/auth/me/payout-account", {
    method: "PATCH", body: JSON.stringify({ payout_account: "qa-sandbox-buyer@example.com" }),
  })).status).toBe(200);
  // The earnings rows live on History; Payout (Figma 7840:9380) shows the ring.
  await tp.goto("/dashboard/history");
  await expect(tp.getByText("Sandbox test").first()).toBeVisible();
  await expect(tp.getByText("QA test earning · not real money").first()).toBeVisible();
  await tp.goto("/dashboard/transfer");
  await expect(tp.getByRole("note")).toContainText("You're a QA tester.");
  await tp.getByRole("button", { name: /^Request ₱/ }).click();
  await expect(tp.getByText(/Requested ₱350\.00/)).toBeVisible();
  await tp.reload();
  await expect(tp.getByTestId("withdrawal").first()).toContainText("Requested");

  // The moderator pays it from Payouts, recording the PayPal sandbox reference.
  // Redesigned 2026-10-02 (Figma Screen/Admin/Payouts): the table masks the
  // address; the Send payout modal shows it in full with a Copy button.
  await mp.goto("/admin/payouts");
  // The table names the member by display name and links the person; find
  // the row by that link rather than by the handle.
  const person = `a[href="/admin/people/${fx.users.qatester.id}"]`;
  const row = mp.getByTestId("payout-row").filter({ has: mp.locator(person) }).first();
  await expect(row).toContainText("QA tester");
  await row.getByRole("button", { name: "Open" }).click();
  const send = mp.getByRole("dialog", { name: "Send payout" });
  await expect(send).toContainText("qa-sandbox-buyer@example.com");
  await send.getByLabel("Transfer reference").fill("SANDBOX-E2E-TXN");
  await send.getByRole("button", { name: "Mark as sent" }).click();
  // The confirm records it through the API ("Recording…"), then closes; only
  // then has it moved to Sent. Leaving before that answer raced the write: the
  // Sent page could be read before the payout was marked paid.
  const confirm = mp.getByRole("dialog", { name: "Mark as sent?" });
  const marked = mp.waitForResponse((r) => r.request().method() === "POST" && r.url().endsWith("/mark-paid"));
  await confirm.getByRole("button", { name: "Mark as sent" }).click();
  expect((await marked).status()).toBe(200);
  await expect(confirm).toHaveCount(0);
  await mp.goto("/admin/payouts?view=sent");
  await expect(mp.getByTestId("payout-row").filter({ has: mp.locator(person) }).first()).toContainText("SANDBOX-E2E-TXN");

  // The tester sees it paid, with the reference, and was told.
  await tp.reload();
  const withdrawal = tp.getByTestId("withdrawal").first();
  await expect(withdrawal).toContainText("Paid");
  await expect(withdrawal).toContainText("SANDBOX-E2E-TXN");
  const after = await api("qatester", "/api/v1/notifications?limit=10");
  const paid = after.body.find((n: { kind: string }) => n.kind === "payout_paid");
  expect(paid?.title).toContain("₱350.00");

  await mod.close();
  await tester.close();
});

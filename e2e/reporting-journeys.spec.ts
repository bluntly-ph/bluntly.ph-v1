import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * The four system reports, on the REAL stack (production Next build, FastAPI,
 * Postgres seeded by backend/scripts/e2e_fixtures.py). Skipped anywhere
 * E2E_FIXTURES is unset.
 *
 * Money the fixtures put in place (exact, from the importers' own split):
 *   statementer cycle 1996-11: one Shopee sale of ₱1,000.00, uncleared -> ₱300.00
 *              clearing. Its own reviewer and cycle: "reviewer"'s per-run-cycle sale
 *              is cleared by br-journeys' remittance, which may run first.
 *   nearcash   cycle 1996-06: ₱999.97 cleared -> ₱299.99 withdrawable (below the ₱300 minimum)
 *   atcash     cycle 1996-06: ₱1,000.00 cleared -> ₱300.00 withdrawable (at the minimum)
 *   nearcash   "Lamp flickers" (Hard pass) on the Honesty Fund track with a ₱20.00 sale
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  users: Record<string, { id: string; token: string; username: string }>;
  store: string;
  store_name: string;
  report: { cycle_year: number; cycle_month: number; fund_review: string; store2: string; store2_name: string };
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function api(who: string | null, path: string) {
  const headers: Record<string, string> = {};
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { headers });
  return res.status;
}

async function noSidewaysScroll(page: Page) {
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
}

const JUNE_1996 = () => `month=${fx.report.cycle_month}&year=${fx.report.cycle_year}`;

test("1. staff open the Honesty Fund report: inputs listed, distribution not guessed", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin/reports/honesty-fund?${JUNE_1996()}`, { waitUntil: "load" });
  await expect(page.getByRole("heading", { name: "Honesty Fund Distribution Report" })).toBeVisible();
  await expect(page.getByTestId("fund-formula-status")).toContainText("not yet defined");
  const row = page.getByRole("row").filter({ hasText: "Lamp flickers" }).filter({ hasText: `@${fx.users.nearcash.username}` });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Pending distribution formula");
  await expect(row).toContainText("₱20.00");
});

test("2. staff change the period with the picker", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin/reports/honesty-fund?${JUNE_1996()}`, { waitUntil: "load" });
  await expect(page.getByTestId("report-period")).toHaveText("June 1996");
  await page.getByLabel("Month").selectOption("7");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/month=7/);
  await expect(page.getByTestId("report-period")).toHaveText("July 1996");
  await expect(page.getByRole("row").filter({ hasText: "Lamp flickers" }).filter({ hasText: `@${fx.users.nearcash.username}` })).toBeVisible();
  await expect(page.getByTestId("fund-total")).toHaveText("₱0.00");
});

test("3. staff open the Commissions & Payouts report", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin/reports`, { waitUntil: "load" });
  // Reports opens on the financial report (Figma 8028:12886); the CSV reports are its tabs.
  await expect(page.getByRole("button", { name: "Generate report" })).toBeVisible();
  await page.getByRole("navigation", { name: "Reports sections" }).getByRole("link", { name: "Commissions & Payouts" }).click();
  await expect(page.getByRole("heading", { name: "Commission and Payout Report" })).toBeVisible();
  await page.goto(`${BASE}/admin/reports/commissions?${JUNE_1996()}`, { waitUntil: "load" });
  const commissions = page.getByRole("region", { name: /^Commissions \(/ });
  const near = commissions.getByRole("row").filter({ hasText: `@${fx.users.nearcash.username}` })
    .filter({ hasText: "₱999.97" });
  await expect(near).toHaveCount(1);
  await expect(near).toContainText("Cleared");
  await expect(near).toContainText("₱299.99");
});

test("4. the ₱300 threshold: ₱299.99 is not eligible, ₱300.00 is", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin/reports/commissions?${JUNE_1996()}`, { waitUntil: "load" });
  const readiness = page.getByRole("region", { name: "Reviewer payout readiness" });
  const near = readiness.getByRole("row").filter({ hasText: `@${fx.users.nearcash.username}` });
  const at = readiness.getByRole("row").filter({ hasText: `@${fx.users.atcash.username}` });
  await expect(near).toContainText("₱299.99");
  await expect(near.getByTestId("cashout-eligible")).toHaveText("No");
  await expect(at).toContainText("₱300.00");
  await expect(at.getByTestId("cashout-eligible")).toHaveText("Yes");
});

test("5. a claimed seller opens their Rating Summary", async ({ page, context }) => {
  await as(context, "owner");
  // The old store dashboard opens the Seller console; the report is linked from Insights.
  await page.goto(`${BASE}/sellers/${fx.store}/dashboard`, { waitUntil: "load" });
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.store}$`));
  await page.getByRole("link", { name: "Insights" }).first().click();
  await page.getByRole("link", { name: "Rating summary report" }).click();
  await expect(page.getByRole("heading", { name: "Seller Rating Summary" })).toBeVisible();
  await expect(page.getByText(fx.store_name).first()).toBeVisible();
  // The fixture store has one buyer review (overall 1) — all time, whatever the month.
  const allTime = page.getByRole("region", { name: "All time" });
  await expect(allTime.getByTestId("review-count")).toHaveText("1");
  await expect(allTime.getByTestId("overall-median")).toHaveText("1");
  await expect(allTime.getByTestId("recommendation-rate")).toHaveText("0.0%");
});

test("6. another seller cannot read it", async ({ page, context }) => {
  await as(context, "ownertwo");
  await page.goto(`${BASE}/sellers/${fx.store}/reports`, { waitUntil: "load" });
  await expect(page.getByTestId("report-unavailable")).toContainText("don't have access");
  await expect(page.getByText("Seller Rating Summary")).toHaveCount(0);
  expect(await api("ownertwo", `/api/v1/sellers/${fx.store}/reports/rating-summary`)).toBe(403);
  // …while their own store's report opens.
  expect(await api("ownertwo", `/api/v1/sellers/${fx.report.store2}/reports/rating-summary`)).toBe(200);
});

test("7. a reviewer opens their Earnings Statement", async ({ page, context }) => {
  await as(context, "statementer");
  await page.goto(`${BASE}/dashboard`, { waitUntil: "load" });
  await page.getByRole("link", { name: "Earnings statement" }).click();
  await expect(page.getByRole("heading", { name: "Reviewer Earnings Statement" })).toBeVisible();
  await expect(page.getByText(`@${fx.users.statementer.username}`).first()).toBeVisible();
});

test("8. the reviewer filters by month", async ({ page, context }) => {
  await as(context, "statementer");
  await page.goto(`${BASE}/dashboard/statement?month=11&year=1996`, { waitUntil: "load" });
  await expect(page.getByTestId("earned-in-period")).toHaveText("₱300.00");
  await expect(page.getByRole("row").filter({ hasText: "Clearing" }).first()).toBeVisible();
  await page.getByLabel("Month").selectOption("12");
  await page.getByRole("button", { name: "Show" }).click();
  await expect(page).toHaveURL(/month=12&year=1996/);
  await expect(page.getByTestId("earned-in-period")).toHaveText("₱0.00");
  await expect(page.getByText("No earnings in this period.")).toBeVisible();
});

test("9. the reviewer exports the statement as CSV", async ({ page, context }) => {
  await as(context, "statementer");
  await page.goto(`${BASE}/dashboard/statement?month=11&year=1996`, { waitUntil: "load" });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Export CSV" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("bluntly-earnings-statement-1996-11.csv");
  const path = await download.path();
  const text = readFileSync(path!, "utf8").replace(/^﻿/, "");
  const [header, ...rows] = text.trim().split(/\r?\n/);
  expect(header.startsWith("Recognised at,Cycle month,Commission ID")).toBe(true);
  expect(rows).toHaveLength(1);
  expect(rows[0]).toContain(",1000.00,300.00,clearing,");
});

test("10. unauthorized users are rejected", async ({ page, context }) => {
  // Signed out: the statement asks you to sign in.
  await page.goto(`${BASE}/dashboard/statement`, { waitUntil: "load" });
  await expect(page).toHaveURL(/\/login/);
  // A member who is not staff is turned away from the console's reports…
  await as(context, "buyer");
  await page.goto(`${BASE}/admin/reports/commissions`, { waitUntil: "load" });
  await expect(page).not.toHaveURL(/\/admin\/reports/);
  // …and the API refuses the reports themselves, however they are called.
  expect(await api("buyer", "/api/v1/admin/reports/commissions-payouts")).toBe(403);
  expect(await api("buyer", "/api/v1/admin/reports/honesty-fund")).toBe(403);
  expect(await api("buyer", `/api/v1/admin/reports/earnings-statement/${fx.users.statementer.id}`)).toBe(403);
  expect(await api(null, "/api/v1/reports/earnings-statement")).toBe(401);
});

for (const width of [390, 768, 1440]) {
  test(`reports fit a ${width}px screen without sideways scroll`, async ({ page, context }) => {
    await page.setViewportSize({ width, height: 900 });
    await as(context, "statementer");
    await page.goto(`${BASE}/dashboard/statement?month=11&year=1996`, { waitUntil: "load" });
    await expect(page.getByTestId("earned-in-period")).toBeVisible();
    await noSidewaysScroll(page);
    await as(context, "owner");
    await page.goto(`${BASE}/sellers/${fx.store}/reports`, { waitUntil: "load" });
    await expect(page.getByRole("heading", { name: "Seller Rating Summary" })).toBeVisible();
    await noSidewaysScroll(page);
    await as(context, "administrator");
    await page.goto(`${BASE}/admin/reports/commissions?${JUNE_1996()}`, { waitUntil: "load" });
    await expect(page.getByRole("heading", { name: "Commission and Payout Report" })).toBeVisible();
    await noSidewaysScroll(page);
  });
}

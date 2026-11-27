import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Owner decisions A-D (2026-09-28): the Administrator console at /admin, the
 * Super Admin's user management and 2.5-star routing, on the REAL stack
 * (production Next build, FastAPI, Postgres seeded by
 * backend/scripts/e2e_fixtures.py). Every journey reads its outcome back from
 * the API. Skipped anywhere E2E_FIXTURES is unset.
 *
 * Fixtures: "administrator" (an Administrator), "superadmin" (the only Super
 * Admin in the e2e database), "promotee" (a member to promote), a store claim
 * waiting on an Administrator, and two 2.5-star "It depends" reviews an
 * Administrator approved, waiting on the Super Admin.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  users: Record<string, { id: string; token: string; username: string }>;
  routing: Record<"fund" | "platform", { id: string; title: string }>;
  pending_claim: { id: string; store: string; store_name: string };
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  // A protected Vercel Preview answers only with its automation bypass (never logged).
  const bypass = process.env.VERCEL_AUTOMATION_BYPASS_SECRET;
  if (bypass) headers["x-vercel-protection-bypass"] = bypass;
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

async function noSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
}

const rail = (page: Page) => page.getByRole("navigation", { name: "Admin sections" });

test("1-2. an Administrator signs in and opens /admin", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin`);
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  // The rail link carries its count pill ("Queue 12"), so match the start.
  await expect(rail(page).getByRole("link", { name: /^Queue\b/ })).toBeVisible();
  // The user card names the role; nothing says "Moderator" anywhere.
  await expect(page.getByText("Administrator", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/moderator/i)).toHaveCount(0);
});

test("3. an Administrator approves a seller claim", async ({ page, context }) => {
  await as(context, "administrator");
  // The list is oldest first, ten a page: open the page the claim is on.
  const claims = (await api("administrator", "/api/v1/admin/seller-claims?limit=200")).body as { id: string }[];
  const at = claims.findIndex((c) => c.id === fx.pending_claim.id);
  expect(at).toBeGreaterThanOrEqual(0);
  await page.goto(`${BASE}/admin/sellers?page=${Math.floor(at / 10) + 1}`);
  const row = page.getByTestId("claim-row").filter({ hasText: fx.pending_claim.store_name });
  await row.getByRole("button", { name: "Review" }).click();
  const modal = page.getByRole("dialog", { name: "Review claim" });
  await modal.getByRole("button", { name: "Approve", exact: true }).click();
  await page.getByRole("button", { name: "Confirm approval" }).click();
  await expect
    .poll(async () => (await api(null, `/api/v1/sellers/${fx.pending_claim.store}`)).body?.claim_status)
    .toBe("claimed");
});

test("4-5. an Administrator has no user management, in the UI or the API", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin`);
  await expect(rail(page).getByRole("link", { name: "Users" })).toHaveCount(0);
  await expect(rail(page).getByText("Super Admin", { exact: true })).toHaveCount(0);
  await page.goto(`${BASE}/admin/users`);
  await expect(page.getByTestId("super-admin-only")).toContainText("User management");
  // No user search on the page itself (the shell's top-bar search is on every page).
  await expect(page.getByRole("main").getByRole("search")).toHaveCount(0);
  expect((await api("administrator", "/api/v1/admin/users?q=USR-000001")).status).toBe(403);
  const promote = await api("administrator", `/api/v1/admin/users/${fx.users.promotee.id}/role`, {
    method: "PATCH",
    body: JSON.stringify({ role: "administrator" }),
  });
  expect(promote.status).toBe(403);
});

test("6. an Administrator cannot resolve a 2.5-star item", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/admin/special-routing`);
  await expect(page.getByTestId("super-admin-only")).toBeVisible();
  await expect(page.getByTestId("routing-queue")).toHaveCount(0);
  const tried = await api("administrator", `/api/v1/admin/super/special-routing/${fx.routing.fund.id}`, {
    method: "POST",
    body: JSON.stringify({ destination: "honesty_fund", confirm: "route" }),
  });
  expect(tried.status).toBe(403);
  expect((await api("administrator", "/api/v1/admin/super/special-routing")).status).toBe(403);
});

test("7-8. the Super Admin signs in and opens User management", async ({ page, context }) => {
  await as(context, "superadmin");
  await page.goto(`${BASE}/admin`);
  await expect(page.getByText("Super Admin", { exact: true }).first()).toBeVisible();
  // People has no subtab row (Figma Screen/Admin/People 7998:11693; owner
  // 2026-10-03): User management opens from Settings -> Team -> Manage roles.
  await page.getByRole("link", { name: "Settings", exact: true }).first().click();
  await page.getByRole("link", { name: "Manage roles" }).click();
  await expect(page).toHaveURL(/\/admin\/users$/);
  await expect(page.getByRole("heading", { name: "User management" })).toBeVisible();
  await expect(page.getByRole("main").getByRole("search")).toBeVisible();
});

test("9-10. the Super Admin promotes a member; the new Administrator has exactly that access", async ({ browser }) => {
  const superCtx = await browser.newContext();
  await as(superCtx, "superadmin");
  const page = await superCtx.newPage();
  await page.goto(`${BASE}/admin/users`);
  await page.getByPlaceholder("USR-000123, UUID, exact email, or name").fill(fx.users.promotee.id);
  await page.getByRole("button", { name: "Search" }).click();
  const row = page.getByRole("row").filter({ hasText: `@${fx.users.promotee.username}` });
  await row.getByRole("combobox").selectOption("administrator");
  const dialog = page.getByRole("dialog", { name: /Change .*role\?/ });
  await expect(dialog).toContainText("Member → Administrator");
  await dialog.getByRole("button", { name: "Confirm change" }).click();
  await expect(page.getByRole("status").filter({ hasText: "is now an Administrator" })).toBeVisible();
  await superCtx.close();

  const me = await api("promotee", "/api/v1/auth/me");
  expect(me.body.role).toBe("administrator");
  const promoted = await browser.newContext();
  await as(promoted, "promotee");
  const theirs = await promoted.newPage();
  await theirs.goto(`${BASE}/admin/review-queue`);
  await expect(theirs).toHaveURL(/\/admin\/review-queue/);
  await expect(rail(theirs).getByRole("link", { name: "Users" })).toHaveCount(0);
  expect((await api("promotee", "/api/v1/admin/users?q=x")).status).toBe(403);
  await promoted.close();
});

// Screen/Admin/SpecialRouting 8178:20045 → Overlay/Routing/Track 8178:20344.
async function routeFromQueue(page: Page, title: string, destination: "Honesty Fund" | "Platform") {
  // The table pages (10 a page); a cumulative fixture database can hold more.
  await page.getByRole("navigation", { name: "Routing pages" }).getByLabel("Rows per page").selectOption("50");
  await page.getByTestId("routing-queue").getByRole("button", { name: `Route ${title}` }).click();
  const dialog = page.getByRole("dialog", { name: "Route earnings" });
  await expect(dialog).toContainText(title);
  await expect(dialog).toContainText("Verdict · It depends");
  await expect(dialog.getByRole("button", { name: "Choose a route" })).toBeDisabled();
  await dialog.getByRole("radio", { name: new RegExp(`^${destination}`) }).check();
  await dialog.getByLabel("Note for the log").fill("e2e: routed from the console");
  await dialog.getByRole("button", { name: `Route to ${destination}` }).click();
  await expect(page.getByRole("status").filter({ hasText: `routed to ${destination}` })).toBeVisible();
}

test("11. the Super Admin routes a 2.5-star item to the Honesty Fund", async ({ page, context }) => {
  await as(context, "superadmin");
  await page.goto(`${BASE}/admin/special-routing`);
  await routeFromQueue(page, fx.routing.fund.title, "Honesty Fund");
  const review = (await api("superadmin", `/api/v1/reviews/${fx.routing.fund.id}`)).body;
  expect(review.earn_eligible_status).toBe("honesty_fund");
});

test("12. another 2.5-star item goes to the Platform", async ({ page, context }) => {
  await as(context, "superadmin");
  await page.goto(`${BASE}/admin/special-routing`);
  await routeFromQueue(page, fx.routing.platform.title, "Platform");
  const review = (await api("superadmin", `/api/v1/reviews/${fx.routing.platform.id}`)).body;
  expect(review.earn_eligible_status).toBe("approved");
  await expect(page.getByTestId("routing-queue").getByRole("button", { name: `Route ${fx.routing.platform.title}` })).toHaveCount(0);
});

test("13. the audit history shows both decisions", async ({ page, context }) => {
  await as(context, "superadmin");
  await page.goto(`${BASE}/admin/special-routing`);
  const history = page.getByTestId("routing-history");
  await expect(history.getByRole("row").filter({ hasText: "Honesty Fund" }).first()).toBeVisible();
  await expect(history.getByRole("row").filter({ hasText: "Platform" }).first()).toBeVisible();
  const decisions = (await api("superadmin", "/api/v1/admin/super/special-routing/history")).body as {
    review_id: string;
    destination: string;
  }[];
  const mine = Object.fromEntries(
    decisions
      .filter((d) => d.review_id === fx.routing.fund.id || d.review_id === fx.routing.platform.id)
      .map((d) => [d.review_id, d.destination]),
  );
  expect(mine).toEqual({ [fx.routing.fund.id]: "honesty_fund", [fx.routing.platform.id]: "platform" });
});

test("14. the last Super Admin cannot be demoted", async ({ page, context }) => {
  await as(context, "superadmin");
  await page.goto(`${BASE}/admin/users`);
  await page.getByPlaceholder("USR-000123, UUID, exact email, or name").fill(fx.users.superadmin.id);
  await page.getByRole("button", { name: "Search" }).click();
  const row = page.getByRole("row").filter({ hasText: `@${fx.users.superadmin.username}` });
  await row.getByRole("combobox").selectOption("administrator");
  await page.getByRole("dialog", { name: /Change .*role\?/ }).getByRole("button", { name: "Confirm change" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "last Super Admin" })).toBeVisible();
  expect((await api("superadmin", "/api/v1/auth/me")).body.role).toBe("super_admin");
});

test("15. /moderate still lands on /admin, path and query kept", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/moderate/review-queue?tab=support`);
  await expect(page).toHaveURL(/\/admin\/review-queue\?tab=support$/);
  await page.goto(`${BASE}/moderate`);
  await expect(page).toHaveURL(/\/admin$/);
});

test("16. the admin console on a phone", async ({ browser }) => {
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await as(phone, "superadmin");
  const page = await phone.newPage();
  await page.goto(`${BASE}/admin`);
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  await noSidewaysScroll(page);
  await page.getByRole("button", { name: "Open admin navigation" }).click();
  await expect(page.getByRole("link", { name: "Special routing" }).last()).toBeVisible();
  await page.getByRole("link", { name: "Special routing" }).last().click();
  await expect(page).toHaveURL(/\/admin\/special-routing/);
  await noSidewaysScroll(page);
  await phone.close();
});

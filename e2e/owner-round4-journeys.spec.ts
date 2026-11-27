import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Owner requests of 2026-09-28 and the QA workbook items still failing, on the
 * REAL stack (production Next build, FastAPI, Postgres seeded by
 * backend/scripts/e2e_fixtures.py). Skipped anywhere E2E_FIXTURES is unset.
 *
 *  - Dashboard → Answers shows answers to the member's own questions.
 *  - Search finds people and opens their profile.
 *  - A review with a long unbroken string stays inside the page.
 *  - /profile: no Log out, Earnings or Edit chips; ⋯ holds Share and Edit.
 *  - The side navigation has Feed.
 *  - QA-043: a seller review takes votes and replies.
 *  - QA-053: All filters has Review score, Trust rating and Budget.
 *  - QA-006: a review without an affiliate link links its marketplace listing.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  tag: string;
  users: Record<string, { id: string; token: string; username: string }>;
  products: { fan: string; fresh: string; doomed: string; fan_name: string };
  reviews: { old: string; fresh: string; doomed: string };
  question: string;
  store: string;
  seller_review: string;
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
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

async function noSidewaysScroll(page: Page) {
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
}

test("Dashboard → Answers lists the answers to my own questions, not /questions", async ({ page, context }) => {
  await as(context, "asker");
  await page.goto(`${BASE}/dashboard`, { waitUntil: "load" });
  await page.getByRole("link", { name: "Answers", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard\?tab=answers/);
  await expect(page.getByRole("heading", { name: "Answers to your questions" })).toBeVisible();
  // The asker's product question (answered by the reviewer) is listed with
  // its answer; the newest-answered question comes first.
  const row = page.getByTestId("my-question").filter({
    has: page.locator(`a[href="/questions/${fx.question}"]`),
  });
  await expect(row).toBeVisible();
});

test("Search → People finds a member by @handle and opens their profile", async ({ page }) => {
  const who = fx.users.reviewer.username;
  await page.goto(`${BASE}/search?tab=people&q=${encodeURIComponent(`@${who}`)}`, { waitUntil: "load" });
  const hit = page.getByTestId("person-result").filter({ hasText: `@${who}` });
  await expect(hit).toBeVisible();
  await hit.getByRole("link").first().click();
  await expect(page).toHaveURL(new RegExp(`/u/${who}$`));
});

test("The search box suggests a person alongside products", async ({ page }) => {
  const who = fx.users.reviewer.username;
  await page.goto(`${BASE}/search`, { waitUntil: "load" });
  await page.getByRole("combobox").first().fill(who);
  const option = page.getByRole("option").filter({ hasText: `@${who}` });
  await expect(option).toBeVisible();
  await option.click();
  await expect(page).toHaveURL(new RegExp(`/u/${who}$`));
});

test("A review with a 4,000-character unbroken string stays inside the page", async ({ page, context }) => {
  const product = await api("voter", "/api/v1/products", {
    method: "POST",
    body: JSON.stringify({
      name: `Wrap probe ${fx.tag} ${Date.now().toString(36)}`,
      category: "electronics",
      source_url: `https://shopee.ph/wrap-i.1.${Date.now() % 1e12}`,
    }),
  });
  expect([200, 201]).toContain(product.status);
  const review = await api("voter", "/api/v1/reviews", {
    method: "POST",
    body: JSON.stringify({
      product_id: (product.body as { id: string }).id,
      title: "W".repeat(150),
      star_rating: 3,
      discussion: "a".repeat(3921),
      verdict: "it_depends",
    }),
  });
  expect(review.status).toBe(201);
  await as(context, "voter");
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${BASE}/reviews/${(review.body as { id: string }).id}`, { waitUntil: "load" });
    await noSidewaysScroll(page);
  }
});

test("/profile keeps Log out in the side navigation and puts Share and Edit behind ⋯", async ({ page, context }) => {
  await as(context, "reviewer");
  await page.goto(`${BASE}/profile`, { waitUntil: "load" });
  const main = page.locator("main");
  await expect(main.getByRole("button", { name: "Log out" })).toHaveCount(0);
  await expect(main.getByRole("link", { name: "Earnings" })).toHaveCount(0);
  await expect(main.getByRole("link", { name: "Edit profile" })).toHaveCount(0);

  await main.getByRole("button", { name: "Profile options" }).click();
  await expect(page.getByRole("menuitem", { name: "Share profile" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Edit profile" }).click();
  await expect(page).toHaveURL(/\/profile\/edit$/);

  await page.goto(`${BASE}/profile`, { waitUntil: "load" });
  await main.getByRole("button", { name: "Profile options" }).click();
  await page.getByRole("menuitem", { name: "Share profile" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // Log out is still one tap away, in the side navigation.
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Menu and profile/ }).first().click();
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
});

for (const who of ["reviewer", null] as const) {
  test(`The side navigation has Feed (${who ? "signed in" : "signed out"})`, async ({ page, context }) => {
    if (who) await as(context, who);
    await page.goto(`${BASE}/categories`, { waitUntil: "load" });
    // "Menu and profile" signed in, "Menu" signed out.
    await page.getByRole("button", { name: /^Menu/ }).first().click();
    const feed = page.getByLabel("Primary").getByRole("link", { name: "Feed", exact: true });
    await expect(feed).toHaveAttribute("href", "/feed");
    await feed.click();
    await expect(page).toHaveURL(/\/feed$/);
  });
}

test("QA-043: a seller review takes a vote and a reply", async ({ page, context }) => {
  await as(context, "voter");
  await page.goto(`${BASE}/sellers/${fx.store}`, { waitUntil: "load" });
  const card = page.locator(`#seller-review-${fx.seller_review}`);
  await card.getByRole("button", { name: /^Helpful, \d+/ }).click();
  await expect(card.getByRole("button", { name: /^Helpful, 1/ })).toHaveAttribute("aria-pressed", "true");

  const text = `Same here ${fx.tag}`;
  await card.getByRole("button", { name: "Reply" }).click();
  await card.getByPlaceholder("Reply to this review. Links aren't allowed.").fill(text);
  await card.getByRole("button", { name: "Post reply" }).click();
  await expect(card.getByTestId("seller-reply").filter({ hasText: text })).toBeVisible();

  await page.reload({ waitUntil: "load" });
  await expect(card.getByTestId("seller-reply").filter({ hasText: text })).toBeVisible();
  await expect(card.getByRole("button", { name: /^Helpful, 1/ })).toBeVisible();
});

test("QA-053: All filters has Review score, Trust rating and Budget, and they reach the URL", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/search`, { waitUntil: "load" });
  await page.getByRole("button", { name: "All filters" }).click();
  const sheet = page.getByRole("dialog", { name: "Filters" });
  for (const heading of ["Review score", "Trust rating", "Budget", "Time", "Category"]) {
    await expect(sheet.getByRole("heading", { name: heading, exact: true })).toBeVisible();
  }
  // FilterChips (Screen/Search/Reviews/Filters 7762:9999); budget is a chip per stop.
  for (const name of ["Controversial", "80–100", "Up to ₱2,500"]) {
    const chip = sheet.getByRole("button", { name, exact: true });
    await chip.click();
    await expect(chip).toHaveAttribute("aria-pressed", "true");
  }
  // Each definition is a tap away (QA-053).
  await sheet.getByRole("button", { name: "About review score" }).click();
  await expect(sheet.getByText(/Hidden Gems/).first()).toBeVisible();
  await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
  await expect(page).toHaveURL(/lens=controversial/);
  await expect(page).toHaveURL(/trust=high/);
  await expect(page).toHaveURL(/max_price=2500/);
  for (const chip of ["Controversial", "Trust 80–100", "Up to ₱2,500"]) {
    await expect(page.getByRole("button", { name: `${chip}. Change filters` })).toBeVisible();
  }
});

test("QA-006: a review without an affiliate link links its marketplace listing, labelled", async ({ page }) => {
  const full = await api(null, `/api/v1/reviews/${fx.reviews.fresh}/full`);
  expect(full.status).toBe(200);
  const body = full.body as { review: { referral_redirect_url: string | null }; listing_url: string | null };
  test.skip(Boolean(body.review.referral_redirect_url), "this fixture review has an affiliate link");
  expect(body.listing_url).toMatch(/^https:\/\/shopee\.ph\//);

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${BASE}/reviews/${fx.reviews.fresh}`, { waitUntil: "load" });
  const link = page.getByTestId("listing-link");
  await expect(link).toHaveText(/View on Shopee/);
  await expect(link).toHaveAttribute("href", body.listing_url!);
  await expect(link).toHaveAttribute("rel", /nofollow/);
  await expect(page.getByText("Not an affiliate link — nobody earns from this click.", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("listing-link-mobile")).toBeVisible();
});

import { existsSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * The capstone defense walkthrough, end to end, on the defense dataset.
 *
 * Runs against the REAL stack (production Next build, FastAPI, Postgres)
 * seeded by `python -m scripts.defense.seed`, and signs every persona in
 * through the real one-time-code flow: the API's console email provider logs
 * each code, and E2E_API_LOG points at that log. Each scene is one part of the
 * presentation, in presentation order, and every stop is photographed at
 * desktop and phone width into test-results/defense/ for the team to review.
 *
 * The scenes change real state (a vote, a Best Answer, a moderator's
 * decisions), so the walkthrough runs once, serially, never retried - and
 * never against the TEST project the panel will see: CI runs it on its own
 * database, and the defense data on TEST is re-seeded, not rehearsed on.
 *
 * Env: DEFENSE_SEED (the seed's --out JSON), E2E_API_LOG, and optionally
 * DEFENSE_IMAGES (the seed's --image-cache): on a local database review photos
 * point at a host that does not exist, and the cached product pictures stand
 * in for them so the screenshots look like the site.
 */

const SEED = process.env.DEFENSE_SEED;
const API_LOG = process.env.E2E_API_LOG;
const IMAGES = process.env.DEFENSE_IMAGES;
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const SHOTS = path.join("test-results", "defense");

type Seed = {
  target: string;
  personas: Record<string, { username: string; email: string; id: string }>;
  products: Record<string, string>;
  stores: Record<string, string>;
  reviews: Record<string, string>;
  questions: Record<string, string>;
};
const seed: Seed = SEED ? JSON.parse(readFileSync(SEED, "utf8")) : ({} as Seed);

test.skip(!SEED || !API_LOG, "needs the seeded defense stack (DEFENSE_SEED, E2E_API_LOG)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(180_000);

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

/** The newest code the console provider logged for `email`. */
function latestCode(email: string): string | null {
  const lines = readFileSync(API_LOG!, "utf8").split("\n").filter((l) => l.includes(email));
  for (const line of lines.reverse()) {
    const m = line.match(/"code":\s*"(\d{6})"/);
    if (m) return m[1];
  }
  return null;
}

/** Local review photos name their product; serve its cached picture. */
async function servePhotos(context: BrowserContext) {
  if (!IMAGES) return;
  await context.route(/^https:\/\/local\.supabase\.co\//, async (route) => {
    const key = route.request().url().match(/\/([a-z0-9_]+)-[0-9a-f]{32}\.jpg/)?.[1];
    const file = key ? path.join(IMAGES, `${key}.img`) : "";
    if (file && existsSync(file)) {
      await route.fulfill({ status: 200, body: readFileSync(file) });
    } else {
      await route.fulfill({ status: 404, body: "" });
    }
  });
}

/** Sign in through the real form: email, emailed code, Continue. */
async function signIn(page: Page, persona: string): Promise<void> {
  const email = seed.personas[persona].email;
  const before = latestCode(email);
  await page.goto(`${BASE}/login`, { waitUntil: "load" });
  await page.locator('input[name="email"]').fill(email);
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByLabel("Digit 1")).toBeVisible();
  let code: string | null = null;
  await expect
    .poll(() => {
      code = latestCode(email);
      return code !== null && code !== before;
    }, { timeout: 15_000 })
    .toBe(true);
  for (const [i, digit] of [...code!].entries()) {
    await page.getByLabel(`Digit ${i + 1}`).fill(digit);
  }
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 20_000 });
}

/** A fresh browser for one persona, signed in unless it is the visitor. */
async function open(browser: import("@playwright/test").Browser, persona: string | null) {
  const context = await browser.newContext({ viewport: DESKTOP });
  await servePhotos(context);
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  if (persona) await signIn(page, persona);
  return { context, page, errors };
}

/**
 * Photograph a stop at desktop and phone width, after checking it is clean:
 * rendered, no sideways scroll, and no placeholder or broken-value text.
 */
async function stop(page: Page, name: string, url?: string) {
  if (url) {
    const res = await page.goto(`${BASE}${url}`, { waitUntil: "load" });
    expect(res?.status(), `${url} status`).toBe(200);
  }
  await page.locator("main").first().waitFor();
  await page.waitForLoadState("networkidle", { timeout: 5_000 }).catch(() => undefined);
  mkdirSync(SHOTS, { recursive: true });
  for (const [label, size] of [["desktop", DESKTOP], ["phone", PHONE]] as const) {
    await page.setViewportSize(size);
    await page.waitForTimeout(250);
    const facts = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      junk: [...document.body.innerText.matchAll(/\b(undefined|NaN|null|lorem ipsum|\[object Object\])\b/gi)]
        .map((m) => m[0]),
    }));
    expect(facts.overflow, `${name} @${label}: sideways scroll`).toBeLessThanOrEqual(0);
    expect(facts.junk, `${name} @${label}: placeholder text`).toEqual([]);
    await page.screenshot({ path: path.join(SHOTS, `${name}-${label}.png`) });
  }
  await page.setViewportSize(DESKTOP);
}

/** The iPhone 17's real Shopee affiliate link (scripts/defense/dataset.py). */
const IPHONE_LINK = "https://s.shopee.ph/7AdQOJz8uS";

/** The signed-in page's own session token, for reading back through the API. */
async function sessionToken(context: BrowserContext): Promise<string> {
  const cookie = (await context.cookies()).find((c) => c.name === "bluntly_session");
  return cookie?.value ?? "";
}

async function api(pathname: string) {
  const res = await fetch(`${API}${pathname}`);
  return res.json();
}

/* ------------------------------------------------------------------ scenes */

test("1 · a visitor browses, searches and reads", async ({ browser }) => {
  const { context, page, errors } = await open(browser, null);
  await stop(page, "01-home", "/");
  await stop(page, "02-feed", "/feed");
  await expect(page.getByRole("heading", { name: "For you" })).toBeVisible();

  // A search alias (§6): "PowerCore" is the 737's old name, and finds it.
  await stop(page, "03-search", "/search?q=powercore");
  await expect(page.getByText(/Anker 737 Power Bank/).first()).toBeVisible();
  await expect(page.getByText(/Anker Nano/)).toHaveCount(0);

  // A review with its three-month update in the same thread (§2).
  await stop(page, "04-review-thread", `/reviews/${seed.reviews.m_anker737}`);
  const thread = (await api(`/api/v1/reviews/${seed.reviews.m_anker737}/thread`)) as
    { entries: { title: string; is_latest: boolean }[] };
  expect(thread.entries.length).toBeGreaterThanOrEqual(2);
  const latest = thread.entries.find((e) => e.is_latest)!;
  await expect(page.getByText(latest.title).first()).toBeVisible();

  // Price history from both marketplaces (§16).
  await stop(page, "05-review-prices", `/reviews/${seed.reviews.m_iphone17}`);
  const prices = (await api(`/api/v1/products/${seed.products.iphone_17}/prices`)) as { platforms: string[] };
  expect([...prices.platforms].sort()).toEqual(["lazada", "shopee"]);

  await stop(page, "06-questions", "/questions");
  await stop(page, "07-question", `/questions/${seed.questions.q_737_recharge}`);
  await stop(page, "08-store", `/sellers/${seed.stores.powerhub}`);
  await expect(page.getByRole("heading", { name: "PowerHub PH" }).first()).toBeVisible();
  await stop(page, "09-requests", "/requests");
  await stop(page, "10-reviewer-profile", `/u/${seed.personas.kristine.username}`);
  expect(errors).toEqual([]);
  await context.close();
});

test("2 · a new reviewer signs in with an emailed code and votes", async ({ browser }) => {
  const { context, page, errors } = await open(browser, "paolo");
  await stop(page, "11-new-reviewer-dashboard", "/dashboard");
  await stop(page, "12-review-to-vote", `/reviews/${seed.reviews.k_p20i}`);
  const up = page.getByRole("button", { name: /^Helpful, / }).first();
  await expect(up).toHaveAttribute("aria-pressed", "false");
  await up.click();
  await expect(up).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: /^Helpful, / }).first()).toHaveAttribute("aria-pressed", "true");
  // The composer, one question per screen (§1): product, experience, verdict,
  // stars, pros and cons, who it is not for, photo, title, price paid.
  await stop(page, "13-write-a-review", "/reviews/new");
  await page.getByLabel("Search for the product you bought").fill("soundcore liberty");
  await page.getByRole("button", { name: /Soundcore Liberty 4 NC/ }).first().click();
  await page.getByRole("textbox").first().fill(
    "Two months of daily jeepney and MRT commutes. The noise cancelling takes the edge off " +
      "the engine rumble, and one charge of the case lasts me the whole work week.",
  );
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Yes, absolutely/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("radio", { name: "4.5 stars", exact: true }).check({ force: true });
  await page.getByRole("button", { name: "Continue" }).click();
  for (const chip of ["Portable", "Easy to use", "Too expensive"]) {
    await page.getByRole("button", { name: chip, exact: true }).click();
  }
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("textbox").first().fill("Audiophiles who want a studio-flat sound");
  await page.getByRole("button", { name: "Continue" }).click();
  // No photo from this browser: the review publishes, unverified, and can
  // be verified later with one (§1). A photo is what makes it earn.
  await page.getByRole("button", { name: /Skip – I.ll add a photo later/ }).click();
  await page.getByPlaceholder("Your interesting title here...").fill("Quiet commutes, all week");
  await page.getByRole("button", { name: "No, I bought it myself" }).click();
  await stop(page, "13b-composer-final-step");
  await page.getByRole("button", { name: "Submit" }).click();
  const money = page.getByRole("dialog");
  await money.getByPlaceholder("How much was it?").fill("4999");
  await money.getByRole("button", { name: "Lazada", exact: true }).click();
  await money.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your review is now live!" })).toBeVisible();
  await page.getByRole("link", { name: "View my review" }).click();
  await expect(page.getByText("Quiet commutes, all week").first()).toBeVisible();
  await stop(page, "13c-new-review-live");
  expect(errors).toEqual([]);
  await context.close();
});

test("3 · an established reviewer: money, history, and the Best Answer", async ({ browser }) => {
  const { context, page, errors } = await open(browser, "maria");
  await stop(page, "14-wallet", "/dashboard");
  await stop(page, "15-transfer", "/dashboard/transfer");
  await expect(page.getByText("Minimum met")).toBeVisible();
  // Cleared money only (§15): the part still clearing stays in the wallet.
  const before = (await (await fetch(`${API}/api/v1/payouts/balance`, {
    headers: { authorization: `Bearer ${await sessionToken(context)}` },
  })).json()) as { withdrawable: string };
  await page.getByRole("button", { name: /^Request ₱/ }).click();
  await expect(page.getByText(new RegExp(`Requested ₱${Number(before.withdrawable).toFixed(2)}`))).toBeVisible();
  await stop(page, "15b-withdrawal-requested");
  await stop(page, "16-earnings-history", "/dashboard/history");
  await stop(page, "17-notifications", "/notifications");

  await stop(page, "18-own-question", `/questions/${seed.questions.q_nano_ipad}`);
  await page.getByRole("button", { name: "Mark best answer" }).first().click();
  await expect(page.getByText("picked by the person who asked")).toBeVisible();
  const detail = (await api(`/api/v1/questions/${seed.questions.q_nano_ipad}`)) as { best_answer_id: string | null };
  expect(detail.best_answer_id).not.toBeNull();
  expect(errors).toEqual([]);
  await context.close();
});

test("4 · a Stage 3 reviewer's standing", async ({ browser }) => {
  const { context, page, errors } = await open(browser, "kristine");
  await stop(page, "19-stage3-profile", "/profile");
  const trust = (await (await fetch(`${API}/api/v1/users/public/${seed.personas.kristine.username}`)).json()) as
    { trust_stage: number };
  expect(trust.trust_stage).toBe(3);
  expect(errors).toEqual([]);
  await context.close();
});

test("5 · the store owner answers a buyer in public", async ({ browser }) => {
  const { context, page, errors } = await open(browser, "rico");
  await stop(page, "20-seller-dashboard", `/sellers/${seed.stores.powerhub}/dashboard`);
  await page.goto(`${BASE}/sellers/${seed.stores.powerhub}`, { waitUntil: "load" });
  await page.getByRole("button", { name: "Respond as the store" }).first().click();
  await page.getByLabel("Your public response").fill(
    "Salamat sa review! We now ship every power bank with a printed warranty card.",
  );
  await page.getByRole("button", { name: "Post response" }).click();
  await expect(page.getByText("We now ship every power bank with a printed warranty card.")).toBeVisible();
  await stop(page, "21-store-response");
  expect(errors).toEqual([]);
  await context.close();
});

test("6 · the moderator works every queue", async ({ browser }) => {
  test.setTimeout(300_000);
  const { context, page, errors } = await open(browser, "administrator");
  await stop(page, "22-console-overview", "/admin");

  // The earnings queue: a review that passed the helpfulness gate (§3).
  await stop(page, "23-review-queue", "/admin/review-queue");
  await page.getByRole("row").filter({ hasText: "Apple iPhone 17" }).first().click();
  // The row opens the review modal; Approve earnings opens its confirm dialog.
  await page.getByRole("button", { name: "Approve earnings" }).first().click();
  await page
    .getByRole("dialog", { name: "Approve earnings?" })
    .getByRole("button", { name: "Approve earnings" })
    .click();
  await expect
    .poll(async () => ((await api(`/api/v1/reviews/${seed.reviews.c_mark_iphone}`)) as
      { earn_eligible_status: string }).earn_eligible_status)
    .toBe("approved");

  // The catalogue: a new product is named, a duplicate is attached (§5).
  await stop(page, "24-products", "/admin/products");
  // Figma Products Queue (7966:11087) -> Edit -> Add to catalogue (7970:11467).
  const xiaomi = page.getByTestId("queue-row").filter({ hasText: "xiaomi power bank 20000mah" });
  await xiaomi.hover();
  await xiaomi.getByRole("button", { name: "Edit" }).click();
  const naming = page.getByRole("dialog", { name: "Add to catalogue" });
  await naming.getByLabel("Brand", { exact: true }).fill("Xiaomi");
  await naming.getByLabel("Line", { exact: true }).fill("Power Bank");
  await naming.getByRole("button", { name: "Add part" }).click();
  await naming.getByLabel("Variant", { exact: true }).fill("20,000mAh, 22.5W");
  await expect(naming.getByTestId("saves-as")).toHaveText("Xiaomi Power Bank 20,000mAh, 22.5W");
  await naming.getByRole("button", { name: "Add to catalogue" }).click();
  await expect(naming).toBeHidden();
  // MQA-004: the new product reopens in Edit, so its name can be checked and
  // changed straight away; the walkthrough closes it and carries on.
  const named = page.getByRole("dialog", { name: "Edit product" });
  await expect(named.getByText(/Added to the catalogue/)).toBeVisible();
  await named.getByRole("button", { name: "Close" }).first().click();
  await expect(named).toBeHidden();

  // A duplicate is merged into the product it duplicates (§5).
  const dup = page.getByTestId("queue-row").filter({ hasText: "anker nano powerbank 10k" });
  await dup.hover();
  await dup.getByRole("button", { name: "Edit" }).click();
  const nano = (await api(`/api/v1/products/${seed.products.anker_nano_10k}`)) as { canonical_name: string };
  const merging = page.getByRole("dialog", { name: "Add to catalogue" });
  // By role: the closed "Merge into …?" confirm also carries that name.
  await merging.getByRole("textbox", { name: "Merge into" }).fill(nano.canonical_name.slice(0, 20));
  await merging.getByRole("button", { name: nano.canonical_name }).click();
  await merging.getByRole("button", { name: "Merge into product" }).click();
  await expect(merging).toBeHidden();
  await stop(page, "25-products-after");

  // Prices: the outlier waits for a glance, and is rejected (§16).
  await stop(page, "26-prices", "/admin/prices");
  // The seeded outlier is the iPhone 17's; scoped to it so a database with
  // other pending prices (a shared local one) still finds exactly this row.
  const outlier = page.getByRole("row").filter({ hasText: "Far outside the usual range" }).filter({ hasText: "Apple iPhone 17" });
  await expect(outlier).toHaveCount(1);
  await outlier.getByPlaceholder("Note (optional)").fill("Far below every other report for this model.");
  await outlier.getByRole("button", { name: "Reject" }).click();
  await expect(outlier).toHaveCount(0);

  // Reports: the urgent one - a phone number in a review - is taken down (§12).
  await stop(page, "26b-reports", "/admin/review-queue?tab=report");
  // One table row per report; the decision is in its modal (the 2026-10-02 queue redesign).
  await page.locator("tbody tr", { hasText: "Contains a phone number" }).first().click();
  const urgent = page.getByRole("dialog");
  await urgent.getByPlaceholder("Note for the audit log (optional)").fill("Phone number and an off-platform sale.");
  await urgent.getByRole("button", { name: "Remove content" }).click();
  await urgent.getByRole("button", { name: "Confirm removal" }).click();
  await expect
    .poll(async () => (await fetch(`${API}/api/v1/reviews/${seed.reviews.c_hazel_p20i}`)).status)
    .toBe(404);

  // Affiliate links: the review approved above gets its marketplace link (§4).
  await stop(page, "27-affiliate-links", "/admin/affiliate-links?tab=links");
  const waiting = page.getByRole("listitem").filter({ hasText: "Great phone, but 128GB fills up fast" });
  await waiting.getByRole("button", { name: "Attach affiliate link" }).click();
  await waiting.getByLabel("Affiliate link").fill(IPHONE_LINK);
  await waiting.getByRole("button", { name: "Attach", exact: true }).click();
  await expect
    .poll(async () => ((await api(`/api/v1/reviews/${seed.reviews.c_mark_iphone}`)) as
      { earn_eligible_status: string }).earn_eligible_status)
    .toBe("monetized");

  // Stores: the pending claim with its DTI registration is approved (§9).
  await stop(page, "28-sellers", "/admin/sellers");
  const claim = page.getByTestId("claim-row").filter({ hasText: "Cebu Gadget Hub" }).first();
  await expect(claim.getByText("DTI 5902144")).toBeVisible(); // registrationLabel: the kind once (Figma 7992:11327)
  await claim.getByRole("button", { name: "Review" }).click();
  await page.getByRole("dialog", { name: "Review claim" }).getByRole("button", { name: "Approve", exact: true }).click();
  await page.getByRole("button", { name: "Confirm approval" }).click();
  await expect
    .poll(async () => ((await api(`/api/v1/sellers/${seed.stores.cebuhub}`)) as { claim_status: string }).claim_status)
    .toBe("claimed");

  // People: the member under investigation (§12).
  await stop(page, "29-users", "/admin/users");
  await stop(page, "30-honesty-fund", "/admin/honesty-fund");
  await stop(page, "31-analytics", "/admin/analytics");
  await stop(page, "32-activity-log", "/admin/activity");
  expect(errors).toEqual([]);
  await context.close();
});

test("7 · every stop holds at 320, 768 and 1440", async ({ browser }) => {
  const stops = ["/", "/feed", `/reviews/${seed.reviews.m_anker737}`, `/questions/${seed.questions.q_nano_ipad}`,
    `/sellers/${seed.stores.powerhub}`, "/search?q=power%20bank", "/requests"];
  for (const width of [320, 768, 1440]) {
    const context = await browser.newContext({ viewport: { width, height: 900 } });
    await servePhotos(context);
    const page = await context.newPage();
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    for (const url of stops) {
      const res = await page.goto(`${BASE}${url}`, { waitUntil: "load" });
      expect(res?.status(), `${url} @${width}`).toBe(200);
      await page.locator("main").first().waitFor();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `${url} @${width}px sideways scroll`).toBeLessThanOrEqual(0);
    }
    expect(errors, `page errors @${width}`).toEqual([]);
    await context.close();
  }
});

import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Figma round-2 parity (2026-09-24), against the REAL stack seeded by
 * backend/scripts/e2e_fixtures.py. Frames read that day from file
 * lso4Ri4hDaZxvCebhUqlY5 — see docs/FIGMA_ROUND2_VERIFICATION.md.
 *
 * Every control asserted here must DO something: each journey reads the
 * outcome (the URL the API is asked for, the rows shown, the API itself),
 * never just that a pill or button is drawn. Phone and desktop where the
 * layout differs.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  tag: string;
  users: Record<string, { id: string; token: string; username: string }>;
  products: { fan: string; fan_name: string };
  reviews: { old: string; fresh: string; doomed: string };
  store: string;
  store_name: string;
  open_store: string;
  open_store_name: string;
  comment: string;
  beauty_review: string;
  half_star_seller_review: string;
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });

const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1280, height: 900 };

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

/**
 * Choose an option in a sheet the way a person does: by its label. The native
 * input is visually hidden under the drawn mark (FilterSheet), so a click on
 * the input's own box would land on the mark; the label is the target.
 */
async function pick(scope: ReturnType<Page["getByRole"]>, role: "checkbox" | "radio", name: string, on = true) {
  const input = scope.getByRole(role, { name, exact: true });
  if ((await input.isChecked()) !== on) {
    await input.locator("xpath=ancestor::label[1]").click();
  }
  await expect(input).toBeChecked({ checked: on });
}

/** A FilterChip (7808:9228) in the search filter sheet: a pressed toggle. */
async function chip(scope: ReturnType<Page["getByRole"]>, name: string, on = true) {
  const button = scope.getByRole("button", { name, exact: true });
  if ((await button.getAttribute("aria-pressed")) !== String(on)) await button.click();
  await expect(button).toHaveAttribute("aria-pressed", String(on));
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
}

/* ------------------------------------------------------------ QA-024 share */

for (const [name, viewport, hasTouch] of [
  ["desktop", DESKTOP, false],
  ["phone", PHONE, true],
] as const) {
  test(`QA-024 (${name}): Share to… lists Figma's destinations, each carrying this review's link`, async ({ browser }) => {
    const context = await browser.newContext({ viewport, hasTouch, isMobile: hasTouch });
    const page = await context.newPage();
    await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
    await page.getByRole("button", { name: "Share" }).first().click();
    const sheet = page.getByRole("dialog", { name: "Share to…" });
    await expect(sheet).toBeVisible();

    const link = `${BASE}/reviews/${fx.reviews.old}`;
    const destinations = sheet.getByRole("list", { name: "Share to" }).getByRole("link");
    const names = await destinations.allInnerTexts();
    const expected = hasTouch
      ? ["Facebook", "Messenger", "Reddit", "X", "Viber", "Telegram", "WhatsApp"]
      : ["Facebook", "Reddit", "X", "Telegram", "WhatsApp"];
    expect(names.map((n) => n.trim())).toEqual(expected);
    for (let i = 0; i < expected.length; i++) {
      const href = await destinations.nth(i).getAttribute("href");
      expect(href, expected[i]).toContain(encodeURIComponent(link));
      expect(await destinations.nth(i).getAttribute("target")).toBe("_blank");
      expect(await destinations.nth(i).getAttribute("rel")).toContain("noopener");
    }
    // Not drawn: Instagram (no web share address) and Bookmark (omitted by decision).
    await expect(sheet.getByText("Instagram")).toHaveCount(0);
    await expect(sheet.getByText("Bookmark")).toHaveCount(0);
    await expect(sheet.getByRole("button", { name: "Copy link" })).toBeVisible();
    // The preview card carries the review's own words.
    await expect(sheet.getByText("Quiet on low, loud on turbo", { exact: false })).toBeVisible();
    // A reader is not told to "boost your commission".
    await expect(sheet.getByText("boost your commission")).toHaveCount(0);
    await noOverflow(page);
    await context.close();
  });
}

test("QA-024: the author's own share sheet carries the author prompt", async ({ page, context }) => {
  await as(context, "reviewer");
  await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
  await page.getByRole("button", { name: "Share" }).first().click();
  const sheet = page.getByRole("dialog", { name: "Share to…" });
  // No affiliate link on this review, so no commission is promised.
  await expect(sheet.getByText("Share your post on other platforms to get more views.")).toBeVisible();
  await expect(sheet.getByText("boost your commission")).toHaveCount(0);
});

/* ------------------------------------------------------ QA-020 comment rows */

test("QA-020: every comment has the same row; the author's Delete lives in its ⋯", async ({ page, context }) => {
  // Its own two comments — the viewer's and someone else's — so both kinds of
  // row are on the page whatever other journeys do to the fixture comment.
  const own = await api("commenter", `/api/v1/reviews/${fx.reviews.fresh}/comments`, {
    method: "POST", body: JSON.stringify({ body: `My own view ${fx.tag}` }),
  });
  const other = await api("voter", `/api/v1/reviews/${fx.reviews.fresh}/comments`, {
    method: "POST", body: JSON.stringify({ body: `Someone else's view ${fx.tag}` }),
  });
  expect([own.status, other.status]).toEqual([201, 201]);
  const ownId = (own.body as { id: string }).id;
  const otherId = (other.body as { id: string }).id;

  await as(context, "commenter");
  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/reviews/${fx.reviews.fresh}`, { waitUntil: "load" });
  const mine = page.locator(`#comment-${ownId}`);
  const theirs = page.locator(`#comment-${otherId}`);
  for (const row of [mine, theirs]) {
    await expect(row.getByRole("button", { name: /^Helpful, / })).toBeVisible();
    await expect(row.getByRole("button", { name: /^Not helpful, / })).toBeVisible();
    await expect(row.getByRole("button", { name: "Reply" })).toBeVisible();
    await expect(row.getByRole("button", { name: "Share" })).toBeVisible();
    // Delete is never in the row itself any more.
    await expect(row.getByRole("button", { name: "Delete", exact: true })).toHaveCount(0);
  }
  // The ⋯ holds each comment's own actions: Delete on the viewer's own
  // comment only; Report, Follow and Save on anyone else's (QA-069, round 3 —
  // before it, another member's comment had no ⋯ because nothing went in it).
  await mine.getByRole("button", { name: "More actions for this comment" }).click();
  await expect(mine.getByRole("menuitem")).toHaveText(["Delete"]);
  await page.keyboard.press("Escape");
  await expect(mine.getByRole("menuitem", { name: "Delete" })).toHaveCount(0);
  await theirs.getByRole("button", { name: "More actions for this comment" }).click();
  await expect(theirs.getByRole("menuitem")).toHaveText(["Report", "Follow comment", "Save comment"]);
  await page.keyboard.press("Escape");
  await expect(theirs.getByRole("menuitem")).toHaveCount(0);
  // The byline carries the Honesty Score, as the frame draws it.
  await expect(theirs.getByRole("img", { name: /\b80\b/ })).toBeVisible();
  await noOverflow(page);
});

/* ---------------------------------------- comment sort is the dropdown */

test("Comment sort opens the dropdown menu; By date reorders ties at once", async ({ page }) => {
  // Two unvoted comments: equally helpful, so the date order decides.
  const first = await api("commenter", `/api/v1/reviews/${fx.reviews.fresh}/comments`, {
    method: "POST", body: JSON.stringify({ body: `Earlier view ${fx.tag}` }),
  });
  const second = await api("voter", `/api/v1/reviews/${fx.reviews.fresh}/comments`, {
    method: "POST", body: JSON.stringify({ body: `Later view ${fx.tag}` }),
  });
  expect([first.status, second.status]).toEqual([201, 201]);
  const ids = [(first.body as { id: string }).id, (second.body as { id: string }).id];
  const position = async () => {
    const order = await page.locator("[id^='comment-']").evaluateAll((els) => els.map((e) => e.id));
    return ids.map((id) => order.indexOf(`comment-${id}`));
  };

  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/reviews/${fx.reviews.fresh}`, { waitUntil: "load" });
  const [earlier, later] = await position();
  expect(later).toBeLessThan(earlier); // Latest first by default.

  const pill = page.getByRole("button", { name: /^Most helpful/ });
  await expect(pill).toHaveAttribute("aria-haspopup", "menu");
  await pill.click();
  const menu = page.getByRole("menu", { name: "Sort comments" });
  await expect(menu.getByRole("group")).toHaveCount(2);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(menu.getByRole("menuitemradio", { name: "Latest" })).toHaveAttribute("aria-checked", "true");
  await menu.getByRole("group", { name: "By date" }).getByRole("menuitemradio", { name: "Oldest" }).click();
  await expect(menu).toHaveCount(0);
  await expect(pill).toBeFocused();
  const [earlier2, later2] = await position();
  expect(earlier2).toBeLessThan(later2);
  // Rating kept its value; date shows the new one.
  await pill.click();
  await expect(menu.getByRole("menuitemradio", { name: "Most helpful" })).toHaveAttribute("aria-checked", "true");
  await expect(menu.getByRole("menuitemradio", { name: "Oldest" })).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await noOverflow(page);
});

/* ------------------------------------------- QA-025 / QA-053 All filters */

test("QA-025/053 (phone): several categories and a period filter the results for real", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?q=${fx.tag}`, { waitUntil: "load" });
  // When the search names a product, the phone draws Figma's ListHeader/Reviews
  // (7702:7593): the same sheet behind a "Filters" chip (PIM 923fc35). The
  // sheet is Screen/Search/Reviews/Filters (7762:9999): FilterChips, applied
  // by its "Show reviews" pill.
  const filters = page.getByRole("button", { name: /^(All filters|Filters)$/ });
  await filters.click();
  const sheet = page.getByRole("dialog", { name: "Filters" });
  await chip(sheet, "Beauty");
  await chip(sheet, "Electronics & Tech");
  // Both stay pressed: several at once (QA-025).
  await expect(sheet.getByRole("button", { name: "Beauty", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(sheet.getByRole("button", { name: "All", exact: true }).last()).toHaveAttribute("aria-pressed", "false");
  await chip(sheet, "Past month");
  await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();

  await page.waitForURL(/category=beauty%2Celectronics-tech/);
  expect(page.url()).toContain("period=month");
  // Both categories' reviews are in the results; the four-month-old fan review is not.
  await expect(page.getByRole("heading", { name: `Gentle soap ${fx.tag}` })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tiny and quick" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Great fan for commuting" })).toHaveCount(0);
  // The applied chips follow the hairline.
  await expect(page.getByRole("button", { name: "Beauty. Change filters" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Past month. Change filters" })).toBeVisible();

  // Only Beauty: the electronics reviews go.
  await filters.click();
  await chip(sheet, "Electronics & Tech", false);
  await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
  await expect(page.getByRole("heading", { name: "Tiny and quick" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: `Gentle soap ${fx.tag}` })).toBeVisible();
  await noOverflow(page);
});

test("QA-053 (phone): Sort offers Oldest from the dropdown, and it reorders", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?q=${fx.tag}&category=electronics-tech`, { waitUntil: "load" });
  // With a product named, ListHeader/Reviews labels the sort chip with the
  // current order ("Most helpful"); otherwise it is the "Sort" pill (923fc35).
  // It opens the Menu of Screen/Search/Reviews/Sort open (7762:9948): the
  // current order checked, a tap applies.
  const pill = page.getByRole("button", { name: /^(Sort|Most helpful|Newest|Oldest)$/ });
  await pill.click();
  const menu = page.getByRole("menu", { name: "Sort reviews" });
  await expect(menu.getByRole("menuitemradio", { name: "Most helpful" })).toHaveAttribute("aria-checked", "true");
  await expect(menu.getByRole("menuitemradio")).toHaveText(["Most helpful", "Newest", "Oldest", "Lowest rated"]);
  const box = await menu.boundingBox();
  expect(Math.round(box!.width)).toBe(220);
  // Escape closes it without a change and gives the pill its focus back.
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(pill).toBeFocused();
  await pill.click();
  await menu.getByRole("menuitemradio", { name: "Oldest" }).click();
  await page.waitForURL(/sort=oldest/);
  const titles = await page.locator("main li h2").allInnerTexts();
  expect(titles[0]).toContain("Great fan for commuting"); // the four-month-old one first
});

test("QA-025 (desktop): the rail's categories add to the set rather than replace it", async ({ page }) => {
  await page.setViewportSize(DESKTOP);
  await page.goto(`${BASE}/search?q=${fx.tag}&category=beauty`, { waitUntil: "load" });
  await page.getByRole("link", { name: "Electronics & Tech" }).click();
  await page.waitForURL(/category=beauty%2Celectronics-tech/);
  await expect(page.getByRole("link", { name: "Beauty" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("link", { name: "Electronics & Tech" })).toHaveAttribute("aria-pressed", "true");
});

/* --------------------------------------------------- QA-050 Questions tab */

test("QA-050: the Questions tab draws the pills, and Sort orders by date", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?tab=questions&q=${fx.tag}`, { waitUntil: "load" });
  await expect(page.getByRole("button", { name: "All filters" })).toBeVisible();
  await page.getByRole("button", { name: "Sort" }).click();
  await page.getByRole("menu", { name: "Sort questions" }).getByRole("menuitemradio", { name: "Oldest" }).click();
  await page.waitForURL(/sort=oldest/);
  expect(page.url()).toContain("tab=questions");
  await page.getByRole("button", { name: "All filters" }).click();
  await chip(page.getByRole("dialog", { name: "Filters" }), "Past year");
  await page.getByRole("button", { name: "Show questions" }).click();
  await page.waitForURL(/period=year/);
  await expect(page.getByText("Does it get hot after an hour on turbo?", { exact: false })).toBeVisible();
});

/* ------------------------------------------- search filters, step 2 */

test("Filters step 2 (phone): Rating and Show only filter for real, and the pill counts first", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?q=${fx.tag}`, { waitUntil: "load" });
  await page.getByRole("button", { name: /^(All filters|Filters)$/ }).click();
  const sheet = page.getByRole("dialog", { name: "Filters" });
  // The frame's groups first (7762:9999): Rating, then Show only.
  await expect(sheet.getByRole("group", { name: "Rating", exact: true })).toBeVisible();
  await expect(sheet.getByRole("group", { name: "Show only" }).locator("[data-chip]")).toHaveText([
    "With photos", "Verified buyers", "Recommends it",
  ]);
  await chip(sheet, "5 ★");
  // The pill says how many before anything is applied — the API's own count.
  const expected = (await api(null, `/api/v1/reviews/feed/count?q=${fx.tag}&stars=5`)).body as { total: number };
  const noun = expected.total === 1 ? "review" : "reviews";
  await expect(sheet.getByRole("button", { name: `Show ${expected.total} ${noun}` })).toBeVisible();
  await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
  await page.waitForURL(/stars=5/);
  await expect(page.getByRole("button", { name: "5★. Change filters" })).toBeVisible();
  // Show only narrows further, and Reset in the sheet clears both.
  await page.getByRole("button", { name: "5★. Change filters" }).click();
  await chip(sheet, "Recommends it");
  await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
  await page.waitForURL(/recommends=1/);
  expect(page.url()).toContain("stars=5");
  await noOverflow(page);
});

test("Lowest rated is in the review Sort menu and orders by stars", async ({ page }) => {
  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?q=${fx.tag}`, { waitUntil: "load" });
  await page.getByRole("button", { name: /^(Sort|Most helpful|Newest|Oldest)$/ }).click();
  const menu = page.getByRole("menu", { name: "Sort reviews" });
  await expect(menu.getByRole("menuitemradio")).toHaveText(["Most helpful", "Newest", "Oldest", "Lowest rated"]);
  await menu.getByRole("menuitemradio", { name: "Lowest rated" }).click();
  await page.waitForURL(/sort=lowest/);
  const rows = (await api(null, `/api/v1/reviews/feed?q=${fx.tag}&sort=lowest&limit=50`)).body as {
    review: { star_rating: number | string };
  }[];
  const stars = rows.map((r) => Number(r.review.star_rating));
  expect(stars).toEqual([...stars].sort((a, b) => a - b));
});

/* ----------------------------------------------------- QA-052 Sellers tab */

test("QA-052: the Sellers tab counts answered questions and filters to claimed profiles", async ({ page }) => {
  // Its own unclaimed store: the business-rule claim journey claims the
  // fixture's open store, and files run in no fixed order.
  const unclaimedName = `Unclaimed ${fx.tag}`;
  const made = await api("voter", "/api/v1/sellers", {
    method: "POST", body: JSON.stringify({ display_name: unclaimedName, platform: "shopee" }),
  });
  expect([200, 201]).toContain(made.status);

  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?tab=sellers&q=${fx.tag}`, { waitUntil: "load" });
  const claimedRow = page.getByRole("listitem").filter({ hasText: fx.store_name });
  await expect(claimedRow.getByText("1 question answered")).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: unclaimedName })).toBeVisible();

  // Sheet/Filter sellers (8462:36591): Profile, then Sells on with the logos.
  await page.getByRole("button", { name: "All filters" }).click();
  const sellers = page.getByRole("dialog", { name: "Filter sellers" });
  await expect(sellers.getByRole("button", { name: "Shopee", exact: true })).toBeVisible();
  await chip(sellers, "Claimed by the owner");
  await sellers.getByRole("button", { name: /^Show (\d[\d,]* )?sellers?$/ }).click();
  await page.waitForURL(/claimed=1/);
  await expect(page.getByRole("listitem").filter({ hasText: fx.store_name })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: unclaimedName })).toHaveCount(0);

  // The API agrees: every store it returns is claimed, ours included.
  const res = await api(null, `/api/v1/sellers?q=${fx.tag}&claimed=true`);
  const rows = res.body as { display_name: string; claim_status: string }[];
  expect(rows.map((s) => s.display_name)).toContain(fx.store_name);
  expect(rows.map((s) => s.display_name)).not.toContain(unclaimedName);
  expect(rows.every((s) => s.claim_status === "claimed")).toBe(true);
});


// After QA-052: both load this search, and the list is cached for 60 s, so the
// test that creates a store and then expects it in the plain list must come first.
test("Filter sellers step 2: Unclaimed, Rating and Answers buyers, with the live count", async ({ page }) => {
  const unclaimedName = `Unclaimed two ${fx.tag}`;
  const made = await api("voter", "/api/v1/sellers", {
    method: "POST", body: JSON.stringify({ display_name: unclaimedName, platform: "shopee" }),
  });
  expect([200, 201]).toContain(made.status);

  await page.setViewportSize(PHONE);
  await page.goto(`${BASE}/search?tab=sellers&q=${fx.tag}`, { waitUntil: "load" });
  await page.getByRole("button", { name: "All filters" }).click();
  const sellers = page.getByRole("dialog", { name: "Filter sellers" });
  await expect(sellers.getByRole("group", { name: "Rating", exact: true }).locator("[data-chip]")).toHaveText(["4★ & up", "3★ & up", "Any"]);
  await expect(sellers.getByRole("group", { name: "Answers buyers" }).locator("[data-chip]")).toHaveText([
    "Within a day", "Within a week",
  ]);
  await chip(sellers, "Unclaimed");
  const expected = (await api(null, `/api/v1/sellers/count?q=${fx.tag}&claimed=false`)).body as { total: number };
  await expect(sellers.getByRole("button", { name: `Show ${expected.total} ${expected.total === 1 ? "seller" : "sellers"}` })).toBeVisible();
  await sellers.getByRole("button", { name: /^Show (\d[\d,]* )?sellers?$/ }).click();
  await page.waitForURL(/claimed=0/);
  await expect(page.getByRole("listitem").filter({ hasText: unclaimedName })).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: fx.store_name })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Unclaimed. Change filters" })).toBeVisible();
  // An unreviewed store has no rating, so "4★ & up" leaves it out.
  await page.getByRole("button", { name: "Unclaimed. Change filters" }).click();
  await chip(sellers, "4★ & up");
  await sellers.getByRole("button", { name: /^Show (\d[\d,]* )?sellers?$/ }).click();
  await page.waitForURL(/rating=4/);
  await expect(page.getByRole("listitem").filter({ hasText: unclaimedName })).toHaveCount(0);
  await noOverflow(page);
});

/* ------------------------------------------------- QA-057 seller reviews */

for (const [name, viewport] of [["phone", PHONE], ["desktop", DESKTOP]] as const) {
  test(`QA-057 (${name}): the seller page's All filters and Sort work, half stars included`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(`${BASE}/sellers/${fx.open_store}`, { waitUntil: "load" });
    // The All reviews block; the carousel higher up shows the same reviews.
    const all = page.locator("#all-reviews");
    // Both reviews show — the 4.5 one too, which exact-value matching hid.
    await expect(all.getByText("Arrived early, well packed.")).toBeVisible();
    await expect(all.getByText("Slow to ship.")).toBeVisible();

    // Sort is the dropdown menu (owner 2026-10-07): a choice applies at once.
    await all.getByRole("button", { name: "Sort" }).click();
    const menu = page.getByRole("menu", { name: "Sort reviews" });
    await expect(menu.getByRole("group")).toHaveCount(3);
    await menu.getByRole("menuitemradio", { name: "Lowest" }).click();
    await expect(menu).toHaveCount(0);
    const bodies = all.locator("li").filter({ hasText: /Slow to ship\.|Arrived early/ });
    await expect(bodies.first()).toContainText("Slow to ship.");
    await all.getByRole("button", { name: "Sort" }).click();
    await expect(menu.getByRole("menuitemradio", { name: "Lowest" })).toHaveAttribute("aria-checked", "true");
    await menu.getByRole("menuitemradio", { name: "Highest" }).click();
    await expect(bodies.first()).toContainText("Arrived early, well packed.");

    await all.getByRole("button", { name: "All filters" }).click();
    const sheet = page.getByRole("dialog", { name: "All filters" });
    await pick(sheet, "checkbox", "2 star", false);
    await sheet.getByRole("button", { name: "Filter Reviews" }).click();
    await expect(all.getByText("Slow to ship.")).toHaveCount(0);
    await expect(all.getByText("Arrived early, well packed.")).toBeVisible();
    // The live counter says the filter is narrowing: one of the two reviews.
    await expect(all.getByText(/^1 of 2 reviews$/)).toBeVisible();
    // The rating card's ticks are the same filter: 2 star is unticked there too.
    await expect(all.getByRole("group", { name: "Show reviews with" }).getByRole("checkbox").nth(3)).not.toBeChecked();
    await noOverflow(page);
  });
}

/* ------------------------------------------- QA-001 product image (moderator) */

test("QA-001: a moderator adds a product's picture from the catalogue", async ({ page, context }) => {
  // The real route stores the file in Supabase Storage, which this stack does
  // not have; the API side is pinned by test_product_image_upload.py. Here only
  // the upload request is answered, so what is proven is the moderator's path:
  // the control exists on the product's row, sends the chosen file itself to
  // that product's endpoint, and reports the outcome.
  await as(context, "administrator");
  await page.setViewportSize(DESKTOP);
  const products = fx.products;
  const sent: { method: string; type: string; hasPng: boolean }[] = [];
  await page.route(`**/api/bff/api/v1/products/${products.fan}/image`, async (route) => {
    const req = route.request();
    sent.push({
      method: req.method(),
      type: req.headers()["content-type"] ?? "",
      hasPng: (req.postDataBuffer() ?? Buffer.alloc(0)).includes(Buffer.from("\x89PNG", "latin1")),
    });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: products.fan }) });
  });

  // Figma Products (7966:11087): the picture is set from the row's Edit, in
  // Overlay/Product/Catalogue (7970:11467) for a submission, Edit for a product.
  // The fixture product is still a submission: it waits in the Queue, newest first.
  await page.goto(`${BASE}/admin/products?sort=newest&size=50`, { waitUntil: "load" });
  const row = page.getByTestId("queue-row").filter({ hasText: products.fan_name });
  await row.hover();
  await row.getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog", { name: "Add to catalogue" });
  await expect(dialog.getByRole("button", { name: /(Add|Replace) photo/ })).toBeVisible();

  // Not an image: refused in the browser, nothing is sent.
  await dialog.getByLabel("Product image").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await expect(dialog.getByRole("alert")).toHaveText("That file isn't an image.");
  expect(sent).toHaveLength(0);

  const png = Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "latin1"), Buffer.alloc(64)]);
  await dialog.getByLabel("Product image").setInputFiles({ name: "fan.png", mimeType: "image/png", buffer: png });
  await expect(dialog.getByRole("status")).toHaveText("Photo saved.");
  expect(sent).toEqual([{ method: "POST", type: expect.stringContaining("multipart/form-data"), hasPng: true }]);
});

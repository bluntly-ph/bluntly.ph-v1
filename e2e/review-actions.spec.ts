import { expect, test } from "@playwright/test";

/**
 * Review-detail interactions filed by QA (BUG-014, BUG-015) plus the navigation
 * and 404 fixes (BUG-003, BUG-011).
 *
 * These are the checks a screenshot cannot make: a control that renders but does
 * nothing on click looks identical to a working one until you click it.
 */

const SHOWCASE_REVIEW = "00000000-0000-0000-0000-0000000e0001";

test.describe("BUG-015 — share is clickable", () => {
  test("clicking Share copies the link and says so", async ({ page, context, browserName }) => {
    // The clipboard needs permission in Chromium; Firefox/WebKit don't support
    // granting it, so there we only assert the control responds at all.
    if (browserName === "chromium") {
      await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    }
    await page.goto(`/reviews/${SHOWCASE_REVIEW}`);

    const share = page.getByRole("button", { name: /share/i });
    await expect(share).toBeVisible();
    await share.click();

    // The label is the observable proof the handler ran — before the fix the
    // button had no onClick at all and nothing whatsoever happened.
    await expect(
      page.getByRole("button", { name: /link copied|copy failed/i }),
    ).toBeVisible({ timeout: 5000 });

    if (browserName === "chromium") {
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      expect(copied).toContain(`/reviews/${SHOWCASE_REVIEW}`);
    }
  });
});

test.describe("BUG-014 — the comment surface exists", () => {
  test("a signed-out reader sees the thread and a way to join it", async ({ page }) => {
    await page.goto(`/reviews/${SHOWCASE_REVIEW}`);

    await expect(
      page.getByRole("heading", { name: /comments?$|^\d+ comments?$/i }),
    ).toBeVisible();
    // Signed out: read-only, with a login route that returns here afterwards.
    const join = page.getByRole("link", { name: /^log in$/i }).last();
    await expect(join).toBeVisible();
    await expect(join).toHaveAttribute(
      "href",
      `/login?next=/reviews/${SHOWCASE_REVIEW}`,
    );
    // No composer for a guest — posting is gated server-side too.
    await expect(page.getByRole("textbox", { name: /add a comment/i })).toHaveCount(0);
  });
});

test.describe("BUG-003 — styled 404", () => {
  test("an unknown path returns 404 with a route home", async ({ page }) => {
    const response = await page.goto("/this-page-does-not-exist");
    expect(response?.status()).toBe(404);

    // Not the bare framework error: brand chrome and two ways out.
    await expect(page.getByRole("link", { name: /back home/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /search reviews/i })).toBeVisible();
    await expect(page.locator("footer")).toBeVisible();
  });
});

test.describe("BUG-011 — categories round trip", () => {
  // The All filters pill exists below 1024px only: since 4013c0f (2026-09-16)
  // desktop refines search from the page's "Refine" rail and the pill bar is
  // lg:hidden. At the default 1280px viewport these tests waited 30s for a
  // control the design no longer draws there.
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
  });

  test("a filtered view can get back to /categories", async ({ page }) => {
    await page.goto("/categories");
    await page.getByRole("link", { name: /beauty/i }).first().click();
    await expect(page).toHaveURL(/\/search\?category=beauty&from=categories/);

    // The back link QA asked for.
    await expect(
      page.getByRole("link", { name: /all categories/i }),
    ).toBeVisible();

    // Clearing the category returns to /categories rather than dead-ending on
    // /search. The category lives in the Filters sheet (Figma 7762:9999):
    // Reset clears its chips, its pill applies.
    await page.getByRole("button", { name: "All filters", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Filters" });
    await sheet.getByRole("button", { name: "Reset" }).click();
    await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
    await expect(page).toHaveURL(/\/categories$/);
  });

  test("plain search still treats Reset as 'clear the filter'", async ({ page }) => {
    // The fix must not hijack /search reached any other way.
    await page.goto("/search?category=beauty");
    await expect(
      page.getByRole("link", { name: /all categories/i }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "All filters", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Filters" });
    await sheet.getByRole("button", { name: "Reset" }).click();
    await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
    await expect(page).toHaveURL(/\/search$/);
  });
});

test.describe("BUG-005 — the footer stays put on an empty result set", () => {
  test("footer sits at or below the fold when a filter returns nothing", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // A query that cannot match anything, so the results area collapses.
    await page.goto("/search?q=zzzzqqqqnothingmatchesthis");
    await expect(page.getByText(/no reviews found/i)).toBeVisible();

    const geometry = await page.evaluate(() => {
      const f = document.querySelector("footer")!.getBoundingClientRect();
      const main = document.querySelector("main")!.getBoundingClientRect();
      return {
        viewportH: window.innerHeight,
        docH: document.documentElement.scrollHeight,
        footerTop: f.top + window.scrollY,
        footerBottom: f.bottom + window.scrollY,
        mainBottom: main.bottom + window.scrollY,
      };
    });

    // The real property, measured rather than eyeballed: the footer ends at the
    // document's end (no dead band under it) and reaches at least the fold, so
    // it is anchored rather than floating mid-page.
    expect(geometry.docH - geometry.footerBottom).toBeLessThanOrEqual(1);
    expect(geometry.footerBottom).toBeGreaterThanOrEqual(geometry.viewportH - 1);

    // And the empty state now fills the space above it, so nothing is left but
    // the footer's own 16px top margin — not the tall blank band QA saw.
    expect(geometry.footerTop - geometry.mainBottom).toBeLessThanOrEqual(20);
  });
});

// A search that names a product draws ListHeader/Reviews (7702:7593): the sort
// pill carries the current order and the filter pill reads "Filters".
const SORT = /^(Sort|Most helpful|Newest|Oldest)$/;
const FILTERS = /^(All filters|Filters)$/;

test.describe("search filters and sort — Figma Chip/Action and sheets", () => {
  /**
   * The category strip is replaced by the file's own controls (3481:1776):
   * "All filters" and "Sort" pills, opening the FilterChip sheet (7762:9999)
   * and the sort Menu (7762:9948).
   * The sheets offer only what GET /reviews/feed serves — a category and two
   * orders — so each choice is proven to reach the URL the results are read
   * from, at a phone and a desktop width.
   */
  // Phone and tablet: the pills are lg:hidden, desktop uses the Refine rail
  // (4013c0f). 1440 was the other width here before that change.
  for (const size of [{ width: 390, height: 844 }, { width: 768, height: 1024 }]) {
    test(`a category applies from the All filters sheet at ${size.width}px`, async ({ page }) => {
      await page.setViewportSize(size);
      await page.goto("/search?q=fan");
      await page.getByRole("button", { name: FILTERS }).click();
      const sheet = page.getByRole("dialog", { name: "Filters" });
      await sheet.getByRole("button", { name: "Beauty", exact: true }).click();
      await sheet.getByRole("button", { name: /^Show (\d[\d,]* )?reviews?$/ }).click();
      await expect(page).toHaveURL(/\/search\?q=fan&category=beauty$/);
      // Applied, it shows as a filled chip beside the pills.
      await expect(page.getByRole("button", { name: "Beauty. Change filters" })).toBeVisible();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth),
      ).toBe(false);
    });
  }

  test("Newest applies from the Sort menu, and Most helpful restores the default", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/search?q=fan");
    await page.getByRole("button", { name: SORT }).click();
    await page.getByRole("menuitemradio", { name: "Newest" }).click();
    await expect(page).toHaveURL(/\/search\?q=fan&sort=newest$/);

    await page.getByRole("button", { name: SORT }).click();
    await page.getByRole("menuitemradio", { name: "Most helpful" }).click();
    await expect(page).toHaveURL(/\/search\?q=fan$/);
  });

  test("Escape closes the menu and the sheet without applying, focus back on the pill", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/search?q=fan");
    const sort = page.getByRole("button", { name: SORT });
    await sort.click();
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("menu")).toHaveCount(0);
    await expect(sort).toBeFocused();

    const filters = page.getByRole("button", { name: FILTERS });
    await filters.click();
    const sheet = page.getByRole("dialog", { name: "Filters" });
    await sheet.getByRole("button", { name: "Beauty", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(filters).toBeFocused();
    await expect(page).toHaveURL(/\/search\?q=fan$/);
  });
});

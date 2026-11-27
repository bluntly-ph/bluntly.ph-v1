import { test, expect, type Page } from "@playwright/test";

/**
 * The phone's quick actions, as the current Figma file draws them:
 * QuickActions/Button on the browsing screens and Overlay/QuickActions
 * (8502:40871, signed out 8511:41142). It replaced the "Action Menu.png" FAB
 * (60px, 32px insets, 25% black scrim) that this spec asserted until the
 * 2026-10-06 audit.
 *
 * Geometry is asserted against the frames (390x844): a 56x56 FAB 16px from the
 * right and 24px from the bottom, hidden from 768px up because no frame places
 * it wider; open, a #141414 scrim at 45%.
 *
 * Signed out only. All three destinations sit behind the email-OTP login, which
 * cannot be driven here, so each action is proven to reach its REAL route's
 * guard with the return path intact. Signed in, the same link lands on the
 * workflow itself; that half needs a session and is checked by hand.
 */

const MOBILE = { width: 390, height: 844 };
// Screens whose frames draw QuickActions/Button and render without a record.
const SURFACES = ["/search", "/", "/categories"] as const;
// No frame draws it on these.
const NO_FAB = ["/feed", "/questions"] as const;
const ACTIONS = [
  { name: "Ask a question", path: "/questions/new" },
  { name: "Rate a seller", path: "/sellers/rate" },
  { name: "Write a review", path: "/reviews/new" },
] as const;

test.use({ viewport: MOBILE });

const fab = (page: Page) => page.getByRole("button", { name: /^(Close )?quick actions$/i });
const panel = (page: Page) => page.getByRole("navigation", { name: "Quick actions" });

async function openMenu(page: Page, path = "/search") {
  await page.goto(path);
  await fab(page).click();
  await expect(fab(page)).toHaveAttribute("aria-expanded", "true");
  await expect(panel(page)).toBeVisible();
}

test.describe("mobile quick actions", () => {
  for (const path of SURFACES) {
    test(`the FAB sits 16px from the right and 24px from the bottom on ${path}`, async ({ page }) => {
      await page.goto(path);
      const button = fab(page);
      await expect(button).toBeVisible();
      await expect(button).toHaveAttribute("aria-expanded", "false");
      const box = await button.boundingBox();
      expect(box).not.toBeNull();
      expect(Math.round(box!.width)).toBe(56);
      expect(Math.round(box!.height)).toBe(56);
      expect(Math.round(MOBILE.width - (box!.x + box!.width))).toBe(16);
      expect(Math.round(MOBILE.height - (box!.y + box!.height))).toBe(24);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }

  test("expanding shows the three actions in the drawn order over a 45% scrim", async ({ page }) => {
    await openMenu(page);
    await expect(panel(page).getByRole("link")).toHaveText(ACTIONS.map((a) => a.name));
    await expect(fab(page)).toHaveAttribute("aria-controls", /.+/);
    const scrim = page.locator("[data-quick-actions-scrim]");
    await expect(scrim).toBeVisible();
    // #141414 at 45%; Tailwind v4 serialises it as lab(), so read the alpha.
    const bg = await scrim.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toMatch(/[/,]\s*0\.45\)$/);
  });

  test("Escape closes the menu and returns focus to the FAB", async ({ page }) => {
    await openMenu(page);
    await page.keyboard.press("Escape");
    await expect(panel(page)).toHaveCount(0);
    await expect(fab(page)).toBeFocused();
    await expect(fab(page)).toHaveAttribute("aria-expanded", "false");
  });

  test("tapping the scrim closes the menu without touching the page beneath", async ({ page }) => {
    await openMenu(page);
    const before = page.url();
    await page.mouse.click(40, 200);
    await expect(panel(page)).toHaveCount(0);
    expect(page.url()).toBe(before);
  });

  test("the FAB, turned into a close mark, closes the menu", async ({ page }) => {
    await openMenu(page);
    await page.getByRole("button", { name: "Close quick actions" }).click();
    await expect(panel(page)).toHaveCount(0);
  });

  for (const action of ACTIONS) {
    test(`${action.name} opens its real route, behind sign-in, keeping the return path`, async ({
      page,
    }) => {
      await openMenu(page);
      await panel(page).getByRole("link", { name: action.name }).click();
      await expect(page).toHaveURL(
        new RegExp(`/login\\?next=${encodeURIComponent(action.path)}(&|$)`),
      );
    });
  }

  // Screen/Store/Reviews (7580:12921) draws the FAB too. It needs a store to
  // exist, so it is skipped — and says why — where the API has none.
  test("a store page carries the FAB, and Rate a seller keeps that store", async ({ page }) => {
    await page.goto("/search?q=store&tab=sellers");
    const store = page.locator("main a[href^='/sellers/']:not([href^='/sellers/rate'])").first();
    test.skip((await store.count()) === 0, "No seller record to render a store page against.");
    const href = (await store.getAttribute("href"))!;
    await page.goto(href);
    await expect(fab(page)).toHaveCount(1);
    await fab(page).click();
    const sellerId = href.split("/")[2];
    await expect(panel(page).getByRole("link", { name: "Rate a seller" })).toHaveAttribute(
      "href",
      `/sellers/rate?seller=${sellerId}`,
    );
  });

  for (const path of NO_FAB) {
    test(`no FAB on ${path}, which no frame draws it on`, async ({ page }) => {
      await page.goto(path);
      await expect(fab(page)).toHaveCount(0);
    });
  }

  for (const width of [768, 1440]) {
    test(`no FAB at ${width}px, where no frame places one`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/search");
      await expect(fab(page)).toBeHidden();
    });
  }
});

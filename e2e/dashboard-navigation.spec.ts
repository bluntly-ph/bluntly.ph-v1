import { expect, test } from "@playwright/test";

/**
 * Earnings navigation that only a signed-in account can reach.
 *
 * History's old "Historical Bill" pill was a span drawn as a button, going nowhere;
 * the redesigned History (Figma 8098:17238) links the full statement instead.
 * It now opens Payment history on /dashboard — and /dashboard streams in behind
 * its loading.tsx, so the browser's own jump to `#history` found only the
 * skeleton and the reader landed 1,955px above the section (390px, measured
 * 2026-09-17). components/dashboard/ScrollToHash.tsx closes that.
 *
 * A moderator is a signed-in, onboarded account, so the moderator session the
 * console specs use opens these screens too:
 *   E2E_MODERATOR_TOKEN=<token> npx playwright test e2e/dashboard-navigation.spec.ts
 *
 * Never point this at production.
 */

const TOKEN = process.env.E2E_MODERATOR_TOKEN;

test.describe("earnings navigation", () => {
  test.skip(
    !TOKEN,
    "E2E_MODERATOR_TOKEN is not set — needs the isolated test environment (see the file header).",
  );

  test.beforeEach(async ({ context }) => {
    await context.addCookies([{
      name: "bluntly_session",
      value: TOKEN as string,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      secure: false,
      sameSite: "Lax",
    }]);
  });

  test("History (Figma 8098:17238) links its full statement", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/dashboard/history");
    await expect(page.getByRole("heading", { name: "History", level: 1 })).toBeVisible();
    await Promise.all([
      page.waitForURL("**/dashboard/statement", { waitUntil: "load" }),
      page.getByRole("link", { name: "Full statement" }).click(),
    ]);
  });

  test("each Payout tip (Figma 7844:9469, 7844:9529, 7843:9501) opens with its data and leads back", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const [path, heading, card] of [
      ["/dashboard/transfer/answers", "Answer open questions", "Your answers"],
      ["/dashboard/transfer/proof", "Add receipts and photos", "Earnings per review, all reviewers"],
      ["/dashboard/transfer/honest-reviews", "Honest low-star reviews pay too", "Where your earnings come from"],
    ]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
      await expect(page.getByRole("region", { name: card })).toBeVisible();
      await expect(page.getByRole("alert").filter({ hasText: /could not be loaded/ })).toHaveCount(0);
      // The bar's back arrow at 390px (ParentLink shows from md up).
      await expect(page.locator('a[href="/dashboard/transfer"]:visible').first()).toBeVisible();
    }
  });

  test("Performance chooses a review from a searchable sheet (Figma 7849:9886)", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/dashboard/insights");
    await page.getByRole("button", { name: /^Review:/ }).click();
    const sheet = page.getByRole("dialog", { name: "Choose a review" });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("button", { name: /^All reviews/ })).toHaveAttribute("aria-pressed", "true");
    await sheet.getByLabel("Search your reviews").fill("no product is called this");
    await expect(sheet.getByText(/No review matches/)).toBeVisible();
    await sheet.getByLabel("Search your reviews").fill("");
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
  });
});

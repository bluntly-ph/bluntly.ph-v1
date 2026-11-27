import { expect, test, type Page } from "@playwright/test";

/**
 * The admin console's architecture: separate screens, a shell that does not
 * document-scroll, and a rail that stays put.
 *
 * This exists because of a specific, non-obvious regression. Tailwind's
 * `sr-only` is `position: absolute`, so a visually-hidden heading with no
 * positioned ancestor resolves its containing block to the DOCUMENT — it
 * escapes an ancestor's `overflow: hidden` entirely while still contributing to
 * `scrollHeight`. One such heading on the Overview put the whole console into a
 * 379px document scroll at 1024px and dragged the sidebar off the top with it.
 * At 1440 it happened to land inside the viewport, so the bug was invisible in
 * a casual look and in every wider screenshot.
 *
 * `document.scrollHeight` alone is not a sufficient assertion: it can report a
 * gap on a page that does not actually scroll. These tests scroll the window
 * and check `scrollY`, which is what a moderator would experience.
 *
 * Same setup as moderator-a11y.spec.ts:
 *   E2E_MODERATOR_TOKEN=<token> npx playwright test e2e/admin-console.spec.ts
 *
 * Never point this at production.
 */

const TOKEN = process.env.E2E_MODERATOR_TOKEN;

const SCREENS = [
  "/admin",
  "/admin/review-queue",
  "/admin/inbox",
  "/admin/products",
  "/admin/reviewers",
  "/admin/affiliate-links",
  "/admin/honesty-fund",
  "/admin/analytics",
  "/admin/activity",
  "/admin/settings",
];

const DESKTOP = [1440, 1280, 1024];

test.describe("admin console shell", () => {
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

  async function settle(page: Page, route: string) {
    await page.goto(route);
    await page.waitForTimeout(800);
  }

  for (const width of DESKTOP) {
    test(`the document never scrolls at ${width}px`, async ({ page }) => {
      // One visit per admin screen (ten of them, each settling 800ms).
      test.setTimeout(90_000);
      await page.setViewportSize({ width, height: 860 });
      for (const route of SCREENS) {
        await settle(page, route);
        const scrolled = await page.evaluate(() => {
          window.scrollTo(0, 5000);
          const y = window.scrollY;
          window.scrollTo(0, 0);
          return y;
        });
        expect(scrolled, `${route} must not scroll the document`).toBe(0);
      }
    });

    test(`the rail does not move when the workspace scrolls at ${width}px`, async ({ page }) => {
      test.setTimeout(90_000); // ten screens, each compiled on first visit under next dev
      await page.setViewportSize({ width, height: 860 });
      for (const route of SCREENS) {
        await settle(page, route);
        const moved = await page.evaluate(() => {
          const rail = document.querySelector("aside");
          const main = document.querySelector("main");
          if (!rail || !main) return null;
          const before = rail.getBoundingClientRect().top;
          main.scrollTop = main.scrollHeight;
          const after = rail.getBoundingClientRect().top;
          main.scrollTop = 0;
          return Math.abs(after - before);
        });
        expect(moved, `${route} rail must be stationary`).toBeLessThanOrEqual(1);
      }
    });
  }

  // The rail follows Admin/Sidebar 5017:2225 (16px items, 28px glyphs, a 44px
  // pitch) but carries thirteen items to the frame's eight. At the frame's own
  // 832px height that rhythm hid the whole SYSTEM group below the rail's fold,
  // so short screens use a tighter pitch. Laptop heights, not only the frame's.
  for (const height of [720, 768, 832]) {
    test(`every rail item is visible without scrolling the rail at 1280x${height}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height });
      await settle(page, "/admin");
      const belowFold = await page.evaluate(() => {
        const nav = document.querySelector("aside nav");
        if (!nav) return ["(no rail)"];
        const bottom = nav.getBoundingClientRect().bottom;
        return [...nav.querySelectorAll("li")]
          .filter((li) => li.getBoundingClientRect().bottom > bottom + 0.5)
          .map((li) => li.textContent?.trim() ?? "");
      });
      expect(belowFold, "rail items hidden below the fold").toEqual([]);
    });
  }

  test("a visually-hidden heading cannot extend the page", async ({ page }) => {
    // The regression, pinned directly: every sr-only element must be clipped by
    // an ancestor rather than resolving its containing block to the document.
    await page.setViewportSize({ width: 1024, height: 860 });
    await settle(page, "/admin");
    const escaped = await page.evaluate(() => {
      const out: string[] = [];
      for (const el of document.querySelectorAll(".sr-only")) {
        if (getComputedStyle(el).position !== "absolute") continue;
        let anc = el.parentElement;
        let contained = false;
        while (anc && anc !== document.body) {
          const cs = getComputedStyle(anc);
          if (cs.position !== "static") { contained = true; break; }
          anc = anc.parentElement;
        }
        if (!contained) out.push(el.textContent?.trim().slice(0, 40) ?? "(empty)");
      }
      return out;
    });
    expect(escaped, "sr-only elements need a positioned ancestor or they extend the document").toEqual([]);
  });

  test("Overview and Review Queue are separate screens", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 860 });

    await settle(page, "/admin");
    const workbench = (p: Page) => p.getByRole("table", { name: "Reviews awaiting an earnings decision, and take-downs" });
    await expect(workbench(page), "the Overview must not embed the queue workbench").toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();

    await settle(page, "/admin/review-queue");
    await expect(workbench(page), "the Review Queue owns the table").toBeVisible();
    await expect(page.getByRole("navigation", { name: "Pages" }), "and its pagination").toBeVisible();
  });

  test("every navigation destination resolves", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 860 });
    await settle(page, "/admin");
    const hrefs = await page.locator("aside nav a").evaluateAll(
      (as) => as.map((a) => a.getAttribute("href") ?? ""),
    );
    expect(hrefs.length, "the rail should have links").toBeGreaterThan(0);
    for (const href of hrefs) {
      expect(href, "no anchor-only or placeholder destinations").not.toMatch(/^#|javascript:/);
      const resp = await page.goto(href);
      expect(resp?.status(), `${href} must resolve`).toBe(200);
    }
  });

  test("every rail section is live: nothing is left inert", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 860 });
    await settle(page, "/admin");
    // Sellers (claims and appeals) and Settings (8076:16388) are real sections now.
    await expect(page.locator(`aside [aria-disabled="true"]`)).toHaveCount(0);
    await expect(page.locator("aside").getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/admin/settings");
  });

  test("the review modal investigates: Summary, Votes, Voters (Figma 8109–8117)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await settle(page, "/admin/review-queue");
    await page.locator("tbody tr").first().click();
    const dialog = page.getByRole("dialog").first();
    await expect(dialog.getByRole("tab", { name: /^Summary/ })).toHaveAttribute("aria-selected", "true");
    // The counts arrive with the investigation, read once per review.
    await expect(dialog.getByRole("tab", { name: /^Voters \d+ flagged/ })).toBeVisible();
    await dialog.getByRole("tab", { name: /^Votes/ }).click();
    await expect(dialog.getByTestId("investigate-votes")).toContainText("Vote timeline");
    await expect(dialog.getByTestId("investigate-votes")).toContainText("The earnings gate");
    await dialog.getByRole("tab", { name: /^Voters/ }).click();
    await expect(dialog.getByTestId("investigate-voters")).toContainText("How each voter votes on");
    // The decision bar stays on every tab, with the public review a new tab away.
    await expect(dialog.getByRole("button", { name: "Approve earnings" })).toBeVisible();
    const onSite = dialog.getByRole("link", { name: /^Open on site/ });
    await expect(onSite).toHaveAttribute("href", /^\/reviews\/[0-9a-f-]{36}$/);
    await expect(onSite).toHaveAttribute("target", "_blank");
  });
});

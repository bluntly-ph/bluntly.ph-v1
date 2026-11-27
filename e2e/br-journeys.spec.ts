import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Business-rule journeys against the REAL stack: the production Next build, the
 * FastAPI app and a real Postgres, seeded by backend/scripts/e2e_fixtures.py.
 *
 * Signing in is an emailed one-time code a CI browser cannot receive, so each
 * journey carries a fixture user's genuine access token in the site's own
 * session cookie — the same cookie the OTP flow sets. Everything after that is
 * the real UI and the real API. Each journey ends by reading the outcome back
 * from the API, so a page that merely *looked* right does not pass.
 *
 * Runs only when E2E_FIXTURES points at the seeded JSON (the CI job sets it);
 * skipped otherwise so `npm run test:e2e` on a laptop is unaffected.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
type Fx = {
  tag: string;
  remit_cycle: string;
  users: Record<string, { id: string; token: string; username: string }>;
  products: { fan: string; fresh: string; doomed: string; fan_name: string };
  reviews: { old: string; fresh: string; doomed: string };
  question: string;
  answer: string;
  store: string;
  store_name: string;
  open_store: string;
  open_store_name: string;
  seller_review: string;
  comment: string;
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
// Serial, and never retried: each journey changes real state (a vote toggles, a
// comment posts), so a retry would replay it against a different world and
// either fail or pass for the wrong reason.
test.describe.configure({ mode: "serial", retries: 0 });

async function as(context: BrowserContext, who: string) {
  await context.addCookies([
    { name: "bluntly_session", value: fx.users[who].token, url: "http://localhost:3000" },
  ]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

async function noOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
}

// The composer keeps the typed text as its own content, so a getByText for the
// body matches the textarea before anything is sent. Wait for the saved comment
// and the cleared box instead: a reload that races the POST loses the comment.
async function postComment(page: Page, reviewId: string, body: string) {
  const box = page.getByRole("textbox", { name: "Add a comment" });
  await box.fill(body);
  const saved = page.waitForResponse((r) =>
    r.url().endsWith(`/api/v1/reviews/${reviewId}/comments`) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Comment", exact: true }).click();
  expect((await saved).status(), "comment saved").toBe(201);
  await expect(box).toHaveValue("");
}

test("anonymous reader is sent to log in, with the way back kept", async ({ page }) => {
  await page.goto("/dashboard/transfer");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard%2Ftransfer/);
});

test("a vote is counted, survives a reload, and the author cannot vote", async ({ page, context }) => {
  await as(context, "voter");
  await page.goto(`/reviews/${fx.reviews.fresh}`);
  const up = page.getByRole("button", { name: /^Helpful, / }).first();
  await up.click();
  await expect(up).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: /^Helpful, 1/ }).first()).toHaveAttribute("aria-pressed", "true");
  const own = await api("reviewer", `/api/v1/reviews/${fx.reviews.fresh}/vote`, {
    method: "POST", body: JSON.stringify({ vote: "up" }),
  });
  expect(own.status).toBe(409);
});

test("a comment is posted, and deleting it takes two deliberate taps", async ({ page, context }) => {
  await as(context, "commenter");
  await page.goto(`/reviews/${fx.reviews.fresh}`);
  await postComment(page, fx.reviews.fresh, "Posted from the journey.");
  await expect(page.locator("p").filter({ hasText: "Posted from the journey." })).toBeVisible();
  // Delete the fixture's own comment: one tap only arms it.
  const item = page.locator("li, article").filter({ hasText: "Mine to delete." }).first();
  // QA-020: the author's Delete lives in the comment's ⋯ (Figma 7140:3330).
  await item.getByRole("button", { name: "More actions for this comment" }).click();
  await item.getByRole("menuitem", { name: "Delete" }).click();
  await expect(item.getByRole("group", { name: "Confirm deleting your comment" })).toBeVisible();
  await item.getByRole("button", { name: "Yes, delete" }).click();
  await expect.poll(async () => {
    const list = (await api(null, `/api/v1/reviews/${fx.reviews.fresh}/comments`)).body as
      { id: string; is_removed: boolean }[];
    return list.find((c) => c.id === fx.comment)?.is_removed ?? true;
  }).toBe(true);
});

test("the author's thread controls: update opens after 3 months, root delete needs the word", async ({ page, context }) => {
  await as(context, "reviewer");
  await page.goto(`/reviews/${fx.reviews.old}`);
  await expect(page.getByRole("link", { name: "Add an update" })).toBeVisible();
  await page.getByRole("link", { name: "Add an update" }).click();
  await expect(page).toHaveURL(new RegExp(`/reviews/new\\?update=${fx.reviews.old}`));
  await expect(page.getByText("Add an update").first()).toBeVisible();

  await page.goto(`/reviews/${fx.reviews.doomed}`);
  // Owner decision 2026-09-28: one delete dialog, reachable from the thread
  // panel (here), the author row and the ⋯ menu. The word is still required.
  await page.getByRole("region", { name: "Your review" }).getByRole("button", { name: "Delete review" }).click();
  // Only the open dialog is in the accessibility tree (the page also holds the
  // ⋯ menu's and the author row's, closed).
  const dialog = page.getByRole("dialog", { name: "Delete your review?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Delete review" })).toBeDisabled();
  expect((await api(null, `/api/v1/reviews/${fx.reviews.doomed}`)).status).toBe(200);
  await dialog.getByLabel(/Type .delete. to confirm/).fill("delete");
  await dialog.getByRole("button", { name: "Delete review" }).click();
  await expect(page).toHaveURL(/\/profile/);
  expect((await api(null, `/api/v1/reviews/${fx.reviews.doomed}`)).status).toBe(404);
});

test("cashout draws only on cleared money and is reserved at once", async ({ page, context }) => {
  await as(context, "reviewer");
  await page.goto("/dashboard/transfer");
  await expect(page.getByText("Minimum met")).toBeVisible();
  await expect(page.getByText("₱700.00").first()).toBeVisible();
  await expect(page.getByText("₱300.00").first()).toBeVisible();
  await noOverflow(page);
  await page.getByRole("button", { name: /^Request ₱/ }).click();
  await expect(page.getByText(/Requested ₱700\.00/)).toBeVisible();
  const balance = (await api("reviewer", "/api/v1/payouts/balance")).body as Record<string, string>;
  expect(Number(balance.withdrawable)).toBe(0);
  expect(Number(balance.pending_clearance)).toBe(300);
  const payouts = (await api("reviewer", "/api/v1/payouts")).body as { amount: string; status: string }[];
  expect(payouts.map((p) => [Number(p.amount), p.status])).toEqual([[700, "scheduled"]]);
  // Screen/Payout/Requested 7855:11171: the open request, its status, a locked footer.
  await page.reload();
  await expect(page.getByTestId("payout-threshold")).toHaveText("Request sent");
  await expect(page.getByRole("region", { name: "Payout status" })).toContainText("Checking · 3–5 days");
  await expect(page.getByRole("button", { name: "Payout requested" })).toBeDisabled();
  await expect(page.getByText("₱700.00 is locked until it's sent to your PayPal")).toBeVisible();
});

test("the asker picks the Best Answer and asks to be notified", async ({ page, context }) => {
  await as(context, "asker");
  await page.goto(`/questions/${fx.question}`);
  // The question shows what it is ABOUT; "For other buyers" was the removed
  // audience choice (owner decision 2026-09-28).
  await expect(page.getByText("About a product")).toBeVisible();
  await expect(page.getByText("For other buyers")).toHaveCount(0);
  await page.getByRole("button", { name: "Mark best answer" }).click();
  await expect(page.getByText("picked by the person who asked")).toBeVisible();
  await page.getByRole("button", { name: "Notify me!" }).click();
  await expect(page.getByRole("button", { name: "You'll be notified" })).toBeVisible();
  const detail = (await api("asker", `/api/v1/questions/${fx.question}`)).body as
    { best_answer_id: string; is_subscribed: boolean };
  expect(detail.best_answer_id).toBe(fx.answer);
  expect(detail.is_subscribed).toBe(true);
});

test("the store owner responds and flags a review; the admin asks; the buyer answers", async ({ browser }) => {
  const owner = await browser.newContext();
  await as(owner, "owner");
  const op = await owner.newPage();
  await op.goto(`/sellers/${fx.store}`);
  await op.getByRole("button", { name: "Respond as the store" }).first().click();
  await op.getByLabel("Your public response").fill("We refunded this order on 3 Sept.");
  await op.getByRole("button", { name: "Post response" }).click();
  await expect(op.getByText("Response from the store")).toBeVisible();
  await op.getByRole("button", { name: "Flag this review" }).first().click();
  // MQA-041: the store says what is wrong; "never ordered" is the default.
  await expect(op.getByRole("radio", { name: "The buyer never ordered" })).toBeChecked();
  await op.getByLabel("Why do you think they never ordered?").fill("We have no record of this order.");
  await op.getByRole("button", { name: "Send to an admin" }).click();
  await expect(op.getByText(/An admin will review it/)).toBeVisible();
  await owner.close();

  const mod = await browser.newContext();
  await as(mod, "administrator");
  const mp = await mod.newPage();
  type Appeal = { id: string; seller_review_id: string; status: string; order_id: string };
  const current = async () =>
    ((await api("administrator", "/api/v1/admin/seller-review-appeals?limit=200")).body as Appeal[])
      .find((a) => a.seller_review_id === fx.seller_review);
  const all = (await api("administrator", "/api/v1/admin/seller-review-appeals?limit=200")).body as Appeal[];
  const at = all.findIndex((a) => a.seller_review_id === fx.seller_review);
  expect(at).toBeGreaterThanOrEqual(0);
  // Oldest first, ten a page; the row opens the review modal, whose Reviewer
  // thread is how an admin asks the reviewer to back the review up.
  await mp.goto(`/admin/sellers?tab=appeals&page=${Math.floor(at / 10) + 1}`);
  // Its reason repeats across runs on a cumulative database: take the row by position.
  const row = mp.getByTestId("appeal-row").nth(at % 10);
  await expect(row).toContainText("We have no record of this order.");
  await row.getByRole("button", { name: "Review" }).click();
  const modal = mp.getByRole("dialog", { name: "Review appeal" });
  await expect(modal.getByRole("button", { name: "Remove review" })).toBeDisabled();
  await modal.getByRole("tab", { name: "Reviewer" }).click();
  await modal.getByRole("textbox").fill("Please share your order confirmation.");
  await modal.getByRole("button", { name: "Send" }).click();
  await expect.poll(async () => (await current())?.status).toBe("substantiation_requested");
  await expect(modal.getByTestId("appeal-state")).toContainText("Asked");
  const appeal = (await current())!;
  expect(appeal.order_id).toBe("ORD-2409");            // admins see it; nobody else does
  await mod.close();

  const buyer = await browser.newContext();
  await as(buyer, "buyer");
  const bp = await buyer.newPage();
  await bp.goto(`/sellers/appeals/${appeal.id}`);
  await expect(bp.getByText("Please share your order confirmation.")).toBeVisible();
  await bp.getByLabel("Your answer").fill("Order ORD-2409, placed 3 Sept.");
  await bp.getByRole("button", { name: "Send to the admin" }).click();
  await expect(bp.getByText(/You've answered/)).toBeVisible();
  await buyer.close();

  const publicReviews = await (await fetch(`${API}/api/v1/sellers/${fx.store}/reviews`)).text();
  expect(publicReviews).not.toContain("ORD-2409");
});

test("a store claim carries its DTI registration and the moderator approves it", async ({ browser }) => {
  const claimant = await browser.newContext();
  await as(claimant, "claimant");
  const cp = await claimant.newPage();
  await cp.goto(`/sellers/${fx.open_store}`);
  await cp.getByRole("button", { name: "Claim this store" }).click();
  await cp.getByLabel(/DTI business name registration number/).fill("DTI-1112223");
  await cp.getByLabel("Registered business name").fill("OpenShop Trading");
  const shop = cp.getByLabel(/Shop name, exactly as the marketplace shows it/);
  await expect(shop).toHaveValue(fx.open_store_name);
  await cp.getByRole("button", { name: "Send claim" }).click();
  await expect(cp.getByText(/Your claim is in/)).toBeVisible();
  await claimant.close();

  const mod = await browser.newContext();
  await as(mod, "administrator");
  const mp = await mod.newPage();
  const claims = (await api("administrator", "/api/v1/admin/seller-claims?limit=200")).body as {
    seller_id: string; registration_number: string | null;
  }[];
  const at = claims.findIndex((c) => c.seller_id === fx.open_store);
  expect(at).toBeGreaterThanOrEqual(0);
  // The claim keeps the number exactly as the claimant typed it...
  expect(claims[at].registration_number).toBe("DTI-1112223");
  await mp.goto(`/admin/sellers?page=${Math.floor(at / 10) + 1}`);
  const row = mp.getByTestId("claim-row").filter({ hasText: fx.open_store_name });
  // ...and the table names the kind once: "DTI 1112223", not "DTI DTI-1112223"
  // (f62b445, Figma 7992:11327).
  await expect(row.getByText("DTI 1112223", { exact: true })).toBeVisible();
  await row.getByRole("button", { name: "Review" }).click();
  const modal = mp.getByRole("dialog", { name: "Review claim" });
  await expect(modal.getByText("1112223", { exact: true })).toBeVisible();
  await expect(modal.getByText("Matches store")).toBeVisible();
  await modal.getByRole("button", { name: "Approve", exact: true }).click();
  await mp.getByRole("button", { name: "Confirm approval" }).click();
  await expect.poll(async () =>
    ((await api(null, `/api/v1/sellers/${fx.open_store}`)).body as { claim_status: string }).claim_status,
  ).toBe("claimed");
  // §9: the approved account can no longer vote anywhere.
  const vote = await api("claimant", `/api/v1/reviews/${fx.reviews.fresh}/vote`, {
    method: "POST", body: JSON.stringify({ vote: "down" }),
  });
  expect(vote.status).toBe(403);
  await mod.close();
});

test("administrator tools write what they say: investigation, remittance, alias", async ({ page, context }) => {
  await as(context, "administrator");
  // Investigation is operational, so it is on the member's People page
  // (Actions menu since the 2026-10-02 redesign); User management is the
  // Super Admin's (owner decisions C/D).
  await page.goto(`/admin/people/${fx.users.suspect.id}`);
  await page.getByRole("button", { name: "Actions", exact: true }).click();
  // Figma Menu/Person/Actions (8010:12514).
  await page.getByRole("menuitem", { name: "Mark Suspect E2E under investigation" }).click();
  await expect(page.getByText("Investigating", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Actions", exact: true }).click();
  await expect(page.getByRole("menuitem", { name: "Clear the investigation of Suspect E2E" })).toBeVisible();
  // Suspension is the Super Admin's alone: an Administrator sees it locked.
  await expect(page.getByRole("menuitem", { name: /Suspend account/ })).toBeDisabled();
  // Searched by handle: a cumulative test database has more than one page of members.
  const reviewers = (await api("administrator", `/api/v1/admin/reviewers?limit=50&q=${encodeURIComponent(fx.users.suspect.username)}`)).body as {
    rows: { id: string; is_under_investigation: boolean }[];
  };
  expect(reviewers.rows.find((r) => r.id === fx.users.suspect.id)?.is_under_investigation).toBe(true);

  // Figma Affiliate -> Months (8015:13183) -> Record -> Record remittance (8017:12816):
  // the fixture reviewer's sale sits in this run's own cycle, still clearing.
  type Month = { platform: string; cycle_month: string; status: string };
  const months = async () => (await api("administrator", "/api/v1/admin/affiliate/months")).body as Month[];
  const at = (await months()).findIndex((m) => m.platform === "shopee" && m.cycle_month === fx.remit_cycle);
  expect(at).toBeGreaterThanOrEqual(0);
  await page.goto(`/admin/affiliate-links?tab=months&page=${Math.floor(at / 10) + 1}`);
  const month = page.getByTestId("month-row").nth(at % 10);
  await expect(month).toContainText("Clearing");
  await month.hover();
  await month.getByRole("button", { name: "Record" }).click();
  const remit = page.getByRole("dialog", { name: "Record remittance" });
  await expect(remit).toContainText("1 commission");
  await remit.getByLabel("Amount received").fill("1000");
  await remit.getByRole("button", { name: "Record remittance" }).click();
  await expect(remit).toBeHidden();
  await expect.poll(async () => (await months()).find((m) => m.platform === "shopee" && m.cycle_month === fx.remit_cycle)?.status)
    .toBe("remitted");
  await expect(month).toContainText("Cleared");

  // Figma Products (7966:11087) -> Edit -> "Also known as".
  // The fixture product is still a submission: it waits in the Queue, newest first.
  await page.goto(`/admin/products?sort=newest&size=50`);
  const productRow = page.getByTestId("queue-row").filter({ hasText: fx.products.fan_name });
  await productRow.hover();
  await productRow.getByRole("button", { name: "Edit" }).click();
  const edit = page.getByRole("dialog", { name: "Add to catalogue" });
  await edit.getByLabel("Add an alias").fill(`Fanlife9x${fx.tag}`);
  await edit.getByLabel("Add an alias").press("Enter");
  await expect(edit.getByRole("button", { name: `Remove alias Fanlife9x${fx.tag}` })).toBeVisible();
});

test("an alias and a typo both find the product", async ({ page }) => {
  const alias = (await api(null, `/api/v1/products?q=${encodeURIComponent(`Fanlife9x${fx.tag}`)}`))
    .body as { id: string }[];
  expect(alias.map((p) => p.id)).toContain(fx.products.fan);
  const typo = (await api(null, `/api/v1/products?q=${encodeURIComponent(`Jisulyfe Fanlife ${fx.tag}`)}`))
    .body as { id: string }[];
  expect(typo.map((p) => p.id)).toContain(fx.products.fan);
  await page.goto(`/search?q=${encodeURIComponent(fx.products.fan_name)}`);
  await expect(page.getByText("Great fan for commuting").first()).toBeVisible();
});

test("a price is reported from the author's own review and waits for a glance", async ({ page, context }) => {
  await as(context, "reviewer");
  await page.goto(`/reviews/${fx.reviews.fresh}`);
  const report = page.getByRole("button", { name: "Report what you paid" }).first();
  await report.click();
  // The review page draws the form twice (phone and sidebar); act on the one shown.
  await page.locator('input[placeholder="1299"]:visible').fill("1299");
  await page.getByRole("button", { name: "Shopee", exact: true }).click();
  const today = new Date().toISOString().slice(0, 10);
  await page.locator("input[type=date]:visible").first().fill(today);
  await page.getByRole("button", { name: "Send price" }).click();
  await expect(page.getByText(/on the price history now|administrator glances/)).toBeVisible();
  const panel = (await api(null, `/api/v1/products/${fx.products.fresh}/prices`)).body as
    { pending_count: number };
  expect(panel.pending_count).toBe(1);           // no baseline yet → admin glance (§16)
});

test("every signed-in page holds from 320 to 1440 with no errors", async ({ browser }) => {
  test.setTimeout(300_000); // 66 real page loads, not one journey
  const pages: [string, string][] = [
    ["reviewer", `/reviews/${fx.reviews.fresh}`],
    ["reviewer", `/reviews/${fx.reviews.old}`],
    ["asker", `/questions/${fx.question}`],
    ["owner", `/sellers/${fx.store}`],
    ["reviewer", "/dashboard/transfer"],
    ["reviewer", "/dashboard/history"],
    ["reviewer", `/u/${fx.users.reviewer.username}`],
    ["reviewer", "/profile/edit"],
    ["administrator", "/admin/sellers"],
    ["administrator", "/admin/products"],
    ["administrator", "/admin/affiliate-links"],
  ];
  for (const width of [320, 360, 390, 768, 1024, 1440]) {
    for (const who of new Set(pages.map(([w]) => w))) {
      const context = await browser.newContext({ viewport: { width, height: 900 } });
      await as(context, who);
      const page = await context.newPage();
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      for (const [owner, path] of pages.filter(([w]) => w === who)) {
        void owner;
        // Not "networkidle": Next prefetches visible links and the network never
        // settles (tests/test_e2e_assertions_retry.py). The page's own landmark
        // is the signal that it rendered.
        const res = await page.goto(path, { waitUntil: "load" });
        expect(res?.status(), `${path} @${width}`).toBe(200);
        await page.locator("main").first().waitFor();
        const overflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        );
        expect(overflow, `${path} @${width}px sideways scroll`).toBeLessThanOrEqual(0);
        if (width < 768) {
          // iOS zooms any focused field under 16px (QA-036).
          const small = await page.evaluate(() =>
            // Fields that raise a keyboard; checkboxes, radios, sliders and file
            // pickers never zoom (the same exclusions as the rule in globals.css).
            Array.from(document.querySelectorAll(
              "input:not([type=hidden]):not([type=checkbox]):not([type=radio])" +
                ":not([type=range]):not([type=file]):not([type=submit]):not([type=button]), textarea, select",
            ))
              .filter((el) => (el as HTMLElement).offsetParent !== null)
              .map((el) => parseFloat(getComputedStyle(el).fontSize))
              .filter((size) => size < 16),
          );
          expect(small, `${path} @${width}px inputs under 16px`).toEqual([]);
        }
      }
      expect(errors, `page errors for ${who} @${width}`).toEqual([]);
      await context.close();
    }
  }
});

test("a review's age reads the same on the server and in the browser", async ({ browser }) => {
  // The seller page and the review page's comments print ages ("now", "5m").
  // Both sit in Client Components, which React renders on the server and again
  // to hydrate; reading the clock in each render made the two disagree whenever
  // an age crossed a unit in between — React error #418, which failed the test
  // above at 1440 on 2026-09-29 ("now" in the server's HTML, "1m" in the
  // browser's). A browser clock two hours ahead makes every such disagreement
  // certain instead of a one-second window: an age must come from the instant
  // the server rendered, handed down, never from the clock during render.
  // A comment written now, so the review page has a fresh age to print; the
  // seller page has the fixture's seller review, written minutes ago.
  const body = `Age check ${Date.now().toString(36)}`;
  const posted = await api("commenter", `/api/v1/reviews/${fx.reviews.old}/comments`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
  expect(posted.status).toBe(201);

  const context = await browser.newContext();
  await as(context, "asker");
  const page = await context.newPage();
  await page.clock.setFixedTime(Date.now() + 2 * 60 * 60 * 1000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`/sellers/${fx.store}`, { waitUntil: "load" });
  await expect(page.getByText("Never arrived.").first()).toBeVisible();
  await page.goto(`/reviews/${fx.reviews.old}`, { waitUntil: "load" });
  await expect(page.getByText(body)).toBeVisible();
  expect(errors).toEqual([]);
  await context.close();
});

test("hostile input is stored as text and never executes", async ({ page, context }) => {
  await as(context, "commenter");
  await page.goto(`/reviews/${fx.reviews.old}`);
  const payload = `<script>window.__xss=1</script><img src=x onerror="window.__xss=2"><svg onload="window.__xss=3">`;
  await postComment(page, fx.reviews.old, payload);
  const shown = page.locator("p").filter({ hasText: "<script>window.__xss=1</script>" });
  await expect(shown).toBeVisible();
  await page.reload();
  await expect(shown).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();
  await expect(page.locator("img[src='x'], svg[onload]")).toHaveCount(0);

  // Injection-shaped search text is just text to the API.
  for (const q of [`' OR 1=1 --`, `"; DROP TABLE reviews; --`, "%' UNION SELECT 1 --"]) {
    const res = await api(null, `/api/v1/products?q=${encodeURIComponent(q)}`);
    expect(res.status, q).toBe(200);
  }
  const still = await api(null, `/api/v1/reviews/${fx.reviews.old}`);
  expect(still.status).toBe(200);
});

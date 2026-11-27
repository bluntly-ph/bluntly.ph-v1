import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Owner decision patch 2026-09-28, on the REAL stack (production Next build,
 * FastAPI, Postgres seeded by backend/scripts/e2e_fixtures.py): review
 * deletion, staff takedown, the claimed seller's dashboard, seller support
 * requests and the Q&A composer without an audience choice. Each journey
 * reads its outcome back from the API. Skipped anywhere E2E_FIXTURES is unset.
 *
 * The patch world (fixtures "patch"):
 *   deleter      three reviews: unpaid, previously PAID (a cleared ₱500.00
 *                Lazada sale in Feb 1995, its share paid out), and one for
 *                the phone
 *   stranger     a review for staff to take down
 *   patchowner   DeskHub, claimed: a 5★ review with 3 helpful votes and a 3★
 *                review with 2 replies, and one store question
 *   ownertwo     another claimed store's owner
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  users: Record<string, { id: string; token: string; username: string }>;
  products: { fan_name: string };
  patch: {
    unpaid_review: string;
    paid_review: string;
    mobile_review: string;
    paid_share: string;
    takedown_review: string;
    store: string;
    store_name: string;
    praised_review: string;
    grumble_review: string;
    store_question: string;
    product_question: string;
  };
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

/** The conversation journey 8 starts, read by 9 and 10. */
let ticket = "";

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
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
}

/**
 * A review action, wherever the layout puts it: the ⋯ menu on a phone, inline
 * buttons on the website (ReviewOverflowMenu draws one or the other).
 */
async function reviewAction(page: Page, inline: string, menuItem: string) {
  const menu = page.getByRole("button", { name: "More options" }).first();
  if (await menu.isVisible()) {
    await menu.click();
    await page.getByRole("menuitem", { name: menuItem }).click();
  } else {
    await page.getByRole("button", { name: inline, exact: true }).first().click();
  }
}

/** Neither the inline button nor the menu item exists for this viewer. */
async function noReviewAction(page: Page, inline: string, menuItem: string) {
  const menu = page.getByRole("button", { name: "More options" }).first();
  if (await menu.isVisible()) {
    await menu.click();
    await expect(page.getByRole("menuitem", { name: menuItem })).toHaveCount(0);
    await page.keyboard.press("Escape");
  }
  await expect(page.getByRole("button", { name: inline, exact: true })).toHaveCount(0);
}

async function deleteFromMenu(page: Page) {
  await reviewAction(page, "Delete review", "Delete review");
  const dialog = page.getByRole("dialog", { name: "Delete your review?" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Delete review" })).toBeDisabled();
  await dialog.getByLabel(/Type .delete. to confirm/).fill("delete");
  await dialog.getByRole("button", { name: "Delete review" }).click();
  await expect(page).toHaveURL(/\/profile\?deleted=1/);
  await expect(page.getByRole("status").filter({ hasText: "Your review was deleted." })).toBeVisible();
}

test("1. a reviewer deletes their own unpaid review", async ({ page, context }) => {
  await as(context, "deleter");
  await page.goto(`${BASE}/reviews/${fx.patch.unpaid_review}`);
  await deleteFromMenu(page);
  expect((await api(null, `/api/v1/reviews/${fx.patch.unpaid_review}`)).status).toBe(404);
  // Gone from the author's own list too.
  const mine = (await api("deleter", "/api/v1/users/me/reviews")).body as { id: string }[] | null;
  if (Array.isArray(mine)) expect(mine.map((r) => r.id)).not.toContain(fx.patch.unpaid_review);
});

test("2. a previously-paid review is deleted; the paid trace stays", async ({ page, context }) => {
  await as(context, "deleter");
  await page.goto(`${BASE}/reviews/${fx.patch.paid_review}`);
  await reviewAction(page, "Delete review", "Delete review");
  const dialog = page.getByRole("dialog", { name: "Delete your review?" });
  await expect(dialog.getByText("Money you were already paid stays yours; nothing is taken back.")).toBeVisible();
  await dialog.getByLabel(/Type .delete. to confirm/).fill("delete");
  await dialog.getByRole("button", { name: "Delete review" }).click();
  await expect(page).toHaveURL(/\/profile\?deleted=1/);
  expect((await api(null, `/api/v1/reviews/${fx.patch.paid_review}`)).status).toBe(404);

  // The earnings statement still carries the sale and the payout.
  const statement = (await api("deleter", "/api/v1/reports/earnings-statement?year=1995")).body as {
    entries: { review_title: string | null; reviewer_earning: string }[];
    payouts: { amount: string; status: string }[];
  };
  const entry = statement.entries.find((e) => e.review_title === "Toaster browns evenly");
  expect(entry, "the paid sale is still on the statement").toBeTruthy();
  expect(entry!.reviewer_earning).toBe(fx.patch.paid_share);
  expect(statement.payouts.map((p) => [p.amount, p.status])).toContainEqual([fx.patch.paid_share, "paid"]);
  await page.goto(`${BASE}/dashboard/statement?year=1995`);
  await expect(page.getByRole("row").filter({ hasText: "Toaster browns evenly" }).first()).toBeVisible();
});

test("3. another member cannot delete someone else's review", async ({ page, context }) => {
  await as(context, "stranger");
  await page.goto(`${BASE}/reviews/${fx.patch.mobile_review}`);
  await expect(page.getByRole("heading", { name: "Blender is loud" }).first()).toBeVisible();
  await noReviewAction(page, "Delete review", "Delete review");
  await noReviewAction(page, "Take down", "Take down (staff)");
  const refused = await api("stranger", `/api/v1/reviews/${fx.patch.mobile_review}?confirm=delete-thread`, {
    method: "DELETE",
  });
  expect(refused.status).toBe(403);
  expect(refused.body.code).toBe("not_review_author");
  expect((await api(null, `/api/v1/reviews/${fx.patch.mobile_review}`)).status).toBe(200);
});

test("4. an Administrator takes a review down, with a reason", async ({ page, context }) => {
  await as(context, "administrator");
  await page.goto(`${BASE}/reviews/${fx.patch.takedown_review}`);
  // Staff get the takedown, never the author's delete.
  await noReviewAction(page, "Delete review", "Delete review");
  await reviewAction(page, "Take down", "Take down (staff)");
  const dialog = page.getByRole("dialog", { name: "Take this review down?" });
  await expect(dialog.getByRole("button", { name: "Take down" })).toBeDisabled();
  await dialog.getByLabel("Reason (sent to the author)").fill("Test content, not a real purchase.");
  await dialog.getByRole("button", { name: "Take down" }).click();
  await expect.poll(async () => (await api(null, `/api/v1/reviews/${fx.patch.takedown_review}`)).status).toBe(404);
});

// The store dashboard is the Seller console's Overview since 2026-10-03
// (Figma Screen/Seller/Overview 8190:20643); /sellers/<id>/dashboard redirects.
test("5. the claimed seller opens their console", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/dashboard`);
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}$`));
  await expect(page.getByRole("heading", { level: 1 })).toContainText(fx.patch.store_name);
  await expect(page.getByRole("button", { name: new RegExp(`Store: ${fx.patch.store_name}`) }).first()).toContainText("Lazada");
  await page.goto(`${BASE}/sellers/${fx.patch.store}/dashboard`);
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}$`));
});

test("6. the seller sees figures that match the data", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}?period=all`);
  const dash = (await api("patchowner", `/api/v1/sellers/${fx.patch.store}/dashboard`)).body as {
    analytics: { review_count: number; replies_total: number; helpful_votes_total: number; responses_total: number };
  };
  expect(dash.analytics).toMatchObject({ review_count: 2, replies_total: 2, helpful_votes_total: 3 });
  await expect(page.getByText("Median of 2 reviews")).toBeVisible();
  await expect(page.getByText("4 / 5", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(`${dash.analytics.responses_total} of 2`)).toBeVisible();
  await expect(page.getByRole("table", { name: "Recent reviews" }).locator("tbody tr")).toHaveCount(2);
});

test("7. the seller sees what is waiting on them", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}`);
  const waiting = page.locator("#waiting");
  await expect(waiting.getByText("no response", { exact: false })).toHaveCount(2);
  await expect(waiting.getByRole("link", { name: "Respond" }).first()).toHaveAttribute(
    "href",
    new RegExp(`^/seller/${fx.patch.store}/reviews\\?respond=[0-9a-f-]{36}$`),
  );
  // Respond happens in the console's Reviews screen (Figma 8196:20870), on that review.
  await waiting.getByRole("link", { name: "Respond" }).first().click();
  await expect(page.getByRole("dialog", { name: /^Respond to / })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}/reviews$`));
  await expect(page.getByRole("heading", { level: 1, name: "Reviews" })).toBeVisible();
  await expect(page.getByTestId("seller-review-row")).toHaveCount(2);
});

test("7b. a response past the limit shows the over-limit state and cannot be posted", async ({ page, context }) => {
  // Console design system: counted textareas carry no maxLength, so the Figma
  // over-limit state is reachable and Post stays off until it is shortened.
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}/reviews`);
  await page.getByTestId("seller-review-row").first().getByRole("button", { name: "Respond" }).click();
  const box = page.getByLabel("Your public response");
  const post = page.getByRole("button", { name: "Post response" });
  await box.fill("x".repeat(1001));
  await expect(box).toHaveValue("x".repeat(1001));
  await expect(box).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByText("1,001 / 1,000")).toBeVisible();
  await expect(page.getByText("1 character over the limit. Shorten it to send.")).toBeVisible();
  await expect(post).toBeDisabled();
  await box.fill("x".repeat(1000));
  await expect(box).not.toHaveAttribute("aria-invalid", "true");
  await expect(post).toBeEnabled();
  await page.getByRole("button", { name: "Cancel" }).click();
});

test("7c. Quick actions: search, a count opens its screen, respond to the oldest review", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}`);
  const qa = page.getByRole("dialog", { name: "Quick actions" });
  // ⌘K / Ctrl+K works once the shell has hydrated.
  await expect(async () => {
    if (!(await qa.isVisible())) await page.keyboard.press("Control+k");
    await expect(qa).toBeVisible({ timeout: 1000 });
  }).toPass();
  await expect(qa.getByRole("option", { name: /Reviews that need a response\s*2/ })).toBeVisible();
  await qa.getByRole("combobox").fill("csv");
  await expect(qa.getByRole("option")).toHaveText(["Download CSV"]);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: /Download CSV|Export/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Quick actions" }).click();
  await qa.getByRole("option", { name: /Unanswered questions/ }).click();
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}/questions$`));
  await page.keyboard.press("Control+k");
  await qa.getByRole("combobox").fill("oldest");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/reviews\?respond=oldest$/);
  await expect(page.getByRole("dialog", { name: /^Respond to / })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}/reviews$`));
  // The frame's other actions (Figma 8212:23261): the oldest question, and linking a product.
  await page.keyboard.press("Control+k");
  await qa.getByRole("combobox").fill("oldest question");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/questions\?answer=oldest$/);
  await expect(page.getByRole("dialog", { name: "Answer a question" })).toBeVisible();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}/questions$`));
  await page.keyboard.press("Control+k");
  await qa.getByRole("combobox").fill("link");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/products\?link=1$/);
  await expect(page.getByRole("dialog", { name: "Link a product" })).toBeVisible();
});

test("8. the seller writes to the team (New message replaces the request form)", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}#support`);
  await page.getByRole("link", { name: "New message" }).click();
  const dialog = page.getByRole("dialog", { name: "New message" });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("About").selectOption("account");
  await dialog.getByLabel("Message").fill("The missing-bolt review: our packing list shows all four bolts for order ORD-3002.");
  await dialog.getByRole("button", { name: "Send" }).click();
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}/messages\\?c=[0-9a-f-]+`));
  ticket = new URL(page.url()).searchParams.get("c")!;
  await expect(page.getByTestId("thread-message").first()).toContainText("ORD-3002");
  await expect(dialog).toHaveCount(0);
  const mine = (await api("patchowner", `/api/v1/conversations/${ticket}`)).body as { status: string; seller_id: string };
  expect(mine.status).toBe("open");
  expect(mine.seller_id).toBe(fx.patch.store);
});

test("9. an Administrator answers in the Inbox and moves it to Support", async ({ browser }) => {
  expect(ticket, "journey 8 wrote to the team").not.toBe("");
  const staff = await browser.newContext();
  await as(staff, "administrator");
  const page = await staff.newPage();
  await page.goto(`${BASE}/admin/inbox?q=ORD-3002&c=${ticket}`);
  await expect(page.getByTestId("inbox-row").first()).toContainText(fx.patch.store_name);
  await page.getByRole("textbox", { name: /Reply to/ }).fill("We asked the reviewer to show the order.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("thread-message").filter({ hasText: "We asked the reviewer" })).toHaveAttribute("data-mine", "true");
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Move to Queue → Support" }).click();
  // MQA-021/024: moving to Support keeps ONE open thread (not closed), with
  // the support reference recorded in it.
  await expect(page.getByRole("list", { name: "Messages" })).toContainText("Moved to Queue → Support (SUP-");
  await expect(page.getByRole("button", { name: "Status: Open" })).toBeVisible();
  await expect(page.getByTestId("inbox-closed")).toHaveCount(0);
  await staff.close();

  const seller = await browser.newContext();
  await as(seller, "patchowner");
  const mine = await seller.newPage();
  await mine.goto(`${BASE}/seller/${fx.patch.store}/messages?c=${ticket}`);
  await expect(mine.getByTestId("thread-message").filter({ hasText: "We asked the reviewer to show the order." })).toHaveAttribute("data-mine", "false");
  await expect(mine.getByRole("textbox", { name: "Message the Bluntly team" })).toBeVisible();
  await seller.close();
});

test("10. a second seller cannot read the first seller's conversation", async ({ page, context }) => {
  expect(ticket).not.toBe("");
  await as(context, "ownertwo");
  const refused = await api("ownertwo", `/api/v1/conversations/${ticket}`);
  expect(refused.status).toBe(404);
  await page.goto(`${BASE}/seller/${fx.patch.store}/messages?c=${ticket}`);
  await expect(page.getByRole("heading", { name: "This isn’t your store" })).toBeVisible();
  await expect(page.getByText("ORD-3002")).toHaveCount(0);
});

test("11. the question composer asks no audience", async ({ page, context }) => {
  await as(context, "asker");
  await page.goto(`${BASE}/questions/new`);
  await expect(page.getByLabel("Search for the product your question is about")).toBeVisible();
  await expect(page.getByText("How can we help you?")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "I want to ask a seller" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "I want to ask other buyers" })).toHaveCount(0);
  await page.getByLabel("Search for the product your question is about").fill(fx.products.fan_name);
  await page.getByRole("button", { name: new RegExp(fx.products.fan_name) }).first().click();
  await page.getByLabel("What’s your main question?").fill("How long does one charge last on the middle setting?");
  await page.getByRole("button", { name: "Submit" }).click();
  const view = page.getByRole("link", { name: "View my question" });
  await expect(view).toBeVisible();
  const href = await view.getAttribute("href");
  const created = (await api("asker", href!.replace("/questions/", "/api/v1/questions/"))).body as Record<string, unknown>;
  expect(created).not.toHaveProperty("directed_to");
  await view.click();
  await expect(page.getByText("About a product")).toBeVisible();
});

test("12. a buyer answers a product question through the answer flow", async ({ page, context }) => {
  await as(context, "buyer");
  await page.goto(`${BASE}/questions/${fx.patch.product_question}`);
  // A product question is answered through the seven steps (it needs a
  // rating), not a one-line box.
  await expect(page.getByLabel("Your answer")).toHaveCount(0);
  await page.getByRole("link", { name: /Write your answer/ }).click();
  await page.waitForURL(`**/questions/${fx.patch.product_question}/answer`);
  await expect(page.getByTestId("answer-step-counter")).toHaveText("Step 1 out of 7 · Required");
  await page.getByLabel("Your answer").fill("Loud enough across a small bedroom, not a living room.");
  const next = page.getByRole("button", { name: "Continue" });
  for (let i = 0; i < 4; i++) await next.click(); // nothing specific was asked for
  await expect(page.getByTestId("answer-step-counter")).toHaveText("Step 5 out of 7 · Added information");
  await next.click();
  await expect(page.getByTestId("answer-step-counter")).toHaveText("Step 6 out of 7 · Required");
  await expect(next).toBeDisabled(); // the rating is always required
  await page.getByLabel("4 stars", { exact: true }).check({ force: true });
  await next.click();
  await page.getByRole("button", { name: /Skip – post without a photo/ }).click();
  await expect(page.getByText("Answer posted!")).toBeVisible();
  // A member's answer, not the store's, with its rating.
  await expect
    .poll(async () => {
      const detail = (await api(null, `/api/v1/questions/${fx.patch.product_question}`)).body as {
        answers: { is_seller_answer: boolean; parts: { text: string; rating: string | null } }[];
      };
      const mine = detail.answers.find((a) => a.parts.text.startsWith("Loud enough across"));
      return mine ? [mine.is_seller_answer, mine.parts.rating] : null;
    })
    .toEqual([false, "4"]);
  await page.goto(`${BASE}/questions/${fx.patch.product_question}`);
  await expect(page.getByText("Loud enough across a small bedroom, not a living room.")).toBeVisible();
});

test("13. the store's owner answers its own store question as the store", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/questions/${fx.patch.store_question}`);
  await expect(page.getByText("About a store")).toBeVisible();
  await page.getByLabel("Your answer").fill("Yes, Davao in five to seven days.");
  await page.getByRole("button", { name: "Post answer" }).click();
  await expect
    .poll(async () => {
      const detail = (await api(null, `/api/v1/questions/${fx.patch.store_question}`)).body as {
        answers: { body: string; is_seller_answer: boolean }[];
      };
      return detail.answers.find((a) => a.body.startsWith("Yes, Davao"))?.is_seller_answer;
    })
    .toBe(true);
  await page.reload();
  await expect(page.getByText("Yes, Davao in five to seven days.")).toBeVisible();
});

test("13b. the store edits its answer in the console; buyers see Edited", async ({ page, context }) => {
  // Figma Screen/Seller/Questions/Answered 8201:22543 → Overlay/Store/EditAnswer 8202:22530.
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}/questions`);
  // Questions toolbar (Figma Menu/Seller/Questions/Sort 8198:21562, Filter 8198:21572).
  await page.getByRole("button", { name: "Search questions" }).click();
  await page.getByRole("textbox", { name: "Search questions" }).fill("Davao");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\?q=Davao$/);
  await page.getByRole("button", { name: /^Answered/ }).click();
  const row = page.getByTestId("seller-question-row").filter({ hasText: "Yes, Davao" });
  await expect(page.getByTestId("seller-question-row")).toHaveCount(1);
  await row.getByRole("button", { name: "Edit" }).click();
  const dialog = page.getByRole("dialog", { name: "Edit your answer" });
  await expect(dialog.getByLabel("Your answer")).toHaveValue("Yes, Davao in five to seven days.");
  await expect(dialog.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await expect(dialog.getByText("Buyers see “Edited” next to your answer.")).toBeVisible();
  await dialog.getByLabel("Your answer").fill("Yes, Davao in five to seven working days.");
  await dialog.getByRole("button", { name: "Save changes" }).click();
  // Confirm/Store/SaveAnswer 8202:22737.
  const confirm = page.getByRole("dialog", { name: "Save your edit?" });
  await expect(confirm).toContainText("Buyers see “Edited” next to it.");
  await confirm.getByRole("button", { name: "Save changes" }).click();
  await expect(dialog).toBeHidden();
  await page.goto(`${BASE}/questions/${fx.patch.store_question}`);
  const answer = page.getByTestId("answer").filter({ hasText: "Yes, Davao in five to seven working days." });
  await expect(answer).toContainText("Edited");
  // Nobody else can edit the store's answer.
  const detail = (await api(null, `/api/v1/questions/${fx.patch.store_question}`)).body as {
    answers: { id: string; is_seller_answer: boolean }[];
  };
  const id = detail.answers.find((a) => a.is_seller_answer)!.id;
  const res = await api("asker", `/api/v1/questions/${fx.patch.store_question}/answers/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ body: "Hijacked" }),
  });
  expect(res.status).toBe(403);
});

test("14. the asker selects the Best Answer", async ({ page, context }) => {
  await as(context, "asker");
  await page.goto(`${BASE}/questions/${fx.patch.product_question}`);
  await page.getByRole("button", { name: "Mark best answer" }).first().click();
  await expect(page.getByText("picked by the person who asked")).toBeVisible();
  const detail = (await api("asker", `/api/v1/questions/${fx.patch.product_question}`)).body as {
    best_answer_id: string | null;
    answers: { id: string; body: string }[];
  };
  const buyers = detail.answers.find((a) => a.body.startsWith("Loud enough across"));
  expect(detail.best_answer_id).toBe(buyers?.id);
});

test("14b. Settings: notification switches save, and Give up asks first (Figma 8218:24151)", async ({ page, context }) => {
  await as(context, "patchowner");
  await page.goto(`${BASE}/seller/${fx.patch.store}/settings`);
  const questions = page.getByRole("switch", { name: "New questions" });
  await expect(questions).toHaveAttribute("aria-checked", "true");
  await questions.click();
  await expect(questions).toHaveAttribute("aria-checked", "false");
  await expect.poll(async () => (await api("patchowner", "/api/v1/users/me/notification-prefs")).body?.store_questions).toBe(false);
  await page.reload();
  await expect(page.getByRole("switch", { name: "New questions" })).toHaveAttribute("aria-checked", "false");
  // Only low reviews depends on new reviews.
  await page.getByRole("switch", { name: "New reviews of your store" }).click();
  await expect(page.getByRole("switch", { name: "Only low reviews" })).toBeDisabled();
  // The email channels (0085) are on by default and can be turned off.
  const weekly = page.getByRole("switch", { name: "Weekly summary" });
  await expect(weekly).toBeEnabled();
  await expect(page.getByRole("switch", { name: "Also by email" })).toHaveAttribute("aria-checked", "true");
  await weekly.click();
  await expect.poll(async () => (await api("patchowner", "/api/v1/users/me/notification-prefs")).body?.weekly_summary).toBe(false);
  // Put them back for the journeys that follow.
  await weekly.click();
  await page.getByRole("switch", { name: "New reviews of your store" }).click();
  await page.getByRole("switch", { name: "New questions" }).click();
  await expect.poll(async () => (await api("patchowner", "/api/v1/users/me/notification-prefs")).body?.store_questions).toBe(true);
  await expect.poll(async () => (await api("patchowner", "/api/v1/users/me/notification-prefs")).body?.weekly_summary).toBe(true);

  await page.getByRole("button", { name: `Give up ${fx.patch.store_name}` }).click();
  const confirm = page.getByRole("dialog", { name: `Give up ${fx.patch.store_name}?` });
  await expect(confirm).toBeVisible();
  await confirm.getByRole("button", { name: "Keep it" }).click();
  await expect(confirm).toBeHidden();
  expect((await api("patchowner", "/api/v1/sellers/mine")).body.map((s: { id: string }) => s.id)).toContain(fx.patch.store);
});

test("15. the seller dashboard on a phone", async ({ browser }) => {
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await as(phone, "patchowner");
  const page = await phone.newPage();
  await page.goto(`${BASE}/seller/dashboard`);
  await expect(page).toHaveURL(new RegExp(`/seller/${fx.patch.store}$`));
  await expect(page.getByText("Would recommend")).toBeVisible();
  await expect(page.getByRole("link", { name: "New message" })).toBeVisible();
  await noSidewaysScroll(page);
  await page.locator("#support").scrollIntoViewIfNeeded();
  await noSidewaysScroll(page);
  await phone.close();
});

test("16. a review is deleted on a phone", async ({ browser }) => {
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await as(phone, "deleter");
  const page = await phone.newPage();
  await page.goto(`${BASE}/reviews/${fx.patch.mobile_review}`);
  await noSidewaysScroll(page);
  await deleteFromMenu(page);
  await noSidewaysScroll(page);
  expect((await api(null, `/api/v1/reviews/${fx.patch.mobile_review}`)).status).toBe(404);
  await phone.close();
});

import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext } from "@playwright/test";

/**
 * Dev/QA sync of 2026-09-29, on the REAL stack (production Next build, FastAPI,
 * Postgres seeded by backend/scripts/e2e_fixtures.py). Each journey drives the
 * browser and reads its outcome back from the API. Skipped anywhere
 * E2E_FIXTURES is unset. See docs/MEETING_2026_09_29_DECISIONS.md.
 *
 *   B  the Reports tab says WHY an item was reported, beside the item
 *   I  the Bounty Board: a request names its product, many people answer, the
 *      ASKER picks the Best Answer, and the request leaves the board but keeps
 *      its page and stays searchable
 *   J  "Someone answered your request" opens the request itself
 *   F  choosing a tier chip does not zero the other tier chips
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = { users: Record<string, { id: string; token: string; username: string }> };
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

const TAG = Math.random().toString(36).slice(2, 8);

/**
 * Every review these journeys write, deleted by its author afterwards. The
 * specs share one database and run in name order, and the Recent feed shows
 * twelve cards: left behind, these newer reviews pushed the fixture review
 * qa-round2's feed journey looks for off its first page.
 */
const written: { who: string; id: string }[] = [];

test.afterAll(async () => {
  for (const { who, id } of written) {
    await api(who, `/api/v1/reviews/${id}?confirm=delete-thread`, { method: "DELETE" });
  }
});

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

async function product(who: string, name: string): Promise<string> {
  const res = await api(who, "/api/v1/products", {
    method: "POST",
    body: JSON.stringify({ name, category: "electronics" }),
  });
  expect([200, 201]).toContain(res.status);
  return res.body.id;
}

async function review(who: string, productId: string, title: string, discussion: string): Promise<string> {
  const res = await api(who, "/api/v1/reviews", {
    method: "POST",
    body: JSON.stringify({ product_id: productId, title, discussion, verdict: "yes_absolutely", star_rating: 4 }),
  });
  expect(res.status, JSON.stringify(res.body)).toBe(201);
  written.push({ who, id: res.body.id });
  return res.body.id;
}

test("B. an Administrator sees why an item was reported, beside the item", async ({ page, context }) => {
  const pid = await product("m29writer", `Report Panel Fan ${TAG}`);
  const rid = await review("m29writer", pid, `Panel fan ${TAG}`, "Three weeks on the desk; quiet and steady.");
  const note = `The photo is the shop's own listing image ${TAG}.`;
  const filed = await api("m29second", `/api/v1/reviews/${rid}/report`, {
    method: "POST",
    body: JSON.stringify({ reason: "fake_proof", notes: note }),
  });
  expect(filed.status).toBe(201);

  await as(context, "administrator");
  await page.goto("/admin/review-queue?tab=report&rsort=oldest");
  // One table row per report; the member's note is under its reason, and the
  // details open in a modal.
  const card = page.locator("tbody tr", { hasText: note }).first();
  await card.click();
  const panel = page.getByRole("dialog").getByTestId("report-detail");
  await expect(panel.getByTestId("report-summary")).toContainText(
    "A member reported this review as “Fake photo or receipt”.",
  );
  await expect(panel.getByTestId("report-summary")).toContainText(note);
  // The reported content itself, side by side with the report.
  await expect(panel).toContainText(`Panel fan ${TAG}`);
  await expect(panel).toContainText("Three weeks on the desk");
  await expect(panel.getByRole("link", { name: "Open the reported item" })).toHaveAttribute("href", `/reviews/${rid}`);
  // Nothing fabricated: no reverse-image result and no IP claim for a member's
  // report. Since MQA-003 (cf0c07c) the panel lists the review's integrity
  // checks, and a check with no provider says it did not run instead of
  // reading as a pass or a match (ADR-007: no reverse-image provider).
  await expect(panel).not.toContainText(/same IP/i);
  const checks = panel.getByTestId("report-integrity");
  for (const label of ["Reverse image search", "Plagiarism (web)"]) {
    const check = checks.getByRole("listitem").filter({ hasText: label });
    await expect(check).toHaveCount(1);
    await expect(check).toHaveAttribute("data-state", "not_run");
    await expect(check).toContainText(`${label} (did not run) · No provider is configured, so this check does not run.`);
  }
  // That "did not run" row is the panel's only mention of a reverse image.
  expect((await panel.innerText()).match(/reverse image/gi)).toHaveLength(1);
});

test("I + J. the asker picks the Best Answer; the request leaves the board and keeps its page", async ({
  page,
  context,
}) => {
  const name = `Tefal Wok Pan ${TAG}`;
  const pid = await product("m29writer", name);

  // The asker posts a request, choosing the product first.
  await as(context, "m29asker");
  await page.goto("/requests/new");
  await page.getByLabel(/Which product\?/).fill(name);
  await page.getByRole("button", { name }).click();
  await expect(page.getByTestId("request-product")).toHaveText(name);
  await page.getByLabel("What do you want reviewed?").fill(`Is the ${name} durable?`);
  await page
    .getByLabel("Details")
    .fill("Planning to use it daily for stir-fry. Does the coating last past six months of heavy use?");
  await page.getByRole("button", { name: "Post request" }).click();
  await page.waitForURL(/\/requests\/[0-9a-f-]{36}$/);
  const requestId = page.url().split("/").pop() as string;
  await expect(page.getByTestId("request-status")).toHaveText("Open: waiting for the Best Answer");
  await expect(page.getByText("No answers yet.")).toBeVisible();

  // Two people answer with reviews of the product.
  const first = await review("m29writer", pid, `Wok, four months in ${TAG}`, "Coating still fine; no warping.");
  const second = await review("m29second", pid, `Wok after six months ${TAG}`, "Slight wear at the centre, still fine.");

  // The asker's notice opens the request itself (J).
  const notes = (await api("m29asker", "/api/v1/notifications?limit=100")).body as {
    id: string;
    kind: string;
    title: string;
    link: string;
  }[];
  const answered = notes.find((n) => n.kind === "request_answered" && n.link === `/requests/${requestId}`);
  expect(answered?.title).toBe("2 people answered your request");
  await page.goto("/notifications");
  await page.locator(`li[data-notification-id="${answered!.id}"]`).getByRole("button").first().click();
  await page.waitForURL(new RegExp(`/requests/${requestId}$`));

  // Both answers are there; the asker picks the second (I).
  const answers = page.getByTestId("request-answers").locator("li");
  await expect(answers).toHaveCount(2);
  await answers
    .filter({ hasText: `Wok after six months ${TAG}` })
    .getByRole("button", { name: "Pick as Best Answer" })
    .click();
  await expect(page.getByTestId("request-status")).toHaveText("Answered: Best Answer picked");
  await expect(page.locator('li[data-best="true"]')).toContainText(`Wok after six months ${TAG}`);
  await expect(page.getByText("Best Answer · picked by the person who asked")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pick as Best Answer" })).toHaveCount(0);

  const row = (await api(null, `/api/v1/requests/${requestId}`)).body;
  expect(row.status).toBe("fulfilled");
  expect(row.fulfilled_by_review_id).toBe(second);
  expect(first).not.toBe(second);

  // Off the board...
  await page.goto("/requests");
  await expect(page.getByText(`Is the ${name} durable?`)).toHaveCount(0);
  // ...not deleted: search still finds it, answered.
  await page.goto(`/search?tab=questions&q=${encodeURIComponent(name)}`);
  const found = page.getByTestId("search-requests");
  await expect(found).toContainText(`Is the ${name} durable?`);
  await expect(found).toContainText("Answered: Best Answer picked");
});

test("I. only the asker is offered the Best Answer", async ({ page, context }) => {
  const name = `Kettle ${TAG}`;
  const pid = await product("m29writer", name);
  const req = await api("m29asker", "/api/v1/requests", {
    method: "POST",
    body: JSON.stringify({
      product_id: pid,
      title: `Does the ${name} rust?`,
      details: "Hard water in our area. Does the base discolour or rust after a few months of use?",
    }),
  });
  expect(req.status).toBe(201);
  await review("m29writer", pid, `Kettle, three months ${TAG}`, "No rust yet; descale monthly.");

  await as(context, "m29second");
  await page.goto(`/requests/${req.body.id}`);
  await expect(page.getByTestId("request-answers").locator("li")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Pick as Best Answer" })).toHaveCount(0);
  const refused = await api("m29second", `/api/v1/requests/${req.body.id}/best-answer`, {
    method: "POST",
    body: JSON.stringify({ review_id: (await api(null, `/api/v1/requests/${req.body.id}/answers`)).body[0].review_id }),
  });
  expect(refused.status).toBe(403);
});

test("F. choosing a tier chip keeps the other tier chips counted", async ({ page, context }) => {
  const all = (await api("administrator", "/api/v1/admin/review-queue?limit=1")).body.counts.by_tier as Record<
    string,
    number
  >;
  const tiers = Object.entries(all).filter(([, n]) => n > 0);
  test.skip(tiers.length < 2, "needs two non-empty tiers in the fixture queue");
  const [[chosen], [other, otherCount]] = tiers;

  const LABELS: Record<string, string> = {
    highest: "Highest",
    high: "High",
    neutral: "Neutral",
    low: "Low",
    lowest: "Lowest",
  };
  await as(context, "administrator");
  await page.goto(`/admin/review-queue?tier=${chosen}`);
  // The tier chips live in the toolbar's Filters menu (Queue rebuilt to Figma 8060:15564).
  await page.getByRole("button", { name: /^Filters/ }).click();
  const chips = page.getByText("Tier", { exact: true }).locator("..");
  // The OTHER tier's own chip keeps its count; before the fix it read 0.
  await expect(chips.getByRole("link", { name: `${LABELS[other]} ${otherCount}`, exact: true })).toBeVisible();
  await expect(chips.getByRole("link", { name: `${LABELS[other]} 0`, exact: true })).toHaveCount(0);
  const filtered = (await api("administrator", `/api/v1/admin/review-queue?limit=1&tier=${chosen}`)).body.counts
    .by_tier as Record<string, number>;
  expect(filtered).toEqual(all);
});

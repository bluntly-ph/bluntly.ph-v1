import { readFileSync } from "node:fs";

import { chromium, expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Independent QA round 2 — journeys that need two separately signed-in
 * browsers, against the REAL stack (production Next build, FastAPI, Postgres;
 * seeded by backend/scripts/e2e_fixtures.py). Runs in the same CI job as
 * br-journeys.spec.ts and is skipped anywhere E2E_FIXTURES is unset.
 *
 * Unlike br-journeys, sign-in here goes through the real one-time-code flow:
 * the CI API uses the console email provider, which logs each code, and
 * E2E_API_LOG points at that log. QA-061 is about what signing in does to
 * OTHER sessions, so a cookie injected from outside would not test it.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API_LOG = process.env.E2E_API_LOG;
type Fx = {
  tag: string;
  users: Record<string, { id: string; username: string; token: string }>;
  reviews: { old: string; fresh: string; doomed: string };
  products: { fan: string; fan_name: string };
};
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES || !API_LOG, "needs the seeded real stack (E2E_FIXTURES, E2E_API_LOG)");
test.describe.configure({ mode: "serial", retries: 0 });
// Each journey signs in through the real code flow two or more times.
test.setTimeout(90_000);

const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const emailOf = (name: string) => `e2e_${name}_${fx.tag}@example.com`;

/** The newest code the console provider logged for `email`. */
function latestCode(email: string): string | null {
  const lines = readFileSync(API_LOG!, "utf8").split("\n").filter((l) => l.includes(email));
  for (const line of lines.reverse()) {
    const m = line.match(/"code":\s*"(\d{6})"/);
    if (m) return m[1];
  }
  return null;
}

/** Sign in through the real form: email, emailed code, Continue. */
async function signIn(page: Page, name: string): Promise<void> {
  const email = emailOf(name);
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

/** Who this page's session is, asked of the API through the page's own cookie. */
async function whoAmI(page: Page): Promise<string | null> {
  return page.evaluate(async () => {
    const res = await fetch("/api/bff/api/v1/auth/me", { cache: "no-store" });
    if (!res.ok) return null;
    return ((await res.json()) as { username: string | null }).username;
  });
}

async function freshPage(context: BrowserContext): Promise<Page> {
  const page = await context.newPage();
  await page.goto(`${BASE}/`, { waitUntil: "load" });
  return page;
}

test("QA-061 E: two browser processes keep two accounts apart through real sign-ins", async () => {
  // Two launches are two processes with two cookie jars — the same isolation
  // two browser profiles, or Chrome and Edge, or a normal and a private window
  // have. This is the setup the report describes as "a separate browser".
  const first = await chromium.launch();
  const second = await chromium.launch();
  try {
    const a = await (await first.newContext()).newPage();
    await signIn(a, "voter");
    expect(await whoAmI(a)).toBe(fx.users.voter.username);

    const b = await (await second.newContext()).newPage();
    await signIn(b, "asker");
    expect(await whoAmI(b)).toBe(fx.users.asker.username);

    // The first browser, after the second signed in: still its own account,
    // on a fresh load and on an authenticated API call.
    await a.reload({ waitUntil: "load" });
    expect(await whoAmI(a)).toBe(fx.users.voter.username);
    await a.goto(`${BASE}/dashboard`, { waitUntil: "load" });
    expect(new URL(a.url()).pathname).toBe("/dashboard");
    expect(await whoAmI(a)).toBe(fx.users.voter.username);

    // And signing the second out does not sign the first out.
    await b.context().clearCookies();
    expect(await whoAmI(b)).toBeNull();
    expect(await whoAmI(a)).toBe(fx.users.voter.username);
  } finally {
    await first.close();
    await second.close();
  }
});

test("QA-061 B: two isolated contexts in one browser (a normal and a private window) stay apart", async ({ browser }) => {
  const normal = await browser.newContext();
  const incognito = await browser.newContext();
  try {
    const a = await normal.newPage();
    await signIn(a, "commenter");
    const b = await incognito.newPage();
    await signIn(b, "buyer");

    await a.reload({ waitUntil: "load" });
    expect(await whoAmI(a)).toBe(fx.users.commenter.username);
    expect(await whoAmI(b)).toBe(fx.users.buyer.username);
  } finally {
    await normal.close();
    await incognito.close();
  }
});

test("QA-061 A: two tabs of ONE profile share one session, as every cookie-based site does", async ({ browser }) => {
  // What the report describes, reproduced step by step. Tabs of one browser
  // profile share its cookie jar, so there is one session per profile:
  //   1. tab 2 cannot open the sign-in page while tab 1's account is signed in
  //      (proxy.ts sends a signed-in reader from /login to /);
  //   2. so reaching a second account means Log out first — which ends the
  //      profile's one session, for tab 1 too;
  //   3. signing in as the second account then shows it in both tabs.
  // By design, not leakage: separate profiles stay apart (E and B above).
  const profile = await browser.newContext();
  try {
    const tab1 = await profile.newPage();
    await signIn(tab1, "suspect");
    const tab2 = await freshPage(profile);

    await tab2.goto(`${BASE}/login`, { waitUntil: "load" });
    expect(new URL(tab2.url()).pathname).toBe("/");
    expect(await whoAmI(tab2)).toBe(fx.users.suspect.username);

    await tab2.getByRole("button", { name: "Menu and profile" }).click();
    await tab2.getByRole("button", { name: "Log out" }).click();
    await expect.poll(() => whoAmI(tab2)).toBeNull();
    expect(await whoAmI(tab1)).toBeNull();              // the same profile's one session

    await signIn(tab2, "claimant");
    // The tab still drawn for the first account now says so, instead of
    // quietly acting as the second (QA-061, round 4).
    await expect(tab1.getByTestId("account-switch-notice")).toContainText(
      `@${fx.users.claimant.username}`,
    );
    await tab1.reload({ waitUntil: "load" });
    expect(await whoAmI(tab1)).toBe(fx.users.claimant.username);
    await expect(tab1.getByTestId("account-switch-notice")).toHaveCount(0);
  } finally {
    await profile.close();
  }
});

/* ------------------------------------------------ comments, votes, share */

/** Journeys below carry a fixture session in the site's own cookie (as br-journeys). */
async function as(context: BrowserContext, who: string) {
  await context.addCookies([
    { name: "bluntly_session", value: fx.users[who].token, url: BASE },
  ]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

type ThreadRow = { id: string; body: string; is_removed: boolean; replies: ThreadRow[] };

test("QA-039: a confirmed delete takes the comment off the page, and a reload keeps it off", async ({ page, context }) => {
  const text = `QA039 retract ${fx.tag}`;
  const posted = await api("commenter", `/api/v1/reviews/${fx.reviews.old}/comments`, {
    method: "POST", body: JSON.stringify({ body: text }),
  });
  expect(posted.status).toBe(201);
  await as(context, "commenter");
  await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
  const row = page.locator(`#comment-${(posted.body as { id: string }).id}`);
  await row.getByRole("button", { name: "More actions for this comment" }).click();
  await row.getByRole("menuitem", { name: "Delete" }).click();
  await row.getByRole("button", { name: "Yes, delete" }).click();
  await expect(page.getByText(text)).toHaveCount(0);
  await page.reload({ waitUntil: "load" });
  await expect(page.getByText(text)).toHaveCount(0);
  const thread = (await api(null, `/api/v1/reviews/${fx.reviews.old}/comments`)).body as ThreadRow[];
  expect(thread.some((c) => c.body === text)).toBe(false);
});

test("QA-029: a reply can be answered, and the answer joins the same thread", async ({ page, context }) => {
  const top = await api("commenter", `/api/v1/reviews/${fx.reviews.old}/comments`, {
    method: "POST", body: JSON.stringify({ body: `QA029 top ${fx.tag}` }),
  });
  const topId = (top.body as { id: string }).id;
  const reply = await api("voter", `/api/v1/reviews/${fx.reviews.old}/comments`, {
    method: "POST", body: JSON.stringify({ body: `QA029 reply ${fx.tag}`, parent_id: topId }),
  });
  const replyId = (reply.body as { id: string }).id;

  await as(context, "asker");
  await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
  const replyRow = page.locator(`#comment-${replyId}`);
  await replyRow.getByRole("button", { name: "Reply" }).click();
  const box = page.getByRole("textbox", { name: "Write a reply" });
  await expect(box).toHaveValue(`@${fx.users.voter.username} `);
  await box.fill(`@${fx.users.voter.username} same here ${fx.tag}`);
  await page.locator("form").filter({ has: box }).getByRole("button", { name: "Reply", exact: true }).click();
  // A successful post closes the composer; until then the text is only in the box.
  await expect(box).toBeHidden();
  await expect(page.locator("p").filter({ hasText: `same here ${fx.tag}` })).toBeVisible();

  await expect.poll(async () => {
    const thread = (await api(null, `/api/v1/reviews/${fx.reviews.old}/comments`)).body as ThreadRow[];
    return thread.find((c) => c.id === topId)?.replies.map((r) => r.body) ?? [];
  }).toContain(`@${fx.users.voter.username} same here ${fx.tag}`);
});

test("QA-027/028: a feed card's downvote is a real control that records the vote", async ({ page, context }) => {
  await as(context, "asker");
  await page.goto(`${BASE}/feed?tab=recent`, { waitUntil: "load" });
  const card = page.locator("article").filter({ hasText: "Great fan for commuting" }).first();
  await expect(card.getByRole("button", { name: /^Not helpful, / })).toBeVisible();
  await expect(card.getByRole("button", { name: "Share" })).toBeVisible();
  await expect(card.getByRole("link", { name: /comments/ })).toBeVisible();

  await card.getByRole("button", { name: /^Not helpful, / }).click();
  await expect(card.getByRole("button", { name: /^Not helpful, / })).toHaveAttribute("aria-pressed", "true");
  // Still on the feed: the tap acted, it did not navigate.
  expect(new URL(page.url()).pathname).toBe("/feed");
  const read = (await api("asker", `/api/v1/reviews/${fx.reviews.old}`)).body as { my_vote: string | null };
  expect(read.my_vote).toBe("down");
});

test("QA-024: Share opens the app's own sheet with the review's link, and copying says so", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE });
  await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
  await page.getByRole("button", { name: "Share" }).first().click();
  const sheet = page.getByRole("dialog", { name: "Share" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("textbox", { name: "Link to share" })).toHaveValue(
    `${BASE}/reviews/${fx.reviews.old}`,
  );
  await sheet.getByRole("button", { name: "Copy link" }).click();
  await expect(sheet.getByText("Link copied to your clipboard.")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
});

test("QA-030: the up and down counts are set in the same type", async ({ page }) => {
  await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
  const sizes = await page.evaluate(() => {
    const up = document.querySelector('button[aria-label^="Helpful, "] span');
    const down = document.querySelector('button[aria-label^="Not helpful, "] span');
    const read = (el: Element | null) => (el ? getComputedStyle(el) : null);
    return [read(up), read(down)].map((s) => (s ? `${s.fontSize}/${s.fontWeight}/${s.lineHeight}` : null));
  });
  expect(sizes[0]).not.toBeNull();
  expect(sizes[0]).toBe(sizes[1]);
});

/* ------------------------------------------------ drafts and the composer */

for (const device of [
  { name: "desktop", viewport: { width: 1280, height: 900 }, hasTouch: false },
  { name: "phone", viewport: { width: 390, height: 844 }, hasTouch: true },
]) {
  test(`QA-003 + QA-038 (${device.name}): an account draft opens on a new device; custom Pros/Cons stay chosen`, async ({ browser }) => {
    // One account draft, at the Pros and cons step, saved "from another device".
    const who = device.name === "desktop" ? "buyer" : "claimant";
    const draft = {
      step: 3,
      product: { id: fx.products.fan, canonical_name: fx.products.fan_name, category: "electronics", image_url: null },
      title: "", discussion: "Quiet on low, loud on turbo; lasted a full commute both ways.",
      verdict: "yes_absolutely", verdictWhy: "It does the job.", rating: 4, pros: "", cons: "",
      target: "", anti: "", photoUrl: null, receiptKey: null, price: "", pricePlatform: null,
      disclosure: null, savedAt: Date.now(),
    };
    const saved = await api(who, `/api/v1/review-drafts/${fx.products.fan}`, {
      method: "PUT", body: JSON.stringify({ draft, saved_at: draft.savedAt }),
    });
    expect(saved.status).toBe(200);

    // A new context is a device that has never seen this draft (empty storage).
    const context = await browser.newContext({ viewport: device.viewport, hasTouch: device.hasTouch });
    try {
      await as(context, who);
      const page = await context.newPage();
      await page.goto(`${BASE}/reviews/new`, { waitUntil: "load" });
      await page.getByRole("button", { name: "Pick up" }).first().click();

      const pro = page.getByRole("textbox", { name: "Add a pro…" });
      await pro.fill("Budget friendly");
      await pro.press("Enter");
      await expect(page.getByRole("button", { name: "Budget friendly" })).toHaveAttribute("aria-pressed", "true");
      await expect(pro).toHaveValue("");

      // A con confirmed by leaving the field (a tap elsewhere), not by Enter.
      const con = page.getByRole("textbox", { name: "Add a con…" });
      await con.fill("Short cable");
      await page.getByText("Cons", { exact: true }).click();
      await expect(page.getByRole("button", { name: "Short cable" })).toHaveAttribute("aria-pressed", "true");

      // The explicit Add button, for keyboards that send no Enter.
      await pro.fill("Lightweight");
      await page.getByRole("button", { name: "Add “Lightweight”" }).click();
      await expect(page.getByRole("button", { name: "Lightweight" })).toHaveAttribute("aria-pressed", "true");
      await expect(pro).toHaveAttribute("autocomplete", "off");

      // A duplicate is not added twice.
      await pro.fill("budget friendly");
      await pro.press("Enter");
      await expect(page.getByRole("button", { name: /^budget friendly$/i })).toHaveCount(1);

      // Forward a step and back: both are still chosen.
      await page.getByRole("button", { name: "Continue" }).click();
      await expect(page.getByRole("textbox", { name: "Add a pro…" })).toHaveCount(0);
      await page.getByRole("button", { name: /Back to Pros and cons/ }).click();
      await expect(page.getByRole("button", { name: "Budget friendly" })).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByRole("button", { name: "Short cable" })).toHaveAttribute("aria-pressed", "true");

      // And the account copy has them, for the next device.
      await expect.poll(async () => {
        const list = (await api(who, "/api/v1/review-drafts")).body as { slot: string; draft: { pros: string; cons: string } }[];
        const mine = list.find((d) => d.slot === fx.products.fan)?.draft;
        return mine ? `${mine.pros.split("\n").join(",")}|${mine.cons}` : "";
      }, { timeout: 15_000 }).toBe("Budget friendly,Lightweight|Short cable");
    } finally {
      await context.close();
    }
  });
}

/* ------------------------------------------------ navigation */

test("QA-016: dashboard subpages have a worded way back on desktop, direct visits included", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  try {
    await as(context, "reviewer");
    const page = await context.newPage();
    for (const sub of ["/dashboard/reviews", "/dashboard/history", "/dashboard/transfer", "/dashboard/insights"]) {
      await page.goto(`${BASE}${sub}`, { waitUntil: "load" });   // a direct visit: nothing behind it
      const up = page.getByRole("main").getByRole("link", { name: "Dashboard", exact: true });
      await expect(up, sub).toBeVisible();
      await up.click();
      await page.waitForURL((url) => url.pathname === "/dashboard");
    }
  } finally {
    await context.close();
  }

  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  try {
    await as(phone, "reviewer");
    const page = await phone.newPage();
    await page.goto(`${BASE}/dashboard/reviews`, { waitUntil: "load" });
    await page.getByRole("link", { name: "Back" }).click();          // the hero's arrow, as before
    await page.waitForURL((url) => url.pathname === "/dashboard");
  } finally {
    await phone.close();
  }
});

test("QA-023: a question row shows it is clickable, and opens by pointer or keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${BASE}/questions`, { waitUntil: "load" });
  const row = page.locator('a[href^="/questions/"]').filter({ has: page.locator("h2") }).first();
  const rest = await row.evaluate((el) => getComputedStyle(el).backgroundColor);
  await row.hover();
  await expect.poll(() => row.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(rest);
  expect(await row.evaluate((el) => getComputedStyle(el).cursor)).toBe("pointer");

  const href = await row.getAttribute("href");
  await row.focus();
  await page.keyboard.press("Enter");
  await page.waitForURL((url) => url.pathname === href);
});

test("QA-059: nothing pops over the headline on desktop; the phone's three-dot menu stays inside the page", async ({ browser }) => {
  // Desktop (retest 2026-09-24: the menu still covered the product title): the
  // actions are plain buttons at the author line's right end — no menu at all.
  {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    try {
      const page = await context.newPage();
      await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
      await expect(page.getByRole("button", { name: "More options" }).locator("visible=true")).toHaveCount(0);
      const copy = page.getByRole("button", { name: "Copy link" }).locator("visible=true").first();
      await expect(copy).toBeVisible();
      const c = (await copy.boundingBox())!;
      const h = (await page.locator("h1").first().boundingBox())!;
      expect(c.y + c.height, "Copy link sits above the headline").toBeLessThanOrEqual(h.y + 1);
    } finally {
      await context.close();
    }
  }
  for (const viewport of [{ width: 390, height: 844 }, { width: 320, height: 640 }]) {
    const context = await browser.newContext({ viewport });
    try {
      const page = await context.newPage();
      await page.goto(`${BASE}/reviews/${fx.reviews.old}`, { waitUntil: "load" });
      const trigger = page.getByRole("button", { name: "More options" }).locator("visible=true").first();
      await trigger.click();
      const menu = page.getByRole("menu");
      await expect(menu).toBeVisible();
      const m = (await menu.boundingBox())!;
      const t = (await trigger.boundingBox())!;
      const label = `${viewport.width}px`;
      expect(m.x, label).toBeGreaterThanOrEqual(0);
      expect(m.x + m.width, label).toBeLessThanOrEqual(viewport.width);
      // It opens from the trigger's own edge, not hanging off the other side.
      const fromLeft = Math.abs(m.x - t.x) < 2;
      const fromRight = Math.abs(m.x + m.width - (t.x + t.width)) < 2;
      expect(fromLeft || fromRight, label).toBe(true);
      await expect(menu.getByRole("menuitem", { name: "Copy link" })).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();
    } finally {
      await context.close();
    }
  }
});

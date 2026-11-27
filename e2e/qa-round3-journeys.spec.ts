import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Independent QA round 3 (QA-062..075) against the REAL stack: the production
 * Next build, FastAPI and Postgres, seeded by backend/scripts/e2e_fixtures.py.
 * Runs in the same CI job as br-journeys.spec.ts and is skipped anywhere
 * E2E_FIXTURES is unset.
 *
 * Each identity is its own browser context carrying its own fixture session
 * (the site's real cookie). Other people's actions go through the API with
 * THEIR tokens, never the viewer's. Uploads and the final review POST are
 * answered in the browser: CI has no storage bucket, and the journeys assert
 * what the page SENDS.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  tag: string;
  users: Record<string, { id: string; token: string; username: string }>;
  products: { fan: string; fresh: string; doomed: string; fan_name: string };
  reviews: { old: string; fresh: string; doomed: string };
  comment: string;
};
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

/** The comment the first journey posts, which the second votes on and saves:
 *  the fixture's own comment may already have been deleted by an earlier spec. */
let postedComment = "";

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  return { status: res.status, body: res.status === 204 ? null : await res.json().catch(() => null) };
}

async function badge(page: Page): Promise<number> {
  const label = await page.getByRole("button", { name: /Menu and profile/ }).first().getAttribute("aria-label");
  return Number(label?.match(/(\d+) unread/)?.[1] ?? 0);
}

async function unread(who: string): Promise<number> {
  return (await api(who, "/api/v1/notifications/unread-count")).body.count;
}

/** A real JPEG, drawn in the page, `w`×`h`. */
async function jpeg(page: Page, w: number, h: number): Promise<Buffer> {
  const b64 = await page.evaluate(async ([width, height]) => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#c8d2e6";
    ctx.fillRect(0, 0, width, height);
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 12;
    ctx.strokeRect(width * 0.3, height * 0.3, width * 0.4, height * 0.4);
    const blob: Blob = await new Promise((r) => canvas.toBlob((b) => r(b!), "image/jpeg", 0.9));
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let s = "";
    for (const byte of bytes) s += String.fromCharCode(byte);
    return btoa(s);
  }, [w, h]);
  return Buffer.from(b64, "base64");
}

function jpegSize(buf: Buffer): { w: number; h: number } | null {
  let i = 2;
  while (i < buf.length) {
    if (buf[i] !== 0xff) { i++; continue; }
    const marker = buf[i + 1];
    if (marker >= 0xc0 && marker <= 0xc3) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
    i += 2 + buf.readUInt16BE(i + 2);
  }
  return null;
}

test("QA-064/065/067: a mention is announced once, opens its comment, and read state follows everywhere", async ({ browser }) => {
  // Its own mentionee: qa-round2 mentions @voter, and on a second worker that
  // notice can land between this journey's counts.
  const posted = await api("commenter", `/api/v1/reviews/${fx.reviews.fresh}/comments`, {
    method: "POST", body: JSON.stringify({ body: `Worth asking @${fx.users.mentionee.username} too.` }),
  });
  expect(posted.status).toBe(201);
  postedComment = posted.body.id;
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await as(context, "mentionee");
  const page = await context.newPage();
  const other = await context.newPage();
  await page.goto(`${BASE}/notifications`);
  await other.goto(`${BASE}/feed`);
  const start = await unread("mentionee");
  await expect.poll(() => badge(page)).toBe(start);
  await expect.poll(() => badge(other)).toBe(start);

  const notes = (await api("mentionee", "/api/v1/notifications?limit=50")).body as { id: string; kind: string; link: string }[];
  const mention = notes.find((n) => n.kind === "comment_mention" && n.link.endsWith(posted.body.id))!;
  expect(mention.link).toBe(`/reviews/${fx.reviews.fresh}#comment-${posted.body.id}`);
  await page.locator(`li[data-notification-id="${mention.id}"]`).getByRole("button").first().click();
  await page.waitForURL(`**/reviews/${fx.reviews.fresh}#comment-${posted.body.id}`);
  // Read on the server before the page landed, and on both surfaces at once.
  expect(await unread("mentionee")).toBe(start - 1);
  await expect.poll(() => badge(page)).toBe(start - 1);
  await expect.poll(() => badge(other)).toBe(start - 1);

  await page.goto(`${BASE}/notifications`);
  const row = page.locator(`li[data-notification-id="${mention.id}"]`);
  await expect(row).toHaveAttribute("data-unread", "false");
  await row.getByRole("button", { name: /Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Mark as unread" }).click();
  await expect(row).toHaveAttribute("data-unread", "true");
  await expect.poll(() => badge(page)).toBe(start);
  await expect.poll(() => badge(other)).toBe(start);
  await row.getByRole("button", { name: /Actions for/ }).click();
  await page.getByRole("menuitem", { name: "Remove from list" }).click();
  await expect(row).toHaveCount(0);
  await page.reload();
  await expect(page.locator(`li[data-notification-id="${mention.id}"]`)).toHaveCount(0);
  expect(await unread("mentionee")).toBe(start - 1);
  // Soft: the comment it announced is still there.
  const thread = (await api(null, `/api/v1/reviews/${fx.reviews.fresh}/comments`)).body as { id: string }[];
  expect(thread.some((c) => c.id === posted.body.id)).toBe(true);
  await context.close();
});

test("QA-068/069: a vote does not move a comment; another's comment offers Report, Follow and Save", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await as(context, "asker");
  const page = await context.newPage();
  await page.goto(`${BASE}/reviews/${fx.reviews.fresh}#comments`);
  const order = () => page.locator("#comments > ul > li > div[id^=comment-]").evaluateAll((els) => els.map((e) => e.id));
  const before = await order();
  expect(before.length).toBeGreaterThan(1);
  const cid = postedComment || fx.comment;
  const target = page.locator(`#comment-${cid}`);
  await target.getByRole("button", { name: /^Helpful/ }).click();
  await expect(target.getByRole("button", { name: /^Helpful/ })).toHaveAttribute("aria-pressed", "true");
  expect(await order()).toEqual(before);

  const menu = target.getByRole("button", { name: "More actions for this comment" });
  await menu.click();
  await expect(page.getByRole("menuitem")).toHaveText(["Report", "Follow comment", "Save comment"]);
  await page.getByRole("menuitem", { name: "Save comment" }).click();
  await menu.click();
  await expect(page.getByRole("menuitem", { name: "Unsave comment" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Report" }).click();
  const dialog = page.getByRole("dialog", { name: "Report this comment" });
  await dialog.getByText("Spam", { exact: true }).click();
  await dialog.getByRole("button", { name: "Send report" }).click();
  await expect(dialog.getByText(/your report is with the administrators/)).toBeVisible();
  await dialog.getByRole("button", { name: "Done" }).click();
  const queue = (await api("administrator", "/api/v1/admin/reports?target_type=comment&limit=100")).body;
  const filed = queue.items.find((i: { report: { target_ref: string } }) => i.report.target_ref === cid);
  expect(filed.target.link).toBe(`/reviews/${fx.reviews.fresh}#comment-${cid}`);

  await page.goto(`${BASE}/profile?tab=saved`);
  await expect(page.locator(`a[href$="#comment-${cid}"]`)).toBeVisible();
  // Private: nobody else's list, and no Saved tab on a public profile.
  expect(((await api("voter", "/api/v1/users/me/saved-comments")).body as { id: string }[]).some((s) => s.id === cid)).toBe(false);
  await page.goto(`${BASE}/u/${fx.users.asker.id}`);
  await expect(page.getByRole("link", { name: "Saved" })).toHaveCount(0);
  await context.close();
});

test("QA-062/063: only the crop is uploaded, and Skip sends the review with no photo", async ({ browser }) => {
  const product = { id: fx.products.doomed, canonical_name: `Baseus Blade ${fx.tag}`, category: "electronics-tech", image_url: null };
  const draft = {
    step: 5, product,
    title: "", discussion: "Two weeks in a work bag; thin, charges a phone twice.", verdict: "yes_absolutely", verdictWhy: "",
    rating: 4, pros: "Worth it!", cons: "Gets warm", target: "", anti: "Anyone needing laptop power.", photoUrls: [],
    receiptKey: null, price: "", pricePlatform: null, disclosure: null, savedAt: Date.now(),
  };
  expect((await api("voter", `/api/v1/review-drafts/${product.id}`, { method: "PUT", body: JSON.stringify({ draft, saved_at: draft.savedAt }) })).status).toBe(200);
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await as(context, "voter");
  const page = await context.newPage();
  const uploads: Buffer[] = [];
  await page.route("**/api/bff/api/v1/reviews/photo", async (route) => {
    const body = route.request().postDataBuffer()!;
    const start = body.indexOf(Buffer.from([0xff, 0xd8, 0xff]));
    uploads.push(body.subarray(start, body.lastIndexOf(Buffer.from([0xff, 0xd9])) + 2));
    await route.fulfill({ json: { url: `https://ci.supabase.co/storage/v1/object/public/review-photos/${fx.users.voter.id}/${"a".repeat(32)}.jpg` } });
  });
  await page.route(/review-photos/, (route) => route.fulfill({ status: 200, contentType: "image/jpeg", body: uploads.at(-1) }));
  let submitted: { photo_url: string | null; photo_urls: string[] } | null = null;
  await page.route("**/api/bff/api/v1/reviews", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { id: "00000000-0000-0000-0000-000000000000" } });
  });

  await page.goto(`${BASE}/reviews/new`);
  await page.locator("div.justify-between").filter({ hasText: `Unfinished review of ${product.canonical_name}` })
    .getByRole("button", { name: "Pick up" }).click();
  const original = await jpeg(page, 1600, 1200);
  await page.getByTestId("review-photos-input").setInputFiles({ name: "landscape.jpg", mimeType: "image/jpeg", buffer: original });
  await expect(page.locator("[data-cropper=square]")).toBeVisible();
  expect(uploads).toHaveLength(0);
  const img = page.getByTestId("crop-window").locator("img");
  await expect(img).toHaveCSS("position", "absolute");
  const before = await img.evaluate((i) => i.style.width);
  // A two-finger pinch, as touch pointers.
  await page.getByTestId("crop-window").evaluate((el) => {
    const r = el.getBoundingClientRect();
    const ev = (type: string, id: number, x: number) => el.dispatchEvent(new PointerEvent(type, { pointerId: id, pointerType: "touch", clientX: r.left + x, clientY: r.top + 150, bubbles: true }));
    ev("pointerdown", 1, 120); ev("pointerdown", 2, 180); ev("pointermove", 1, 80); ev("pointermove", 2, 220); ev("pointerup", 1, 80); ev("pointerup", 2, 220);
  });
  expect(parseFloat(await img.evaluate((i) => i.style.width))).toBeGreaterThan(parseFloat(before));
  await page.getByRole("button", { name: "Use this crop" }).click();
  await expect(page.getByRole("button", { name: "Replace photo 1" })).toBeVisible();
  expect(uploads).toHaveLength(1);
  const size = jpegSize(uploads[0])!;
  expect(size.w).toBe(size.h);
  expect(uploads[0].length).not.toBe(original.length);

  await page.getByRole("button", { name: /Skip/ }).click();
  await page.getByLabel(/title/i).first().fill("Thin and quick");
  await page.getByRole("button", { name: "No, I bought it myself" }).click();
  await page.getByRole("button", { name: "Submit", exact: true }).last().click();
  await page.getByRole("button", { name: /Skip .* continue to submission/ }).click();
  await expect.poll(() => submitted).not.toBeNull();
  expect(submitted!.photo_url).toBeNull();
  expect(submitted!.photo_urls).toEqual([]);
  await api("voter", `/api/v1/review-drafts/${product.id}`, { method: "DELETE" });
  await context.close();
});

test("QA-071/072: a pasted link proposes an editable name and needs a category", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await as(context, "asker");
  const page = await context.newPage();
  await page.goto(`${BASE}/reviews/new`);
  const link = `https://shopee.ph/Baseus-Bowie-${fx.tag}-Earbuds-i.4455.${Date.now()}`;
  await page.getByLabel(/Paste its Shopee or Lazada link/).fill(link);
  await page.getByRole("button", { name: "Use this link" }).click();
  const name = page.getByLabel("Product name");
  await expect(name).toHaveValue(`Baseus Bowie ${fx.tag} Earbuds`);
  const add = page.getByRole("button", { name: "Add product" });
  await expect(add).toBeDisabled();
  await page.getByLabel("Category").selectOption("audio");
  await name.fill(link);
  await expect(add).toBeDisabled();
  await name.fill(`Baseus Bowie ${fx.tag} E2`);
  await expect(add).toBeEnabled();
  const created = page.waitForResponse((r) => r.url().endsWith("/api/bff/api/v1/products") && r.request().method() === "POST");
  await add.click();
  const product = await (await created).json();
  expect(product).toMatchObject({ canonical_name: `Baseus Bowie ${fx.tag} E2`, category: "audio", status: "pending" });
  await context.close();
});

test("QA-075: the claim form refuses a malformed registration and claims no verification", async ({ browser }) => {
  // A store of its own: the fixture's open store is claimed by an earlier spec.
  const store = await api("voter", "/api/v1/sellers", {
    method: "POST", body: JSON.stringify({ display_name: `R3 Shop ${fx.tag}`, platform: "shopee" }),
  });
  expect(store.status).toBe(201);
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await as(context, "asker");
  const page = await context.newPage();
  await page.goto(`${BASE}/sellers/${store.body.id}`);
  await page.getByRole("button", { name: "Claim this store" }).first().click();
  const number = page.locator('input[aria-describedby$="-number-help"]');
  await page.getByLabel("Registered business name").fill("OpenShop Trading");
  const send = page.getByRole("button", { name: "Send claim" });
  await number.fill("1234567");
  await expect(send).toBeDisabled();
  await expect(page.getByText("That looks like a placeholder")).toBeVisible();
  await number.fill("DTI-3318207");
  await expect(send).toBeEnabled();
  await expect(page.getByText(/We check the format only/)).toBeVisible();
  await expect(page.getByText(/government verified/i)).toHaveCount(0);
  await context.close();
});

test("QA-070: a review link unfurls with a public picture, and the share sheet shows it", async ({ page }) => {
  const html = await (await fetch(`${BASE}/reviews/${fx.reviews.old}`)).text();
  const og = html.match(/<meta property="og:image" content="([^"]+)"/)?.[1];
  expect(og).toBeTruthy();
  expect(og!.startsWith("https://")).toBe(true);
  expect(html).toMatch(/<meta name="twitter:card" content="summary_large_image"/);
  expect(og).not.toMatch(/receipt/i);
  await page.goto(`/reviews/${fx.reviews.old}`);
  await page.getByRole("button", { name: /^Share/ }).first().click();
  await expect(page.locator("dialog[open] img[data-share-preview-image]")).toBeVisible();
});

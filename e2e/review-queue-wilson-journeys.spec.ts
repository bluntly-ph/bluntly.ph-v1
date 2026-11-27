import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * QA patch of 2026-09-29 (Trust Score, anti-farming and plagiarism, Review
 * Queue / Wilson), on the REAL stack: production Next build, FastAPI, and
 * Postgres seeded by backend/scripts/e2e_fixtures.py. Every figure the browser
 * shows is read back from the API and compared. Skipped anywhere E2E_FIXTURES
 * is unset. See docs/QA_CURRENT_RECONCILIATION.md.
 *
 *   Q  review A and review B both reach the Review Queue once their
 *      trust-weighted votes pass the Post-Seeding gate, each with its OWN Wilson
 *   R  All Reviews lists both with both Wilson figures, sorts by Wilson either
 *      way, and Refresh shows a changed vote
 *   T  the Honesty Score on a review is the author's stored score rounded, and
 *      it moves when an earnings approval recalculates it
 *   D  a copied review is published at once and staff see why it was flagged;
 *      no address is shown anywhere
 *   N  three fresh accounts up-voting one member from one network, through the
 *      site (browser -> BFF -> API), produce a network report; no address or
 *      hash is shown. Runs only with E2E_EXPECT_NETWORK_SIGNAL=1: the site must
 *      sign the voter's address (VERCEL=1 + CLIENT_IP_SIGNING_SECRET on both the
 *      site and the API). Locally each voter's browser sends the same
 *      X-Forwarded-For, standing in for the Vercel edge.
 *   I  a resized copy of another review's photo is flagged as reused. Runs only
 *      with E2E_STORAGE=1: uploads need real Storage (a TEST/QA Preview).
 *
 * Against a protected Vercel Preview, set VERCEL_AUTOMATION_BYPASS_SECRET; it is
 * sent as x-vercel-protection-bypass on every page and API call and never logged.
 *
 * The API runs Post-Seeding (the default), so a new review joins the queue
 * only through its votes. The fixture's three voters are Stage 5 with
 * reputation 100 (weight 3.0 each): three up-votes pass the gate.
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = {
  photo_base: string;
  users: Record<string, { id: string; token: string; username: string }>;
};
const fx: Fx = FIXTURES
  ? JSON.parse(readFileSync(FIXTURES, "utf8"))
  : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

const TAG = Math.random().toString(36).slice(2, 8);
const VOTERS = ["rqvoter1", "rqvoter2", "rqvoter3"];

/** Vercel's protection bypass for a protected Preview, when one is given. */
const BYPASS: Record<string, string> = process.env
  .VERCEL_AUTOMATION_BYPASS_SECRET
  ? {
      "x-vercel-protection-bypass": process.env.VERCEL_AUTOMATION_BYPASS_SECRET,
      "x-vercel-set-bypass-cookie": "true",
    }
  : {};

/** Deleted by their authors afterwards, so the Recent feed other specs read is
 *  as they left it (see meeting-0929-journeys.spec.ts). */
const written: { who: string; id: string }[] = [];

test.afterAll(async () => {
  for (const { who, id } of written) {
    await api(who, `/api/v1/reviews/${id}?confirm=delete-thread`, {
      method: "DELETE",
    });
  }
});

async function as(context: BrowserContext, who: string) {
  await context.addCookies([
    { name: "bluntly_session", value: fx.users[who].token, url: BASE },
  ]);
}

async function api(who: string | null, path: string, init: RequestInit = {}) {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    ...BYPASS,
  };
  if (who) headers.authorization = `Bearer ${fx.users[who].token}`;
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...headers, ...(init.headers as object) },
  });
  return {
    status: res.status,
    body: res.status === 204 ? null : await res.json().catch(() => null),
  };
}

async function product(who: string, name: string): Promise<string> {
  const res = await api(who, "/api/v1/products", {
    method: "POST",
    body: JSON.stringify({ name, category: "electronics" }),
  });
  expect([200, 201]).toContain(res.status);
  return res.body.id;
}

/** A review with the author's own photo, so an administrator may approve its
 *  earnings (§3 ownership evidence). */
async function review(
  who: string,
  productId: string,
  title: string,
  discussion: string,
): Promise<string> {
  const photo_url = `${fx.photo_base}/${fx.users[who].id}/${randomBytes(16).toString("hex")}.jpg`;
  const res = await api(who, "/api/v1/reviews", {
    method: "POST",
    body: JSON.stringify({
      product_id: productId,
      title,
      discussion,
      verdict: "yes_absolutely",
      star_rating: 4,
      photo_url,
    }),
  });
  expect(res.status, JSON.stringify(res.body)).toBe(201);
  written.push({ who, id: res.body.id });
  return res.body.id;
}

async function vote(who: string, reviewId: string, direction: "up" | "down") {
  const res = await api(who, `/api/v1/reviews/${reviewId}/vote`, {
    method: "POST",
    body: JSON.stringify({ vote: direction }),
  });
  expect(res.status, JSON.stringify(res.body)).toBe(200);
}

type QueueItem = {
  review: { id: string; title: string; wilson_score: string };
};
async function queued(): Promise<QueueItem[]> {
  const res = await api(
    "administrator",
    `/api/v1/admin/review-queue?q=${TAG}&limit=100`,
  );
  expect(res.status).toBe(200);
  return res.body.items;
}

type Row = {
  id: string;
  title: string;
  wilson_score: string;
  in_review_queue: boolean;
  gate: { wilson_lower_bound: number; passes: boolean };
};
async function allReviews(sort = "newest"): Promise<Row[]> {
  const res = await api(
    "administrator",
    `/api/v1/admin/reviews?q=${TAG}&sort=${sort}&limit=100`,
  );
  expect(res.status).toBe(200);
  return res.body.items;
}

const two = (value: string | number) => Number(value).toFixed(2);

function queueRow(page: Page, title: string) {
  // The queue's first cell names the product and carries the title in its tooltip.
  return page.locator("tbody tr", {
    has: page.locator(`td[title*="${title}"]`),
  });
}

function allRow(page: Page, id: string) {
  return page.locator(
    `[data-testid="all-reviews-row"][data-review-id="${id}"]`,
  );
}

const A = `Queue A ${TAG}`;
const B = `Queue B ${TAG}`;
const ids: { a?: string; b?: string } = {};

test("Q. review A and review B both reach the Review Queue, each with its own Wilson", async ({
  page,
  context,
}) => {
  ids.a = await review(
    "rqwriter",
    await product("rqwriter", `Queue Kettle ${TAG}`),
    A,
    `Kettle ${TAG}: boils a litre in about four minutes and the lid seal has not leaked after a month of daily use.`,
  );
  ids.b = await review(
    "rqwriter",
    await product("rqwriter", `Queue Lamp ${TAG}`),
    B,
    `Desk lamp ${TAG}: the warm setting is easy on the eyes at night, though the clamp loosens if the arm is fully extended.`,
  );

  // Post-Seeding: published at once, not in the queue until the votes say so.
  expect(await queued()).toEqual([]);
  expect((await api(null, `/api/v1/reviews/${ids.a}`)).status).toBe(200);

  // A: three up-votes. B: the same three, and one down-vote from a Stage 1
  // member (weight 0.25), which keeps it above the gate but lowers its Wilson.
  await vote("rqcopier", ids.b, "down");
  for (const who of VOTERS) {
    await vote(who, ids.a, "up");
    await vote(who, ids.b, "up");
  }

  const items = await queued();
  const a = items.find((i) => i.review.id === ids.a);
  const b = items.find((i) => i.review.id === ids.b);
  expect(a, "review A is in the queue").toBeTruthy();
  expect(b, "review B is in the queue").toBeTruthy();
  expect(Number(a!.review.wilson_score)).toBeGreaterThan(
    Number(b!.review.wilson_score),
  );

  // The screen shows each review's own figure, not a shared or stale one.
  await as(context, "administrator");
  await page.goto(`/admin/review-queue?q=${TAG}`);
  await expect(page.getByTestId("queue-membership")).toContainText(
    "A new review joins once its trust-weighted votes pass the earnings gate.",
  );
  // The redesigned table (Figma 7943:11402) has no Wilson column; the figure
  // is in the review's modal.
  for (const [title, item] of [[A, a!], [B, b!]] as const) {
    await queueRow(page, title).click();
    await expect(page.getByRole("dialog").getByTestId("queue-wilson")).toHaveText(
      two(item.review.wilson_score),
    );
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).first().click();
  }
});

test("R. All reviews shows both figures, sorts by Wilson both ways, and a reload shows a changed vote", async ({
  page,
  context,
}) => {
  // Staff only.
  expect((await api("rqwriter", `/api/v1/admin/reviews?q=${TAG}`)).status).toBe(
    403,
  );

  const rows = await allReviews();
  const a = rows.find((r) => r.id === ids.a)!;
  const b = rows.find((r) => r.id === ids.b)!;
  expect(a.in_review_queue && b.in_review_queue).toBe(true);
  expect(a.gate.passes && b.gate.passes).toBe(true);

  await as(context, "administrator");
  await page.goto(`/admin/review-queue?tab=all&aq=${TAG}`);
  // Figma Queue/AllReviews 8060:15564: one Wilson column (public); the gate
  // figure, votes and the queue reason ride in each row's tooltip / sr text.
  await expect(page.getByRole("navigation", { name: "All reviews pages" })).toContainText("Showing 1–2 of 2");
  for (const row of [a, b]) {
    await expect(
      allRow(page, row.id).getByTestId("all-reviews-wilson"),
    ).toHaveText(two(row.wilson_score));
    await expect(
      allRow(page, row.id).getByTestId("all-reviews-gate"),
    ).toHaveText(two(row.gate.wilson_lower_bound));
    await expect(
      allRow(page, row.id).getByTestId("all-reviews-queue-status"),
    ).toHaveText("In the Review Queue");
  }

  // Wilson, high to low: A leads. Low to high: B leads. Same order as the API.
  await page.getByRole("button", { name: "Sort" }).click();
  await page.getByRole("menuitemradio", { name: "Wilson: high to low" }).click();
  await page.waitForURL(/asort=wilson_desc/);
  await expect(page.getByTestId("all-reviews-row").first()).toHaveAttribute(
    "data-review-id",
    ids.a!,
  );
  expect((await allReviews("wilson_desc")).map((r) => r.id)).toEqual([
    ids.a,
    ids.b,
  ]);
  await page.getByRole("button", { name: "Sort" }).click();
  await page.getByRole("menuitemradio", { name: "Wilson: low to high" }).click();
  await page.waitForURL(/asort=wilson_asc/);
  await expect(page.getByTestId("all-reviews-row").first()).toHaveAttribute(
    "data-review-id",
    ids.b!,
  );
  expect((await allReviews("wilson_asc")).map((r) => r.id)).toEqual([
    ids.b,
    ids.a,
  ]);

  // A voter changes their mind on A. The list shows the new figure on the
  // next load (the frame draws no Refresh), and A stays queued: votes never
  // pull a queued review back out.
  const before = two(a.wilson_score);
  await vote("rqvoter1", ids.a!, "down");
  const after = (await allReviews()).find((r) => r.id === ids.a)!;
  expect(two(after.wilson_score)).not.toBe(before);
  await page.reload();
  await expect(
    allRow(page, ids.a!).getByTestId("all-reviews-wilson"),
  ).toHaveText(two(after.wilson_score));
  await expect(
    allRow(page, ids.a!).getByTestId("all-reviews-votes"),
  ).toHaveText("2 / 1");
  await expect(
    allRow(page, ids.a!).getByTestId("all-reviews-queue-status"),
  ).toHaveText("In the Review Queue");
});

test("T. the Honesty Score shown is the author's stored score, and an approval recalculates it", async ({
  page,
  context,
}) => {
  // A signed-in reader: their page is never served from the shared cache. A
  // signed-out page may show the previous score for up to 60 seconds
  // (lib/reviews.ts getReviewFull, revalidate 60).
  await as(context, "rqvoter2");
  const shown = async (score: string) => {
    await page.goto(`/reviews/${ids.a}`);
    await expect(
      page
        .getByRole("img", {
          name: new RegExp(
            `trust score ${Math.round(Number(score))} out of 100$`,
          ),
        })
        .first(),
    ).toBeVisible();
  };
  const stored = async () =>
    (await api(null, `/api/v1/reviews/${ids.a}/full`)).body.author
      .reputation_score as string;

  const before = await stored();
  await shown(before);

  // An earnings approval counts the review toward its author's trust
  // (docs/TRUST_SCORE_COMPUTATION.md, §8): the score is recomputed from A's
  // votes, and the page shows the new figure.
  const approved = await api(
    "administrator",
    `/api/v1/admin/reviews/${ids.a}/approve-earnings`,
    { method: "POST" },
  );
  expect(approved.status, JSON.stringify(approved.body)).toBe(200);
  const after = await stored();
  expect(after).not.toBe(before);
  await shown(after);
});

test("D. a copied review is published at once, and staff see why it was flagged", async ({
  page,
  context,
}) => {
  const pid = await product("rqwriter", `Queue Fan ${TAG}`);
  const text =
    `Fan ${TAG}: three speeds, and even the highest is quiet enough to sleep beside. ` +
    "The oscillation clicks once at each end of its sweep, which you stop noticing after a night or two.";
  const original = await review("rqwriter", pid, `Original fan ${TAG}`, text);
  // Case, punctuation and spacing changed: still the same words.
  const copied = await review(
    "rqcopier",
    pid,
    `Second fan ${TAG}`,
    text.toUpperCase().replace(/[.,:]/g, " ;"),
  );

  // Publication is never held for it, and the public page accuses no one.
  expect((await api(null, `/api/v1/reviews/${copied}`)).status).toBe(200);
  await page.goto(`/reviews/${copied}`);
  await expect(
    page.getByRole("heading", { name: `Second fan ${TAG}` }),
  ).toBeVisible();
  // (The report form's own "Copied from somewhere else" choice is on every
  // review; the staff finding is what must not be.)
  await expect(page.locator("main")).not.toContainText(
    /possible copied|duplicate-text|system detected|plagiari/i,
  );

  await as(context, "administrator");
  await page.goto("/admin/review-queue?tab=report");
  // One table row per report; its first cell carries the review title. The
  // details open in a modal.
  const card = page.locator("tbody tr", { has: page.locator(`td[title*="Second fan ${TAG}"]`) }).first();
  await expect(card).toContainText("System");
  await card.click();
  const panel = page.getByRole("dialog").getByTestId("report-detail");
  await expect(panel.getByTestId("report-summary")).toContainText(
    "Possible copied review: its text closely matches another review already in the database",
  );
  await expect(
    panel.getByRole("link", { name: `Original fan ${TAG}` }),
  ).toHaveAttribute("href", `/reviews/${original}`);
  // Evidence, not an address: nothing shaped like an IP is on the panel.
  await expect(panel).not.toContainText(/\b\d{1,3}(\.\d{1,3}){3}\b|same IP/i);
});

test("N. up-votes from one network, cast through the site, become evidence with no address", async ({
  browser,
}) => {
  test.skip(
    process.env.E2E_EXPECT_NETWORK_SIGNAL !== "1",
    "needs a site that signs the voter's address (E2E_EXPECT_NETWORK_SIGNAL=1)",
  );
  // A documentation-range address, fresh each run, standing in for the edge's
  // view of one household. On a real Preview the edge overwrites it with the
  // runner's own address, which is the same for all three voters anyway.
  const network = `198.51.100.${10 + Math.floor(Math.random() * 200)}`;
  const target = await review(
    "rqwriter",
    await product("rqwriter", `Network Router ${TAG}`),
    `Network router ${TAG}`,
    `Router ${TAG}: covers two floors without a mesh node, and the admin page loads quickly on a phone.`,
  );

  for (const who of ["rqfresh1", "rqfresh2", "rqfresh3"]) {
    const context = await browser.newContext({
      extraHTTPHeaders: { ...BYPASS, "x-forwarded-for": network },
    });
    await as(context, who);
    const page = await context.newPage();
    await page.goto(`${BASE}/reviews/${target}`);
    const helpful = page.getByRole("button", { name: /^Helpful, / }).first();
    await helpful.click();
    await expect(helpful).toHaveAttribute("aria-pressed", "true");
    await context.close();
  }
  // Every vote stands: the signal removes nothing.
  expect(
    (await api(null, `/api/v1/reviews/${target}`)).body.helpful_votes,
  ).toBe(3);

  // Staff see the report, with counts and no address.
  const author = fx.users.rqwriter.id;
  let found: { explanation?: { summary: string } } | undefined;
  const everything: unknown[] = [];
  for (let offset = 0; offset < 2000 && !found; offset += 100) {
    const res = await api(
      "administrator",
      `/api/v1/admin/reports?limit=100&offset=${offset}`,
    );
    expect(res.status).toBe(200);
    everything.push(...res.body.items);
    found = res.body.items.find(
      (i: {
        report: { target_ref: string };
        explanation?: { signal?: string };
      }) =>
        i.report.target_ref === author &&
        i.explanation?.signal === "shared_network_votes",
    );
    if (res.body.items.length < 100) break;
  }
  expect(found, "a shared-network report on the author").toBeTruthy();
  expect(found!.explanation!.summary).toMatch(
    /^Possible vote farming: \d+ accounts on one network/,
  );
  expect(found!.explanation!.summary).toContain(
    "No IP address is stored or shown.",
  );
  // The address appears in no staff API response.
  expect(JSON.stringify(everything)).not.toContain(network);
});

test("I. a resized copy of another review's photo is flagged as reused", async ({
  page,
}) => {
  test.skip(
    process.env.E2E_STORAGE !== "1",
    "uploads need real Storage (E2E_STORAGE=1 on a TEST/QA Preview)",
  );
  // A photo drawn fresh for this run, and the same photo at half size, lower
  // quality: a different file with the same picture.
  await page.goto(`${BASE}/welcome`);
  const [original, resized] = await page.evaluate(() => {
    const big = document.createElement("canvas");
    big.width = 1200;
    big.height = 900;
    const g = big.getContext("2d")!;
    g.fillStyle = `hsl(${Math.random() * 360} 60% 50%)`;
    g.fillRect(0, 0, 1200, 900);
    for (let i = 0; i < 25; i++) {
      g.fillStyle = `hsl(${Math.random() * 360} 70% ${20 + Math.random() * 60}%)`;
      g.fillRect(
        Math.random() * 1200,
        Math.random() * 900,
        50 + Math.random() * 450,
        50 + Math.random() * 350,
      );
    }
    const small = document.createElement("canvas");
    small.width = 600;
    small.height = 450;
    small.getContext("2d")!.drawImage(big, 0, 0, 600, 450);
    return [
      big.toDataURL("image/jpeg", 0.9),
      small.toDataURL("image/jpeg", 0.6),
    ];
  });
  const upload = async (who: string, dataUrl: string): Promise<string> => {
    const form = new FormData();
    form.append(
      "file",
      new Blob([Buffer.from(dataUrl.split(",")[1], "base64")], {
        type: "image/jpeg",
      }),
      "photo.jpg",
    );
    const res = await fetch(`${API}/api/v1/reviews/photo`, {
      method: "POST",
      headers: { ...BYPASS, authorization: `Bearer ${fx.users[who].token}` },
      body: form,
    });
    expect(res.status).toBe(200);
    return (await res.json()).url;
  };
  const withPhoto = async (who: string, title: string, url: string) => {
    const res = await api(who, "/api/v1/reviews", {
      method: "POST",
      body: JSON.stringify({
        product_id: await product(who, `${title} product`),
        title,
        discussion: `${title}: a week of use so far, and it does what the listing said it would.`,
        verdict: "yes_absolutely",
        star_rating: 4,
        photo_url: url,
      }),
    });
    expect(res.status, JSON.stringify(res.body)).toBe(201);
    written.push({ who, id: res.body.id });
    return res.body.id as string;
  };
  const first = await withPhoto(
    "rqwriter",
    `Photo original ${TAG}`,
    await upload("rqwriter", original),
  );
  const second = await withPhoto(
    "rqcopier",
    `Photo reused ${TAG}`,
    await upload("rqcopier", resized),
  );
  expect((await api(null, `/api/v1/reviews/${second}`)).status).toBe(200);

  let found:
    | {
        explanation?: {
          summary: string;
          evidence: { label: string; link?: string }[];
        };
      }
    | undefined;
  for (let offset = 0; offset < 2000 && !found; offset += 100) {
    const res = await api(
      "administrator",
      `/api/v1/admin/reports?limit=100&offset=${offset}`,
    );
    found = res.body.items.find(
      (i: {
        report: { target_ref: string };
        explanation?: { signal?: string };
      }) =>
        i.report.target_ref === second &&
        i.explanation?.signal === "duplicate_image",
    );
    if (res.body.items.length < 100) break;
  }
  expect(found, "a reused-photo report on the later review").toBeTruthy();
  expect(found!.explanation!.summary).toMatch(/^Possible reused photo/);
  const matching = found!.explanation!.evidence.find(
    (e) => e.label === "Matching review",
  );
  expect(matching?.link).toBe(`/reviews/${first}`);
});

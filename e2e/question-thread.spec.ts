import { readFileSync } from "node:fs";

import { expect, test, type BrowserContext } from "@playwright/test";

/**
 * The question page as a thread (Figma Question Detail v6B 7731:15601,
 * migration 0073): a member up-votes the question, votes an answer helpful and
 * replies under it; all three survive a reload and read back from the API; the
 * composer opens the answer flow. The asker cannot up-vote their own question.
 * Skipped anywhere E2E_FIXTURES is unset (scripts.e2e_fixtures writes it).
 */

const FIXTURES = process.env.E2E_FIXTURES;
const API = process.env.E2E_API_URL ?? "http://localhost:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
type Fx = { users: Record<string, { id: string; token: string }>; question: string; answer: string };
const fx: Fx = FIXTURES ? JSON.parse(readFileSync(FIXTURES, "utf8")) : ({} as Fx);

test.skip(!FIXTURES, "needs the seeded real stack (E2E_FIXTURES)");
test.describe.configure({ mode: "serial", retries: 0 });
test.setTimeout(90_000);

async function as(context: BrowserContext, who: string) {
  await context.addCookies([{ name: "bluntly_session", value: fx.users[who].token, url: BASE }]);
}

async function detail(who: string) {
  const res = await fetch(`${API}/api/v1/questions/${fx.question}`, {
    headers: { authorization: `Bearer ${fx.users[who].token}` },
  });
  return (await res.json()) as {
    upvotes: number;
    my_upvote: boolean;
    reply_count: number;
    answers: { id: string; helpful_votes: number; my_vote: string | null; replies: { body: string }[] }[];
  };
}

test("a member up-votes, votes an answer and replies; it all persists", async ({ page, context }) => {
  await as(context, "stranger");
  const before = await detail("stranger");
  await page.goto(`/questions/${fx.question}`);

  const up = page.getByTestId("question-upvote");
  await expect(up).toHaveAttribute("aria-pressed", before.my_upvote ? "true" : "false");
  if (before.my_upvote) {
    await up.click();
    await expect(up).toHaveAttribute("aria-pressed", "false");
  }
  await up.click();
  await expect(up).toHaveAttribute("aria-pressed", "true");

  const answer = page.locator(`#answer-${fx.answer}`);
  const helpful = answer.getByRole("button", { name: /^Helpful/ }).first();
  if ((await helpful.getAttribute("aria-pressed")) === "true") await helpful.click();
  await expect(helpful).toHaveAttribute("aria-pressed", "false");
  await helpful.click();
  await expect(helpful).toHaveAttribute("aria-pressed", "true");

  const text = `Thread check ${Date.now()}`;
  await answer.getByTestId("reply-toggle").click();
  await answer.getByLabel("Your reply").fill(text);
  await answer.getByTestId("reply-submit").click();
  await expect(page.getByText(text)).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("question-upvote")).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(`#answer-${fx.answer}`).getByRole("button", { name: /^Helpful/ }).first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByText(text)).toBeVisible();

  const after = await detail("stranger");
  expect(after.my_upvote).toBe(true);
  const a = after.answers.find((x) => x.id === fx.answer)!;
  expect(a.my_vote).toBe("up");
  expect(a.replies.some((r) => r.body === text)).toBe(true);
  expect(after.reply_count).toBeGreaterThan(before.reply_count);

  await page.getByRole("link", { name: /Write your answer/ }).click();
  await page.waitForURL(`**/questions/${fx.question}/answer`);
  await expect(page.getByText("Step 1 out of 7")).toBeVisible();
});

test("the asker cannot up-vote their own question", async ({ page, context }) => {
  await as(context, "asker");
  await page.goto(`/questions/${fx.question}`);
  await expect(page.getByTestId("question-upvote")).toBeDisabled();
  const res = await fetch(`${API}/api/v1/questions/${fx.question}/vote`, {
    method: "PUT",
    headers: { "content-type": "application/json", authorization: `Bearer ${fx.users.asker.token}` },
    body: JSON.stringify({ up: true }),
  });
  expect(res.status).toBe(422);
});

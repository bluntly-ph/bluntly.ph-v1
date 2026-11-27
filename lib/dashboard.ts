import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

/**
 * Reviewer earnings data, fetched server-side with the session token: the PHP
 * wallet balance and the payout history. Each call is defended so one failing
 * endpoint doesn't blank the whole dashboard.
 *
 * The token ledger (`/tokens/transactions`) is deliberately NOT read here. Its
 * `amount` is an integer token count, not pesos, and the token economy was
 * retired in favour of the PHP revenue share — surfacing it next to peso figures
 * read as money and wasn't. `/tokens/balance` is still the only source of
 * `wallet_balance`, so it stays; only `token_balance` is ignored.
 */

export type Balance = { token_balance: number; wallet_balance: string };

export type Payout = {
  id: string;
  amount: string;
  currency: string;
  status: string;
  scheduled_for: string;
  paid_at: string | null;
  created_at: string;
  provider_ref?: string | null;
  failure_reason?: string | null;
};

/** Minimum PHP wallet balance before a payout can be scheduled (PAYOUT_MIN_PHP). */
export const PAYOUT_MIN_PHP = 300;

/**
 * Business Rules §19: what can be cashed out now and what is still clearing
 * (GET /payouts/balance). Earned commission clears only once the marketplace
 * has paid Bluntly for that month; until then it is shown, never withdrawable.
 */
export type PayoutBalance = {
  wallet_balance: string;
  withdrawable: string;
  pending_clearance: string;
  minimum_cashout: string;
  can_cash_out: boolean;
  payout_account_set: boolean;
  /** A named QA tester: the balance may hold sandbox test earnings. */
  qa_tester?: boolean;
  /** Figma Screen/Payout: the withdrawable money split for its pie chart. */
  withdrawable_commission?: string;
  withdrawable_honesty_fund?: string;
  /** The locked state: how far the withdrawable money is from the minimum. */
  short_of_minimum?: string;
  /** Requested and waiting to be sent. */
  in_flight?: string;
  /** Where payouts go, masked (j***@gmail.com). */
  payout_account_masked?: string | null;
  /** The name on that account, as the member gave it (Screen/Payout/Details). */
  payout_account_name?: string | null;
};

export async function getPayoutBalance(): Promise<PayoutBalance | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<PayoutBalance>("/api/v1/payouts/balance", { token }).catch(() => null);
}

export async function getDashboard(): Promise<{
  balance: Balance | null;
  payouts: Payout[];
}> {
  const token = await getSessionToken();
  if (!token) return { balance: null, payouts: [] };

  const [balance, payouts] = await Promise.all([
    apiFetch<Balance>("/api/v1/tokens/balance", { token }).catch(() => null),
    apiFetch<Payout[]>("/api/v1/payouts", { token }).catch(() => []),
  ]);
  return { balance, payouts };
}

/** ₱ with two decimals, from a string-decimal amount (never parse for math). */
export function peso(amount: string | number): string {
  const n = typeof amount === "string" ? Number(amount) : amount;
  return `₱${n.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export type DashboardSeriesPoint = { day: string; amount: string };

export type DashboardReviewRow = {
  review_id: string;
  title: string;
  photo_url: string | null;
  earnings: string;
  views: number;
  helped: number;
  series: DashboardSeriesPoint[];
};

export type DashboardSummary = {
  range: string;
  window_start: string;
  window_end: string;
  estimated_commission: string;
  earned_in_window: string;
  total_views: number;
  /** Null while nothing measures read time; `unavailable` names it. */
  average_read_seconds: number | null;
  unavailable: string[];
  has_earnings: boolean;
  series: DashboardSeriesPoint[];
  reviews: DashboardReviewRow[];
};

export const DASHBOARD_RANGES = [
  { key: "7d", label: "This week" },
  { key: "30d", label: "This month" },
  { key: "90d", label: "Last 90 days" },
] as const;

export async function getDashboardSummary(
  range: string,
): Promise<DashboardSummary | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const key = DASHBOARD_RANGES.some((r) => r.key === range) ? range : "7d";
  return apiFetch<DashboardSummary>(
    `/api/v1/users/me/dashboard?range=${key}`, { token },
  ).catch(() => null);
}

/**
 * Compact counts, the way the design writes them: "47k views", "1.3k helped".
 *
 * Below 1000 the exact number is short enough to be worth keeping — "900
 * helped" is more useful than "0.9k".
 */
export function compactCount(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) {
    const k = n / 1000;
    return `${k < 10 ? k.toFixed(1).replace(/\.0$/, "") : Math.round(k)}k`;
  }
  const m = n / 1_000_000;
  return `${m < 10 ? m.toFixed(1).replace(/\.0$/, "") : Math.round(m)}m`;
}

/** ₱ with no decimals — the list rows in the design read "₱536", not "₱536.00". */
export function pesoWhole(amount: string | number): string {
  const n = typeof amount === "string" ? Number(amount) : amount;
  return `₱${Math.round(n).toLocaleString("en-PH")}`;
}

export type EarningBreakdown = {
  gross_amount: string;
  commission_rate: string | null;
  platform_share: string;
  honesty_fund_share: string;
  reviewer_share: string;
};

export type EarningRow = {
  commission_id: string;
  occurred_on: string;
  review_id: string | null;
  review_title: string | null;
  product_name: string | null;
  photo_url: string | null;
  amount: string;
  /** pending | to_earn | paid | returned */
  status: string;
  breakdown: EarningBreakdown;
  /** A QA sandbox test earning: credited to test payouts, no sale behind it. */
  is_test?: boolean;
};

export type EarningsHistory = {
  all_time: string;
  counts: Record<string, number>;
  rows: EarningRow[];
  has_data: boolean;
};

/**
 * The History frame's filter tabs.
 *
 * These are the reviewer-facing reading of the canonical pair, not the
 * canonical vocabulary itself — "To earn" is a completed sale that has not been
 * paid, which is exactly the distinction a reviewer needs and exactly what
 * "Completed" would blur.
 */
/**
 * The tabs frame 5762:472 actually draws: All / Pending / To earn / Returned.
 *
 * `paid` is a real settlement state and the API serves it, but the frame has no
 * tab for it, so it is reachable by URL rather than shown as a fifth tab that
 * the design does not have. Paid rows still appear under All.
 */
export const EARNING_TABS = [
  { key: "all", label: "All" },
  { key: "pending", label: "Pending" },
  { key: "to_earn", label: "To earn" },
  { key: "returned", label: "Returned" },
] as const;

/** Every filter the API accepts, including the one with no tab. */
export const EARNING_FILTERS = ["all", "pending", "to_earn", "paid", "returned"];

/**
 * Sum peso strings exactly, in centavos.
 *
 * The shares are rounded independently when they are written, so adding them as
 * floats can land a centavo out on a screen whose entire job is showing a
 * reviewer where their money went.
 */
export function sumPeso(...values: (string | null | undefined)[]): string {
  const centavos = values.reduce((total, v) => {
    if (!v) return total;
    const [whole, frac = ""] = String(v).replace(/[^0-9.-]/g, "").split(".");
    const sign = whole.trim().startsWith("-") ? -1 : 1;
    const w = Math.abs(parseInt(whole, 10) || 0);
    const c = parseInt((frac + "00").slice(0, 2), 10) || 0;
    return total + sign * (w * 100 + c);
  }, 0);
  return (centavos / 100).toFixed(2);
}

/** Badge tone per status. Each badge also carries its own words. */
export const EARNING_TONE: Record<string, string> = {
  pending: "bg-[var(--accent-star)]/15 text-[var(--accent-star)]",
  to_earn: "bg-[var(--accent-success)]/15 text-[var(--accent-success)]",
  paid: "bg-[var(--accent-trust)]/15 text-[var(--accent-trust)]",
  returned: "bg-[var(--accent-danger)]/15 text-[var(--accent-danger)]",
};

export const EARNING_LABEL: Record<string, string> = {
  pending: "Pending",
  to_earn: "To earn",
  paid: "Paid",
  returned: "Returned",
};

export async function getEarnings(
  status: string,
): Promise<EarningsHistory | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const key = EARNING_FILTERS.includes(status) ? status : "all";
  return apiFetch<EarningsHistory>(
    `/api/v1/users/me/earnings?status=${key}`, { token },
  ).catch(() => null);
}

/**
 * The Insights contribution streak (frame 5762:752).
 *
 * Owner decision, 2026-08-27: this counts days the reviewer CONTRIBUTED —
 * published a review, asked a question, answered one, or submitted a price
 * observation. It is not an attendance metric, and nothing here tracks reading
 * or browsing. Every date comes from a timestamp the backend already stores.
 */
export type StreakDay = { day: string; contributed: boolean };

export type ContributionStreak = {
  current_streak: number;
  last_contribution: string | null;
  active_today: boolean;
  total_days: number;
  calendar_month: string;
  calendar: StreakDay[];
};

export async function getStreak(): Promise<ContributionStreak | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<ContributionStreak>("/api/v1/users/me/streak", { token })
    .catch(() => null);
}

/** A question on the dashboard's Answers tab (GET /questions/mine). */
export type MyAnswer = {
  id: string;
  body: string;
  is_best_answer: boolean;
  is_seller_answer: boolean;
  seller_name: string | null;
  created_at: string;
  responder: { username: string | null; display_name: string | null } | null;
  /** The answer's own words, without its structured lines (the API parses every body). */
  parts?: { text?: string | null } | null;
};

export type MyQuestion = {
  id: string;
  body: string;
  product_name: string | null;
  seller_name: string | null;
  answer_count: number;
  created_at: string;
  latest_answers: MyAnswer[];
  my_answer: MyAnswer | null;
};

/** The Answers tab: questions the member asked, and questions they answered. */
export async function getMyQuestions(): Promise<{ asked: MyQuestion[]; answered: MyQuestion[] } | null> {
  const token = await getSessionToken();
  if (!token) return null;
  try {
    const [asked, answered] = await Promise.all([
      apiFetch<MyQuestion[]>("/api/v1/questions/mine?role=asked&limit=30", { token }),
      apiFetch<MyQuestion[]>("/api/v1/questions/mine?role=answered&limit=30", { token }),
    ]);
    return { asked, answered };
  } catch {
    return null;
  }
}

// The redesigned contributor dashboard (Figma Screen/Dashboard 7833:9534) ------

export type ContributorBucket = { label: string; start: string; end: string; earned: string; returned: string; current: boolean };
export type ContributorBest = {
  review_id: string;
  product_id: string | null;
  product_name: string;
  image_url: string | null;
  views: number;
  helped: number;
  earned: string;
};
export type ContributorRequirement = { key: string; label: string; have: number; needed: number; done: boolean };
export type ContributorReach = { views: number; helped: number; clicks: number; bought: number };
export type ContributorDashboard = {
  total_balance: string;
  commission_balance: string;
  honesty_fund_balance: string;
  pending: string;
  withdrawable: string;
  minimum_cashout: string;
  period: "week" | "month";
  earned: string;
  returned: string;
  buckets: ContributorBucket[];
  best: ContributorBest[];
  stage: number;
  level_name: string;
  next_stage: number | null;
  next_level_name: string | null;
  requirements: ContributorRequirement[];
  held_for_review: boolean;
  honesty_score: number;
  honesty_fund_earned: string;
  /** Any commission or Honesty Fund credit on record, ever (the empty state). */
  has_earned?: boolean;
  reach_choice: "this" | "last";
  reach_month: string;
  reach_previous_month: string;
  reach: ContributorReach;
  reach_previous: ContributorReach;
};

/** Wallet, earnings, trust stage and reach in one read (`/users/me/contributor`). */
export async function getContributorDashboard(period: string, reach: string): Promise<ContributorDashboard | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const p = period === "month" ? "month" : "week";
  const r = reach === "last" ? "last" : "this";
  return apiFetch<ContributorDashboard>(`/api/v1/users/me/contributor?period=${p}&reach=${r}`, { token }).catch(() => null);
}

// Performance (Figma Screen/Performance 7848:9542) -------------------------------

export type PerformanceProduct = {
  product_id: string;
  name: string;
  image_url: string | null;
  reviews: number;
  /** "Your reviews" rows: the period's views, people helped and earnings. */
  views: number;
  helped: number;
  earned: string;
  /** The latest published review of it (the chooser's date). */
  published_at?: string | null;
};
export type PerformanceBucket = {
  label: string;
  start: string;
  end: string;
  views: number;
  helped: number;
  earned: string;
  returned: string;
  current: boolean;
  /** Helpful / not-helpful votes cast in the bucket (Card/Votes). */
  up: number;
  down: number;
};
export type Performance = {
  period: "week" | "month";
  product_id: string | null;
  products: PerformanceProduct[];
  totals: ContributorReach;
  earned: string;
  returned: string;
  buckets: PerformanceBucket[];
  /** Card/Review: average stars and count of these reviews; all-time helpful votes and comments. */
  rating: string | null;
  review_count: number;
  upvotes: number;
  comments: number;
  /** Card/Votes totals over the period. */
  helpful: number;
  not_helpful: number;
  /** Card/Earnings: the last 30 Manila days, oldest first. */
  daily: { day: string; earned: string }[];
  earned_30d: string;
  earned_7d: string;
  /** Card/From view to buy: the last 7 days and the 7 before. */
  reach_week: ContributorReach | null;
  reach_prev_week: ContributorReach | null;
  /** Card/Commission: the split of the breakdown's net commission (every credited sale). */
  share_you: string;
  share_honesty_fund: string;
  share_platform: string;
  /** Card/Buyers: completed orders per marketplace (Shopee and Lazada always). */
  orders: { platform: string; orders: number }[];
  /** The ⓘ "Commission breakdown" sheet (Figma 9057:47088). */
  commission?: CommissionBreakdown | null;
};

export type CommissionBreakdown = import("@/lib/api-types").components["schemas"]["CommissionBreakdownOut"];

/** All reviewed products, or one (the screen's product switcher). */
export async function getPerformance(productId: string | null, period: string): Promise<Performance | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const params = new URLSearchParams({ period: period === "week" ? "week" : "month" });
  if (productId && /^[0-9a-f-]{36}$/i.test(productId)) params.set("product_id", productId);
  return apiFetch<Performance>(`/api/v1/users/me/performance?${params}`, { token }).catch(() => null);
}

// Payout tips (Figma 7844:9469, 7844:9529, 7843:9501) ---------------------------

export type PayoutTips = import("@/lib/api-types").components["schemas"]["PayoutTipsOut"];

/** Open questions to answer and reviews missing proof (`/users/me/payout-tips`). */
export async function getPayoutTips(): Promise<PayoutTips | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<PayoutTips>("/api/v1/users/me/payout-tips", { token }).catch(() => null);
}

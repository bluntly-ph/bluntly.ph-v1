import "server-only";

import type { AllReviewsPage, AllReviewsResult } from "@/components/admin/all-reviews-model";
import type { Triage } from "@/components/admin/review-queue-model";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

/** One card in the administrator queue (GET /admin/review-queue). */
export type QueueItem = {
  review: {
    id: string;
    title: string;
    discussion: string;
    verdict: "yes_absolutely" | "it_depends" | "hard_pass";
    star_rating: number;
    verification_status: "verified" | "unverified";
    /** Proof of purchase was submitted. Never its location — administrators fetch
     *  the object itself from GET /reviews/{id}/receipt, which authorizes the
     *  caller and returns a short-lived signed URL. */
    has_receipt: boolean;
    /** Disclosure (X.1); null when the review predates the question. */
    material_relationship?: "none" | "free_or_discounted" | "connected" | null;
    created_at: string;
    /** Already served by ReviewOut; the queue screen's Score column and the
     *  detail panel read these rather than inventing a ranking. */
    review_id: string | null;
    photo_url: string | null;
    wilson_score: string;
    helpful_votes: number;
    unhelpful_votes: number;
    /** Null when an administrator has taken the review down (it is public otherwise). */
    published_at?: string | null;
    earn_eligible_status?: string;
  };
  product: {
    id: string;
    canonical_name: string | null;
    source_url: string | null;
    platforms: { platform: string; is_monetizable: boolean }[];
  };
  author: {
    id: string;
    display_name: string | null;
    trust_stage: number;
    reputation_score: string;
    /** The reviewer snapshot's fourth figure (contract §17), served since 2026-09-16. */
    verified_review_count: number;
  } | null;
  /** The review's comment total, removed ones excluded. */
  comment_count: number;
  suggested_platform: string | null;
  suggested_sub_id: string | null;
  /** This monetized review was edited after its affiliate link was attached. */
  edited_since_monetized?: boolean;
  signals: {
    velocity: boolean;
    collusion: boolean;
    duplicate_content: boolean;
    author_account_age_days: number;
    author_review_count: number;
  };
  /**
   * FR-8 layers 2 and 3 (plagiarism, reverse image). A sibling of `signals`,
   * which stays frozen at the advisory six. Optional so a card from an older
   * API still renders — and renders as "No provider", never as a pass.
   */
  integrity?: { plagiarism_status?: string; reverse_image_status?: string };
  /**
   * The voting relationships behind `signals.collusion` / `signals.velocity`
   * (dev/QA sync 2026-09-29). Accounts only: no voter IP or location exists.
   * Optional so a card from an older API still renders.
   */
  voting?: {
    upvoters: number;
    reciprocal_upvoters: number;
    min_upvoters: number;
    threshold: number;
    max_upvotes_in_velocity_window: number;
    velocity_window_seconds: number;
    velocity_threshold: number;
  };
  /**
   * The server's priority assessment for this card (policy `review-priority-v1`).
   *
   * A sibling of `signals`, never a field inside it: the six advisory signals
   * are frozen by the backend's telemetry-isolation gate. The signals are
   * evidence an administrator reads; this is the policy's decision about where the
   * card sits, and the console renders it rather than deriving its own.
   */
  priority: {
    policy_version: string;
    lane: string;
    score: number;
    band: string;
    sla_state: string;
    due_at: string;
    factors: {
      code: string;
      observed: boolean | number | string;
      contribution: number;
      explanation: string;
    }[];
    /** Business Rules §12: "user_reported" and/or "system_detected". */
    origins?: string[];
  };
  /** Which review timestamp stood in for the queue-entry time (no column yet). */
  queue_time_basis?: string;
  /** Admin priority tier (dev note 2026-09-26): triage only, never membership. */
  triage?: Triage | null;
};

/** Totals over the whole filtered queue, computed before the page was cut. */
export type QueueCounts = {
  total: number;
  by_lane: Record<string, number>;
  by_band: Record<string, number>;
  by_sla: Record<string, number>;
  /** Admin priority tiers over the same filtered set. */
  by_tier?: Record<string, number>;
  /** MQA-015: what each view ("waiting", "taken_down") would show. */
  by_view?: Record<string, number>;
};

/**
 * What the queue screen received.
 *
 * A discriminated result, because "the API failed" and "there is nothing in
 * the queue" must not render the same. They used to: `getQueue` caught every
 * error and returned empty arrays, so an outage drew an empty table under the
 * words "nothing waiting" — the single most reassuring thing a moderation
 * console can say, and in that moment the least true.
 */
export type QueueResult =
  | {
      available: true;
      items: QueueItem[];
      total: number;
      counts: QueueCounts;
      /** Which earnings-gate phase decides membership (Business Rules §2). */
      earnGatePhase: "seeding" | "post_seeding";
      fetchedAt: number;
    }
  | { available: false; reason: "unauthenticated" | "unavailable"; fetchedAt: number };

/** One filed report in the administrator queue (GET /admin/reports). */
export type ReportItem = {
  report: {
    id: string;
    log_id: string | null;
    target_type: string | null;
    target_ref: string | null;
    reason: string | null;
    notes: string | null;
    evidence_url: string | null;
    created_at: string;
    /** How the report was closed. null while it is still open. */
    resolution:
      | "dismissed"
      | "content_removed"
      | "content_restored"
      | "escalated"
      | null;
    resolved_at: string | null;
  };
  reporter: {
    id: string;
    display_name: string | null;
    username: string | null;
    trust_stage: number;
  } | null;
  target: {
    id: string;
    title: string | null;
    author_id: string | null;
    is_published: boolean;
    /** Same-site path to the item (`/reviews/…`, `…#comment-…`), or null. */
    link?: string | null;
    /** The reported content, shown beside the report (dev/QA sync 2026-09-29). */
    excerpt?: string | null;
    author_username?: string | null;
    product_name?: string | null;
    star_rating?: number | null;
    verdict?: string | null;
    /** "published", "taken_down", "removed", or "member" for an account. */
    state?: string | null;
  } | null;
  target_report_count: number;
  /** Business Rules §12: a person's report, or an automated integrity signal. */
  origin?: "user_reported" | "system_detected";
  /** The target's trust-weighted open reports; escalation is at 1.0. */
  target_weighted_reports?: number;
  escalated?: boolean;
  urgent_reason?: boolean;
  report_surge?: boolean;
  /** The reported item's admin priority tier (open queue only). */
  triage?: Triage | null;
  /**
   * Why it was reported, written by the server from stored fields only: the
   * member's category and note, or the system signal and the evidence stored
   * when it fired. Never generated text.
   */
  explanation?: ReportExplanation | null;
  /** MQA-003: a reported review's integrity checks, as its queue card has them. */
  review_signals?: ReportReviewSignals | null;
};

/** The Review Queue card's checks for a reported review (GET /admin/reports). */
export type ReportReviewSignals = {
  signals: QueueItem["signals"] & { duplicate_of?: string | null };
  voting?: QueueItem["voting"] | null;
  integrity?: QueueItem["integrity"];
  edited_since_monetized?: boolean;
  /** The review has a photo, so the reused-photo check applies. */
  has_photo?: boolean;
  /** The System found its photo on an earlier review. */
  reused_photo?: boolean;
};

export type ReportExplanation = {
  summary: string;
  signal: string | null;
  signal_label: string | null;
  evidence: { label: string; value: string; link: string | null }[];
  /** False for a system report filed before its evidence was stored. */
  evidence_stored: boolean;
};

/** Reader-facing labels for the backend `ModerationReason` enum. */
export { REPORT_REASON_LABELS } from "@/components/admin/review-queue-model";

/**
 * Reports filed by the community, newest first. Defended like the review queue:
 * a failing reports endpoint must not blank the whole moderation page.
 */
/** One page of the Reports view, with the API's totals for the whole status
 *  (MQA-045): `total` reports on `itemsTotal` distinct items. Both are null
 *  when the request failed, so an outage never reads as "0 reports". */
export type ReportsPage = { items: ReportItem[]; total: number | null; itemsTotal: number | null };

export async function getReports(query = "limit=50"): Promise<ReportsPage> {
  const token = await getSessionToken();
  if (!token) return { items: [], total: null, itemsTotal: null };
  try {
    const res = await apiFetch<{ items: ReportItem[]; total: number; items_total?: number }>(
      `/api/v1/admin/reports?${query}`,
      { token },
    );
    return { items: res.items, total: res.total, itemsTotal: res.items_total ?? null };
  } catch {
    return { items: [], total: null, itemsTotal: null };
  }
}

/**
 * One page of the policy-ordered review queue.
 *
 * `query` is the already-validated canonical filter string from
 * `review-queue-model.queueApiQuery` — band, lane, sla, factor, q, limit and
 * offset. Ordering and filtering happen server-side across the whole backlog,
 * so a High-priority review submitted after the first fifty is on page one.
 *
 * `fetchedAt` is when the queue was read, as epoch milliseconds. The screen
 * writes every timestamp as "3s ago" and renders on the server before it
 * hydrates on the client; reading the clock inside the component would give
 * those two renders different answers and tear the table's hydration. Reading
 * it once here also makes it true — these ages are relative to the fetch.
 */
export async function getQueue(query = `limit=${50}`): Promise<QueueResult> {
  const fetchedAt = Date.now();
  const token = await getSessionToken();
  if (!token) return { available: false, reason: "unauthenticated", fetchedAt };
  try {
    const res = await apiFetch<{
      items: QueueItem[];
      total: number;
      counts: QueueCounts;
      earn_gate_phase?: "seeding" | "post_seeding";
    }>(`/api/v1/admin/review-queue?${query}`, { token });
    return {
      available: true,
      items: res.items ?? [],
      total: res.total ?? 0,
      counts: res.counts ?? { total: 0, by_lane: {}, by_band: {}, by_sla: {} },
      earnGatePhase: res.earn_gate_phase ?? "post_seeding",
      fetchedAt,
    };
  } catch {
    // Deliberately NOT an empty queue. The caller renders the difference.
    return { available: false, reason: "unavailable", fetchedAt };
  }
}

/**
 * One page of All Reviews (GET /admin/reviews): every review that still
 * exists, with its current votes and both Wilson figures. `query` comes from
 * `all-reviews-model.allReviewsApiQuery`. Uncached, like every signed-in read
 * (`apiFetch` never caches a request that carries a token), so a vote cast a
 * moment ago is on the next load.
 */
export async function getAllReviews(query: string): Promise<AllReviewsResult> {
  const fetchedAt = Date.now();
  const token = await getSessionToken();
  if (!token) return { available: false, reason: "unauthenticated", fetchedAt };
  try {
    const page = await apiFetch<AllReviewsPage>(`/api/v1/admin/reviews?${query}`, { token });
    return { available: true, page, fetchedAt };
  } catch {
    return { available: false, reason: "unavailable", fetchedAt };
  }
}

export type AdminOverviewData = {
  queue_total: number;
  high_priority: number;
  approved_today: number;
  approved_delta: number;
  pending_affiliate: number;
  honesty_fund_pool: string;
  honesty_fund_month: string;
  urgent: number;
  /** Queue depth against the policy's SLA targets. `urgent` is the overdue one. */
  approaching_sla?: number;
  overdue_sla?: number;
  breakdown: { label: string; count: number }[];
  affiliate: {
    lifecycle: { label: string; count: number }[];
    settlement: { label: string; count: number }[];
    recognised_amount: string;
    reversed_amount: string;
    unrecovered_amount: string;
    has_data: boolean;
  };
  activity: {
    action: string;
    actor: string | null;
    target_ref: string | null;
    at: string;
  }[];
  /** Sections the backend could not compute for this request. */
  unavailable?: string[];
};

export async function getAdminOverview(): Promise<AdminOverviewData | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<AdminOverviewData>("/api/v1/admin/analytics/overview", { token })
    .catch(() => null);
}

/** One row of the moderation audit log (GET /admin/activity). */
export type ActivityRow = {
  id: string;
  action: string;
  actor: string | null;
  target_type: string | null;
  target_ref: string | null;
  at: string;
  /** The target in words and its admin link (MQA-016: Recent Activity opens it). */
  target_label?: string | null;
  href?: string | null;
  /** A report decision's or price decision's real outcome (MQA-006/008). */
  outcome?: string | null;
};

/** One contributor (GET /admin/reviewers). Carries no email or session data. */
export type ReviewerRow = {
  id: string;
  username: string | null;
  display_name: string | null;
  role: string;
  trust_stage: number;
  reputation_score: string;
  published_reviews: number;
  joined: string;
  /** Business Rules §11: halves the account's vote weight while set. */
  is_under_investigation?: boolean;
};

export async function getActivityLog(
  limit = 60,
): Promise<{ rows: ActivityRow[]; total: number } | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<{ rows: ActivityRow[]; total: number }>(
    `/api/v1/admin/activity?limit=${limit}`, { token },
  ).catch(() => null);
}

export async function getReviewers(
  limit = 60,
): Promise<{ rows: ReviewerRow[]; total: number } | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<{ rows: ReviewerRow[]; total: number }>(
    `/api/v1/admin/reviewers?limit=${limit}`, { token },
  ).catch(() => null);
}

/** One scheduled-maintenance execution (GET /admin/cron-runs). */
export type CronRunRow = {
  task: string;
  source: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  processed: number | null;
  failure: string | null;
  detail: string | null;
};

export type TaskHealth = {
  task: string;
  cadence: string;
  /** healthy | due | overdue | failed | never_run */
  state: string;
  period: string;
  due_at: string;
  last_run: CronRunRow | null;
  last_success_at: string | null;
};

export type SchedulerHealth = {
  tasks: TaskHealth[];
  latest: CronRunRow[];
  recent: CronRunRow[];
  never_run: string[];
};

export async function getSchedulerHealth(): Promise<SchedulerHealth | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<SchedulerHealth>("/api/v1/admin/cron-runs?limit=40", { token })
    .catch(() => null);
}

/** Raw engagement counts for one window (GET /admin/awaiting-affiliate). */
export type MomentumWindow = {
  opens: number;
  upvotes: number;
  downvotes: number;
  comments: number;
  participants: number;
};

export type MomentumFacts = {
  last_24h: MomentumWindow;
  last_7d: MomentumWindow;
  open_reports: number;
};

export type AwaitingAffiliateItem = {
  review: { id: string; title: string; star_rating: number; published_at: string | null };
  product: { id: string; canonical_name: string | null };
  author_display_name: string | null;
  platforms: { platform: string; platform_url: string | null; is_monetizable: boolean; has_active_link: boolean }[];
  suggested_platform: string | null;
  suggested_sub_id: string;
  earnings_approved_at: string | null;
  momentum: MomentumFacts;
};

/**
 * Public reviews whose earnings are approved but which have no active affiliate
 * link yet. Raw facts only — how to rank them is a pending business rule.
 */
export async function getAwaitingAffiliate(): Promise<{ items: AwaitingAffiliateItem[]; total: number } | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<{ items: AwaitingAffiliateItem[]; total: number }>(
    "/api/v1/admin/awaiting-affiliate?limit=50",
    { token },
  ).catch(() => null);
}

/** How payouts leave bluntly right now (GET /admin/payouts/provider). No secrets. */
export type PayoutProviderStatus = {
  provider: string;
  method: "paypal_sandbox" | "paypal_live" | "manual";
  paypal_configured: boolean;
  api_base_is_sandbox: boolean;
  api_submission_available: boolean;
  minimum_cashout: string;
  qa_test_earnings_allowed: boolean;
};

/** One payout as the administrator paying it sees it (GET /admin/payouts). */
export type AdminPayout = {
  id: string;
  payout_id: string | null;
  user_id: string;
  amount: string;
  currency: string;
  status: "scheduled" | "processing" | "paid" | "failed" | "cancelled";
  method: string;
  provider_ref: string | null;
  batch_id: string | null;
  scheduled_for: string;
  paid_at: string | null;
  failure_reason: string | null;
  created_at: string;
  username: string | null;
  payout_account: string | null;
  qa_tester: boolean;
  display_name?: string | null;
  trust_stage?: number | null;
  trust_level_name?: string | null;
};

/** GET /admin/payouts/summary: the Payouts screen's three cards. */
export type PayoutSummary = {
  to_send_total: string;
  to_send_count: number;
  oldest_requested_at: string | null;
  sent_month_total: string;
  sent_month_count: number;
  month_start: string;
  sent_count: number;
  failed_count: number;
  waiting_in_wallets: string;
};

export async function getPayoutSummary(): Promise<PayoutSummary | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<PayoutSummary>("/api/v1/admin/payouts/summary", { token }).catch(() => null);
}

export async function getPayoutProvider(): Promise<PayoutProviderStatus | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<PayoutProviderStatus>("/api/v1/admin/payouts/provider", { token }).catch(() => null);
}

/**
 * The newest 100 payouts in each of `statuses`, newest first. Asked per
 * status so one tab is never crowded out by another (198 waiting requests
 * used to leave the Sent tab showing 17 of its 82).
 */
export async function getAdminPayouts(statuses: string[]): Promise<AdminPayout[] | null> {
  const token = await getSessionToken();
  if (!token) return null;
  try {
    const lists = await Promise.all(
      statuses.map((s) => apiFetch<AdminPayout[]>(`/api/v1/admin/payouts?status=${s}&limit=100`, { token })),
    );
    return lists.flat().sort((x, y) => Date.parse(y.created_at) - Date.parse(x.created_at));
  } catch {
    return null;
  }
}

/** The named QA testers and their published reviews (GET /admin/qa-sandbox/testers). */
export type QaSandboxData = {
  testers: {
    user_id: string;
    username: string | null;
    display_name: string | null;
    payout_account_set: boolean;
    wallet_balance: string;
    test_earned: string;
    reviews: {
      review_id: string;
      title: string | null;
      published_at: string | null;
      credited_amount: string | null;
      credited_at: string | null;
    }[];
  }[];
  default_amount: string;
  max_amount: string;
  can_manage_testers: boolean;
};

export async function getQaSandbox(): Promise<QaSandboxData | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<QaSandboxData>("/api/v1/admin/qa-sandbox/testers", { token }).catch(() => null);
}

/** One row of the Overview's "Needs attention" panel. `count` is null when the
 *  backend could not compute it: render a dash, never a zero. */
export type AttentionItem = { key: string; label: string; count: number | null; detail?: string | null };
export type AttentionGroup = { key: string; label: string; items: AttentionItem[] };

/** GET /admin/analytics/needs-attention (staff). Null when unavailable. */
export async function getNeedsAttention(): Promise<AttentionGroup[] | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<{ groups: AttentionGroup[] }>("/api/v1/admin/analytics/needs-attention", { token })
    .then((r) => r.groups)
    .catch(() => null);
}

export type QueuePreviewItem = {
  review_id: string;
  product_name: string | null;
  image_url: string | null;
  author_name: string | null;
  star_rating: number;
  entered_at: string;
  due_at: string;
  sla_state: string;
};
export type QueuePreviewTab = {
  key: "earn_eligible" | "flagged" | "first_review" | "new_product";
  label: string;
  count: number;
  items: QueuePreviewItem[];
};

/** GET /admin/analytics/queue-preview: the Overview's Review queue card. */
export async function getQueuePreview(): Promise<QueuePreviewTab[] | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<{ tabs: QueuePreviewTab[] }>("/api/v1/admin/analytics/queue-preview", { token })
    .then((r) => r.tabs)
    .catch(() => null);
}

export type EarningsRange = "1M" | "6M" | "1Y";
export type AffiliateEarnings = {
  range: EarningsRange;
  verified: string;
  previous_verified: string;
  delta_pct: number | null;
  returned: string;
  returned_pct: number | null;
  absorbed: string;
  pending_orders: number;
  pending: { platform: string; orders: number; amount: string }[];
  buckets: { label: string; start: string; verified: string; returned: string }[];
};

/** GET /admin/analytics/affiliate-earnings: the Overview's money card. */
export async function getAffiliateEarnings(range: EarningsRange): Promise<AffiliateEarnings | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<AffiliateEarnings>(
    `/api/v1/admin/analytics/affiliate-earnings?range=${range}`, { token })
    .catch(() => null);
}

/** The Overview's three cards, each failing on its own, read at `fetchedAt`
 *  (epoch ms) so queue ages agree between the server and client renders. */
export async function getOverviewPanels(range: EarningsRange) {
  const fetchedAt = Date.now();
  const [preview, attention, earnings] = await Promise.all([
    getQueuePreview(),
    getNeedsAttention(),
    getAffiliateEarnings(range),
  ]);
  return { preview, attention, earnings, fetchedAt };
}

export type PersonRef = {
  id: string;
  name: string;
  username: string | null;
  trust_stage: number;
  trust_level_name: string | null;
};

/** GET /admin/people/{id}: one member, for an investigation (staff). */
export type PersonInvestigation = {
  person: {
    id: string;
    user_ref: string | null;
    name: string;
    username: string | null;
    role: string;
    trust_stage: number;
    trust_level_name: string | null;
    /** The EFFECTIVE Honesty Score (the override when set, else computed). */
    reputation_score: string;
    joined: string;
    status: "active" | "investigating" | "suspended";
    /** 0095 trust score override (RESEARCH 769c038). */
    computed_score?: string | null;
    score_override?: string | null;
    is_score_overridden?: boolean;
    score_override_reason?: string | null;
    score_overridden_at?: string | null;
    avatar_url?: string | null;
  };
  range: "1M" | "6M" | "1Y";
  votes_total: number;
  votes_up: number;
  votes_down: number;
  daily: { day: string; up: number; down: number }[];
  spike: { day: string; up: number; down: number } | null;
  interactions: {
    person: PersonRef;
    up: number;
    down: number;
    comments: number;
    up_back: number;
    same_day: number;
    share_pct: number;
    reciprocity_pct: number;
    same_network: boolean;
    last_at: string | null;
  }[];
  interactions_total: number;
  top3_share_pct: number;
  activity: {
    kind: string;
    at: string;
    title: string;
    subtitle: string | null;
    other: PersonRef | null;
    href: string | null;
  }[];
  activity_total: number;
  reports: {
    id: string;
    direction: "filed" | "received";
    reason: string | null;
    target_type: string | null;
    target_label: string;
    other: PersonRef | null;
    status: string;
    at: string;
    href: string | null;
    notes: string | null;
  }[];
  moderation: {
    id: string;
    action: string;
    target_type: string | null;
    target_label: string;
    moderator: string | null;
    reason: string | null;
    notes: string | null;
    at: string;
  }[];
  linked: { person: PersonRef; basis: "shared_network" | "shared_payout_account"; detail: string }[];
  signals: {
    reports_against: number;
    reports_against_upheld: number;
    reports_filed: number;
    reports_filed_upheld: number;
    moderation: number;
    takedowns: number;
    earned: string | null;
    pending: string | null;
    linked_accounts: number;
  };
};

export async function getPersonInvestigation(
  id: string,
  range: "1M" | "6M" | "1Y",
): Promise<{ data: PersonInvestigation | null; status: number; fetchedAt: number }> {
  const fetchedAt = Date.now();
  const token = await getSessionToken();
  if (!token) return { data: null, status: 401, fetchedAt };
  try {
    const data = await apiFetch<PersonInvestigation>(
      `/api/v1/admin/people/${encodeURIComponent(id)}?range=${range}`, { token });
    return { data, status: 200, fetchedAt };
  } catch (error) {
    const status = (error as { status?: number })?.status ?? 503;
    return { data: null, status, fetchedAt };
  }
}

export type PeopleStatus = "all" | "active" | "investigating" | "suspended";
export type PeopleRow = ReviewerRow & {
  user_ref?: string | null;
  trust_level_name?: string | null;
  is_suspended?: boolean;
  /** 0095: the algorithm's score; `reputation_score` is the EFFECTIVE one (override if set). */
  computed_score?: string | null;
  score_override?: string | null;
  is_score_overridden?: boolean;
  /** The member's own uploaded photo; null when there is none. */
  avatar_url?: string | null;
};
export type PeoplePage = {
  rows: PeopleRow[];
  total: number;
  counts: { all: number; active: number; investigating: number; suspended: number } | null;
  /** Per trust stage ("0".."5") under the scope, search and status: the Filter menu's chips. */
  stages?: Record<string, number> | null;
};
export type PeopleSort = "published" | "newest" | "oldest";

/** The People list: members only (no staff, no claimed sellers), by status. */
export async function getPeople(params: {
  status: PeopleStatus;
  q: string;
  limit: number;
  offset: number;
  sort?: PeopleSort;
  stage?: number | null;
}): Promise<PeoplePage | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const query = new URLSearchParams({
    scope: "members",
    status: params.status,
    limit: String(params.limit),
    offset: String(params.offset),
  });
  if (params.q) query.set("q", params.q);
  if (params.sort && params.sort !== "published") query.set("sort", params.sort);
  if (params.stage !== undefined && params.stage !== null) query.set("stage", String(params.stage));
  return apiFetch<PeoplePage>(`/api/v1/admin/reviewers?${query}`, { token }).catch(() => null);
}

// Reports: the financial report (Figma Screen/Admin/Reports 8028:12886) --------

export type FinancialShare = { key: "bluntly" | "reviewers" | "honesty_fund"; label: string; amount: string; rate: number | null };
export type FinancialReport = {
  meta: { title: string; generated_at: string; notes: string[]; period: { kind: string; label: string; start: string; end: string } };
  span: string;
  span_short: string;
  kpis: { net_commission: string; money_in: string; money_out: string; still_owed: string };
  revenue: {
    earned: string;
    reversed: string;
    absorbed: string;
    net: string;
    shares: FinancialShare[];
    by_marketplace: { marketplace: string; orders: number; commissions: number; earned: string }[];
    orders_total: number;
    commissions_total: number;
  };
  money_in: {
    rows: { marketplace: string; cycle_month: string; expected: string; received: string | null; received_on: string | null; shortfall: string | null; status: "cleared" | "clearing" }[];
    received_total: string;
    shortfall_total: string;
  };
  money_out: {
    sent: { count: number; amount: string };
    to_send: { count: number; amount: string };
    failed: { count: number; amount: string };
    cancelled: { count: number; amount: string };
    honesty_fund: { cycle_month: string; credited_on: string; count: number; amount: string }[];
    paid_out_total: string;
    /** PayPal sandbox payouts: no real money moved, so not in paid_out_total. */
    sandbox_excluded?: { count: number; amount: string } | null;
  };
  liabilities: {
    as_of: string;
    cleared_in_wallets: string;
    payouts_to_send: string;
    still_clearing: string;
    unattributed: string;
    unattributed_count: number;
  };
};

export type FinancialReportEntry = {
  id: string;
  title: string;
  period_label: string;
  period_kind: string;
  span_short: string;
  sections: string[];
  pages: number;
  generated_at: string;
  generated_by: string | null;
  download_path: string;
};

/** The Reports screen's cards for one month ("2026-09"). Null when unavailable. */
export async function getFinancialReport(month: string): Promise<FinancialReport | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const [year, m] = month.split("-");
  return apiFetch<FinancialReport>(`/api/v1/admin/reports/financial?month=${Number(m)}&year=${Number(year)}`, { token }).catch(
    () => null,
  );
}

export async function getFinancialReportHistory(): Promise<FinancialReportEntry[] | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<FinancialReportEntry[]>("/api/v1/admin/reports/financial/history", { token }).catch(() => null);
}

type GenSchemas = import("@/lib/api-types").components["schemas"];
/** Figma Products Catalogue (7967:11173), generated from the API. */
export type CatalogueResult = GenSchemas["CatalogueOut"];
export type CatalogueRow = GenSchemas["CatalogueRowOut"];
export type ProductQueueResult = GenSchemas["ProductQueueOut"];

/** GET /admin/products/catalogue — named products, aliases and price trend. */
export async function getProductCatalogue(params: {
  q?: string;
  category?: string;
  sort?: string;
  limit: number;
  offset: number;
}): Promise<CatalogueResult | null> {
  const token = await getSessionToken();
  if (!token) return null;
  const qs = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) });
  if (params.q) qs.set("q", params.q);
  if (params.category) qs.set("category", params.category);
  if (params.sort) qs.set("sort", params.sort);
  return apiFetch<CatalogueResult>(`/api/v1/admin/products/catalogue?${qs}`, { token }).catch(() => null);
}

/** GET /admin/products/queue — submissions waiting to be named or merged. */
export async function getProductQueue(sort: "oldest" | "newest" = "oldest"): Promise<ProductQueueResult | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<ProductQueueResult>(`/api/v1/admin/products/queue?sort=${sort}`, { token }).catch(() => null);
}

/** The Honesty Fund tab (GET /admin/payouts/honesty-fund; Figma 8024:13286). */
export type FundCycles = import("@/lib/api-types").components["schemas"]["FundCyclesOut"];
export type FundCycle = import("@/lib/api-types").components["schemas"]["FundCycleOut"];

export async function getHonestyFundCycles(): Promise<FundCycles | null> {
  const token = await getSessionToken();
  if (!token) return null;
  return apiFetch<FundCycles>("/api/v1/admin/payouts/honesty-fund", { token }).catch(() => null);
}

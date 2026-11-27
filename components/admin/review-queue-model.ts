/**
 * The Review Queue's presentation logic, kept out of the screen component.
 *
 * Same arrangement as `components/analytics/globe-model.ts`: the screen is a
 * client component the frontend test runner cannot render, so everything that
 * can be got wrong — which row is high priority, which number a cell shows,
 * which cells have no number to show — lives here as plain functions with
 * structural input types and no imports.
 *
 * The rule this module exists to enforce: a moderation console must never
 * print a number it cannot source. Every metric the console draws is either
 * read from the queue card the API actually returned, or returned as an
 * unavailable `Stat` carrying the reason. There is no third case, and in
 * particular there is no "0" standing in for "we do not measure this" — on a
 * fraud-review screen those two read identically and mean opposite things.
 *
 * Priority obeys a second rule, added with the server-owned contract: this
 * module RENDERS the assessment and never computes one. Ordering, filtering
 * and banding are the policy's, decided over the whole backlog before the page
 * was cut. A helper here that re-sorted or re-filtered a page would be making
 * a whole-queue claim from the fifty rows it happens to hold.
 *
 * The design frames this screen was built to (5017:1738 / 5017:3758 / 6532:278)
 * were deleted from the Figma file on 2026-09-09 and replaced by a single
 * 1280x1943 "Admin Page - Review Queue" (6922:837). The layout below is still
 * the old frame's; the re-layout is its own piece of work.
 */

export type Priority = "High" | "Normal" | "Low";

/** The policy's own vocabulary, as the API serializes it. */
export type Band = "high" | "normal" | "low";
export type Lane = "escalated" | "reported" | "integrity" | "routine" | "quality_audit";
export type Sla = "on_track" | "approaching" | "overdue";

const BANDS: Band[] = ["high", "normal", "low"];
const LANES: Lane[] = ["escalated", "reported", "integrity", "routine", "quality_audit"];
const SLAS: Sla[] = ["on_track", "approaching", "overdue"];

/**
 * One reason a review sits where it does, written by the policy.
 *
 * `explanation` is prose the server composed; nothing here translates a code
 * into wording of its own. A code this build has never seen therefore still
 * renders correctly the day the server starts sending it, which is the point —
 * a console that silently drops unfamiliar reasons hides exactly the new signal
 * an administrator most needs to see.
 */
export type PriorityFactor = {
  code: string;
  observed: boolean | number | string;
  contribution: number;
  explanation: string;
};

/** The server's assessment of one card. Rendered, never recomputed. */
export type QueuePriority = {
  policy_version: string;
  lane: string;
  score: number;
  band: string;
  sla_state: string;
  due_at: string;
  factors?: PriorityFactor[];
  /** Business Rules §12: "user_reported" and/or "system_detected". */
  origins?: string[];
};

/** The canonical server-side filters, exactly as the URL carries them. */
export type QueueFilters = {
  band: Band | "";
  lane: Lane | "";
  sla: Sla | "";
  factor: string;
  q: string;
  /** Admin priority tier (dev note 2026-09-26); "" is every tier. */
  tier: PriorityTier | "";
  /** Queue order. Priority tier is the triage default; "policy" is the older
   *  lane/SLA order (escalation order on the Report tab); "oldest" is arrival. */
  sort: QueueSort;
  /** The Report tab's own order. It defaults to escalation, not tier:
   *  Business Rules §12 has safety and personal-information reports escalate
   *  "near-immediately regardless of anything else", and the tiers do not
   *  weigh report urgency. The tier is still shown, filterable and sortable. */
  rsort: ReportSort;
  /** The Report tab's status dropdown (Figma "Open"): open, resolved, or both. */
  rstatus?: ReportStatus;
  /** The Report tab's page (?rpage=), 1-based; REPORT_PAGE_SIZE rows a page. */
  rpage?: number;
  /** MQA-015: the reviews waiting for a decision (the work), or the ones a
   *  moderator took down - decided, kept one switch away with Restore. */
  view?: QueueView;
  limit: number;
  offset: number;
};

/** The API's totals for one Report status: every report, and the distinct
 *  items they are on (MQA-045). Null when the API did not answer. */
export type ReportTotals = { reports: number | null; items: number | null };

const STATUS_WORD: Record<ReportStatus, string> = {
  open: "open",
  escalated: "escalated",
  resolved: "resolved",
  all: "",
};

/** "6 open reports on 4 items" — both figures under their own names (MQA-045). */
export function reportTotalsLine(totals: ReportTotals | null, status: ReportStatus = "open"): string | null {
  if (!totals || totals.reports === null) return null;
  const word = STATUS_WORD[status];
  const reports = `${totals.reports.toLocaleString("en-PH")} ${word ? `${word} ` : ""}report${totals.reports === 1 ? "" : "s"}`;
  if (totals.items === null || totals.reports === 0) return reports;
  return `${reports} on ${totals.items.toLocaleString("en-PH")} item${totals.items === 1 ? "" : "s"}`;
}

/** Rows on one page of the Report tab. The Reviews tab's report counts read
 *  this page too (`reportCountFor`), so it stays as large as it was. */
export const REPORT_PAGE_SIZE = 50;

export type QueueView = "waiting" | "taken_down";
export const QUEUE_VIEWS: QueueView[] = ["waiting", "taken_down"];
export const QUEUE_VIEW_LABELS: Record<QueueView, string> = {
  waiting: "Waiting for a decision",
  taken_down: "Taken down",
};

export type ReportStatus = "open" | "escalated" | "resolved" | "all";
export const REPORT_STATUSES: ReportStatus[] = ["open", "escalated", "resolved", "all"];

/* ------------------------------------------------------ priority tiers */

/**
 * The admin priority tiers (dev note "Admin Dashboard: Priority Tier System",
 * 2026-09-26). A triage label on an item ALREADY in a queue: it sorts,
 * filters and explains, and never decides whether anything is queued. The
 * server computes it (`priority_tiers.py`); this module only names it.
 */
export type PriorityTier = "highest" | "high" | "neutral" | "low" | "lowest";
export const PRIORITY_TIERS: PriorityTier[] = ["highest", "high", "neutral", "low", "lowest"];
export type QueueSort = "tier" | "policy" | "oldest";
const SORTS: QueueSort[] = ["tier", "policy", "oldest"];
export const DEFAULT_SORT: QueueSort = "tier";
export type ReportSort = "escalation" | "tier" | "newest" | "oldest";
const REPORT_SORTS: ReportSort[] = ["escalation", "tier", "newest", "oldest"];

/** MQA-001: a report filed within this long reads "New" in the Reports list. */
export const NEW_REPORT_MS = 24 * 60 * 60 * 1000;

export function isNewReport(createdAt: string, now: number): boolean {
  const age = now - new Date(createdAt).getTime();
  return age >= 0 && age < NEW_REPORT_MS;
}
export const DEFAULT_REPORT_SORT: ReportSort = "escalation";

export const TIER_LABELS: Record<PriorityTier, string> = {
  highest: "Highest",
  high: "High",
  neutral: "Neutral",
  low: "Low",
  lowest: "Lowest",
};

export type TierReason = { code: string; label: string; detail: string };
export type Triage = {
  tier: PriorityTier;
  base_tier: PriorityTier;
  aged: boolean;
  aged_at: string | null;
  clock_started_at: string;
  routine_spot_check: boolean;
  reasons: TierReason[];
};

/** "Highest", or "Lowest · routine spot-check" — the badge text. */
export function tierLabel(triage: Pick<Triage, "tier" | "routine_spot_check">): string {
  const base = TIER_LABELS[triage.tier] ?? titleCase(triage.tier);
  return triage.routine_spot_check ? `${base} · routine spot-check` : base;
}

/**
 * Why, in one line: "Wilson near threshold + 2 fraud reports". Built from the
 * server's own reason labels, so a reason this build has never seen still
 * reads correctly. Never a bare number.
 */
export function tierSummary(triage: Pick<Triage, "reasons">): string {
  return triage.reasons.map((r) => r.label).join(" + ");
}

export const DEFAULT_LIMIT = 50;

/** The page sizes the console offers, and the only ones a URL may ask for. */
export const QUEUE_LIMITS = [10, 25, 50, 100];

/** A queue card, narrowed to the fields this module reads. */
export type QueueCard = {
  review: {
    id: string;
    review_id: string | null;
    title: string;
    verification_status: string;
    created_at: string;
    wilson_score: string;
    helpful_votes: number;
    unhelpful_votes: number;
  };
  product: { canonical_name: string | null };
  author: {
    display_name: string | null;
    reputation_score: string;
    /** Optional: a card from an API older than 2026-09-16 does not carry it. */
    verified_review_count?: number;
  } | null;
  /** The review's comment total, removed ones excluded. Optional for the same reason. */
  comment_count?: number;
  signals: {
    velocity: boolean;
    collusion: boolean;
    duplicate_content: boolean;
    author_account_age_days: number;
    author_review_count: number;
  };
  /** FR-8 layers 2 and 3. Read through `externalCheckLabel`, never directly. */
  integrity?: { plagiarism_status?: string; reverse_image_status?: string };
  /** The canonical assessment (design section 5). A sibling of `signals`. */
  priority: QueuePriority;
  /**
   * Which review timestamp stood in for the queue-entry time the schema does
   * not have yet: `created_at` for an initial pending review, `updated_at` for
   * a monetized-but-edited one. The UI must not present either as precise
   * lifecycle timing, which is what `QUEUE_TIME_APPROXIMATE` is for.
   */
  queue_time_basis?: string;
  /** Admin priority tier; absent from a server older than this build. */
  triage?: Triage | null;
};

/** A filed report, narrowed to the fields this module reads. */
export type ReportRow = {
  report: { target_ref: string | null };
  target: { id: string } | null;
  target_report_count: number;
};

/**
 * One cell of the detail panel: a value the API supplied, or the reason it
 * could not. Callers render the reason; they never invent a value.
 */
export type Stat =
  | { label: string; available: true; value: string }
  | { label: string; available: false; value: null; reason: string };

const available = (label: string, value: string): Stat => ({
  label,
  available: true,
  value,
});

const unavailable = (label: string, reason: string): Stat => ({
  label,
  available: false,
  value: null,
  reason,
});

/* -------------------------------------------------------------- priority */

/**
 * The band the server assessed, as a label.
 *
 * This used to derive a band here from the advisory fraud signals: High if any
 * signal fired, else Normal if the receipt was unverified, else Low. That was a
 * moderation policy written in the browser, and it disagreed with both the
 * Overview's headline and the order the queue itself arrived in. The policy now
 * lives in `moderation_priority.py`, is applied to the whole backlog before the
 * page is cut, and this function's entire job is to title-case its answer.
 *
 * An unfamiliar band — a server ahead of this deploy — is title-cased and shown
 * as-is. Substituting a band we recognise would misreport the queue; showing
 * nothing would hide a row's standing altogether.
 */
export function priorityOf(item: QueueCard): string {
  return titleCase(item.priority?.band ?? "");
}

function titleCase(value: string): string {
  if (!value) return "";
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Reader-facing labels for the backend `ModerationReason` enum. Here rather
 * than in lib/moderation.ts, which is server-only, so the client queue screen
 * can name a report's reason too.
 */
export const REPORT_REASON_LABELS: Record<string, string> = {
  safety_threat: "Threat or safety risk",
  personal_information: "Personal information",
  fake_proof: "Fake photo or receipt",
  plagiarized: "Copied from elsewhere",
  spam: "Spam",
  harassment: "Harassment or abuse",
  conflict_of_interest: "Undisclosed conflict of interest",
  seller_posing_as_buyer: "Seller posing as a buyer",
  counterfeit: "Counterfeit product",
  other: "Something else",
};

/**
 * Where a card's evidence came from (Business Rules §12): a person's report,
 * an automated check, or both. Every card says — an administrator must never have
 * to guess whether a human or a detector raised it. A card with neither is
 * routine intake, and says that instead of nothing.
 */
export function originLabel(origins: readonly string[] | undefined): string {
  const set = new Set(origins ?? []);
  const user = set.has("user_reported");
  const system = set.has("system_detected");
  if (user && system) return "User report + system detected";
  if (user) return "User report";
  if (system) return "System detected";
  return "Routine intake";
}

/** The lane and SLA state as labels, on the same terms as the band. */
export function laneLabel(item: QueueCard): string {
  return titleCase(item.priority?.lane ?? "");
}

/**
 * The reasons behind the score, in the policy's own words.
 *
 * A missing explanation falls back to the code rather than rendering an empty
 * row: a factor that contributed to a review's placement must be legible even
 * when the wording is missing.
 */
export function factorLines(item: QueueCard): PriorityFactor[] {
  const factors = item.priority?.factors ?? [];
  return factors.map((factor) => ({
    ...factor,
    explanation: factor.explanation?.trim() ? factor.explanation : factor.code,
  }));
}

/* ------------------------------------------------------------------ time */

const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "3s ago" / "5m ago" / "2h ago" / "4d ago" / "6mo ago" / "2y ago". */
export function relativeAge(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (seconds < MINUTE) return `${Math.floor(seconds)}s ago`;
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m ago`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h ago`;
  return accountAgeLabel(Math.floor(seconds / DAY));
}

/**
 * The same wording from a whole-day count, which is what
 * `signals.author_account_age_days` is — an integer, not a timestamp.
 */
export function accountAgeLabel(days: number): string {
  const whole = Math.max(0, Math.floor(days));
  if (whole < 30) return `${whole}d ago`;
  if (whole < 365) return `${Math.floor(whole / 30)}mo ago`;
  return `${Math.floor(whole / 365)}y ago`;
}

/* ------------------------------------------------------------ table rows */

/*
 * `queueRows` and `paginate` used to live here. Both are gone, and their
 * absence is the contract.
 *
 * `queueRows` filtered by a band this module derived and re-sorted by
 * `created_at`. `paginate` then cut that re-ordered list. Every one of those is
 * a claim about the WHOLE backlog, and the browser holds one page of it — so
 * filtering to High hid the High rows that were on page two, and sorting by
 * date overruled a policy order that had already weighed lane, SLA and score.
 *
 * The server does all three now, over every candidate, before it cuts the page
 * (`referral_service.get_prioritized_queue`). The screen renders `items` in the
 * order they arrived and changes the URL to ask a different question.
 */

/* --------------------------------------------------------- SLA and timing */

/**
 * Why every age on this screen is an approximation, stated once.
 *
 * There is no queue-entry column yet. Priority is evaluated against the
 * review's `created_at` (or `updated_at`, for a monetized review edited since
 * its link was attached), which is when the review was WRITTEN, not when it
 * reached the queue. For an initial submission those are the same moment; for
 * anything requeued they are not. Saying so is the difference between an
 * approximate age and a wrong one.
 */
export const QUEUE_TIME_APPROXIMATE =
  "Queue age is approximate: it is measured from the review's created_at " +
  "(updated_at for an edited one), because no queue-entry timestamp is " +
  "recorded yet. Treat it as an age, not as lifecycle timing.";

/** Which timestamp this card's age came from, in words. */
export function queueTimeBasisLabel(item: QueueCard): string {
  return item.queue_time_basis === "review_updated_at"
    ? "measured from the last edit"
    : "measured from submission";
}

/**
 * How long this card has been waiting, on its own declared basis.
 *
 * A DURATION ("3h"), not a relative timestamp ("3h ago"). The panel reads
 * "Waiting 3h", and "Waiting 3h ago" is not a thing a queue can say.
 */
export function queueAgeLabel(item: QueueCard, now: number = Date.now()): string {
  const started = Date.parse(item.review.created_at);
  if (Number.isNaN(started)) return "";
  return durationLabel(Math.max(0, (now - started) / 1000));
}

/**
 * Where this card stands against its lane's SLA target.
 *
 * The state is the server's; only the wording is ours. `due_at` is what the
 * policy computed from the lane target, so the remaining or elapsed time is
 * arithmetic on a served value rather than a second SLA implementation.
 */
export function slaStat(
  item: QueueCard,
  now: number = Date.now(),
): { state: string; label: string; available: boolean; value: string } {
  const state = item.priority?.sla_state ?? "";
  const due = Date.parse(item.priority?.due_at ?? "");

  if (!state || Number.isNaN(due)) {
    return { state, label: "SLA", available: false, value: "" };
  }

  const deltaSeconds = Math.abs(now - due) / 1000;
  const span = durationLabel(deltaSeconds);
  const value =
    state === "overdue"
      ? `Overdue by ${span}`
      : state === "approaching"
        ? `Due in ${span}`
        : `On track — ${span} left`;

  return { state, label: titleCase(state), available: true, value };
}

/** "3h" / "47m" / "2d" — a span, not a point in time. */
function durationLabel(seconds: number): string {
  if (seconds < MINUTE) return `${Math.floor(seconds)}s`;
  if (seconds < HOUR) return `${Math.floor(seconds / MINUTE)}m`;
  if (seconds < DAY) return `${Math.floor(seconds / HOUR)}h`;
  return `${Math.floor(seconds / DAY)}d`;
}

/* ----------------------------------------------------------- URL filters */

/**
 * Read the canonical filters out of a URL.
 *
 * Anything the policy does not define is dropped rather than forwarded: a
 * hand-edited `?band=critical` narrows to "no band filter" instead of putting a
 * 422 on the administrator's screen, and nothing unvalidated is ever passed through
 * to the API.
 */
export function parseQueueFilters(params: URLSearchParams): QueueFilters {
  const oneOf = <T extends string>(allowed: T[], value: string | null): T | "" =>
    allowed.includes((value ?? "") as T) ? ((value ?? "") as T) : "";

  const limit = Number.parseInt(params.get("limit") ?? "", 10);
  const offset = Number.parseInt(params.get("offset") ?? "", 10);
  const rpage = Number.parseInt(params.get("rpage") ?? "", 10);

  return {
    band: oneOf(BANDS, params.get("band")),
    lane: oneOf(LANES, params.get("lane")),
    sla: oneOf(SLAS, params.get("sla")),
    factor: (params.get("factor") ?? "").trim(),
    q: (params.get("q") ?? "").trim(),
    tier: oneOf(PRIORITY_TIERS, params.get("tier")),
    sort: oneOf(SORTS, params.get("sort")) || DEFAULT_SORT,
    rsort: oneOf(REPORT_SORTS, params.get("rsort")) || DEFAULT_REPORT_SORT,
    rstatus: oneOf(REPORT_STATUSES, params.get("rstatus")) || "open",
    rpage: Number.isFinite(rpage) && rpage > 1 ? rpage : 1,
    view: oneOf(QUEUE_VIEWS, params.get("view")) || "waiting",
    limit: QUEUE_LIMITS.includes(limit) ? limit : DEFAULT_LIMIT,
    offset: Number.isFinite(offset) && offset > 0 ? offset : 0,
  };
}

/** The query string for the API call. Only what is actually set is sent. */
export function queueApiQuery(filters: QueueFilters): string {
  const params = new URLSearchParams();
  if (filters.band) params.set("band", filters.band);
  if (filters.lane) params.set("lane", filters.lane);
  if (filters.sla) params.set("sla", filters.sla);
  if (filters.factor) params.set("factor", filters.factor);
  if (filters.q) params.set("q", filters.q);
  if (filters.tier) params.set("tier", filters.tier);
  params.set("sort", filters.sort || DEFAULT_SORT);
  if (filters.view === "taken_down") params.set("view", "taken_down");
  params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  return params.toString();
}

/**
 * The Report tab's API query: the tier filter, and the tab's own order
 * (escalation by default — see `QueueFilters.rsort`).
 */
export function reportsApiQuery(filters: Pick<QueueFilters, "tier" | "rsort" | "rstatus" | "rpage">): string {
  const params = new URLSearchParams({ limit: String(REPORT_PAGE_SIZE) });
  if (filters.tier) params.set("tier", filters.tier);
  params.set("sort", filters.rsort || DEFAULT_REPORT_SORT);
  if (filters.rstatus && filters.rstatus !== "open") params.set("status", filters.rstatus);
  const page = filters.rpage && filters.rpage > 1 ? Math.floor(filters.rpage) : 1;
  if (page > 1) params.set("offset", String((page - 1) * REPORT_PAGE_SIZE));
  return params.toString();
}

/**
 * A link to the same queue with one thing changed.
 *
 * Changing a filter resets the page, because an offset counted into one
 * filtered list means nothing in another; passing `offset` explicitly is how
 * pagination keeps it.
 */
export function queueHref(
  filters: QueueFilters,
  changes: Partial<QueueFilters> & { tab?: Tab } = {},
): string {
  const next: QueueFilters = {
    ...filters,
    ...changes,
    offset: "offset" in changes ? (changes.offset ?? 0) : 0,
  };
  const params = new URLSearchParams();
  if (changes.tab) params.set("tab", changes.tab);
  if (next.band) params.set("band", next.band);
  if (next.lane) params.set("lane", next.lane);
  if (next.sla) params.set("sla", next.sla);
  if (next.factor) params.set("factor", next.factor);
  if (next.tier) params.set("tier", next.tier);
  if (next.sort && next.sort !== DEFAULT_SORT) params.set("sort", next.sort);
  if (next.rsort && next.rsort !== DEFAULT_REPORT_SORT) params.set("rsort", next.rsort);
  if (next.rstatus && next.rstatus !== "open") params.set("rstatus", next.rstatus);
  if (next.view === "taken_down") params.set("view", "taken_down");
  if (next.q) params.set("q", next.q);
  if (next.limit !== DEFAULT_LIMIT) params.set("limit", String(next.limit));
  if (next.offset) params.set("offset", String(next.offset));
  const query = params.toString();
  return query ? `${QUEUE_ROUTE}?${query}` : QUEUE_ROUTE;
}

/**
 * The ID column.
 *
 * The frame draws a short sequential "B-270". No such counter exists: the
 * backend's human reference is `review_id`, minted as `rev_<10 hex>`
 * (`review_service.py`). The real reference is what an administrator can paste into
 * a search or a report, so it wins over the frame's placeholder shape.
 */
export function reviewIdLabel(review: { review_id: string | null; id: string }): string {
  return review.review_id ?? review.id.slice(0, 8);
}

/**
 * How many reports were filed against this review, or `null` when this console
 * cannot tell.
 *
 * Reports are already fetched for the Report tab, so this costs no request.
 * `target_ref` holds either the UUID or the human reference depending on how
 * the report was filed — `admin_overview_service._reported_review_ids` unions
 * both forms for exactly this reason, and matching only one would under-count.
 * When a row matches, `target_report_count` is the backend's own total for
 * that target, so it is exact and is returned as-is.
 *
 * NULL, NEVER ZERO, when nothing matches. The feed this searches is the 50
 * most recent reports, and `getReports` returns an empty array when the fetch
 * FAILS as well as when there is genuinely nothing. So "no matching row" has
 * three possible causes — no reports exist, this review's reports fell outside
 * the newest 50, or the request errored — and only the first would justify
 * printing "0". Printing it anyway tells an administrator this review is unreported
 * when it may be the most-reported one on the site.
 */
export function reportCountFor(item: QueueCard, reports: ReportRow[]): number | null {
  const ids = new Set([item.review.id, item.review.review_id].filter(Boolean));
  for (const row of reports) {
    if (
      (row.report.target_ref && ids.has(row.report.target_ref)) ||
      (row.target && ids.has(row.target.id))
    ) {
      return row.target_report_count;
    }
  }
  return null;
}

/* ------------------------------------------------------------- engagement */

const NO_VIEW_SOURCE =
  "Views are counted per hour in review_view_buckets, and the administrator queue " +
  "may not read them: the telemetry-isolation gate requires every module that " +
  "feeds a moderation decision to stay independent of reading telemetry " +
  "(backend test_telemetry_isolation). The reviewer's own dashboard shows " +
  "them. This is a deliberate boundary, not a missing join.";

const NO_SHARE_SOURCE =
  "Nothing in this build counts shares: there is no share column, share " +
  "event table or share endpoint anywhere in the backend.";

const NO_REPORT_EVIDENCE =
  "This console reads only the 50 most recent reports, and that partial feed " +
  "names no report against this review. A failed reports request looks " +
  "identical to an empty one, so absence here is not evidence of zero.";

const NO_COMMENT_COUNT_ON_CARD =
  "This queue card predates the comment count being served; reload the queue.";

const NO_TOP_COMMENT =
  "Comments are returned oldest-first with no ranking parameter, so there is " +
  "no server-side notion of a top comment to show.";

/**
 * The engagement panel.
 *
 * Upvotes, downvotes and the report count are real. Views, shares, comments
 * and the top comment have no source that reaches this screen, and say so.
 */
export function engagementFor(item: QueueCard, reports: ReportRow[]) {
  const reportCount = reportCountFor(item, reports);

  return {
    upvotes: item.review.helpful_votes,
    downvotes: item.review.unhelpful_votes,
    views: unavailable("Views", NO_VIEW_SOURCE),
    shares: unavailable("Shares", NO_SHARE_SOURCE),
    reports: reportCount === null
      ? unavailable("Reports", NO_REPORT_EVIDENCE)
      : available("Reports", String(reportCount)),
    // Served on the card since 2026-09-16. A card from an older API has no
    // field at all, which is why this is `?? null` and not `?? 0`: absent and
    // "no comments" are different things and only one of them is a number.
    comments:
      item.comment_count === undefined || item.comment_count === null
        ? unavailable("Comments", NO_COMMENT_COUNT_ON_CARD)
        : available("Comments", String(item.comment_count)),
    topComment: unavailable("Top comment", NO_TOP_COMMENT),
  };
}

/* ---------------------------------------------------------- author card */

const NO_VERIFIED_COUNT =
  "This queue card predates the verified-review count being served; reload " +
  "the queue. signals.author_review_count includes unverified work and " +
  "cannot stand in for it.";

/**
 * The four stats the frame draws beside the author's name.
 *
 * All four come off the queue card now. Verified Reviews was the odd one out
 * until 2026-09-16 — the column on `users` was always real and `QueueAuthor`
 * simply did not carry it — so the console drew it as unavailable rather than
 * borrowing the total, which counts unverified work too.
 */
export function authorTrustStats(item: QueueCard): Stat[] {
  // reputation_score is a Decimal serialized as a string. An empty or
  // malformed one must not become "NaN" on screen next to a reviewer's name.
  const score = item.author ? Number(item.author.reputation_score) : Number.NaN;

  return [
    available("Age", accountAgeLabel(item.signals.author_account_age_days)),
    Number.isFinite(score) && item.author?.reputation_score !== ""
      ? available("Trust Score", String(Math.round(score)))
      : unavailable(
          "Trust Score",
          item.author
            ? "This author's reputation score did not parse as a number."
            : "This review's author account no longer exists.",
        ),
    available("Total Reviews", String(item.signals.author_review_count)),
    item.author?.verified_review_count === undefined
      ? unavailable("Verified Reviews", NO_VERIFIED_COUNT)
      : available("Verified Reviews", String(item.author.verified_review_count)),
  ];
}

/* --------------------------------------------------- panels with no source */

/**
 * The per-review Voting Distribution globe and the flagged-voter cards.
 *
 * `review_first_vote_geo_buckets` does store per-review vote geography, but it
 * is write-only: no route reads it, and `test_telemetry_isolation.py` floods
 * that exact table while asserting the administrator queue card is unchanged. So
 * there is nothing to render and, until a reviewed read path exists, nothing
 * that may be rendered. Flagged-voter counts have no source at all.
 */
export const VOTING_GEOGRAPHY_UNAVAILABLE =
  "Per-review vote geography is stored in review_first_vote_geo_buckets but " +
  "no endpoint serves it, and the telemetry-isolation gate requires the " +
  "administrator queue to stay independent of it. Nothing here is derived from " +
  "reading telemetry.";

export const FLAGGED_VOTERS_UNAVAILABLE =
  "No flagged-voter aggregate exists in this build: votes carry no geography, " +
  "no trust bucketing and no fraud classification.";

export const REVERSE_IMAGE_SEARCH_UNAVAILABLE =
  "No reverse image search provider is configured, so no web search runs. " +
  "Inside bluntly, every review photo is compared with every other review's " +
  "photo, and copied text is checked on every submission (QA 2026-09-29).";

/**
 * One external integrity check (plagiarism or reverse image) as the card shows
 * it. Only "clear" and "flagged" mean a provider actually ran; anything else —
 * "not_configured", a missing field, a status this build does not know — reads
 * as "No provider", so an unchecked review never looks like a passed one.
 */
export function externalCheckLabel(status: string | undefined): { label: string; ran: boolean } {
  if (status === "clear") return { label: "No match found", ran: true };
  if (status === "flagged") return { label: "Match found", ran: true };
  return { label: "No provider", ran: false };
}

/**
 * MQA-003: a reported review's integrity checks, for the Reports view - the
 * checks its Review Queue card runs (the API builds both from the same card),
 * plus the reused-photo check. Flagged first. "not_run" is a check that could
 * not run (no provider, no photo), never shown as a pass.
 */
export type IntegrityCheck = {
  key: "spike" | "ring" | "copy" | "photo" | "ris" | "plagiarism" | "edited";
  label: string;
  state: "flagged" | "clear" | "not_run";
  detail: string;
};

export type ReviewSignalFacts = {
  signals: { velocity: boolean; collusion: boolean; duplicate_content: boolean };
  voting?: {
    upvoters: number;
    reciprocal_upvoters: number;
    min_upvoters: number;
    threshold: number;
    max_upvotes_in_velocity_window: number;
    velocity_threshold: number;
  } | null;
  integrity?: { plagiarism_status?: string; reverse_image_status?: string };
  edited_since_monetized?: boolean;
  has_photo?: boolean;
  reused_photo?: boolean;
};

export function reviewIntegrityChecks(facts: ReviewSignalFacts | null | undefined): IntegrityCheck[] {
  if (!facts) return [];
  const s = facts.signals;
  const v = facts.voting ?? null;
  const external = (key: "ris" | "plagiarism", label: string, status: string | undefined): IntegrityCheck => {
    const found = externalCheckLabel(status);
    return {
      key,
      label,
      state: !found.ran ? "not_run" : status === "flagged" ? "flagged" : "clear",
      detail: found.ran ? found.label : "No provider is configured, so this check does not run.",
    };
  };
  const checks: IntegrityCheck[] = [
    {
      key: "spike",
      label: "Vote spike",
      state: s.velocity ? "flagged" : "clear",
      detail: s.velocity
        ? v
          ? `${v.max_upvotes_in_velocity_window} up-votes within one hour; the check fires above ${v.velocity_threshold}.`
          : "Up-votes arrived faster than this check allows."
        : "No vote spike",
    },
    {
      key: "ring",
      label: "Voting ring",
      state: s.collusion ? "flagged" : "clear",
      detail: s.collusion
        ? v
          ? `${v.reciprocal_upvoters} of ${v.upvoters} up-voters are up-voted back by the author; the check fires at ${v.min_upvoters}+ up-voters above ${Math.round(v.threshold * 100)}% reciprocal.`
          : "The voting pattern matches the collusion check."
        : v && v.upvoters > 0
          ? "Votes look independent"
          : "No up-votes yet",
    },
    {
      key: "copy",
      label: "Copied text",
      state: s.duplicate_content ? "flagged" : "clear",
      detail: s.duplicate_content ? "The text matches a review already published on Bluntly." : "Text is original on Bluntly",
    },
    {
      key: "photo",
      label: "Reused photo",
      state: !facts.has_photo ? "not_run" : facts.reused_photo ? "flagged" : "clear",
      detail: !facts.has_photo
        ? "No photo on this review."
        : facts.reused_photo
          ? "Its photo matches an earlier review's photo on Bluntly."
          : "Photo not found on an earlier review",
    },
    external("ris", "Reverse image search", facts.integrity?.reverse_image_status),
    external("plagiarism", "Plagiarism (web)", facts.integrity?.plagiarism_status),
    {
      key: "edited",
      label: "Edited after its link",
      state: facts.edited_since_monetized ? "flagged" : "clear",
      detail: facts.edited_since_monetized
        ? "Changed since its affiliate link was attached."
        : "Not edited after a link",
    },
  ];
  const rank = { flagged: 0, clear: 1, not_run: 2 } as const;
  return checks.map((c, i) => [c, i] as const).sort((a, b) => rank[a[0].state] - rank[b[0].state] || a[1] - b[1]).map(([c]) => c);
}

/* ------------------------------------------------- selection and tab links */

/**
 * The console's tabs, in the order the console draws them. "all" is All
 * Reviews (QA, 2026-09-29): every review, beside the Reviews work queue.
 */
export type Tab = "reviews" | "all" | "answers" | "report" | "support";

const TAB_KEYS: Tab[] = ["reviews", "all", "answers", "report", "support"];

export const QUEUE_ROUTE = "/admin/review-queue";

export function isTab(value: string | null | undefined): value is Tab {
  return typeof value === "string" && (TAB_KEYS as string[]).includes(value);
}

/**
 * The row the detail panel shows.
 *
 * Chosen from the rows CURRENTLY VISIBLE, never from the whole queue. Picking
 * from the full source let the panel keep describing a review that the active
 * filter or the current page had scrolled away — an administrator reading the
 * evidence for one review while the table highlighted none of it, which is
 * exactly how the wrong review gets actioned.
 */
export function selectVisibleQueueItem<T extends QueueCard>(
  visible: T[],
  selectedId: string | null,
): T | null {
  if (visible.length === 0) return null;
  return visible.find((row) => row.review.id === selectedId) ?? visible[0];
}

/**
 * Where a tab points.
 *
 * The tabs are links, not local state. `AdminShell` titles the page from
 * `?tab` and `AdminNav` highlights its Q&A entry by matching `tab=answers`, so
 * a tab held only in component state left the heading and the rail describing
 * a different tab than the one on screen — and made the view unshareable.
 * The URL is the single source of truth; these hrefs are how it changes.
 *
 * EVERY canonical filter rides along, not just the band: coming back to a tab
 * that had quietly dropped the lane or the search would show an administrator a
 * wider queue than the one they left, with nothing on screen saying so. The
 * offset does not ride along — a page number counted into the list being left
 * behind means nothing in the one being opened.
 */
export function tabHref(tab: Tab, filters: QueueFilters): string {
  return queueHref(filters, { tab });
}

/**
 * The short label on the Voting Distribution panel.
 *
 * Wording matters here. `review_first_vote_geo_buckets` DOES record per-review
 * vote geography — `request_traffic_service.record_first_vote_geo` writes a row
 * on every newly created vote. What does not exist is a read path. Saying the
 * data is "not measured" states the opposite of the truth about what this
 * product collects, which is the wrong answer to give anyone asking a privacy
 * or retention question.
 */
export const VOTING_GEOGRAPHY_SHORT =
  "Collected per review, but not served to this console.";

/**
 * How a closed report reads on screen.
 *
 * Here rather than in `lib/moderation.ts` because the queue screen is a client
 * component: that module is `server-only`, and importing a VALUE from it (a
 * type is erased) would pull the server bundle into the browser.
 */
export const REPORT_RESOLUTION_LABELS: Record<string, string> = {
  dismissed: "Dismissed — the content stands",
  content_removed: "Removed — the review was unpublished",
  content_restored: "Restored — the review was published again",
  escalated: "Escalated to a Super Admin, who decides it",
};

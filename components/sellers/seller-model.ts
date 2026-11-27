/**
 * The rules behind the seller surfaces (FR-4), testable without a DOM.
 *
 * Two of them carry the honesty of every seller page:
 *
 *  - A store nobody has rated shows NO rate, not "0%". The API sends null for
 *    every rate and average until there is a review to aggregate, and
 *    `percent(null)` keeps it null rather than formatting it into a claim.
 *  - A rating is sent only once all six answers exist. "Not the same",
 *    "Missing item" and "I don't recommend" are answers; `false` is not blank.
 *
 * Limits: the prose floor is read off the owner's frames ("15 characters
 * remaining"). The title was the frame's 30 until MQA-038: a natural headline
 * ("Disappointing Quality — Died After a Week") did not fit and was cut off
 * mid-word, so it is 80 now (the API allows 200). Both fields count the same
 * way, "12 / 80" (MQA-039), through `fieldCounter`.
 */

export const MAX_SELLER_TITLE = 80;
export const MIN_SELLER_PROSE = 15;
export const MAX_SELLER_PHOTOS = 4;
export const MAX_SELLER_COMMENT = 2000;

export type SellerPlatform = "shopee" | "lazada" | "amazon" | "other";

export const PLATFORM_LABEL: Record<SellerPlatform, string> = {
  shopee: "Shopee",
  lazada: "Lazada",
  amazon: "Amazon",
  other: "Other marketplace",
};

export type SellerDraft = {
  overall: number | null;
  recommend: boolean | null;
  service: number | null;
  packaging: number | null;
  accuracy: boolean | null;
  completeness: boolean | null;
  title: string;
  comment: string;
  photoUrls: string[];
  /**
   * Business Rules §10: the marketplace order ID, optional and self-reported.
   * Never shown publicly; only an admin sees it, and only on an appeal.
   */
  orderId?: string;
};

export type SellerDimension =
  | "overall"
  | "recommend"
  | "service"
  | "packaging"
  | "accuracy"
  | "completeness";

/** Top to bottom, as "Seller Review - Step 2.png" draws them. */
const DIMENSION_ORDER: readonly SellerDimension[] = [
  "overall",
  "recommend",
  "service",
  "packaging",
  "accuracy",
  "completeness",
];

/** What a disabled Continue is waiting for, said to assistive technology. */
export const DIMENSION_PROMPT: Record<SellerDimension, string> = {
  overall: "Give the seller a star rating",
  recommend: "Say whether you recommend this seller",
  service: "Rate their customer service",
  packaging: "Rate their packaging",
  accuracy: "Say whether the order matched the listing",
  completeness: "Say whether your order was complete",
};

export function emptySellerDraft(): SellerDraft {
  return {
    overall: null,
    recommend: null,
    service: null,
    packaging: null,
    accuracy: null,
    completeness: null,
    title: "",
    comment: "",
    photoUrls: [],
  };
}

/** The first unanswered dimension, or null when all six have an answer. */
export function missingDimension(draft: SellerDraft): SellerDimension | null {
  return DIMENSION_ORDER.find((key) => draft[key] === null) ?? null;
}

/**
 * One counter format for every field (MQA-039): "length / max", and how close
 * it is - "near" from 90% of the cap, "over" past it (typing and pasting are
 * never cut short; the counter says it, and `contentBlocker` holds the
 * submit), "short" while under a minimum, with how many more are needed.
 */
export function fieldCounter(
  length: number,
  max: number,
  min = 0,
): { text: string; tone: "ok" | "near" | "over" | "short"; note: string | null } {
  const text = `${length} / ${max}`;
  if (length > max) {
    const over = length - max;
    return { text, tone: "over", note: `${over} character${over === 1 ? "" : "s"} over the limit` };
  }
  if (min > 0 && length < min) {
    const more = min - length;
    return { text, tone: "short", note: `${more} more character${more === 1 ? "" : "s"} needed` };
  }
  return { text, tone: length >= Math.ceil(max * 0.9) ? "near" : "ok", note: null };
}

/** Why the written step cannot be submitted yet, or null. */
export function contentBlocker(draft: SellerDraft): string | null {
  const title = draft.title.trim();
  if (!title) return "Give your review a title";
  if (title.length > MAX_SELLER_TITLE) {
    return `Keep the title to ${MAX_SELLER_TITLE} characters`;
  }
  const short = MIN_SELLER_PROSE - draft.comment.trim().length;
  if (short > 0) return `${short} more character${short === 1 ? "" : "s"} to go`;
  if (draft.comment.trim().length > MAX_SELLER_COMMENT) {
    return `Keep the description to ${MAX_SELLER_COMMENT} characters`;
  }
  return null;
}

export type SellerReviewPayload = {
  overall_rating: number;
  would_recommend: boolean;
  customer_service: number;
  packaging_quality: number;
  accuracy: boolean;
  order_completeness: boolean;
  title: string;
  comment: string;
  photo_urls: string[];
  order_id?: string;
};

/** The POST body. Throws rather than sending a half-answered rating. */
export function toSellerReviewPayload(draft: SellerDraft): SellerReviewPayload {
  const missing = missingDimension(draft);
  if (missing) throw new Error(`The ${missing} answer is missing`);
  const blocker = contentBlocker(draft);
  if (blocker) throw new Error(blocker);
  return {
    overall_rating: draft.overall as number,
    would_recommend: draft.recommend as boolean,
    customer_service: draft.service as number,
    packaging_quality: draft.packaging as number,
    accuracy: draft.accuracy as boolean,
    order_completeness: draft.completeness as boolean,
    title: draft.title.trim(),
    comment: draft.comment.trim(),
    photo_urls: [...draft.photoUrls],
    // Only when given: an empty field is "no order ID", not an empty one.
    ...(draft.orderId?.trim() ? { order_id: draft.orderId.trim() } : {}),
  };
}

/** 0.755 -> "76%". Null stays null: no data is not a zero. */
export function percent(rate: number | null): string | null {
  return rate === null ? null : `${Math.round(rate * 100)}%`;
}

export type StarBar = { star: number; count: number; share: number };

/**
 * The five-to-one breakdown. JSON delivers the keys as strings, and a star
 * nobody gave may be absent; both read as a count.
 */
export function distributionBars(distribution: Record<string, number>): StarBar[] {
  const counts = [5, 4, 3, 2, 1].map((star) => ({
    star,
    count: Number(distribution[star] ?? 0) || 0,
  }));
  const total = counts.reduce((sum, bar) => sum + bar.count, 0);
  return counts.map((bar) => ({ ...bar, share: total === 0 ? 0 : bar.count / total }));
}

/**
 * A star's share as the seller page frame writes it: "88%", "2.3%". Under ten
 * percent keeps one decimal; a share that rounds up to ten reads "10%".
 */
export function sharePercent(share: number): string {
  const pct = share * 100;
  if (pct === 0) return "0%";
  if (pct < 10) {
    const fixed = pct.toFixed(1);
    return fixed === "10.0" ? "10%" : `${fixed}%`;
  }
  return `${Math.round(pct)}%`;
}

/**
 * A review's age the way the seller frames write it: "5h", "12d". Pure: `now`
 * is the instant the SERVER rendered the page, passed down, never a clock read
 * during render. The seller page's lists are Client Components, so React
 * renders them on the server and again to hydrate; a review crossing a unit
 * between the two ("now" at 59s, "1m" at 60s) made the texts disagree and threw
 * React error #418 (br-journeys, 2026-09-29). An unreadable date gets no age;
 * one in the future is "now" rather than a negative number.
 */
export function shortAge(iso: string, now: number): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  if (seconds < 60) return "now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 14) return `${days}d`;
  if (days < 365) return `${Math.floor(days / 7)}w`;
  return `${Math.floor(days / 365)}y`;
}

type FilterableReview = {
  overall_rating: number;
  title: string | null;
  comment: string | null;
  created_at?: string;
};

/**
 * The star bar a rating belongs to — the store summary's own rule
 * (seller_service.summarize_reviews): ratings are half steps since 0048, so a
 * 4.5 counts in the 4-star bar and a 0 in the 1-star bar.
 */
export function starBucket(rating: number): number {
  return Math.max(1, Math.min(5, Math.floor(rating)));
}

/** The All filters sheet's Time, in days (search-tabs-model's Period). */
const PERIOD_DAYS = { year: 365, month: 30 } as const;

/**
 * The "All reviews" filter: only the ticked stars, and — when a keyword is
 * given — only reviews whose title or comment contains it, ignoring case —
 * and, when a period is given, only those posted within it (QA-057).
 * No star ticked matches nothing, which is what the unticked boxes say.
 *
 * Stars match by BAR, not by exact value. Matching `4.5` against the ticked
 * `[5, 4, 3, 2, 1]` found nothing, so every half-star review was missing from
 * the list even with every box ticked, while the bars above counted it.
 */
export function filterSellerReviews<T extends FilterableReview>(
  reviews: readonly T[],
  {
    stars,
    keyword,
    period = "all",
    now = Date.now(),
  }: { stars: readonly number[]; keyword: string; period?: "all" | "year" | "month"; now?: number },
): T[] {
  const needle = keyword.trim().toLowerCase();
  const since = period === "all" ? null : now - PERIOD_DAYS[period] * 86_400_000;
  return reviews.filter((review) => {
    if (!stars.includes(starBucket(review.overall_rating))) return false;
    if (since !== null && review.created_at && Date.parse(review.created_at) < since) return false;
    if (!needle) return true;
    return `${review.title ?? ""}\n${review.comment ?? ""}`.toLowerCase().includes(needle);
  });
}

export type SellerReviewSort = "newest" | "oldest" | "highest" | "lowest" | "photos";

/**
 * The seller page's Sort sheet, grouped as the Sort frame (1591:5408) groups
 * its orders: "By date:", then the rating, then photos.
 */
export const SELLER_REVIEW_SORT_SECTIONS: { heading: string; options: { value: SellerReviewSort; label: string }[] }[] = [
  { heading: "By date:", options: [{ value: "newest", label: "Latest" }, { value: "oldest", label: "Oldest" }] },
  { heading: "Rating:", options: [{ value: "highest", label: "Highest" }, { value: "lowest", label: "Lowest" }] },
  { heading: "Photos:", options: [{ value: "photos", label: "With photos first" }] },
];

export const SELLER_REVIEW_SORTS: { value: SellerReviewSort; label: string }[] =
  SELLER_REVIEW_SORT_SECTIONS.flatMap((s) => s.options);

type SortableReview = { overall_rating: number; created_at: string; photo_urls?: readonly string[] };

/**
 * QA-057: the seller page's Sort. A copy, never the input reordered; ties
 * fall back to newest first so the order is stable and meaningful.
 */
export function sortSellerReviews<T extends SortableReview>(reviews: readonly T[], sort: SellerReviewSort): T[] {
  const newest = (a: T, b: T) => Date.parse(b.created_at) - Date.parse(a.created_at);
  const by: Record<SellerReviewSort, (a: T, b: T) => number> = {
    newest,
    oldest: (a, b) => -newest(a, b),
    highest: (a, b) => b.overall_rating - a.overall_rating || newest(a, b),
    lowest: (a, b) => a.overall_rating - b.overall_rating || newest(a, b),
    photos: (a, b) => (b.photo_urls?.length ? 1 : 0) - (a.photo_urls?.length ? 1 : 0) || newest(a, b),
  };
  return [...reviews].sort(by[sort]);
}

/** The word under the average ("4.7 Excellent" in the seller page frame). */
export function ratingWord(average: number | null): string | null {
  if (average === null) return null;
  if (average >= 4.5) return "Excellent";
  if (average >= 3.5) return "Good";
  if (average >= 2.5) return "Average";
  if (average >= 1.5) return "Poor";
  return "Bad";
}

/** A store has no logo in this product, so it is drawn as its initials. */
export function sellerInitials(name: string): string {
  const initials = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((word) => word[0].toUpperCase())
    .join("");
  return initials || "?";
}

/** The line in the card above the written step, following the stars given. */
export function ratingPrompt(overall: number | null): string | null {
  if (overall === null) return null;
  if (overall >= 5) return "You gave them a great rating. We’d love to hear more!";
  if (overall === 4) return "You gave them a pretty good rating. We’d love to hear more!";
  if (overall === 3) return "A mixed experience? Tell people what went right and what didn’t.";
  return "Sorry it didn’t go well. Tell people what happened.";
}

/* --------------------------------------------------- owner dashboard */

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-09" -> "Sep 2026". Fixed English names, so the label never depends on locale. */
export function monthLabel(key: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(key);
  if (!match) return key;
  const index = Number(match[2]) - 1;
  return index >= 0 && index < 12 ? `${MONTH_NAMES[index]} ${match[1]}` : key;
}

export type VolumeBar = { month: string; count: number; share: number };

/**
 * Review volume as bars, each a share of the busiest month in the window. The
 * API zero-fills the months, so a quiet month is an empty bar, never a gap.
 */
export function volumeBars(months: { month: string; count: number }[]): VolumeBar[] {
  const max = months.reduce((most, m) => Math.max(most, m.count), 0);
  return months.map((m) => ({ month: m.month, count: m.count, share: max === 0 ? 0 : m.count / max }));
}

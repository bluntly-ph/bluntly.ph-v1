/** Which set of results /search is showing. */
export type SearchTab = "reviews" | "questions" | "sellers" | "people";

/**
 * The review orders the feed serves (GET /reviews/feed `sort`): most helpful —
 * a Wilson lower bound on helpful votes, and the default — then newest and
 * oldest, and "Lowest rated" (the Sort menu, Figma 7762:9948): fewest stars first.
 */
export type ReviewSort = "wilson" | "newest" | "oldest" | "lowest";

export const DEFAULT_REVIEW_SORT: ReviewSort = "wilson";

/** All filters' Time (Figma 1587:4658): the reviews and questions APIs serve it. */
export type Period = "all" | "year" | "month";

/**
 * The All filters sheet's Review score lens (QA-053). "Most Helpful" is no
 * lens — the feed's default order. Definitions: backend
 * app/services/review_lenses.py, and LENS_INFO below, which the sheet shows.
 */
export type ReviewLens = "hidden_gems" | "controversial" | "trending";

export const LENS_LABEL: Record<ReviewLens, string> = {
  hidden_gems: "Hidden Gems",
  controversial: "Controversial",
  trending: "Trending",
};

export const LENS_INFO =
  "All: every review, readers' most helpful first. Hidden Gems: reviews readers found helpful, of products " +
  "at most three people have reviewed. Controversial: readers split on it, most votes first. " +
  "Trending: the most helpful votes and comments in the past 7 days.";

/** The Trust rating bands: the author's trust score, 80–100 or under 80. */
export type TrustBand = "high" | "low";

export const TRUST_LABEL: Record<TrustBand, string> = {
  high: "Trust 80–100",
  low: "Trust under 80",
};

/**
 * The Budget slider's stops, in pesos: what the reviewer paid, at most this.
 * The last stop is no limit. Fixed stops rather than any number, so every
 * position means a round amount a reader can read back from the chip.
 */
export const BUDGET_STEPS = [500, 1000, 2500, 5000, 10000] as const;

/** The Questions tab's By-date order (QA-050). */
export type QuestionSort = "newest" | "oldest";

/**
 * The Sellers tab's order. "ranked" is the default (MQA-033): the
 * best-evidenced stores first — the confidence in a store's share of positive
 * reviews, so many good reviews outrank a few perfect ones, nudged by recent
 * reviews (backend seller_service.seller_rank_score). Then the most-reviewed
 * first, or by name (QA-052).
 */
export type SellerSort = "ranked" | "reviews" | "name";

export const DEFAULT_SELLER_SORT: SellerSort = "ranked";

export const SELLER_SORT_LABEL: Record<SellerSort, string> = {
  ranked: "Best evidenced",
  reviews: "Most reviews",
  name: "Name (A–Z)",
};

export const SELLER_SORT_INFO =
  "Best evidenced: stores with the most and best reviews first — many good reviews outrank a few " +
  "perfect ones, and recent reviews count a little more. Stores with no reviews come last.";

/** The marketplaces a store can be filtered to. */
export type SellerPlatformFilter = "shopee" | "lazada";

export const PERIOD_LABEL: Record<Exclude<Period, "all">, string> = {
  year: "Past year",
  month: "Past month",
};

/** A `?sort=` value from the URL, narrowed to an order the feed serves. */
export function parseReviewSort(raw: string | undefined): ReviewSort {
  return raw === "newest" || raw === "oldest" || raw === "lowest" ? raw : DEFAULT_REVIEW_SORT;
}

/** The filter sheet's Rating groups (Figma 7762:9999), highest first. */
export const STAR_GROUPS = [5, 4, 3, 2, 1] as const;

/** `?stars=5,4` as whole-star groups, highest first, without repeats. */
export function parseStars(raw: string | undefined): number[] {
  const picked = new Set((raw ?? "").split(",").map((v) => Number(v.trim())));
  return STAR_GROUPS.filter((s) => picked.has(s));
}

/** `?photos=1` and the other Show only switches. */
export function parseFlag(raw: string | undefined): boolean {
  return raw === "1" || raw === "true";
}

/** `?claimed=1` claimed only, `?claimed=0` unclaimed only, else both. */
export function parseClaimed(raw: string | undefined): boolean | undefined {
  if (raw === "1" || raw === "true") return true;
  if (raw === "0" || raw === "false") return false;
  return undefined;
}

export type SellerRatingFloor = 3 | 4;

export function parseSellerRating(raw: string | undefined): SellerRatingFloor | undefined {
  return raw === "4" ? 4 : raw === "3" ? 3 : undefined;
}

export type AnswerWindow = "day" | "week";

export const ANSWER_WINDOW_LABEL: Record<AnswerWindow, string> = {
  day: "Within a day",
  week: "Within a week",
};

export function parseAnswerWindow(raw: string | undefined): AnswerWindow | undefined {
  return raw === "day" || raw === "week" ? raw : undefined;
}

export function parsePeriod(raw: string | undefined): Period {
  return raw === "year" || raw === "month" ? raw : "all";
}

export function parseQuestionSort(raw: string | undefined): QuestionSort {
  return raw === "oldest" ? "oldest" : "newest";
}

export function parseSellerSort(raw: string | undefined): SellerSort {
  return raw === "reviews" || raw === "name" ? raw : DEFAULT_SELLER_SORT;
}

export function parseLens(raw: string | undefined): ReviewLens | undefined {
  return raw === "hidden_gems" || raw === "controversial" || raw === "trending" ? raw : undefined;
}

export function parseTrust(raw: string | undefined): TrustBand | undefined {
  return raw === "high" || raw === "low" ? raw : undefined;
}

/** `?max_price=` narrowed to one of the slider's stops; anything else is no budget. */
export function parseBudget(raw: string | undefined): number | undefined {
  const n = Number(raw);
  return (BUDGET_STEPS as readonly number[]).includes(n) ? n : undefined;
}

export function budgetLabel(maxPrice: number): string {
  return `Up to ₱${maxPrice.toLocaleString("en-PH")}`;
}

export function parsePlatform(raw: string | undefined): SellerPlatformFilter | undefined {
  return raw === "shopee" || raw === "lazada" ? raw : undefined;
}

/**
 * `?category=` as a list (QA-025). Several categories travel comma-separated,
 * in the order chosen, without repeats; `known` drops anything that is not a
 * real category so a hand-edited URL cannot put an inert filter on the page.
 */
export function parseCategories(
  raw: string | string[] | undefined,
  known?: readonly string[],
): string[] {
  const parts = (Array.isArray(raw) ? raw : [raw ?? ""]).flatMap((v) => v.split(","));
  const out: string[] = [];
  for (const part of parts) {
    const slug = part.trim();
    if (!slug || out.includes(slug)) continue;
    if (known && !known.includes(slug)) continue;
    out.push(slug);
  }
  return out;
}

export type SearchState = {
  q?: string;
  from?: string;
  /** Reviews: one category, as older links carry it. */
  category?: string;
  /** Reviews: any number of categories. */
  categories?: readonly string[];
  sort?: ReviewSort;
  /** Reviews: All filters' Review score, Trust rating and Budget (QA-053). */
  lens?: ReviewLens;
  trust?: TrustBand;
  maxPrice?: number;
  /** Reviews: the sheet's Rating, Show only and Variant (Figma 7762:9999). */
  stars?: readonly number[];
  photos?: boolean;
  verified?: boolean;
  recommends?: boolean;
  variant?: string;
  /** Reviews and questions. */
  period?: Period;
  questionSort?: QuestionSort;
  platform?: SellerPlatformFilter;
  /** Sellers' Profile: true claimed, false unclaimed, undefined both. */
  claimed?: boolean;
  minRating?: SellerRatingFloor;
  answers?: AnswerWindow;
  sellerSort?: SellerSort;
};

/**
 * The href for a tab, preserving the reader's context across the switch.
 *
 * Exported so the rules are testable without a DOM: the query follows the reader
 * to the other tab, `reviews` is the default and so carries no `tab` parameter,
 * and each tab's filters and order stay with that tab — a category means
 * nothing to a store, and a filter the other tab does not apply would sit in
 * the URL silently doing nothing. Defaults are left out, so the plain URL stays
 * the canonical one.
 */
export function searchTabHref(tab: SearchTab, state: SearchState = {}): string {
  const { q, from } = state;
  const params = new URLSearchParams();
  if (q?.trim()) params.set("q", q);
  if (tab === "reviews") {
    const categories = parseCategories([...(state.category ? [state.category] : []), ...(state.categories ?? [])]);
    if (categories.length) params.set("category", categories.join(","));
    if (state.sort && state.sort !== DEFAULT_REVIEW_SORT) params.set("sort", state.sort);
    if (state.period && state.period !== "all") params.set("period", state.period);
    if (state.lens) params.set("lens", state.lens);
    if (state.trust) params.set("trust", state.trust);
    if (state.maxPrice) params.set("max_price", String(state.maxPrice));
    const stars = parseStars((state.stars ?? []).join(","));
    if (stars.length && stars.length < STAR_GROUPS.length) params.set("stars", stars.join(","));
    if (state.photos) params.set("photos", "1");
    if (state.verified) params.set("verified", "1");
    if (state.recommends) params.set("recommends", "1");
    if (state.variant) params.set("variant", state.variant);
  } else {
    params.set("tab", tab);
    if (tab === "questions") {
      if (state.questionSort === "oldest") params.set("sort", "oldest");
      if (state.period && state.period !== "all") params.set("period", state.period);
    } else if (tab === "sellers") {
      if (state.platform) params.set("platform", state.platform);
      if (state.claimed !== undefined) params.set("claimed", state.claimed ? "1" : "0");
      if (state.minRating) params.set("rating", String(state.minRating));
      if (state.answers) params.set("answers", state.answers);
      if (state.sellerSort && state.sellerSort !== DEFAULT_SELLER_SORT) params.set("sort", state.sellerSort);
    }
  }
  if (from) params.set("from", from);
  const qs = params.toString();
  return `/search${qs ? `?${qs}` : ""}`;
}

/**
 * Where clearing the review filters goes. A visitor who arrived from
 * /categories goes back there rather than being stranded on an unfiltered
 * /search (BUG-011); anyone else keeps their query and order with the filters
 * dropped.
 */
export function clearCategoryHref({
  q,
  sort,
  from,
}: {
  q?: string;
  sort?: ReviewSort;
  from?: string;
}): string {
  if (from === "categories") return "/categories";
  return searchTabHref("reviews", { q, sort, from });
}

/** A category's membership flipped — the desktop rail's category links. */
export function toggleCategory(categories: readonly string[], slug: string): string[] {
  return categories.includes(slug) ? categories.filter((c) => c !== slug) : [...categories, slug];
}

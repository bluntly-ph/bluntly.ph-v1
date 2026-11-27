/**
 * The query strings the search's filters send, in one place the server and the
 * browser share: the page's list (lib/reviews, lib/sellers, server-only) and
 * the filter sheet's live "Show 42 reviews" / "Show 24 sellers" count, which
 * asks GET /reviews/feed/count and GET /sellers/count from the browser through
 * /api/bff while the reader is still choosing. Same builder, so the count on
 * the pill is the count the list will show.
 */

/** GET /reviews/feed and /reviews/feed/count filters. */
export type FeedFilters = {
  q?: string;
  category?: string;
  categories?: readonly string[];
  author_id?: string;
  product_id?: string;
  period?: "all" | "year" | "month";
  lens?: "hidden_gems" | "controversial" | "trending";
  trust?: "high" | "low";
  maxPrice?: number;
  /** Rating (Figma 7762:9999): whole-star groups, several at once. */
  stars?: readonly number[];
  /** Show only. */
  photos?: boolean;
  verified?: boolean;
  recommends?: boolean;
  /** One of the product's variants (GET /reviews/feed/variants). */
  variant?: string;
};

/** The longest search text the API accepts (`q: max_length=200` on /reviews/feed). */
export const MAX_QUERY_LENGTH = 200;

/** The filters as URL parameters, normalized (see `feedQuery`). */
export function feedFilterParams(opts: FeedFilters): URLSearchParams {
  const params = new URLSearchParams();
  const q = opts.q?.trim().slice(0, MAX_QUERY_LENGTH).trim();
  if (q) params.set("q", q);
  // One spelling per category, in one order: the API lowercases slugs itself
  // (app/core/categories.py spellings_for), so "Beauty" and "beauty", or
  // "a,b" and "b,a", are the same results and must be the same cache entry.
  const categories = [opts.category, ...(opts.categories ?? [])]
    .map((c) => c?.trim().toLowerCase())
    .filter((c): c is string => Boolean(c));
  for (const c of [...new Set(categories)].sort()) params.append("category", c);
  if (opts.period && opts.period !== "all") params.set("period", opts.period);
  if (opts.lens) params.set("lens", opts.lens);
  if (opts.trust) params.set("trust", opts.trust);
  if (opts.maxPrice) params.set("max_price", String(opts.maxPrice));
  if (opts.author_id) params.set("author_id", opts.author_id);
  if (opts.product_id) params.set("product_id", opts.product_id);
  for (const s of [...new Set(opts.stars ?? [])].sort((a, b) => a - b)) params.append("stars", String(s));
  if (opts.photos) params.set("photos", "true");
  if (opts.verified) params.set("verified", "true");
  if (opts.recommends) params.set("recommends", "true");
  const variant = opts.variant?.trim();
  if (variant) params.set("variant", variant);
  return params;
}

/** The page controls that ride beside the filters on /feed and /feed/page. */
export type FeedPage = {
  sort?: "wilson" | "newest" | "oldest" | "lowest";
  limit?: number;
  offset?: number;
  mode?: "plain" | "for-you";
  /** "card": only what a card shows (FeedCardOut). */
  view?: "card";
};

/**
 * Every review feed and count query string, built in one place (2026-10-22).
 *
 * The query string is the Data Cache key, so two requests for the same results
 * must spell it the same way, or each is a miss and a backend call: keys are
 * sorted, values normalized as above, and only filter keys are ever read, so a
 * page's UI-only parameters (`from`, `tab`, `page`, the sheet's open state)
 * can never split the cache. The filter sheet's live count uses it too, so the
 * pill and the list it promises always ask the same question.
 */
export function feedQuery(opts: FeedFilters, page: FeedPage = {}): string {
  const params = feedFilterParams(opts);
  if (page.sort) params.set("sort", page.sort);
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  if (page.offset) params.set("offset", String(page.offset));
  if (page.mode) params.set("mode", page.mode);
  if (page.view) params.set("view", page.view);
  params.sort();
  return params.toString();
}

/** GET /sellers and /sellers/count filters (Sheet/Filter sellers 8462:36591). */
export type SellerFilters = {
  q?: string;
  platform?: "shopee" | "lazada";
  /** Profile: true claimed by the owner, false unclaimed, undefined both. */
  claimed?: boolean;
  /** Rating: "4★ & up" / "3★ & up". */
  minRating?: 3 | 4;
  /** Answers buyers: the store's median time to answer, within a day or a week. */
  answers?: "day" | "week";
};

export function sellerFilterParams(opts: SellerFilters): URLSearchParams {
  const params = new URLSearchParams();
  const needle = opts.q?.trim();
  if (needle) params.set("q", needle);
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.claimed !== undefined) params.set("claimed", String(opts.claimed));
  if (opts.minRating) params.set("min_rating", String(opts.minRating));
  if (opts.answers) params.set("answers_within", opts.answers);
  return params;
}

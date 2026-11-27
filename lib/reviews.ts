import "server-only";

import { apiFetch } from "./api/client";
import { feedQuery, type FeedFilters, type FeedPage } from "./search-filter-params";
import { REVIEW_LISTS, reviewTag } from "./cache-tags";
import { usablePhoto } from "./image";
import { reviewPhoto, reviewPhotos } from "./review-media";
import { showsTrustBadge } from "@/components/review/trust-badge-model";
import type { Comment } from "./comments";
import type { PricePanel } from "./products";
import {
  FEATURED_REVIEW,
  READING_REVIEWS,
  type ReviewCardData,
} from "./landing-data";

/**
 * Read-side data for the public card surfaces, from `GET /api/v1/reviews/feed`
 * (published reviews joined with author + product). Everything is fetched
 * server-side without a token — the feed is public. If the backend is
 * unreachable or empty, the curated landing samples stand in so the page is
 * never blank.
 */

export type Verdict = "yes_absolutely" | "it_depends" | "hard_pass";

type FeedItem = {
  review: {
    id: string;
    review_id: string | null;
    title: string;
    discussion: string;
    verdict: Verdict;
    verdict_explanation: string | null;
    target_audience: string | null;
    anti_target_audience: string | null;
    star_rating: number;
    pros: string[] | null;
    cons: string[] | null;
    price_paid: string | null;
    /** Disclosure (X.1); null when the review predates the question. */
    material_relationship?: "none" | "free_or_discounted" | "connected" | null;
    photo_url: string | null;
    /**
     * Every photo the reviewer uploaded, in order, once the API stores them
     * (docs/REVIEW_MEDIA_CONTRACT.md); absent before. Read via reviewPhotos.
     */
    photo_urls?: string[] | null;
    verification_status: "verified" | "unverified";
    /** X.2: proof + administrator decision + publication. Read via showsTrustBadge. */
    has_trust_badge?: boolean;
    /** Business Rules §3: a photo of the item or a receipt — "Photo provided". */
    photo_provided?: boolean;
    /** Business Rules §4: the thread's root id (a root is its own thread). */
    thread_id?: string | null;
    is_thread_root?: boolean;
    /** The one allowed photo swap was used at this time. */
    photo_replaced_at?: string | null;
    helpful_votes: number;
    unhelpful_votes: number;
    /**
     * The requesting viewer's own vote (BUG-013). Only ever populated when the
     * call carries a token — an anonymous read has no viewer, so it is null for
     * everyone and the response stays safely cacheable.
     */
    my_vote: "up" | "down" | null;
    /** null while held for moderation; only its author or an administrator can load it then. */
    published_at?: string | null;
    earn_eligible_status?: string;
    created_at: string;
    referral_redirect_url: string | null;
  };
  author: {
    id: string;
    username: string | null;
    display_name: string | null;
    avatar_url: string | null;
    trust_stage: number;
    trust_level_name: string | null;
    /** 0..100 (ADR-003); shown beside the level name. See lib/trust.ts. */
    reputation_score: string | null;
  } | null;
  product: {
    id: string;
    canonical_name: string | null;
    category: string | null;
    /** Median of each reviewer's latest entry (Business Rules §4). */
    median_rating?: string | null;
    /** Deprecated alias of median_rating. */
    avg_rating: string | null;
    /** How many published reviews the product has, for the desktop sidebar. */
    review_count: number;
    /** The product listing image: product context only, never a review's photo. */
    image_url: string | null;
  } | null;
  /** Live count of non-removed comments, for the card's stats row (BUG-006). */
  comment_count: number;
  /** QA-054: the administrator's reason, served only to the review's author. */
  author_rejection_reason?: string | null;
  /** QA-054: why an administrator took it down, while it is down; author only. */
  author_takedown_reason?: string | null;
  /**
   * QA-006: the product's own marketplace listing (https, a known
   * marketplace host), for reviews without an approved affiliate link.
   * A plain link: it earns nobody anything. Served on the full review only.
   */
  listing_url?: string | null;
  listing_platform?: "shopee" | "lazada" | "amazon" | "other" | null;
};

export type ReviewFull = FeedItem;

/**
 * One card from a card list (`/reviews/feed?view=card`, `/reviews/feed/page`):
 * only what `toCard`, `toFeedCard` and `toFeatured` read (E1, 2026-10-22). The
 * review's text arrives as a 200-character `excerpt` cut by the API, never as
 * the full discussion. A full FeedItem fits this shape too (the own-reviews
 * list still reads the full one), which is why `discussion` stays optional.
 */
type CardItem = {
  review: Pick<
    FeedItem["review"],
    | "id"
    | "title"
    | "verdict"
    | "star_rating"
    | "photo_url"
    | "photo_urls"
    | "helpful_votes"
    | "unhelpful_votes"
    | "my_vote"
    | "created_at"
    | "has_trust_badge"
  > & { excerpt?: string; discussion?: string };
  author: FeedItem["author"];
  product: { id: string; canonical_name: string | null; category: string | null } | null;
  comment_count: number;
};

/** The text a card excerpts: the API's excerpt, or a full item's discussion. */
function cardText(item: CardItem): string {
  return item.review.excerpt ?? item.review.discussion ?? "";
}

/**
 * A single review with its author and product, or null if not found/visible.
 *
 * Pass the viewer's `token` to get `my_vote` populated (BUG-013). Doing so also
 * suppresses the shared Data Cache — apiFetch drops `revalidate` whenever a
 * token is present — which is the point: a response carrying one reader's vote
 * must never be served to another. Signed-out readers keep the cached path.
 */
export async function getReviewFull(
  id: string,
  token?: string | null,
): Promise<ReviewFull | null> {
  try {
    return await apiFetch<FeedItem>(`/api/v1/reviews/${id}/full`, {
      token: token ?? undefined,
      revalidate: 60,
      tags: [reviewTag(id)],
    });
  } catch {
    return null;
  }
}

/** One entry of a review thread (Business Rules §4). The latest one counts. */
export type ThreadEntry = {
  id: string;
  title: string;
  verdict: Verdict;
  star_rating: number;
  published_at: string | null;
  created_at: string;
  is_root: boolean;
  is_latest: boolean;
};

export type ReviewThread = {
  thread_id: string;
  entries: ThreadEntry[];
  /** Author only: when the next update entry may be added. */
  next_update_at: string | null;
};

/**
 * A review's whole thread. With the author's token it also says when their
 * next update opens; that is per-viewer, so a token read is never cached
 * (apiFetch drops `revalidate` whenever a token is present).
 */
export async function getReviewThread(
  id: string,
  token?: string | null,
): Promise<ReviewThread | null> {
  try {
    return await apiFetch<ReviewThread>(`/api/v1/reviews/${id}/thread`, {
      token: token ?? undefined,
      revalidate: 60,
      tags: [reviewTag(id)],
    });
  } catch {
    return null;
  }
}

/**
 * Everything the review page renders, in ONE backend call
 * (GET /api/v1/pages/review/{id}; cost plan, 2026-10-22). It replaced seven
 * calls in two rounds (review, comments, thread, then the price panel,
 * related reviews and the payout-removal count), each a billed function call
 * and a database transaction. Each part comes from the same handler as its
 * own route, with the same viewer, so nothing on the page changes.
 *
 * Signed out (no token), it is cached for 60 s under this review's tag, which
 * every write to the review already expires, and under the lists' tag for the
 * related column. With a token it is per-viewer and never cached. Null when
 * the review is not visible to this viewer, or the API did not answer.
 */
export type ReviewPageData = {
  data: ReviewFull;
  comments: Comment[];
  thread: ReviewThread | null;
  pricePanel: PricePanel | null;
  /** Up to five, read signed out; the page drops the open review and keeps four. */
  related: ReviewCardData[];
  removedAfterPayout: number;
};

export async function getReviewPageData(
  id: string,
  token?: string | null,
): Promise<ReviewPageData | null> {
  try {
    const page = await apiFetch<{
      review: FeedItem;
      comments: Comment[];
      thread: ReviewThread | null;
      price_panel: PricePanel | null;
      related: CardItem[];
      removed_after_payout_count: number;
    }>(
      `/api/v1/pages/review/${encodeURIComponent(id)}`,
      token ? { token } : { revalidate: 60, tags: [reviewTag(id), REVIEW_LISTS] },
    );
    return {
      data: page.review,
      comments: page.comments ?? [],
      thread: page.thread ?? null,
      pricePanel: page.price_panel ?? null,
      related: (page.related ?? []).map(toCard),
      removedAfterPayout: page.removed_after_payout_count ?? 0,
    };
  } catch {
    return null;
  }
}

export { ageLabel, compact };

export type FeaturedData = {
  id: string;
  author: string;
  /** The @handle, shown instead of a "Verified Buyer" label (BUG-004). */
  username: string | null;
  /** The reviewer's own photo, when they have one; else a hue placeholder. */
  avatarUrl: string | null;
  authorHue: number;
  /** Null only on the offline sample, which has no real author to rate. */
  trust: string | null;
  ageLabel: string;
  /** Trust level name and its 0..100 score, rendered together by TrustBadge. */
  trustStage: number;
  trustScore: string | null;
  /** Bold half of the split headline — the product (BUG-004). */
  product: string | null;
  /** Italic half — what the reviewer concluded about it. */
  title: string;
  excerpt: string;
  /** Its reactions, compacted ("1.3k"), for the hero's ReviewQuoteCard. */
  upvotes: string;
  comments: string;
};

/**
 * Split a headline into "what it is" and "what they thought" (BUG-004).
 *
 * Reviewers overwhelmingly write titles that already name the product —
 * "Akko 5075B Plus — the budget board that punches up" — which is why simply
 * prefixing the canonical name produced "Akko 5075B Plus — Akko 5075B Plus — …".
 * So prefer the reviewer's own dash if there is one, and fall back to the
 * canonical name only when the title carries no product of its own.
 */
export function splitHeadline(
  title: string,
  productName: string | null | undefined,
): { product: string | null; rest: string } {
  const dash = title.match(/^(.{2,80}?)\s+[—–-]\s+(.+)$/);
  if (dash) return { product: dash[1].trim(), rest: dash[2].trim() };
  if (productName?.trim()) return { product: productName.trim(), rest: title.trim() };
  return { product: null, rest: title.trim() };
}

/** Stable 0–359 hue from a string, for placeholder avatar/image tints. */
function hueOf(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return h;
}

/** "5h" / "12d" / "3w" — the compact age the cards show. */
function ageLabel(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  const h = Math.floor(secs / 3600);
  if (h < 1) return `${Math.max(1, Math.floor(secs / 60))}m`;
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d`;
  return `${Math.floor(d / 7)}w`;
}

/** 11 → "11", 14800 → "14.8k", 3_200_000 → "3.2m". */
function compact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}m`;
}

function authorName(item: CardItem): string {
  return item.author?.display_name || item.author?.username || "reviewer";
}

/** A submitted photo we can actually render — not the synthetic seed placeholder. */
// Defined in `lib/image.ts` (client-safe) and re-exported here so the server
// components already importing it from this module keep working. Imported as
// well as re-exported, because the helpers below call it.
export { usablePhoto };

/**
 * The card headline. Reviewers write titles that already name the product
 * ("Akko 5075B Plus — the budget board…"), so we use the title as-is; prefixing
 * the canonical product name only produced "Product — Product — …" duplication.
 */
function cardTitle(item: CardItem): string {
  return item.review.title.trim();
}

function toCard(item: CardItem): ReviewCardData {
  const author = authorName(item);
  return {
    id: item.review.id,
    author,
    authorHue: hueOf(author),
    ageLabel: ageLabel(item.review.created_at),
    username: item.author?.username ?? null,
    avatarUrl: usablePhoto(item.author?.avatar_url),
    trustScore: item.author?.reputation_score ?? null,
    trustStage: item.author?.trust_stage ?? 0,
    trustLevel: item.author?.trust_level_name ?? null,
    product: item.product?.canonical_name ?? null,
    title: cardTitle(item),
    upvotes: compact(item.review.helpful_votes),
    // Real, from the feed's grouped count (BUG-006). Hardcoded empty before,
    // which is why the comment stat never once appeared on a card.
    comments: item.comment_count ? compact(item.comment_count) : "0",
    imageHue: hueOf(item.review.id),
    // The reviewer's own photo only — it is evidence they actually held the
    // thing. Without one the card shows its hue placeholder: the product's
    // listing image is not the reviewer's photo (owner bug report, 2026-10-03;
    // it was the fallback under BUG-009).
    imageUrl: reviewPhoto(item.review),
    photoUrls: reviewPhotos(item.review),
    authorId: item.author?.id ?? null,
    helpfulCount: item.review.helpful_votes ?? 0,
    unhelpfulCount: item.review.unhelpful_votes ?? 0,
    myVote: item.review.my_vote ?? null,
    excerpt: excerptOf(cardText(item)),
  };
}

function toFeatured(item: CardItem): FeaturedData {
  const author = authorName(item);
  // The canonical name in full — the card used to shorten it, so "Jisulife
  // Handheld Fan Life9" reached the reader as "Jisulife Life9" (BUG-004).
  const { product, rest } = splitHeadline(cardTitle(item), item.product?.canonical_name);
  return {
    id: item.review.id,
    author,
    username: item.author?.username ?? null,
    avatarUrl: usablePhoto(item.author?.avatar_url),
    authorHue: hueOf(author),
    trust: item.author?.trust_level_name ?? `Stage ${item.author?.trust_stage ?? 0}`,
    trustStage: item.author?.trust_stage ?? 0,
    trustScore: item.author?.reputation_score ?? null,
    ageLabel: ageLabel(item.review.created_at),
    product,
    title: rest,
    excerpt: cardText(item),
    upvotes: compact(item.review.helpful_votes),
    comments: item.comment_count ? compact(item.comment_count) : "0",
  };
}

/** The curated fallback featured card, from the static sample content. */
const SAMPLE_HEADLINE = splitHeadline(FEATURED_REVIEW.title, null);

const SAMPLE_FEATURED: FeaturedData = {
  id: "",
  author: FEATURED_REVIEW.author,
  // No handle or photo for the sample: it stands in when the backend is
  // unreachable, and inventing a plausible @handle for a person who does not
  // exist is worse than showing the display name alone.
  username: null,
  avatarUrl: null,
  authorHue: hueOf(FEATURED_REVIEW.author),
  // No trust level either. This read "Community Expert" at stage 3 — a level
  // nobody earned, and not even stage 3's name. The card draws no badge for it.
  trust: null,
  // No score on the sample: it stands in when the backend is unreachable, and a
  // fabricated trust number is exactly the kind of thing this site exists to
  // not do. TrustBadge renders the level name alone when the score is null.
  trustStage: 3,
  trustScore: null,
  ageLabel: FEATURED_REVIEW.ageLabel,
  product: SAMPLE_HEADLINE.product,
  title: SAMPLE_HEADLINE.rest,
  excerpt: FEATURED_REVIEW.excerpt,
  // Its real zero: an invented reaction count is a made-up number too.
  upvotes: "0",
  comments: "0",
};

/** Search / browse results for the search, category, and profile surfaces. */
/**
 * The signed-in reader's own votes, laid over cards that came from the shared
 * cache (cost plan, 2026-10-22). A card list is the same for everyone except
 * `my_vote`, so a signed-in read used to skip the cache entirely for that one
 * field; it now reads the cached anonymous list and asks only
 * GET /reviews/my-votes for the reader's votes. If that call fails the cards
 * show no vote highlighted, which is how they read signed out.
 */
async function withMyVotes(items: CardItem[], token: string): Promise<CardItem[]> {
  const ids = items.map((i) => i.review.id);
  if (!ids.length) return items;
  const params = new URLSearchParams();
  for (const id of ids.slice(0, 100)) params.append("ids", id);
  const mine = await apiFetch<{ votes: Record<string, "up" | "down"> }>(
    `/api/v1/reviews/my-votes?${params}`,
    { token },
  ).catch(() => null);
  if (!mine) return items;
  return items.map((i) => ({ ...i, review: { ...i.review, my_vote: mine.votes[i.review.id] ?? null } }));
}

export async function searchReviews(opts: FeedFilters & {
  /** "lowest": the Sort menu's "Lowest rated" (Figma 7762:9948). */
  sort?: "wilson" | "newest" | "oldest" | "lowest";
  limit?: number;
  /** Where the page starts (MQA-036: the Reviews tab has page numbers). */
  offset?: number;
  /**
   * The signed-in reader's session: the rows then carry their own votes
   * (QA-027/028). The list itself always comes from the shared 60 s cache;
   * only the votes are read with the token (`withMyVotes`).
   */
  token?: string | null;
}): Promise<ReviewCardData[] | null> {
  const query = feedQuery(opts, {
    sort: opts.sort ?? "wilson",
    limit: opts.limit ?? 24,
    offset: opts.offset,
    view: "card",
  });
  try {
    // Always the shared, cached list; a signed-in reader's votes come on top.
    const items = await apiFetch<CardItem[]>(`/api/v1/reviews/feed?${query}`,
      { revalidate: 60, tags: [REVIEW_LISTS] });
    return (opts.token ? await withMyVotes(items, opts.token) : items).map(toCard);
  } catch {
    // null, not [] — "we could not reach the server" and "this search matched
    // nothing" are different answers, and only one of them is the reader's
    // fault to act on. Returning [] made an outage read as "No reviews found".
    return null;
  }
}

/**
 * How many reviews a search or the feed pages through (GET /reviews/feed/count,
 * the same filters and query as the list), for "214 reviews" and the page
 * numbers. null when the API did not answer: the list still shows, unnumbered.
 */
export async function countReviews(opts: FeedFilters): Promise<number | null> {
  try {
    // Five minutes: a total moves slower than the cards, and nothing on the
    // page reads it to the review (the list beside it is the 60-second read).
    const out = await apiFetch<{ total: number }>(`/api/v1/reviews/feed/count?${feedQuery(opts)}`, {
      revalidate: 300,
      tags: [REVIEW_LISTS],
    });
    return out.total;
  } catch {
    return null;
  }
}

/**
 * The variants one product's reviewers reported (GET /reviews/feed/variants),
 * for the filter sheet's Variant chips. Empty when none did, or when the API
 * did not answer: either way the sheet draws no Variant group.
 */
export async function getReviewVariants(productId: string): Promise<string[]> {
  try {
    return await apiFetch<string[]>(
      `/api/v1/reviews/feed/variants?product_id=${encodeURIComponent(productId)}`,
      { revalidate: 60, tags: [REVIEW_LISTS] },
    );
  } catch {
    return [];
  }
}

/** Where one of the caller's own reviews stands (GET /api/v1/reviews/mine). */
export type OwnReviewStatus = "pending" | "published" | "rejected";

export type OwnReviewCard = ReviewCardData & {
  status: OwnReviewStatus;
  rejectionReason: string | null;
};

/**
 * The signed-in user's own reviews, in every state, for their profile.
 *
 * Not the public feed: that is publication-gated, and reading it here is how a
 * just-submitted review vanished from its author's profile on refresh
 * (2026-09-18) — it is held for moderation, so the public read left it out.
 * Credentialed, so never cached (lib/api/client.ts), and the API decides whose
 * reviews they are from the token alone.
 */
export async function getMyReviews(token: string | null): Promise<OwnReviewCard[] | null> {
  if (!token) return null;
  try {
    const items = await apiFetch<(FeedItem & { status: OwnReviewStatus; rejection_reason: string | null })[]>(
      "/api/v1/reviews/mine?limit=48",
      { token },
    );
    return items.map((item) => ({
      ...toCard(item),
      status: item.status,
      rejectionReason: item.rejection_reason,
    }));
  } catch {
    return null;
  }
}

export type AuthorProfile = {
  id: string;
  name: string;
  username: string | null;
  avatarUrl: string | null;
  trust: string;
  trustStage: number;
  /** 0..100 (ADR-003), shown beside the level name. See lib/trust.ts. */
  trustScore: string | null;
  /** When the account was created, for the "Joined …" line. */
  joinedAt: string;
  /** Published reviews that carry proof. */
  verifiedReviewCount: number;
  /** Business Rules §17: public engagement figures. */
  peopleHelped: number;
  commentCount: number;
  interactsWithMost: ProfileInteraction[];
  mostInteractedBy: ProfileInteraction[];
  /** §9: a claimed seller account, said so readers know who they are hearing. */
  isClaimedSeller: boolean;
};

export type ProfileInteraction = {
  user_id: string;
  username: string | null;
  display_name: string | null;
  upvotes: number;
  downvotes: number;
  comments: number;
};

/** What `GET /users/public/{handle}` returns. Public fields only. */
type PublicProfile = {
  id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  trust_stage: number;
  trust_level_name: string;
  reputation_score: string;
  verified_review_count: number;
  review_count: number;
  created_at: string;
  people_helped?: number;
  comment_count?: number;
  interacts_with_most?: ProfileInteraction[];
  most_interacted_by?: ProfileInteraction[];
  is_claimed_seller?: boolean;
};

/**
 * A public reviewer profile: the reviewer's public identity plus their
 * published reviews.
 *
 * `handle` is a username or an id, because both are in circulation — the site
 * links reviewers by id and a person typing a profile URL types the @handle.
 *
 * BUG-030. This used to be built from the review feed alone, filtered by
 * `author_id`, and that was wrong twice over: `author_id` takes a UUID, so
 * `/u/ciel` could never resolve, and a reviewer with no published review has no
 * feed row at all — so an account that plainly exists answered "not found".
 * Identity now comes from `GET /users/public/{handle}`, which needs neither,
 * and the feed is fetched second with the id it resolves.
 *
 * Still returns null for a reviewer who does not exist, which is what the
 * route turns into a real 404. A reviewer who exists and has published nothing
 * is NOT null: they get their profile and an empty list, which is the truth.
 */
export async function getAuthorProfile(handle: string): Promise<{
  author: AuthorProfile;
  cards: ReviewCardData[];
} | null> {
  let profile: PublicProfile;
  try {
    profile = await apiFetch<PublicProfile>(
      `/api/v1/users/public/${encodeURIComponent(handle)}`,
      { revalidate: 60, tags: [REVIEW_LISTS] },
    );
  } catch {
    // 404 for an unknown handle, and anything else the API could not answer.
    // Either way there is no profile to show; the route calls notFound().
    return null;
  }

  let cards: ReviewCardData[] = [];
  try {
    const items = await apiFetch<CardItem[]>(
      `/api/v1/reviews/feed?${feedQuery({ author_id: profile.id }, { sort: "newest", limit: 48, view: "card" })}`,
      { revalidate: 60, tags: [REVIEW_LISTS] },
    );
    cards = items.map(toCard);
  } catch {
    // The identity resolved; a feed outage costs the reviews, not the page.
    cards = [];
  }

  return {
    author: {
      id: profile.id,
      name: profile.display_name || profile.username || "reviewer",
      username: profile.username,
      avatarUrl: profile.avatar_url,
      trust: profile.trust_level_name || `Stage ${profile.trust_stage}`,
      trustStage: profile.trust_stage,
      trustScore: profile.reputation_score ?? null,
      joinedAt: profile.created_at,
      verifiedReviewCount: profile.verified_review_count,
      peopleHelped: profile.people_helped ?? 0,
      commentCount: profile.comment_count ?? 0,
      interactsWithMost: profile.interacts_with_most ?? [],
      mostInteractedBy: profile.most_interacted_by ?? [],
      isClaimedSeller: Boolean(profile.is_claimed_seller),
    },
    cards,
  };
}

export async function getLandingReviews(): Promise<{
  featured: FeaturedData;
  cards: ReviewCardData[];
}> {
  try {
    const items = await apiFetch<CardItem[]>(
      `/api/v1/reviews/feed?${feedQuery({}, { sort: "wilson", limit: 6, view: "card" })}`,
      { revalidate: 60, tags: [REVIEW_LISTS] },
    );
    if (items?.length) {
      return { featured: toFeatured(items[0]), cards: items.map(toCard) };
    }
  } catch {
    // fall through to the curated samples
  }
  return { featured: SAMPLE_FEATURED, cards: READING_REVIEWS };
}

/** A feed row: enough signal to judge a review without opening it. */
export type FeedCardData = {
  id: string;
  title: string;
  product: string | null;
  category: string | null;
  /** The reviewer's photo when usable, else the product listing image. */
  imageUrl: string | null;
  imageHue: number;
  verdict: string;
  stars: number;
  verified: boolean;
  excerpt: string;
  author: string;
  authorId: string | null;
  username: string | null;
  trustLevel: string | null;
  trustStage: number;
  trustScore: string | null;
  helpful: string;
  comments: string;
  ageLabel: string;
  /** Raw counts and the viewer's own vote, for the card's vote bar (QA-027/028). */
  helpfulCount: number;
  unhelpfulCount: number;
  myVote: "up" | "down" | null;
};

/** First ~180 characters of the discussion, cut on a word. */
function excerptOf(text: string | null | undefined): string {
  const clean = (text ?? "").replace(/\s+/g, " ").trim();
  if (clean.length <= 180) return clean;
  const cut = clean.slice(0, 180);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 120 ? lastSpace : 180).trimEnd()}…`;
}

function toFeedCard(item: CardItem): FeedCardData {
  const name = authorName(item);
  return {
    id: item.review.id,
    title: item.review.title.trim(),
    product: item.product?.canonical_name ?? null,
    category: item.product?.category ?? null,
    // The reviewer's own photo is the point of the platform; without one the
    // gradient stands in. Never the product listing image (see reviewPhoto).
    imageUrl: reviewPhoto(item.review),
    imageHue: hueOf(name),
    verdict: item.review.verdict,
    stars: item.review.star_rating,
    verified: showsTrustBadge(item.review),
    excerpt: excerptOf(cardText(item)),
    author: name,
    authorId: item.author?.id ?? null,
    username: item.author?.username ?? null,
    trustLevel: item.author?.trust_level_name ?? null,
    trustStage: item.author?.trust_stage ?? 0,
    trustScore: item.author?.reputation_score ?? null,
    helpful: compact(item.review.helpful_votes ?? 0),
    comments: compact(item.comment_count ?? 0),
    ageLabel: ageLabel(item.review.created_at),
    helpfulCount: item.review.helpful_votes ?? 0,
    unhelpfulCount: item.review.unhelpful_votes ?? 0,
    myVote: item.review.my_vote ?? null,
  };
}

type ReviewPageOptions = FeedFilters & {
  sort?: FeedPage["sort"];
  limit?: number;
  offset?: number;
  mode?: FeedPage["mode"];
  /** The signed-in reader's session, for their own votes (and "For You" ranking, read uncached). */
  token?: string | null;
};

/**
 * A page of review cards and the filters' total in one call
 * (GET /reviews/feed/page), for the search's Reviews tab and the Feed.
 *
 * They used to ask twice per render, the list and then its count, and both
 * missed the cache together. The total now rides on the page's own query.
 * Signed out it is one cached read (60 seconds, `review-lists`); with a token
 * it is uncached, because the rows carry the reader's own votes.
 *
 * `layout` picks the card each page draws. null means the API did not answer.
 */
export async function getReviewPage(
  opts: ReviewPageOptions & { layout: "feed" },
): Promise<{ cards: FeedCardData[]; total: number } | null>;
export async function getReviewPage(
  opts: ReviewPageOptions & { layout?: "search" },
): Promise<{ cards: ReviewCardData[]; total: number } | null>;
export async function getReviewPage(
  opts: ReviewPageOptions & { layout?: "search" | "feed" },
): Promise<{ cards: (ReviewCardData | FeedCardData)[]; total: number } | null> {
  const query = feedQuery(opts, {
    sort: opts.sort ?? "wilson",
    limit: opts.limit ?? 24,
    offset: opts.offset,
    mode: opts.mode,
  });
  try {
    // "For You" ranks by the reader's own interests, so it is personal and
    // read with the token, uncached. Every other page is the same for everyone
    // but its votes: read it from the shared cache and lay the votes on top.
    const personal = opts.token && opts.mode === "for-you";
    const page = await apiFetch<{ items: CardItem[]; total: number }>(
      `/api/v1/reviews/feed/page?${query}`,
      personal ? { token: opts.token } : { revalidate: 60, tags: [REVIEW_LISTS] },
    );
    const items = opts.token && !personal ? await withMyVotes(page.items, opts.token) : page.items;
    const cards = opts.layout === "feed" ? items.map(toFeedCard) : items.map(toCard);
    return { cards, total: page.total };
  } catch {
    return null;
  }
}

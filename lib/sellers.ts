import "server-only";

import { sellerFilterParams, type SellerFilters } from "./search-filter-params";
import { apiFetch } from "./api/client";
import { ApiError } from "./api/errors";
import type { QAAuthor } from "./qa";
import { getSessionToken } from "./session";
import type { SellerPlatform } from "@/components/sellers/seller-model";

export type SellerClaimStatus = "unclaimed" | "pending" | "claimed" | "rejected";

export type Seller = {
  id: string;
  display_name: string;
  platform: SellerPlatform;
  store_url: string | null;
  claim_status: SellerClaimStatus;
  /** Visible reviews only; a removed one no longer counts. */
  review_count: number;
  /** Null until someone has rated the store. */
  overall_average: number | null;
  /** Store questions with at least one answer (QA-052). */
  answered_question_count?: number;
  created_at: string;
};

export type SellerSummary = {
  review_count: number;
  accuracy_rate: number | null;
  order_completeness_rate: number | null;
  recommend_rate: number | null;
  customer_service_average: number | null;
  packaging_quality_average: number | null;
  overall_average: number | null;
  /** "1".."5" -> count. */
  rating_distribution: Record<string, number>;
};

export type SellerDetail = Seller & {
  summary: SellerSummary;
  /** Someone's claim on the store is waiting for an administrator (MQA-012); never whose. */
  claim_under_review?: boolean;
};

export type SellerReview = {
  id: string;
  seller_id: string;
  product_id: string | null;
  title: string | null;
  accuracy: boolean;
  order_completeness: boolean;
  customer_service: number;
  packaging_quality: number;
  overall_rating: number;
  would_recommend: boolean;
  comment: string | null;
  photo_urls: string[];
  reviewer: QAAuthor | null;
  created_at: string;
  /** Business Rules §9: the claimed store's one public response. */
  seller_response?: string | null;
  seller_response_at?: string | null;
  /** Set when the store edited its response (0082): buyers see "Edited". */
  seller_response_edited_at?: string | null;
  /** §10: the buyer gave an order ID. The ID itself is never public. */
  order_id_provided?: boolean;
  /** QA-043: helpfulness votes (moving no rating) and the viewer's own. */
  helpful_votes?: number;
  unhelpful_votes?: number;
  my_vote?: "up" | "down" | null;
  /** QA-043: members' replies, oldest first. */
  replies?: { id: string; body: string; created_at: string; author: QAAuthor | null }[];
  reply_count?: number;
};

export type SellerClaim = {
  id: string;
  seller_id: string;
  seller_display_name: string | null;
  status: SellerClaimStatus;
  evidence: string | null;
  decision_note: string | null;
  created_at: string;
  decided_at: string | null;
  /** Business Rules §9: the DTI/SEC registration the claim rests on. */
  registration_kind?: "dti" | "sec" | null;
  registration_number?: string | null;
  registered_business_name?: string | null;
  marketplace_shop_name?: string | null;
  /** Does the shop name given match this store's name? */
  shop_name_matches?: boolean | null;
};

/** A seller's appeal against one review of their store (§10). Admin only. */
export type SellerAppeal = {
  id: string;
  seller_review_id: string;
  seller_id: string;
  reason: string;
  status: "open" | "substantiation_requested" | "upheld" | "dismissed";
  substantiation_request: string | null;
  substantiation_requested_at: string | null;
  substantiation_response: string | null;
  substantiated_at: string | null;
  decision_note: string | null;
  decided_at: string | null;
  created_at: string;
  /** The reviewer's self-reported order ID: admin context for this appeal only. */
  order_id: string | null;
};

/** Store search for the Sellers tab. Public. Null means unreachable. */
export async function searchSellers(
  q: string,
  limit = 24,
  /** The Sellers tab's filters and order (QA-052; Sheet/Filter sellers 8462:36591). */
  options: Omit<SellerFilters, "q"> & { sort?: "ranked" | "reviews" | "name" } = {},
): Promise<Seller[] | null> {
  try {
    const params = sellerFilterParams({ ...options, q });
    params.set("limit", String(limit));
    // "ranked" is the API's default (MQA-033); the other orders are asked for.
    if (options.sort && options.sort !== "ranked") params.set("sort", options.sort);
    return await apiFetch<Seller[]>(`/api/v1/sellers?${params}`, { revalidate: 60 });
  } catch {
    return null;
  }
}

/**
 * One store with its summary. Short-lived cache: a buyer who has just rated
 * the store lands here from the composer, and a minute-old summary would read
 * as if their rating had not counted.
 */
/**
 * One store. A signed-in read carries the token, which apiFetch never caches:
 * the store owner who just responded, flagged a review or rated a store must
 * see it on the page the router refreshes to, not a 5-second-old copy
 * (full-system QA, D6 — the same class of defect as QA-044). Signed-out
 * readers keep the short shared cache.
 */
export async function getSeller(id: string, token?: string | null): Promise<SellerDetail | null> {
  try {
    return await apiFetch<SellerDetail>(`/api/v1/sellers/${encodeURIComponent(id)}`, {
      token,
      ...(token ? {} : { revalidate: 5 }),
    });
  } catch {
    return null;
  }
}

/** A store's reviews; signed-in reads are uncached for the reason on getSeller. */
export async function getSellerReviews(
  id: string,
  limit = 30,
  token?: string | null,
): Promise<SellerReview[] | null> {
  try {
    return await apiFetch<SellerReview[]>(
      `/api/v1/sellers/${encodeURIComponent(id)}/reviews?limit=${limit}`,
      { token, ...(token ? {} : { revalidate: 5 }) },
    );
  } catch {
    return null;
  }
}

/**
 * Every review of a store, newest first, 100 a page (the API's page size), up
 * to `max`. The Seller console filters and sorts on the client, so it needs
 * the whole list rather than the newest page. `capped` says when `max` cut it.
 */
export async function getAllSellerReviews(
  id: string,
  token: string | null,
  max = 1000,
): Promise<{ reviews: SellerReview[]; capped: boolean } | null> {
  const PAGE = 100;
  const reviews: SellerReview[] = [];
  try {
    while (reviews.length < max) {
      const page = await apiFetch<SellerReview[]>(
        `/api/v1/sellers/${encodeURIComponent(id)}/reviews?limit=${PAGE}&offset=${reviews.length}`,
        { token },
      );
      reviews.push(...page);
      if (page.length < PAGE) return { reviews, capped: false };
    }
    return { reviews: reviews.slice(0, max), capped: true };
  } catch {
    return null;
  }
}

export type MonthCount = { month: string; count: number };

export type DashboardReviewRow = {
  id: string;
  created_at: string;
  reviewer: string | null;
  title: string | null;
  excerpt: string | null;
  overall_rating: number;
  helpful_votes: number;
  unhelpful_votes: number;
  reply_count: number;
  /** helpful votes + replies (docs/SELLER_DASHBOARD.md). */
  engagement: number;
  has_store_response: boolean;
  /** The store's "suspected fake" flag, if raised. */
  appeal_status: string | null;
};

export type SellerDashboardAnalytics = {
  review_count: number;
  median_rating: number | null;
  rating_distribution: Record<string, number>;
  replies_total: number;
  helpful_votes_total: number;
  questions_total: number;
  questions_answered_by_store: number;
  responses_total: number;
  response_rate: number | null;
  appeals_open: number;
  support_open: number;
  months: { month: string; reviews: number; replies: number; questions: number }[];
  /** Visible reviews still without the store's response (all of them, not the capped list). */
  reviews_awaiting_response?: number;
  most_engaged: DashboardReviewRow | null;
  most_discussed: DashboardReviewRow | null;
};

export type SellerDashboard = {
  seller: SellerDetail;
  /** Visible reviews per Manila month, oldest first, zero-filled. */
  monthly_volume: MonthCount[];
  /** Store questions with no answer from the store yet. */
  unanswered_questions: number;
  /** Oldest first, at most 20. */
  waiting_questions: { id: string; body: string; created_at: string }[];
  /** Owner decision 2026-09-28 (backend/app/services/seller_dashboard.py). */
  analytics?: SellerDashboardAnalytics | null;
  /** Newest first, at most 30. */
  reviews?: DashboardReviewRow[];
  /** Still without the store's response, OLDEST first, at most 20 (total: analytics.reviews_awaiting_response). */
  waiting_reviews?: DashboardReviewRow[];
  recent_activity?: { kind: string; at: string; label: string; link: string | null }[];
};

/**
 * Stores the signed-in account runs (approved claims only). Empty on any
 * failure: it only decides whether a dashboard link is offered, and a missing
 * link is the safe way for that to fail.
 */
export async function getMyStores(): Promise<Seller[]> {
  try {
    return await apiFetch<Seller[]>("/api/v1/sellers/mine", { token: await getSessionToken() });
  } catch {
    return [];
  }
}

export type DashboardResult =
  | { ok: true; dashboard: SellerDashboard }
  | { ok: false; reason: "not_owner" | "not_found" | "unavailable" };

/** The owner's dashboard, or why it cannot be shown. Branches on `code`, not prose. */
export async function getSellerDashboard(id: string): Promise<DashboardResult> {
  try {
    const dashboard = await apiFetch<SellerDashboard>(
      `/api/v1/sellers/${encodeURIComponent(id)}/dashboard`,
      { token: await getSessionToken() },
    );
    return { ok: true, dashboard };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === "not_store_owner") return { ok: false, reason: "not_owner" };
      if (error.status === 404 || error.status === 422) return { ok: false, reason: "not_found" };
    }
    return { ok: false, reason: "unavailable" };
  }
}

type SellerSchemas = import("@/lib/api-types").components["schemas"];
/** The admin Sellers screen's rows (Figma 7992:11327 / 7992:11823), as generated. */
export type AdminSellerClaim = SellerSchemas["SellerClaimOut"];
export type AdminSellerAppeal = SellerSchemas["SellerAppealOut"];

/**
 * Every row of a staff list that pages by limit/offset, 200 a read. The admin
 * Sellers screen filters and pages its tables itself, so it needs them all:
 * reading only the first 200 left every later claim or appeal out of reach.
 * Bounded at 25 reads (5,000 rows) so a runaway list cannot hang the page.
 */
async function everyPage<T>(path: string): Promise<T[]> {
  const token = await getSessionToken();
  const rows: T[] = [];
  for (let offset = 0; offset < 5000; offset += 200) {
    const sep = path.includes("?") ? "&" : "?";
    const page = await apiFetch<T[]>(`${path}${sep}limit=200&offset=${offset}`, { token });
    rows.push(...page);
    if (page.length < 200) break;
  }
  return rows;
}

/** Pending claims with claimant and store context (staff), every one of them. */
export async function getAdminSellerClaims(): Promise<AdminSellerClaim[] | null> {
  try {
    return await everyPage<AdminSellerClaim>("/api/v1/admin/seller-claims");
  } catch {
    return null;
  }
}

/** Open appeals with the appealed review and reviewer (staff); `decided`: upheld and dismissed ones. */
export async function getAdminSellerAppeals(decided = false): Promise<AdminSellerAppeal[] | null> {
  try {
    return await everyPage<AdminSellerAppeal>(`/api/v1/admin/seller-review-appeals${decided ? "?decided=true" : ""}`);
  } catch {
    return null;
  }
}

/** Stores' product link requests (0077, staff). */
export type AdminStoreProduct = import("@/lib/api-types").components["schemas"]["AdminStoreProductOut"];
export async function getAdminStoreProducts(): Promise<AdminStoreProduct[] | null> {
  try {
    return await apiFetch<AdminStoreProduct[]>("/api/v1/admin/store-products?status=pending", { token: await getSessionToken() });
  } catch {
    return null;
  }
}

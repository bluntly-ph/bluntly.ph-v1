import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

/**
 * Product-side reads for FR-2: the community price panel and comparison.
 *
 * Both return `null` on failure rather than an empty shape, for the same
 * reason the review reads do: "we could not reach the server" and "there is no
 * data yet" are different answers, and only one of them is the reader's to act
 * on. The price panel has a third state on top of that — *enough* data — which
 * is a property of the data itself, not of the request.
 */

export type PricePanel = {
  product_id: string;
  /** False until ≥3 INDEPENDENT submitters have contributed (FR-2). */
  sufficient: boolean;
  observation_count: number;
  independent_count: number;
  required_independent: number;
  currency: string;
  /** Null whenever `sufficient` is false — the API publishes no prices below the threshold. */
  low: string | null;
  high: string | null;
  median: string | null;
  latest_observed_at: string | null;
  platforms: string[];
  /** Reports waiting for an administrator. Counted, never priced. */
  pending_count: number;
  /** Business Rules §16: one line per marketplace, never blended. */
  series?: Record<string, { observed_at: string; price: string }[]>;
};

export type PriceObservationQueueItem = {
  id: string;
  product_id: string;
  product_name: string | null;
  platform: "shopee" | "lazada" | "amazon" | "other";
  price: string;
  variant: string | null;
  observed_at: string;
  source: "manual" | "review";
  status: "pending" | "approved" | "rejected";
  submitter_username: string | null;
  decision_note: string | null;
  /** Why it waits (§16): far outside the usual range, or no range to judge by yet. */
  hold_reason?: "outlier" | "no_baseline" | string | null;
  created_at: string;
  /** The product's usual price on this marketplace (median of its approved
   *  recent prices) and how many there are; null when there are none. */
  usual_median?: string | null;
  usual_count?: number;
  /** The viewer reported it, so the API refuses their decision. */
  reported_by_viewer?: boolean;
};

export type ComparisonEntry = {
  product: {
    id: string;
    canonical_name: string | null;
    category: string | null;
    image_url: string | null;
    review_count: number;
    avg_rating: string | null;
  };
  price: PricePanel;
  review_count: number;
  avg_rating: string | null;
  trust_score: string | null;
  verified_review_count: number;
};

export type Comparison = {
  entries: ComparisonEntry[];
  not_found: string[];
};

export async function getPricePanel(productId: string): Promise<PricePanel | null> {
  try {
    return await apiFetch<PricePanel>(
      `/api/v1/products/${encodeURIComponent(productId)}/prices`,
      { revalidate: 60 },
    );
  } catch {
    return null;
  }
}

/**
 * Business Rules §4: how many of this product's review threads were deleted by
 * their authors after they had paid out. Shown only as a count on the product
 * — never which review — so a pattern of post-payout deletions stays visible.
 * Zero on any failure: the note is context, not a gate.
 */
export async function getRemovedAfterPayoutCount(productId: string): Promise<number> {
  try {
    const product = await apiFetch<{ removed_after_payout_count?: number }>(
      `/api/v1/products/${encodeURIComponent(productId)}`,
      { revalidate: 300 },
    );
    return product.removed_after_payout_count ?? 0;
  } catch {
    return 0;
  }
}

/** 2–4 products, side by side. Returns null on transport failure only. */
export async function getComparison(ids: string[]): Promise<Comparison | null> {
  if (ids.length < 2 || ids.length > 4) return null;
  try {
    return await apiFetch<Comparison>(
      `/api/v1/products/compare?ids=${ids.map(encodeURIComponent).join(",")}`,
      { revalidate: 60 },
    );
  } catch {
    return null;
  }
}

/** "₱1,200" — prices arrive as string decimals and must stay that way until display. */
export function peso(value: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `₱${n.toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;
}

/** Administrator only: prices waiting for a decision. Per-user, so never cached. */
/**
 * One page of the prices waiting for a decision, with the totals (MQA-043):
 * `total` matches the filters, `waiting` is every pending price. The list and
 * its count are asked with the same filters, so the pages add up to the total.
 * null when the API did not answer.
 */
export async function getPriceObservationPage(
  filters: URLSearchParams,
  page: number,
  size: number,
): Promise<{ items: PriceObservationQueueItem[]; total: number; waiting: number } | null> {
  const token = await getSessionToken();
  const list = new URLSearchParams(filters);
  list.set("limit", String(size));
  if (page > 1) list.set("offset", String((page - 1) * size));
  const counted = new URLSearchParams(filters);
  counted.delete("sort");
  try {
    const [items, total, waiting] = await Promise.all([
      apiFetch<PriceObservationQueueItem[]>(`/api/v1/admin/price-observations?${list}`, { token }),
      apiFetch<{ total: number }>(`/api/v1/admin/price-observations/count?${counted}`, { token }),
      counted.toString()
        ? apiFetch<{ total: number }>("/api/v1/admin/price-observations/count", { token })
        : null,
    ]);
    return { items, total: total.total, waiting: waiting?.total ?? total.total };
  } catch {
    return null;
  }
}

/**
 * One product's identity, for opening the review composer on it
 * (`/reviews/new?product=`, from a request's "Answer with a review").
 * null when it does not exist or cannot be reached; the composer then asks.
 */
export async function getProductSummary(
  productId: string,
): Promise<{ id: string; canonical_name: string | null; category: string | null; image_url: string | null } | null> {
  try {
    const p = await apiFetch<{ id: string; canonical_name: string | null; category: string | null; image_url?: string | null }>(
      `/api/v1/products/${encodeURIComponent(productId)}`,
    );
    return { id: p.id, canonical_name: p.canonical_name, category: p.category, image_url: p.image_url ?? null };
  } catch {
    return null;
  }
}

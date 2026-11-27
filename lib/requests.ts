import "server-only";

import { apiFetch } from "./api/client";

/** A community review request (GET /api/v1/requests). */
export type RequestItem = {
  id: string;
  title: string;
  details: string;
  source_url: string | null;
  upvote_count: number;
  /**
   * Whether the requesting viewer has up-voted this (BUG-026). Only populated
   * when the call carries a token; false for anonymous reads.
   */
  my_upvote: boolean;
  status: string;
  created_at: string;
  /**
   * The product it is about. Every new request names one (dev/QA sync
   * 2026-09-29); an older request can still carry none.
   */
  product_id?: string | null;
  product_name?: string | null;
  /** How many reviews answer it: reviews of its product written after it. */
  answer_count?: number;
  /** The asker's Best Answer, once picked; the request then leaves the board. */
  fulfilled_by_review_id?: string | null;
  fulfilled_at?: string | null;
  requester_id?: string;
};

/** One answer to a request: a public review of its product (GET /requests/{id}/answers). */
export type RequestAnswer = {
  review_id: string;
  title: string | null;
  excerpt: string;
  star_rating: number;
  verdict: string;
  author_username: string | null;
  author_display_name: string | null;
  created_at: string;
  is_best: boolean;
};

/**
 * Open requests, newest or most-wanted.
 *
 * Readable without a token; pass the viewer's to get `my_upvote` filled in, so
 * the board renders their existing up-votes as pressed instead of resetting on
 * every load.
 */
export async function getRequests(
  sort: "demand" | "newest" = "demand",
  token?: string | null,
): Promise<RequestItem[] | null> {
  try {
    return await apiFetch<RequestItem[]>(
      `/api/v1/requests?status=open&sort=${sort}&limit=30`,
      { token: token ?? undefined },
    );
  } catch {
    // null, not [] — an unreachable API is not an empty board, and the
    // caller has to be able to tell those apart to say so honestly.
    return null;
  }
}

/**
 * One request, in any state but removed: its own page is where it lives for
 * good once it leaves the board (dev/QA sync 2026-09-29). null when it does
 * not exist or cannot be reached.
 */
export async function getRequest(id: string, token?: string | null): Promise<RequestItem | null> {
  try {
    return await apiFetch<RequestItem>(`/api/v1/requests/${encodeURIComponent(id)}`, {
      token: token ?? undefined,
    });
  } catch {
    return null;
  }
}

/** Every review that answers a request, the Best Answer first once picked. */
export async function getRequestAnswers(id: string): Promise<RequestAnswer[] | null> {
  try {
    return await apiFetch<RequestAnswer[]>(`/api/v1/requests/${encodeURIComponent(id)}/answers`);
  } catch {
    return null;
  }
}

/** Requests in any state whose question or product matches `q` (search). */
export async function searchRequests(q: string): Promise<RequestItem[]> {
  const term = q.trim();
  if (!term) return [];
  try {
    return await apiFetch<RequestItem[]>(
      `/api/v1/requests?q=${encodeURIComponent(term.slice(0, 100))}&sort=demand&limit=10`,
    );
  } catch {
    return [];
  }
}

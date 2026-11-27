import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

/**
 * The Super Admin's 2.5-star routing queue (owner decision A;
 * backend/app/api/v1/routes/super_admin.py). `null` when the API did not
 * answer — an outage is not an empty queue.
 */

export type SpecialRoutingItem = {
  review_id: string;
  review_ref: string | null;
  title: string;
  product_name: string | null;
  author: string | null;
  latest_entry_id: string;
  verdict: "yes_absolutely" | "it_depends" | "hard_pass";
  stars: string;
  photo_provided: boolean;
  status: string;
  created_at: string;
  escalated_at: string | null;
  author_name?: string | null;
  excerpt?: string | null;
  product_image_url?: string | null;
  approval_note?: string | null;
};

export type SpecialRoutingDecision = {
  at: string;
  review_id: string | null;
  review_ref: string | null;
  destination: "honesty_fund" | "platform" | null;
  previous_status: string | null;
  actor_staff_ref: string | null;
  actor_name?: string | null;
};

async function read<T>(path: string): Promise<T | null> {
  const token = await getSessionToken();
  if (!token) return null;
  try {
    return await apiFetch<T>(path, { token });
  } catch {
    return null;
  }
}

export function getSpecialRoutingQueue() {
  return read<SpecialRoutingItem[]>("/api/v1/admin/super/special-routing");
}

export function getSpecialRoutingHistory() {
  return read<SpecialRoutingDecision[]>("/api/v1/admin/super/special-routing/history?limit=50");
}

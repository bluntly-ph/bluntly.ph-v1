import "server-only";

import { apiFetch } from "./api/client";
import { ApiError } from "./api/errors";
import { getSessionToken } from "./session";

/**
 * Seller support requests (owner decision 2026-09-28;
 * backend/app/api/v1/routes/support.py). Per-user data: never cached.
 *
 * The seller's view never carries the staff-only internal note — the API's
 * seller schema has no field for it — so nothing here could show one.
 */

export type SupportCategory =
  | "report_review"
  | "takedown_investigation"
  | "fake_review_dispute"
  | "account_claim"
  | "listing_product"
  | "store_change"
  | "general";

export type SupportStatus = "open" | "in_review" | "waiting_for_seller" | "resolved" | "rejected";

export type SupportRequest = {
  id: string;
  reference: string;
  /** The Messages thread this request was moved from: its one history (MQA-021). */
  conversation_id?: string | null;
  seller_id: string;
  seller_name: string | null;
  category: SupportCategory;
  subject: string;
  message: string;
  related_seller_review_id: string | null;
  related_review_id: string | null;
  related_product_id: string | null;
  status: SupportStatus;
  admin_response: string | null;
  admin_responded_at: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
};

export type SupportResult<T> =
  | { ok: true; data: T }
  | { ok: false; reason: "forbidden" | "not_found" | "unavailable" };

async function read<T>(path: string): Promise<SupportResult<T>> {
  try {
    return { ok: true, data: await apiFetch<T>(path, { token: await getSessionToken() }) };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401 || error.status === 403) return { ok: false, reason: "forbidden" };
      if (error.status === 404 || error.status === 422) return { ok: false, reason: "not_found" };
    }
    return { ok: false, reason: "unavailable" };
  }
}

export function getStoreSupportRequests(sellerId: string) {
  return read<SupportRequest[]>(`/api/v1/sellers/${encodeURIComponent(sellerId)}/support-requests`);
}

export function getStoreSupportRequest(sellerId: string, requestId: string) {
  return read<SupportRequest>(
    `/api/v1/sellers/${encodeURIComponent(sellerId)}/support-requests/${encodeURIComponent(requestId)}`,
  );
}

/** The staff view: who is handling it, and the note the seller never sees. */
export type AdminSupportRequest = SupportRequest & {
  created_by: string | null;
  assigned_admin: string | null;
  assigned_admin_id: string | null;
  internal_note: string | null;
};

/**
 * The staff support queue, oldest first. `null` when the API is unreachable —
 * an outage is not an empty queue, and the tab says which it is.
 */
export async function getAdminSupportRequests(): Promise<AdminSupportRequest[] | null> {
  const token = await getSessionToken();
  if (!token) return null;
  try {
    return await apiFetch<AdminSupportRequest[]>("/api/v1/admin/support-requests?limit=200", { token });
  } catch {
    return null;
  }
}

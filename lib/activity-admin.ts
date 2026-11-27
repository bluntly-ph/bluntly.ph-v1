import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

type Schemas = import("@/lib/api-types").components["schemas"];
/** The Activity log's reads (Figma Screen/Admin/ActivityLog 8074:16245), as generated. */
export type ActivityEntry = Schemas["ActivityRow"];
export type ActivitySummary = Schemas["ActivitySummaryOut"];
export type ActivityFilters = { actor?: string; action?: string; target?: string; range?: string; q?: string };

export function activityQuery(f: ActivityFilters): URLSearchParams {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) qs.set(k, v);
  return qs;
}

/** Staff only; never cached. Null when unreachable. */
export async function getActivityEntries(f: ActivityFilters, limit: number): Promise<{ rows: ActivityEntry[]; total: number } | null> {
  const qs = activityQuery(f);
  qs.set("limit", String(limit));
  try {
    return await apiFetch<{ rows: ActivityEntry[]; total: number }>(`/api/v1/admin/activity?${qs}`, { token: await getSessionToken() });
  } catch {
    return null;
  }
}

export async function getActivitySummary(): Promise<ActivitySummary | null> {
  try {
    return await apiFetch<ActivitySummary>("/api/v1/admin/activity/summary", { token: await getSessionToken() });
  } catch {
    return null;
  }
}

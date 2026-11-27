import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

export type AnalyticsSummary = import("@/lib/api-types").components["schemas"]["AnalyticsSummaryOut"];

/** GET /admin/analytics/summary (Figma Screen/Admin/Analytics 8071:16115). Staff only. */
export async function getAnalyticsSummary(range: string): Promise<AnalyticsSummary | null> {
  try {
    return await apiFetch<AnalyticsSummary>(`/api/v1/admin/analytics/summary?range=${range}`, { token: await getSessionToken() });
  } catch {
    return null;
  }
}

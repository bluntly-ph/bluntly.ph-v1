import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

/** GET /admin/settings (Figma Screen/Admin/Settings 8076:16388), as generated. */
export type AdminSettings = import("@/lib/api-types").components["schemas"]["SettingsOut"];

export async function getAdminSettings(): Promise<AdminSettings | null> {
  try {
    return await apiFetch<AdminSettings>("/api/v1/admin/settings", { token: await getSessionToken() });
  } catch {
    return null;
  }
}

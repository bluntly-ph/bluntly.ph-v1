import "server-only";

import { cache } from "react";

import { apiFetch } from "./api/client";
import { ApiError } from "./api/errors";
import { getSessionToken } from "./session";

/**
 * The Seller console's reads (Figma Screen/Seller/*). Every call is the signed-in
 * owner's own; the API re-derives ownership on each one (403 not_store_owner).
 * `cache` dedupes the layout's and the page's identical reads in one request.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
export type ConsoleDashboard = Schemas["SellerDashboardOut"];
export type ConsoleClaim = Schemas["SellerClaimOut"];
export type ConsoleAppeal = Schemas["SellerAppealOut"];
export type ConsoleStore = Schemas["SellerOut"];
export type ConsoleQuestion = Schemas["StoreQuestionOut"];
export type ConsolePeriod = NonNullable<ConsoleDashboard["period"]>;
export type StoreProducts = Schemas["StoreProductsOut"];
export type StoreProductAnalytics = Schemas["StoreProductAnalyticsOut"];
export type StoreInsights = Schemas["StoreInsightsOut"];
export type StoreProfile = Schemas["StoreProfileOut"];
export type NotificationPrefs = Schemas["NotificationPrefs"];

export const PERIODS: { key: ConsolePeriod; label: string }[] = [
  { key: "30d", label: "Last 30 days" },
  { key: "3m", label: "Last 3 months" },
  { key: "6m", label: "Last 6 months" },
  { key: "12m", label: "Last 12 months" },
  { key: "all", label: "All time" },
];

export function parsePeriod(raw: string | string[] | undefined): ConsolePeriod {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return PERIODS.some((p) => p.key === v) ? (v as ConsolePeriod) : "6m";
}

export type ConsoleDashboardResult =
  | { ok: true; dashboard: ConsoleDashboard }
  | { ok: false; reason: "not_owner" | "not_found" | "unavailable" };

export const getConsoleDashboard = cache(async (storeId: string, period: ConsolePeriod = "6m"): Promise<ConsoleDashboardResult> => {
  try {
    const dashboard = await apiFetch<ConsoleDashboard>(
      `/api/v1/sellers/${encodeURIComponent(storeId)}/dashboard?period=${period}`,
      { token: await getSessionToken() },
    );
    return { ok: true, dashboard };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === "not_store_owner" || error.status === 403) return { ok: false, reason: "not_owner" };
      if (error.status === 404 || error.status === 422) return { ok: false, reason: "not_found" };
    }
    return { ok: false, reason: "unavailable" };
  }
});

/** Which store notices reach the account (Settings). Null on failure: the switches then don't draw. */
export const getNotificationPrefs = cache(async (): Promise<NotificationPrefs | null> => {
  try {
    return await apiFetch<NotificationPrefs>("/api/v1/users/me/notification-prefs", { token: await getSessionToken() });
  } catch {
    return null;
  }
});

/** Stores this account runs (approved claims). Empty on failure. */
export const getConsoleStores = cache(async (): Promise<ConsoleStore[]> => {
  try {
    return await apiFetch<ConsoleStore[]>("/api/v1/sellers/mine", { token: await getSessionToken() });
  } catch {
    return [];
  }
});

/** The account's own claims, newest first. Empty on failure. */
export const getMyClaims = cache(async (): Promise<ConsoleClaim[]> => {
  try {
    return await apiFetch<ConsoleClaim[]>("/api/v1/sellers/claims/mine", { token: await getSessionToken() });
  } catch {
    return [];
  }
});

export type StoreChange = Schemas["StoreChangeOut"];

/** The store's change requests and their status (MQA-025); [] when unreadable. */
export async function getStoreChanges(storeId: string): Promise<StoreChange[]> {
  try {
    return await apiFetch<StoreChange[]>(`/api/v1/sellers/${encodeURIComponent(storeId)}/change-requests`, {
      token: await getSessionToken(),
    });
  } catch {
    return [];
  }
}

/** The flags the store's owner raised, or null when they could not be read. */
export const getStoreAppeals = cache(async (storeId: string): Promise<ConsoleAppeal[] | null> => {
  try {
    return await apiFetch<ConsoleAppeal[]>(`/api/v1/sellers/${encodeURIComponent(storeId)}/appeals`, {
      token: await getSessionToken(),
    });
  } catch {
    return null;
  }
});

/** The store's questions with its own answers, or null when they could not be read. */
export const getStoreQuestions = cache(async (storeId: string): Promise<ConsoleQuestion[] | null> => {
  try {
    return await apiFetch<ConsoleQuestion[]>(`/api/v1/sellers/${encodeURIComponent(storeId)}/questions?limit=200`, {
      token: await getSessionToken(),
    });
  } catch {
    return null;
  }
});

/** The store's product links with their figures (0077), or null when unreadable. */
export const getStoreProducts = cache(async (storeId: string): Promise<StoreProducts | null> => {
  try {
    return await apiFetch<StoreProducts>(`/api/v1/sellers/${encodeURIComponent(storeId)}/products`, {
      token: await getSessionToken(),
    });
  } catch {
    return null;
  }
});

/** A linked product's analytics; "not_linked" until a moderator approves the link. */
export const getStoreProductAnalytics = cache(
  async (storeId: string, productId: string): Promise<StoreProductAnalytics | "not_linked" | null> => {
    try {
      return await apiFetch<StoreProductAnalytics>(
        `/api/v1/sellers/${encodeURIComponent(storeId)}/products/${encodeURIComponent(productId)}/analytics`,
        { token: await getSessionToken() },
      );
    } catch (error) {
      if (error instanceof ApiError && (error.status === 404 || error.status === 422)) return "not_linked";
      return null;
    }
  },
);

/** Store review figures by month (Screen/Seller/Insights), or null when unreadable. */
export const getStoreInsights = cache(async (storeId: string, period: ConsolePeriod = "6m"): Promise<StoreInsights | null> => {
  try {
    return await apiFetch<StoreInsights>(
      `/api/v1/sellers/${encodeURIComponent(storeId)}/insights?period=${encodeURIComponent(period)}`,
      { token: await getSessionToken() },
    );
  } catch {
    return null;
  }
});

/** The store and how its claim was verified (Screen/Seller/StoreProfile), or null. */
export const getStoreProfile = cache(async (storeId: string): Promise<StoreProfile | null> => {
  try {
    return await apiFetch<StoreProfile>(`/api/v1/sellers/${encodeURIComponent(storeId)}/profile`, {
      token: await getSessionToken(),
    });
  } catch {
    return null;
  }
});

/** The signed-in account's unread notifications (the bell's dot). 0 on failure. */
export const getUnreadCount = cache(async (): Promise<number> => {
  try {
    const r = await apiFetch<{ count: number }>("/api/v1/notifications/unread-count", { token: await getSessionToken() });
    return r.count;
  } catch {
    return 0;
  }
});

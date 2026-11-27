import "server-only";

import { apiFetch } from "./api/client";
import { getSessionToken } from "./session";

type Schemas = import("@/lib/api-types").components["schemas"];
/** The admin Affiliate screen's reads (Figma 8015:12542 / 8015:13183 / 8015:13726), as generated. */
export type AffiliateTransactionPage = Schemas["AffiliateTransactionPageOut"];
export type AffiliateTransaction = Schemas["AffiliateTransactionOut"];
export type AffiliateMonth = Schemas["AffiliateMonthOut"];
export type AffiliateImport = Schemas["AffiliateImportOut"];

export type TransactionQuery = {
  q?: string;
  platform?: string;
  status?: string;
  settlement?: string;
  attribution?: string;
  updated?: string;
  sort?: string;
  limit: number;
  offset: number;
};

/** Staff only; per-user data, so never cached. Null when unreachable. */
export async function getAffiliateTransactions(query: TransactionQuery): Promise<AffiliateTransactionPage | null> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== "") qs.set(k, String(v));
  try {
    return await apiFetch<AffiliateTransactionPage>(`/api/v1/admin/affiliate/transactions?${qs}`, {
      token: await getSessionToken(),
    });
  } catch {
    return null;
  }
}

export async function getAffiliateMonths(): Promise<AffiliateMonth[] | null> {
  try {
    return await apiFetch<AffiliateMonth[]>("/api/v1/admin/affiliate/months", { token: await getSessionToken() });
  } catch {
    return null;
  }
}

export async function getAffiliateImports(): Promise<AffiliateImport[] | null> {
  try {
    return await apiFetch<AffiliateImport[]>("/api/v1/admin/affiliate/imports?limit=200", {
      token: await getSessionToken(),
    });
  } catch {
    return null;
  }
}

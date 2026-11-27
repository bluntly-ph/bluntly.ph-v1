import type { Metadata } from "next";

import { AffiliateScreen, type AffiliateTab } from "@/components/admin/affiliate/AffiliateScreen";
import { AwaitingLinks } from "@/components/admin/affiliate/AwaitingLinks";
import { getAffiliateImports, getAffiliateMonths, getAffiliateTransactions } from "@/lib/affiliate-admin";
import { getAdminOverview, getAwaitingAffiliate } from "@/lib/moderation";

export const metadata: Metadata = { title: "Affiliate — bluntly admin" };

const TABS: AffiliateTab[] = ["transactions", "months", "imports", "links"];
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

/**
 * Admin Affiliate (Figma 8015:12542 Transactions, 8015:13183 Months,
 * 8015:13726 Imports; Import 8017:12742 and Remittance 8017:12816 overlays).
 *
 * Lifecycle (what the marketplace says happened to the order) and settlement
 * (what our ledger did about it) stay two separate axes: a completed order can
 * be not earned, and a returned one can be paid (the platform absorbs it).
 */
export default async function AffiliatePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const tab = (TABS as string[]).includes(one(sp.tab) ?? "") ? (one(sp.tab) as AffiliateTab) : "transactions";
  const size = [10, 25, 50].includes(Number(one(sp.size))) ? Number(one(sp.size)) : 10;
  const page = Math.max(1, Math.floor(Number(one(sp.page)) || 1));
  const onTx = tab === "transactions";
  const [overview, tx, months, imports, awaiting] = await Promise.all([
    getAdminOverview(),
    getAffiliateTransactions({
      q: onTx ? one(sp.q) : undefined,
      platform: onTx ? one(sp.platform) : undefined,
      status: onTx ? one(sp.status) : undefined,
      settlement: onTx ? one(sp.settlement) : undefined,
      attribution: onTx ? one(sp.attribution) : undefined,
      updated: onTx ? one(sp.updated) : undefined,
      sort: onTx ? one(sp.sort) : undefined,
      limit: onTx ? size : 1,
      offset: onTx ? (page - 1) * size : 0,
    }),
    getAffiliateMonths(),
    getAffiliateImports(),
    tab === "links" ? getAwaitingAffiliate() : Promise.resolve(null),
  ]);
  const ledger = overview?.affiliate?.has_data ? overview.affiliate : null;
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
  return (
    <AffiliateScreen
      tab={tab}
      ledger={ledger}
      tx={tx}
      months={months}
      imports={imports}
      needsLink={awaiting?.total ?? overview?.pending_affiliate ?? null}
      page={page}
      size={size}
      today={today}
    >
      {tab === "links" ? <AwaitingLinks data={awaiting} /> : null}
    </AffiliateScreen>
  );
}

import type { Metadata } from "next";

import { wantsDecidedAppeals } from "@/components/admin/list-models";
import { SellersScreen } from "@/components/admin/sellers/SellersScreen";
import { flatParams } from "@/components/console/list-query";
import { getAdminSellerAppeals, getAdminSellerClaims, getAdminStoreProducts } from "@/lib/sellers";

export const metadata: Metadata = { title: "Sellers — bluntly admin" };

/**
 * Admin Sellers: claims waiting for a decision (FR-4, Business Rules §9) and
 * appeals sellers filed against reviews of their stores (§10). Each row opens
 * a review modal with the case's chat; on an appeal, the Reviewer thread is
 * how an administrator asks the reviewer to back the review up, and their
 * reply is the substantiation that unlocks "Remove review".
 */
export default async function SellersAdminPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const query = flatParams(sp, ["tab", "sort", "reg", "market", "status", "rating", "q"]);
  const tab = query.tab === "appeals" ? "appeals" : query.tab === "links" ? "links" : "claims";
  const page = Math.max(1, Math.floor(Number(sp.page) || 1));
  const size = [10, 25, 50].includes(Number(sp.size)) ? Number(sp.size) : 10;
  const [claims, appeals, links] = await Promise.all([
    getAdminSellerClaims(),
    getAdminSellerAppeals(tab === "appeals" && wantsDecidedAppeals(query)),
    getAdminStoreProducts(),
  ]);
  return (
    <SellersScreen
      tab={tab}
      query={query}
      claims={claims}
      appeals={appeals}
      links={links}
      page={page}
      size={size}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}

import type { Metadata } from "next";

import { SellerInsights } from "@/components/seller/console/SellerInsights";
import { getStoreInsights, parsePeriod } from "@/lib/seller-console";

export const metadata: Metadata = { title: "Insights — bluntly seller" };

/**
 * Screen/Seller/Insights (Figma 8208:22905): the store's own reviews over the
 * period in the URL. The console layout has already checked the store is the
 * caller's; the API checks again.
 */
export default async function SellerInsightsPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const period = parsePeriod((await searchParams).period);
  const data = await getStoreInsights(storeId, period);
  if (!data) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-[24px] font-semibold leading-none">Insights</h1>
        <p role="alert" className="rounded-[16px] border border-[var(--border-subtle)] p-5 text-[14px] text-[var(--text-secondary)]">
          Insights couldn’t be loaded just now. Refresh the page to try again.
        </p>
      </div>
    );
  }
  return <SellerInsights storeId={storeId} data={data} />;
}

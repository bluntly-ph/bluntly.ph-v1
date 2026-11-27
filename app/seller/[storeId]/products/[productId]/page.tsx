import type { Metadata } from "next";
import Link from "next/link";

import { SellerProductAnalytics } from "@/components/seller/console/SellerProductAnalytics";
import { getStoreProductAnalytics } from "@/lib/seller-console";

export const metadata: Metadata = { title: "Product analytics — bluntly seller" };

/** Screen/Seller/Products/Analytics (Figma 8205:22802): approved links only. */
export default async function SellerProductAnalyticsPage({ params }: { params: Promise<{ storeId: string; productId: string }> }) {
  const { storeId, productId } = await params;
  const a = await getStoreProductAnalytics(storeId, productId);
  if (a === null || a === "not_linked") {
    return (
      <div className="flex max-w-[560px] flex-col gap-3">
        <h1 className="text-[24px] font-semibold leading-none">Product analytics</h1>
        <p className="text-[14px] text-[var(--text-secondary)]">
          {a === "not_linked"
            ? "This product isn’t linked to your store yet. Its analytics show once a moderator approves the link."
            : "The analytics couldn’t be loaded. Try again in a moment."}
        </p>
        <Link href={`/seller/${storeId}/products`} className="text-[14px] text-[var(--chart-honesty-fund)] hover:underline">
          Back to Products
        </Link>
      </div>
    );
  }
  return <SellerProductAnalytics storeId={storeId} a={a} />;
}

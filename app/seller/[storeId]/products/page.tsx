import type { Metadata } from "next";

import { flatParams } from "@/components/console/list-query";
import { SellerProducts } from "@/components/seller/console/SellerProducts";
import { getConsoleStores, getStoreProducts } from "@/lib/seller-console";

export const metadata: Metadata = { title: "Products — bluntly seller" };

/**
 * Screen/Seller/Products (Figma 8204:22648): the product pages this store links
 * to, a moderator's approval away from showing their figures here. The console
 * layout has already checked the store is the caller's; the API checks again.
 */
export default async function SellerProductsPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const sp = await searchParams;
  const query = flatParams(sp, ["tab", "sort", "category", "rating", "open", "q"]);
  const [data, stores] = await Promise.all([getStoreProducts(storeId), getConsoleStores()]);
  const page = Math.max(1, Math.floor(Number(Array.isArray(sp.page) ? sp.page[0] : sp.page) || 1));
  const rawSize = Number(Array.isArray(sp.size) ? sp.size[0] : sp.size);
  return (
    <SellerProducts
      storeId={storeId}
      storeName={stores.find((s) => s.id === storeId)?.display_name ?? "your store"}
      data={data}
      query={query}
      page={page}
      size={[10, 25, 50].includes(rawSize) ? rawSize : 10}
      openLink={sp.link === "1"}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}

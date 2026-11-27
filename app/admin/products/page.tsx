import type { Metadata } from "next";

import { ProductsScreen } from "@/components/admin/products/ProductsScreen";
import { getProductCatalogue, getProductQueue } from "@/lib/moderation";

export const metadata: Metadata = { title: "Products — bluntly admin" };

/**
 * Admin Products (Figma Screen/Admin/Products/Queue 7966:11087 and Catalogue
 * 7967:11173). The Queue lists submissions waiting to be named or merged; the
 * Catalogue lists named products. Both read the staff-only product endpoints.
 */
export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string; q?: string; category?: string; sort?: string; page?: string; size?: string }>;
}) {
  const sp = await searchParams;
  const tab = sp.tab === "catalogue" ? "catalogue" : "queue";
  const size = [10, 25, 50].includes(Number(sp.size)) ? Number(sp.size) : 10;
  const page = Math.max(1, Math.floor(Number(sp.page) || 1));
  const [catalogue, queue] = await Promise.all([
    getProductCatalogue({
      q: tab === "catalogue" ? sp.q : undefined,
      category: tab === "catalogue" ? sp.category : undefined,
      sort: tab === "catalogue" ? sp.sort : undefined,
      limit: tab === "catalogue" ? size : 1,
      offset: tab === "catalogue" ? (page - 1) * size : 0,
    }),
    getProductQueue(tab === "queue" && sp.sort === "newest" ? "newest" : "oldest"),
  ]);
  return (
    <ProductsScreen
      tab={tab}
      catalogue={catalogue}
      queue={queue}
      page={page}
      size={size}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}

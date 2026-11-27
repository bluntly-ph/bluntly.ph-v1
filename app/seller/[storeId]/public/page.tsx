import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PUBLIC_SORTS, SellerPublicPreview, type PublicSort } from "@/components/seller/console/SellerPublicPreview";
import { getStoreQuestions } from "@/lib/seller-console";
import { getSeller, getSellerReviews } from "@/lib/sellers";
import { getSessionToken } from "@/lib/session";

export const metadata: Metadata = { title: "Public page — bluntly seller" };

/**
 * Screen/Seller/PublicPage (Figma 8217:23574): the store's public page, read
 * inside the console. The console layout has already checked the store is the
 * caller's; everything shown here is public anyway.
 */
export default async function SellerPublicPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const raw = (await searchParams).sort;
  const sort = (PUBLIC_SORTS.find((s) => s.key === (Array.isArray(raw) ? raw[0] : raw))?.key ?? "helpful") as PublicSort;
  const token = await getSessionToken();
  const [seller, reviews, questions] = await Promise.all([
    getSeller(storeId, token),
    getSellerReviews(storeId, 100, token),
    getStoreQuestions(storeId),
  ]);
  if (!seller) notFound();
  return (
    <SellerPublicPreview
      storeId={storeId}
      seller={seller}
      reviews={reviews}
      questions={questions}
      sort={sort}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}

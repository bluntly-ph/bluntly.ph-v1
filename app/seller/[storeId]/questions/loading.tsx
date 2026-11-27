import { SELLER_LISTS, SellerListSkeleton } from "@/components/seller/console/SellerSkeletons";

/** Screen/Seller/Questions/Loading (Figma 8228:25961), inside the real rail. */
export default function Loading() {
  return <SellerListSkeleton spec={SELLER_LISTS.questions} />;
}

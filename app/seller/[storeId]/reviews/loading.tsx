import { SELLER_LISTS, SellerListSkeleton } from "@/components/seller/console/SellerSkeletons";

/** Screen/Seller/Reviews/Loading (Figma 8228:25327), inside the real rail. */
export default function Loading() {
  return <SellerListSkeleton spec={SELLER_LISTS.reviews} />;
}

import { SELLER_LISTS, SellerListSkeleton } from "@/components/seller/console/SellerSkeletons";

/** Screen/Seller/Appeals/Loading (Figma 8228:26321), inside the real rail. */
export default function Loading() {
  return <SellerListSkeleton spec={SELLER_LISTS.appeals} />;
}

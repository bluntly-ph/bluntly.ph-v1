import { SELLER_LISTS, SellerListSkeleton } from "@/components/seller/console/SellerSkeletons";

/** Screen/Seller/Products/Loading (Figma 8228:26685), inside the real rail. */
export default function Loading() {
  return <SellerListSkeleton spec={SELLER_LISTS.products} />;
}

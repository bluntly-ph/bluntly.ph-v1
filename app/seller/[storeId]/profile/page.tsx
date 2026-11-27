import type { Metadata } from "next";

import { SellerStoreProfile } from "@/components/seller/console/SellerStoreProfile";
import { getConsoleStores, getMyClaims, getStoreChanges, getStoreProfile } from "@/lib/seller-console";

export const metadata: Metadata = { title: "Store profile — bluntly seller" };

/**
 * Screen/Seller/StoreProfile (Figma 8209:23011). The console layout has already
 * checked the store is the caller's; the API checks again.
 */
export default async function SellerStoreProfilePage({ params }: { params: Promise<{ storeId: string }> }) {
  const { storeId } = await params;
  const [profile, stores, claims, changes] = await Promise.all([
    getStoreProfile(storeId),
    getConsoleStores(),
    getMyClaims(),
    getStoreChanges(storeId),
  ]);
  if (!profile) {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-[24px] font-semibold leading-none">Store profile</h1>
        <p role="alert" className="rounded-[16px] border border-[var(--border-subtle)] p-5 text-[14px] text-[var(--text-secondary)]">
          The store profile couldn’t be loaded just now. Refresh the page to try again.
        </p>
      </div>
    );
  }
  return (
    <SellerStoreProfile
      profile={profile}
      changes={changes}
      stores={stores.map((s) => ({ id: s.id, name: s.display_name, platform: s.platform }))}
      claims={claims
        .filter((c) => c.status === "pending")
        .map((c) => ({ id: c.id, storeName: c.seller_display_name ?? "Store", platform: c.seller_platform ?? "other" }))}
    />
  );
}

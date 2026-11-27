import { SellerSettings } from "@/components/seller/console/SellerSettings";
import { requireOnboardedUser } from "@/lib/dal";
import { getConsoleStores, getMyClaims, getNotificationPrefs } from "@/lib/seller-console";

/** Screen/Seller/Settings (Figma 8218:24151). The layout has already checked ownership. */
export default async function SellerSettingsPage({ params }: { params: Promise<{ storeId: string }> }) {
  const { storeId } = await params;
  const [me, stores, claims, prefs] = await Promise.all([requireOnboardedUser(), getConsoleStores(), getMyClaims(), getNotificationPrefs()]);
  const store = stores.find((s) => s.id === storeId);
  return (
    <SellerSettings
      storeId={storeId}
      storeName={store?.display_name ?? "your store"}
      prefs={prefs}
      stores={stores.map((s) => s.display_name)}
      inReview={claims.filter((c) => c.status === "pending").map((c) => c.seller_display_name ?? "Store")}
      me={{ displayName: me.display_name, username: me.username, email: me.email, joined: me.created_at, avatarUrl: me.avatar_url, hasPassword: Boolean(me.has_password) }}
    />
  );
}

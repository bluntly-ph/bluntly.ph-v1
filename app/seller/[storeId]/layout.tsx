import type { Metadata } from "next";
import Link from "next/link";

import { SellerShell } from "@/components/seller/console/SellerShell";
import { requireOnboardedUser } from "@/lib/dal";
import { getMyUnread } from "@/lib/messages";
import { getConsoleDashboard, getConsoleStores, getMyClaims, getUnreadCount } from "@/lib/seller-console";

export const metadata: Metadata = { title: "Seller console — bluntly" };

/**
 * The Seller console (Figma Screen/Seller/*): one store's workspace, for its
 * approved owner only. Ownership is the API's: the store must be in
 * GET /sellers/mine, and every screen reads owner-only endpoints that re-check
 * it (403 not_store_owner) — this layout only decides what to draw.
 */
export default async function SellerConsoleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ storeId: string }>;
}) {
  const { storeId } = await params;
  const me = await requireOnboardedUser();
  const [stores, claims] = await Promise.all([getConsoleStores(), getMyClaims()]);
  const store = stores.find((s) => s.id === storeId);
  if (!store) {
    return (
      <main className="mx-auto flex min-h-dvh max-w-[36rem] flex-col justify-center gap-3 px-6">
        <h1 className="text-[22px] font-semibold">This isn&rsquo;t your store</h1>
        <p className="text-[14px] text-[var(--text-secondary)]">
          Only a store&rsquo;s approved owner can open its console. If you run this store, claim it from its page; an
          administrator checks every claim against your DTI or SEC registration.
        </p>
        <p className="flex gap-4 text-[14px]">
          <Link href="/seller/dashboard" className="text-[var(--accent-primary)] hover:underline">
            Your stores
          </Link>
          <Link href={`/sellers/${storeId}`} className="text-[var(--accent-primary)] hover:underline">
            The store&rsquo;s public page
          </Link>
        </p>
      </main>
    );
  }
  const [dash, unread, messagesUnread] = await Promise.all([
    getConsoleDashboard(storeId),
    getUnreadCount(),
    getMyUnread(storeId),
  ]);
  const d = dash.ok ? dash.dashboard : null;
  const counts = {
    reviews: d?.analytics?.reviews_awaiting_response ?? 0,
    questions: d?.unanswered_questions ?? 0,
    appeals: d?.analytics?.appeals_open ?? 0,
  };
  const pending = claims
    .filter((c) => c.status === "pending")
    .map((c) => ({
      id: c.id,
      storeName: c.seller_display_name ?? "Store",
      platform: c.seller_platform ?? "other",
      status: c.status,
      createdAt: c.created_at,
      registrationKind: c.registration_kind ?? null,
      registrationNumber: c.registration_number ?? null,
      businessName: c.registered_business_name ?? null,
      shopName: c.marketplace_shop_name ?? null,
    }));
  return (
    <SellerShell
      store={{ id: store.id, name: store.display_name, platform: store.platform }}
      stores={stores.map((s) => ({ id: s.id, name: s.display_name, platform: s.platform }))}
      claims={pending}
      counts={counts}
      viewer={me.display_name ?? me.username ?? "you"}
      unread={unread}
      messagesUnread={messagesUnread}
    >
      {children}
    </SellerShell>
  );
}

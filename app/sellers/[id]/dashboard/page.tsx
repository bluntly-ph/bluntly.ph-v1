import { redirect } from "next/navigation";

/**
 * The store dashboard moved into the Seller console (Figma Screen/Seller/Overview,
 * 2026-10-03). This address stays valid — claim-approval notifications and old
 * bookmarks point here — and the console checks ownership as this page did.
 */
export default async function StoreDashboardRedirect({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/seller/${encodeURIComponent(id)}`);
}

import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getMyStores } from "@/lib/sellers";
import { getMyClaims } from "@/lib/seller-console";

export const metadata: Metadata = { title: "Seller dashboard — bluntly" };

/**
 * `/seller/dashboard` (owner decision 2026-09-28): the claimed seller's way in.
 *
 * It opens the Seller console (`/seller/{id}`, Figma Screen/Seller/*) on the
 * account's first store — the console's store switcher reaches the others.
 * Without a store it says how to claim one, and where a claim in review stands.
 */
export default async function SellerDashboardEntry() {
  const me = await requireOnboardedUser();
  const [stores, claims] = await Promise.all([getMyStores(), getMyClaims()]);
  if (stores.length >= 1) redirect(`/seller/${stores[0].id}`);
  const inReview = claims.filter((c) => c.status === "pending");

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      <main className="mx-auto w-full min-w-0 max-w-[44rem] flex-1 px-4 py-8 md:px-6">
        <h1 className="text-[22px] font-bold text-[var(--text-primary)]">Seller dashboard</h1>
        {inReview.length ? (
          <ul className="mt-4 flex flex-col gap-2" aria-label="Claims in review">
            {inReview.map((c) => (
              <li key={c.id} className="rounded-[12px] bg-[var(--surface-card)] px-4 py-3 text-[14px] shadow-[var(--shadow-card)]">
                <span className="font-semibold">{c.seller_display_name}</span>{" "}
                <span className="text-[var(--text-muted)]">· {c.seller_platform} · in review</span>
                <span className="block text-[12px] text-[var(--text-secondary)]">
                  An administrator is checking your registration; you&rsquo;ll be notified either way.
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {stores.length === 0 ? (
          <p className="mt-3 text-[14px] text-[var(--text-secondary)]">
            You don&rsquo;t run a claimed store yet. Find your store on{" "}
            <Link href="/search?tab=sellers" className="text-[var(--accent-primary)] hover:underline">
              Sellers
            </Link>{" "}
            and claim it from its page; an administrator checks every claim against your DTI or SEC
            registration.
          </p>
        ) : (
          <ul className="mt-4 flex flex-col gap-2">
            {stores.map((s) => (
              <li key={s.id}>
                <Link
                  href={`/seller/${s.id}`}
                  className="block rounded-[12px] bg-[var(--surface-card)] px-4 py-3 text-[14px] font-semibold text-[var(--text-primary)] shadow-[var(--shadow-card)] hover:text-[var(--accent-primary)]"
                >
                  {s.display_name} <span className="font-normal text-[var(--text-muted)]">· {s.platform}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}

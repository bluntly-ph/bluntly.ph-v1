import type { Metadata } from "next";

import { DashboardBar } from "@/components/dashboard/DashboardBar";
import { ParentLink } from "@/components/dashboard/DashboardParts";
import { PayoutDetailsForm } from "@/components/dashboard/PayoutDetailsForm";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getPayoutBalance } from "@/lib/dashboard";
import { trustLevel } from "@/lib/trust";

export const metadata: Metadata = { title: "Payout details — bluntly" };

/** Screen/Payout/Details (Figma 7843:9432), reached from Payout's "Change". */
export default async function PayoutDetailsPage() {
  const me = await requireOnboardedUser();
  const balance = await getPayoutBalance();
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <DashboardBar backHref="/dashboard/transfer" trustLevel={trustLevel(me.trust_level_name, me.trust_stage)} />
      </div>
      <main className="mx-auto flex w-full max-w-[390px] flex-1 flex-col md:max-w-[480px] md:pt-8">
        <div className="px-4">
          <ParentLink href="/dashboard/transfer" label="Payout" />
        </div>
        <h1 className="px-5 pb-4 text-[24px] font-semibold leading-none text-[var(--text-primary)]">Payout details</h1>
        <PayoutDetailsForm masked={balance?.payout_account_masked ?? null} accountName={balance?.payout_account_name ?? null} />
      </main>
    </div>
  );
}

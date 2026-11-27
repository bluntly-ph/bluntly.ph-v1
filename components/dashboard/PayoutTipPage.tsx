import Link from "next/link";

import { DashboardBar } from "@/components/dashboard/DashboardBar";
import { ParentLink } from "@/components/dashboard/DashboardParts";
import { SiteHeader } from "@/components/site/SiteHeader";
import type { SessionUser } from "@/lib/dal";
import { trustLevel } from "@/lib/trust";


/**
 * The shell shared by the Payout tips (Figma 7844:9469, 7844:9529, 7843:9501):
 * back to Payout, a title with one line of why, the cards, and one action
 * pinned to the bottom.
 */
export function PayoutTipPage({
  me,
  title,
  lead,
  action,
  children,
}: {
  me: SessionUser;
  title: string;
  lead: string;
  action?: { href: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <DashboardBar backHref="/dashboard/transfer" trustLevel={trustLevel(me.trust_level_name, me.trust_stage)} />
      </div>
      <main className="mx-auto flex w-full max-w-[390px] flex-1 flex-col md:max-w-[480px] md:pt-8">
        <div className="flex flex-col gap-3 px-4 pb-4">
          <ParentLink href="/dashboard/transfer" label="Payout" />
          <div className="flex flex-col gap-2 px-1">
            <h1 className="text-[24px] font-semibold leading-[1.2] text-[var(--text-primary)]">{title}</h1>
            <p className="text-[14px] leading-[1.4] text-[var(--base-gray-400)]">{lead}</p>
          </div>
          {children}
        </div>
        <div className="flex-1" />
        {action ? (
          <div className="sticky bottom-0 bg-[var(--surface-card)] px-4 pb-6 pt-2">
            <Link
              href={action.href}
              className="flex h-14 w-full items-center justify-center rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-6 text-[16px] font-semibold leading-none text-[var(--text-on-brand)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
            >
              {action.label}
            </Link>
          </div>
        ) : null}
      </main>
    </div>
  );
}

export function TipCard({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={label} className="w-full rounded-[32px] bg-[var(--surface-app)] p-[3px]">
      <div className={`w-full rounded-[32px] bg-[var(--surface-card)] px-5 py-4 ${className}`}>
        <h2 className="mb-2 text-[12px] font-normal leading-normal text-[var(--chart-honesty-fund)]">{label}</h2>
        {children}
      </div>
    </section>
  );
}

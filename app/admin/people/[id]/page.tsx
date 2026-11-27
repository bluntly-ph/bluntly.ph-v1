import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PersonInvestigation } from "@/components/admin/people/PersonInvestigation";
import { getSuperAdminAccess } from "@/lib/dal";
import { getPersonInvestigation } from "@/lib/moderation";

export const metadata: Metadata = {
  title: "Person — bluntly admin",
};

const TABS = ["overview", "activity", "interactions", "reports", "moderation"] as const;
type Tab = (typeof TABS)[number];

/**
 * A member's investigation page (Figma Screen/Admin/People/Person and tabs,
 * meeting 2026-10-02). Staff only: the admin layout checks the role and the
 * API refuses anyone else.
 */
export default async function PersonPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";
  const range = one(sp.range) === "6M" ? "6M" : one(sp.range) === "1Y" ? "1Y" : "1M";
  const rawTab = one(sp.tab);
  const tab: Tab = (TABS as readonly string[]).includes(rawTab) ? (rawTab as Tab) : "overview";

  const [{ data, status, fetchedAt }, access] = await Promise.all([getPersonInvestigation(id, range), getSuperAdminAccess()]);
  if (status === 404 || status === 422) notFound();
  if (!data) {
    return (
      <p role="alert" className="text-[14px] text-[var(--text-secondary)]">
        This member&apos;s record could not be loaded. Nothing has changed; try again in a moment.
      </p>
    );
  }
  return <PersonInvestigation data={data} tab={tab} now={fetchedAt} canSuspend={access.allowed} />;
}

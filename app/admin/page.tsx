import type { Metadata } from "next";

import { ActivityCard } from "@/components/admin/overview/ActivityCard";
import { AffiliateEarningsCard } from "@/components/admin/overview/AffiliateEarningsCard";
import { InboxCard } from "@/components/admin/overview/InboxCard";
import { NeedsAttentionCard } from "@/components/admin/overview/NeedsAttentionCard";
import { PayoutCycleCard } from "@/components/admin/overview/PayoutCycleCard";
import { ReviewQueueCard } from "@/components/admin/overview/ReviewQueueCard";
import { getActivityEntries } from "@/lib/activity-admin";
import { getInbox } from "@/lib/messages";
import { getHonestyFundCycles, getOverviewPanels, getPayoutSummary, type EarningsRange } from "@/lib/moderation";
import { getAdminSettings } from "@/lib/settings-admin";

export const metadata: Metadata = {
  title: "Overview — bluntly admin",
};

/**
 * The Overview, built to "Screen/Admin/Overview v4" (8444:38623, read
 * 2026-10-05; v3 7879:10223 before it): actionable items first.
 *
 *   Row/Top     Review queue (394px) beside Needs attention
 *   Row/Middle  Inbox (394px) beside Recent team activity
 *   Row/Money   Affiliate earnings beside This payout cycle (300px)
 *
 * Every figure is read from the API; nothing from the frame's sample values.
 * Each card fetches on its own and fails on its own: one panel's outage says
 * so in that panel and leaves the others standing. Traffic geography, which an
 * older Overview carried, lives on Analytics (footer of the rail).
 */
export default async function AdminOverviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const raw = Array.isArray(params.range) ? params.range[0] : params.range;
  const range: EarningsRange = raw === "1M" || raw === "1Y" ? raw : "6M";

  const [{ preview, attention, earnings, fetchedAt }, inbox, activity, payouts, settings, fund] = await Promise.all([
    getOverviewPanels(range),
    getInbox({ tab: "all", topic: "", status: "open", handled: "", q: "", sort: "waiting", page: 1, size: 3 }),
    getActivityEntries({}, 5),
    getPayoutSummary(),
    getAdminSettings(),
    getHonestyFundCycles(),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 xl:grid-cols-[394px_minmax(0,1fr)]">
        <ReviewQueueCard tabs={preview} now={fetchedAt} />
        <NeedsAttentionCard groups={attention} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[394px_minmax(0,1fr)]">
        <InboxCard data={inbox ? { items: inbox.items, total: inbox.total } : null} now={fetchedAt} />
        <ActivityCard rows={activity?.rows ?? null} now={fetchedAt} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <AffiliateEarningsCard data={earnings} range={range} />
        <PayoutCycleCard
          summary={payouts}
          payoutDay={settings?.payout_day ?? null}
          payoutMinimum={settings?.payout_minimum ?? null}
          fund={fund ? { pool: fund.current.pool, distributes_on: fund.distributes_on } : null}
          now={fetchedAt}
        />
      </div>
    </div>
  );
}

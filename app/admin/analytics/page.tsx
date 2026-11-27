import type { Metadata } from "next";

import { AnalyticsScreen } from "@/components/admin/analytics/AnalyticsScreen";
import { RequestDistribution } from "@/components/analytics/RequestDistribution";
import { getAnalyticsSummary } from "@/lib/analytics-admin";

export const metadata: Metadata = { title: "Analytics — bluntly admin" };

const RANGES = ["7d", "30d", "90d", "12m"];

/**
 * Admin Analytics (Figma Screen/Admin/Analytics 8071:16115): key figures
 * against the period before, reviews per day, the review-to-commission
 * funnel, moderation, community, top products, reader cities and the
 * integrity sweep's open findings — all counted from recorded rows. The
 * request-location detail (edge-resolved, no IPs, 90 days) stays below.
 */
export default async function AnalyticsPage({ searchParams }: { searchParams: Promise<{ range?: string }> }) {
  const sp = await searchParams;
  const range = RANGES.includes(sp.range ?? "") ? (sp.range as string) : "30d";
  const data = await getAnalyticsSummary(range);
  // eslint-disable-next-line react-hooks/purity -- a server render's clock, read once.
  const now = Date.now();
  return (
    <AnalyticsScreen data={data} range={range} now={now}>
      <details className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4">
        <summary className="cursor-pointer text-[14px] font-medium">Request detail by location</summary>
        <div className="mt-3">
          <RequestDistribution />
        </div>
      </details>
    </AnalyticsScreen>
  );
}

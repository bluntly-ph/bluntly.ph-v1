import type { Metadata } from "next";

import { ActivityScreen } from "@/components/admin/activity/ActivityScreen";
import { getActivityEntries, getActivitySummary } from "@/lib/activity-admin";
import { getSuperAdminAccess } from "@/lib/dal";
import { getSchedulerHealth } from "@/lib/moderation";

export const metadata: Metadata = { title: "Activity log — bluntly admin" };

const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";

/**
 * The full audit log (Figma Screen/Admin/ActivityLog 8074:16245).
 *
 * The Overview's feed shows five entries and deliberately omits `receipt_view`,
 * which records an administrator opening someone's proof of purchase. That
 * omission is about not advertising private-evidence access as routine
 * activity in a dashboard; the audit log is where the complete record belongs,
 * and its "Proof-of-purchase views" card lists them on purpose.
 */
export default async function ActivityLogPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const range = ["today", "7d", "30d", "all"].includes(one(sp.range)) ? one(sp.range) : "7d";
  const limit = Math.min(200, Math.max(50, Number.parseInt(one(sp.limit), 10) || 50));
  const filters = { actor: one(sp.actor), action: one(sp.action), target: one(sp.target), range, q: one(sp.q).slice(0, 120) };
  const [log, summary, scheduler, access] = await Promise.all([
    getActivityEntries(filters, limit),
    getActivitySummary(),
    getSchedulerHealth(),
    getSuperAdminAccess(),
  ]);
  return (
    <ActivityScreen
      entries={log?.rows ?? null}
      total={log?.total ?? 0}
      summary={summary}
      tasks={scheduler?.tasks ?? null}
      limit={limit}
      canRunAll={access.allowed}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}

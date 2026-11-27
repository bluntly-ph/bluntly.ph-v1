import type { Metadata } from "next";

import { SpecialRoutingQueue } from "@/components/admin/SpecialRoutingQueue";
import { SuperAdminOnly } from "@/components/admin/SuperAdminOnly";
import { getSuperAdminAccess } from "@/lib/dal";
import { getReports } from "@/lib/moderation";
import { getSpecialRoutingHistory, getSpecialRoutingQueue } from "@/lib/special-routing";

export const metadata: Metadata = { title: "Special routing — bluntly admin" };

/**
 * The Super Admin's 2.5-star "It depends" routing queue (owner decision A),
 * drawn to Figma Screen/Admin/SpecialRouting 8178:20045.
 */
export default async function SpecialRoutingPage() {
  const { allowed } = await getSuperAdminAccess();
  if (!allowed) return <SuperAdminOnly what="Routing 2.5-star It depends reviews" />;
  const [items, history, escalated] = await Promise.all([
    getSpecialRoutingQueue(),
    getSpecialRoutingHistory(),
    // The frame's "Escalated reports" tab: the reports an Administrator sent up.
    getReports("status=escalated&limit=1"),
  ]);
  // eslint-disable-next-line react-hooks/purity -- a server render's clock, read once.
  const now = Date.now();
  return <SpecialRoutingQueue items={items} history={history} now={now} escalatedReports={escalated.total} />;
}

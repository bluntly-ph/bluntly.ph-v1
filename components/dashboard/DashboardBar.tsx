import { getMyUnread } from "@/lib/messages";

import { DashboardNav } from "./DashboardScreen";

/**
 * The white dashboard bar with its Chat link, for the pages under /dashboard.
 * Figma draws the Chat link (24px ChatCircleDots, the brand dot while anything
 * is unread) on Screen/Dashboard 7833:9536 and on every screen it leads to:
 * Payout 7840:9380 and Locked 7840:9462, History 8098:17238, Performance
 * 7848:9542. The unread count is read here so each page does not have to.
 */
export async function DashboardBar({ backHref, trustLevel }: { backHref: string; trustLevel: string }) {
  const unread = await getMyUnread();
  return <DashboardNav backHref={backHref} trustLevel={trustLevel} tone="light" unread={unread} />;
}

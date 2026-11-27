import { Suspense } from "react";

import { AdminShell } from "@/components/admin/AdminShell";
import { requireStaff } from "@/lib/dal";
import { getInboxUnread } from "@/lib/messages";
import { getActivityLog, getNeedsAttention } from "@/lib/moderation";

/**
 * The Administrator console's shell wraps every /admin route (owner decisions
 * B-D, 2026-09-28; /moderate redirects here).
 *
 * It lives in a layout rather than in each page so the rail and top bar are
 * not torn down and rebuilt on navigation: moving between Overview and the
 * Queue changes only the workspace.
 *
 * The role check is here too, so every child route inherits it and none can be
 * added later that forgets it.
 */
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Redirects: to /login if signed out, to / unless an Administrator or a
  // Super Admin. Super Admin sections check again (getSuperAdminAccess).
  const me = await requireStaff();
  const [groups, activity, inboxUnread] = await Promise.all([
    getNeedsAttention(),
    getActivityLog(20),
    getInboxUnread(),
  ]);

  // The rail's pills, keyed like the Overview's "Needs attention" rows. A count
  // the backend could not compute stays null and draws no pill.
  const attention = {
    ...Object.fromEntries((groups ?? []).flatMap((g) => g.items.map((i) => [i.key, i.count]))),
    inbox_unread: inboxUnread,
  };

  return (
    <Suspense fallback={null}>
      <AdminShell
        attention={attention}
        inboxUnread={inboxUnread}
        activity={activity?.rows ?? null}
        // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
        activityFetchedAt={Date.now()}
        viewer={{
          name: me.display_name ?? me.username ?? "Administrator",
          role: me.role,
        }}
      >
        {children}
      </AdminShell>
    </Suspense>
  );
}

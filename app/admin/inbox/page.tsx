import type { Metadata } from "next";

import { InboxScreen } from "@/components/admin/inbox/InboxScreen";
import { requireStaff } from "@/lib/dal";
import { getInbox, getInboxConversation, getInboxStaff, parseInboxQuery } from "@/lib/messages";

export const metadata: Metadata = { title: "Inbox — bluntly admin" };

/**
 * Screen/Admin/Inbox (Figma 8291:30461): sellers and reviewers writing to the
 * Bluntly team. The list and the open conversation are the URL; opening one
 * marks it read for the whole team (GET /admin/inbox/{id}).
 */
export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const me = await requireStaff();
  const sp = await searchParams;
  const query = parseInboxQuery(sp);
  const asked = (Array.isArray(sp.c) ? sp.c[0] : sp.c) ?? "";
  const [list, staff] = await Promise.all([getInbox(query), getInboxStaff()]);
  // As drawn: the newest conversation is open when none is named.
  const selectedId = asked || list?.items[0]?.id || null;
  const conversation = selectedId ? await getInboxConversation(selectedId) : null;
  return (
    <InboxScreen
      list={list}
      query={query}
      conversation={conversation}
      selectedId={selectedId}
      explicit={!!asked}
      staff={staff}
      me={{ id: me.id, name: me.display_name ?? me.username ?? "you" }}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}

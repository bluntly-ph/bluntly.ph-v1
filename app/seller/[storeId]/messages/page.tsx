import type { Metadata } from "next";

import { SellerMessages } from "@/components/messages/MemberMessages";
import type { Topic } from "@/components/messages/messages-model";
import { requireOnboardedUser } from "@/lib/dal";
import { getLinkOptions, getMyConversation, getMyConversations } from "@/lib/messages";

export const metadata: Metadata = { title: "Messages — bluntly seller" };

const TOPICS = new Set(["appeal", "claim", "product", "account", "other"]);

/**
 * Screen/Seller/Inbox (Figma 8304:32524): the store owner and the Bluntly
 * team. The console layout has already checked this is the caller's store; the
 * API checks it again on every read (owner only).
 */
export default async function SellerMessagesPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";
  const status = one(sp.status) === "closed" ? "closed" : "open";
  const asked = one(sp.c);
  const me = await requireOnboardedUser();
  const [list, options] = await Promise.all([getMyConversations(status, storeId), getLinkOptions("seller", storeId)]);
  const selectedId = asked || list?.items[0]?.id || null;
  const conversation = selectedId ? await getMyConversation(selectedId) : null;
  const topic = one(sp.topic);
  return (
    <SellerMessages
      storeId={storeId}
      status={status}
      list={list}
      conversation={conversation}
      selectedId={selectedId}
      explicit={!!asked}
      options={options}
      me={{ id: me.id }}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
      compose={one(sp.new) ? { topic: TOPICS.has(topic) ? (topic as Topic) : undefined, link: one(sp.link) || undefined } : null}
    />
  );
}

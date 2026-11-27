import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { MessagesNav, MessagesRail, ReviewerThread } from "@/components/messages/ReviewerMessages";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getMyConversation, getMyConversations } from "@/lib/messages";

export const metadata: Metadata = { title: "Conversation — bluntly" };

/**
 * Screen/Messages/Thread (Figma 8296:31305): one of your conversations with the
 * team. Someone else's is a 404 from the API, so it is a 404 here.
 */
export default async function ConversationPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ status?: string }>;
}) {
  const me = await requireOnboardedUser();
  const { id } = await params;
  const conversation = await getMyConversation(id);
  if (!conversation) notFound();
  // MQA-031: the list beside it on a wide screen, on the side it belongs to.
  const asked = (await searchParams).status;
  const status = asked === "closed" || (!asked && conversation.status === "closed") ? "closed" : "open";
  const list = await getMyConversations(status);
  return (
    <div className="flex h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <MessagesNav backHref="/messages" avatarUrl={me.avatar_url ?? null} name={me.display_name ?? me.username ?? "You"} />
      </div>
      <main className="mx-auto flex min-h-0 w-full max-w-[480px] flex-1 flex-col md:pt-6 lg:max-w-[1120px] lg:flex-row lg:gap-6 lg:px-6 lg:pb-6">
        <aside className="hidden min-h-0 lg:flex lg:w-[340px] lg:shrink-0 lg:flex-col">
          {/* eslint-disable-next-line react-hooks/purity -- read once per request, on the server */}
          <MessagesRail status={status} list={list} activeId={conversation.id} now={Date.now()} />
        </aside>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col lg:rounded-[16px] lg:border lg:border-[var(--border-subtle)] lg:pt-4">
          {/* eslint-disable-next-line react-hooks/purity -- read once per request, on the server */}
          <ReviewerThread conversation={conversation} me={{ id: me.id }} now={Date.now()} />
        </div>
      </main>
    </div>
  );
}

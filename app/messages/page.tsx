import type { Metadata } from "next";

import { MessagesNav, MessagesRail, ReviewerMessagesList } from "@/components/messages/ReviewerMessages";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getMyConversations } from "@/lib/messages";

export const metadata: Metadata = { title: "Messages — bluntly" };

/** Screen/Messages (Figma 8296:31219, Empty 8296:31548): you and the Bluntly team. */
export default async function MessagesPage({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  const me = await requireOnboardedUser();
  const status = (await searchParams).status === "closed" ? "closed" : "open";
  const list = await getMyConversations(status);
  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <MessagesNav backHref="/dashboard" avatarUrl={me.avatar_url ?? null} name={me.display_name ?? me.username ?? "You"} />
      </div>
      {/* MQA-031: from lg, the list on the left and the conversation on the
          right (picking one opens /messages/<id> with the list still beside
          it); below lg, the phone frame's single column. */}
      <main className="mx-auto flex w-full max-w-[480px] flex-1 flex-col md:pt-8 lg:max-w-[1120px] lg:flex-row lg:gap-6 lg:px-6 lg:pb-8">
        <aside className="hidden lg:flex lg:w-[340px] lg:shrink-0 lg:flex-col">
          {/* eslint-disable-next-line react-hooks/purity -- read once per request, on the server */}
          <MessagesRail status={status} list={list} activeId={null} now={Date.now()} />
        </aside>
        <div className="flex flex-1 flex-col lg:hidden">
          {/* eslint-disable-next-line react-hooks/purity -- read once per request, on the server */}
          <ReviewerMessagesList status={status} list={list} now={Date.now()} />
        </div>
        <section aria-label="Conversation" className="hidden flex-1 flex-col items-center justify-center gap-2 rounded-[16px] border border-[var(--border-subtle)] p-8 text-center lg:flex">
          <p className="text-[16px] font-semibold">{list?.items.length ? "Pick a conversation" : "Start a conversation"}</p>
          <p className="max-w-[320px] text-[12px] text-[var(--text-secondary)]">
            {list?.items.length ? "It opens here, with your list beside it." : "Use New message. We reply within 1 business day."}
          </p>
        </section>
      </main>
    </div>
  );
}
